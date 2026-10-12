"""
The rule chain — classification tier 1 (provenance «قاعدة»).

The codebook's golden rule: read **two fields only**, the description (H) and the
resolution (I). The resolution outranks the description when they disagree — classify
by what was actually handled. The CRM's case title and service tag are never truth.

Contact type, by the codebook's two tests (Q4-2025 pilot rubric, Full Report Prompt):

* a **service request** only when the agent *executed an action* on the customer's
  account or the system — an explanation, a link or a referral is an **inquiry**;
* a **complaint** when the text expresses dissatisfaction, a failure report or an
  objection;
* a **compliment** when it expresses thanks with no complaint in it.

Main service and sub-classification come from the taxonomy's signals (codebook §4),
counted in H and I with the resolution weighted higher. A sub-classification hint
column (U16) naming a taxonomy entry settles both.

Each tier returns a confidence. The run sends anything below X5 to the model; the
thresholds live in the settings, never here (R11).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..engine.parse import Case
from ..engine.taxonomy import TaxonomyIndex
from ..engine.text import count_hits, fold_text

__all__ = ["RuleResult", "classify_by_rules"]

_F = lambda words: [fold_text(w) for w in words]  # noqa: E731

# Resolution phrases that report an action executed on the account or the system.
_ACTION = _F([
    "تم تعديل", "تم تحديث", "تم الغاء", "تم إلغاء", "تم اصدار", "تم إصدار", "تم تسجيل",
    "تم رفع الطلب", "تم رفع طلب", "تم تنفيذ", "تم صرف", "تم تفعيل", "تم اضافة", "تم إضافة",
    "تم ضم", "تم انجاز", "تم إنجاز", "تم اعتماد", "تم ارسال الشهادة", "تم إرسال الشهادة",
    "تم ايقاف", "تم إيقاف", "تم استرجاع", "تم تحويل المبلغ", "تمت المعالجة", "تم معالجة الطلب",
    "تم تصحيح", "تم ربط", "تم تجديد", "updated", "has been processed", "was issued",
    "has been cancelled", "has been registered",
])
# Resolution phrases that answer with information, a link or a referral.
_INFO = _F([
    "http", "www.", "يرجى", "يمكنكم", "يمكنك", "من خلال", "عبر الرابط", "نفيدكم", "نود افادتكم",
    "نود إفادتكم", "للاستفسار", "التواصل مع", "الدخول على", "يتم احتساب", "بامكانكم",
    "بإمكانكم", "الخطوات", "المتطلبات", "please", "you can", "via the link",
])
_COMPLAINT = _F([
    "شكوى", "اشتكي", "أشتكي", "استياء", "غير راض", "غير راضي", "سوء", "تأخر", "تاخر",
    "لم يتم الرد", "لا يوجد رد", "لم يتم حل", "اعتراض", "معترض", "تظلم", "مماطلة",
    "complaint", "dissatisfied", "not satisfied",
])
_THANKS = _F(["شكرا", "شكراً", "اشكر", "أشكر", "ثناء", "ممتاز", "تقدير", "thank you", "thanks"])


@dataclass
class RuleResult:
    contact_type: str | None
    true_type: str | None
    main_service: str | None
    sub_classification: str | None
    confidence: float
    reason: str
    type_confidence: float = 0.0


def _contact_type(desc: str, res: str) -> tuple[str, str, float, str]:
    """(contact type, true type, confidence, reason) from H and I."""
    action = count_hits(res, _ACTION)
    info = count_hits(res, _INFO)
    complaint = count_hits(desc, _COMPLAINT)
    thanks = count_hits(desc, _THANKS)

    if thanks and not complaint and len(desc) < 400:
        return "شكر وثناء", "compliment", 0.88, "الوصف يعبّر عن الشكر دون شكوى."
    if complaint >= 2 or (complaint and not info and not action):
        return "شكوى", "complaint", 0.78 if complaint >= 2 else 0.68, "الوصف يعبّر عن استياء أو إبلاغ عن إخفاق."
    if action and action >= info:
        return "طلب خدمة", "service_request", 0.86 if action >= 2 else 0.8, "رد المعالجة يذكر تنفيذ إجراء على الحساب أو النظام."
    if info:
        return "استفسار", "inquiry", 0.86 if info >= 2 else 0.8, "رد المعالجة يقدّم معلومة أو رابطاً أو توجيهاً دون تنفيذ إجراء."
    return "استفسار", "inquiry", 0.5, "لا يتضح من الرد تنفيذ إجراء؛ يُرجَّح أنه استفسار."


def _score(text_desc: str, text_res: str, signals: list[str]) -> float:
    return count_hits(text_res, signals) * 1.5 + count_hits(text_desc, signals)


def classify_by_rules(case: Case, tax: TaxonomyIndex) -> RuleResult:
    """Tier-1 labels and the confidence the rule chain has in them."""
    desc = fold_text(case.description)
    res = fold_text(case.resolution_text)
    contact, true_type, type_conf, type_reason = _contact_type(desc, res)

    # A hint column naming a taxonomy entry settles the service.
    hint = tax.sub(case.sub_hint) if case.sub_hint else None
    if hint and len(tax.mains_for_sub(hint)) == 1:
        return RuleResult(
            contact, true_type, tax.mains_for_sub(hint)[0], hint,
            min(type_conf, 0.9), f"{type_reason} التصنيف الفرعي مسجَّل في النظام ويطابق التصنيف المعتمد.",
            type_conf,
        )

    scores = sorted(
        ((_score(desc, res, signals), name) for name, signals in tax.main_signals.items() if signals),
        reverse=True,
    )
    if not scores or scores[0][0] == 0:
        other = tax.other_service
        sub = tax.main_to_subs.get(other, [None])[0] if other else None
        return RuleResult(contact, true_type, other, sub, 0.35, f"{type_reason} لم تُطابِق أي مؤشرات خدمة.", type_conf)
    best_score, best = scores[0]
    second = scores[1][0] if len(scores) > 1 else 0.0
    # Calibrated on the ADPF Q2 2026 reviewed labels: only a clear, uncontested
    # signal is trusted without the model. A contested one goes to the model.
    if best_score >= 2.5 and second == 0:
        service_conf = 0.9
    elif best_score >= 2 and second <= best_score / 3:
        service_conf = 0.8
    elif best_score > second:
        service_conf = 0.62
    else:
        service_conf = 0.5

    subs = tax.main_to_subs.get(best, [])
    if len(subs) == 1:
        sub, sub_conf = subs[0], 0.95
    else:
        sub_scores = sorted(
            ((_score(desc, res, tax.sub_signals.get((best, s), [])), s) for s in subs),
            reverse=True,
        )
        top, top_sub = sub_scores[0]
        runner = sub_scores[1][0] if len(sub_scores) > 1 else 0.0
        if top > runner:
            sub, sub_conf = top_sub, 0.85 if top >= 1.5 else 0.76
        else:
            sub, sub_conf = subs[0], 0.55
    confidence = round(min(type_conf, service_conf, sub_conf), 3)
    reason = f"{type_reason} مؤشرات الوصف والرد تشير إلى «{best}» / «{sub}»."
    return RuleResult(contact, true_type, best, sub, confidence, reason, type_conf)
