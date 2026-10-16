"""
Layer 1 — the parser and ``compute()``.

The engine is pinned against the ADPF Q2 2026 labelled master: the worked example in
the Full Report Prompt §3 is "the real Q2 2026 figures recomputed from the labelled
master", so ``compute()`` must reproduce them exactly (Prerequisites §8, computation
correctness — exact).
"""
from __future__ import annotations

import json
from collections import defaultdict

import pytest

from noveintel_inquiries.models import InquiryRecord, ReferenceLists, TenantSettings, TransactionRow
from noveintel_inquiries.models.columns import COLUMNS, LABEL_COLUMNS, SENSITIVE_COLUMNS
from noveintel_inquiries.classification.labels import UmbrellaRegistry, apply_frozen
from noveintel_inquiries.engine.compute import ComputeInputs, compute, pct
from noveintel_inquiries.engine.frameworks import evaluate_frameworks
from noveintel_inquiries.engine.parse import normalise_sla, parse_records, recorded_type_of, split_bilingual
from noveintel_inquiries.engine.period import period_from_datetimes
from noveintel_inquiries.engine.redact import redact
from noveintel_inquiries.engine.taxonomy import load_taxonomy
from noveintel_inquiries.engine.wording import TYPE_TO_CONTACT

from .conftest import FIXTURES, SETTINGS


def _settings(**extra) -> TenantSettings:
    return TenantSettings(**{**SETTINGS, **extra})


class TestRegistry:
    def test_no_two_columns_share_a_folded_spelling(self):
        seen = defaultdict(set)
        for spec in COLUMNS + LABEL_COLUMNS + SENSITIVE_COLUMNS:
            for folded in spec.folded:
                seen[folded].add(spec.name)
        assert {k: v for k, v in seen.items() if len(v) > 1} == {}


class TestValueReaders:
    @pytest.mark.parametrize("raw,expected", [
        ("🟢 Green", "within"), ("🟡 Amber", "near"), ("🔴 Red", "over"), ("نعم", "within"),
        ("لا", "over"), (True, "within"), (False, "over"), ("", None), ("Closed", None),
    ])
    def test_sla_normalisation(self, raw, expected):
        assert normalise_sla(raw) == expected

    def test_closed_status_is_not_on_time(self):
        assert normalise_sla("مغلق", strict=True) is None

    @pytest.mark.parametrize("raw,expected", [
        ("Information - معلومات", "inquiry"), ("Request for Service - طلب الخدمة", "service_request"),
        ("استفسار", "inquiry"), ("طلب", "service_request"), ("شكوى", "complaint"),
        ("شكر و ثناء", "compliment"), ("Incident - حادث", "incident"), ("", None),
    ])
    def test_recorded_types(self, raw, expected):
        assert recorded_type_of(raw) == expected

    def test_bilingual_split(self):
        assert split_bilingual("Gratuity payment - صرف المكافآت") == ("Gratuity payment", "صرف المكافآت")
        assert split_bilingual("هاتف") == ("", "هاتف")


class TestRedaction:
    def test_every_placeholder(self):
        text = redact(
            "متابعة 260608-7869231 بتاريخ 12/05/2026 بمبلغ 5,000 درهم رقمي 0501234567 هويتي 784-1990-1234567-1 "
            "اسمي محمد أحمد علي\nاسم جهة العمل: شركة الاختبار",
            known_values=["محمد أحمد علي"],
        )
        for placeholder in ("[رقم التتبع]", "[تاريخ]", "[مبلغ]", "[بيانات اتصال]", "[الهوية الإماراتية]", "[الاسم]", "[جهة العمل]"):
            assert placeholder in text
        for leaked in ("7869231", "0501234567", "1234567", "محمد", "شركة الاختبار"):
            assert leaked not in text

    def test_links_survive(self):
        assert "https://tamm.abudhabi/x?a=1" in redact("الرابط https://tamm.abudhabi/x?a=1")


