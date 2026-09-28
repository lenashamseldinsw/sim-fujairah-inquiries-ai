"""
Failures the core raises, defined where the core can see them.

``StageFailure`` lives here rather than in ``api/errors.py`` for a layering reason
that a test pins: importing the pipeline must not require FastAPI. The contract and
the core are useful to a caller that will never run the HTTP service — a library
embedding, a notebook, a batch job — and a core exception defined inside the web layer
would drag the whole framework in behind it.

``api/errors.py`` re-exports this, so the web layer still has one place to import its
failures from.
"""
from __future__ import annotations

__all__ = ["StageFailure"]


class StageFailure(Exception):
    """A pipeline stage reported that it could not complete.

    The orchestrator's stages return ``(success, message)`` rather than raising, so
    the entry point turns a failed stage into one of these. It carries the stage name
    because that is the first thing an operator asks, and because the job record
    surfaces it as ``error.stage``.

    Deliberately not an HTTP error: a stage failure reaches a caller inside a finished
    job's record, not as the status of the request that asked about it.
    """

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage
