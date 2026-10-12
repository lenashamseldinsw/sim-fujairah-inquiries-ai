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
    HEATMAP = "heatmap"


class ChartKey(StrEnum):
    """Stable identifiers for the charts a run can produce.

    The ADPF identities are Data Mapping §6's, verbatim; the Fujairah-native ones keep
    the names this API already published, except ``sla_compliance``, which is now
    Data Mapping's ``timeliness_donut`` (O10). A key absent from ``charts`` means the
    data did not support that chart, which is not an error. Select by key, never by
    position.
    """

    # Fujairah-native (S3)
    CLASSIFICATION_MIX = "classification_mix"          # O7 recorded vs actual type
    ACTUAL_TYPE_MIX = "actual_type_mix"                # O8
    SERVICE_DISTRIBUTION = "service_distribution"      # O9 recorded service tag
    SEVERITY_MIX = "severity_mix"                      # O11
    SUB_CLASS_BY_TYPE = "sub_class_by_type"            # O13
    DEPARTMENT_DISTRIBUTION = "department_distribution"  # O14
    CLASSIFICATION_QUALITY = "classification_quality"  # O21
    PERIOD_COMPARISON = "period_comparison"            # O20
    # Data Mapping §6
    MONTHLY_BAR = "monthly_bar"                        # O19
    MAIN_SERVICE_BAR = "main_service_bar"
    SUB_SERVICE_BAR = "sub_service_bar"
    CHANNEL_DONUT = "channel_donut"                    # O12
    CHANNEL_COMPARISON_BAR = "channel_comparison_bar"
    TIMELINESS_DONUT = "timeliness_donut"              # O10 (locked status colours)
    RECORDED_VS_TRUE_STACKED = "recorded_vs_true_stacked"
    INQ_PER_100_BAR = "inq_per_100_bar"                # O26
    BUNDLE_BAR = "bundle_bar"                          # O22
    BUNDLE_SERVICE_HEATMAP = "bundle_service_heatmap"  # O23
    NEAR_OVER_BY_BUNDLE_BAR = "near_over_by_bundle_bar"  # O25
    TOP_ROOT_CAUSES_BAR = "top_root_causes_bar"        # O24
    HOWTO_BY_SERVICE_BAR = "howto_by_service_bar"
    FAQ_COVERAGE_BAR = "faq_coverage_bar"
    FOCUS_1_MONTHLY_BAR = "focus_1_monthly_bar"
    FOCUS_1_SUBCLASS_DONUT = "focus_1_subclass_donut"
    FOCUS_1_BUNDLE_BAR = "focus_1_bundle_bar"
    FOCUS_2_MONTHLY_BAR = "focus_2_monthly_bar"
    FOCUS_2_SUBCLASS_DONUT = "focus_2_subclass_donut"
    FOCUS_2_BUNDLE_BAR = "focus_2_bundle_bar"
    FOCUS_3_MONTHLY_BAR = "focus_3_monthly_bar"
    FOCUS_3_SUBCLASS_DONUT = "focus_3_subclass_donut"
    FOCUS_3_BUNDLE_BAR = "focus_3_bundle_bar"
    FOCUS_4_MONTHLY_BAR = "focus_4_monthly_bar"
    FOCUS_4_SUBCLASS_DONUT = "focus_4_subclass_donut"
    FOCUS_4_BUNDLE_BAR = "focus_4_bundle_bar"
    FOCUS_5_MONTHLY_BAR = "focus_5_monthly_bar"
    FOCUS_5_SUBCLASS_DONUT = "focus_5_subclass_donut"
    FOCUS_5_BUNDLE_BAR = "focus_5_bundle_bar"


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
    output_id: str | None = Field(
        default=None,
        description="The Domain Definition Sheet output this chart renders (O1–O26), "
        "for binding to a Builder output.",
    )
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
