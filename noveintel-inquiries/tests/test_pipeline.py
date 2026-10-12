"""
A whole run, end to end, with the fake gateway — and the Platformisation
Requirements' closing conditions (R1–R12) checked on what it produced.
"""
from __future__ import annotations

import asyncio
import json
import zipfile
from pathlib import Path

import pytest

from noveintel_inquiries.api.models import GenerateInquiriesReportRequest, Language
from noveintel_inquiries.exceptions import MissingInputs
from noveintel_inquiries.pipeline import generate_report, validate_records
from noveintel_inquiries.storage import LocalDirectoryStore

from .conftest import FIXTURES, SETTINGS

IDENTITY = ("Khalid Al Test", "784-1985-7654321-9", "0509876543", "secret.person@example.com")

_TEXTS = [
    ("كيف يمكنني ضم مدة خدمة سابقة", "من خلال هذه الخدمة يمكنكم تقديم طلب ضم مدة الخدمة السابقة عبر الرابط https://x"),
    ("متى موعد صرف المعاش التقاعدي", "نفيدكم بأن صرف المعاش التقاعدي يتم في الأسبوع الأخير من الشهر"),
    ("أرجو إصدار شهادة لمن يهمه الأمر", "تم إصدار الشهادة وإرسالها عبر لوحة المتعامل"),
    ("كيف أجدد الإقرار السنوي", "يرجى تجديد الإقرار السنوي من خلال الإقرار السنوي في المنصة"),
]


def _records(adpf_labelled, n=60, labels=False):
    rows = []
    for i, source in enumerate(adpf_labelled[:n]):
        desc, res = _TEXTS[i % len(_TEXTS)]
        row = {k: v for k, v in source.items() if labels or not k.startswith("label_")}
        row.update(description=desc, resolution_text=res)
        rows.append(row)
    rows[0]["Customer"] = IDENTITY[0]
    rows[0]["description"] = f"اسمي {IDENTITY[0]} هويتي {IDENTITY[1]} رقمي {IDENTITY[2]} بريدي {IDENTITY[3]} وأسأل عن ضم مدة خدمة سابقة"
    rows[1]["closed_datetime"] = "2026-06-30T10:00:00"
    return rows


def _request(adpf_labelled, **overrides):
    body = {
        "records": _records(adpf_labelled),
        "settings": {**SETTINGS, "root_cause_extraction": True, "frameworks": [{"id": "entity_process_kpi"}, {"id": "tamm_contact_centre"}]},
        "reference_lists": {
            "taxonomy": "adpf_codebook_v1",
            "transactions": json.loads((FIXTURES / "adpf_q2_2026_transactions.json").read_text(encoding="utf-8")),
            "faq_catalogue": [{"question_ar": "كيف يمكنني ضم مدة خدمة سابقة", "main_service": "ضم الخدمة السابقة"}],
            "guidebook": {"title": "دليل الخدمات", "pages": 40, "year": "2026",
                          "entries": [{"title": "ضم مدة خدمة سابقة", "text": "يمكن تقديم طلب ضم مدة الخدمة السابقة"}]},
        },
        "history": {"previous_period": {"label_ar": "الربع الأول 2026", "label_en": "Q1 2026", "total_cases": 50,
                                        "within_deadline_pct": 98.8, "digital_share_pct": 16.3, "channel_pct": {"Phone": 83.7}}},
        "entity": {"name_ar": "صندوق أبوظبي للتقاعد", "name_en": "Abu Dhabi Pension Fund", "closing_statement": "رؤية الصندوق"},
        "options": {"include_english": True},
    }
    for key, value in overrides.items():
        body[key] = value
    return GenerateInquiriesReportRequest.model_validate(body)


def _run(request, tmp_path):
    store = LocalDirectoryStore(tmp_path / "store")
    bundle = asyncio.run(generate_report(request, store=store))
    return bundle, store


def _file(store, ref) -> Path:
    return Path(store.root) / ref.container / ref.key if hasattr(store, "root") else None


