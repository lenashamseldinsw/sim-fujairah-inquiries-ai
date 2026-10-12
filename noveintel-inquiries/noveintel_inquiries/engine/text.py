"""
Text normalisation shared by the parser, the rule chain and the evidence matchers.

Two different jobs, kept apart on purpose:

``fold_header`` folds a *column name* so that spelling variants of one header compare
equal (Platformisation requirement R4). The Fujairah export spells the department
header «الإداره العامة» with ه where the contract had ة; the ADPF export arrives in
English with mixed case and stray spaces. A list of known spellings misses the next
one, so headers are compared after folding instead.

``fold_text`` folds *free text* for keyword matching: the same letter-family folding
plus diacritic and tatweel removal, so a keyword written «الإقرار» matches a
description typed «الاقرار». It never changes what is stored or shown — only what is
compared.
"""
from __future__ import annotations

import re
import unicodedata

__all__ = [
    "fold_header",
    "fold_text",
    "contains_any",
    "count_hits",
    "clean_label",
    "word_count",
    "to_western_digits",
]

# Arabic harakat, tanween, shadda, sukun, superscript alef and the Quranic marks.
_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭ]")
_TATWEEL = "ـ"

# Letter families that real exports write interchangeably.
_LETTER_FOLD = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ة": "ه",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
        "ک": "ك",
        "ی": "ي",
    }
)

_ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

_SEPARATORS = re.compile(r"[\s_\-–—/\\.:]+")
_PUNCT_EDGES = re.compile(r"^[\W_]+|[\W_]+$", re.UNICODE)


def to_western_digits(value: str) -> str:
    """Replace Arabic-Indic and Persian digits with ASCII ones."""
    return value.translate(_ARABIC_INDIC)


def _base_fold(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value))
    value = _DIACRITICS.sub("", value).replace(_TATWEEL, "")
    value = value.translate(_LETTER_FOLD)
    return to_western_digits(value).casefold()


def fold_header(name: object) -> str:
    """Fold a column header so spelling variants compare equal.

    Folds ه/ة, the hamza forms of alef, ى/ي, diacritics and tatweel; treats spaces,
    underscores, hyphens and slashes as one separator; trims; ignores case. Two headers
    that fold to the same string are the same column.
    """
    if name is None:
        return ""
    folded = _base_fold(str(name))
    folded = _SEPARATORS.sub(" ", folded)
    return _PUNCT_EDGES.sub("", folded.strip())


def fold_text(value: object) -> str:
    """Fold free text for keyword comparison. Never used for display."""
    if value is None:
        return ""
    folded = _base_fold(str(value))
    return re.sub(r"\s+", " ", folded).strip()


def contains_any(folded_text: str, folded_keywords: list[str]) -> bool:
    """Whether any pre-folded keyword occurs in pre-folded text."""
    return any(k and k in folded_text for k in folded_keywords)


def count_hits(folded_text: str, folded_keywords: list[str]) -> int:
    """How many distinct pre-folded keywords occur in pre-folded text."""
    return sum(1 for k in set(folded_keywords) if k and k in folded_text)


def clean_label(value: object) -> str:
    """Trim a label and collapse inner whitespace. Keeps the original spelling."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def word_count(value: str) -> int:
    """Words in a sentence, counting a token of letters or digits as a word."""
    return len([w for w in re.split(r"\s+", value.strip()) if w])
