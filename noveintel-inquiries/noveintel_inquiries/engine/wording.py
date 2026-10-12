"""
Wording the report is not allowed to improvise (Prerequisites §3, Full Report Prompt §5).

Fixed terms, the exact timeliness labels, channel names, the platform's banned words
and the ADPF vocabulary list that ships as the default override. Applied in two
places: given to the narrative model as instructions, and enforced on what it returns
(``apply_vocabulary``, ``replace_banned``, ``clean_list_item``), so a slip in the prose
is corrected rather than shipped.
"""
from __future__ import annotations

import re

from .text import fold_text

__all__ = [
    "BANNED_AR",
    "BANNED_EN",
    "CONTACT_TYPES",
    "CONTACT_TYPE_EN",
    "DEFAULT_VOCABULARY",
    "PROVENANCE",
    "PROVENANCE_EN",
    "TIMELINESS_LABELS",
    "TRUE_TYPES",
    "apply_vocabulary",
    "channel_label",
    "clean_list_item",
    "is_phone_channel",
    "is_walk_in_channel",
    "is_live_chat_or_self_service",
    "month_name",
    "replace_banned",
    "NOT_PROVIDED",
    "UNCLASSIFIED",
]

# «لم يُزوَّد» — a present-but-empty column. «غير مصنَّف» — a case without a label.
NOT_PROVIDED = {"ar": "لم يُزوَّد", "en": "Not provided"}
UNCLASSIFIED = {"ar": "غير مصنَّف", "en": "Unclassified"}

# D1 — the four actual contact types, and their English names.
CONTACT_TYPES: tuple[str, ...] = ("استفسار", "طلب خدمة", "شكوى", "شكر وثناء")
CONTACT_TYPE_EN: dict[str, str] = {
    "استفسار": "Inquiry",
    "طلب خدمة": "Service request",
    "شكوى": "Complaint",
    "شكر وثناء": "Compliment",
}
# Canonical recorded/true type → D1.
TYPE_TO_CONTACT = {
    "inquiry": "استفسار",
    "service_request": "طلب خدمة",
    "complaint": "شكوى",
    "incident": "شكوى",
    "compliment": "شكر وثناء",
    "suggestion": "استفسار",
}
CONTACT_TO_TYPE = {
    "استفسار": "inquiry",
    "طلب خدمة": "service_request",
    "شكوى": "complaint",
    "شكر وثناء": "compliment",
}
TRUE_TYPES: tuple[str, ...] = (
    "inquiry", "service_request", "complaint", "incident", "compliment", "out_of_scope",
)

# D6 — provenance, as the report prints it, in the ADPF practice's own words:
#   «آلي - موثوق»   auto: settled quickly by the keyword rules or copied from an
#                   identical case;
#   «نموذج»         the model's first pass;
#   «آلي - مُصحّح»   auto, then corrected by a rule;
#   «يدوي - مُراجع» the deep review: a second, higher-effort AI pass over the cases the
#                   first pass was unsure of. Not a person — the ADPF label is kept so a
#                   labelled master round-trips with its own words.
PROVENANCE: dict[str, str] = {
    "auto": "آلي - موثوق",
    "llm": "نموذج",
    "auto_corrected": "آلي - مُصحّح",
    "deep_review": "يدوي - مُراجع",
    "draft": "مسودة - مُصنّفة آلياً",
}
PROVENANCE_EN: dict[str, str] = {
    "auto": "Auto — keywords or duplicate",
    "llm": "Model",
    "auto_corrected": "Auto — rule-corrected",
    "deep_review": "Reviewed — deep AI review",
    "draft": "Draft — auto-classified",
}

TIMELINESS_LABELS: dict[str, dict[str, str]] = {
    "within": {"ar": "ضمن المهلة", "en": "Within deadline"},
    "near": {"ar": "قرب انتهاء المهلة", "en": "Near deadline"},
    "over": {"ar": "متجاوزة المهلة", "en": "Over deadline"},
    "unspecified": {"ar": "غير محدد", "en": "Unspecified"},
}

# Platform banned words (Domain 01 test round; guardrail #10) → neutral replacements.
BANNED_AR: dict[str, str] = {
    "هيمنت": "استحوذت",
    "تهيمن": "تستحوذ",
    "يهيمن": "يستحوذ",
    "هيمنة": "الحصة الأكبر",
    "الهيمنة": "الحصة الأكبر",
    "سيطرة": "الحصة الأكبر",
    "السيطرة": "الحصة الأكبر",
    "سيطرت": "استحوذت",
    "تسيطر": "تستحوذ",
}
BANNED_EN: dict[str, str] = {
    "dominated": "formed the largest share of",
    "dominates": "forms the largest share of",
    "dominating": "forming the largest share of",
    "dominant": "largest",
    "dominance": "largest share",
    "commanding": "leading",
    "overwhelming": "large",
    "overwhelmingly": "largely",
}