def _all_text(path: Path) -> str:
    if path.suffix in (".docx", ".xlsx"):
        with zipfile.ZipFile(path) as z:
            return "".join(z.read(n).decode("utf-8", "ignore") for n in z.namelist() if n.endswith(".xml"))
    return path.read_text(encoding="utf-8")


@pytest.fixture
def run(adpf_labelled, gateway, tmp_path):
    bundle, store = _run(_request(adpf_labelled), tmp_path)
    files = {p.name: p for p in (tmp_path / "store").rglob("*") if p.is_file()}
    return bundle, files, gateway


class TestRun:
    def test_every_artefact_in_both_languages(self, run):
        bundle, files, _ = run
        assert set(bundle.documents.report) == {Language.AR, Language.EN}
        assert bundle.documents.workbook and bundle.documents.labels
        assert {"report_ar.docx", "report_en.docx", "cases.xlsx", "labels.json", "report_ar_data.json", "report_en_data.json"} <= set(files)

    def test_all_sections_with_x8(self, run):
        bundle = run[0]
        keys = [s["key"] for s in bundle.report[Language.AR]["sections"]]
        assert keys == ["executive_summary", "methodology", "classification_map", "customer_journey", "digital_gaps",
                        "digital_transformation", "ai_use_cases", "improvement_roadmap", "conclusion", "root_causes", "service_focus"]
        assert bundle.report[Language.AR]["cover"]["id"] == "S0"

    def test_charts_carry_builder_output_ids(self, run):
        charts = {c.key.value: c for c in run[0].charts}
        assert charts["classification_mix"].output_id == "O7"
        assert charts["timeliness_donut"].output_id == "O10"
        assert charts["bundle_bar"].output_id == "O22"
        assert charts["timeliness_donut"].colors == ["#2E8B6B", "#C68A2E", "#B5393F"]

    def test_the_narrative_was_cleaned(self, run):
        n = run[0].narratives[Language.AR].report
        assert "هيمن" not in n.executive_summary
        assert n.key_findings == ["نتيجة أولى", "نتيجة ثانية"]
        assert all(i.addresses_cases != 999999 for i in n.initiatives)

    def test_no_entity_was_hard_coded(self, run):
        _, files, _ = run
        for name in ("report_ar.docx", "report_en.docx"):
            text = _all_text(files[name])
            assert "الفجيرة" not in text and "Fujairah" not in text


