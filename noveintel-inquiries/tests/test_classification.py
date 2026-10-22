"""
Layer 2 — the classifier: codebook rules, routing, frozen labels, provenance, the
root-cause codebook and umbrella discovery. Model calls go to the fake gateway.
"""
from __future__ import annotations

import pytest

from noveintel_inquiries.models import InquiryRecord, TenantSettings
from noveintel_inquiries.classification.classify import classify_cases, group_umbrellas
from noveintel_inquiries.classification.rootcause import check_root_cause
from noveintel_inquiries.classification.rules import classify_by_rules
from noveintel_inquiries.engine.compute import Umbrella
from noveintel_inquiries.engine.parse import parse_records
from noveintel_inquiries.engine.taxonomy import load_taxonomy

from .conftest import SETTINGS

TAX = load_taxonomy("adpf_codebook_v1")


def _cases(rows, **settings):
    s = TenantSettings(**{**SETTINGS, **settings})
    return parse_records([InquiryRecord.model_validate({"case_type": "Information - معلومات", **r}) for r in rows], s).cases, s


class TestRules:
    def test_a_link_or_explanation_is_an_inquiry(self):
        case = _cases([{"case_id": "1", "description": "كيف أضم مدة خدمة سابقة",
                        "resolution_text": "من خلال الخدمة يمكنكم تقديم الطلب عبر الرابط https://x"}])[0][0]
        assert classify_by_rules(case, TAX).contact_type == "استفسار"

    def test_an_executed_action_is_a_service_request(self):
        case = _cases([{"case_id": "1", "description": "أرجو تعديل بيانات الحساب المصرفي",
                        "resolution_text": "تم تعديل بيانات الحساب المصرفي وتم تحديث الملف"}])[0][0]
        assert classify_by_rules(case, TAX).contact_type == "طلب خدمة"

    def test_resolution_signals_choose_the_service(self):
        case = _cases([{"case_id": "1", "description": "استفسار",
                        "resolution_text": "يرجى تجديد الإقرار السنوي من خلال الإقرار السنوي في المنصة لتجنب إيقاف المعاش"}])[0][0]
        result = classify_by_rules(case, TAX)
        assert result.main_service == "الإقرار السنوي" and result.sub_classification == "الإقرار السنوي"

    def test_no_signal_falls_to_the_catch_all_with_low_confidence(self):
        case = _cases([{"case_id": "1", "description": "مرحبا", "resolution_text": "تم"}])[0][0]
        result = classify_by_rules(case, TAX)
        assert result.main_service == "أخرى" and result.confidence < 0.5

    def test_a_hint_naming_a_taxonomy_entry_settles_the_service(self):
        case = _cases([{"case_id": "1", "sub_classification_hint": "ضم مدة خدمة سابقة", "description": "x",
                        "resolution_text": "من خلال الرابط"}])[0][0]
        assert classify_by_rules(case, TAX).main_service == "ضم الخدمة السابقة"


class TestRootCauseCodebook:
    def test_a_good_cause_passes(self):
        check = check_root_cause("الاستفسار عن موعد صرف المعاش التقاعدي لشهر يونيو",
                                 main_service="إنهاء خدمة المؤمن عليه", sub="صرف المعاشات التقاعدية", tax=TAX)
        assert check.violation is None

    def test_case_specifics_are_struck_out(self):
        check = check_root_cause("متابعة حالة سابقة بخصوص تعذر إيداع مبلغ الضم 260608-7869231 لدى البنك",
                                 main_service="ضم الخدمة السابقة", sub="ضم مدة خدمة سابقة", tax=TAX)
        assert check.fixed and "7869231" not in check.text

    @pytest.mark.parametrize("text,rule", [
        ("متابعة", "R1"), ("متابعة حالة سابقة", "R1"),
        ("الاستفسار " * 16, "R1"),
    ])
    def test_breaches_are_named(self, text, rule):
        check = check_root_cause(text, main_service="أخرى", sub="أخرى", tax=TAX)
        assert check.violation and check.violation.startswith(rule)

    def test_a_cause_naming_another_service_breaks_r3(self):
        check = check_root_cause("الاستفسار عن كيفية التواصل بخصوص تسجيل المؤمن عليه في الصندوق",
                                 main_service="دعم جهات العمل", sub="متابعة خدمات جهات العمل", tax=TAX)
        assert check.violation and check.violation.startswith("R3")


