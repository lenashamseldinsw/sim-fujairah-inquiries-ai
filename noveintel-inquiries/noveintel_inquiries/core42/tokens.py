"""
Token and cost tracking for Core42 calls.

Rates are **looked up, never inferred from the model name**: a table that
classifies by substring silently misprices every model whose name lacks the
substring. An unknown model falls back to the provider default and says so.

Usage is tracked per ``stage`` because aggregate cost is useless for
optimisation — cost per pipeline stage tells you which prompt to cut.

**One ledger per run, not per process.** A service worker runs several pipelines
at once, and each one calls ``reset()`` as it starts; with a single process-wide
list, two overlapping runs cleared and read each other's calls. ``run_scope()``
gives the run in progress a ledger of its own, held in a context variable, and
``track``, ``summary`` and ``reset`` act on that one. Outside a scope they act on
the process ledger, exactly as before.

A context variable does not cross into a ``ThreadPoolExecutor`` worker by itself,
and the stages fan out on executors. ``ScopedThreadPoolExecutor`` carries the
submitting thread's context into each task; the service installs it in the stage
modules in place of the stdlib class, so their calls land in the right ledger.
"""

from __future__ import annotations

import contextvars
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)

# Core42 pricing, per 1K tokens, keyed by model. Override or extend as the
# deployment's contract changes; "default" covers anything not listed.
PRICING: Dict[str, Dict[str, float]] = {
    "default": {"input": 0.00125, "output": 0.01000},  # $1.25 / $10.00 per 1M
}


@dataclass
class TokenUsage:
    model: str
    stage: str
    input_tokens: int
    output_tokens: int
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cost(self) -> float:
        rates = PRICING.get(self.model)
        if rates is None:
            logger.debug(
                "No explicit pricing for model %r; using the default rates.", self.model
            )
            rates = PRICING["default"]
        return (
            (self.input_tokens / 1000) * rates["input"]
            + (self.output_tokens / 1000) * rates["output"]
        )


class _Ledger:
    """The calls one run made, and the gateway failures it hit."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.calls: List[TokenUsage] = []
        self.gateway_failures = 0


_process_ledger = _Ledger()
_run_ledger: contextvars.ContextVar[Optional[_Ledger]] = contextvars.ContextVar(
    "core42_run_ledger", default=None
)


def _current() -> _Ledger:
    return _run_ledger.get() or _process_ledger


@contextmanager
def run_scope() -> Iterator[None]:
    """Give the code inside its own ledger, invisible to any other run."""
    token = _run_ledger.set(_Ledger())
    try:
        yield
    finally:
        _run_ledger.reset(token)


class ScopedThreadPoolExecutor(ThreadPoolExecutor):
    """A ``ThreadPoolExecutor`` whose tasks run in the submitter's context.

    A fresh copy per task: one ``Context`` cannot be entered by two threads at
    once. The copy still points at the same ledger object, which is what matters.
    """

    def submit(self, fn, /, *args, **kwargs):
        return super().submit(contextvars.copy_context().run, fn, *args, **kwargs)


def track(model: str, input_tokens: int, output_tokens: int, stage: str = "unknown") -> None:
    """Record one call. Thread-safe: the pipeline stages fan out across threads."""
    ledger = _current()
    with ledger.lock:
        ledger.calls.append(
            TokenUsage(
                model=model,
                stage=stage,
                input_tokens=int(input_tokens or 0),
                output_tokens=int(output_tokens or 0),
            )
        )


def track_failure() -> None:
    """Record a gateway call that failed for good — every retry spent, or refused."""
    ledger = _current()
    with ledger.lock:
        ledger.gateway_failures += 1


def summary() -> Dict[str, object]:
    """Totals overall and per stage, for logging at the end of a run."""
    ledger = _current()
    with ledger.lock:
        calls = list(ledger.calls)
        gateway_failures = ledger.gateway_failures
    per_stage: Dict[str, Dict[str, float]] = {}
    for call in calls:
        bucket = per_stage.setdefault(
            call.stage, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
        )
        bucket["calls"] += 1
        bucket["input_tokens"] += call.input_tokens
        bucket["output_tokens"] += call.output_tokens
        bucket["cost_usd"] += call.cost
    models = sorted({call.model for call in calls if call.model})
    return {
        "calls": len(calls),
        "input_tokens": sum(c.input_tokens for c in calls),
        "output_tokens": sum(c.output_tokens for c in calls),
        "cost_usd": round(sum(c.cost for c in calls), 4),
        "model": ", ".join(models) or None,
        "gateway_failures": gateway_failures,
        "by_stage": per_stage,
    }


def reset() -> None:
    """Clear the ledger — call at the start of a pipeline run."""
    ledger = _current()
    with ledger.lock:
        ledger.calls.clear()
        ledger.gateway_failures = 0
