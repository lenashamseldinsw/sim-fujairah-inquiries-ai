"""
One customer-contact case, as the platform sends it.

Records arrive already mapped. The NoveIntelligence data home maps each tenant's
export headers onto the universal columns (``columns.py``) before calling this
service, so a record is normally keyed by canonical snake_case names —
``case_id``, ``description``, ``resolution_text``. A record keyed by a recognised
export header (``Case Number``, «رقم الطلب») or by this API's earlier field names
(``case_number``, ``case_details``) is renamed on the way in, matching headers by
their folded spelling rather than a list (R4). See ``columns.py``.

**Required is checked per column, not per record.** The five hard-required columns
(U1–U4 and U9) must be present in the export — present in at least one record — or
the request is refused with ``missing_required_columns`` naming them. A present
column that is blank in a given row is not a refusal: a blank case id marks an export
artefact row, which is dropped and counted; a blank description or resolution
degrades that case to «لم يُزوَّد». That is the Domain 01 ruling the Prerequisites
carry over: absent column → refused; present-but-empty → degraded and said so.

**Frozen labels.** A record may carry ``label_*`` fields — D1–D8 settled in an
earlier run and stored by the platform. Those are respected: the classifier never
overwrites a supplied label, and only fills the ones that are missing.

**Sensitive columns** (customer name, ID number, mobile, …) are accepted so their
values can redact the same row's free text, then dropped before anything else reads
the row. They are never stored, sent to a model, or written to an artefact.

Unknown keys are kept and passed through to the parse log as unmapped columns.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._coercion import OptionalFlag, OptionalNumber, OptionalStr
from .columns import (
    COLUMN_BY_NAME,
    COLUMNS,
    LABEL_COLUMNS,
    REQUIRED_COLUMNS,
    SENSITIVE_COLUMNS,
    HeaderMatch,
    resolve_header,
)

__all__ = [
    "HARD_REQUIRED_COLUMNS",
    "InquiryRecord",
    "canonical_key",
]

# The columns a run is refused without, by canonical name.
HARD_REQUIRED_COLUMNS: frozenset[str] = frozenset(c.name for c in REQUIRED_COLUMNS)


def canonical_key(key: str) -> str:
    """The canonical name a record key maps to, or the key itself when unmapped."""
    if key in COLUMN_BY_NAME:
        return key
    spec, kind = resolve_header(key)
    if spec is not None and kind in (
        HeaderMatch.UNIVERSAL, HeaderMatch.LABEL, HeaderMatch.SENSITIVE
    ):
        return spec.name
    return key


def _describe(name: str) -> str:
    spec = COLUMN_BY_NAME[name]
    text = f"{spec.uid} · {spec.label_en} / {spec.label_ar}."
    return f"{text} {spec.role}".strip()


class InquiryRecord(BaseModel):
    """A single case from the period being analysed."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    # ── Universal columns ─────────────────────────────────────────────────────
    case_id: OptionalStr = Field(default=None, description=_describe("case_id"))
    description: OptionalStr = Field(default=None, description=_describe("description"))
    resolution_text: OptionalStr = Field(
        default=None, description=_describe("resolution_text")
    )
    case_type: OptionalStr = Field(default=None, description=_describe("case_type"))
    crm_service: OptionalStr = Field(default=None, description=_describe("crm_service"))
    crm_service_group: OptionalStr = Field(
        default=None, description=_describe("crm_service_group")
    )
    severity: OptionalStr = Field(default=None, description=_describe("severity"))
    channel: OptionalStr = Field(default=None, description=_describe("channel"))
    opened_datetime: OptionalStr = Field(
        default=None,
        description=_describe("opened_datetime")
        + " ISO 8601 is safest; slash dates are read day-first.",
    )
    closed_datetime: OptionalStr = Field(default=None, description=_describe("closed_datetime"))
    sla_status: OptionalStr = Field(
        default=None,
        description=_describe("sla_status")
        + " Accepts SLA colours (🟢 Green / 🟡 Amber / 🔴 Red), yes/no, نعم/لا and booleans.",
    )
    status: OptionalStr = Field(default=None, description=_describe("status"))
    department: OptionalStr = Field(default=None, description=_describe("department"))
    owner: OptionalStr = Field(default=None, description=_describe("owner"))
    resolved_by: OptionalStr = Field(default=None, description=_describe("resolved_by"))
    sub_classification_hint: OptionalStr = Field(
        default=None, description=_describe("sub_classification_hint")
    )
    escalation_datetime: OptionalStr = Field(
        default=None, description=_describe("escalation_datetime")
    )
    entity: OptionalStr = Field(default=None, description=_describe("entity"))
    accepted_datetime: OptionalStr = Field(default=None, description=_describe("accepted_datetime"))
    classified_datetime: OptionalStr = Field(
        default=None, description=_describe("classified_datetime")
    )
    first_response_datetime: OptionalStr = Field(
        default=None, description=_describe("first_response_datetime")
    )
    resolved_datetime: OptionalStr = Field(default=None, description=_describe("resolved_datetime"))
    customer_verdict: OptionalStr = Field(default=None, description=_describe("customer_verdict"))
    reopen_flag: OptionalFlag = Field(default=None, description=_describe("reopen_flag"))
    fcr_flag: OptionalFlag = Field(default=None, description=_describe("fcr_flag"))
    closure_reason: OptionalStr = Field(default=None, description=_describe("closure_reason"))
    satisfaction_score: OptionalNumber = Field(
        default=None, description=_describe("satisfaction_score")
    )
    crm_title: OptionalStr = Field(default=None, description=_describe("crm_title"))
    updated_datetime: OptionalStr = Field(default=None, description=_describe("updated_datetime"))

    # ── Frozen labels (D1–D8) ─────────────────────────────────────────────────
    label_contact_type: OptionalStr = Field(
        default=None,
        description="D1, already settled: استفسار | طلب خدمة | شكوى | شكر وثناء.",
    )
    label_true_type: OptionalStr = Field(
        default=None,
        description="Type detection, already settled: inquiry | service_request | "
        "complaint | incident | compliment | out_of_scope.",
    )
    label_main_service: OptionalStr = Field(
        default=None, description="Main service (O), already settled. A taxonomy name."
    )
    label_sub_classification: OptionalStr = Field(
        default=None, description="D2 sub-classification (N), already settled."
    )
    label_reason: OptionalStr = Field(default=None, description="D3, already settled.")
    label_confidence: OptionalNumber = Field(default=None, description="D5, 0–1.")
    label_provenance: OptionalStr = Field(
        default=None,
        description="D6: قاعدة | نموذج | آلي - موثوق | آلي - مُصحّح | يدوي - مُراجع.",
    )
    label_root_cause: OptionalStr = Field(default=None, description="D7, already settled.")
    label_bundle: OptionalStr = Field(
        default=None, description="D8 umbrella, already settled — the confirmed set's name."
    )

    # ── Sensitive (excluded at ingest) ────────────────────────────────────────
    customer_name: OptionalStr = Field(
        default=None,
        exclude=True,
        description="Sensitive. Used only to redact this row's free text, then dropped.",
    )
    nationality: OptionalStr = Field(default=None, exclude=True, description="Sensitive.")
    national_id: OptionalStr = Field(default=None, exclude=True, description="Sensitive.")
    mobile: OptionalStr = Field(default=None, exclude=True, description="Sensitive.")
    employee_number: OptionalStr = Field(default=None, exclude=True, description="Sensitive.")
    created_by: OptionalStr = Field(default=None, exclude=True, description="Sensitive.")
    email: OptionalStr = Field(default=None, exclude=True, description="Sensitive.")

    @model_validator(mode="before")
    @classmethod
    def _rename_known_headers(cls, data: Any) -> Any:
        """Rename recognised header spellings to their canonical field names.

        The first key that maps to a column wins; a later spelling of the same column
        is kept under its own name as an unmapped pass-through rather than silently
        overwriting the first. ``(Do Not Modify)`` system columns are dropped here.
        """
        if not isinstance(data, dict):
            return data
        renamed: dict[str, Any] = {}
        for key, value in data.items():
            name = canonical_key(str(key))
            if name == key and resolve_header(key)[1] is HeaderMatch.SYSTEM:
                renamed.setdefault("__system__", []).append(str(key))
                continue
            if name in renamed and name != key:
                renamed.setdefault(str(key), value)
                continue
            renamed[name] = value
        system = renamed.pop("__system__", None)
        if system:
            renamed["__system_columns__"] = system
        return renamed

    def sensitive_values(self) -> list[str]:
        """This row's identity values, for redacting its own free text."""
        values = [getattr(self, c.name) for c in SENSITIVE_COLUMNS]
        return [v for v in values if v]

    def supplied_columns(self) -> set[str]:
        """Canonical columns this record actually carried (a blank cell counts)."""
        extra = {k for k in (self.__pydantic_extra__ or {}) if k != "__system_columns__"}
        return set(self.model_fields_set) | extra

    def extras(self) -> dict[str, Any]:
        """Unmapped pass-through keys."""
        return {
            k: v for k, v in (self.__pydantic_extra__ or {}).items()
            if k != "__system_columns__"
        }

    def system_columns(self) -> list[str]:
        return list((self.__pydantic_extra__ or {}).get("__system_columns__") or [])


UNIVERSAL_NAMES = tuple(c.name for c in COLUMNS)
LABEL_NAMES = tuple(c.name for c in LABEL_COLUMNS)
SENSITIVE_NAMES = tuple(c.name for c in SENSITIVE_COLUMNS)
