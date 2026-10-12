"""
Tenant settings — the Domain Definition Sheet's context fields X1–X12.

The Domain Admin fills these in the Builder's data home; the platform sends them on
every run. Three are **required** by the definition — the timeliness target (X2), the
timeliness framework (X3) and the case-type scope (X4) — and a request without them
is refused with ``missing_required_columns``, naming each one, exactly as a missing
required column is. The schema marks them optional only so that one check can name
every missing field in one answer rather than pydantic reporting them one by one.

Everything else carries the default the Prerequisites §2.3 states, so a request that
says nothing about, say, the digital-channel set gets the documented default and the
report says which basis it used.
"""
from __future__ import annotations

import re
from datetime import date, time
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

__all__ = [
    "CaseTypeScope",
    "ComparisonBasis",
    "DigitalChannelDefinition",
    "FrameworkId",
    "FrameworkSelection",
    "RecordedType",
    "TenantSettings",
    "TimelinessFramework",
    "WorkingCalendar",
    "REQUIRED_SETTINGS",
    "DEFAULT_DEFLECTABLE_BUNDLES",
]


class TimelinessFramework(StrEnum):
    """X3 — which framework the timeliness figures are reported against."""

    ENTITY_PROCESS_KPI = "entity_process_kpi"
    TAMM = "tamm"
    GSR = "gsr"
    OTHER = "other"


class CaseTypeScope(StrEnum):
    """X4 — which recorded case types the report analyses."""

    INQUIRIES_AND_SERVICE_REQUESTS = "inquiries_and_service_requests"
    INQUIRIES_ONLY = "inquiries_only"
    ALL_RECORDED_TYPES = "all_recorded_types"


class DigitalChannelDefinition(StrEnum):
    """X7 — what counts as a digital channel."""

    ALL_NON_PHONE = "all_non_phone"
    LIVE_CHAT_AND_SELF_SERVICE = "live_chat_and_self_service"


class ComparisonBasis(StrEnum):
    """X12 — what a run is compared with."""

    PREVIOUS_PERIOD = "previous_period"
    SAME_PERIOD_LAST_YEAR = "same_period_last_year"


class RecordedType(StrEnum):
    """The canonical form of a CRM's recorded case type (U4)."""

    INQUIRY = "inquiry"
    SERVICE_REQUEST = "service_request"
    COMPLAINT = "complaint"
    INCIDENT = "incident"
    SUGGESTION = "suggestion"
    COMPLIMENT = "compliment"


class FrameworkId(StrEnum):
    """The framework registry (Prerequisites §1.D)."""

    ENTITY_PROCESS_KPI = "entity_process_kpi"
    TAMM_CONTACT_CENTRE = "tamm_contact_centre"
    AD_GOV_CUSTOMER_SERVICE_GUIDE = "ad_gov_customer_service_guide"
    GSR = "gsr"


class FrameworkSelection(BaseModel):
    """One framework the Client Admin selected, with the targets they set.

    Targets are tenant values — the brief fixes none. Omitted targets take the
    registry default the entity's process document states (acceptance 120 minutes,
    classification 16 working hours, timeliness = X2 working days).
    """

    id: FrameworkId
    targets: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Per-indicator targets. Keys: acceptance_minutes, "
            "classification_working_hours, resolution_working_days, "
            "timeliness_working_days, pending_working_days."
        ),
    )


# Prerequisites §2.3: Procedures · Eligibility · Values · Payment dates · Locations.
# Umbrellas are AI-generated per tenant, so this default only bites when a tenant's
# umbrellas carry these names — ADPF's do. A tenant overrides it by name.
DEFAULT_DEFLECTABLE_BUNDLES: tuple[str, ...] = (
    "طلب إجراءات ومتطلبات الخدمة",
    "شروط الاستحقاق والأهلية",
    "قيم ومبالغ وآلية الاحتساب",
    "مواعيد الصرف والمستحقات المالية",
    "مواقع وقنوات التواصل",
)

_DAYS = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
}
_CALENDAR_RE = re.compile(
    r"^\s*(?P<d1>[A-Za-z]{3})[a-z]*\s*[-–—]\s*(?P<d2>[A-Za-z]{3})[a-z]*\s+"
    r"(?P<h1>\d{1,2}):(?P<m1>\d{2})\s*[-–—]\s*(?P<h2>\d{1,2}):(?P<m2>\d{2})\s*$"
)


class WorkingCalendar(BaseModel):
    """X11, parsed: which weekdays are worked and between which hours."""

    weekdays: list[int] = Field(description="Python weekday numbers, Monday = 0.")
    start: time
    end: time

    @classmethod
    def parse(cls, text: str) -> "WorkingCalendar":
        match = _CALENDAR_RE.match(text or "")
        if not match:
            raise ValueError(
                "working_calendar must read like 'Sun–Thu 07:30–15:30'."
            )
        first = _DAYS[match["d1"].lower()]
        last = _DAYS[match["d2"].lower()]
        days, day = [], first
        while True:
            days.append(day)
            if day == last:
                break
            day = (day + 1) % 7
        start = time(int(match["h1"]), int(match["m1"]))
        end = time(int(match["h2"]), int(match["m2"]))
        if end <= start:
            raise ValueError("working_calendar must end after it starts.")
        return cls(weekdays=days, start=start, end=end)


class TenantSettings(BaseModel):
    """The Domain Definition Sheet's context fields, X1–X12."""

    source_system: str | None = Field(
        default=None,
        description="X1 · Source system / نظام المصدر, e.g. 'TAMM CRM'. Printed in the "
        "introduction and the methodology sources table.",
    )
    timeliness_target_working_days: float | None = Field(
        default=None,
        gt=0,
        description="X2 · **Required.** Timeliness target in working days "
        "(ADPF: 2). Used for the SLA labels and timestamp-based timeliness.",
    )
    timeliness_framework: TimelinessFramework | None = Field(
        default=None,
        description="X3 · **Required.** The framework timeliness is reported against.",
    )
    case_type_scope: CaseTypeScope | None = Field(
        default=None,
        description="X4 · **Required.** Which recorded case types are analysed. "
        "Excluded types are counted and reported in the scope note.",
    )
    llm_threshold: float = Field(
        default=0.75, ge=0, le=1,
        description="X5 · Rule-chain confidence below this goes to the model.",
    )
    review_threshold: float = Field(
        default=0.65, ge=0, le=1,
        description="X6 · Confidence below this goes to the deep review — a second, "
        "higher-effort AI pass («يدوي - مُراجع»), not a person. A tenant may set X5 = X6 "
        "(ADPF ran a single 0.90 gate).",
    )
    digital_channel_definition: DigitalChannelDefinition = Field(
        default=DigitalChannelDefinition.ALL_NON_PHONE,
        description="X7 · Default: every channel except phone and walk-in.",
    )
    digital_channels: list[str] | None = Field(
        default=None,
        description="An explicit digital-channel list that overrides X7, matched on "
        "the channel values as recorded.",
    )
    root_cause_extraction: bool = Field(
        default=False,
        description="X8 · On: a root cause per case (root-cause codebook R1–R7), "
        "umbrella discovery, and the optional sections S10–S11.",
    )
    umbrella_count_range: str = Field(
        default="6–10",
        description="X8a · Target umbrella count for the discovery step.",
    )
    agent_level_reporting: bool = Field(
        default=False,
        description="X9 · Non-punitive per-owner figures. Queues excluded; never ranked.",
    )
    focus_services_count: int = Field(
        default=2, ge=1, le=5, description="X10 · Focus services in S11."
    )
    working_calendar: str = Field(
        default="Sun–Thu 07:30–15:30",
        description="X11 · Used only for timestamp-based timeliness.",
    )
    public_holidays: list[date] = Field(
        default_factory=list, description="Non-working dates for working-time maths."
    )
    comparison_basis: ComparisonBasis = Field(
        default=ComparisonBasis.PREVIOUS_PERIOD,
        description="X12 · Which stored run the comparison reads from ``history``.",
    )
    frameworks: list[FrameworkSelection] = Field(
        default_factory=list,
        description="The framework registry selections (Prerequisites §1.D). Empty "
        "means the X3 framework alone, at its registry defaults.",
    )
    deflectable_bundles: list[str] | None = Field(
        default=None,
        description="Umbrellas the tenant marks self-service-able (DEFLECTABLE_PCT). "
        "Default: procedures, eligibility, values, payment dates, locations.",
    )
    event_threshold_pct: float = Field(
        default=50.0, gt=0,
        description="EVENTS: a cluster's month-over-month rise that counts as an event.",
    )
    event_min_cases: int = Field(
        default=30, ge=1, description="EVENTS: the smallest month count that can be one."
    )
    top_root_causes: int = Field(default=12, ge=1, le=50)
    root_causes_per_bundle: int = Field(default=5, ge=1, le=20)
    queue_owner_pattern: str = Field(
        default="SM-ND|queue|قائمة|فريق",
        description="Regex. An owner matching it is a queue, not a person.",
    )
    case_type_map: dict[str, RecordedType] | None = Field(
        default=None,
        description="Recorded case-type value → canonical type, for values the "
        "built-in recogniser does not know.",
    )

    @field_validator("umbrella_count_range")
    @classmethod
    def _range(cls, value: str) -> str:
        cls.parse_range(value)
        return value

    @field_validator("working_calendar")
    @classmethod
    def _calendar(cls, value: str) -> str:
        WorkingCalendar.parse(value)
        return value

    @field_validator("queue_owner_pattern")
    @classmethod
    def _pattern(cls, value: str) -> str:
        re.compile(value)
        return value

    @model_validator(mode="after")
    def _thresholds(self) -> "TenantSettings":
        if self.review_threshold > self.llm_threshold:
            raise ValueError(
                "review_threshold (X6) cannot exceed llm_threshold (X5): a case below "
                "X6 is by definition below X5."
            )
        return self

    @staticmethod
    def parse_range(value: str) -> tuple[int, int]:
        numbers = [int(n) for n in re.findall(r"\d+", value or "")]
        if len(numbers) != 2 or numbers[0] < 1 or numbers[0] > numbers[1]:
            raise ValueError("umbrella_count_range must read like '6–10'.")
        return numbers[0], numbers[1]

    def umbrella_range(self) -> tuple[int, int]:
        return self.parse_range(self.umbrella_count_range)

    def calendar(self) -> WorkingCalendar:
        return WorkingCalendar.parse(self.working_calendar)

    def selected_frameworks(self) -> list[FrameworkSelection]:
        """The registry selections, defaulting to the X3 framework."""
        if self.frameworks:
            return list(self.frameworks)
        mapping = {
            TimelinessFramework.ENTITY_PROCESS_KPI: FrameworkId.ENTITY_PROCESS_KPI,
            TimelinessFramework.TAMM: FrameworkId.TAMM_CONTACT_CENTRE,
            TimelinessFramework.GSR: FrameworkId.GSR,
        }
        chosen = mapping.get(self.timeliness_framework or TimelinessFramework.OTHER)
        return [FrameworkSelection(id=chosen)] if chosen else []

    def deflectable(self) -> list[str]:
        if self.deflectable_bundles is not None:
            return list(self.deflectable_bundles)
        return list(DEFAULT_DEFLECTABLE_BUNDLES)


# The required context fields, by field name → (X-id, label).
REQUIRED_SETTINGS: dict[str, tuple[str, str]] = {
    "timeliness_target_working_days": ("X2", "Timeliness target (working days) / مستهدف زمن الاستجابة"),
    "timeliness_framework": ("X3", "Timeliness framework / إطار الالتزام الزمني"),
    "case_type_scope": ("X4", "Case-type scope / نطاق أنواع الحالات"),
}
