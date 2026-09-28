"""
The job layer: the promises a caller polling an id is relying on.

The restart behaviour is the one worth reading. A worker that dies mid-run must not
have its jobs resumed — half a pipeline stitched onto another process's half would
produce a report whose figures came from two different runs — so recovery fails them
instead, which a caller can retry.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest

from noveintel_complaints.api.models import JobState, JobStatus
from noveintel_complaints.jobs import JobNotFound, JobRunner, LocalJobStore


def queued(job_id: str = "job1") -> JobState:
    return JobState(
        job_id=job_id,
        status=JobStatus.QUEUED,
        created_at=datetime.now(timezone.utc),
    )


class TestLocalJobStore:
    async def test_create_then_get(self, tmp_path):
        store = LocalJobStore(tmp_path)
        await store.create(queued())
        assert (await store.get("job1")).status is JobStatus.QUEUED

    async def test_an_unknown_job_raises(self, tmp_path):
        with pytest.raises(JobNotFound):
            await LocalJobStore(tmp_path).get("nope")

    async def test_get_returns_a_copy(self, tmp_path):
        """A caller serialising a state while the run mutates its own copy must not
        see a field change between two lines of the response."""
        store = LocalJobStore(tmp_path)
        await store.create(queued())
        first = await store.get("job1")
        first.progress = 0.9
        assert (await store.get("job1")).progress == 0.0

    async def test_state_is_mirrored_to_disk(self, tmp_path):
        store = LocalJobStore(tmp_path)
        await store.create(queued())
        assert (tmp_path / "job1.json").is_file()

    async def test_a_restart_fails_a_running_job_rather_than_resuming_it(self, tmp_path):
        store = LocalJobStore(tmp_path)
        state = queued()
        state.status = JobStatus.RUNNING
        state.stage = "stage4"
        await store.create(state)

        # A new process over the same directory — the mirror is all it has.
        restarted = LocalJobStore(tmp_path)
        assert restarted.recover() == 1
        recovered = await restarted.get("job1")
        assert recovered.status is JobStatus.FAILED
        assert recovered.error.code == "worker_restarted"
        assert recovered.error.stage == "stage4"

    async def test_recovery_leaves_finished_jobs_alone(self, tmp_path):
        store = LocalJobStore(tmp_path)
        state = queued()
        state.status = JobStatus.SUCCEEDED
        state.finished_at = datetime.now(timezone.utc)
        await store.create(state)
        assert LocalJobStore(tmp_path).recover() == 0

    async def test_an_unreadable_mirror_does_not_break_startup(self, tmp_path):
        """A process killed mid-write leaves a half file describing a job that is gone."""
        (tmp_path).mkdir(exist_ok=True)
        (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
        assert LocalJobStore(tmp_path).recover() == 0

    async def test_expired_jobs_are_purged(self, tmp_path):
        store = LocalJobStore(tmp_path, ttl_sec=0.0)
        state = queued()
        state.finished_at = datetime.now(timezone.utc)
        await store.create(state)
        await store.update(state)
        await asyncio.sleep(0.01)
        assert await store.purge_expired() == 1
        with pytest.raises(JobNotFound):
            await store.get("job1")


class TestJobRunner:
    async def test_a_successful_run_records_its_result(self, tmp_path):
        store = LocalJobStore(tmp_path)
        await store.create(queued())
        runner = JobRunner(store)

        async def run(progress):
            progress(0.5, "جارٍ", "Stage 3: classifying")
            return None  # the bundle; not needed to pin the status transitions

        runner.submit("job1", run)
        await asyncio.sleep(0.1)
        assert (await store.get("job1")).status is JobStatus.SUCCEEDED

    async def test_a_failing_run_is_classified_not_swallowed(self, tmp_path):
        store = LocalJobStore(tmp_path)
        await store.create(queued())
        runner = JobRunner(store)

        async def run(progress):
            raise ValueError("The records cannot be analysed.")

        runner.submit("job1", run)
        await asyncio.sleep(0.1)
        state = await store.get("job1")
        assert state.status is JobStatus.FAILED
        assert state.error.code == "unprocessable_records"

    async def test_an_unhandled_error_does_not_leak_its_message(self, tmp_path):
        """An exception's text can carry a fragment of the caller's data."""
        store = LocalJobStore(tmp_path)
        await store.create(queued())
        runner = JobRunner(store)

        async def run(progress):
            raise KeyError("رقم الهوية 784-1990-1234567-1")

        runner.submit("job1", run)
        await asyncio.sleep(0.1)
        state = await store.get("job1")
        assert state.error.code == "internal_error"
        assert "784" not in state.error.message

    async def test_a_run_past_its_ceiling_is_abandoned(self, tmp_path):
        store = LocalJobStore(tmp_path)
        await store.create(queued())
        runner = JobRunner(store, max_runtime_sec=0.05)

        async def run(progress):
            await asyncio.sleep(5)

        runner.submit("job1", run)
        await asyncio.sleep(0.3)
        state = await store.get("job1")
        assert state.status is JobStatus.FAILED
        assert state.error.code == "runtime_exceeded"

    async def test_shutdown_cancels_rather_than_leaving_a_job_running(self, tmp_path):
        store = LocalJobStore(tmp_path)
        await store.create(queued())
        runner = JobRunner(store)

        async def run(progress):
            await asyncio.sleep(10)

        runner.submit("job1", run)
        await asyncio.sleep(0.05)
        await runner.shutdown(timeout=1.0)
        assert (await store.get("job1")).status is JobStatus.CANCELLED


class TestQueueDispatch:
    """The queue path: what the route does differently when a run executes elsewhere."""

    def test_the_dispatcher_advertises_that_it_needs_the_request_stored(self):
        """The route branches on this. A JobRunner's closure already holds the
        request; a queued run's does not exist in the worker that will run it."""
        from noveintel_complaints.jobs import JobRunner, QueueDispatcher

        assert QueueDispatcher.needs_stored_request is True
        assert getattr(JobRunner, "needs_stored_request", False) is False

    def test_submit_enqueues_the_job_id_and_nothing_else(self):
        """A queue message caps at 64 KiB and a real export is megabytes, so the
        payload cannot travel in the message."""
        from noveintel_complaints.jobs import QueueDispatcher, QueueSender

        sent = []

        class Recorder(QueueSender):
            def send(self, message): sent.append(message)

        QueueDispatcher(Recorder()).submit("abc123", lambda progress: None)
        assert json.loads(sent[0]) == {"job_id": "abc123", "v": 1}

    def test_a_failed_enqueue_raises_rather_than_stranding_the_job(self):
        """The job row already says 'queued'. If nothing will pick it up, the caller
        has to learn that now rather than by polling forever."""
        from noveintel_complaints.jobs import JobStoreError, QueueDispatcher, QueueSender

        class Broken(QueueSender):
            def send(self, message): raise RuntimeError("queue is down")

        with pytest.raises(JobStoreError, match="not started"):
            QueueDispatcher(Broken()).submit("abc123", lambda progress: None)

    async def test_shutdown_is_a_no_op(self):
        """This worker is not running anything, but the lifespan calls it regardless."""
        from noveintel_complaints.jobs import QueueDispatcher, QueueSender

        await QueueDispatcher(QueueSender()).shutdown()


