"""
A fake Core42 gateway: every model call answered locally, by tool name.

Installed by patching ``Core42Client`` so the whole pipeline runs end to end with no
network — the wiring, the counting, the documents and the post-processing are what is
under test, not the model's prose. Answers are deterministic and deliberately simple:
a label set per case, one umbrella, one friction per group pair, one FAQ per service.

Markers in a case description steer the classifier: ``review-me`` gives a first-pass
confidence below X6 (so the deep review runs); ``still-low`` keeps it low through the
deep review too. A narrative payload carrying ``arabic`` is the translation call; it is
answered with English that keeps every figure of the Arabic.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from noveintel_inquiries.models.narratives import InquiriesReportNarratives, SectionNarratives


@dataclass
class _Block:
    input: dict
    type: str = "tool_use"
    name: str = ""
    id: str = "t1"


@dataclass
class _Message:
    content: list
    stop_reason: str = "tool_use"
    model: str = "fake"


@dataclass
class FakeGateway:
    """Records calls; answers each tool deterministically."""

    calls: list[str] = field(default_factory=list)
    fail_tools: set[str] = field(default_factory=set)
    narrative_figure: str | None = None  # a figure to plant in the prose, for the fidelity check

    def create(self, *, model=None, messages=None, max_tokens=None, system=None, tools=None,
               tool_choice=None, stage=None, **_: Any) -> _Message:
        from noveintel_inquiries.core42 import tokens

        tool = tools[0]
        name = tool["name"]
        self.calls.append(name)
        tokens.track("fake-model", 100, 50, stage or "test")
        if name in self.fail_tools:
            raise RuntimeError(f"fake failure in {name}")
        user = messages[-1]["content"]
        answer = getattr(self, f"_{name}")(user, tool, system or "")
        return _Message(content=[_Block(input=answer, name=name)])

    # ── classification ──
    def _classify_cases(self, user: str, tool: dict, system: str) -> dict:
        schema = tool["input_schema"]["properties"]["cases"]["items"]["properties"]
        mains = schema["main_service"]["enum"]
        blocks = user.split("\n\n---\n\n")
        out = []
        for block in blocks:
            match = re.search(r"case_id: (\S+)", block)
            if not match:
                continue
            fixed = dict(re.findall(r"(\w+)=([^;\n]+)", block.split("fixed labels (keep unchanged):")[1].split("\n")[0])) \
                if "fixed labels" in block else {}
            main = fixed.get("main_service") or mains[0]
            subs = [s for s in schema["sub_classification"]["enum"]]
            sub = fixed.get("sub_classification") or subs[0]
            item = {
                "case_id": match.group(1),
                "actual_contact_type": fixed.get("actual_contact_type", "استفسار"),
                "true_type": "complaint" if "شكوى" in block[:400] else "inquiry",
                "main_service": main,
                "sub_classification": sub,
                "classification_reason": "الرد يشرح الخطوات ويحيل إلى صفحة الخدمة",
                "evidence": "الرد يقدم رابط الخدمة",
                "confidence": self._confidence(block, system),
            }
            if "root_cause" in schema:
                item["root_cause"] = (
                    "متابعة" if "short-cause" in block and "FIX:" not in block
                    else "الاستفسار عن إجراءات تقديم الخدمة عبر القنوات الرقمية المعتمدة"
                )
            out.append(item)
        return {"cases": out}

    @staticmethod
    def _confidence(block: str, system: str) -> float:
        if "Deep review" in system:
            return 0.6 if "still-low" in block else 0.92
        return 0.62 if ("review-me" in block or "still-low" in block) else 0.88

    def _cluster_root_causes(self, user: str, tool: dict, system: str) -> dict:
        data = json.loads(user)
        carried = data.get("carried_umbrellas") or []
        if carried:
            target = carried[0]["id"]
            umbrellas = []
        else:
            target = "n1"
            umbrellas = [{"id": "n1", "ar": "طلب إجراءات ومتطلبات الخدمة", "en": "Procedures & requirements",
                          "meaning_ar": "كيف أقدّم وما المطلوب", "meaning_en": "How to apply and what is needed", "new": True}]
        return {"umbrellas": umbrellas, "assignment": [{"root_cause": rc["id"], "umbrella_id": target} for rc in data["root_causes"]]}

    def _merge_umbrellas(self, user: str, tool: dict, system: str) -> dict:
        return {"mapping": []}

    # ── analysis ──
    def _map_journey(self, user: str, tool: dict, system: str) -> dict:
        groups = [g["group_id"] for g in json.loads(user)["groups"]]
        return {
            "frictions": [{"name_ar": "صعوبة الوصول إلى متطلبات الخدمة", "name_en": "Hard-to-find service requirements",
                           "root_cause_category": "inaccessible_info", "remedy_ar": "نشر المتطلبات في صفحة الخدمة",
                           "remedy_en": "Publish the requirements on the service page", "group_ids": groups[:2]}],
            "notification_opportunities": [{"type_ar": "إشعار حالة الطلب", "type_en": "Request-status notice",
                                            "trigger_ar": "تغير حالة الطلب", "trigger_en": "Request status changes",
                                            "message_ar": "تم تحديث حالة طلبكم", "message_en": "Your request status was updated",
                                            "group_ids": groups[2:3] or groups[:1]}],
        }

    def _propose_faqs(self, user: str, tool: dict, system: str) -> dict:
        data = json.loads(user)
        words = []
        for sample in data["samples"]:
            words += [w for w in re.findall(r"[؀-ۿ]{4,}", sample["description"])]
        common = [w for w, _ in __import__("collections").Counter(words).most_common(3)] or ["الخدمة"]
        return {"faqs": [{"question_ar": "كيف أتقدم بطلب الخدمة؟", "question_en": "How do I apply for the service?",
                          "answer_ar": "عبر القنوات الرقمية المعتمدة", "answer_en": "Through the approved digital channels",
                          "keywords_ar": common}]}

    def _assess_guidebook(self, user: str, tool: dict, system: str) -> dict:
        frictions = json.loads(user)["frictions"]
        return {"gaps": [{"friction_id": f["friction_id"], "topic_ar": "متطلبات الخدمة", "topic_en": "Service requirements",
                          "guidebook_status": "Missing", "guidebook_excerpt": "", "gap_type": "missing_content",
                          "recommendation_ar": "إضافة المتطلبات إلى الدليل", "recommendation_en": "Add the requirements to the guidebook"}
                         for f in frictions]}

    # ── narratives ──
    def _translate_labels(self, user: str, tool: dict, system: str) -> dict:
        return {"labels": [{"id": x["id"], "en": f"EN {x['id']}"} for x in json.loads(user)]}

    def _write_report_narratives(self, user: str, tool: dict, system: str) -> dict:
        ctx = _payload(user)
        if "arabic" in ctx:
            return _translate(ctx["arabic"], ctx.get("glossary") or {})
        total = ctx["KPI"]["total_cases"]
        en = "Use only" in system or "You are a specialist" in system
        figure = self.narrative_figure or str(total)
        para = (f"The run analysed {figure} cases; customer contacts dominated the phone channel." if en
                else f"جرى تحليل {figure} حالة وهيمنت القنوات الهاتفية على التواصل.")
        sources = ctx.get("INITIATIVE_SOURCES") or [{"id": "none", "cases": 0}]
        data = {name: para for name, f in InquiriesReportNarratives.model_fields.items()}
        data.update({
            "service_focus_narratives": [], "bundle_narratives": [],
            "priority_faqs": ["1. سؤال عن المتطلبات"], "key_findings": ["- نتيجة أولى", "• نتيجة ثانية"],
            "recommendations": ["توصية"], "event_narratives": [], "friction_points": ["نقطة"],
            "initiatives": [{"title": "مبادرة", "horizon": "immediate", "bundle_ref": sources[0]["id"],
                             "addresses_cases": 999999, "description": para},
                            {"title": "بلا مرجع", "horizon": "short", "bundle_ref": "nope", "addresses_cases": 1, "description": para}],
            "top_service_short": "خدمة رئيسية طويلة الاسم جداً للتجربة",
        })
        if ctx.get("BUNDLE"):
            data["bundle_narratives"] = [{"bundle": ctx["BUNDLE"]["labels"][0], "narrative": para}]
            data["service_focus_narratives"] = [
                {"service": f["service"], "overview": para, "why_this_service": para,
                 "sub_class_narrative": para, "bundle_narrative": para} for f in ctx.get("SERVICE_FOCUS", [])
            ]
        return data

    def _write_section_narratives(self, user: str, tool: dict, system: str) -> dict:
        ctx = _payload(user)
        if "arabic" in ctx:
            return _translate(ctx["arabic"], ctx.get("glossary") or {})
        sources = ctx.get("INITIATIVE_SOURCES") or [{"id": "none"}]
        data = {name: "نص" for name in SectionNarratives.model_fields}
        data["ai_use_cases"] = [{"title": "مساعد", "function": "يجيب", "source_ref": sources[0]["id"],
                                 "effort": "low", "impact_cases": 5}]
        return data


# Keys whose values are references or enums, never prose: a translation keeps them.
_KEEP = {"horizon", "bundle_ref", "source_ref", "effort", "addresses_cases", "impact_cases", "bundle", "service"}


def _payload(user: str) -> dict:
    """The JSON a narrative call carries — after any retry note."""
    return json.loads(user.rsplit("\n\n", 1)[-1])


def _translate(node: Any, glossary: dict[str, str], key: str = "") -> Any:
    """A stand-in English rendering that keeps every figure of the Arabic."""
    if isinstance(node, dict):
        return {k: (v if k in _KEEP else _translate(v, glossary, k)) for k, v in node.items()}
    if isinstance(node, list):
        return [_translate(x, glossary, key) for x in node]
    if isinstance(node, str) and node:
        if node in glossary:
            return glossary[node]
        figures = re.findall(r"\d+(?:\.\d+)?%?", node)
        return ("English text " + " ".join(figures)).strip()
    return node


def install(monkeypatch, gateway: FakeGateway | None = None) -> FakeGateway:
    """Route every Core42 call in the package to ``gateway``."""
    from noveintel_inquiries.core42 import messages as messages_module

    gateway = gateway or FakeGateway()

    class _FakeMessages:
        def create(self, **kwargs):
            return gateway.create(**kwargs)

    def _init(self, api_key=None, model=None):
        self.api_key = "fake"
        self.model = "fake"
        self.messages = _FakeMessages()

    monkeypatch.setattr(messages_module.Core42Client, "__init__", _init)
    return gateway