class TestPlatformisation:
    def test_r1_methodology_describes_this_run(self, adpf_labelled, gateway, tmp_path):
        """S2 differs between two uploads with different column sets."""
        def fields(bundle):
            s2 = next(s for s in bundle.report[Language.AR]["sections"] if s["key"] == "methodology")
            s23 = next(x for x in s2["subsections"] if x["id"] == "S2.3")
            return [r[next(iter(r))] for r in s23["tables"][0]["rows"]]

        with_channel, _ = _run(_request(adpf_labelled), tmp_path / "a")
        rows = _records(adpf_labelled)
        for r in rows:
            r.pop("channel")
        without, _ = _run(_request(adpf_labelled, records=rows), tmp_path / "b")
        assert fields(with_channel) != fields(without)
        assert any("U8" in f for f in fields(with_channel)) and not any("U8" in f for f in fields(without))

    def test_r2_one_denominator(self, run):
        bundle, files, _ = run
        import openpyxl

        total = bundle.total_cases
        s3 = next(s for s in bundle.report[Language.AR]["sections"] if s["key"] == "classification_map")
        types = next(x for x in s3["subsections"] if x["id"] == "S3.2")["tables"][0]
        assert sum(int(r["العدد"].replace(",", "")) for r in types["rows"]) == total
        wb = openpyxl.load_workbook(files["cases.xlsx"])
        per_type = sum(wb[name].max_row - 1 for name in ("استفسارات", "طلبات خدمة", "شكاوى", "شكر وثناء") if name in wb.sheetnames)
        assert per_type == total == wb["كل الحالات"].max_row - 1
        assert bundle.report[Language.AR]["cover"]["tiles"][0]["value"] == f"{total:,}"

    def test_r3_no_identity_in_any_artefact(self, run):
        bundle, files, _ = run
        texts = [_all_text(p) for p in files.values()] + [bundle.model_dump_json()]
        for value in IDENTITY:
            assert not any(value in t for t in texts), value

    def test_r5_faq_frequency_is_its_evidence(self, run):
        bundle, files, _ = run
        labels = json.loads(files["labels.json"].read_text(encoding="utf-8"))["cases"]
        for faq in bundle.metrics["VALIDATED_FAQS"]:
            assert faq["frequency"] == sum(1 for c in labels if c["faq_id"] == faq["id"])

    def test_r6_s6_tables_equal_the_engine(self, run):
        bundle = run[0]
        s6 = next(s for s in bundle.report[Language.AR]["sections"] if s["key"] == "digital_transformation")
        if bundle.metrics["VALIDATED_FAQS"]:
            table = s6["subsections"][0]["tables"][0]
            assert [int(r["التكرار"]) for r in table["rows"]] == [q["frequency"] for q in bundle.metrics["VALIDATED_FAQS"]]
        notes = bundle.metrics["NOTIFICATION_OPPORTUNITIES"]
        if notes:
            table = next(x for x in s6["subsections"] if x["id"] == "S6.2")["tables"][0]
            assert [int(r[list(r)[-1]].replace(",", "")) for r in table["rows"]] == [n["cases_eliminated"] for n in notes]

    def test_r7_both_totals_labelled(self, run):
        tiles = {t["output_id"]: t["label"] for t in run[0].report[Language.AR]["cover"]["tiles"]}
        assert tiles["O1"] == "إجمالي الحالات" and tiles["O2"] == "الحالات المغلقة"

    def test_r9_comparison_from_history(self, run):
        bundle = run[0]
        assert bundle.metrics["COMPARISON"]["total_cases"]["previous"] == 50
        assert bundle.snapshot.total_cases == bundle.total_cases

    def test_r11_thresholds_and_provenance(self, run):
        bundle, files, _ = run
        assert (bundle.classification.llm_threshold, bundle.classification.review_threshold) == (0.75, 0.65)
        labels = json.loads(files["labels.json"].read_text(encoding="utf-8"))["cases"]
        assert all(c["label_provenance"] for c in labels)

    def test_r12_recorded_vs_actual(self, run):
        assert any(c.key.value == "classification_mix" for c in run[0].charts)


class TestWarningsAndRules:
    def test_umbrellas_await_confirmation(self, run):
        codes = {w.code for w in run[0].warnings}
        assert "umbrellas_pending_confirmation" in codes and "metric_gap" in codes

    def test_english_unavailable_without_catalogue_english(self, adpf_labelled, gateway, tmp_path):
        tax = json.loads((Path(__file__).resolve().parents[1] / "noveintel_inquiries/resources/taxonomy_adpf_codebook_v1.json").read_text(encoding="utf-8"))
        for main in tax["main_services"]:
            main.pop("name_en")
            for sub in main["sub_classifications"]:
                sub.pop("name_en")
        request = _request(adpf_labelled)
        request.reference_lists.taxonomy = type(request.reference_lists).model_validate({"taxonomy": tax}).taxonomy
        bundle, _ = _run(request, tmp_path)
        assert Language.EN not in bundle.documents.report
        assert any(w.code == "english_export_unavailable" for w in bundle.warnings)

    def test_an_unverifiable_figure_is_reported(self, adpf_labelled, monkeypatch, tmp_path):
        from .fakes import FakeGateway, install

        install(monkeypatch, FakeGateway(narrative_figure="98765"))
        bundle, _ = _run(_request(adpf_labelled), tmp_path)
        warning = next(w for w in bundle.warnings if w.code == "narrative_unverified_figures")
        assert "98765" in warning.detail["figures"]

    def test_no_guidebook_omits_the_gap_table_with_a_note(self, adpf_labelled, gateway, tmp_path):
        request = _request(adpf_labelled)
        request.reference_lists.guidebook = None
        bundle, _ = _run(request, tmp_path)
        assert bundle.metrics["GAP_TABLE"] == []
        assert any(w.code == "section_omitted" for w in bundle.warnings)
        s5 = next(s for s in bundle.report[Language.AR]["sections"] if s["key"] == "digital_gaps")
        assert s5.get("notes")

    def test_x8_off_has_no_root_cause_sections(self, adpf_labelled, gateway, tmp_path):
        request = _request(adpf_labelled)
        request.settings.root_cause_extraction = False
        bundle, _ = _run(request, tmp_path)
        keys = [s["key"] for s in bundle.report[Language.AR]["sections"]]
        assert "root_causes" not in keys and "BUNDLE" not in bundle.metrics
        assert bundle.narratives[Language.AR].report.bundle_narratives == []

    def test_frozen_labels_need_no_classification_call(self, adpf_labelled, gateway, tmp_path):
        request = _request(adpf_labelled, records=_records(adpf_labelled, labels=True))
        for record in request.records:
            record.label_contact_type = "استفسار"
        _run(request, tmp_path)
        assert "classify_cases" not in gateway.calls or gateway.calls.count("classify_cases") <= 1

    def test_missing_inputs_are_refused(self, adpf_labelled):
        request = _request(adpf_labelled)
        request.reference_lists.taxonomy = None
        with pytest.raises(MissingInputs) as err:
            asyncio.run(generate_report(request))
        assert "reference_lists.taxonomy" in str(err.value)

    def test_validate_reports_the_parse_log(self, adpf_labelled):
        result = validate_records(_request(adpf_labelled))
        assert result["total_cases"] == 60 and result["parse_log"]["sensitive_columns_excluded"] == ["customer_name"]


