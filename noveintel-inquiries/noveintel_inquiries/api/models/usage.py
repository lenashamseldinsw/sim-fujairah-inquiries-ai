"""
``RunUsage`` — what one run's model calls consumed.

Tokens come from the gateway; cost does not, so it is computed from configured
per-million-token rates. Input and output are priced separately because that is how
every provider bills — output typically runs several times the input rate, so a single
blended rate applied to the total would be wrong by a wide margin.

Scope is the Core42 calls the pipeline made and nothing else. Excel assembly, document
rendering and storage are not measured.

``by_stage`` is this module's addition to the shared shape. A inquiries run makes dozens
of calls across six stages, and an aggregate figure says nothing actionable about
which prompt to cut — so the per-stage ledger the pipeline already keeps is surfaced
rather than summed away.

One honest limit: the count covers calls this code saw return a response. A gateway
that retries internally never surfaces an object to read, so a heavily-retried run may
have cost more than is reported here. Treat this as a good-faith accounting of
observed calls, not a billing reconciliation.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = ["RunUsage", "StageUsage"]


class StageUsage(BaseModel):
    """Token and cost figures for one pipeline stage."""

    calls: int = Field(ge=0, description="Model calls this stage made.")
    input_tokens: int = Field(ge=0, description="Prompt tokens this stage consumed.")
    output_tokens: int = Field(
        ge=0, description="Completion tokens this stage consumed."
    )
    cost: float | None = Field(
        default=None,
        description=(
            "Cost in USD for this stage, or null when the run could not be priced."
        ),
    )


class RunUsage(BaseModel):
    """Aggregate token and cost figures for the model calls in one run."""

    tokens: int = Field(
        ge=0,
        description=(
            "Total tokens across every model call in the run — the sum of "
            "input_tokens and output_tokens."
        ),
    )
    cost: float | None = Field(
        description=(
            "Total cost in USD. Null means the run could not be priced because "
            "CORE42_INPUT_COST_PER_1M or CORE42_OUTPUT_COST_PER_1M is unset — the "
            "tokens are still reported, and a 'pricing_not_configured' warning says "
            "so. Null is deliberately not 0.0: an unpriced run and a free one are "
            "different things."
        )
    )
    input_tokens: int = Field(
        ge=0, description="Prompt tokens across every call, priced at the input rate."
    )
    output_tokens: int = Field(
        ge=0,
        description="Completion tokens across every call, priced at the output rate.",
    )
    calls: int = Field(
        ge=0,
        description=(
            "Model calls that returned a response. A inquiries run makes dozens — "
            "per-case classification in stage 3, analysis in stages 4 and 5, and one "
            "per report section plus the English translation in stage 6 — so this is "
            "counted rather than assumed."
        ),
    )
    model: str | None = Field(
        default=None,
        description=(
            "The model as reported by the responses, which can differ from the one "
            "requested when a gateway aliases or version-pins. Null when no call was "
            "made. Several names joined by ', ' means one rate pair priced more than "
            "one model, and the cost is approximate."
        ),
    )
    by_stage: dict[str, StageUsage] = Field(
        default_factory=dict,
        description=(
            "The same figures broken down by pipeline stage. Aggregate cost says "
            "nothing actionable; cost per stage says which prompt to cut."
        ),
    )
