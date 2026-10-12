"""
Redaction — applied before any text reaches a model, and in every example shown.

Data Mapping §2's placeholders:

    person names → [الاسم]            Emirates ID / national ID → [الهوية الإماراتية]
    tracking / case refs → [رقم التتبع]   dates → [تاريخ]       amounts → [مبلغ]
    employer names → [جهة العمل]       phone / e-mail → [بيانات اتصال]

Pattern-based redaction of free text cannot be perfect — a name typed with no cue
around it looks like any other word — so it is backed by the one source that is
exact: the row's own sensitive columns. The customer name, ID number and mobile the
export carried for this case are replaced wherever they occur in this case's text,
before the columns themselves are dropped (BR-34/35, R3).

URLs are kept: a link in the resolution is evidence the case was answered with
information, which is what the codebook's contact-type test reads.
"""
from __future__ import annotations

import re

__all__ = ["redact", "PLACEHOLDERS"]

PLACEHOLDERS = {
    "name": "[الاسم]",
    "id": "[الهوية الإماراتية]",
    "tracking": "[رقم التتبع]",
    "date": "[تاريخ]",
    "amount": "[مبلغ]",
    "employer": "[جهة العمل]",
    "contact": "[بيانات اتصال]",
}

_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_EMIRATES_ID = re.compile(r"\b784[\s-]?\d{4}[\s-]?\d{7}[\s-]?\d\b")
_PHONE = re.compile(
    r"(?<!\d)(?:\+?971|00971|0)\s?-?(?:5\d|[234679])[\s-]?\d{3}[\s-]?\d{4}(?!\d)"
)
_CASE_REF = re.compile(r"\b\d{6}-\d{5,8}\b")
_DATE = re.compile(
    r"\b(?:\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{4}[/.\-]\d{1,2}[/.\-]\d{1,2})\b"
)
_AMOUNT = re.compile(
    r"(?:(?:AED|درهم|دراهم|د\.?إ\.?)\s*[\d٠-٩][\d٠-٩,.]*|[\d٠-٩][\d٠-٩,.]*\s*"
    r"(?:AED|aed|Dhs?|درهم|دراهم|د\.?إ\.?|الف درهم|ألف درهم))"
)
_LONG_NUMBER = re.compile(r"(?<![\d\[])\d{6,}(?![\d\]])")
_CODE = re.compile(r"\b[A-Za-z]{2,6}-?\d{3,}[A-Za-z0-9\-]*\b|\b[A-Za-z]{2,6}-?(?=\[رقم التتبع\])")
_MONTHS = (
    "يناير|فبراير|مارس|ابريل|أبريل|إبريل|مايو|يونيو|يوليو|اغسطس|أغسطس|سبتمبر|اكتوبر|أكتوبر|نوفمبر|ديسمبر|"
    "January|February|March|April|May|June|July|August|September|October|November|December|"
    "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
_WRITTEN_DATE = re.compile(
    rf"\b\d{{1,2}}\s+(?:{_MONTHS})\.?,?\s+\d{{4}}\b|\b(?:{_MONTHS})\s+\d{{1,2}},?\s+\d{{4}}\b", re.IGNORECASE
)
# Employer cues without a colon: «جهة عملك اوم للمقاولات …», «شركة …». The name is
# taken word by word until a stop word; a generic phrase («جهة العمل الجديدة») starts
# with the definite article and is left alone.
_EMPLOYER_CUE = re.compile(
    r"((?:(?:جه[ةه]\s+(?:العمل|عملي|عملك|عمله|عملها)|الجه[ةه]|الشرك[ةه]|شرك[ةه])\s*[:：]?|(?:company|employer)(?:\s+name)?\s*[:：])\s*)"
    r"((?:[^\s\[\]،,.؛:\n]+\s*){1,6})",
    re.IGNORECASE,
)
_EMPLOYER_STOP = {
    "من", "في", "على", "عن", "الى", "إلى", "لم", "تم", "قد", "و", "مع", "برقم", "رقم", "حيث", "التي", "الذي",
    "وذلك", "لغايات", "بتاريخ", "تاريخ", "منذ", "ولم", "وتم", "لدى", "حتى", "is", "has", "to", "the", "and", "for",
}
_EMPLOYER = re.compile(
    r"((?:اسم\s+)?جهة\s+العمل\s*[:：]\s*)([^\n.،,؛]+)|((?:employer|company)(?:\s+name)?\s*[:：]\s*)([^\n.,;]+)",
    re.IGNORECASE,
)
_NAME_CUES = re.compile(
    r"((?:اسمي|اسم المتعامل|اسم المؤمن عليه|اسم (?:المتوفي|المتوفى|المتوفية|الموظف|الموظفة|المتقاعد|المتقاعدة|الوالد|الوالدة|الأب|الام|الأم|الابن|الابنة|المستحق)\s*[:：]?|المتعامل\s*[:：]|السيد(?:ة)?|الأستاذ(?:ة)?|المرحوم(?:ة)?|"
    r"(?i:my name is|name\s*[:：]|mr\.?|mrs\.?|ms\.?|miss))\s*)"
    r"((?:[\u0621-\u064A]{2,}\s*){1,6}|(?:[A-Z][a-z]+\s*){1,3})"
)


# Words that end a name: a name cue is followed by the name, then the sentence goes on.
_NAME_STOP = {
    "يسأل", "يسال", "تسأل", "يستفسر", "تستفسر", "يرغب", "ترغب", "يود", "تود", "يطلب",
    "تطلب", "عن", "حول", "بخصوص", "في", "من", "على", "الى", "إلى", "رقم", "المحترم",
    "المحترمة", "و", "مع", "بشأن", "لديه", "لديها", "قام", "قامت", "تم", "هل",
}


def _name_replacement(match: re.Match) -> str:
    words = match.group(2).split()
    taken = 0
    for word in words:
        if word in _NAME_STOP or taken == 5:
            break
        taken += 1
    rest = " ".join(words[taken:])
    tail = (" " + rest) if rest else ""
    if not taken:
        return match.group(0)
    return match.group(1) + PLACEHOLDERS["name"] + tail + " "


def _employer_replacement(match: re.Match) -> str:
    words = match.group(2).split()
    if not words or words[0].startswith("ال") or words[0] in _EMPLOYER_STOP or words[0].startswith("["):
        return match.group(0)
    taken = 0
    for word in words:
        if word in _EMPLOYER_STOP or word.startswith("[") or taken == 5:
            break
        taken += 1
    rest = " ".join(words[taken:])
    return match.group(1) + PLACEHOLDERS["employer"] + ((" " + rest) if rest else "") + " "


def _mask_known(text: str, known: list[str]) -> str:
    for value in sorted({v.strip() for v in known if v and len(v.strip()) >= 3}, key=len, reverse=True):
        text = re.sub(re.escape(value), PLACEHOLDERS["name"], text, flags=re.IGNORECASE)
        # Each part of a multi-word name, when it is distinctive enough to be safe.
        for part in value.split():
            if len(part) >= 4 and not part.isdigit():
                text = re.sub(
                    rf"(?<![\w\[]){re.escape(part)}(?![\w\]])",
                    PLACEHOLDERS["name"], text, flags=re.IGNORECASE,
                )
    return text


def redact(text: object, known_values: list[str] | None = None, case_id: str | None = None) -> str:
    """Redact one free-text field. ``known_values`` are this row's identity values."""
    if text is None:
        return ""
    value = str(text)
    if not value.strip():
        return value

    urls: list[str] = []

    def _hold(match: re.Match) -> str:
        urls.append(match.group(0))
        return f"\x00{len(urls) - 1}\x00"

    value = _URL.sub(_hold, value)
    if known_values:
        value = _mask_known(value, known_values)
    if case_id:
        value = value.replace(str(case_id), PLACEHOLDERS["tracking"])
    value = _EMAIL.sub(PLACEHOLDERS["contact"], value)
    value = _EMIRATES_ID.sub(PLACEHOLDERS["id"], value)
    value = _PHONE.sub(PLACEHOLDERS["contact"], value)
    value = _CASE_REF.sub(PLACEHOLDERS["tracking"], value)
    value = _DATE.sub(PLACEHOLDERS["date"], value)
    value = _WRITTEN_DATE.sub(PLACEHOLDERS["date"], value)
    value = _AMOUNT.sub(PLACEHOLDERS["amount"], value)
    value = _LONG_NUMBER.sub(PLACEHOLDERS["tracking"], value)
    value = _CODE.sub(PLACEHOLDERS["tracking"], value)
    value = re.sub(r"(?:\[رقم التتبع\]){2,}", PLACEHOLDERS["tracking"], value)
    value = _EMPLOYER.sub(
        lambda m: (m.group(1) or m.group(3)) + PLACEHOLDERS["employer"], value
    )
    value = _EMPLOYER_CUE.sub(_employer_replacement, value)
    value = _NAME_CUES.sub(_name_replacement, value)
    value = re.sub(r"\x00(\d+)\x00", lambda m: urls[int(m.group(1))], value)
    return re.sub(r"[ \t]{2,}", " ", value).strip()