class TestParser:
    def test_artefacts_duplicates_scope_and_identity(self):
        rows = [
            {"case_id": "1", "case_type": "Information - معلومات", "Customer": "Ali Ahmed", "description": "Ali Ahmed asks"},
            {"case_id": "1", "case_type": "Information - معلومات"},
            {"case_id": None, "case_type": "Information - معلومات"},
            {"case_id": "2", "case_type": "Complaint - شكوى"},
            {"case_id": "3", "case_type": ""},
            {"case_id": "4", "case_type": "Request for Service - طلب الخدمة", "(Do Not Modify) Case": "g"},
        ]
        run = parse_records([InquiryRecord.model_validate(r) for r in rows], _settings())
        log = run.log
        assert (log.records_received, log.artefact_rows_dropped, log.duplicates_removed) == (6, 1, 1)
        assert log.scope_excluded == {"complaint": 1}
        assert log.unspecified_type_kept == 1
        assert [c.case_id for c in run.cases] == ["1", "3", "4"]
        assert log.sensitive_columns_excluded == ["customer_name"]
        assert log.system_columns_dropped == ["(Do Not Modify) Case"]
        assert "Ali Ahmed" not in run.cases[0].description

    def test_all_types_scope_keeps_complaints(self):
        rows = [{"case_id": "2", "case_type": "شكوى"}]
        run = parse_records([InquiryRecord.model_validate(r) for r in rows], _settings(case_type_scope="all_recorded_types"))
        assert len(run.cases) == 1

    def test_present_but_empty_is_logged(self):
        rows = [{"case_id": "1", "case_type": "استفسار", "channel": None}, {"case_id": "2", "case_type": "استفسار", "channel": ""}]
        log = parse_records([InquiryRecord.model_validate(r) for r in rows], _settings()).log
        assert log.columns_present_but_empty == ["channel"]

    def test_multi_entity_exports_are_scoped(self):
        rows = [{"case_id": "1", "case_type": "استفسار", "entity": "Abu Dhabi Pension Fund - صندوق أبوظبي للتقاعد"},
                {"case_id": "2", "case_type": "استفسار", "entity": "Other Entity"}]
        run = parse_records([InquiryRecord.model_validate(r) for r in rows], _settings(), ("صندوق أبوظبي للتقاعد", "Abu Dhabi Pension Fund"))
        assert [c.case_id for c in run.cases] == ["1"] and run.log.entity_rows_excluded == 1


@pytest.fixture(scope="module")
def adpf_metrics(adpf_labelled):
    """compute() over the labelled master, D1 taken from the recorded type.

    The master carries O, N, P, confidence, provenance and bundle but no actual contact
    type, so D1 is set from the recorded type here — which makes the reclassification
    rate zero by construction and leaves every other figure untouched.
    """
    settings = _settings(root_cause_extraction=True, frameworks=[{"id": "entity_process_kpi"}, {"id": "tamm_contact_centre"}])
    run = parse_records([InquiryRecord.model_validate(r) for r in adpf_labelled], settings)
    tax = load_taxonomy("adpf_codebook_v1")
    registry = UmbrellaRegistry([])
    apply_frozen(run.cases, tax, registry)
    for case in run.cases:
        case.contact_type = TYPE_TO_CONTACT[case.recorded_type]
        case.true_type = case.recorded_type
    transactions = [TransactionRow(**r) for r in json.loads((FIXTURES / "adpf_q2_2026_transactions.json").read_text(encoding="utf-8"))]
    period = period_from_datetimes([c.opened for c in run.cases])
    frameworks = evaluate_frameworks(run.cases, settings, set(run.log.columns_mapped))
    metrics = compute(ComputeInputs(
        cases=run.cases, settings=settings, taxonomy=tax, period=period, parse_log=run.log,
        reference=ReferenceLists(taxonomy="adpf_codebook_v1", transactions=transactions),
        umbrellas=registry.umbrellas, frameworks=frameworks,
    ))
    return metrics, run.cases