class TestBranding:
    def _theme_colour(self, files) -> str:
        with zipfile.ZipFile(files["report_ar.docx"]) as z:
            return z.read("word/document.xml").decode("utf-8")

    def test_the_documented_default_palette(self, run):
        assert "201853" in self._theme_colour(run[1])

    def test_a_tenant_brand_wins(self, adpf_labelled, gateway, tmp_path):
        request = _request(adpf_labelled)
        request.entity.brand.primary = "#0A7A3D"
        _, store = _run(request, tmp_path)
        files = {p.name: p for p in (tmp_path / "store").rglob("*") if p.is_file()}
        xml = self._theme_colour(files)
        assert "0A7A3D" in xml and "201853" not in xml


class TestEnglishByTranslation:
    def test_the_english_report_is_a_translation_of_the_arabic(self, adpf_labelled, monkeypatch, tmp_path):
        from .fakes import FakeGateway, install

        stages = []

        class Watch(FakeGateway):
            def create(self, **kwargs):
                stages.append((kwargs["tools"][0]["name"], kwargs.get("stage"), "arabic" in kwargs["messages"][-1]["content"]))
                return super().create(**kwargs)

        install(monkeypatch, Watch())
        bundle, _ = _run(_request(adpf_labelled), tmp_path)
        writes = sorted(s[1:] for s in stages if s[0].startswith("write_"))
        # Two Arabic writes and two translations of them — no English writing prompt.
        assert writes == [("narratives", False), ("narratives", False), ("translation", True), ("translation", True)]
        assert Language.EN in bundle.documents.report
        assert bundle.narratives[Language.EN].report.executive_summary.startswith("English text")

    def test_a_failed_translation_keeps_the_arabic_report(self, adpf_labelled, monkeypatch, tmp_path):
        from .fakes import FakeGateway, install

        class NoTranslation(FakeGateway):
            def create(self, **kwargs):
                if kwargs.get("stage") == "translation":
                    raise RuntimeError("fake translation failure")
                return super().create(**kwargs)

        install(monkeypatch, NoTranslation())
        bundle, _ = _run(_request(adpf_labelled), tmp_path)
        assert Language.AR in bundle.documents.report and Language.EN not in bundle.documents.report
        assert any(w.code == "english_export_unavailable" for w in bundle.warnings)

    def test_the_glossary_carries_the_names_the_report_prints(self):
        from noveintel_inquiries.api.models import EntityInfo, Period
        from noveintel_inquiries.engine.compute import Umbrella
        from noveintel_inquiries.engine.localize import Localizer
        from noveintel_inquiries.engine.taxonomy import load_taxonomy
        from noveintel_inquiries.pipeline import _glossary

        tax = load_taxonomy("adpf_codebook_v1")
        umbrellas = [Umbrella(id="u1", name_ar="مواعيد الصرف", name_en="Payment dates")]
        period = Period(granularity="quarterly", index=2, year=2026, start="2026-04-01", end="2026-06-30", label_ar="الربع الثاني 2026", label_en="Q2 2026")
        entity = EntityInfo(name_ar="جهة", name_en="Entity")
        metrics = {"JOURNEY_MAP": [{"name_ar": "غموض", "name_en": "Ambiguity"}]}
        g = _glossary(metrics, tax, umbrellas, {"سبب": "Cause"}, entity, period,
                      Localizer("ar", tax, umbrellas, {}), Localizer("en", tax, umbrellas, {}))
        assert g["الإقرار السنوي"] == tax.en("الإقرار السنوي")
        assert g["مواعيد الصرف"] == "Payment dates" and g["غموض"] == "Ambiguity" and g["سبب"] == "Cause"
        assert g["الربع الثاني 2026"] == "Q2 2026" and g["جهة"] == "Entity"
        assert g["آلي - موثوق"] == "Auto — keywords or duplicate" and g["ضمن المهلة"] == "Within deadline"


