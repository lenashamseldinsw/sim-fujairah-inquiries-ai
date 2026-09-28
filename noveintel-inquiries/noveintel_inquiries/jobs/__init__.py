"""
The async job layer.

A run is minutes of sequential model calls — dozens of them across six stages — and
does not fit the 230 seconds Azure allows an HTTP response. The porting guide's §5.6
names exactly this case: when a run cannot fit in about 200 seconds even in the best
case, a synchronous route is the wrong design.

So the work route records a job and answers ``202``; something runs it off the request
path and writes each stage back into a ``JobStore``; the caller polls
``GET /v1/jobs/{job_id}``.

**Two independent choices**, which is why there are two families here.

*Where state lives* — ``LocalJobStore`` (in-process, mirrored to disk) or
``TableStorageJobStore`` (durable, and visible to every instance).

*Where the run executes* — ``JobRunner`` (this worker's event loop) or
``QueueDispatcher`` (a queue, with ``worker.execute_job`` on the other side). Only the
queue makes a run survive the worker that accepted it: an unacknowledged message is
redelivered.

Both pairs satisfy the same two-method shape, so ``deps.get_job_runner`` hands back
either and no route can tell the difference.
"""
from __future__ import annotations

from .base import JobNotFound, JobStore, JobStoreError
from .factory import create_job_store
from .local import LocalJobStore
from .payloads import delete_request, load_request, save_request
from .queue import QueueDispatcher, QueueSender
from .runner import JobRunner, ProgressReporter
from .table_storage import TableStorageJobStore
from .worker import execute_job, fail_job

__all__ = [
    "JobNotFound",
    "JobRunner",
    "JobStore",
    "JobStoreError",
    "LocalJobStore",
    "ProgressReporter",
    "QueueDispatcher",
    "QueueSender",
    "TableStorageJobStore",
    "create_job_store",
    "delete_request",
    "execute_job",
    "fail_job",
    "load_request",
    "save_request",
]
