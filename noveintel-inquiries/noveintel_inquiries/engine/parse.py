"""
Layer 1, first half — the parser.

Records in, the run's case set ``S`` out, plus a parse log that accounts for every
record that did not make it into ``S`` (Prerequisites §1.F, R2):

* ``(Do Not Modify) …`` system columns dropped; sensitive identity columns used once
  to redact the same row's text, then excluded (R3, BR-34/35);
* artefact rows — no case id — dropped and counted;
* duplicates across concatenated exports removed by case id, first occurrence kept;
* bilingual "English - عربي" labels split, so either half matches the catalogue;
* SLA values normalised to within / near / over / unspecified (colours, emoji,
  yes/no, نعم/لا);
* dates parsed ISO-first, then day-first;
* a multi-entity export scoped to the tenant;
* the case-type scope (X4) applied *after* dedup, excluded types counted;
* free text redacted before anything else reads it.

Nothing is dropped silently: ``ParseLog`` is reported in the methodology section
and returned in ``metrics.PARSE_LOG``.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..api.models.columns import COLUMNS, COLUMN_BY_NAME, LABEL_COLUMNS
from ..api.models.records import InquiryRecord
from ..api.models.settings import CaseTypeScope, RecordedType, TenantSettings
from .redact import redact
from .text import clean_label, fold_text

__all__ = ["Case", "ParseLog", "ParsedRun", "parse_records", "split_bilingual",
           "normalise_sla", "recorded_type_of", "parse_datetimes"]

_ARABIC = re.compile(r"[؀-ۿ]")
_LATIN = re.compile(r"[A-Za-z]")


@dataclass
class Case:
    """One in-scope case: universal columns, frozen labels, and what the run derives."""

    case_id: str
    description: str = ""          # redacted
    resolution_text: str = ""      # redacted
    description_missing: bool = False
    resolution_missing: bool = False
    case_type_raw: str = ""
    recorded_type: str | None = None   # RecordedType value
    crm_service: str = ""
    crm_service_en: str = ""
    crm_service_ar: str = ""
    crm_service_group: str = ""
    severity: str = ""
    channel: str = ""
    opened: datetime | None = None
    closed: datetime | None = None
    sla: str = "unspecified"
    sla_raw: str = ""
    status: str = ""
    department: str = ""
    owner: str = ""
    resolved_by: str = ""
    sub_hint: str = ""
    escalation: datetime | None = None
    entity: str = ""
    accepted: datetime | None = None
    classified_at: datetime | None = None
    first_response: datetime | None = None
    resolved_at: datetime | None = None
    updated: datetime | None = None
    customer_verdict: str = ""
    reopen: bool | None = None
    fcr: bool | None = None
    closure_reason: str = ""
    satisfaction: float | None = None
    crm_title: str = ""
    frozen: dict[str, Any] = field(default_factory=dict)

    # ── Derived by the classifier (D1–D8) ─────────────────────────────────────
    contact_type: str | None = None        # D1
    true_type: str | None = None
    main_service: str | None = None        # O
    sub_classification: str | None = None  # D2
    reason: str = ""                       # D3
    confidence: float | None = None        # D5
    provenance: str | None = None          # D6 key (see engine.wording.PROVENANCE)
    root_cause: str | None = None          # D7
    bundle: str | None = None              # D8 umbrella id
    deep_reviewed: bool = False            # went through the deep (second) AI review
    low_confidence: bool = False           # still below X6 after the deep review
    duplicate_of: str | None = None        # labels copied from this identical case
    evidence: str = ""
    corrections: list[str] = field(default_factory=list)
    faq_id: str | None = None              # S6.1 evidence link (R5)

    @property
    def misclassified(self) -> bool | None:
        """D4 — recorded type ≠ actual contact type. None when either is unknown."""
        from .wording import TYPE_TO_CONTACT

        if not self.recorded_type or not self.contact_type:
            return None
        recorded = TYPE_TO_CONTACT.get(self.recorded_type)
        return recorded != self.contact_type

    @property
    def is_closed(self) -> bool:
        return self.closed is not None

    @property
    def labelled(self) -> bool:
        return bool(self.main_service and self.sub_classification)


@dataclass
class ParseLog:
    records_received: int = 0
    artefact_rows_dropped: int = 0
    duplicates_removed: int = 0
    entity_rows_excluded: int = 0
    scope_excluded: dict[str, int] = field(default_factory=dict)
    case_types_present: dict[str, int] = field(default_factory=dict)
    unspecified_type_kept: int = 0
    in_scope_total: int = 0
    columns_mapped: list[str] = field(default_factory=list)
    columns_unmapped: list[str] = field(default_factory=list)
    columns_present_but_empty: list[str] = field(default_factory=list)
    label_columns_supplied: list[str] = field(default_factory=list)
    system_columns_dropped: list[str] = field(default_factory=list)
    sensitive_columns_excluded: list[str] = field(default_factory=list)
    unreadable_dates: int = 0
    dropped_at_stage: dict[str, int] = field(default_factory=dict)
    scope: str = ""

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class ParsedRun:
    cases: list[Case]
    log: ParseLog


# ── Value readers ─────────────────────────────────────────────────────────────


def split_bilingual(value: str) -> tuple[str, str]:
    """Split "English - عربي" into its halves. A one-language value fills one side."""
    value = clean_label(value)
    if not value:
        return "", ""
    has_ar, has_en = bool(_ARABIC.search(value)), bool(_LATIN.search(value))
    if not (has_ar and has_en):
        return (value, "") if has_en else ("", value)
    first_ar = _ARABIC.search(value).start()
    en = value[:first_ar].strip(" -–—_:\"'\n")
    ar = value[first_ar:].strip(" -–—_:\"'\n")
    if _LATIN.search(ar) and not _LATIN.search(en):
        # "عربي - English": the other way round.
        last_ar = max(m.end() for m in _ARABIC.finditer(value))
        ar, en = value[:last_ar].strip(" -–—_:"), value[last_ar:].strip(" -–—_:")
    return en, ar


_TYPE_TOKENS: list[tuple[str, tuple[str, ...]]] = [
    (RecordedType.COMPLIMENT, ("compliment", "شكر", "ثناء", "praise")),
    (RecordedType.COMPLAINT, ("complaint", "شكوي", "شكاوي", "شكوى")),
    (RecordedType.INCIDENT, ("incident", "حادث", "بلاغ", "عطل")),
    (RecordedType.SUGGESTION, ("suggestion", "اقتراح", "مقترح")),
    (RecordedType.INQUIRY, ("information", "inquiry", "enquiry", "معلومات", "استفسار")),
    (RecordedType.SERVICE_REQUEST, ("request", "service", "طلب")),
]


def recorded_type_of(raw: str, overrides: dict[str, RecordedType] | None = None) -> str | None:
    """The canonical recorded type, or None when the value is blank or unknown."""
    if not raw:
        return None
    if overrides:
        folded_overrides = {fold_text(k): v for k, v in overrides.items()}
        hit = folded_overrides.get(fold_text(raw))
        if hit:
            return RecordedType(hit).value
    folded = fold_text(raw)
    for kind, tokens in _TYPE_TOKENS:
        if any(fold_text(t) in folded for t in tokens):
            return RecordedType(kind).value
    return None


_SLA_EXACT = {
    "within": {"yes", "y", "true", "1", "نعم", "صح", "ضمن", "within", "green", "on time", "ontime"},
    "near": {"amber", "yellow", "near", "قرب"},
    "over": {"no", "n", "false", "0", "لا", "خطا", "red", "late", "over", "breach", "breached"},
}
_SLA_SUBSTR = {
    "within": ("green", "🟢", "within", "on time", "ضمن المهله", "خلال الوقت", "ملتزم", "compliant"),
    "near": ("amber", "yellow", "🟡", "near", "قرب", "warning", "وشك"),
    "over": ("red", "🔴", "overdue", "breach", "late", "متجاوز", "متاخر", "خارج المهله", "تجاوز"),
}


def normalise_sla(raw: object, strict: bool = False) -> str | None:
    """within / near / over, or None when the value says nothing about timeliness.

    ``strict`` accepts only unmistakable timeliness words — used when falling back to
    the status column, whose "Closed" must not be read as "on time".
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        return "within" if raw else "over"
    text = str(raw).strip()
    if not text:
        return None
    folded = fold_text(text)
    if not strict:
        for key, tokens in _SLA_EXACT.items():
            if folded in tokens:
                return key
    for key in ("near", "over", "within"):
        if any(fold_text(t) in folded or t in text for t in _SLA_SUBSTR[key]):
            if strict and key == "within" and folded in {"closed", "مغلق"}:
                continue
            return key
    return None