# The ADPF locked vocabulary (Prerequisites §3) — the default override list.
DEFAULT_VOCABULARY: dict[str, dict[str, str]] = {
    "ar": {
        "التحول الرقمي": "التحويل الرقمي",
        "الرُّبريك": "المعايير",
        "الربريك": "المعايير",
        "فجوة حرجة": "فرصة رقمية",
        "فجوات حرجة": "فرص رقمية",
        "مصنَّفة خطأً": "قابلة لإعادة التصنيف الذكي",
        "مصنفة خطأ": "قابلة لإعادة التصنيف الذكي",
        "بناء منظومة إشعارات جديدة": "تنسيق تحسين صياغة إشعارات «تم» المعتمدة",
        "منظومة إشعارات جديدة": "منظومة إشعارات «تم» المعتمدة",
    },
    "en": {
        "rubric": "criteria",
        "critical gap": "digital opportunity",
        "critical gaps": "digital opportunities",
        "mis-classified": "eligible for smart re-classification",
        "misclassified": "eligible for smart re-classification",
        "digital transformation": "digital transformation",
    },
}

_LEADING_SYMBOLS = re.compile(r"^\s*(?:[-–—•·*▪►✓✔]|\(?\d+[.)\-]|\(?[a-zA-Z][.)])\s*")
_AI_LATIN = re.compile(r"(?<![A-Za-z])AI(?![A-Za-z])")


def clean_list_item(item: str) -> str:
    """Strip a leading number, bullet or symbol — list fields are plain text."""
    previous = None
    text = str(item or "").strip()
    while previous != text:
        previous = text
        text = _LEADING_SYMBOLS.sub("", text).strip()
    return text


def replace_banned(text: str, lang: str) -> tuple[str, list[str]]:
    """Replace banned dramatic words with the neutral term. Returns what was hit."""
    hits: list[str] = []
    table = BANNED_AR if lang == "ar" else BANNED_EN
    for word in sorted(table, key=len, reverse=True):
        replacement = table[word]
        if lang == "ar":
            # A conjunction glued to the word («وهيمنت») is kept on the replacement.
            pattern = re.compile(
                r"(?<![؀-ۿ])([وف]?)" + re.escape(word) + r"(?![؀-ۿ])"
            )
            repl = lambda m, r=replacement: m.group(1) + r  # noqa: E731
        else:
            pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
            repl = replacement
        if pattern.search(text):
            hits.append(word)
            text = pattern.sub(repl, text)
    return text, hits


def apply_vocabulary(text: str, overrides: dict[str, str], lang: str) -> str:
    """Apply the tenant's wording overrides, then the platform's fixed rules."""
    for avoid in sorted(overrides, key=len, reverse=True):
        use = overrides[avoid]
        if not avoid or avoid == use:
            continue
        if lang == "en":
            text = re.sub(rf"\b{re.escape(avoid)}\b", use, text, flags=re.IGNORECASE)
        else:
            text = text.replace(avoid, use)
    if lang == "ar":
        # «الذكاء الاصطناعي» not «AI» (ADPF vocabulary).
        text = _AI_LATIN.sub("الذكاء الاصطناعي", text)
    else:
        text = _AI_LATIN.sub("artificial intelligence", text)
    return text


# ── Channels ──────────────────────────────────────────────────────────────────
# Recorded channel values are an open set; these recognise the common ones so the
# report can name them in each language and decide the digital share.
_CHANNELS: list[tuple[tuple[str, ...], str, str, str]] = [
    # (folded tokens, key, Arabic, English)
    (("phone", "هاتف", "الهاتف", "اتصال", "مكالمه", "call", "voice"), "phone", "الهاتف", "Phone"),
    (("live chat", "الدردشه", "دردشه", "chat", "محادثه"), "live_chat", "الدردشة الحية", "Live chat"),
    (("self service", "خدمه ذاتيه", "الخدمه الذاتيه", "self-service", "portal", "بوابه"), "self_service", "الخدمة الذاتية", "Self-service"),
    (("mail", "email", "e-mail", "بريد", "البريد"), "mail", "البريد", "Mail"),
    (("virtual agent", "المساعد الافتراضي", "chatbot", "bot"), "virtual_agent", "المساعد الافتراضي", "Virtual agent"),
    (("social", "تواصل اجتماعي", "وسائل التواصل"), "social", "وسائل التواصل", "Social media"),
    (("walk-in", "walk in", "زياره شخصيه", "حضوري", "مركز الخدمه", "service center"), "walk_in", "الزيارة الشخصية", "Walk-in"),
    (("app", "تطبيق", "التطبيق", "application", "mobile app"), "app", "التطبيق الذكي", "Mobile app"),
    (("website", "web", "موقع", "الموقع الالكتروني"), "website", "الموقع الإلكتروني", "Website"),
]


def _channel_entry(value: str):
    folded = fold_text(value)
    for tokens, key, ar, en in _CHANNELS:
        for token in tokens:
            if fold_text(token) in folded:
                return key, ar, en
    return None


def channel_key(value: str) -> str | None:
    hit = _channel_entry(value)
    return hit[0] if hit else None


def channel_label(value: str, lang: str) -> str:
    """The channel's name in the report language, or the recorded value."""
    hit = _channel_entry(value)
    if not hit:
        return value
    return hit[1] if lang == "ar" else hit[2]


def is_phone_channel(value: str) -> bool:
    return channel_key(value) == "phone"


def is_walk_in_channel(value: str) -> bool:
    return channel_key(value) == "walk_in"


def is_live_chat_or_self_service(value: str) -> bool:
    return channel_key(value) in {"live_chat", "self_service"}


_MONTHS_AR = (
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
)
_MONTHS_EN = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def month_name(month: int, lang: str, year: int | None = None, with_year: bool = False) -> str:
    name = (_MONTHS_AR if lang == "ar" else _MONTHS_EN)[month - 1]
    return f"{name} {year}" if with_year and year else name
