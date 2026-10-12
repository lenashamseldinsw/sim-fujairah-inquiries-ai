"""
The input payload for an inquiries analysis run.

The request carries the data itself — mapping and file parsing happen upstream in the
platform's data home — plus the tenant's settings (X1–X12), its reference lists, the
stored history the comparison reads, and the identity pack.

``missing_required_fields`` is the one place "required" is decided. A required column
absent from every record, a required setting not sent, and the required taxonomy all
come back in one ``missing_required_columns`` answer:

    The following input field(s) were missing or unmapped: case_id (U1 · رقم الطلب),
    settings.case_type_scope (X4 · Case-type scope / نطاق أنواع الحالات).
"""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field, field_validator

from .columns import REQUIRED_COLUMNS
from .entity import EntityInfo
from .enums import SECTION_IDS, Language, PeriodGranularity, ReportSection
from .records import InquiryRecord
from .reference import History, ReferenceLists
from .settings import REQUIRED_SETTINGS, TenantSettings

__all__ = [
    "AnalysisOptions",
    "GenerateInquiriesReportRequest",
    "MissingField",
    "missing_required_fields",
    "missing_fields_message",
    "LARGE_RUN_RECORDS",
]

# Above this a run is long enough that a caller should be warned. Not a limit.
LARGE_RUN_RECORDS = 5000


class AnalysisOptions(BaseModel):
    """Run-level output options."""

    language: Language = Field(
        default=Language.AR,
        description="The primary report language. Echoed as the bundle's "
        "``primary_language``. The Arabic report is always produced.",
    )
    include_english: bool = Field(
        default=True,
        description="Whether to produce the English report. It is a translation of the "
        "finished Arabic narrative, made in the background, and needs English names in "
        "the taxonomy — without them the English export is unavailable and a warning "
        "says so (Domain 01 ruling).",
    )
    sections: list[ReportSection] | None = Field(
        default=None,
        description="The report sections to produce, by key (``executive_summary``) or "
        "id (``S1``), in any order — the report keeps its own order. Omit for every "
        "section the run can produce. The cover (S0) is always included. S10 and S11 "
        "also need root-cause extraction (X8); asked for without it they are left out "
        "with a ``section_omitted`` warning. A hidden section still feeds the sections "
        "that depend on it (Definition Sheet §6, decision #6): its analysis runs when a "
        "shown section needs it and is skipped when none does.",
    )

    @field_validator("sections", mode="before")
    @classmethod
    def _section_ids(cls, value):
        if value is None:
            return None
        by_id = {sid.lower(): section.value for section, sid in SECTION_IDS.items()}
        out = []
        for item in value:
            text = str(item).strip()
            out.append(by_id.get(text.lower(), text.lower()))
        return out
    granularity: PeriodGranularity | None = Field(
        default=None,
        description="Granularity to label the period at. Omit to derive it from the "
        "span of the opening dates. Relabels; never filters.",
    )


class GenerateInquiriesReportRequest(BaseModel):
    """The full input payload for an inquiries analysis run."""

    records: list[InquiryRecord] = Field(
        min_length=1,
        description="The period's cases, one object per row, keyed by the universal "
        "column names (or a recognised header spelling — see the schema docs).",
    )
    settings: TenantSettings = Field(
        default_factory=TenantSettings,
        description="The tenant's context fields X1–X12. X2, X3 and X4 are required.",
    )
    reference_lists: ReferenceLists = Field(
        default_factory=ReferenceLists,
        description="The tenant's reference lists. ``taxonomy`` is required.",
    )
    history: History | None = Field(
        default=None,
        description="Stored snapshots of earlier runs, for the period comparison.",
    )
    options: AnalysisOptions = Field(default_factory=AnalysisOptions)
    entity: EntityInfo = Field(
        description="Identity and branding of the organisation the report is for. "
        "Required, with no tenant defaults."
    )

    @property
    def is_large(self) -> bool:
        return len(self.records) >= LARGE_RUN_RECORDS


@dataclass(frozen=True)
class MissingField:
    """One required input that did not arrive."""

    field: str
    uid: str
    label: str

    def describe(self) -> str:
        return f"{self.field} ({self.uid} · {self.label})"


def missing_required_fields(request: GenerateInquiriesReportRequest) -> list[MissingField]:
    """Every required input the request lacks, columns first.

    A column counts as present when any record carries it — a blank cell is
    present-but-empty, which degrades rather than refuses.
    """
    supplied: set[str] = set()
    for record in request.records:
        supplied |= record.supplied_columns()

    missing = [
        MissingField(spec.name, spec.uid, f"{spec.label_ar} / {spec.label_en}")
        for spec in REQUIRED_COLUMNS
        if spec.name not in supplied
    ]
    for name, (uid, label) in REQUIRED_SETTINGS.items():
        if getattr(request.settings, name) is None:
            missing.append(MissingField(f"settings.{name}", uid, label))
    if request.reference_lists.taxonomy is None:
        missing.append(
            MissingField(
                "reference_lists.taxonomy",
                "OCL",
                "Classification taxonomy / التصنيف — a catalogue, or 'adpf_codebook_v1'",
            )
        )
    return missing


def missing_fields_message(missing: list[MissingField]) -> str:
    return (
        "The following input field(s) were missing or unmapped: "
        + ", ".join(m.describe() for m in missing)
        + "."
    )
