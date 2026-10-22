"""
FAQ detection (Section 04): grouping, judging, merging, and the engine's sums.

The model only labels — a verdict per question group, a question for the largest —
and the engine counts, so every figure here is checked against the labels on the
cases. No test needs the network: ``fakes.fake_embed`` hashes character trigrams.
"""
from __future__ import annotations

import numpy as np
import pytest

from noveintel_inquiries.analysis import faqs as faqs_module
from noveintel_inquiries.analysis.faqs import detect_faqs, faq_entries, group_units
from noveintel_inquiries.analysis.prompts import FAQ_JUDGE_TOOL, FAQ_MERGE_TOOL
from noveintel_inquiries.core42 import embeddings
from noveintel_inquiries.engine.compute import Umbrella, faq_catalogue_volume, faq_coverage, faq_population
from noveintel_inquiries.engine.parse import Case
from noveintel_inquiries.models import TenantSettings
from noveintel_inquiries.models.reference import FaqEntry

from .conftest import SETTINGS
from .fakes import FakeGateway, install

HOWTO = Umbrella(id="u1", name_ar="طلب إجراءات ومتطلبات الخدمة")
DATES = Umbrella(id="u2", name_ar="مواعيد الصرف والمستحقات المالية")
FOLLOW = Umbrella(id="u3", name_ar="متابعة طلب أو معاملة قائمة")

APPLY = "الاستفسار عن كيفية التقديم على صرف مكافأة نهاية الخدمة"
APPLY_2 = "الاستفسار عن كيفية التقديم على طلب صرف مكافأة نهاية الخدمة"
DATE = "الاستفسار عن موعد صرف المعاش التقاعدي"
CERT = "الاستفسار عن كيفية إصدار شهادة غير مسجل في الصندوق"
TRACK = "الاستفسار عن متابعة حالة معاملة إنهاء الخدمة"

CATALOGUE = [
    FaqEntry(question_ar="كيف يمكن للمؤمن عليه التقديم على صرف مكافأة نهاية الخدمة؟", answer_ar="عبر منصة تم من خلال خدمة صرف المنافع التقاعدية."),
    FaqEntry(question_ar="ما هو نظام الخصم المباشر؟", answer_ar="نظام لتسهيل سداد الاشتراكات الشهرية."),
]


def _settings(**extra) -> TenantSettings:
    return TenantSettings(**{**SETTINGS, **extra})


def _case(n: int, root_cause: str, bundle: str, service: str = "إنهاء خدمة المؤمن عليه") -> Case:
    return Case(case_id=f"c{n}", description="وصف منقح", contact_type="استفسار", true_type="inquiry",
                main_service=service, sub_classification="صرف مكافأة", root_cause=root_cause, bundle=bundle)


def _cases() -> list[Case]:
    rows = [(APPLY, "u1")] * 6 + [(APPLY_2, "u1")] * 3 + [(DATE, "u2")] * 5 + [(CERT, "u1")] * 4 + \
           [("الاستفسار عن سؤال نادر جداً لا يشبه غيره", "u1")] + [(TRACK, "u3")] * 7
    return [_case(i, rc, b) for i, (rc, b) in enumerate(rows)]


def _run(cases, *, gateway: FakeGateway, catalogue=CATALOGUE, **settings):
    return detect_faqs(cases, umbrellas=[HOWTO, DATES, FOLLOW], settings=_settings(**settings),
                       catalogue=catalogue, guidebook=None, entity="ADPF", vocabulary={"ar": {}, "en": {}})


@pytest.fixture
def fake(monkeypatch):
    return install(monkeypatch)


class TestNoAnswers:
    def test_no_tool_asks_for_an_answer(self):
        for tool in (FAQ_JUDGE_TOOL, FAQ_MERGE_TOOL):
            fields = tool["input_schema"]["properties"]
            flat = str(fields)
            assert "answer_ar" not in flat and "answer_en" not in flat

    def test_no_priority_faq_carries_an_answer(self, fake):
        result = _run(_cases(), gateway=fake)
        assert result.priority and not any(k.startswith("answer") for q in result.priority for k in q)


class TestGrouping:
    def test_leader_grouping_is_greedy_and_ordered(self):
        v = np.array([[1, 0], [0.99, 0.141], [0, 1], [0.6, 0.8]], dtype=np.float32)
        v /= np.linalg.norm(v, axis=1, keepdims=True)
        assert group_units(v, 0.95) == [[0, 1], [2], [3]]
        # Unit 3 is over the threshold for both leaders and joins the closer one.
        assert group_units(v, 0.5) == [[0, 1], [2, 3]]

    def test_paraphrases_group_and_different_questions_do_not(self, fake):
        result = _run(_cases(), gateway=fake)
        assert result.groups >= 4
        apply = next(q for q in result.priority if any(r["text"] == APPLY for r in q["root_causes"]))
        assert {r["text"] for r in apply["root_causes"]} >= {APPLY, APPLY_2}
        assert all(r["text"] != DATE for r in apply["root_causes"])
        assert all(q["question_ar"] for q in result.priority)


