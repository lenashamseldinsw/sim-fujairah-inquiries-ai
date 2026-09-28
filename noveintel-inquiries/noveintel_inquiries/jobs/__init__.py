"""
The async job layer.

A inquiries run is minutes of sequential model calls — dozens of them across six stages —
and does not fit the 230 seconds Azure allows an HTTP response. The porting guide's
§5.6 names exactly this case: when a run cannot fit in about 200 seconds even in the
best case, a synchronous route is the wrong design.

So the work route records a job and answers ``202``; ``JobRunner`` runs it off the
request path and writes each stage back into a ``JobStore``; the caller polls
``GET /v1/jobs/{job_id}``. Everything else about the service is module 01's shape
unchanged.
"""
from __future__ import annotations

from .base import JobNotFound, JobStore, JobStoreError
from .factory import create_job_store
from .local import LocalJobStore
from .runner import JobRunner, ProgressReporter

__all__ = [
    "JobNotFound",
    "JobRunner",
    "JobStore",
    "JobStoreError",
    "LocalJobStore",
    "ProgressReporter",
    "create_job_store",
]
