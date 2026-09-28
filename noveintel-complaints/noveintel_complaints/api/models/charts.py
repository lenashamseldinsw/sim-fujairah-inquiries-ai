"""
Renderer-agnostic chart specifications.

A spec carries data, bilingual titles and categories, and colours. It says nothing
about the renderer: the same spec becomes a Word chart in the .docx the pipeline
builds, an ECharts option in a dashboard, or an SVG in a front end. That is the point
— rendering belongs to the consumer, and this service does not pick one for it.

``ChartSpec``, ``ChartSeries`` and ``ChartKind`` are the shared shape, kept identical
across NoveIntelligence modules so one parser reads them all. ``ChartKey`` is **not**
shared: each module defines its own enum of stable chart identifiers.

**Select charts by ``key``, never by position or by list length.** That is the
cross-module contract the BO adopted on 2026-08-27, and it exists because the number
of charts varies with the data — a tenant with no rejected requests gets no rejection
chart, and a consumer reading ``charts[3]`` then renders the wrong one under the
right heading.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

__all__ = ["ChartKey", "ChartKind", "ChartSeries", "ChartSpec"]


class ChartKind(StrEnum):
    """How a spec is meant to be drawn."""

    BAR = "bar"
    COLUMN = "column"
    PIE = "pie"
    DOUGHNUT = "doughnut"
    LINE = "line"
    STACKED_BAR = "stacked_bar"


class ChartKey(StrEnum):
    """Stable identifiers for the charts a complaints run can produce.

    A key names what the chart *is about*, not where it appears, so re-ordering the
    report does not change it. A key absent from ``charts`` means the data did not
    support that chart — a tenant that records no severity gets no severity chart —
    and that is not an error.

    These are assigned by the chart builders in ``stages/stage6_json_report.py``. A
    new chart there needs a new member here, and adding one is not a breaking change:
    a consumer selecting by key ignores what it does not recognise.
    """

    CLASSIFICATION_MIX = "classification_mix"
    SERVICE_DISTRIBUTION = "service_distribution"
    RESOLUTION_STATUS = "resolution_status"
    SEVERITY_MIX = "severity_mix"
    SLA_CLOSURE = "sla_closure"


class ChartSeries(BaseModel):
    """One named run of values across the spec's categories."""

    name_ar: str = Field(description="Series name in Arabic, for an Arabic render.")
    name_en: str = Field(description="Series name in English, for an English render.")
    values: list[float] = Field(
        description=(
            "One value per category, in the same order as ``categories_ar``. A null "
            "category has a value here too — send 0 only when zero is the truth."
        )
    )

    def name(self, lang: str) -> str:
        """Series name for the given language."""
        return self.name_ar if lang == "ar" else self.name_en


class ChartSpec(BaseModel):
    """Everything needed to draw one chart, and nothing about how."""

    key: ChartKey = Field(
        description=(
            "Stable identifier for what this chart shows. Select on this — never on "
            "the chart's position in the list, which varies with the data."
        )
    )
    kind: ChartKind = Field(description="How the chart is meant to be drawn.")
    title_ar: str = Field(description="Chart title in Arabic.")
    title_en: str = Field(description="Chart title in English.")
    categories_ar: list[str] = Field(
        description="Category (axis or slice) labels in Arabic."
    )
    categories_en: list[str] = Field(
        description=(
            "Category labels in English, in the same order as ``categories_ar``. "
            "Falls back to the Arabic labels for values the pipeline could not "
            "translate, so an English render is never blank."
        )
    )
    series: list[ChartSeries] = Field(
        description=(
            "One entry for a single-series chart; several for a grouped or stacked "
            "one. Every series has one value per category."
        )
    )
    colors: list[str] = Field(
        default_factory=list,
        description=(
            "Hex colours, one per series for a bar or line chart and one per category "
            "for a pie. Empty means the consumer picks, which is the right answer for "
            "a dashboard with its own palette."
        ),
    )

    def title(self, lang: str) -> str:
        """Chart title for the given language."""
        return self.title_ar if lang == "ar" else self.title_en

    def categories(self, lang: str) -> list[str]:
        """Category labels for the given language."""
        return self.categories_ar if lang == "ar" else self.categories_en
