"""
The deterministic layer.

Small, and honestly so. In module 01 ``engine/`` is the whole computation and the
model only writes prose around figures it computed. That separation does not survive
the port intact: this module's six stages interleave deterministic work with model
calls by design — stage 2 classifies by rule, stage 3 hands the rest to the model,
stages 4 and 5 reason over both — and splitting them apart would be a rewrite of the
pipeline rather than a port of it.

So what lives here is the part that genuinely is pure, is shared with module 01, and
has to agree with it exactly: resolving the reporting period. The rest of the
deterministic output is computed inside the stages and surfaced through the bundle's
``metrics``, which is what a reader checks the prose against.

See ``docs/schema.md`` for what ``metrics`` contains and which figures are computed
rather than written.
"""
from __future__ import annotations

from .period import (
    derive_granularity,
    parse_dates,
    period_from_datetimes,
    resolve_period,
)

__all__ = [
    "derive_granularity",
    "parse_dates",
    "period_from_datetimes",
    "resolve_period",
]
