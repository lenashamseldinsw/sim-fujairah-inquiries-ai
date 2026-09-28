"""
The request contract: one test per validation rule, accepting and rejecting.

These run without a gateway, without pandas doing anything interesting, and without
the pipeline. They pin the promises the OpenAPI document makes.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from noveintel_inquiries.api.models import (
    HARD_REQUIRED_COLUMNS,
    AnalysisOptions,
    BrandColors,
    EntityInfo,
    Language,
    InquiryRecord,
    GenerateInquiriesReportRequest,
    records_to_frame,
)


class TestRecords:
    def test_accepts_snake_case(self, record_dicts):
        record = InquiryRecord(**record_dicts[0])
        assert record.case_number == record_dicts[0]["case_number"]

    def test_accepts_arabic_column_names(self, record_dicts):
        """A caller that already normalised a dataframe posts the Arabic keys."""
        snake = InquiryRecord(**record_dicts[0])
        arabic = InquiryRecord(**snake.to_columns())
        assert arabic.case_number == snake.case_number
        assert arabic.case_details == snake.case_details

    @pytest.mark.parametrize("column", sorted(HARD_REQUIRED_COLUMNS))
    def test_required_column_missing_is_rejected(self, record_dicts, column):
        row = dict(record_dicts[0])
        row.pop(column)
        with pytest.raises(ValidationError) as caught:
            InquiryRecord(**row)
        # Pydantic locates a missing field by its alias when the model declares one,
        # so the error names the Arabic column. ``api/errors.py`` maps both spellings
        # back to the field, which is what lets the missing-column fold work at all.
        alias = InquiryRecord.model_fields[column].alias
        assert any(
            error["loc"] in {(column,), (alias,)} for error in caught.value.errors()
        )

    @pytest.mark.parametrize("blank", ["", "  ", "nan", "-", "None", "N/A", None])
    def test_required_column_blank_is_rejected(self, record_dicts, blank):
        """A spreadsheet's many spellings of "empty" are all rejected for a required
        field, rather than reaching a stage as the literal string "nan"."""
        row = dict(record_dicts[0])
        row["case_number"] = blank
        with pytest.raises(ValidationError):
            InquiryRecord(**row)

    @pytest.mark.parametrize("blank", ["", "  ", "nan", "-", "N/A"])
    def test_optional_column_blank_becomes_none(self, record_dicts, blank):
        row = dict(record_dicts[0])
        row["date_opened"] = blank
        assert InquiryRecord(**row).date_opened is None

    def test_whitespace_is_collapsed_not_merely_stripped(self, record_dicts):
        """Arabic pasted out of a web form carries newlines and runs of spaces, and
        the pipeline compares these values against each other."""
        row = dict(record_dicts[0])
        row["case_details"] = "  استفسار\n\n  عن   الرخصة  "
        assert InquiryRecord(**row).case_details == "استفسار عن الرخصة"

    def test_unknown_columns_are_kept(self, record_dicts):
        """A tenant recording something this contract has not heard of keeps it."""
        row = dict(record_dicts[0])
        row["عمود_غير_معروف"] = "قيمة"
        assert InquiryRecord(**row).to_columns()["عمود_غير_معروف"] == "قيمة"

    def test_to_columns_omits_what_was_not_sent(self, record_dicts):
        """Stage 1 counts the columns it is given and the report prints that count,
        so an unsent column must not appear as a null."""
        row = {k: v for k, v in record_dicts[0].items() if k in HARD_REQUIRED_COLUMNS}
        assert set(InquiryRecord(**row).to_columns()) == {
            InquiryRecord.model_fields[name].alias for name in HARD_REQUIRED_COLUMNS
        }


class TestFrame:
    def test_columns_are_the_union_in_first_seen_order(self, record_dicts):
        frame = records_to_frame([InquiryRecord(**row) for row in record_dicts])
        assert len(frame) == len(record_dicts)
        # Required columns come first because they are declared first on the model.
        assert list(frame.columns)[0] == InquiryRecord.model_fields["case_number"].alias

    def test_a_ragged_export_gets_nulls_not_a_rejection(self, record_dicts):
        rows = [dict(record_dicts[0]), dict(record_dicts[0])]
        rows[0]["date_opened"] = "2025-01-05"
        rows[1].pop("date_opened", None)
        frame = records_to_frame([InquiryRecord(**row) for row in rows])
        assert frame[InquiryRecord.model_fields["date_opened"].alias].isna().sum() == 1


class TestEntity:
    def test_names_are_required(self):
        with pytest.raises(ValidationError):
            EntityInfo(name_ar="شرطة الفجيرة")

    def test_two_logo_sources_are_rejected(self):
        """One or the other. Both means the caller does not know which is used."""
        with pytest.raises(ValidationError, match="not both"):
            EntityInfo(
                name_ar="أ", name_en="A", logo_path="/tmp/x.png", logo_base64="AAA="
            )

    def test_no_logo_is_fine(self):
        assert EntityInfo(name_ar="أ", name_en="A").logo_bytes() is None

    def test_logo_base64_accepts_a_data_uri(self):
        png = "data:image/png;base64,aGVsbG8="
        assert EntityInfo(name_ar="أ", name_en="A", logo_base64=png).logo_bytes() == b"hello"

    def test_bad_base64_raises_rather_than_returning_rubbish(self):
        entity = EntityInfo(name_ar="أ", name_en="A", logo_base64="not base64!!")
        with pytest.raises(ValueError, match="not valid base64"):
            entity.logo_bytes()

    def test_brand_defaults_are_the_platform_palette_not_a_tenant(self):
        assert BrandColors().primary == "#201853"

    def test_a_bad_hex_colour_is_rejected(self):
        with pytest.raises(ValidationError):
            BrandColors(primary="navy")

    def test_name_picks_the_language(self, entity):
        assert entity.name("ar") == entity.name_ar
        assert entity.name("en") == entity.name_en


class TestOptions:
    def test_defaults(self):
        options = AnalysisOptions()
        assert options.language is Language.AR
        assert options.include_english is True
        assert options.granularity is None

    def test_an_empty_record_list_is_rejected(self, entity):
        with pytest.raises(ValidationError):
            GenerateInquiriesReportRequest(records=[], entity=entity)

    def test_entity_has_no_default(self, record_dicts):
        with pytest.raises(ValidationError):
            GenerateInquiriesReportRequest(records=[InquiryRecord(**record_dicts[0])])
