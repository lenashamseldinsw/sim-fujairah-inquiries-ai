"""
The period resolver — the one genuinely pure thing in the module, pinned exactly.

It is shared with module 01, so a divergence here means two NoveIntelligence reports
over the same quarter carry different labels, which looks broken even when both are
right.
"""
from __future__ import annotations

from datetime import date

import pytest

from noveintel_complaints.api.models import PeriodGranularity
from noveintel_complaints.engine import derive_granularity, parse_dates, resolve_period
from noveintel_complaints.stages.state import extract_month_year_range


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


class TestMonthYearExtraction:
    """``stages.state.extract_month_year_range`` — the label Stage 6 cannot run without.

    Regression tests for a defect a live run found. The Streamlit path handed this
    function pandas Timestamps, whose ``str()`` uses a space separator, so only that
    form was ever exercised. A JSON caller sends ISO 8601 with a ``T`` — the format
    this API documents as safest — which parsed as nothing, left ``month_year`` None,
    and failed Stage 6 with an error blaming Stage 3.
    """

    def test_iso_8601_with_a_t_separator(self):
        cases = [
            {"date_opened": "2025-07-17T12:01:16"},
            {"date_opened": "2025-02-17T09:07:08"},
        ]
        assert extract_month_year_range(cases) == "February - July 2025"

    def test_a_space_separator_still_works(self):
        """What the Streamlit path produced. Must not regress."""
        assert (
            extract_month_year_range([{"date_opened": "2025-02-17 09:07:08"}])
            == "February 2025"
        )

    @pytest.mark.parametrize(
        "value", ["2025-02-17", "17/02/2025", "2025-02-17T09:07:08", "2025-02-17 09:07:08"]
    )
    def test_every_documented_format_yields_a_label(self, value):
        assert extract_month_year_range([{"date_opened": value}]) == "February 2025"

    def test_arabic_month_names(self):
        assert (
            extract_month_year_range([{"date_opened": "2025-02-17T09:07:08"}], lang="ar")
            == "فبراير 2025"
        )

    def test_unparseable_dates_give_none_not_a_wrong_label(self):
        """None is what Stage 6 checks for. A plausible-looking wrong label would be
        worse: it would print on the cover of a report about a different period."""
        assert extract_month_year_range([{"date_opened": "not a date"}]) is None
        assert extract_month_year_range([]) is None
