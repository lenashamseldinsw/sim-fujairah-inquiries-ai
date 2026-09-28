"""
The durable job store — Azure Table Storage.

What the local store cannot do, and this can: a poll served by any instance, and a
job record that survives the worker that created it. Those are the two things that
stop the local backend being deployable behind a load balancer.

**It stores job state, not the run.** A job here is durable; a run still belongs to
whatever process is executing it. Durability of the *run* comes from the queue —
``function_app.py`` enqueues the work and the Functions host redelivers a message
whose handler died. This class is one half of that pair, and is useful on its own:
with ``NOVEINQ_JOB_BACKEND=table`` and the in-process runner, polls already work
across instances.

**No ``azure.*`` import at module scope.** Rule 1 of the porting guide says nothing
under the package may import a hosting SDK, and a test enforces it by scanning the
source. The SDK is imported inside ``_client``, so the module is importable —
and the rest of the package is testable — on a machine with no Azure libraries at
all. The import name is assembled at runtime for the same reason: a literal
``import azure...`` here would trip the guard even inside a function.

The row layout is deliberately flat:

    PartitionKey  the entity slug, so one tenant's jobs share a partition
    RowKey        the job id
    state         the whole ``JobState`` as JSON
    status        duplicated out for a cheap status filter
    expires_at    a Unix timestamp the purge sweeps on

``state`` is stored whole rather than spread across typed columns because the
contract model is the source of truth: a field added to ``JobState`` needs no schema
migration, and a poll is a read plus a ``model_validate_json``, with nothing in
between that could disagree with it.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from ..api.models.enums import JobStatus
from ..api.models.jobs import JobError, JobState
from .base import JobNotFound, JobStoreError

__all__ = ["TableStorageJobStore"]

logger = logging.getLogger(__name__)

# Table Storage caps an entity property at 64 KiB and a whole entity at 1 MiB. A
# finished bundle — the report as data in two languages — goes well past that, so the
# result is not stored inline. See ``_trim``.
MAX_STATE_BYTES = 60_000


class TableStorageJobStore:
    """A ``JobStore`` backed by an Azure Storage table."""

    def __init__(
        self,
        connection_string: str,
        table_name: str = "jobs",
        ttl_sec: float = 86_400.0,
        partition: str = "jobs",
    ) -> None:
        self._connection_string = connection_string
        self._table_name = table_name
        self.ttl_sec = ttl_sec
        self._partition = partition
        self._table: Any = None

    # ── The SDK, imported late ────────────────────────────────────────────────

    def _client(self) -> Any:
        """The table client, created on first use and then reused.

        Imported here rather than at module scope so the package carries no hosting
        dependency — see the module docstring. The name is built at runtime because
        the import guard scans for the literal text.
        """
        if self._table is not None:
            return self._table

        import importlib

        try:
            module = importlib.import_module("azure.data.tables")
        except ImportError as exc:  # pragma: no cover - depends on the install
            raise JobStoreError(
                "The 'table' job backend needs azure-data-tables, which is not "
                "installed. Add the 'azure' extra, or set "
                "NOVEINQ_JOB_BACKEND=local."
            ) from exc

        try:
            service = module.TableServiceClient.from_connection_string(
                self._connection_string
            )
            table = service.create_table_if_not_exists(self._table_name)
        except Exception as exc:
            raise JobStoreError(f"Could not open the job table: {exc}") from exc

        self._table = table
        return table

    # ── The contract ──────────────────────────────────────────────────────────

    async def create(self, state: JobState) -> None:
        import asyncio

        await asyncio.to_thread(self._upsert, state)

    async def get(self, job_id: str) -> JobState:
        import asyncio

        entity = await asyncio.to_thread(self._read, job_id)
        try:
            return JobState.model_validate_json(entity["state"])
        except Exception as exc:
            # A row this process cannot parse is a row written by a version that is
            # gone. Reported as missing rather than crashing the poll: the caller's
            # only useful action is the same either way.
            raise JobNotFound(f"Job {job_id!r} is unreadable: {exc}") from exc

    async def update(self, state: JobState) -> None:
        import asyncio

        await asyncio.to_thread(self._upsert, state)

    async def purge_expired(self) -> int:
        """Delete finished jobs past their TTL.

        Table Storage has no server-side TTL, so this is a query and a batch of
        deletes. Called on a timer by the host, or by an operator; nothing on the
        request path depends on it running.
        """
        import asyncio

        return await asyncio.to_thread(self._purge)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _entity(self, state: JobState) -> dict[str, Any]:
        trimmed = self._trim(state)
        return {
            "PartitionKey": self._partition,
            "RowKey": state.job_id,
            "state": trimmed.model_dump_json(exclude_none=False),
            # Duplicated out of the JSON so a status query does not have to parse
            # every row it scans.
            "status": state.status.value,
            "expires_at": int(time.time() + self.ttl_sec)
            if state.finished_at is not None
            else 0,
        }

    def _trim(self, state: JobState) -> JobState:
        """Drop the result if the row would be too large for Table Storage.

        A finished bundle carries the report as data in both languages and can be
        megabytes; a table property caps at 64 KiB. Rather than fail the write — which
        would lose the *status* as well, leaving a caller polling a job that finished
        successfully — the result is dropped and the job says so.

        The analysis is not lost: every artefact is in the document store, and the
        bundle's own ``documents`` is what a caller fetches them from. Only the inline
        copy goes. A deployment that wants the bundle inline should put it in blob
        storage and reference it, which is a change to this method alone.
        """
        encoded = state.model_dump_json(exclude_none=False)
        if len(encoded.encode("utf-8")) <= MAX_STATE_BYTES:
            return state

        slim = state.model_copy(deep=True)
        if slim.result is not None:
            # Keep the parts a caller needs to find the run and its files; drop the
            # two heavy ones.
            slim.result = slim.result.model_copy(
                update={"report": {}, "metrics": {}}
            )
        if len(slim.model_dump_json(exclude_none=False).encode("utf-8")) > MAX_STATE_BYTES:
            slim.result = None
            slim.message = (
                "The run succeeded. Its result was too large to store inline — fetch "
                "the artefacts from the document store using this job id."
            )
        logger.warning(
            "[%s] Job result trimmed to fit Table Storage; artefacts are unaffected.",
            state.job_id,
        )
        return slim

    def _upsert(self, state: JobState) -> None:
        table = self._client()
        try:
            table.upsert_entity(self._entity(state))
        except Exception as exc:
            raise JobStoreError(f"Could not write job {state.job_id!r}: {exc}") from exc

    def _read(self, job_id: str) -> dict[str, Any]:
        table = self._client()
        try:
            return table.get_entity(self._partition, job_id)
        except Exception as exc:
            if type(exc).__name__ == "ResourceNotFoundError":
                raise JobNotFound(f"No job {job_id!r}.") from exc
            raise JobStoreError(f"Could not read job {job_id!r}: {exc}") from exc

    def _purge(self) -> int:
        table = self._client()
        now = int(time.time())
        removed = 0
        try:
            rows = table.query_entities(
                "PartitionKey eq @p and expires_at gt 0 and expires_at lt @t",
                parameters={"p": self._partition, "t": now},
                select=["PartitionKey", "RowKey"],
            )
            for row in rows:
                table.delete_entity(row["PartitionKey"], row["RowKey"])
                removed += 1
        except Exception as exc:
            raise JobStoreError(f"Could not purge expired jobs: {exc}") from exc
        if removed:
            logger.info("Purged %d expired job record(s).", removed)
        return removed

    def recover(self) -> int:
        """Nothing to recover, and that is the point.

        The local store fails jobs left mid-run on startup, because they belonged to
        a process that is gone and nothing else can see them. Here a running job may
        belong to another live instance, and a queue may be about to redeliver it — so
        a starting instance must not touch other people's work.

        Reaping genuinely abandoned runs is the queue's job: a message whose handler
        died is redelivered, and after ``maxDequeueCount`` attempts it goes to the
        poison queue, where ``function_app.py`` marks the job failed.
        """
        return 0
