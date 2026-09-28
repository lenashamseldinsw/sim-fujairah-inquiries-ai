"""
Shared record helpers — the coercers that make a dataframe dump acceptable input.

Records arrive from a caller that exported a spreadsheet and serialised it. That
export carries the debris a spreadsheet leaves behind: the string ``"nan"`` where
pandas wrote a missing float, ``"-"`` where a human typed a dash to mean "none",
``"None"`` from a careless ``str()``, and whitespace everywhere. None of it is a
reason to reject a run, and all of it means the same thing — no value.

So input is accepted leniently and normalised once, here, at the boundary. Output
stays strict. That asymmetry is deliberate (porting guide §6.11): the caller's export
is not something we control, and the report is.
"""
from __future__ import annotations

from typing import Annotated, Any

from pydantic import BeforeValidator

__all__ = [
    "OptionalFlag",
    "OptionalStr",
    "RequiredStr",
    "is_blank",
]

# Values that a spreadsheet export uses to mean "empty". Compared casefolded.
_BLANK_TOKENS = {
    "",
    "-",
    "--",
    "nan",
    "none",
    "null",
    "n/a",
    "na",
    "#n/a",
    "#null!",
}

# What a tenant writes for yes and no, in either language.
_TRUE_TOKENS = {"1", "true", "yes", "y", "نعم", "صح", "مغلق"}
_FALSE_TOKENS = {"0", "false", "no", "n", "لا", "خطأ", "مفتوح"}


def is_blank(value: Any) -> bool:
    """Whether a value means "no value", in any of the forms an export produces.

    ``None`` and a float NaN are the honest forms. The rest are strings that only
    look like values: a spreadsheet round-tripped through pandas and ``str()``
    produces ``"nan"`` for a missing number, and a human filling a cell by hand
    produces ``"-"``.
    """
    if value is None:
        return True
    # NaN is the only value that is not equal to itself, which is how a float
    # missing-marker is spotted without importing numpy at the contract layer.
    if isinstance(value, float) and value != value:
        return True
    if isinstance(value, str):
        return " ".join(value.split()).casefold() in _BLANK_TOKENS
    return False


def _scalar_to_text(value: Any) -> str:
    """Render a spreadsheet scalar as the text the pipeline expects.

    A number, a date or a boolean in a text column is an ordinary export artefact —
    a case number that a spreadsheet stored as a float, a date pandas already
    parsed — and stringifying it is the right, lenient thing.

    A dict or a list is not. Those cannot come from a cell; they come from a caller
    sending the wrong shape, and ``str()`` would turn that mistake into a plausible
    looking value — a case whose details read ``{'text': '...'}`` — that survives all
    the way into the report. Leniency is for the debris an export leaves behind, not
    for structural errors, so those are refused and pydantic reports the field.
    """
    if isinstance(value, (dict, list, tuple, set)):
        raise ValueError(
            "Expected a text value; received a nested object. Send the cell's text, "
            "not the structure around it."
        )
    return str(value)


def _coerce_optional_str(value: Any) -> str | None:
    """Fold a cell to clean text, or to ``None`` when it means nothing.

    Whitespace is collapsed rather than merely stripped: an Arabic cell copied out of
    a web form routinely carries newlines and runs of spaces mid-string, and the
    pipeline's matching compares these values against each other.
    """
    if is_blank(value):
        return None
    if isinstance(value, str):
        return " ".join(value.split())
    return _scalar_to_text(value)


def _coerce_required_str(value: Any) -> Any:
    """The same, but an absent value stays absent so pydantic reports it.

    Returning ``None`` here rather than a default is what turns a blank required cell
    into a validation error naming the field, instead of a downstream failure in a
    stage that expected text.
    """
    if is_blank(value):
        return None
    if isinstance(value, str):
        return " ".join(value.split())
    return _scalar_to_text(value)


def _coerce_flag(value: Any) -> bool | None:
    """Read a yes/no cell in either language, or ``None`` when it is blank.

    Unrecognised text is kept as ``None`` rather than guessed. A cell reading
    "partially" is not a no, and treating it as one would quietly move a case into
    the compliant column.
    """
    if is_blank(value):
        return None
    if isinstance(value, bool):
        return value
    token = " ".join(str(value).split()).casefold()
    if token in _TRUE_TOKENS:
        return True
    if token in _FALSE_TOKENS:
        return False
    return None


OptionalStr = Annotated[str | None, BeforeValidator(_coerce_optional_str)]
RequiredStr = Annotated[str, BeforeValidator(_coerce_required_str)]
OptionalFlag = Annotated[bool | None, BeforeValidator(_coerce_flag)]
