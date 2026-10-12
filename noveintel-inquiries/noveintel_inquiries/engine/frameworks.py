"""
The framework registry (Prerequisites §1.D) — standards and SLAs, tenant-selected.

No single standard governs inquiries. The platform ships the definitions; the Client
Admin selects which apply and sets each target. For every indicator the registry says
what it needs from the export, and the run evidences only what the data supports: an
indicator the export cannot compute is reported as a **recommendation to enable the
field** — the Domain 01 "metric gap" pattern — and never as zero.

Timeliness rule: when ``sla_status`` is present it is the source of truth (the CRM
applied the tenant's own targets). When accept / classify / resolve timestamps are
present, each indicator is computed in working time on the tenant calendar (X11).
When neither is present the indicator is not computable.

Sources: the entity process document «عملية الرد على طلبات خدمة الاستفسارات
والاقتراحات والثناء من المتعاملين» (process KPI, 2 working days, and the six TAMM
contact-centre indicators with their FCR exclusions), the Abu Dhabi Government
Customer Service Guide, and the GSR manual.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable

from ..api.models.settings import FrameworkId, TenantSettings, WorkingCalendar
from .parse import Case
from .text import fold_text

__all__ = ["evaluate_frameworks", "working_seconds", "FRAMEWORK_NAMES"]

FRAMEWORK_NAMES: dict[str, dict[str, str]] = {
    FrameworkId.ENTITY_PROCESS_KPI: {
        "ar": "مؤشر العملية للجهة — الرد على الاستفسارات وطلبات الخدمة",
        "en": "Entity process KPI — responding to inquiries and service requests",
    },
    FrameworkId.TAMM_CONTACT_CENTRE: {
        "ar": "مؤشرات مركز اتصال حكومة أبوظبي «تم»",
        "en": "Abu Dhabi Government Contact Centre (TAMM) indicators",
    },
    FrameworkId.AD_GOV_CUSTOMER_SERVICE_GUIDE: {
        "ar": "دليل خدمة المتعاملين لحكومة أبوظبي",
        "en": "Abu Dhabi Government Customer Service Guide",
    },
    FrameworkId.GSR: {
        "ar": "النظام العالمي لتصنيف الخدمات (نجوم)",
        "en": "UAE Global Star Rating (GSR)",
    },
}

_FIELD_NAMES = {
    "sla_status": ("حالة الالتزام بمستوى الخدمة", "SLA status"),
    "accepted_datetime": ("تاريخ ووقت قبول الحالة", "accepted date-time"),
    "classified_datetime": ("تاريخ ووقت تصنيف الحالة", "classified date-time"),
    "resolved_datetime": ("تاريخ ووقت حل الحالة", "resolved date-time"),
    "closed_datetime": ("تاريخ إغلاق الطلب", "closed date-time"),
    "customer_verdict": ("رأي المتعامل في الحل", "customer verdict"),
    "reopen_flag": ("مؤشر إعادة فتح الحالة", "reopen flag"),
    "fcr_flag": ("مؤشر الحل من أول اتصال", "first-contact-resolution flag"),
    "closure_reason": ("سبب الإغلاق", "closure reason"),
    "escalation_datetime": ("موعد التصعيد", "escalation date-time"),
    "open_cases": ("الحالات المفتوحة في التصدير", "open cases in the export"),
}

# FCR exclusions (process document): raised by the entity or the contact centre,
# auto-closed for no customer response, closed on the customer's request, closed as
# "information available".
_FCR_EXCLUSIONS = (
    "عدم الاستجابه", "عدم استجابه", "بناء علي طلب المتعامل", "بناء على طلب المتعامل",
    "auto", "no response", "customer request", "اغلاق تلقائي", "مرفوعه من الجهه",
    "raised by", "information available", "المعلومات متاحه",
)


def working_seconds(start: datetime, end: datetime, calendar: WorkingCalendar,
                    holidays: set[date]) -> float:
    """Working time between two instants on the tenant calendar, in seconds."""
    if end <= start:
        return 0.0
    total = 0.0
    day = start.date()
    while day <= end.date():
        if day.weekday() in calendar.weekdays and day not in holidays:
            window_start = datetime.combine(day, calendar.start)
            window_end = datetime.combine(day, calendar.end)
            lo, hi = max(start, window_start), min(end, window_end)
            if hi > lo:
                total += (hi - lo).total_seconds()
        day += timedelta(days=1)
    return total


@dataclass
class Indicator:
    framework: str
    key: str
    name_ar: str
    name_en: str
    definition_ar: str
    definition_en: str
    status: str = "not_computable"   # computed | partial | not_computable | reference
    value_pct: float | None = None
    numerator: int | None = None
    denominator: int | None = None
    target_ar: str = ""
    target_en: str = ""
    basis: str = ""
    needs: list[str] = field(default_factory=list)
    recommendation_ar: str = ""
    recommendation_en: str = ""

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _pct(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator * 100, 1) if denominator else None


def _recommend(ind: Indicator, missing: list[str]) -> None:
    ind.needs = missing
    names_ar = "، ".join(_FIELD_NAMES[m][0] for m in missing)
    names_en = ", ".join(_FIELD_NAMES[m][1] for m in missing)
    ind.recommendation_ar = (
        f"تفعيل حقل {names_ar} في تصدير نظام إدارة علاقات المتعاملين لاحتساب {ind.name_ar}."
    )
    ind.recommendation_en = (
        f"Enable the {names_en} field in the CRM export to compute {ind.name_en}."
    )


def _is_resolved(case: Case) -> bool:
    if case.closed or case.resolved_at:
        return True
    status = fold_text(case.status)
    return any(t in status for t in ("closed", "مغلق", "resolved", "تم الحل", "منجز"))


def evaluate_frameworks(cases: list[Case], settings: TenantSettings,
                        supplied: set[str]) -> list[dict[str, Any]]:
    """Every selected framework's indicators, computed or recommended."""
    calendar = settings.calendar()
    holidays = set(settings.public_holidays)
    target_days = settings.timeliness_target_working_days or 2
    day_seconds = (
        datetime.combine(date.today(), calendar.end) - datetime.combine(date.today(), calendar.start)
    ).total_seconds()
    has_sla = "sla_status" in supplied and any(c.sla != "unspecified" for c in cases)
    out: list[Indicator] = []

    def elapsed_ok(case: Case, end_attr: str, limit_seconds: float) -> bool | None:
        end = getattr(case, end_attr)
        if not case.opened or not end:
            return None
        return working_seconds(case.opened, end, calendar, holidays) <= limit_seconds

    def timestamp_indicator(ind: Indicator, end_attr: str, field_name: str,
                            limit_seconds: float, population: Callable[[Case], bool]) -> None:
        verdicts = [elapsed_ok(c, end_attr, limit_seconds) for c in cases if population(c)]
        measured = [v for v in verdicts if v is not None]
        if field_name in supplied and measured:
            ind.status = "computed"
            ind.numerator, ind.denominator = sum(measured), len(measured)
            ind.value_pct = _pct(ind.numerator, ind.denominator)
            ind.basis = "timestamps"
        else:
            _recommend(ind, [field_name])

    for selection in settings.selected_frameworks():
        targets = selection.targets
        fid = selection.id
        if fid is FrameworkId.ENTITY_PROCESS_KPI:
            days = targets.get("timeliness_working_days", target_days)
            ind = Indicator(
                fid.value, "timeliness",
                "نسبة الالتزام بزمن الاستجابة", "Response-time compliance",
                "الردود المنجزة ضمن المستهدف ÷ إجمالي الحالات الواردة × 100، تُقاس شهرياً.",
                "Responses completed within the target ÷ total received × 100, measured monthly.",
                target_ar=f"{_fmt(days)} يوم عمل", target_en=f"{_fmt(days)} working days",
            )
            if has_sla:
                within = sum(1 for c in cases if c.sla in ("within", "near"))
                ind.status, ind.basis = "computed", "sla_status"
                ind.numerator, ind.denominator = within, len(cases)
                ind.value_pct = _pct(within, len(cases))
            else:
                attr, column = (
                    ("resolved_at", "resolved_datetime") if "resolved_datetime" in supplied
                    else ("closed", "closed_datetime")
                )
                timestamp_indicator(ind, attr, column, days * day_seconds, lambda c: True)
                if ind.status != "computed":
                    _recommend(ind, ["sla_status", "resolved_datetime"])
            out.append(ind)
        elif fid is FrameworkId.TAMM_CONTACT_CENTRE:
            acc = Indicator(
                fid.value, "acceptance", "مؤشر القبول", "Acceptance",
                "الحالات المقبولة أو المرفوضة ضمن الإطار الزمني المتفق عليه (120 دقيقة من الإسناد) ÷ الحالات المسندة.",
                "Cases accepted or rejected within the agreed window (120 minutes from assignment) ÷ cases assigned.",
            )
            minutes = targets.get("acceptance_minutes", 120)
            acc.target_ar, acc.target_en = f"{_fmt(minutes)} دقيقة", f"{_fmt(minutes)} minutes"
            timestamp_indicator(acc, "accepted", "accepted_datetime", minutes * 60, lambda c: True)
            out.append(acc)

            cls_ = Indicator(
                fid.value, "classification", "مؤشر التصنيف", "Classification",
                "الحالات المصنفة ضمن 16 ساعة عمل ÷ الحالات المصنفة.",
                "Cases classified within 16 working hours ÷ cases classified.",
            )
            hours = targets.get("classification_working_hours", 16)
            cls_.target_ar, cls_.target_en = f"{_fmt(hours)} ساعة عمل", f"{_fmt(hours)} working hours"
            timestamp_indicator(cls_, "classified_at", "classified_datetime", hours * 3600, lambda c: True)
            out.append(cls_)

            res = Indicator(
                fid.value, "resolution", "مؤشر الحل", "Resolution",
                "الحالات المحلولة ضمن مستوى الخدمة المتفق عليه ÷ الحالات المحلولة.",
                "Cases resolved within the agreed SLA ÷ cases resolved.",
                target_ar="مستوى الخدمة المتفق عليه", target_en="the agreed SLA",
            )
            resolved = [c for c in cases if _is_resolved(c) and c.sla != "unspecified"]
            if has_sla and resolved:
                res.status, res.basis = "computed", "sla_status"
                res.numerator = sum(1 for c in resolved if c.sla in ("within", "near"))
                res.denominator = len(resolved)
                res.value_pct = _pct(res.numerator, res.denominator)
            else:
                days = targets.get("resolution_working_days", target_days)
                timestamp_indicator(res, "resolved_at", "resolved_datetime", days * day_seconds, _is_resolved)
                if res.status != "computed":
                    _recommend(res, ["sla_status", "resolved_datetime"])
            out.append(res)

            accu = Indicator(
                fid.value, "accuracy", "مؤشر الدقة", "Accuracy",
                "الحالات التي قبل المتعامل حلها ÷ الحالات المحلولة (إغلاق من الإسناد الأول ودون حالات عدم رضا).",
                "Resolutions accepted by the customer ÷ cases resolved (closed from first assignment, zero dissatisfaction).",
            )
            resolved_all = [c for c in cases if _is_resolved(c)]
            judged = [c for c in resolved_all if c.customer_verdict or c.reopen is not None]
            if judged and ("customer_verdict" in supplied or "reopen_flag" in supplied):
                ok = 0
                for c in judged:
                    verdict = fold_text(c.customer_verdict)
                    dissatisfied = any(t in verdict for t in ("dissatisf", "غير راض", "رفض", "reject"))
                    if not dissatisfied and not c.reopen:
                        ok += 1
                accu.status, accu.basis = "computed", "customer_verdict / reopen_flag"
                accu.numerator, accu.denominator = ok, len(judged)
                accu.value_pct = _pct(ok, len(judged))
            else:
                _recommend(accu, ["customer_verdict", "reopen_flag"])
            out.append(accu)

            pend = Indicator(
                fid.value, "pending", "مؤشر الحالات العالقة", "Pending cases",
                "الحالات العالقة خارج الإطار الزمني ÷ إجمالي الحالات النشطة.",
                "Open cases past their window ÷ active cases.",
            )
            open_cases = [c for c in cases if not _is_resolved(c)]
            export_time = max(
                (d for c in cases for d in (c.updated, c.opened) if d), default=None
            )
            if open_cases and "escalation_datetime" in supplied and export_time:
                windowed = [c for c in open_cases if c.escalation]
                past = sum(1 for c in windowed if c.escalation < export_time)
                pend.status = "partial" if len(windowed) < len(open_cases) else "computed"
                pend.basis = "status + escalation_datetime at export time"
                pend.numerator, pend.denominator = past, len(open_cases)
                pend.value_pct = _pct(past, len(open_cases))
            else:
                missing = [] if open_cases else ["open_cases"]
                if "escalation_datetime" not in supplied:
                    missing.append("escalation_datetime")
                _recommend(pend, missing or ["escalation_datetime"])
            out.append(pend)

            fcr = Indicator(
                fid.value, "fcr", "مؤشر الحل من أول اتصال", "First-contact resolution",
                "(حالات الحل من أول اتصال + الحل من الخط الأول) ÷ (حالات المعلومات المغلقة − الاستثناءات).",
                "(FCR + FLR) ÷ (closed information cases − exclusions).",
            )
            info_closed = [
                c for c in cases
                if _is_resolved(c) and c.recorded_type == "inquiry" and c.fcr is not None
                and not any(t in fold_text(c.closure_reason) for t in map(fold_text, _FCR_EXCLUSIONS))
            ]
            if "fcr_flag" in supplied and info_closed:
                fcr.status, fcr.basis = "computed", "fcr_flag + closure_reason"
                fcr.numerator = sum(1 for c in info_closed if c.fcr)
                fcr.denominator = len(info_closed)
                fcr.value_pct = _pct(fcr.numerator, fcr.denominator)
                if "closure_reason" not in supplied:
                    fcr.status = "partial"
            else:
                _recommend(fcr, ["fcr_flag", "closure_reason"])
            out.append(fcr)
        elif fid is FrameworkId.AD_GOV_CUSTOMER_SERVICE_GUIDE:
            out.append(Indicator(
                fid.value, "csg_compliance",
                "نسبة الالتزام بمعايير دليل خدمة المتعاملين", "Compliance with the Customer Service Guide",
                "مؤشر استراتيجي تُقاس عليه الجهة؛ لا يُحتسب من بيانات الحالات ويُستشهد به في الخلاصة.",
                "A strategic indicator the entity reports against; not measurable from case data — cited in the closing.",
                status="reference",
            ))
        elif fid is FrameworkId.GSR:
            out.append(Indicator(
                fid.value, "gsr_pillars",
                "محاور كفاءة الخدمة وتجربة المتعامل وقنوات تقديم الخدمة", "Service efficiency, customer experience and delivery-channel pillars",
                "تقييم نضج؛ تدعم أدلة الالتزام الزمني ومزيج القنوات والأسباب الجذرية هذه المحاور دون افتراض عتبات رقمية.",
                "Maturity-scored; the report's timeliness, channel-mix and root-cause evidence supports these pillars — no numeric thresholds asserted.",
                status="reference",
            ))
    return [i.as_dict() for i in out]


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)