def parse_datetimes(values: list[object]) -> list[datetime | None]:
    """Parse dates positionally — ISO 8601 first, then day-first."""
    import pandas as pd

    if not values:
        return []
    series = pd.Series(values, dtype="object")
    blank = series.isna() | series.astype(str).str.strip().isin(["", "nan", "NaT", "None"])
    series = series.where(~blank, None)
    parsed = pd.to_datetime(series, errors="coerce", format="ISO8601")
    unresolved = parsed.isna() & ~blank
    if unresolved.any():
        fallback = pd.to_datetime(series[unresolved], errors="coerce", dayfirst=True, format="mixed")
        parsed = parsed.where(~unresolved, fallback)
    out: list[datetime | None] = []
    for value in parsed:
        if pd.isna(value):
            out.append(None)
        else:
            stamp = value.to_pydatetime()
            out.append(stamp.replace(tzinfo=None) if stamp.tzinfo else stamp)
    return out


def _common_prefix(values: list[str]) -> str:
    """A leading " - "-separated segment shared by most department values."""
    heads = Counter(v.split(" - ", 1)[0] for v in values if " - " in v)
    if not heads:
        return ""
    head, count = heads.most_common(1)[0]
    return head if count >= max(2, len(values) * 0.5) else ""


# ── The parser ────────────────────────────────────────────────────────────────