class TestPendingRequests:
    """Storing the request so a worker in another process can rebuild the run."""

    async def test_round_trips_through_the_document_store(self, tmp_path):
        from noveintel_complaints.jobs import load_request, save_request
        from noveintel_complaints.storage import LocalDirectoryStore

        store = LocalDirectoryStore(tmp_path)
        await save_request(store, "abc123", '{"records": []}')
        assert await load_request(store, "abc123") == '{"records": []}'

    async def test_filed_under_a_reserved_prefix_not_beside_the_artefacts(self, tmp_path):
        """A payload is the run's input and is customer data. Listing a tenant's
        reports must not turn one up."""
        from noveintel_complaints.jobs import save_request
        from noveintel_complaints.jobs.payloads import PREFIX
        from noveintel_complaints.storage import LocalDirectoryStore

        await save_request(LocalDirectoryStore(tmp_path), "abc123", "{}")
        written = [p for p in (tmp_path / "reports").rglob("*.json")]
        assert written and written[0].parent.name == PREFIX.strip("_") or PREFIX in str(written[0])

    async def test_no_store_is_a_refusal_not_a_silent_success(self, tmp_path):
        """A job whose input was never written is one the worker cannot run."""
        from noveintel_complaints.jobs import JobStoreError, save_request

        with pytest.raises(JobStoreError, match="document store"):
            await save_request(None, "abc123", "{}")

    async def test_a_missing_payload_reports_why(self, tmp_path):
        from noveintel_complaints.jobs import JobStoreError, load_request
        from noveintel_complaints.storage import LocalDirectoryStore

        with pytest.raises(JobStoreError, match="cleaned up|could not be read"):
            await load_request(LocalDirectoryStore(tmp_path), "gone")

    @pytest.mark.parametrize("bad", ["../escape", "a/b", "abc-123"])
    async def test_a_non_alphanumeric_job_id_is_refused(self, tmp_path, bad):
        """Ids are hex generated here, but the day one comes from a caller this is a
        write anywhere the process can reach."""
        from noveintel_complaints.jobs import JobStoreError, save_request
        from noveintel_complaints.storage import LocalDirectoryStore

        with pytest.raises(JobStoreError, match="alphanumeric"):
            await save_request(LocalDirectoryStore(tmp_path), bad, "{}")