class TestWorkedExample:
    """Full Report Prompt §3 — the real Q2 2026 figures."""

    def test_kpi(self, adpf_metrics):
        kpi = adpf_metrics[0]["KPI"]
        assert kpi["total_cases"] == 10630
        assert kpi["classified"] == 10628
        assert kpi["classified_pct"] == 99.98
        assert (kpi["main_services"], kpi["sub_classes"], kpi["bundles"]) == (13, 25, 8)
        assert kpi["within_deadline_pct"] == 97.7
        assert kpi["digital_share_pct"] == 16.6
        assert kpi["top_service"] == {"name": "إنهاء خدمة المؤمن عليه", "pct": 33.6, "count": 3569}
        assert kpi["report_period"] == "الربع الثاني 2026"
        assert kpi["period_date_range"] == "01/04/2026 – 30/06/2026"

    def test_monthly(self, adpf_metrics):
        monthly = adpf_metrics[0]["MONTHLY"]
        assert monthly["labels"] == ["أبريل", "مايو", "يونيو"]
        assert monthly["values"] == [3469, 3121, 4040]
        assert monthly["pct"] == [32.6, 29.4, 38.0]

    def test_channels(self, adpf_metrics):
        channel = adpf_metrics[0]["CHANNEL"]
        assert channel["values"] == [8868, 1180, 462, 101, 17, 2]
        assert channel["pct"] == [83.4, 11.1, 4.3, 1.0, 0.2, 0.0]

    def test_recorded_types(self, adpf_metrics):
        assert adpf_metrics[0]["CASE_TYPE_RECORDED"]["values"] == [5329, 5301]

    def test_main_services(self, adpf_metrics):
        main = adpf_metrics[0]["MAIN_SERVICE"]
        assert main["values"][:4] == [3569, 2573, 1136, 733]
        assert main["pct"][:4] == [33.6, 24.2, 10.7, 6.9]
        assert main["labels"][-1] == "غير مصنَّف" and main["values"][-1] == 2

    def test_bundles(self, adpf_metrics):
        bundle = adpf_metrics[0]["BUNDLE"]
        assert bundle["values"] == [5294, 1720, 991, 984, 855, 438, 279, 67]
        assert bundle["pct"] == [49.8, 16.2, 9.3, 9.3, 8.0, 4.1, 2.6, 0.6]

    def test_root_cause_top(self, adpf_metrics):
        top = adpf_metrics[0]["ROOT_CAUSE_TOP"]
        assert top["values"][:5] == [168, 123, 117, 114, 109]
        assert top["labels"][0] == "الاستفسار عن موعد صرف المعاش التقاعدي"

    def test_bundle_by_service(self, adpf_metrics):
        row = adpf_metrics[0]["BUNDLE_BY_SERVICE"]["counts"]["إنهاء خدمة المؤمن عليه"]
        assert row["طلب إجراءات ومتطلبات الخدمة"] == 1239
        assert row["شروط الاستحقاق والأهلية"] == 833

    def test_service_focus(self, adpf_metrics):
        first = adpf_metrics[0]["SERVICE_FOCUS"][0]
        assert first["count"] == 3569 and first["share_pct"] == 33.6
        assert first["months"] == {"أبريل": 1092, "مايو": 1105, "يونيو": 1372}
        assert first["peak_month"] == "يونيو"
        assert first["within_deadline_pct"] == 98.3
        assert first["sub_classes"]["values"] == [1911, 1179, 401, 78]
        assert first["bundles"]["pct"] == [34.7, 23.3, 17.1, 10.3, 7.9]
        assert (first["phone_pct"], first["livechat_pct"]) == (85.4, 9.1)

    def test_timeliness(self, adpf_metrics):
        t = adpf_metrics[0]["TIMELINESS"]
        assert (t["within"], t["near"], t["over"]) == (9527, 855, 248)
        assert (t["within_pct"], t["near_pct"], t["over_pct"]) == (89.6, 8.0, 2.3)
        assert t["within_deadline_pct"] == 97.7 and t["breached_pct"] == 2.3
        assert t["target"] == "يومان عمل"

    def test_near_over_by_bundle(self, adpf_metrics):
        no = adpf_metrics[0]["NEAR_OVER_BY_BUNDLE"]
        assert no["labels"][:2] == ["تعذر إتمام خدمة رقمية أو خلل تقني", "بيانات غير محدثة أو معاملة لم تُقدَّم"]
        assert no["pct"][:5] == [18.3, 13.0, 12.3, 12.3, 12.1]

    def test_classification_quality(self, adpf_metrics):
        cq = adpf_metrics[0]["CLASSIFICATION_QUALITY"]
        assert cq["provenance"] == {"يدوي - مُراجع": 6630, "آلي - موثوق": 3412, "آلي - مُصحّح": 586}
        assert cq["provenance_pct"] == [62.4, 32.1, 5.5]
        assert cq["mean_confidence"] == 0.735

    def test_events(self, adpf_metrics):
        first = adpf_metrics[0]["EVENTS"][0]
        assert (first["cluster"], first["month"], first["from"], first["to"]) == ("متابعة طلب أو معاملة قائمة", "يونيو", 225, 442)

    def test_transactions_use_the_rows_sent(self, adpf_metrics):
        """The delivered report's 141,135 denominator is open item 2: with every row
        counted the ratio is 19.2; the per-sub-service join matches the report."""
        tx = adpf_metrics[0]["INQ_PER_100_TX"]
        assert tx["transactions_total"] == 55492
        assert tx["overall"] == 19.2
        sub = dict(zip(tx["by_sub_service"]["labels"], tx["by_sub_service"]["per_100"]))
        assert sub["صرف المعاشات التقاعدية"] == 827.3

    def test_recorded_vs_true_with_the_learned_crosswalk(self, adpf_metrics):
        """Open item 4: the report's 71.7% basis is undefined; the learned crosswalk gives 79.3%."""
        assert adpf_metrics[0]["RECORDED_VS_TRUE"]["match_pct"] == 79.3


