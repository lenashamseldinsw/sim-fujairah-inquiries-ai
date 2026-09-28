"""
Runtime configuration for the Customer Inquiries Analytics service.

Five settings groups, deliberately separate, each with its own prefix and its own
cached getter.

``Settings`` is the Core42 connection. ``PricingSettings`` is what that connection's
tokens cost. ``StorageSettings`` says where finished artefacts are put. ``JobSettings``
governs the async job store. ``ApiSettings`` is the HTTP service wrapped around the
lot, and exists only when the API layer is running.

Credentials come from the environment (or a ``.env`` file), never from a Streamlit
secrets file: this package is standalone by design.

    CORE42_API_KEY=...          # required
    CORE42_BASE_URL=...         # optional, defaults to the Core42 v1 endpoint
    CORE42_MODEL=...            # optional, the reasoning tier
    CORE42_MODEL_FAST=...       # optional, the bulk per-case classification tier
    CORE42_REQUEST_TIMEOUT=...  # optional, per-call timeout in seconds

    CORE42_INPUT_COST_PER_1M=...   # optional, USD per 1M input tokens
    CORE42_OUTPUT_COST_PER_1M=...  # optional, USD per 1M output tokens

    NOVEINQ_API_KEY=...       # optional, enables app-level auth
    NOVEINQ_LOG_LEVEL=...     # optional, INFO by default
    NOVEINQ_MAX_RECORDS=...   # optional, reject a run larger than this

    NOVEINQ_JOB_BACKEND=...       # optional, 'local' or 'table'
    NOVEINQ_JOB_DISPATCH=...      # optional, 'inprocess' or 'queue'
    NOVEINQ_JOB_CONNECTION_STRING=  # required by 'table' and 'queue'
    NOVEINQ_JOB_DIR=...       # optional, where job state is written
    NOVEINQ_JOB_TTL_SEC=...   # optional, how long a finished job is kept

    NOVEINQ_STORAGE_BACKEND=          # optional, 'local' (the only one, for now)
    NOVEINQ_STORAGE_DIR=...           # optional, root of the filesystem store
    NOVEINQ_STORAGE_CONTAINER=...     # optional, container / bucket / top-level dir
    NOVEINQ_STORAGE_PUBLIC_BASE_URL=  # optional, unset means file: URIs

**There is no HTTP budget here**, and its absence is the one real departure from
module 01's config. That service runs synchronously and needs a wall-clock budget
under Azure's 230-second response ceiling. A inquiries run is minutes of sequential
model calls, so the work route hands back a job id instead and no request is ever
held open — the ceiling stops being something to budget against. ``JobSettings.
max_runtime_sec`` bounds the *run* rather than the response.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "ApiSettings",
    "JobSettings",
    "PricingSettings",
    "Settings",
    "StorageSettings",
    "get_api_settings",
    "get_job_settings",
    "get_pricing_settings",
    "get_settings",
    "get_storage_settings",
]


def _blank_is_none(value: object) -> object:
    """Treat a declared-but-empty variable as absent rather than as a bad value.

    Declaring a variable and leaving it blank is how an operator says "not this one"
    — it is what a copied ``local.settings.json`` template looks like, and what an
    empty deployment-slot setting looks like. Without this, that reads as an
    unparseable number and takes the whole settings object down with it, which means
    a failed startup and a 503 rather than the default the operator was asking for.
    """
    if isinstance(value, str) and not value.strip():
        return None
    return value


class Settings(BaseSettings):
    """Core42 connection settings, read from the environment.

    These mirror what ``noveintel_inquiries.core42.settings`` reads, and deliberately so: the
    vendored Core42 layer is the pipeline's own door to the gateway and reads the
    environment itself, while this group is what the API layer validates at startup
    and reports on ``/ready``. One environment, two readers, and a missing key shows
    up on the probe rather than in the middle of a run.
    """

    model_config = SettingsConfigDict(
        env_prefix="CORE42_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: str = Field(
        description="Core42 API key. Sent as the OpenAI-compatible bearer token."
    )
    base_url: str = Field(
        default="https://api.core42.ai/v1",
        description="Core42 OpenAI-compatible endpoint.",
    )
    model: str = Field(
        default="gpt-5.1",
        description=(
            "The reasoning tier: pattern analysis, gap analysis and the report prose."
        ),
    )
    model_fast: str = Field(
        default="",
        description=(
            "The bulk tier, used for per-case classification in stage 3. Empty means "
            "the same model as the reasoning tier."
        ),
    )
    request_timeout: float = Field(
        default=240.0,
        gt=0,
        description=(
            "Per-request timeout in seconds for one model call. Generous: a report "
            "section is a long structured generation."
        ),
    )


class PricingSettings(BaseSettings):
    """What the model's tokens cost, read from the environment.

    Its own group rather than fields on ``Settings`` because that one is the
    *connection* and nothing more; but the same ``CORE42_`` prefix, because a rate
    belongs to the model being called rather than to the service calling it.

    Providers publish prices per million tokens, so that is the unit here — copied
    straight off a pricing page with no arithmetic in between, which is one fewer
    place to slip a decimal point.

    Both default to unset, because there is no rate that is right to assume: shipping
    one would go stale and would be wrong for any negotiated contract. Unset means a
    run reports its tokens with a null cost and says why, which is honest where a
    silent zero would not be.
    """

    model_config = SettingsConfigDict(
        env_prefix="CORE42_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    input_cost_per_1m: float | None = Field(
        default=None,
        ge=0,
        description="USD per 1,000,000 input (prompt) tokens. Unset disables costing.",
    )
    output_cost_per_1m: float | None = Field(
        default=None,
        ge=0,
        description=(
            "USD per 1,000,000 output (completion) tokens. Unset disables costing. "
            "Priced separately from input because providers charge several times more "
            "for it — a single blended rate would be materially wrong."
        ),
    )

    @field_validator("input_cost_per_1m", "output_cost_per_1m", mode="before")
    @classmethod
    def _blank_means_unset(cls, value: object) -> object:
        return _blank_is_none(value)

    @property
    def configured(self) -> bool:
        """Whether a run can be costed. Both rates are needed, or neither is usable."""
        return self.input_cost_per_1m is not None and self.output_cost_per_1m is not None


class StorageSettings(BaseSettings):
    """Where finished artefacts are put, read from the environment.

    Its own group rather than fields on ``ApiSettings`` because storage is not the
    HTTP layer's concern: a library caller using ``generate_report`` directly stores
    artefacts too, and never constructs ``ApiSettings`` at all.

    There is no dedicated blob storage for this project yet, so ``local`` is the only
    backend and the default. Adding a real one means a new backend name here and an
    implementation in ``noveintel_inquiries.storage`` — nothing else moves, and no caller changes,
    because the response already carries references rather than bytes.
    """

    model_config = SettingsConfigDict(
        env_prefix="NOVEINQ_STORAGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    backend: str = Field(
        default="local",
        description=(
            "Which store to use. Only 'local' exists today — a directory on the "
            "service's own disk, standing in for a blob container until one is "
            "provisioned."
        ),
    )
    dir: Path = Field(
        default=Path("storage"),
        description=(
            "Root of the filesystem store, relative to the working directory unless "
            "absolute. Only the 'local' backend reads this."
        ),
    )
    container: str = Field(
        default="reports",
        description=(
            "Container the artefacts are filed under, reported back on every "
            "reference. A blob container or bucket for a real backend; a directory "
            "beneath the root for the local one."
        ),
    )
    public_base_url: str | None = Field(
        default=None,
        description=(
            "Prefix the local backend builds its URLs from, as "
            "'<base>/<container>/<key>'. Unset — the default — means it returns "
            "file: URIs instead, which are honest about being on the service's disk. "
            "Set it to whatever serves the storage directory and the URLs become "
            "fetchable, making the contract identical to a real blob backend's."
        ),
    )


class JobSettings(BaseSettings):
    """The async job store, read from the environment.

    Its own group because the job layer is what makes this module differ from module
    01, and because a real deployment will want to point it at something durable
    without touching anything else.

    Two axes, and they are independent. ``backend`` says where job *state* lives;
    ``dispatch`` says where the *run* executes. The defaults — ``local`` and
    ``inprocess`` — need no Azure account and are right for development and for a
    single always-on instance.

    ``local`` keeps jobs in the worker's own memory and mirrors each change to a file
    under ``dir``. It is **not** durable across a restart: a job that was running when
    the process died is reported ``failed`` on the next poll rather than silently
    resumed, because resuming half a pipeline would produce a report from two
    different runs. It is also invisible to other instances, so a poll can 404 against
    the worker that did not accept the job.

    ``backend="table"`` fixes the second problem: any instance can serve a poll.
    ``dispatch="queue"`` fixes the first: an unacknowledged message is redelivered, so
    a run that died with its worker is picked up again from the start. Production
    wants both. See ``README.md``.
    """

    model_config = SettingsConfigDict(
        env_prefix="NOVEINQ_JOB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    backend: str = Field(
        default="local",
        description=(
            "Where job state lives. 'local' is in-process, mirrored to disk: honest "
            "for one worker, and neither durable across a restart nor visible to "
            "another instance. 'table' is Azure Table Storage, which is both — any "
            "instance can serve a poll, and a record outlives the worker that wrote "
            "it. 'table' needs a connection string."
        ),
    )
    dispatch: str = Field(
        default="inprocess",
        description=(
            "Where a run executes. 'inprocess' runs it on this worker's event loop, "
            "which is right for local development and a single always-on instance. "
            "'queue' enqueues it for a queue-triggered function to pick up, which is "
            "what makes a run survive the worker that accepted it: an unacknowledged "
            "message is redelivered. 'queue' needs a connection string and a document "
            "store, since the request is stored for the worker to read."
        ),
    )
    connection_string: str = Field(
        default="",
        description=(
            "Azure Storage connection string for the 'table' backend and the 'queue' "
            "dispatcher. 'UseDevelopmentStorage=true' works against Azurite."
        ),
    )
    table_name: str = Field(
        default="jobs",
        description="Table the job records are written to. Created if absent.",
    )
    queue_name: str = Field(
        default="analysis-runs",
        description=(
            "Queue the work messages go to. The queue-triggered function in "
            "function_app.py must bind to the same name, and its poison queue "
            "('<name>-poison') is what catches a run that failed every delivery."
        ),
    )
    dir: Path = Field(
        default=Path("jobs"),
        description=(
            "Directory the local backend mirrors job state into, relative to the "
            "working directory unless absolute."
        ),
    )
    ttl_sec: float = Field(
        default=86_400.0,
        gt=0,
        description=(
            "How long a finished job stays pollable, in seconds. Default is a day — "
            "long enough for a caller to come back after an overnight run, short "
            "enough that the store does not grow without bound. The artefacts in "
            "storage outlive this; only the job record is dropped."
        ),
    )
    max_runtime_sec: float = Field(
        default=3_600.0,
        gt=0,
        description=(
            "Wall-clock ceiling for one run, in seconds. A run that exceeds it is "
            "abandoned and reported failed, so a wedged model call cannot hold a "
            "worker slot forever. Default is an hour, which is well clear of a large "
            "export's honest runtime."
        ),
    )
    max_concurrent: int = Field(
        default=2,
        ge=1,
        description=(
            "Runs allowed to execute at once in one worker. Each run fans out to "
            "several in-flight model calls of its own — the Core42 layer caps those "
            "globally — so this is about memory and orderly queueing rather than "
            "gateway pressure. Jobs beyond it stay 'queued'."
        ),
    )


class ApiSettings(BaseSettings):
    """HTTP service settings, read from the environment.

    Separate from ``Settings`` because they answer to different owners: those are the
    model gateway's, these are the service's own. The prefix differs too —
    ``CORE42_API_KEY`` is the Core42 credential, ``NOVEINQ_API_KEY`` is the key a
    caller presents to us.
    """

    model_config = SettingsConfigDict(
        env_prefix="NOVEINQ_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: str | None = Field(
        default=None,
        description=(
            "If set, every /v1 request must present this key in the X-API-Key header. "
            "Leave unset behind a gateway that already authenticates — on Azure "
            "Functions the platform enforces its own function key before a request "
            "ever reaches the app."
        ),
    )
    log_level: str = Field(
        default="INFO",
        description=(
            "Threshold for the service's own log output: CRITICAL, ERROR, WARNING, "
            "INFO or DEBUG. INFO narrates each pipeline stage; DEBUG adds per-stage "
            "timings. Ignored when the host has already configured logging, which on "
            "Azure Functions it has."
        ),
    )
    max_records: int = Field(
        default=100_000,
        gt=0,
        description=(
            "Largest run the service will accept, in records. A body past it is "
            "rejected with 422 ``too_many_records`` rather than accepted into a job "
            "that would run for hours. Raise it deliberately, having checked that the "
            "worker has the memory: the whole export is held in a dataframe."
        ),
    )

    @field_validator("log_level", mode="before")
    @classmethod
    def _blank_level_means_default(cls, value: object) -> object:
        """A declared-but-empty variable means "leave it alone", not "log nothing"."""
        if isinstance(value, str) and not value.strip():
            return "INFO"
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Core42 settings, read from the environment once."""
    return Settings()  # type: ignore[call-arg]  — populated from the environment


@lru_cache(maxsize=1)
def get_api_settings() -> ApiSettings:
    """Return the process-wide API settings, read from the environment once."""
    return ApiSettings()


@lru_cache(maxsize=1)
def get_storage_settings() -> StorageSettings:
    """Return the process-wide storage settings, read from the environment once."""
    return StorageSettings()


@lru_cache(maxsize=1)
def get_pricing_settings() -> PricingSettings:
    """Return the process-wide pricing settings, read from the environment once."""
    return PricingSettings()


@lru_cache(maxsize=1)
def get_job_settings() -> JobSettings:
    """Return the process-wide job settings, read from the environment once."""
    return JobSettings()