class TestQueueWorker:
    """``execute_job`` — the other half of the queue pairing."""

    async def test_a_redelivered_finished_job_is_not_run_again(self, tmp_path):
        """The handler completed but the acknowledgement was lost. Re-running would
        spend a second run's tokens to overwrite a good result."""
        from noveintel_complaints.jobs import LocalJobStore, execute_job

        store = LocalJobStore(tmp_path)
        state = JobState(job_id="job1", status=JobStatus.SUCCEEDED,
                         created_at=datetime.now(timezone.utc),
                         finished_at=datetime.now(timezone.utc))
        await store.create(state)
        await execute_job("job1", jobs=store, store=None, request_type=object)
        assert (await store.get("job1")).status is JobStatus.SUCCEEDED

    async def test_a_vanished_job_is_dropped_not_raised_on(self, tmp_path):
        """Raising would have the host redeliver a message about a job that is gone."""
        from noveintel_complaints.jobs import LocalJobStore, execute_job

        await execute_job("nosuch", jobs=LocalJobStore(tmp_path), store=None,
                          request_type=object)

    async def test_an_unreadable_request_fails_the_job_with_a_reason(self, tmp_path):
        from noveintel_complaints.jobs import LocalJobStore, execute_job
        from noveintel_complaints.storage import LocalDirectoryStore

        store = LocalJobStore(tmp_path / "jobs")
        await store.create(queued())
        await execute_job("job1", jobs=store, store=LocalDirectoryStore(tmp_path / "s"),
                          request_type=object)
        state = await store.get("job1")
        assert state.status is JobStatus.FAILED
        assert state.error.code == "request_unavailable"

    async def test_fail_job_records_a_poison_queue_outcome(self, tmp_path):
        """A message that exhausted its deliveries names a job someone is polling."""
        from noveintel_complaints.api.models.jobs import JobError
        from noveintel_complaints.jobs import LocalJobStore, fail_job

        store = LocalJobStore(tmp_path)
        state = queued()
        state.status = JobStatus.RUNNING
        await store.create(state)
        await fail_job(store, "job1", JobError(code="delivery_failed", message="gave up"))
        assert (await store.get("job1")).status is JobStatus.FAILED


class TestTableStoreWithoutAzure:
    """The table backend must be importable and diagnosable with no SDK installed."""

    def test_importing_it_needs_no_azure_package(self):
        from noveintel_complaints.jobs import TableStorageJobStore

        assert TableStorageJobStore("UseDevelopmentStorage=true")

    def test_the_factory_refuses_an_unconfigured_table_backend(self, monkeypatch):
        from noveintel_complaints.config import get_job_settings
        from noveintel_complaints.jobs import JobStoreError
        from noveintel_complaints.jobs.factory import create_job_store

        monkeypatch.setenv("NOVECOMP_JOB_BACKEND", "table")
        monkeypatch.setenv("NOVECOMP_JOB_CONNECTION_STRING", "")
        get_job_settings.cache_clear()
        create_job_store.cache_clear()
        try:
            with pytest.raises(JobStoreError, match="CONNECTION_STRING"):
                create_job_store()
        finally:
            get_job_settings.cache_clear()
            create_job_store.cache_clear()

    def test_an_unknown_backend_names_the_valid_ones(self, monkeypatch):
        from noveintel_complaints.config import get_job_settings
        from noveintel_complaints.jobs import JobStoreError
        from noveintel_complaints.jobs.factory import create_job_store

        monkeypatch.setenv("NOVECOMP_JOB_BACKEND", "cosmos")
        get_job_settings.cache_clear()
        create_job_store.cache_clear()
        try:
            with pytest.raises(JobStoreError, match="'local' or 'table'"):
                create_job_store()
        finally:
            get_job_settings.cache_clear()
            create_job_store.cache_clear()
