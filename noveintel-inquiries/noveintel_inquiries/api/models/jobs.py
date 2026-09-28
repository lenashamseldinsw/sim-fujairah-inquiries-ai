"""
The async job contract.

Module 01 answers its work route synchronously: a report is two model calls and fits
comfortably inside the 230 seconds Azure's load balancer allows an HTTP response. A
inquiries run does not. It makes dozens of sequential calls across six stages — per-case
classification, pattern analysis, guidebook gap analysis, nine report sections and a
full English translation — and on a real export that is minutes, not seconds.

The porting guide's own §5.6 names this case: when a run cannot fit in about 200
seconds even in the best case, a synchronous route is the wrong design. So the work
route accepts the job and answers ``202`` with a ``job_id``; the caller polls.

Everything else about the module is unchanged — same identity model, same error
envelope, same storage contract — and the payload a poll returns once the job
succeeds is exactly the ``InquiriesBundle`` a synchronous route would have returned. A
caller that later moves to a faster synchronous module reuses its result parser.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .enums import JobStatus
from .responses import InquiriesBundle

__all__ = ["JobAccepted", "JobError", "JobState"]


class JobAccepted(BaseModel):
    """What the work route answers: the job exists, nothing has run yet."""

    job_id: str = Field(
        description=(
            "Identifies the job. Poll ``GET /v1/jobs/{job_id}`` with it. It is also "
            "the run id the analysis will use, so it appears in every log line the "
            "run produces and in each stored artefact's key — one id ties the "
            "response, the logs and the files together."
        )
    )
    status: JobStatus = Field(
        description="Always 'queued' here. It is 'running' by the first poll."
    )
    poll_url: str = Field(
        description=(
            "Where to poll, relative to the service root. Given so a caller need not "
            "build the path itself."
        )
    )
    created_at: datetime = Field(description="When the job was accepted, in UTC.")
    estimated_seconds: int | None = Field(
        default=None,
        description=(
            "A rough expectation of how long the run will take, from the case count. "
            "For pacing a poll interval, not a promise — a run over a large export "
            "with heavy model contention takes materially longer. Null when the "
            "record count gives no useful signal."
        ),
    )


class JobError(BaseModel):
    """Why a job failed.

    The same ``code``/``message`` shape as the HTTP error envelope, because the
    failure is the same kind of thing — it just arrives inside a ``200`` describing a
    finished job rather than as the status of the request that asked about it. A poll
    that finds a failed job is a successful poll.
    """

    code: str = Field(
        description=(
            "Stable machine-readable identifier. 'unprocessable_records' when the "
            "pipeline refused the data, 'upstream_error' when the gateway failed, "
            "'stage_failed' when a pipeline stage could not complete, "
            "'internal_error' for anything unhandled."
        )
    )
    message: str = Field(description="What went wrong, in one sentence.")
    stage: str | None = Field(
        default=None,
        description=(
            "The pipeline stage that failed — 'stage1' through 'stage6' — when the "
            "failure can be attributed to one. Null otherwise."
        ),
    )


class JobState(BaseModel):
    """What a poll returns."""

    job_id: str = Field(description="The job being reported on.")
    status: JobStatus = Field(
        description=(
            "'queued' or 'running' means poll again. 'succeeded', 'failed' and "
            "'cancelled' are terminal — the job will not change again."
        )
    )
    created_at: datetime = Field(description="When the job was accepted, in UTC.")
    started_at: datetime | None = Field(
        default=None, description="When the run began, in UTC. Null while queued."
    )
    finished_at: datetime | None = Field(
        default=None,
        description="When the run reached a terminal status, in UTC. Null before that.",
    )
    stage: str | None = Field(
        default=None,
        description=(
            "The stage currently running — 'stage1' through 'stage6'. Null before the "
            "run starts and after it finishes."
        ),
    )
    progress: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "How far the run has got, 0.0 to 1.0. Stage boundaries, so it moves in "
            "steps rather than smoothly, and it is for showing a caller something is "
            "happening rather than for estimating a finish time."
        ),
    )
    message: str | None = Field(
        default=None,
        description=(
            "The current step in words, e.g. 'Stage 3: classifying 412 cases'. For "
            "display; do not branch on it."
        ),
    )
    result: InquiriesBundle | None = Field(
        default=None,
        description=(
            "The finished analysis. Present only when ``status`` is 'succeeded', and "
            "identical to what a synchronous route would have returned."
        ),
    )
    error: JobError | None = Field(
        default=None,
        description="Why the run failed. Present only when ``status`` is 'failed'.",
    )
