"""
Token and cost tracking for Core42 calls.

Rates are **looked up, never inferred from the model name**: a table that
classifies by substring silently misprices every model whose name lacks the
substring. An unknown model falls back to the provider default and says so.

Usage is tracked per ``stage`` because aggregate cost is useless for
optimisation — cost per pipeline stage tells you which prompt to cut.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List

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


_lock = threading.Lock()
_calls: List[TokenUsage] = []


def track(model: str, input_tokens: int, output_tokens: int, stage: str = "unknown") -> None:
    """Record one call. Thread-safe: the pipeline stages fan out across threads."""
    with _lock:
        _calls.append(
            TokenUsage(
                model=model,
                stage=stage,
                input_tokens=int(input_tokens or 0),
                output_tokens=int(output_tokens or 0),
            )
        )


def summary() -> Dict[str, object]:
    """Totals overall and per stage, for logging at the end of a run."""
    with _lock:
        calls = list(_calls)
    per_stage: Dict[str, Dict[str, float]] = {}
    for call in calls:
        bucket = per_stage.setdefault(
            call.stage, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
        )
        bucket["calls"] += 1
        bucket["input_tokens"] += call.input_tokens
        bucket["output_tokens"] += call.output_tokens
        bucket["cost_usd"] += call.cost
    return {
        "calls": len(calls),
        "input_tokens": sum(c.input_tokens for c in calls),
        "output_tokens": sum(c.output_tokens for c in calls),
        "cost_usd": round(sum(c.cost for c in calls), 4),
        "by_stage": per_stage,
    }


def reset() -> None:
    """Clear the ledger — call at the start of a pipeline run."""
    with _lock:
        _calls.clear()
