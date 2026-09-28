"""
The input payload for a complaints analysis run.

The request carries the data itself — file parsing happens upstream — plus the
run-level options and the tenant identity pack.

``entity`` is Module 03's territory in the long run, but until a client-profile store
exists there is nowhere else to read it from, so every request states who the report
is for. There is no default: a report must never carry another tenant's name, logo or
colours.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .entity import EntityInfo
from .enums import Language, PeriodGranularity
from .records import ComplaintRecord

__all__ = ["AnalysisOptions", "GenerateComplaintsReportRequest"]

# Above this, a run is long enough that a caller should be warned rather than left
# to discover it from a poll that does not settle for half an hour. It is not a
# limit — the job is accepted either way — see ``max_records`` on ApiSettings for
# the limit.
LARGE_RUN_RECORDS = 5000


class AnalysisOptions(BaseModel):
    """Run-level settings for a single analysis.

    Deliberately short. The knobs here are the ones the pipeline actually honours;
    an option the six stages ignore would be a lie in the OpenAPI document, so there
    isn't one.
    """

    language: Language = Field(
        default=Language.AR,
        description=(
            "The primary report language — which document the run is *for*. The "
            "Arabic report is always produced, because the analysis itself runs in "
            "Arabic; this marks which one the caller asked for, and is echoed back "
            "as the bundle's ``primary_language``. To decide whether an English "
            "report is produced at all, use ``include_english``."
        ),
    )
    include_english: bool = Field(
        default=True,
        description=(
            "Whether to produce the English report. The English document is a full "
            "translation of all nine sections and is the single largest block of "
            "tokens in a run — switching it off roughly halves the cost and the wall "
            "clock. Off means no English document, no English report data, and no "
            "warning: it was not wanted, so it is not missing."
        ),
    )
    granularity: PeriodGranularity | None = Field(
        default=None,
        description=(
            "Granularity to express the reporting period at. Omit to derive it from "
            "the span of the case dates, which is what almost every caller wants. "
            "Setting it does not filter the data — every record sent is analysed; it "
            "only changes how the period is labelled."
        ),
    )


class GenerateComplaintsReportRequest(BaseModel):
    """The full input payload for a complaints analysis run."""

    records: list[ComplaintRecord] = Field(
        min_length=1,
        description=(
            "The period's cases, one object per row. Field names may be the "
            "snake_case form or the normalised Arabic column name — both are "
            "accepted, and a payload may mix them."
        ),
    )
    options: AnalysisOptions = Field(
        default_factory=AnalysisOptions,
        description="Run-level settings. Omit to accept the defaults.",
    )
    entity: EntityInfo = Field(
        description=(
            "Identity and branding of the organisation the report is for — name, "
            "logo, brand colours, closing statement. Required, and with no defaults "
            "of its own: a report must never carry another tenant's identity."
        )
    )

    @property
    def is_large(self) -> bool:
        """Whether this run is big enough to be worth warning the caller about."""
        return len(self.records) >= LARGE_RUN_RECORDS
