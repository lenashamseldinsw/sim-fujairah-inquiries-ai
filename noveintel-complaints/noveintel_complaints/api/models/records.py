"""
One complaint case, as the caller sends it.

File parsing stays with the caller (porting guide §2): the Streamlit app read an
Excel export — with the header on row 5, and the right sheet chosen by counting data
rows — and this service takes the rows already structured. ``scripts/
make_fixtures.py`` turns a real export into a ready-to-POST body, and that script —
not the service — is where that spreadsheet knowledge now lives.

**Two names for every field.** The JSON name is snake_case, per the cross-module
convention, and the alias is the normalised Arabic column the pipeline's stage 1
expects. Either is accepted.

**Four fields are required**: the case number, the request details, the resolution
and the service. The service is required here where it is optional in the inquiries
module, and that is not an oversight — it is the primary classification signal for a
complaint, and stage 1 refuses a run without it.

**This contract carries personal data.** ``applicant_name``, ``national_id``,
``mobile`` and ``employee_number`` identify a real person. They are optional: send
them only if the report needs them, because everything sent is written into the
workbook this run stores. The error handler never echoes a rejected record back —
see ``api/errors.py`` — for exactly this reason.

Unknown keys are kept (``extra="allow"``) and passed through to the dataframe, so a
tenant recording a column this contract has not heard of still has it counted in the
"structured fields" figure the methodology section prints.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ._coercion import OptionalFlag, OptionalStr, RequiredStr, is_blank

__all__ = [
    "HARD_REQUIRED_COLUMNS",
    "PERSONAL_DATA_FIELDS",
    "ComplaintRecord",
    "records_to_frame",
]

# The columns stage 1 refuses a run without, named by their JSON field. Used by the
# error handler to fold a hundred thousand identical per-record failures into one.
HARD_REQUIRED_COLUMNS: frozenset[str] = frozenset(
    {"case_number", "case_details", "resolution", "service"}
)

# Fields that identify a real person. Named so a caller can strip them in one step,
# and so the smoke script can refuse to print them.
PERSONAL_DATA_FIELDS: frozenset[str] = frozenset(
    {"applicant_name", "nationality", "national_id", "mobile", "employee_number"}
)


class ComplaintRecord(BaseModel):
    """A single complaint case from the period being analysed."""

    model_config = ConfigDict(
        populate_by_name=True,
        # Accept a column this contract does not model rather than reject the row.
        extra="allow",
    )

    # ── Required ──────────────────────────────────────────────────────────────
    case_number: RequiredStr = Field(
        alias="رقم_الطلب",
        description=(
            "The case reference, unique within the export. Carried through to the "
            "workbook so a figure in the report can be traced back to the rows "
            "behind it. A string, not a number: leading zeros are meaningful."
        ),
    )
    case_details: RequiredStr = Field(
        alias="تفاصيل_الطلب",
        description=(
            "What the customer complained about, in their own words. One of the two "
            "free-text fields the classification reads, and the main signal for the "
            "friction and root-cause analysis."
        ),
    )
    resolution: RequiredStr = Field(
        alias="الحل",
        description=(
            "How the complaint was answered or closed, in free text. The second "
            "free-text field the classification reads, and what the gap analysis "
            "compares against the guidebook."
        ),
    )
    service: RequiredStr = Field(
        alias="الخدمة",
        description=(
            "The service the complaint concerns. Required here — unlike the "
            "inquiries module — because it is the primary signal the complaint "
            "classification runs on, and stage 1 refuses a run without it."
        ),
    )

    # ── Optional: case attributes ─────────────────────────────────────────────
    main_service: OptionalStr = Field(
        default=None,
        alias="الخدمة_الرئيسية",
        description=(
            "The parent service, where a tenant records a two-level service tree. "
            "Secondary to ``service``, which is the one the classification reads."
        ),
    )
    severity: OptionalStr = Field(
        default=None,
        alias="شدة_الطلب",
        description=(
            "The severity the source system assigned — routine, complex, urgent. "
            "Reported as recorded and used for the severity breakdown; the pipeline "
            "does not re-derive it from the text."
        ),
    )
    contact_type: OptionalStr = Field(
        default=None,
        alias="نوع_المكالمة",
        description=(
            "The contact type as originally recorded. Where present it is what the "
            "reclassification rate is measured against."
        ),
    )
    status: OptionalStr = Field(
        default=None,
        alias="الحالة",
        description=(
            "The case status as the source system recorded it — open, closed, under "
            "review. Feeds the closure-rate reporting alongside the closure date."
        ),
    )
    service_channel: OptionalStr = Field(
        default=None,
        alias="قناة_تقديم_الخدمة",
        description=(
            "How the complaint was submitted — phone, self-service, live chat, "
            "email, in person. Drives the channel mix and the digital-submission "
            "analysis. An open vocabulary: a tenant's own channel names are kept."
        ),
    )
    date_opened: OptionalStr = Field(
        default=None,
        alias="تاريخ_الإنشاء",
        description=(
            "When the complaint was opened. Any format pandas can read; ISO 8601 is "
            "safest. The reporting period is derived from these."
        ),
    )
    date_closed: OptionalStr = Field(
        default=None,
        alias="تاريخ_الإغلاق",
        description=(
            "When the complaint was closed. Null or empty means still open, which is "
            "a fact the report states rather than an omission — the closure rate is "
            "computed from exactly this."
        ),
    )
    closed_within_sla: OptionalFlag = Field(
        default=None,
        alias="إغلاق_الطلب_خلال_الوقت_المحدد",
        description=(
            "Whether the complaint closed within its target time. Accepts "
            "'نعم'/'لا', 'yes'/'no' and booleans. Null when unrecorded or "
            "unrecognised — never guessed."
        ),
    )
    resolved_by: OptionalStr = Field(
        default=None,
        alias="تم_الحل_بواسطة",
        description="Who resolved the complaint. Feeds the per-handler workload view.",
    )
    general_administration: OptionalStr = Field(
        default=None,
        alias="الإدارة_العامة",
        description=(
            "The department that owns the complaint. Drives the workload map's "
            "per-department view; without it that view is omitted rather than guessed."
        ),
    )
    created_by: OptionalStr = Field(
        default=None,
        alias="انشاء_بواسطة",
        description="Who entered the complaint into the source system.",
    )
    owner: OptionalStr = Field(
        default=None,
        alias="المالك",
        description="The complaint's current owner in the source system.",
    )
    emirate: OptionalStr = Field(
        default=None,
        alias="الإمارة",
        description="The emirate the complaint relates to, where recorded.",
    )

    # ── Optional: personal data ───────────────────────────────────────────────
    # Everything below identifies a real person and is written into the stored
    # workbook. Send only what the report needs.
    applicant_name: OptionalStr = Field(
        default=None,
        alias="اسم_مقدم_الطلب",
        description=(
            "Name of the person who complained. **Personal data** — omit unless the "
            "report needs it, since it is written into the stored workbook."
        ),
    )
    nationality: OptionalStr = Field(
        default=None,
        alias="الجنسية",
        description=(
            "Nationality of the complainant. **Personal data.** An open vocabulary; "
            "a tenant's own spellings are kept."
        ),
    )
    national_id: OptionalStr = Field(
        default=None,
        alias="رقم_الهوية",
        description=(
            "The complainant's identity-document number. **Personal data** — omit "
            "unless the report needs it."
        ),
    )
    mobile: OptionalStr = Field(
        default=None,
        alias="الهاتف_الجوال",
        description=(
            "The complainant's mobile number. **Personal data** — omit unless the "
            "report needs it."
        ),
    )
    employee_number: OptionalStr = Field(
        default=None,
        alias="الرقم_الوظيفي",
        description=(
            "Staff number, where the complaint concerns an employee. **Personal "
            "data** — omit unless the report needs it."
        ),
    )

    def to_columns(self) -> dict[str, Any]:
        """The record as the Arabic-keyed mapping stage 1 expects.

        Only fields the caller actually supplied appear. That matters: stage 1 counts
        the columns it receives and the methodology section prints that count, so
        padding the frame with every modelled column would have the report describe
        an export the tenant never sent.
        """
        aliases = {
            name: field.alias or name
            for name, field in type(self).model_fields.items()
        }
        supplied = self.model_dump(exclude_none=True)
        row = {aliases.get(name, name): value for name, value in supplied.items()}

        # Unmodelled columns come through __pydantic_extra__ under whatever key the
        # caller used, which is the key the tenant records them under.
        for key, value in (self.__pydantic_extra__ or {}).items():
            if not is_blank(value):
                row[key] = value
        return row


def records_to_frame(records: list[ComplaintRecord]) -> "Any":
    """Build the dataframe stage 1 reads from a list of records.

    Imported lazily because ``api.models`` must be importable without pandas — the
    contract is useful to a caller building a request who will never run the
    pipeline, and the porting guide's rule is that importing the models pulls in
    nothing but pydantic.

    The column set is the union of what the records actually carry, in first-seen
    order, so the frame mirrors the caller's export rather than this model's full
    field list. Note that the legacy path applied ``header=4`` when reading the
    tenant's workbook; that is the caller's problem now, and ``scripts/
    make_fixtures.py`` does it.
    """
    import pandas as pd

    rows = [record.to_columns() for record in records]

    ordered: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                ordered.append(key)

    return pd.DataFrame(rows, columns=ordered)
