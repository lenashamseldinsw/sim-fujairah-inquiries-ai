"""
``Period`` — the reporting window a run covers.

The pipeline derives the window from the case dates it was given, and everything
downstream that names the period — the cover page, the executive summary, the
document filename — reads it from here, so the label is resolved once and carried
rather than re-derived per consumer.

Kept byte-identical in shape to module 01's ``Period`` so that a front end or an
orchestrator can parse one period model across every NoveIntelligence module.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from .enums import PeriodGranularity

__all__ = ["Period"]


class Period(BaseModel):
    """The resolved reporting period for a run."""

    granularity: PeriodGranularity = Field(
        description=(
            "Granularity the period is expressed at, either as requested or as "
            "derived from the span of the data."
        )
    )
    index: int = Field(
        ge=1,
        description=(
            "Ordinal of the period within its year: month 1-12, quarter 1-4, "
            "half 1-2, or 1 for an annual period."
        ),
    )
    year: int = Field(description="Calendar year the period falls in.")
    start: date = Field(description="Earliest case date in the data.")
    end: date = Field(description="Latest case date in the data.")
    label_ar: str = Field(
        description="Human-readable period name in Arabic, e.g. 'الربع الأول 2025'."
    )
    label_en: str = Field(
        description="Human-readable period name in English, e.g. 'Q1 2025'."
    )

    def label(self, lang: str) -> str:
        """Period name for the given report language."""
        return self.label_ar if lang == "ar" else self.label_en
