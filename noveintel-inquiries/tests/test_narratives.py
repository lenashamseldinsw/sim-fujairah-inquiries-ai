"""
Layer 3 — the narrative writer's prompts, and the Full Report Prompt §6 checklist
enforced on what it returns.
"""
from __future__ import annotations

import pytest

from noveintel_inquiries.models import InquiriesReportNarratives, SectionNarratives
from noveintel_inquiries.engine.wording import apply_vocabulary, clean_list_item, replace_banned
from noveintel_inquiries.narratives.prompts import narrative_system_prompt, translation_system_prompt
from noveintel_inquiries.narratives.rules import style_block
from noveintel_inquiries.narratives.writer import check_figures, postprocess


def _report(**overrides):
    data = {name: "" for name in InquiriesReportNarratives.model_fields}
    data.update(service_focus_narratives=[], bundle_narratives=[], priority_faqs=[], initiatives=[],
                key_findings=[], recommendations=[], event_narratives=[], friction_points=[])
    data.update(overrides)
    return data


def _sections(**overrides):
    data = {name: "" for name in SectionNarratives.model_fields}
    data["ai_use_cases"] = []
    data.update(overrides)
    return data


class TestSchema:
    def test_the_29_fields_of_the_full_report_prompt(self):
        expected = [
            "intro_statement", "executive_summary", "comparative_analysis", "statistics_intro",
            "monthly_narrative", "main_service_narrative", "sub_service_narrative",
            "transactions_ratio_narrative", "channel_narrative", "recorded_vs_true_narrative",
            "timeliness_narrative", "service_focus_narratives", "root_causes_intro",
            "bundle_distribution_narrative", "bundle_by_service_narrative", "bundle_narratives",
            "top_root_causes_narrative", "timeliness_by_bundle_narrative", "digital_opportunity_narrative",
            "priority_faqs", "roadmap_intro", "initiatives", "key_findings", "recommendations",
            "closing_statement", "methodology_note", "event_narratives", "friction_points", "top_service_short",
        ]
        assert list(InquiriesReportNarratives.model_fields) == expected


class TestPrompts:
    def test_no_entity_is_hard_coded(self):
        prompts = [narrative_system_prompt("ar", root_causes=x8, vocabulary={}) for x8 in (True, False)]
        prompts.append(translation_system_prompt({}))
        for prompt in prompts:
            for name in ("Fujairah", "الفجيرة", "Abu Dhabi Pension", "صندوق أبوظبي"):
                assert name not in prompt

    def test_root_cause_instructions_only_with_x8(self):
        on = narrative_system_prompt("ar", root_causes=True, vocabulary={})
        off = narrative_system_prompt("ar", root_causes=False, vocabulary={})
        assert "ROOT_CAUSE_TOP" in on and "NEAR_OVER_BY_BUNDLE" in on
        assert "NEAR_OVER_BY_BUNDLE" not in off
        assert "اترك فارغة تماماً" in off

    def test_the_report_sections_not_five(self):
        prompt = narrative_system_prompt("ar", root_causes=False, vocabulary={})
        assert "REPORT_SECTIONS" in prompt
        assert "الخمسة" not in prompt

    def test_there_is_no_english_writing_prompt(self):
        with pytest.raises(ValueError, match="translated"):
            narrative_system_prompt("en", root_causes=False, vocabulary={})

    def test_the_translation_prompt_carries_the_english_rules(self):
        prompt = translation_system_prompt({"critical gap": "digital opportunity"})
        assert "glossary" in prompt and "Every number" in prompt
        assert "dominated" in prompt  # the English banned words
        assert "digital opportunity" in prompt

    def test_the_kpi_rule_and_hard_rules_are_carried(self):
        prompt = narrative_system_prompt("ar", root_causes=True, vocabulary={"التحول الرقمي": "التحويل الرقمي"})
        assert "قاعدة صارمة للمؤشرات الرئيسية" in prompt
        assert "قواعد غير قابلة للتفاوض" in prompt
        assert "التحول الرقمي ← التحويل الرقمي" in prompt

    def test_style_block_is_shared(self):
        assert "هيمنت" in style_block("ar", {}) and "dominated" in style_block("en", {})