_DATETIME_FIELDS = {
    "opened_datetime": "opened",
    "closed_datetime": "closed",
    "escalation_datetime": "escalation",
    "accepted_datetime": "accepted",
    "classified_datetime": "classified_at",
    "first_response_datetime": "first_response",
    "resolved_datetime": "resolved_at",
    "updated_datetime": "updated",
}

_LABEL_FIELDS = {c.name: c.name.removeprefix("label_") for c in LABEL_COLUMNS}


def parse_records(
    records: list[InquiryRecord],
    settings: TenantSettings,
    tenant_names: tuple[str, ...] = (),
) -> ParsedRun:
    """Turn the request's records into the run's case set ``S`` and its parse log."""
    log = ParseLog(records_received=len(records))
    scope = settings.case_type_scope or CaseTypeScope.INQUIRIES_AND_SERVICE_REQUESTS
    log.scope = scope.value

    supplied: set[str] = set()
    unmapped: set[str] = set()
    system: set[str] = set()
    for record in records:
        supplied |= record.supplied_columns()
        unmapped |= set(record.extras())
        system |= set(record.system_columns())
    log.columns_mapped = [c.name for c in COLUMNS if c.name in supplied]
    log.label_columns_supplied = [c.name for c in LABEL_COLUMNS if c.name in supplied]
    log.columns_unmapped = sorted(unmapped)
    log.system_columns_dropped = sorted(system)
    log.sensitive_columns_excluded = sorted(
        n for n in supplied if n in COLUMN_BY_NAME and COLUMN_BY_NAME[n].uid.startswith("S-")
    )

    # Present-but-empty: supplied, but blank on every record.
    filled: set[str] = set()
    for record in records:
        for name in log.columns_mapped:
            if getattr(record, name, None) not in (None, ""):
                filled.add(name)
    log.columns_present_but_empty = [n for n in log.columns_mapped if n not in filled]

    # Artefact rows, then duplicates.
    kept: list[InquiryRecord] = []
    seen: set[str] = set()
    for record in records:
        case_id = clean_label(record.case_id)
        if not case_id:
            log.artefact_rows_dropped += 1
            continue
        if case_id in seen:
            log.duplicates_removed += 1
            continue
        seen.add(case_id)
        kept.append(record)

    # Multi-entity exports: keep the tenant's rows when the tenant is identifiable.
    entities = {clean_label(r.entity) for r in kept if r.entity}
    if len(entities) > 1 and tenant_names:
        wanted = [fold_text(n) for n in tenant_names if n]
        mine = {e for e in entities if any(w and w in fold_text(e) for w in wanted)}
        if mine:
            before = len(kept)
            kept = [r for r in kept if not r.entity or clean_label(r.entity) in mine]
            log.entity_rows_excluded = before - len(kept)

    # Dates, positionally, column by column.
    parsed_dates: dict[str, list[datetime | None]] = {}
    for column in _DATETIME_FIELDS:
        if column in supplied:
            raw = [getattr(r, column) for r in kept]
            values = parse_datetimes(raw)
            parsed_dates[column] = values
            if column == "opened_datetime":
                log.unreadable_dates = sum(
                    1 for r, v in zip(raw, values) if r not in (None, "") and v is None
                )

    departments = [clean_label(r.department) for r in kept if r.department]
    prefix = _common_prefix(departments)

    cases: list[Case] = []
    type_counts: Counter[str] = Counter()
    for position, record in enumerate(kept):
        case_type_raw = clean_label(record.case_type)
        type_counts[case_type_raw or "—"] += 1
        recorded = recorded_type_of(case_type_raw, settings.case_type_map)
        if not _in_scope(recorded, scope):
            key = recorded or "unspecified"
            log.scope_excluded[key] = log.scope_excluded.get(key, 0) + 1
            continue
        if recorded is None:
            log.unspecified_type_kept += 1

        case_id = clean_label(record.case_id)
        known = record.sensitive_values()
        description = record.description or ""
        resolution = record.resolution_text or ""
        crm_en, crm_ar = split_bilingual(record.crm_service or "")
        sla = normalise_sla(record.sla_status)
        if sla is None:
            sla = normalise_sla(record.status, strict=True)
        department = clean_label(record.department)
        if prefix and department.startswith(prefix + " - "):
            department = department[len(prefix) + 3:].strip()

        case = Case(
            case_id=case_id,
            description=redact(description, known, case_id),
            resolution_text=redact(resolution, known, case_id),
            description_missing=not description.strip(),
            resolution_missing=not resolution.strip(),
            case_type_raw=case_type_raw,
            recorded_type=recorded,
            crm_service=clean_label(record.crm_service),
            crm_service_en=crm_en,
            crm_service_ar=crm_ar,
            crm_service_group=clean_label(record.crm_service_group),
            severity=clean_label(record.severity),
            channel=clean_label(record.channel),
            sla=sla or "unspecified",
            sla_raw=clean_label(record.sla_status),
            status=clean_label(record.status),
            department=department,
            owner=clean_label(record.owner),
            resolved_by=clean_label(record.resolved_by),
            sub_hint=clean_label(record.sub_classification_hint),
            entity=clean_label(record.entity),
            customer_verdict=clean_label(record.customer_verdict),
            reopen=record.reopen_flag,
            fcr=record.fcr_flag,
            closure_reason=clean_label(record.closure_reason),
            satisfaction=record.satisfaction_score,
            crm_title=redact(record.crm_title or "", known, case_id),
        )
        for column, attr in _DATETIME_FIELDS.items():
            if column in parsed_dates:
                setattr(case, attr, parsed_dates[column][position])
        for column, key in _LABEL_FIELDS.items():
            value = getattr(record, column, None)
            if value not in (None, ""):
                case.frozen[key] = value
        cases.append(case)

    log.case_types_present = dict(type_counts.most_common())
    log.in_scope_total = len(cases)
    return ParsedRun(cases=cases, log=log)


def _in_scope(recorded: str | None, scope: CaseTypeScope) -> bool:
    if recorded is None or scope is CaseTypeScope.ALL_RECORDED_TYPES:
        return True
    if scope is CaseTypeScope.INQUIRIES_ONLY:
        return recorded == RecordedType.INQUIRY.value
    return recorded in (RecordedType.INQUIRY.value, RecordedType.SERVICE_REQUEST.value)
