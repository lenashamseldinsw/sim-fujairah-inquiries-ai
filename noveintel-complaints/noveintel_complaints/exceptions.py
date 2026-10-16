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

__all__ = ["RunAbandoned", "StageFailure", "UpstreamFailure"]


class StageFailure(Exception):
    """A pipeline stage reported that it could not complete.

    The orchestrator's stages return ``(success, message)`` rather than raising, so
    the entry point turns a failed stage into one of these. It carries the stage name
    because that is the first thing an operator asks, and because the job record
    surfaces it as ``error.stage``.

    Deliberately not an HTTP error: a stage failure reaches a caller inside a finished
    job's record, not as the status of the request that asked about it.
    """

    #: The job record's ``error.code``. A class attribute so the job layer reads it
    #: off whichever subclass was raised instead of testing for each one.
    code = "stage_failed"

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


class UpstreamFailure(StageFailure):
    """A stage failed because the model gateway did.

    The orchestrator catches a gateway error inside the stage and reports only that
    the stage failed. Told apart here because the caller's remedy differs: an outage
    is worth retrying later, and a stage that rejects the data is not.

    The message is fixed rather than the gateway's own. An error body can echo part
    of the prompt, and for the complaints module the prompt is personal data.
    """

    code = "upstream_error"

    def __init__(self, stage: str) -> None:
        super().__init__(
            stage,
            f"The model gateway failed during {stage}, so the run could not finish. "
            "This is usually an outage or rate limiting at the gateway rather than a "
            "problem with the records; retrying later is safe.",
        )


class RunAbandoned(Exception):
    """Raised into a run's thread when nobody is waiting for it any more.

    The job runner raises it from the next progress report once a run passes its
    ceiling; the pipeline lets it through untouched. Defined here, not in
    ``jobs/runner.py``, so the pipeline can name it without importing the job layer —
    which imports the pipeline.
    """
