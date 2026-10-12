"""
The period resolver — the one genuinely pure thing in the module, pinned exactly.

It is shared with module 01, so a divergence here means two NoveIntelligence reports
over the same quarter carry different labels, which looks broken even when both are
right.
"""
from __future__ import annotations

from datetime import date

import pytest

from noveintel_inquiries.api.models import PeriodGranularity
from noveintel_inquiries.engine import derive_granularity, parse_dates, resolve_period
from noveintel_inquiries.engine.parse import parse_datetimes


class TestGranularity:
    @pytest.mark.parametrize(
        "start,end,expected",
        [
            (date(2025, 1, 1), date(2025, 1, 31), PeriodGranularity.MONTHLY),
            (date(2025, 1, 5), date(2025, 1, 5), PeriodGranularity.MONTHLY),
            (date(2025, 1, 1), date(2025, 3, 31), PeriodGranularity.QUARTERLY),
            (date(2025, 1, 1), date(2025, 6, 30), PeriodGranularity.SEMI_ANNUAL),
            (date(2025, 1, 1), date(2025, 12, 31), PeriodGranularity.ANNUAL),
        ],
    )
    def test_spans(self, start, end, expected):
        assert derive_granularity(start, end) is expected

    def test_a_short_february_is_still_a_quarter(self):
        """Calendar months, not day counts."""
        assert (
            derive_granularity(date(2025, 1, 1), date(2025, 3, 1))
            is PeriodGranularity.QUARTERLY
        )


class TestResolve:
    def test_labels_are_bilingual(self):
        period = resolve_period([date(2025, 2, 3), date(2025, 3, 20)])
        assert period.label_en == "Q1 2025"
        assert period.label_ar == "الربع الأول 2025"

    def test_it_is_named_off_the_end_of_the_span(self):
        """A run lapping into a new quarter is still about the quarter that closed."""
        period = resolve_period(
            [date(2024, 12, 20), date(2025, 1, 2)], PeriodGranularity.MONTHLY
        )
        assert period.label_en == "January 2025"

    def test_a_requested_granularity_relabels_but_does_not_filter(self):
        period = resolve_period(
            [date(2025, 1, 1), date(2025, 11, 30)], PeriodGranularity.QUARTERLY
        )
        assert period.granularity is PeriodGranularity.QUARTERLY
        # Every date is still inside the window: nothing was dropped.
        assert period.start == date(2025, 1, 1)
        assert period.end == date(2025, 11, 30)

    def test_no_dates_is_an_error_not_a_weaker_answer(self):
        with pytest.raises(ValueError, match="cannot be resolved"):
            resolve_period([])


class TestParsing:
    def test_unreadable_values_are_dropped_not_raised_on(self):
        """A run whose period is weakly labelled is still a run worth doing."""
        assert parse_dates(["2025-01-05", "not a date", None, ""]) == [date(2025, 1, 5)]

    def test_day_comes_first(self):
        """The source systems here are configured for the region: 03/04 is 3 April.
        Reading it the other way silently moves a case between quarters."""
        assert parse_dates(["03/04/2025"]) == [date(2025, 4, 3)]


class TestOneDateReading:
    """The period and the per-case dates are read by the same rules.

    The Streamlit-era pipeline labelled the report from a second, hand-rolled parser
    that could disagree with the period; there is now one rule — ISO 8601 first, then
    day-first — used for both.
    """

    @pytest.mark.parametrize("value", ["2025-02-17T09:07:08", "2025-02-17 09:07:08", "17/02/2025", "2025-02-17"])
    def test_case_dates_and_period_dates_agree(self, value):
        case = parse_datetimes([value])[0]
        assert case is not None and case.date() == parse_dates([value])[0]

    def test_an_ambiguous_slash_date_is_day_first_in_both(self):
        assert parse_datetimes(["03/04/2025"])[0].month == 4 == parse_dates(["03/04/2025"])[0].month

    def test_unparseable_is_none_positionally(self):
        assert parse_datetimes(["not a date", None, "2025-01-05"])[:2] == [None, None]
