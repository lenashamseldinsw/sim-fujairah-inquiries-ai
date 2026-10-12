"""
The input contract: universal columns, header recognition, requiredness, settings,
reference lists and the identity pack.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from noveintel_inquiries.api.models import (
    COLUMNS,
    LABEL_COLUMNS,
    NOVEAI_MAGENTA,
    NOVEAI_NAVY,
    REQUIRED_COLUMNS,
    SENSITIVE_COLUMNS,
    EntityInfo,
    GenerateInquiriesReportRequest,
    InquiryRecord,
    TenantSettings,
    missing_fields_message,
    missing_required_fields,
    resolve_header,
)
from noveintel_inquiries.api.models.columns import HeaderMatch


def _variants(spelling: str) -> list[str]:
    """The spellings real exports produce for one header (R4)."""
    out = {spelling, spelling + " ", " " + spelling, spelling.replace(" ", "_"), spelling.upper(), spelling.lower()}
    for a, b in (("ة", "ه"), ("أ", "ا"), ("إ", "ا"), ("ي", "ى"), ("ه", "ة")):
        if a in spelling:
            out.add(spelling.replace(a, b))
    out.add(spelling.replace(" ", "  "))
    return sorted(out)


class TestHeaderNormalisation:
    """Platformisation R4: headers are matched by normalisation, not a spelling list."""

    @pytest.mark.parametrize("spec", COLUMNS + LABEL_COLUMNS + SENSITIVE_COLUMNS, ids=lambda s: s.name)
    def test_every_spelling_variant_of_every_column_maps(self, spec):
        for spelling in spec.all_spellings():
            for variant in _variants(spelling):
                resolved, _ = resolve_header(variant)
                assert resolved is not None and resolved.name == spec.name, (variant, spec.name)

    def test_the_fujairah_department_spelling_that_was_unmapped_now_maps(self):
        # The Atlas's gap: «الإداره العامة» (ه) left admin blank on every case.
        assert resolve_header("الإداره العامة")[0].name == "department"
        assert resolve_header("الاداره العامه")[0].name == "department"

    def test_adpf_english_headers_map(self):
        for header, name in [("Case Number", "case_id"), ("Resolution Response", "resolution_text"),
                             ("Case Type", "case_type"), ("SLA Color", "sla_status"), ("Date Opened", "opened_datetime"),
                             ("Service Name", "crm_service"), ("Next Escalation Date", "escalation_datetime")]:
            assert resolve_header(header)[0].name == name

    def test_system_columns_are_recognised(self):
        assert resolve_header("(Do Not Modify) Row Checksum")[1] is HeaderMatch.SYSTEM

    def test_an_unknown_header_is_unmapped(self):
        assert resolve_header("something else")[1] is HeaderMatch.UNMAPPED


class TestRecords:
    def test_canonical_names(self, record_dicts):
        record = InquiryRecord.model_validate(record_dicts[0])
        assert record.case_id == record_dicts[0]["case_id"]

    def test_known_headers_and_legacy_names_are_renamed(self):
        record = InquiryRecord.model_validate({
            "رقم الطلب": "1", "case_details": "x", "الحل": "y", "نوع المكالمة": "استفسار",
            "تاريخ_الإنشاء": "2026-01-01", "Owner": "SM-ND queue",
        })
        assert (record.case_id, record.description, record.resolution_text, record.case_type) == ("1", "x", "y", "استفسار")
        assert record.opened_datetime == "2026-01-01"
        assert record.owner == "SM-ND queue"

    def test_system_columns_are_dropped_and_listed(self):
        record = InquiryRecord.model_validate({"case_id": "1", "(Do Not Modify) Case": "guid"})
        assert record.system_columns() == ["(Do Not Modify) Case"]
        assert "(Do Not Modify) Case" not in record.supplied_columns()

    def test_sensitive_values_are_captured_but_never_dumped(self):
        record = InquiryRecord.model_validate({"case_id": "1", "Customer": "Ali Ahmed", "رقم الهوية": "784-1990-1234567-1"})
        assert record.sensitive_values() == ["Ali Ahmed", "784-1990-1234567-1"]
        assert "Ali Ahmed" not in record.model_dump_json()

    def test_unknown_columns_pass_through(self):
        record = InquiryRecord.model_validate({"case_id": "1", "tenant_extra": "v"})
        assert record.extras() == {"tenant_extra": "v"}

    def test_frozen_labels_by_their_adpf_headers(self):
        record = InquiryRecord.model_validate({
            "case_id": "1", "تصنيف إدارة التميز": "لوحة البيانات والشهادات", "ثقة النموذج": "96%",
            "مصدر السبب الجذري": "يدوي - مُراجع", "حزمة السبب الجذري": "x",
        })
        assert record.label_sub_classification == "لوحة البيانات والشهادات"
        assert record.label_confidence == pytest.approx(0.96)
        assert record.label_bundle == "x"

    def test_a_nested_value_is_refused(self):
        with pytest.raises(ValidationError):
            InquiryRecord.model_validate({"case_id": {"id": "1"}})


class TestRequiredInputs:
    def test_a_complete_request_has_nothing_missing(self, analysis_request):
        assert missing_required_fields(analysis_request) == []

    @pytest.mark.parametrize("spec", REQUIRED_COLUMNS, ids=lambda s: s.name)
    def test_a_required_column_absent_everywhere_is_named(self, request_body, spec):
        for record in request_body["records"]:
            record.pop(spec.name, None)
        missing = missing_required_fields(GenerateInquiriesReportRequest.model_validate(request_body))
        assert [m.field for m in missing] == [spec.name]
        message = missing_fields_message(missing)
        assert message.startswith("The following input field(s) were missing or unmapped:")
        assert spec.uid in message

    def test_a_column_present_in_one_record_is_present(self, request_body):
        for record in request_body["records"][1:]:
            record.pop("resolution_text")
        assert missing_required_fields(GenerateInquiriesReportRequest.model_validate(request_body)) == []

    def test_required_settings_and_taxonomy_are_named(self, request_body):
        request_body.pop("settings")
        request_body.pop("reference_lists")
        missing = [m.field for m in missing_required_fields(GenerateInquiriesReportRequest.model_validate(request_body))]
        assert missing == [
            "settings.timeliness_target_working_days", "settings.timeliness_framework",
            "settings.case_type_scope", "reference_lists.taxonomy",
        ]

    def test_every_missing_field_is_named_in_one_message(self, request_body):
        for record in request_body["records"]:
            record.pop("case_id")
            record.pop("opened_datetime")
        request_body["settings"].pop("case_type_scope")
        message = missing_fields_message(missing_required_fields(GenerateInquiriesReportRequest.model_validate(request_body)))
        for name in ("case_id", "opened_datetime", "settings.case_type_scope"):
            assert name in message


class TestSettings:
    def test_documented_defaults(self):
        s = TenantSettings()
        assert (s.llm_threshold, s.review_threshold) == (0.75, 0.65)
        assert s.umbrella_range() == (6, 10)
        assert s.focus_services_count == 2
        assert s.calendar().weekdays == [6, 0, 1, 2, 3]
        assert not s.root_cause_extraction and not s.agent_level_reporting

    def test_review_threshold_cannot_exceed_llm_threshold(self):
        with pytest.raises(ValidationError):
            TenantSettings(llm_threshold=0.6, review_threshold=0.7)

    def test_adpf_single_gate_is_allowed(self):
        assert TenantSettings(llm_threshold=0.9, review_threshold=0.9).review_threshold == 0.9

    @pytest.mark.parametrize("value", ["6-10", "6–10", "3 to 5"])
    def test_umbrella_range_forms(self, value):
        assert TenantSettings(umbrella_count_range=value)

    def test_a_bad_calendar_is_refused(self):
        with pytest.raises(ValidationError):
            TenantSettings(working_calendar="weekdays")

    def test_the_x3_framework_is_the_default_selection(self):
        s = TenantSettings(timeliness_framework="tamm")
        assert [f.id.value for f in s.selected_frameworks()] == ["tamm_contact_centre"]


class TestReferenceLists:
    def test_the_preset_and_a_catalogue_are_both_accepted(self, request_body):
        GenerateInquiriesReportRequest.model_validate(request_body)
        request_body["reference_lists"]["taxonomy"] = {
            "main_services": [{"name_ar": "خدمة", "sub_classifications": [{"name_ar": "فرعية"}]}]
        }
        GenerateInquiriesReportRequest.model_validate(request_body)

    def test_an_unknown_preset_is_refused(self, request_body):
        request_body["reference_lists"]["taxonomy"] = "no_such_preset"
        with pytest.raises(ValidationError):
            GenerateInquiriesReportRequest.model_validate(request_body)


class TestEntity:
    def test_names_are_required(self):
        with pytest.raises(ValidationError):
            EntityInfo(name_ar="أ")

    def test_two_logo_sources_are_rejected(self):
        with pytest.raises(ValidationError):
            EntityInfo(name_ar="أ", name_en="A", logo_path="/x.png", logo_base64="aGk=")

    def test_brand_defaults_are_the_documented_palette(self):
        brand = EntityInfo(name_ar="أ", name_en="A").brand
        assert (brand.primary, brand.secondary) == (NOVEAI_NAVY, NOVEAI_MAGENTA) == ("#201853", "#7E2362")

    def test_a_bad_hex_colour_is_rejected(self):
        with pytest.raises(ValidationError):
            EntityInfo(name_ar="أ", name_en="A", brand={"primary": "navy"})

    def test_bad_base64_raises(self):
        with pytest.raises(ValueError):
            EntityInfo(name_ar="أ", name_en="A", logo_base64="not base64!!").logo_bytes()


class TestRequest:
    def test_an_empty_record_list_is_rejected(self, entity):
        with pytest.raises(ValidationError):
            GenerateInquiriesReportRequest(records=[], entity=entity)

    def test_entity_has_no_default(self, record_dicts):
        with pytest.raises(ValidationError):
            GenerateInquiriesReportRequest(records=[InquiryRecord.model_validate(record_dicts[0])])