class TestSingleDenominator:
    """R2 — one case set for every section."""

    def test_every_distribution_over_s_sums_to_s(self, adpf_metrics):
        m, cases = adpf_metrics
        total = m["KPI"]["total_cases"]
        assert sum(m["ACTUAL_TYPE"]["values"]) == total
        assert sum(m["MONTHLY"]["values"]) + m["MONTHLY"]["undated"] == total
        assert sum(m["CHANNEL"]["values"]) == total
        assert sum(m["CASE_TYPE_RECORDED"]["values"]) == total
        t = m["TIMELINESS"]
        assert t["within"] + t["near"] + t["over"] + t["unspecified"] == total
        assert sum(m["MAIN_SERVICE"]["values"]) == total == len(cases)


class TestFrameworks:
    def test_registry_on_the_adpf_export(self, adpf_metrics):
        by_key = {i["key"]: i for i in adpf_metrics[0]["FRAMEWORKS"]}
        assert by_key["timeliness"]["status"] == "computed" and by_key["timeliness"]["value_pct"] == 97.7
        assert by_key["resolution"]["status"] == "computed"
        for key in ("acceptance", "classification", "accuracy", "fcr"):
            assert by_key[key]["status"] == "not_computable"
            assert by_key[key]["value_pct"] is None
            assert by_key[key]["recommendation_ar"].startswith("تفعيل حقل")

    def test_working_time(self):
        from datetime import datetime

        from noveintel_inquiries.engine.frameworks import working_seconds

        cal = TenantSettings().calendar()
        # Thursday 15:00 → Sunday 08:30: 30 minutes Thursday + 1 hour Sunday.
        seconds = working_seconds(datetime(2026, 6, 4, 15, 0), datetime(2026, 6, 7, 8, 30), cal, set())
        assert seconds == 90 * 60

    def test_timestamps_compute_tamm_acceptance(self):
        rows = [
            {"case_id": "1", "case_type": "استفسار", "opened_datetime": "2026-06-07T08:00:00", "accepted_datetime": "2026-06-07T09:00:00"},
            {"case_id": "2", "case_type": "استفسار", "opened_datetime": "2026-06-07T08:00:00", "accepted_datetime": "2026-06-07T12:00:00"},
        ]
        settings = _settings(frameworks=[{"id": "tamm_contact_centre"}])
        run = parse_records([InquiryRecord.model_validate(r) for r in rows], settings)
        acceptance = next(i for i in evaluate_frameworks(run.cases, settings, set(run.log.columns_mapped)) if i["key"] == "acceptance")
        assert acceptance["status"] == "computed" and acceptance["value_pct"] == 50.0


class TestPct:
    def test_half_up(self):
        assert pct(1, 8) == 12.5 and pct(2, 3) == 66.7

    def test_never_rounds_a_shortfall_to_100(self):
        assert pct(10628, 10630) == 99.98
