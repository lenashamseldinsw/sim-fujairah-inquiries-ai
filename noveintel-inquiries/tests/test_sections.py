"""
The section registry (``sections.SECTIONS``): that it agrees with the contract, the
assembler and the narrative schema, and that a disabled section is never shown.
"""
from __future__ import annotations

from noveintel_inquiries import sections
from noveintel_inquiries.models import ReportSection
from noveintel_inquiries.narratives.prompts import narrative_system_prompt
from noveintel_inquiries.report.assemble import BUILDERS
from noveintel_inquiries.sections import ANALYSIS_ITEMS, EARLY_GROUPS, LATE_GROUP, PARTS, SECTIONS


RETIRED = [k for k, s in SECTIONS.items() if not s.enabled]


class TestRegistry:
    def test_the_enabled_sections_are_the_contract(self):
        """A tenant can ask for exactly the enabled sections, in the same order."""
        assert [k for k, s in SECTIONS.items() if s.enabled] == [s.value for s in ReportSection]

    def test_every_section_has_a_builder(self):
        assert set(BUILDERS) == set(SECTIONS) - {ReportSection.COVER.value}

    def test_every_narrative_field_belongs_to_one_section(self):
        for part, model in PARTS.items():
            owners: dict[str, list[str]] = {}
            for s in SECTIONS.values():
                for f in s.fields(part):
                    owners.setdefault(f, []).append(s.key)
            assert set(owners) == set(model.model_fields), part
            assert all(len(v) == 1 for v in owners.values()), {f: v for f, v in owners.items() if len(v) > 1}

    def test_groups_and_analysis_items_are_known(self):
        groups = set(EARLY_GROUPS) | {LATE_GROUP}
        for s in SECTIONS.values():
            assert s.group in groups and set(s.group_of.values()) <= groups, s.key
            assert set(s.group_of) <= {f for part in PARTS for f in s.fields(part)}, s.key
            assert s.analysis <= set(ANALYSIS_ITEMS), s.key

    def test_the_two_writer_runs_split_the_shown_fields(self):
        """Every field a shown section prints is asked for by exactly one of the two runs."""
        shown = list(SECTIONS)
        calls = sections.narrative_calls(shown)
        for part, model in PARTS.items():
            every = set(model.model_fields)
            early = every - calls["early_hidden"][part]
            late = every - calls["late_hidden"][part]
            assert not early & late
            assert early | late == every - sections.hidden_fields(shown)[part]

    def test_a_section_is_disabled_by_default_and_never_resolved(self):
        class Settings:
            root_cause_extraction = True

        resolved = sections.resolve(None, Settings(), [])
        assert resolved == [s.value for s in ReportSection]
        assert not set(RETIRED) & set(resolved)

    def test_the_retired_fields_prompt_is_added_only_when_asked(self):
        assert "journey_narrative" not in narrative_system_prompt(root_causes=True, vocabulary={})
        assert "journey_narrative" in narrative_system_prompt(root_causes=True, vocabulary={}, section_fields=True)