class TestRouting:
    def test_rules_below_x5_go_to_the_model_and_provenance_is_set_by_the_pipeline(self, gateway):
        cases, s = _cases([
            {"case_id": "rule", "description": "تجديد الإقرار السنوي",
             "resolution_text": "يرجى تجديد الإقرار السنوي من خلال الإقرار السنوي في المنصة الإقرار السنوي"},
            {"case_id": "model", "description": "مرحبا", "resolution_text": "تم"},
        ])
        result = classify_cases(cases, TAX, s, entity_name="E", carried_umbrellas=[])
        by_id = {c.case_id: c for c in cases}
        assert by_id["rule"].provenance == "auto"  # «آلي - موثوق»: settled by the keywords
        assert by_id["model"].provenance == "llm"
        assert result.routed_to_model == 1

    def test_below_x6_goes_to_the_deep_review(self, gateway):
        cases, s = _cases([{"case_id": "1", "description": "review-me مرحبا", "resolution_text": "تم"}])
        result = classify_cases(cases, TAX, s, entity_name="E", carried_umbrellas=[])
        case = cases[0]
        assert case.deep_reviewed and case.provenance == "deep_review"
        assert case.confidence == 0.92 and not case.low_confidence
        assert result.deep_reviewed == 1 and result.low_confidence == 0
        assert gateway.calls == ["classify_cases", "classify_cases"]

    def test_the_deep_review_uses_the_reasoning_tier_and_its_own_stage(self, monkeypatch):
        from .fakes import FakeGateway, install

        seen = []

        class Watch(FakeGateway):
            def create(self, **kwargs):
                seen.append((kwargs.get("model"), kwargs.get("stage"), "Deep review" in (kwargs.get("system") or ""),
                             kwargs.get("reasoning_effort")))
                return super().create(**kwargs)

        install(monkeypatch, Watch())
        cases, s = _cases([{"case_id": "1", "description": "review-me مرحبا", "resolution_text": "تم"}])
        classify_cases(cases, TAX, s, entity_name="E", carried_umbrellas=[])
        from noveintel_inquiries.core42 import DEEP_MODEL, FAST_MODEL

        assert seen[0] == (FAST_MODEL, "classification", False, None)  # the first pass does not reason
        assert seen[-1] == (DEEP_MODEL, "deep_review", True, "low")

    def test_still_low_after_the_deep_review_is_flagged_not_queued(self, gateway):
        cases, s = _cases([{"case_id": "1", "description": "still-low مرحبا", "resolution_text": "تم"}])
        result = classify_cases(cases, TAX, s, entity_name="E", carried_umbrellas=[])
        assert cases[0].deep_reviewed and cases[0].low_confidence
        assert cases[0].main_service  # counted with its best labels
        assert result.low_confidence == 1

    def test_raising_x6_routes_more_to_the_deep_review_without_code(self, gateway):
        cases, s = _cases([{"case_id": "1", "description": "مرحبا", "resolution_text": "تم"}], llm_threshold=0.9, review_threshold=0.9)
        classify_cases(cases, TAX, s, entity_name="E", carried_umbrellas=[])
        assert cases[0].deep_reviewed  # first-pass confidence 0.88 < X6 0.9
        assert not cases[0].low_confidence  # the deep review answered 0.92

    def test_a_failed_model_keeps_rule_labels_and_flags_low_confidence(self, monkeypatch):
        from .fakes import FakeGateway, install

        install(monkeypatch, FakeGateway(fail_tools={"classify_cases"}))
        cases, s = _cases([{"case_id": "1", "description": "مرحبا", "resolution_text": "تم"}])
        result = classify_cases(cases, TAX, s, entity_name="E", carried_umbrellas=[])
        assert cases[0].low_confidence and cases[0].provenance == "auto" and cases[0].main_service
        assert not cases[0].deep_reviewed
        assert result.model_unavailable == 1

    def test_duplicates_are_classified_once_and_copied(self, gateway):
        text = "أرغب في معرفة موعد صرف المعاش لهذا الشهر"
        cases, s = _cases([
            {"case_id": "a", "description": text, "resolution_text": "تم"},
            {"case_id": "b", "description": text, "resolution_text": "تم"},
            {"case_id": "c", "description": "  " + text + " ", "resolution_text": "تم"},
        ])
        result = classify_cases(cases, TAX, s, entity_name="E", carried_umbrellas=[])
        by_id = {c.case_id: c for c in cases}
        assert result.duplicates_reused == 2 and result.routed_to_model == 1
        for copy in ("b", "c"):
            assert by_id[copy].duplicate_of == "a" and by_id[copy].provenance == "auto"
            assert by_id[copy].main_service == by_id["a"].main_service
            assert by_id[copy].sub_classification == by_id["a"].sub_classification

    def test_short_descriptions_are_not_treated_as_duplicates(self, gateway):
        cases, s = _cases([{"case_id": str(i), "description": "مرحبا", "resolution_text": "تم"} for i in range(2)])
        result = classify_cases(cases, TAX, s, entity_name="E", carried_umbrellas=[])
        assert result.duplicates_reused == 0 and result.routed_to_model == 2

    def test_frozen_labels_are_never_overwritten(self, gateway):
        cases, s = _cases([{
            "case_id": "1", "description": "مرحبا", "resolution_text": "تم",
            "label_main_service": "الإقرار السنوي", "label_sub_classification": "الإقرار السنوي",
            "label_contact_type": "طلب خدمة", "label_provenance": "يدوي - مُراجع",
        }])
        classify_cases(cases, TAX, s, entity_name="E", carried_umbrellas=[])
        case = cases[0]
        assert (case.main_service, case.contact_type, case.provenance) == ("الإقرار السنوي", "طلب خدمة", "deep_review")
        assert not case.low_confidence
        assert gateway.calls == []

    def test_frozen_service_without_contact_type_only_fills_the_type(self, gateway):
        cases, s = _cases([{"case_id": "1", "description": "مرحبا", "resolution_text": "تم",
                            "label_main_service": "الإقرار السنوي", "label_sub_classification": "الإقرار السنوي"}])
        classify_cases(cases, TAX, s, entity_name="E", carried_umbrellas=[])
        assert cases[0].main_service == "الإقرار السنوي" and cases[0].contact_type == "استفسار"