class TestWording:
    def test_banned_words_are_replaced_keeping_the_conjunction(self):
        text, hits = replace_banned("وهيمنت الخدمة على التواصل وسيطرة القنوات", "ar")
        assert "هيمنت" not in text and "واستحوذت" in text and hits

    def test_english_banned_words(self):
        text, _ = replace_banned("Phone dominated the mix", "en")
        assert "dominat" not in text.lower()

    def test_vocabulary_and_ai(self):
        assert apply_vocabulary("خطة التحول الرقمي وAI", {"التحول الرقمي": "التحويل الرقمي"}, "ar") == "خطة التحويل الرقمي والذكاء الاصطناعي"
        assert apply_vocabulary("an AI rubric", {"rubric": "criteria"}, "en") == "an artificial intelligence criteria"

    @pytest.mark.parametrize("item", ["1. نص", "- نص", "• نص", "(2) نص", "a) نص", "  نص"])
    def test_list_items_lose_leading_symbols(self, item):
        assert clean_list_item(item) == "نص"


class TestFigures:
    def test_figures_in_the_context_pass(self):
        ctx = {"KPI": {"total_cases": 10628, "within_deadline_pct": 97.7}}
        assert check_figures({"t": "بلغ 10,628 حالة بنسبة 97.7%"}, ctx) == []

    def test_an_invented_figure_is_caught(self):
        ctx = {"KPI": {"total_cases": 10628}}
        assert check_figures({"t": "نحو 10,600 حالة"}, ctx) == ["10,600"]

    def test_arabic_indic_digits_are_read(self):
        assert check_figures({"t": "١٠٦٢٨ حالة"}, {"KPI": {"total_cases": 10628}}) == []


class TestPostprocess:
    def test_conditional_fields_are_emptied_without_their_input(self):
        report = _report(comparative_analysis="x", transactions_ratio_narrative="x", digital_opportunity_narrative="x",
                         priority_faqs=["x"], event_narratives=["x"], root_causes_intro="x",
                         bundle_narratives=[{"bundle": "b", "narrative": "x"}])
        out, sections, _, _ = postprocess(report, _sections(department_narrative="x", digital_gaps_narrative="x"),
                                          {"KPI": {}}, "ar", {}, {})
        for field in ("comparative_analysis", "transactions_ratio_narrative", "digital_opportunity_narrative", "root_causes_intro"):
            assert out[field] == ""
        assert out["priority_faqs"] == out["event_narratives"] == out["bundle_narratives"] == []
        assert sections["department_narrative"] == sections["digital_gaps_narrative"] == ""

    def test_counts_come_from_the_reference(self):
        report = _report(initiatives=[
            {"title": "1. رسالة استباقية", "horizon": "immediate", "bundle_ref": "u5", "addresses_cases": 12345, "description": "d"},
            {"title": "بلا مرجع", "horizon": "short", "bundle_ref": "nope", "addresses_cases": 1, "description": "d"},
        ])
        sections = _sections(ai_use_cases=[{"title": "t", "function": "f", "source_ref": "F1", "effort": "low", "impact_cases": 9}])
        out, sec, _, dropped = postprocess(report, sections, {"KPI": {}}, "ar", {},
                                           {"u5": {"cases": 855}, "F1": {"cases": 40}})
        assert [i["addresses_cases"] for i in out["initiatives"]] == [855]
        assert out["initiatives"][0]["title"] == "رسالة استباقية"
        assert sec["ai_use_cases"][0]["impact_cases"] == 40
        assert dropped == 1

    @pytest.mark.parametrize("lang,limit", [("ar", 14), ("en", 16)])
    def test_the_kpi_tile_name_is_cut(self, lang, limit):
        out, *_ = postprocess(_report(top_service_short="إنهاء خدمة المؤمن عليه في الصندوق"), _sections(), {"KPI": {}}, lang, {}, {})
        assert len(out["top_service_short"]) <= limit


class TestIncompleteAnswers:
    def test_a_missing_field_is_retried_then_filled_empty_and_reported(self, monkeypatch):
        from noveintel_inquiries.narratives.writer import write_narratives

        from .fakes import FakeGateway, install

        class Forgetful(FakeGateway):
            def _write_report_narratives(self, user, tool, system):
                data = super()._write_report_narratives(user, tool, system)
                data.pop("closing_statement")
                return data

        gateway = install(monkeypatch, Forgetful())
        context = {"KPI": {"total_cases": 40}}
        outcome = write_narratives(context, root_causes=False, vocabulary={}, sources=[])
        assert outcome.narratives is not None
        assert outcome.incomplete == ["closing_statement"]
        assert outcome.narratives.report.closing_statement == ""
        assert gateway.calls.count("write_report_narratives") == 2

    def test_a_blank_initiative_title_falls_back_to_its_reference(self):
        report = _report(initiatives=[{"title": "", "horizon": "short", "bundle_ref": "F1", "addresses_cases": 0, "description": "d"}])
        out, *_ = postprocess(report, _sections(), {"KPI": {}}, "ar", {}, {"F1": {"cases": 7, "name": "غموض الإجراءات"}})
        assert out["initiatives"][0]["title"] == "معالجة: غموض الإجراءات"


