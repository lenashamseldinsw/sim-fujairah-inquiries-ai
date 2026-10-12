"""
The universal columns: what one case can carry, under one name each.

The Domain Definition Sheet §3 reconciles three real exports — the Fujairah inquiries
file, the Fujairah complaints file and the ADPF/TAMM export — onto the universal
columns U1–U25. This module is that table as code. Each column has one canonical
snake_case name (the name in this API's contract), its U-id, its Arabic and English
labels, and the header spellings it is recognised under.

**Mapping is the platform's job; recognising is ours.** In production the
NoveIntelligence data home maps a tenant's headers onto these names before a request
is sent, so a record normally arrives keyed by the canonical names. The aliases exist
so a record keyed by a known export header — «رقم الطلب», ``Case Number`` — still
lands, and so the Streamlit-era field names (``case_number``, ``case_details``) keep
working. Matching is by *folded* header (``engine.text.fold_header``): «الإداره
العامة», «الإدارة_العامة» and «الادارة العامه» are one column. That is
Platformisation requirement R4 — normalisation, not a spelling list.

**Four kinds of key a record can carry:**

* a universal column (U1–U25, plus the two captured-but-unused ADPF columns);
* a frozen label (D1–D8) — classification an earlier run already settled and
  the platform stored, which the run must not overwrite;
* a sensitive column — customer identity. Recognised so it can be *excluded at
  ingest* (BR-34/35, R3): its values are used once, to redact the free text of the
  same row, and then dropped. They never reach a model, a sheet or a log;
* anything else — passed through, recorded in the parse log as unmapped, and never
  read by a section (R4).

``(Do Not Modify) …`` system columns from Dynamics-style exports are dropped and
counted.

Pure: no pydantic, no pandas. The contract models and the parser both read it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ...engine.text import fold_header

__all__ = [
    "ColumnKind",
    "ColumnSpec",
    "COLUMNS",
    "LABEL_COLUMNS",
    "SENSITIVE_COLUMNS",
    "REQUIRED_COLUMNS",
    "COLUMN_BY_NAME",
    "resolve_header",
    "is_system_column",
    "HeaderMatch",
]


class ColumnKind(StrEnum):
    """What a column holds, which decides how the parser reads it."""

    TEXT = "text"
    LONG_TEXT = "long_text"
    DATETIME = "datetime"
    FLAG = "flag"
    NUMBER = "number"


@dataclass(frozen=True)
class ColumnSpec:
    """One universal (or label, or sensitive) column."""

    name: str
    uid: str
    label_ar: str
    label_en: str
    kind: ColumnKind = ColumnKind.TEXT
    required: bool = False
    aliases: tuple[str, ...] = ()
    role: str = ""
    folded: frozenset[str] = field(default=frozenset(), compare=False)

    def all_spellings(self) -> tuple[str, ...]:
        return (self.name, self.label_ar, self.label_en, *self.aliases)


def _spec(name: str, uid: str, label_ar: str, label_en: str, **kwargs) -> ColumnSpec:
    spec = ColumnSpec(name, uid, label_ar, label_en, **kwargs)
    folded = frozenset(fold_header(s) for s in spec.all_spellings() if s)
    return ColumnSpec(**{**spec.__dict__, "folded": folded})


_T, _L, _D, _F, _N = (
    ColumnKind.TEXT,
    ColumnKind.LONG_TEXT,
    ColumnKind.DATETIME,
    ColumnKind.FLAG,
    ColumnKind.NUMBER,
)

# ── Universal columns (Definition Sheet §3) ───────────────────────────────────
COLUMNS: tuple[ColumnSpec, ...] = (
    _spec(
        "case_id", "U1", "رقم الطلب", "Case ID", required=True,
        aliases=("Case Number", "case_number", "رقم الحالة"),
        role="Dedup key; evidence ids. A row without one is an export artefact: dropped and counted.",
    ),
    _spec(
        "description", "U2", "تفاصيل الطلب", "Description", kind=_L, required=True,
        aliases=("case_details", "وصف الحالة"),
        role="What the customer asked. Classification input H; redacted before any model sees it.",
    ),
    _spec(
        "resolution_text", "U3", "الحل", "Resolution", kind=_L, required=True,
        aliases=("Resolution Response", "resolution", "رد المعالجة"),
        role="What the agent did. Classification input I — outranks the description.",
    ),
    _spec(
        "case_type", "U4", "نوع المكالمة", "Recorded type", required=True,
        aliases=("Case Type", "contact_type", "نوع الحالة"),
        role="The CRM's own type label. Scope filter and the recorded side of recorded-vs-actual.",
    ),
    _spec(
        "crm_service", "U5", "الخدمة", "Recorded service",
        aliases=("Service Name", "service"),
        role="The CRM's service tag. Context only — the recorded side of RECORDED_VS_TRUE.",
    ),
    _spec(
        "crm_service_group", "U6", "الخدمة الرئيسية", "Recorded main service",
        aliases=("Service Category", "main_service"),
        role="The CRM's service grouping. Classifier context only.",
    ),
    _spec(
        "severity", "U7", "شدة الطلب", "Severity",
        aliases=("Priority", "شدة الشكوى"),
        role="Severity distribution; labels relabelled through the vocabulary list.",
    ),
    _spec(
        "channel", "U8", "قناة تقديم الخدمة", "Channel",
        aliases=("Case Channel", "service_channel", "قناه تقديم الخدمة", "القناة"),
        role="Channel mix and the digital-channel share.",
    ),
    _spec(
        "opened_datetime", "U9", "تاريخ الإنشاء", "Opened date-time", kind=_D, required=True,
        aliases=("Date Opened", "date_opened", "Created On"),
        role="Period anchor and the monthly distribution.",
    ),
    _spec(
        "closed_datetime", "U10", "تاريخ إغلاق الطلب", "Closed date-time", kind=_D,
        aliases=("date_closed", "تاريخ الإغلاق", "Date Closed"),
        role="Closed-cases count. Blank means open.",
    ),
    _spec(
        "sla_status", "U11", "إغلاق الطلب خلال الوقت المحدد", "SLA status",
        aliases=("SLA Color", "sla_compliance", "سلا امتثال", "SLA Status"),
        role="Normalised to within / near / over / unspecified.",
    ),
    _spec(
        "status", "U12", "الحالة", "Status",
        aliases=("Status", "الحالة SLA", "Case Status"),
        role="Open/closed split, pending detection, and the SLA fallback when U11 is blank.",
    ),
    _spec(
        "department", "U13", "الإدارة العامة", "Department",
        aliases=("general_administration", "إدارة عامة", "Department"),
        role="Department distribution.",
    ),
    _spec(
        "owner", "U14", "المالك", "Owner",
        aliases=("Owner",),
        role="Agent-level reporting (X9) when enabled; queue owners are told from people.",
    ),
    _spec(
        "resolved_by", "U15", "تم الحل بواسطة", "Resolved by",
        role="Carried to the companion workbook only.",
    ),
    _spec(
        "sub_classification_hint", "U16", "التصنيف الفرعي", "Sub-classification hint",
        aliases=("sub_classification",),
        role="A hint for the rule chain when it names a taxonomy entry.",
    ),
    _spec(
        "escalation_datetime", "U17", "موعد التصعيد", "Escalation date-time", kind=_D,
        aliases=("Next Escalation Date",),
        role="SLA window; pending-case detection.",
    ),
    _spec(
        "entity", "U18", "الإمارة", "Entity / emirate",
        aliases=("Entity", "الجهة"),
        role="Scoping a multi-entity export.",
    ),
    _spec(
        "accepted_datetime", "U19", "تاريخ القبول", "Accepted date-time", kind=_D,
        role="TAMM acceptance indicator.",
    ),
    _spec(
        "classified_datetime", "U20", "تاريخ التصنيف", "Classified date-time", kind=_D,
        role="TAMM classification indicator.",
    ),
    _spec(
        "first_response_datetime", "U21", "تاريخ أول رد", "First-response date-time", kind=_D,
        role="Timestamp-based timeliness.",
    ),
    _spec(
        "resolved_datetime", "U22", "تاريخ الحل", "Resolved date-time", kind=_D,
        aliases=("Resolved On",),
        role="TAMM resolution indicator and timestamp-based timeliness.",
    ),
    _spec(
        "customer_verdict", "U23", "رأي المتعامل", "Customer verdict",
        role="TAMM accuracy indicator (accepted / dissatisfied).",
    ),
    _spec(
        "reopen_flag", "U24", "إعادة فتح", "Reopen flag", kind=_F,
        role="TAMM accuracy indicator.",
    ),
    _spec(
        "fcr_flag", "U25", "الحل من أول اتصال", "First-contact resolution flag", kind=_F,
        aliases=("FCR",),
        role="TAMM first-contact-resolution indicator.",
    ),
    _spec(
        "closure_reason", "U25b", "سبب الإغلاق", "Closure reason",
        role="FCR exclusions (auto-closed, closed on customer request, …).",
    ),
    _spec(
        "satisfaction_score", "U25c", "درجة الرضا", "Satisfaction score", kind=_N,
        role="Carried; a metric gap recommendation when absent.",
    ),
    # Captured but not used (Prerequisites §2.1.B).
    _spec(
        "crm_title", "U-title", "عنوان الحالة", "Case title",
        aliases=("Case Title",),
        role="The CRM's auto-title. Never used as truth (codebook golden rule).",
    ),
    _spec(
        "updated_datetime", "U-updated", "تاريخ التحديث", "Updated date-time", kind=_D,
        aliases=("Updated Date",),
        role="Last touch. Not a closure proxy unless the tenant says so.",
    ),
)

# ── Frozen labels (D1–D8): classification already settled upstream ────────────
LABEL_COLUMNS: tuple[ColumnSpec, ...] = (
    _spec(
        "label_contact_type", "D1", "التصنيف الفعلي", "Actual contact type",
        aliases=("actual_contact_type",),
    ),
    _spec(
        "label_main_service", "D2a", "الخدمة الرئيسية المصنفة", "Classified main service",
        aliases=("classified_main_service",),
    ),
    _spec(
        "label_sub_classification", "D2", "تصنيف إدارة التميز", "Classified sub-classification",
        aliases=("classified_sub_classification",),
    ),
    _spec(
        "label_reason", "D3", "سبب التصنيف", "Classification reason",
        aliases=("classification_reason",),
    ),
    _spec(
        "label_confidence", "D5", "ثقة النموذج", "Confidence", kind=_N,
        aliases=("ثقة التصنيف", "confidence"),
    ),
    _spec(
        "label_provenance", "D6", "مصدر السبب الجذري", "Provenance",
        aliases=("مصدر التصنيف", "provenance"),
    ),
    _spec(
        "label_root_cause", "D7", "السبب الجذري للاستفسار", "Root cause",
        aliases=("root_cause",),
    ),
    _spec(
        "label_bundle", "D8", "حزمة السبب الجذري", "Bundle",
        aliases=("الحزمة الموضوعية", "bundle", "umbrella"),
    ),
    _spec(
        "label_true_type", "D1b", "النوع الحقيقي", "True type",
        aliases=("true_type",),
    ),
)

# ── Sensitive: never universal, excluded at ingest (R3) ───────────────────────
SENSITIVE_COLUMNS: tuple[ColumnSpec, ...] = (
    _spec("customer_name", "S-name", "اسم مقدم الطلب", "Customer",
          aliases=("applicant_name", "اسم المتعامل", "Customer Name")),
    _spec("nationality", "S-nat", "الجنسية", "Nationality"),
    _spec("national_id", "S-id", "رقم الهوية", "ID number",
          aliases=("emirates_id", "id_number", "Emirates ID")),
    _spec("mobile", "S-mob", "الهاتف الجوال", "Mobile",
          aliases=("mobile_number", "phone", "رقم الهاتف", "Phone")),
    _spec("employee_number", "S-emp", "الرقم الوظيفي", "Employee number",
          aliases=("الرقم الوظيفى",)),
    _spec("created_by", "S-by", "انشاء بواسطة", "Created by",
          aliases=("إنشاء بواسطة",)),
    _spec("email", "S-mail", "البريد الإلكتروني", "Email", aliases=("e-mail",)),
)

REQUIRED_COLUMNS: tuple[ColumnSpec, ...] = tuple(c for c in COLUMNS if c.required)

COLUMN_BY_NAME: dict[str, ColumnSpec] = {
    c.name: c for c in (*COLUMNS, *LABEL_COLUMNS, *SENSITIVE_COLUMNS)
}

_SYSTEM_PREFIX = fold_header("(Do Not Modify)")


class HeaderMatch(StrEnum):
    UNIVERSAL = "universal"
    LABEL = "label"
    SENSITIVE = "sensitive"
    SYSTEM = "system"
    UNMAPPED = "unmapped"


def _index() -> dict[str, tuple[ColumnSpec, HeaderMatch]]:
    index: dict[str, tuple[ColumnSpec, HeaderMatch]] = {}
    groups = (
        (COLUMNS, HeaderMatch.UNIVERSAL),
        (LABEL_COLUMNS, HeaderMatch.LABEL),
        (SENSITIVE_COLUMNS, HeaderMatch.SENSITIVE),
    )
    for specs, kind in groups:
        for spec in specs:
            for folded in spec.folded:
                # First registration wins: a universal spelling is never shadowed
                # by a label or sensitive one that happens to fold the same.
                index.setdefault(folded, (spec, kind))
    return index


_HEADER_INDEX = _index()


def is_system_column(header: object) -> bool:
    """A Dynamics ``(Do Not Modify) …`` system column."""
    return fold_header(header).startswith(_SYSTEM_PREFIX)


def resolve_header(header: object) -> tuple[ColumnSpec | None, HeaderMatch]:
    """Which column a header names, and what kind of column it is."""
    if is_system_column(header):
        return None, HeaderMatch.SYSTEM
    hit = _HEADER_INDEX.get(fold_header(header))
    if hit is None:
        return None, HeaderMatch.UNMAPPED
    return hit
