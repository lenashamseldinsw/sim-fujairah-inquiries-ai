"""
The job layer: the promises a caller polling an id is relying on.

The restart behaviour is the one worth reading. A worker that dies mid-run must not
have its jobs resumed — half a pipeline stitched onto another process's half would
produce a report whose figures came from two different runs — so recovery fails them
instead, which a caller can retry.
"""
from __future__ import annotations

import asyncio
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