class TestRequiredText:
    def test_fields_with_input_may_not_be_empty(self):
        from noveintel_inquiries.narratives.writer import _tool, must_write

        context = {"KPI": {}, "INITIATIVE_SOURCES": [{"id": "F1"}]}
        fields = must_write(context, InquiriesReportNarratives)
        assert "executive_summary" in fields and "initiatives" in fields
        assert "comparative_analysis" not in fields and "root_causes_intro" not in fields
        props = _tool("t", InquiriesReportNarratives, fields)["input_schema"]["properties"]
        assert props["executive_summary"]["minLength"] == 1
        assert props["initiatives"]["minItems"] == 1
        assert "minLength" not in props["comparative_analysis"]

    def test_a_blank_answer_is_retried_with_the_fields_named(self, monkeypatch):
        from noveintel_inquiries.narratives.writer import write_narratives

        from .fakes import FakeGateway, install

        class BlankFirst(FakeGateway):
            seen: list = []

            def _write_report_narratives(self, user, tool, system):
                self.seen.append(user)
                data = super()._write_report_narratives(user, tool, system)
                if len(self.seen) == 1:
                    return {k: ([] if isinstance(v, list) else "") for k, v in data.items()}
                return data

        gateway = BlankFirst()
        install(monkeypatch, gateway)
        outcome = write_narratives({"KPI": {"total_cases": 40}}, root_causes=False, vocabulary={}, sources=[])
        assert outcome.narratives.report.executive_summary
        assert "تركت إجابتك السابقة هذه الحقول فارغة" in gateway.seen[1]


class TestTranslation:
    def _arabic(self):
        from noveintel_inquiries.models import ReportNarratives

        report = _report(executive_summary="جرى تحليل 40 حالة في الإقرار السنوي.",
                         key_findings=["نتيجة 12%"], closing_statement="ختام",
                         initiatives=[{"title": "مبادرة", "horizon": "short", "bundle_ref": "F1",
                                       "addresses_cases": 7, "description": "وصف"}])
        return ReportNarratives.model_validate({"report": report, "sections": _sections(journey_narrative="رحلة")})

    def test_the_arabic_is_translated_keeping_figures_glossary_and_references(self, monkeypatch):
        from noveintel_inquiries.narratives.writer import translate_narratives

        from .fakes import FakeGateway, install

        seen = []

        class Watch(FakeGateway):
            def create(self, **kwargs):
                seen.append((kwargs["stage"], kwargs["messages"][-1]["content"]))
                return super().create(**kwargs)

        install(monkeypatch, Watch())
        outcome = translate_narratives(
            self._arabic(), context={"KPI": {"total_cases": 40}, "X": [12]},
            glossary={"الإقرار السنوي": "Annual declaration", "ختام": "Closing", "غير مستعمل": "Unused"},
            vocabulary={}, sources=[{"id": "F1", "cases": 7, "name": "Procedures"}],
        )
        report = outcome.narratives.report
        assert "40" in report.executive_summary and report.closing_statement == "Closing"
        assert report.initiatives[0].bundle_ref == "F1" and report.initiatives[0].addresses_cases == 7
        assert outcome.narratives.sections.journey_narrative
        assert not outcome.unverified and not outcome.incomplete
        # Two parts, one call each, on the translation stage; only the glossary terms the text uses.
        assert [stage for stage, _ in seen] == ["translation", "translation"]
        assert all("Unused" not in content for _, content in seen)

    def test_a_failed_translation_returns_no_narrative_rather_than_raising(self, monkeypatch):
        from noveintel_inquiries.narratives.writer import translate_narratives

        from .fakes import FakeGateway, install

        install(monkeypatch, FakeGateway(fail_tools={"write_report_narratives"}))
        outcome = translate_narratives(self._arabic(), context={"KPI": {}}, glossary={}, vocabulary={}, sources=[])
        assert outcome.narratives is None and outcome.error


