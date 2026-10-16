"""
The report's sections — one entry each, and everything a run needs to know about one.

A section declares its title, whether it is numbered (01–05 among those shown), whether
it needs root causes (X8), what it needs from the qualitative analysis, the narrative
fields it prints and which narrative call writes them, and the context keys only it
reads. The pipeline, the narrative writer and the assembler all read this table, so
adding a section is an entry here, a builder in ``report/assemble.BUILDERS`` and its
prompt lines; ``tests/test_sections.py`` fails when one of the three is missing.

``enabled=False`` marks the Definition Sheet sections the sample output does not have
(BO, 2026-10-14): the classification map's Fujairah subsections, the customer journey,
the guidebook digital gaps, the digital-transformation plan and the AI use cases. They
are real code — built and prompted — but never shown. Bringing one back is
``enabled=True`` here and its key in ``models.enums.ReportSection`` (with its title in
``SECTION_TITLES``), which is what lets a tenant ask for it; the test that pins the
enum to the enabled entries says so if one half is done without the other. No test
runs a disabled section, so test one before enabling it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import BundleWarning
from .models.enums import SECTION_TITLES, ReportSection as RS
from .models.narratives import InquiriesReportNarratives, SectionNarratives

__all__ = [
    "Section", "SECTIONS", "PARTS", "ANALYSIS_ITEMS", "EARLY_GROUPS", "LATE_GROUP",
    "section", "resolve", "present", "analysis_needed", "prune_context", "hidden_fields", "narrative_calls",
]

#: The narrative's two parts: the Full Report Prompt's 29 fields, and the prose of the
#: retired sections, which that schema has no slot for.
PARTS: dict[str, Any] = {"report": InquiriesReportNarratives, "sections": SectionNarratives}

#: What the qualitative analysis (stage 3) can produce. Gaps need the journey's frictions.
ANALYSIS_ITEMS = ("journey", "faqs", "gaps")

# The narrative is written in calls that run side by side. Every field is written from
# the same figures and none reads another field's text, so the calls are independent:
#   A — the descriptive sections, before the analysis is in;
#   B — Sections 02 and 03 (X8), before the analysis is in;
#   C — once the analysis is in: what uses it, and the conclusion, kept with the roadmap
#       so the recommendations and the initiatives are written together.
EARLY_GROUPS = ("A", "B")
LATE_GROUP = "C"


@dataclass(frozen=True)
class Section:
    key: str
    title: dict[str, str]
    numbered: bool = False
    enabled: bool = True
    #: Sections 02–03: shown only with root-cause extraction (X8) and umbrellas.
    needs_bundles: bool = False
    #: Items of ``ANALYSIS_ITEMS`` this section prints.
    analysis: frozenset[str] = frozenset()
    #: Narrative part → the fields this section prints.
    narrative: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: The narrative call that writes this section's fields…
    group: str = "A"
    #: …except these, written in another call (field → group).
    group_of: dict[str, str] = field(default_factory=dict)
    #: Narrative context keys only some sections read. A key is dropped from the prompt
    #: when none of its readers is shown; a key no section lists is always kept (the KPI
    #: block and the figures every section may cite).
    reads: frozenset[str] = frozenset()

    def fields(self, part: str) -> tuple[str, ...]:
        return self.narrative.get(part, ())

    def field_group(self, name: str) -> str:
        return self.group_of.get(name, self.group)


def _active(key: RS, **kwargs: Any) -> Section:
    return Section(key=key.value, title=SECTION_TITLES[key], **kwargs)


# In report order. Retired entries sit where they would print if they came back.
_ALL: tuple[Section, ...] = (
    _active(RS.COVER, narrative={"report": ("top_service_short",)}),
    _active(
        RS.EXECUTIVE_SUMMARY,
        narrative={"report": ("intro_statement", "executive_summary", "comparative_analysis")},
    ),
    _active(
        RS.STATISTICS, numbered=True,
        narrative={"report": ("statistics_intro", "monthly_narrative", "main_service_narrative",
                              "sub_service_narrative", "transactions_ratio_narrative", "channel_narrative",
                              "recorded_vs_true_narrative", "timeliness_narrative")},
        reads=frozenset({"EVENTS"}),
    ),
    # The Definition Sheet's S3 subsections Section 01 does not have: contact types and
    # reclassification, sub-classes by type, out-of-scope detections, severity,
    # departments and the owner level.
    Section(
        key="classification_map", title={"ar": "خريطة تصنيف الطلبات", "en": "Classification map"},
        numbered=True, enabled=False,
        narrative={"sections": ("contact_type_narrative", "reclassification_narrative",
                                "out_of_scope_narrative", "department_narrative")},
        reads=frozenset({"ACTUAL_TYPE", "RECORDED_VS_ACTUAL", "SUB_CLASS_BY_TYPE", "OUT_OF_SCOPE_DETECTED",
                         "DEPARTMENT", "SEVERITY"}),
    ),
    _active(
        RS.SERVICE_FOCUS, numbered=True, needs_bundles=True, group="B",
        narrative={"report": ("service_focus_narratives",)},
        # The root-cause instructions are given whenever Section 02 or 03 is shown.
        reads=frozenset({"SERVICE_FOCUS", "ROOT_CAUSE_TOP", "BUNDLE_BY_SERVICE", "NEAR_OVER_BY_BUNDLE"}),
    ),
    _active(
        RS.ROOT_CAUSES, numbered=True, needs_bundles=True, group="B",
        narrative={"report": ("root_causes_intro", "bundle_distribution_narrative", "bundle_by_service_narrative",
                              "bundle_narratives", "top_root_causes_narrative", "timeliness_by_bundle_narrative")},
        reads=frozenset({"ROOT_CAUSE_TOP", "BUNDLE_BY_SERVICE", "NEAR_OVER_BY_BUNDLE"}),
    ),
    Section(
        key="customer_journey", title={"ar": "التحديات في رحلة المتعامل", "en": "Customer journey frictions"},
        numbered=True, enabled=False, analysis=frozenset({"journey"}), group=LATE_GROUP,
        narrative={"sections": ("journey_narrative",)},
        reads=frozenset({"JOURNEY_MAP"}),
    ),
    _active(
        RS.DIGITAL_CONTENT_OPPORTUNITIES, numbered=True, analysis=frozenset({"faqs"}), group=LATE_GROUP,
        narrative={"report": ("digital_opportunity_narrative", "priority_faqs")},
        reads=frozenset({"VALIDATED_FAQS", "FAQ_COVERAGE"}),
    ),
    # The guidebook gap table (S5.1) and the root causes behind the gaps (S5.2). Its
    # digital-content part (S5.3) is Section 04.
    Section(
        key="digital_gaps", title={"ar": "تحليل الفجوات الرقمية", "en": "Digital gap analysis"},
        numbered=True, enabled=False, analysis=frozenset({"journey", "gaps"}), group=LATE_GROUP,
        narrative={"sections": ("digital_gaps_narrative", "gap_root_causes_narrative")},
        reads=frozenset({"JOURNEY_MAP", "GAP_TABLE"}),
    ),
    Section(
        key="digital_transformation", title={"ar": "خطة التحويل الرقمي", "en": "Digital transformation plan"},
        numbered=True, enabled=False, analysis=frozenset({"journey", "faqs"}), group=LATE_GROUP,
        narrative={"sections": ("digital_transformation_narrative",)},
        reads=frozenset({"VALIDATED_FAQS", "NOTIFICATION_OPPORTUNITIES"}),
    ),
    Section(
        key="ai_use_cases", title={"ar": "حالات الاستخدام بالذكاء الاصطناعي", "en": "Artificial intelligence use cases"},
        numbered=True, enabled=False, analysis=frozenset({"journey", "faqs"}), group=LATE_GROUP,
        narrative={"sections": ("ai_use_cases_intro", "ai_use_cases")},
        reads=frozenset({"INITIATIVE_SOURCES", "JOURNEY_MAP", "NOTIFICATION_OPPORTUNITIES", "VALIDATED_FAQS"}),
    ),
    # Initiatives cite frictions, notifications and FAQs.
    _active(
        RS.IMPROVEMENT_ROADMAP, numbered=True, analysis=frozenset({"journey", "faqs"}), group=LATE_GROUP,
        narrative={"report": ("roadmap_intro", "initiatives")},
        reads=frozenset({"INITIATIVE_SOURCES", "JOURNEY_MAP", "NOTIFICATION_OPPORTUNITIES", "VALIDATED_FAQS"}),
    ),
    _active(
        RS.CONCLUSION, group=LATE_GROUP,
        narrative={"report": ("key_findings", "recommendations", "closing_statement")},
    ),
    # Methodology · qualitative observations · the journey friction points. Only the
    # friction points wait for the analysis.
    _active(
        RS.APPENDICES, analysis=frozenset({"journey"}),
        narrative={"report": ("methodology_note", "event_narratives", "friction_points")},
        group_of={"friction_points": LATE_GROUP},
        reads=frozenset({"EVENTS", "JOURNEY_MAP"}),
    ),
)

#: Every section, enabled or not, by key, in report order.
SECTIONS: dict[str, Section] = {s.key: s for s in _ALL}


def section(key: Any) -> Section:
    """The entry for a ``ReportSection`` or a key."""
    return SECTIONS[str(getattr(key, "value", key))]


def _enabled() -> list[Section]:
    return [s for s in SECTIONS.values() if s.enabled]


def resolve(requested: list[Any] | None, settings: Any, warnings: list[BundleWarning]) -> list[str]:
    """The tenant's section list, in report order: the cover always; the root-cause
    sections only with X8; a section that is not enabled never."""
    wanted = {str(getattr(x, "value", x)) for x in requested} if requested else {s.key for s in _enabled()}
    wanted.add(RS.COVER.value)
    if not settings.root_cause_extraction:
        asked = [s.key for s in _enabled() if s.needs_bundles and requested and s.key in wanted]
        if asked:
            warnings.append(BundleWarning(
                code="section_omitted",
                message="Root-cause sections were requested but root-cause extraction (X8) is off, so they are left out.",
                detail={"sections": asked, "input": "settings.root_cause_extraction"},
            ))
        wanted -= {s.key for s in SECTIONS.values() if s.needs_bundles}
    return [s.key for s in _enabled() if s.key in wanted]


def present(shown: list[str], metrics: dict[str, Any]) -> list[str]:
    """Of the shown sections, those this run can produce. Sections 02–03 need bundles."""
    return [k for k in shown if not SECTIONS[k].needs_bundles or metrics.get("BUNDLE")]


def analysis_needed(shown: list[str]) -> dict[str, bool]:
    """Which analysis items any shown section prints."""
    needed: set[str] = set()
    for key in shown:
        needed |= SECTIONS[key].analysis
    return {item: item in needed for item in ANALYSIS_ITEMS}


def prune_context(context: dict[str, Any], shown: list[str]) -> dict[str, Any]:
    """The narrative context without the data only hidden or disabled sections read."""
    readers: dict[str, set[str]] = {}
    for s in SECTIONS.values():
        for key in s.reads:
            readers.setdefault(key, set()).add(s.key)
    visible = set(shown)
    return {k: v for k, v in context.items() if k not in readers or readers[k] & visible}


def hidden_fields(shown: list[Any] | set[Any]) -> dict[str, set[str]]:
    """Per part, every narrative field that no shown section prints."""
    keys = {str(getattr(x, "value", x)) for x in shown}
    printed: dict[str, set[str]] = {part: set() for part in PARTS}
    for s in SECTIONS.values():
        if s.key in keys:
            for part in PARTS:
                printed[part].update(s.fields(part))
    return {part: set(model.model_fields) - printed[part] for part, model in PARTS.items()}


def _fields_in(groups: set[str]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {part: set() for part in PARTS}
    for s in SECTIONS.values():
        for part in PARTS:
            out[part].update(f for f in s.fields(part) if s.field_group(f) in groups)
    return out


def narrative_calls(shown: list[str]) -> dict[str, Any]:
    """How the narrative is split for ``narratives.writer.write_narratives``.

    ``early_groups`` are the report-part field sets of groups A and B (one call each);
    ``early_hidden`` and ``late_hidden`` are what each of the two writer runs leaves out:
    everything hidden, plus the other run's fields.
    """
    hidden = hidden_fields(shown)
    early, late = _fields_in(set(EARLY_GROUPS)), _fields_in({LATE_GROUP})
    every = {part: set(model.model_fields) for part, model in PARTS.items()}
    return {
        "early_groups": [_fields_in({g})["report"] for g in EARLY_GROUPS],
        "early_hidden": {part: hidden[part] | (every[part] - early[part]) for part in PARTS},
        "late_hidden": {part: hidden[part] | (every[part] - late[part]) for part in PARTS},
    }