class TestSectionSelection:
    def _keys(self, bundle, lang=Language.AR):
        return [s["key"] for s in bundle.report[lang]["sections"]]

    def test_every_section_by_default(self, adpf_labelled, gateway, tmp_path):
        bundle, _ = _run(_request(adpf_labelled), tmp_path)
        keys = self._keys(bundle)
        for key in ("executive_summary", "customer_journey", "digital_gaps", "ai_use_cases", "root_causes"):
            assert key in keys

    def test_hidden_sections_are_left_out_in_both_languages(self, adpf_labelled, gateway, tmp_path):
        request = _request(adpf_labelled, options={"include_english": True,
                                                   "sections": ["S1", "S2", "S3", "improvement_roadmap", "S9", "S10"]})
        bundle, _ = _run(request, tmp_path)
        expected = ["executive_summary", "methodology", "classification_map", "improvement_roadmap", "conclusion", "root_causes"]
        assert self._keys(bundle) == expected and self._keys(bundle, Language.EN) == expected
        report = bundle.narratives[Language.AR].report
        assert report.friction_points == [] and report.service_focus_narratives == []
        assert bundle.narratives[Language.AR].sections.ai_use_cases == []
        # The roadmap still draws on the journey and the gaps (decision #6), so they ran.
        assert bundle.metrics["JOURNEY_MAP"]

    def test_analysis_no_shown_section_needs_is_skipped(self, adpf_labelled, gateway, tmp_path):
        request = _request(adpf_labelled, options={"sections": ["S2", "S3"]})
        bundle, _ = _run(request, tmp_path)
        assert not {"map_journey", "propose_faqs", "assess_guidebook"} & set(gateway.calls)
        assert bundle.metrics["JOURNEY_MAP"] == [] and bundle.metrics["VALIDATED_FAQS"] == []

    def test_root_cause_sections_without_x8_are_omitted_with_a_warning(self, adpf_labelled, gateway, tmp_path):
        request = _request(adpf_labelled, options={"sections": ["S1", "S10", "S11"]})
        request.settings.root_cause_extraction = False
        bundle, _ = _run(request, tmp_path)
        assert self._keys(bundle) == ["executive_summary"]
        warning = next(w for w in bundle.warnings if w.code == "section_omitted" and "sections" in (w.detail or {}))
        assert warning.detail["sections"] == ["S10", "S11"]

    def test_unknown_section_is_refused(self):
        from pydantic import ValidationError

        from noveintel_inquiries.api.models.requests import AnalysisOptions

        with pytest.raises(ValidationError):
            AnalysisOptions(sections=["S12"])