class TestPartsAndSections:
    def test_each_part_is_handed_on_as_soon_as_it_is_final(self, monkeypatch):
        import threading

        from noveintel_inquiries.narratives.writer import write_narratives

        from .fakes import FakeGateway, install

        release = threading.Event()
        handed: list[str] = []

        class SlowSections(FakeGateway):
            def _write_section_narratives(self, user, tool, system):
                release.wait(5)  # the sections part finishes only after the report part was handed on
                return super()._write_section_narratives(user, tool, system)

        def on_part(outcome):
            handed.append(outcome.part)
            release.set()

        install(monkeypatch, SlowSections())
        outcome = write_narratives({"KPI": {"total_cases": 40}}, root_causes=False, vocabulary={}, sources=[],
                                   on_part=on_part)
        assert handed == ["report", "sections"]
        assert outcome.narratives is not None

    def test_hidden_sections_are_not_asked_for_and_come_back_empty(self, monkeypatch):
        from noveintel_inquiries.models.enums import ReportSection
        from noveintel_inquiries.sections import hidden_fields
        from noveintel_inquiries.narratives.writer import write_narratives

        from .fakes import FakeGateway, install

        seen = []

        class Watch(FakeGateway):
            def create(self, **kwargs):
                seen.append((kwargs["tools"][0]["name"], set(kwargs["tools"][0]["input_schema"]["properties"])))
                return super().create(**kwargs)

        install(monkeypatch, Watch())
        shown = [s for s in ReportSection if s not in (ReportSection.APPENDICES,)]
        context = {"KPI": {"total_cases": 40}, "JOURNEY_MAP": [{"id": "F1"}], "INITIATIVE_SOURCES": [{"id": "F1", "cases": 3}]}
        outcome = write_narratives(context, root_causes=False, vocabulary={}, sources=[{"id": "F1", "cases": 3, "name": "x"}],
                                   hidden=hidden_fields(shown))
        report, sections = outcome.narratives.report, outcome.narratives.sections
        assert report.friction_points == [] and report.methodology_note == ""
        assert sections.ai_use_cases == [] and sections.journey_narrative == ""  # retired: never written
        assert report.executive_summary and report.initiatives
        # Hidden fields are not in the tool at all, so the model spends nothing on them.
        report_tool = next(props for name, props in seen if name == "write_report_narratives")
        assert not {"friction_points", "methodology_note", "event_narratives"} & report_tool
        assert "executive_summary" in report_tool
        assert [name for name, _ in seen] == ["write_report_narratives"]  # the retired part makes no call

    def test_a_part_with_every_section_hidden_makes_no_call(self, monkeypatch):
        from noveintel_inquiries.models.enums import ReportSection
        from noveintel_inquiries.sections import hidden_fields
        from noveintel_inquiries.narratives.writer import write_narratives

        from .fakes import install

        gateway = install(monkeypatch)
        shown = [ReportSection.COVER, ReportSection.EXECUTIVE_SUMMARY, ReportSection.CONCLUSION]
        outcome = write_narratives({"KPI": {"total_cases": 40}}, root_causes=False, vocabulary={}, sources=[],
                                   hidden=hidden_fields(shown))
        assert outcome.narratives is not None
        assert gateway.calls.count("write_section_narratives") == 0

    def test_a_translation_sends_and_asks_for_only_the_written_fields(self, monkeypatch):
        from noveintel_inquiries.narratives.writer import translate_part

        from .fakes import FakeGateway, install

        seen = []

        class Watch(FakeGateway):
            def create(self, **kwargs):
                seen.append((set(kwargs["tools"][0]["input_schema"]["properties"]), kwargs["messages"][-1]["content"]))
                return super().create(**kwargs)

        install(monkeypatch, Watch())
        arabic = _sections(journey_narrative="رحلة المتعامل", digital_gaps_narrative="")
        outcome = translate_part("sections", arabic, context={"KPI": {}}, glossary={}, vocabulary={}, sources=[])
        assert outcome.data["journey_narrative"] and outcome.data["digital_gaps_narrative"] == ""
        props, content = seen[0]
        assert props == {"journey_narrative"} and "digital_gaps_narrative" not in content
        assert len(seen) == 1 and not outcome.incomplete

    def test_a_field_without_input_is_not_asked_for_and_not_reported_missing(self, monkeypatch):
        from noveintel_inquiries.narratives.writer import write_narratives

        from .fakes import FakeGateway, install

        seen = []

        class Watch(FakeGateway):
            def create(self, **kwargs):
                seen.append((kwargs["tools"][0]["name"], set(kwargs["tools"][0]["input_schema"]["properties"])))
                return super().create(**kwargs)

        install(monkeypatch, Watch())
        # No DEPARTMENT in the context: the department narrative has no input.
        outcome = write_narratives({"KPI": {"total_cases": 40}}, root_causes=False, vocabulary={}, sources=[])
        sections_tool = next(props for name, props in seen if name == "write_section_narratives")
        assert "department_narrative" not in sections_tool
        assert "department_narrative" not in outcome.incomplete
        assert outcome.narratives.sections.department_narrative == ""
        assert [name for name, _ in seen].count("write_section_narratives") == 1