class TestRootCausesAndUmbrellas:
    def test_x8_writes_a_cause_per_case_and_discovers_an_umbrella(self, gateway):
        cases, s = _cases([{"case_id": str(i), "description": "مرحبا", "resolution_text": "تم"} for i in range(3)],
                          root_cause_extraction=True)
        result = classify_cases(cases, TAX, s, entity_name="E", carried_umbrellas=[])
        assert all(c.root_cause for c in cases)
        assert result.umbrellas == []  # discovery is its own step, run beside the analysis
        group_umbrellas(cases, result, TAX, s)
        assert len(result.umbrellas) == 1 and result.umbrellas[0].new
        assert {c.bundle for c in cases} == {result.umbrellas[0].id}

    def test_carried_umbrellas_are_reused_and_kept_at_zero(self, gateway):
        carried = [Umbrella(id="u5", name_ar="مواعيد الصرف", name_en="Payment dates", carried=True),
                   Umbrella(id="u9", name_ar="حزمة بلا حالات", name_en="Empty", carried=True)]
        cases, s = _cases([{"case_id": "1", "description": "مرحبا", "resolution_text": "تم"}], root_cause_extraction=True)
        result = classify_cases(cases, TAX, s, entity_name="E", carried_umbrellas=carried)
        group_umbrellas(cases, result, TAX, s)
        assert [u.id for u in result.umbrellas] == ["u5", "u9"]
        assert not any(u.new for u in result.umbrellas)
        assert cases[0].bundle == "u5"

    def test_a_cause_breaking_the_codebook_is_rewritten_and_marked_corrected(self, gateway):
        cases, s = _cases([{"case_id": "1", "description": "short-cause مرحبا", "resolution_text": "تم"}], root_cause_extraction=True)
        result = classify_cases(cases, TAX, s, entity_name="E", carried_umbrellas=[])
        assert result.root_cause_fixes == 1
        assert cases[0].provenance == "auto_corrected"
        assert gateway.calls.count("classify_cases") == 2

    def test_a_cause_still_breaking_after_the_rewrite_goes_to_the_deep_review(self, monkeypatch):
        from .fakes import FakeGateway, install

        class Stubborn(FakeGateway):
            def _classify_cases(self, user, tool, system):
                answer = super()._classify_cases(user, tool, system)
                for item in answer["cases"]:
                    item["cause"] = "متابعة"
                return answer

        install(monkeypatch, Stubborn())
        cases, s = _cases([{"case_id": "1", "description": "مرحبا", "resolution_text": "تم"}], root_cause_extraction=True)
        result = classify_cases(cases, TAX, s, entity_name="E", carried_umbrellas=[])
        assert result.root_cause_fixes == 0
        assert cases[0].deep_reviewed and cases[0].provenance == "deep_review"