class TestPopulation:
    def test_umbrellas_define_the_population_and_the_coverage_base(self):
        cases = _cases()
        pop = faq_population(cases, [HOWTO, DATES, FOLLOW], _settings())
        assert {c.bundle for c in pop.cases} == {"u1", "u2"}  # the follow-up umbrella is not self-service-able
        assert {c.bundle for c in pop.coverage} == {"u1"}
        assert pop.howto_umbrella == "u1"

    def test_without_umbrellas_the_inquiries_are_both(self):
        cases = _cases()
        for c in cases:
            c.bundle = None
        pop = faq_population(cases, [], _settings())
        assert len(pop.cases) == len(cases) == len(pop.coverage)
        assert pop.basis == "inquiry-type cases"


class TestJudging:
    def test_every_coverage_group_is_judged_even_a_single_case(self, fake):
        cases = _cases()
        _run(cases, gateway=fake)
        rare = next(c for c in cases if "نادر" in c.root_cause)
        assert rare.faq_status in ("covered", "partial", "not_covered")
        # Every case of the coverage base belongs to a judged group.
        pop = faq_population(cases, [HOWTO, DATES, FOLLOW], _settings())
        assert all(c.faq_status is not None for c in pop.coverage)

    def test_a_verdict_may_cite_only_the_shortlisted_entries(self, monkeypatch):
        class OffList(FakeGateway):
            def _judge_faq_groups(self, user, tool, system):
                import json
                return {"groups": [{"group_id": g["group_id"], "status": "covered", "faq_ids": ["F99"],
                                    "question_ar": "سؤال؟", "question_en": "Q?"} for g in json.loads(user)["groups"]]}

        gateway = install(monkeypatch, OffList())
        cases = _cases()
        _run(cases, gateway=gateway)
        assert all(c.faq_status in (None, "not_covered") for c in cases)

    def test_answers_are_shown_truncated_never_returned(self, fake):
        _run(_cases(), gateway=fake)
        entries = [e for p in fake.faq_payloads for e in p["catalogue"]]
        assert entries and all(len(e["answer"]) <= 220 for e in entries)

    def test_without_a_catalogue_only_the_largest_groups_are_judged_for_their_question(self, fake):
        cases = _cases()
        result = _run(cases, gateway=fake, catalogue=None, faq_min_cases=4)
        assert all(c.faq_status is None for c in cases)
        assert {q["validation_status"] for q in result.priority} == {"not_checked"}
        assert all(len(p["catalogue"]) == 0 for p in fake.faq_payloads)

    def test_a_failed_batch_leaves_its_cases_unjudged_with_a_warning(self, monkeypatch):
        gateway = install(monkeypatch, FakeGateway(fail_tools={"judge_faq_groups"}))
        cases = _cases()
        result = _run(cases, gateway=gateway)
        assert result.warnings and all(c.faq_status is None for c in cases)


class TestPriorityList:
    def test_frequency_is_the_count_of_cases_carrying_the_id(self, fake):
        cases = _cases()
        result = _run(cases, gateway=fake)
        for q in result.priority:
            assert q["frequency"] == sum(1 for c in cases if c.faq_id == q["id"])
        freqs = [q["frequency"] for q in result.priority]
        assert freqs == sorted(freqs, reverse=True)
        assert [q["id"] for q in result.priority] == [f"Q{i}" for i in range(1, len(freqs) + 1)]

    def test_small_groups_and_the_count_cap(self, fake):
        result = _run(_cases(), gateway=fake, faq_min_cases=5, priority_faqs=2)
        assert len(result.priority) <= 2 and all(q["frequency"] >= 5 for q in result.priority)

    def test_the_merge_pass_counts_one_question_once(self, monkeypatch):
        class Merge(FakeGateway):
            def _merge_faq_questions(self, user, tool, system):
                import json
                groups = json.loads(user)["groups"]
                ids = [g["group_id"] for g in groups if any("مكافأة" in p or "شهادة" in p for p in g["phrasings"])]
                return {"same_question": [{"group_ids": ids}]}

        gateway = install(monkeypatch, Merge())
        cases = _cases()
        result = _run(cases, gateway=gateway)
        merged = result.priority[0]
        assert merged["frequency"] == sum(1 for c in cases if c.root_cause in (APPLY, APPLY_2, CERT))


