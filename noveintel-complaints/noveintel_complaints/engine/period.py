"""
Resolving the reporting window from the data.

Kept identical in behaviour to module 01's ``engine/period.py`` so that two
NoveIntelligence modules run over the same quarter print the same period label. A
front end that shows "الربع الأول 2025" for one and "Q1 2025 (Jan-Mar)" for the other
looks broken even when both are right.

Pure: dates in, a ``Period`` out. No I/O, no model call, nothing that can fail for a
reason outside the arguments. That makes it the one part of a run a test can pin
exactly, which is why the granularity rules live here rather than inside a stage.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Sequence

from ..api.models.enums import PeriodGranularity
from ..api.models.period import Period

__all__ = ["derive_granularity", "parse_dates", "resolve_period"]

_ARABIC_MONTHS = (
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
)
_ENGLISH_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
_ARABIC_QUARTERS = ("الربع الأول", "الربع الثاني", "الربع الثالث", "الربع الرابع")
_ARABIC_HALVES = ("النصف الأول", "النصف الثاني")


def parse_dates(values: Iterable[object]) -> list[date]:
    """Read whatever the caller sent as dates, discarding what is not one.

    Callers export from systems that write dates in every format there is, and a run
    whose period could not be resolved is still a run worth doing — the report simply
    carries a weaker label. So an unparseable value is dropped rather than raised on.

    **Two passes, and the order matters.** ISO 8601 is tried first, because
    ``2025-01-05`` is unambiguously 5 January and a day-first reading turns it into 1
    May — a nine-week error, silently moving cases between quarters. Only what ISO
    could not read is retried day-first, which is right for the ambiguous slash
    formats the regional source systems produce: there ``03/04/2025`` is 3 April, not
    4 March.

    Doing it the other way round, or in one pass with ``dayfirst=True``, misreads
    every ISO date that has a day of 12 or less.
    """
    import pandas as pd

    raw = list(values)
    if not raw:
        return []

    series = pd.Series(raw, dtype="object")
    parsed = pd.to_datetime(series, errors="coerce", format="ISO8601")

    unresolved = parsed.isna()
    if unresolved.any():
        fallback = pd.to_datetime(
            series[unresolved], errors="coerce", dayfirst=True, format="mixed"
        )
        parsed = parsed.where(~unresolved, fallback)

    return [value.date() for value in parsed.dropna()]


def derive_granularity(start: date, end: date) -> PeriodGranularity:
    """Pick the granularity that describes a span without overstating it.

    The thresholds are calendar spans rather than day counts, so a run over exactly
    January to March is a quarter whether or not February had 29 days.

    Boundaries are inclusive at the low end on purpose: data covering one calendar
    month is monthly, and a single day is monthly too — there is no finer granularity
    to fall back on, and calling one day "annual" would be absurd.
    """
    months = (end.year - start.year) * 12 + (end.month - start.month) + 1
    if months <= 1:
        return PeriodGranularity.MONTHLY
    if months <= 3:
        return PeriodGranularity.QUARTERLY
    if months <= 6:
        return PeriodGranularity.SEMI_ANNUAL
    return PeriodGranularity.ANNUAL


def _index_for(granularity: PeriodGranularity, when: date) -> int:
    """Where a date falls within its year, at the given granularity."""
    if granularity is PeriodGranularity.MONTHLY:
        return when.month
    if granularity is PeriodGranularity.QUARTERLY:
        return (when.month - 1) // 3 + 1
    if granularity is PeriodGranularity.SEMI_ANNUAL:
        return 1 if when.month <= 6 else 2
    return 1


def _labels(granularity: PeriodGranularity, index: int, year: int) -> tuple[str, str]:
    """The Arabic and English names for a resolved period."""
    if granularity is PeriodGranularity.MONTHLY:
        return f"{_ARABIC_MONTHS[index - 1]} {year}", f"{_ENGLISH_MONTHS[index - 1]} {year}"
    if granularity is PeriodGranularity.QUARTERLY:
        return f"{_ARABIC_QUARTERS[index - 1]} {year}", f"Q{index} {year}"
    if granularity is PeriodGranularity.SEMI_ANNUAL:
        return f"{_ARABIC_HALVES[index - 1]} {year}", f"H{index} {year}"
    return f"عام {year}", f"FY {year}"


def resolve_period(
    dates: Sequence[date], requested: PeriodGranularity | None = None
) -> Period:
    """Turn the run's dates into the window the report is labelled with.

    ``requested`` overrides the derived granularity but never the dates: asking for a
    quarterly label over eleven months of data relabels the report and analyses every
    record just the same. Filtering is the caller's job, and doing it here silently
    would drop rows a caller believed were counted.

    Raises ``ValueError`` on an empty sequence, because a period with no dates in it
    is not a weaker answer — it is no answer, and the caller sent nothing datable.
    """
    if not dates:
        raise ValueError(
            "No usable dates in the records, so the reporting period cannot be "
            "resolved. At least one record needs a readable date_opened."
        )

    start, end = min(dates), max(dates)
    granularity = requested or derive_granularity(start, end)

    # Indexed and named off the *end* of the span. A run that laps into the first days
    # of a new quarter is still a report about the quarter that just closed, and
    # naming it after the start would label a full-year run by its January.
    index = _index_for(granularity, end)
    label_ar, label_en = _labels(granularity, index, end.year)

    return Period(
        granularity=granularity,
        index=index,
        year=end.year,
        start=start,
        end=end,
        label_ar=label_ar,
        label_en=label_en,
    )


def period_from_datetimes(
    values: Iterable[object], requested: PeriodGranularity | None = None
) -> Period:
    """``parse_dates`` then ``resolve_period`` — the path a run actually takes."""
    return resolve_period(parse_dates(values), requested)