class TestShortOutput:
    """The model answers in a short schema; the classifier reads full labels (cost, measured)."""

    def test_codes_follow_the_taxonomy_and_name_both_levels(self):
        from noveintel_inquiries.classification.prompts import label_codes

        codes = label_codes(TAX)
        assert codes["M1.1"] == (TAX.main_names[0], TAX.main_to_subs[TAX.main_names[0]][0])
        assert all(TAX.is_valid_pair(main, sub) for main, sub in codes.values())
        assert len(codes) == sum(len(v) for v in TAX.main_to_subs.values())

    def test_the_tool_asks_for_no_evidence_and_short_keys(self):
        from noveintel_inquiries.classification.prompts import classifier_tool

        item = classifier_tool(TAX, root_causes=True)["input_schema"]["properties"]["cases"]["items"]
        assert set(item["required"]) == {"id", "type", "tt", "sub", "reason", "conf", "cause"}
        assert "evidence" not in str(item)

    def test_answers_come_back_under_the_case_id_with_full_names(self, monkeypatch):
        from noveintel_inquiries.classification.model import BATCH_SIZE, DEEP_BATCH_SIZE, ModelClassifier

        from .fakes import install

        install(monkeypatch)
        clf = ModelClassifier(TAX, root_causes=True, entity="E")
        assert (BATCH_SIZE, DEEP_BATCH_SIZE) == (40, 10)
        main, sub = TAX.main_names[2], TAX.main_to_subs[TAX.main_names[2]][0]
        assert clf._short({"main_service": main, "sub_classification": sub, "root_cause": "x"}) == {"sub": "M3.1", "cause": "x"}
        back = clf._long({"id": "c1", "type": "استفسار", "tt": "inquiry", "sub": "M3.1", "reason": "r", "conf": 0.9, "cause": "x"}, "260630-1")
        assert back == {"case_id": "260630-1", "main_service": main, "sub_classification": sub, "actual_contact_type": "استفسار",
                        "true_type": "inquiry", "classification_reason": "r", "confidence": 0.9, "root_cause": "x"}
        assert "main_service" not in clf._long({"id": "c1", "sub": "M99.9"}, "x")  # an unknown code sets nothing



