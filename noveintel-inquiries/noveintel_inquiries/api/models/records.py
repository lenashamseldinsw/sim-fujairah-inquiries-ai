"""
One customer-contact case, as the caller sends it.

File parsing stays with the caller (porting guide §2): the Streamlit app read an
Excel export, and this service takes the rows already structured. ``scripts/
make_fixtures.py`` turns a real export into a ready-to-POST body, and that script —
not the service — is where the spreadsheet knowledge now lives.

**Two names for every field.** The JSON name is snake_case, per the cross-module
convention, and the alias is the normalised Arabic column the pipeline's stage 1
expects. Either is accepted. A caller building a payload by hand uses the snake_case
form; a caller that has already normalised a dataframe can post the Arabic keys
unchanged and nothing has to be renamed on the way in.

**Four fields are required**, because stage 1 rejects a run without them and every
later stage reads them: the case number, the request details, the contact type and
the resolution. The rest are optional in the strict sense — a missing closure date
means the case is open, a missing department means the workload map has one fewer
dimension, and neither is a reason to refuse the run. What the report can say
narrows with what it is given, and it says so rather than inventing.

**Required means the column, not the value.** A record must carry every required
key, but a blank cell may be sent as ``null`` — every required field except
``case_number`` accepts it. Stage 1 keeps such rows and routes them down its
fallback path; refusing them would refuse an export the pipeline analyses, and
the first real export tried had 2 blank resolutions in 11 rows.

Unknown keys are kept (``extra="allow"``) and passed through to the dataframe. A
tenant that records a column this contract has never heard of gets it counted in the
"structured fields" figure the methodology section prints, which is the honest
behaviour: the alternative is a report that describes an export narrower than the
one it was given.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ._coercion import (
    OptionalFlag,
    OptionalStr,
    RequiredNullableStr,
    RequiredStr,
    is_blank,
)

__all__ = [
    "HARD_REQUIRED_COLUMNS",
    "InquiryRecord",
    "records_to_frame",
]

# An empty cell, as pandas reads one from Excel.
_NAN = float("nan")

# The columns stage 1 refuses a run without, named by their JSON field. Used by the
# error handler to fold a hundred thousand identical per-record failures into one.
HARD_REQUIRED_COLUMNS: frozenset[str] = frozenset(
    {"case_number", "case_details", "contact_type", "resolution"}
)


class InquiryRecord(BaseModel):
    """A single customer-contact case from the period being analysed."""

    model_config = ConfigDict(
        populate_by_name=True,
        # Accept a column this contract does not model rather than reject the row.
        # See the module docstring: an unmodelled column is a tenant recording
        # something extra, not a malformed export.
        extra="allow",
    )

    # ── Required ──────────────────────────────────────────────────────────────
    case_number: RequiredStr = Field(
        alias="رقم_الطلب",
        description=(
            "The case reference, unique within the export. Carried through to the "
            "workbook so a figure in the report can be traced back to the rows "
            "behind it. A string, not a number: leading zeros are meaningful and a "
            "numeric type loses them."
        ),
    )
    case_details: RequiredNullableStr = Field(
        alias="تفاصيل_الطلب",
        description=(
            "What the customer asked for, in their own words. One of the two "
            "free-text fields the classification reads, and the main signal for the "
            "friction and FAQ analysis. Sending a placeholder here does not fail the "
            "run, but it produces a report about placeholders."
        ),
    )
    contact_type: RequiredNullableStr = Field(
        alias="نوع_المكالمة",
        description=(
            "The contact type as originally recorded — inquiry, complaint, request "
            "or thanks. This is the value the run is measured *against*: stages 2 and "
            "3 classify each case independently, and the report's reclassification "
            "rate is how often the two disagree."
        ),
    )
    resolution: RequiredNullableStr = Field(
        alias="الحل",
        description=(
            "How the case was answered or closed, in free text. The second free-text "
            "field the classification reads, and what the gap analysis compares "
            "against the guidebook to decide whether an answer was already documented."
        ),
    )

    # ── Optional ──────────────────────────────────────────────────────────────
    date_opened: OptionalStr = Field(
        default=None,
        alias="تاريخ_الإنشاء",
        description=(
            "When the case was opened. Any format pandas can read; ISO 8601 is "
            "safest. The reporting period is derived from these, so omitting them "
            "across the board leaves the report without a period label."
        ),
    )
    date_closed: OptionalStr = Field(
        default=None,
        alias="تاريخ_إغلاق_الطلب",
        description=(
            "When the case was closed. Null or empty means still open, which is a "
            "fact the report states rather than an omission — the closure rate is "
            "computed from exactly this."
        ),
    )
    service_channel: OptionalStr = Field(
        default=None,
        alias="قناة_تقديم_الخدمة",
        description=(
            "How the customer made contact — phone, self-service, live chat, email, "
            "in person. Drives the channel mix and the digital-transformation "
            "analysis. An open vocabulary: a tenant's own channel names are kept."
        ),
    )
    sla_status: OptionalStr = Field(
        default=None,
        alias="الحالة_SLA",
        description=(
            "The case's SLA status as the source system recorded it. Reported as "
            "given; the pipeline does not recompute it from the dates."
        ),
    )
    sla_compliance: OptionalFlag = Field(
        default=None,
        alias="سلا_امتثال",
        description=(
            "Whether the case closed within its target time. Accepts 'نعم'/'لا', "
            "'yes'/'no' and booleans. Null when unrecorded or unrecognised — never "
            "guessed, because guessing moves a case into the compliant column."
        ),
    )
    sub_classification: OptionalStr = Field(
        default=None,
        alias="التصنيف_الفرعي",
        description=(
            "The detailed category the source system assigned, beneath the contact "
            "type. Used to group cases for the FAQ and friction analysis. Absent is "
            "fine — the pipeline derives its own grouping."
        ),
    )
    main_service: OptionalStr = Field(
        default=None,
        alias="الخدمة_الرئيسية",
        description=(
            "The service the case concerns. Drives the per-service breakdown and the "
            "service-level FAQ extraction."
        ),
    )
    service: OptionalStr = Field(
        default=None,
        alias="الخدمة",
        description=(
            "A secondary service field some exports carry alongside the main one. "
            "Kept because tenants differ in which of the two they populate."
        ),
    )
    general_administration: OptionalStr = Field(
        default=None,
        alias="الإدارة_العامة",
        description=(
            "The department that owns the case. Drives the workload map's "
            "per-department view; without it that view is omitted rather than guessed."
        ),
    )

    def to_columns(self) -> dict[str, Any]:
        """The record as the Arabic-keyed mapping stage 1 expects.

        Exactly the fields the caller sent appear — including ones sent as ``null``,
        and nothing it did not send. Both halves matter. Stage 1 counts the columns it
        receives and the methodology section prints that count, so padding the frame
        with every modelled column would describe an export the tenant never sent;
        and a column the tenant *did* send, blank in this row, is still a column of
        their export.

        A blank value becomes ``NaN``, which is what pandas produces for an empty
        Excel cell and therefore what the stages were written against. ``None`` would
        stringify as "None" where the stages expect "nan".
        """
        aliases = {
            name: field.alias or name
            for name, field in type(self).model_fields.items()
        }
        supplied = self.model_dump(exclude_unset=True)
        row = {
            aliases.get(name, name): (_NAN if value is None else value)
            for name, value in supplied.items()
        }

        # Unmodelled columns come through __pydantic_extra__ under whatever key the
        # caller used, which is the key the tenant records them under.
        for key, value in (self.__pydantic_extra__ or {}).items():
            row[key] = _NAN if is_blank(value) else value
        return row


def records_to_frame(records: list[InquiryRecord]) -> "Any":
    """Build the dataframe stage 1 reads from a list of records.

    Imported lazily because ``api.models`` must be importable without pandas — the
    contract is useful to a caller building a request who will never run the
    pipeline, and the porting guide's rule is that importing the models pulls in
    nothing but pydantic.

    The column set is the union of what the records actually carry, in first-seen
    order, so the frame mirrors the caller's export rather than this model's full
    field list. Records that omit a column another record has get a null there, which
    is what a ragged export looks like anyway.
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