class TestEngineSums:
    def test_coverage_sums_the_labels_and_counts_unjudged_as_not_covered(self):
        cases = _cases()
        pop = faq_population(cases, [HOWTO, DATES, FOLLOW], _settings())
        statuses = ["covered"] * 5 + ["partial"] * 3 + [None] * (len(pop.coverage) - 8)
        for c, s in zip(pop.coverage, statuses):
            c.faq_status = s
        fc = faq_coverage(pop, catalogue_size=2)
        assert fc["howto_cases"] == [len(pop.coverage)]
        assert fc["covered_cases"] == [5] and fc["partial_cases"] == [3]
        assert fc["catalogue_size"] == 2 and fc["basis"] == "root causes in the procedures umbrella"

    def test_catalogue_volume_keeps_unasked_entries_at_zero(self):
        cases = _cases()
        pop = faq_population(cases, [HOWTO, DATES, FOLLOW], _settings())
        for c in pop.cases[:4]:
            c.faq_status, c.faq_match = "covered", 0
        pop.cases[4].faq_status, pop.cases[4].faq_match = "partial", 0
        volume = faq_catalogue_volume(pop, faq_entries(CATALOGUE, None))
        # The volume is what an entry covers; partial matches are listed beside, not added.
        assert [(r["index"], r["cases"], r["covered_cases"], r["partial_cases"]) for r in volume] == [(0, 4, 4, 1), (1, 0, 0, 0)]


class TestEmbeddings:
    def test_only_approved_models(self, monkeypatch):
        monkeypatch.setenv("CORE42_MODEL_EMBED", "embed-v-4-0")
        with pytest.raises(ValueError, match="approved"):
            embeddings.embedding_model()
        monkeypatch.setenv("CORE42_MODEL_EMBED", "qwen3-embedding")
        assert embeddings.embedding_model() == "qwen3-embedding"
        monkeypatch.delenv("CORE42_MODEL_EMBED")
        assert embeddings.embedding_model() == "text-embedding-3-large"

    def test_vectors_are_cut_and_renormalised_and_counted(self, monkeypatch):
        from types import SimpleNamespace

        from noveintel_inquiries.core42 import tokens

        calls = []

        class Endpoint:
            def create(self, model, input):
                calls.append((model, list(input)))
                data = [SimpleNamespace(index=i, embedding=list(np.arange(3072, dtype=float) + i)) for i in range(len(input))]
                return SimpleNamespace(data=list(reversed(data)), usage=SimpleNamespace(prompt_tokens=7))

        monkeypatch.setattr(embeddings, "get_core42_client", lambda: SimpleNamespace(embeddings=Endpoint()))
        monkeypatch.delenv("CORE42_MODEL_EMBED", raising=False)
        monkeypatch.setenv("CORE42_EMBED_DIMENSIONS", "1024")
        with tokens.run_scope():
            vectors = embeddings.embed_texts(["أ", "ب"])
            ledger = tokens.summary()
        assert vectors.shape == (2, 1024) and np.allclose(np.linalg.norm(vectors, axis=1), 1)
        assert np.allclose(vectors[0], np.arange(1024) / np.linalg.norm(np.arange(1024)))
        assert calls == [("text-embedding-3-large", ["أ", "ب"])]
        assert ledger["input_tokens"] == 7


def test_module_reads_embeddings_through_the_module(monkeypatch):
    """Call sites reach ``embeddings.embed_texts`` through the module, so it can be replaced."""
    seen = []

    def spy(texts, **kwargs):
        seen.append(len(texts))
        return np.eye(len(texts), 8, dtype=np.float32)

    monkeypatch.setattr(embeddings, "embed_texts", spy)
    install(monkeypatch)
    monkeypatch.setattr(embeddings, "embed_texts", spy)
    detect_faqs(_cases(), umbrellas=[HOWTO, DATES, FOLLOW], settings=_settings(), catalogue=CATALOGUE,
                guidebook=None, entity="ADPF", vocabulary={"ar": {}, "en": {}})
    assert seen and faqs_module.embeddings is embeddings


def test_many_batches_come_back_in_order(monkeypatch):
    from types import SimpleNamespace

    class Endpoint:
        def create(self, model, input):
            data = [SimpleNamespace(index=i, embedding=[float(t.split("-")[1])] + [1.0] * 1023) for i, t in enumerate(input)]
            return SimpleNamespace(data=data, usage=SimpleNamespace(prompt_tokens=1))

    monkeypatch.setattr(embeddings, "get_core42_client", lambda: SimpleNamespace(embeddings=Endpoint()))
    monkeypatch.delenv("CORE42_MODEL_EMBED", raising=False)
    texts = [f"t-{i}" for i in range(300)]  # three batches
    vectors = embeddings.embed_texts(texts)
    raw = vectors[:, 0] / vectors[:, 1]  # undo the normalisation on the marker column
    assert np.allclose(raw, np.arange(300))