class TestNearDuplicates:
    """Near-identical cases copy the labels of the earlier one (measured: reviewers agreed 95%)."""

    TEXT = "كيف يمكنني ضم مدة خدمة سابقة إلى خدمتي الحالية في الصندوق"
    RES = "يمكنكم تقديم طلب ضم مدة الخدمة السابقة عبر منصة تم من خلال الرابط"

    def _rows(self):
        return [
            {"case_id": "a", "description": self.TEXT, "resolution_text": self.RES},
            {"case_id": "b", "description": self.TEXT + " لو سمحت", "resolution_text": self.RES},
            {"case_id": "c", "description": self.TEXT + " لو سمحت", "resolution_text": self.RES},  # exact copy of b
            {"case_id": "d", "description": "أرجو تعديل بيانات الحساب المصرفي لصرف المعاش", "resolution_text": "تم تعديل الحساب"},
        ]

    def test_a_near_identical_case_copies_the_earlier_one(self, monkeypatch):
        from .fakes import install

        install(monkeypatch)
        cases, s = _cases(self._rows(), root_cause_extraction=True)
        result = classify_cases(cases, TAX, s, entity_name="E", carried_umbrellas=[])
        by_id = {c.case_id: c for c in cases}
        assert result.near_duplicates_reused == 1
        assert by_id["b"].duplicate_of == "a" and by_id["c"].duplicate_of == "a"  # the exact copy follows through
        assert by_id["d"].duplicate_of is None
        assert by_id["b"].sub_classification == by_id["a"].sub_classification and by_id["b"].provenance == "auto"
        assert "near-identical case a" in by_id["b"].corrections[-1]
        assert result.duplicates_reused == 2

    def test_one_turns_it_off(self, monkeypatch):
        from .fakes import install

        install(monkeypatch)
        cases, s = _cases(self._rows(), near_duplicate_similarity=1.0)
        result = classify_cases(cases, TAX, s, entity_name="E", carried_umbrellas=[])
        assert result.near_duplicates_reused == 0 and {c.case_id for c in cases if c.duplicate_of} == {"c"}

    def test_an_embedding_failure_classifies_everything(self, monkeypatch):
        from noveintel_inquiries.core42 import embeddings

        from .fakes import install

        install(monkeypatch)

        def down(*args, **kwargs):
            raise RuntimeError("gateway down")

        monkeypatch.setattr(embeddings, "embed_texts", down)
        cases, s = _cases(self._rows())
        result = classify_cases(cases, TAX, s, entity_name="E", carried_umbrellas=[])
        assert result.near_duplicates_reused == 0 and all(c.sub_classification for c in cases)


class TestSplitAndMissingAnswers:
    """The deep review once returned 1 answer for 7 cases: the model had split its answer
    across several tool calls and only the first was read."""

    def test_tool_input_merges_every_block(self):
        from types import SimpleNamespace

        from noveintel_inquiries.core42 import tool_input

        block = lambda data: SimpleNamespace(type="tool_use", input=data)  # noqa: E731
        message = SimpleNamespace(content=[block({"cases": [1], "note": ""}), SimpleNamespace(type="text"),
                                           block({"cases": [2, 3], "note": "n", "extra": "x"})])
        assert tool_input(message) == {"cases": [1, 2, 3], "note": "n", "extra": "x"}
        assert tool_input(SimpleNamespace(content=[SimpleNamespace(type="text")])) is None

    def test_an_answer_split_across_tool_calls_labels_every_case(self, monkeypatch):
        from .fakes import FakeGateway, _Block, _Message, install

        class OneCallPerCase(FakeGateway):
            def create(self, **kwargs):
                message = super().create(**kwargs)
                data = message.content[0].input
                if "cases" not in data:
                    return message
                return _Message(content=[_Block(input={"cases": [c]}, name=message.content[0].name) for c in data["cases"]])

        install(monkeypatch, OneCallPerCase())
        topics = ["المعاش", "المكافأة", "الشهادة", "الإقرار", "التسجيل", "الضم", "الحساب"]
        rows = [{"case_id": str(i), "description": f"مرحبا review-me سؤال عن {t}", "resolution_text": f"رد عن {t}"} for i, t in enumerate(topics)]
        cases, s = _cases(rows, near_duplicate_similarity=1.0)
        result = classify_cases(cases, TAX, s, entity_name="E", carried_umbrellas=[])
        assert result.model_unavailable == 0
        assert result.deep_reviewed == 7 and all(c.provenance == "deep_review" for c in cases)

    def test_a_case_left_out_is_asked_for_once_more(self, monkeypatch):
        from .fakes import FakeGateway, install

        class Forgetful(FakeGateway):
            def _classify_cases(self, user, tool, system):
                answer = super()._classify_cases(user, tool, system)
                if len(answer["cases"]) > 1:
                    answer["cases"] = answer["cases"][:-1]  # drop the last case of every multi-case batch
                return answer

        gateway = install(monkeypatch, Forgetful())
        topics = ["المعاش", "المكافأة", "الشهادة"]
        rows = [{"case_id": str(i), "description": f"سؤال مختلف عن {t} في الخدمة", "resolution_text": f"رد عن {t}"} for i, t in enumerate(topics)]
        cases, s = _cases(rows, near_duplicate_similarity=1.0)
        result = classify_cases(cases, TAX, s, entity_name="E", carried_umbrellas=[])
        assert result.model_unavailable == 0 and gateway.calls.count("classify_cases") == 2
