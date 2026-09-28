"""
Brand theming of the Word document.

The rule these pin: **an absent brand must render exactly as the report always has.**
``BrandColors`` defaults to the NoveAI platform palette because it is a shared contract
model and must carry no organisation's colours — so if those defaults reached the
builder, every existing report would silently repaint. ``pipeline.py`` passes ``brand``
on only when the caller actually set it, and the builder falls back to its own design
palette when it is absent.
"""
from __future__ import annotations

import collections
import json
import re
import zipfile
from pathlib import Path

import pytest

from noveintel_complaints.api.models import EntityInfo
from noveintel_complaints.pipeline import _materialise_branding
from noveintel_complaints.stages.build_report_ar import DEFAULT_THEME, _hex, _theme

DESIGN_GOLD = "B68A35"


class TestHexParsing:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("#B68A35", "B68A35"),
            ("b68a35", "B68A35"),
            ("#abc", "AABBCC"),      # 3-digit shorthand
            ("  #B68A35  ", "B68A35"),
        ],
    )
    def test_accepted(self, value, expected):
        assert _hex(value) == expected

    @pytest.mark.parametrize("value", ["navy", "", "#12345", "#1234567", None, 42, []])
    def test_rejected_rather_than_passed_through(self, value):
        """A bad colour reaching python-docx produces a document Word offers to
        repair, so it falls back instead."""
        assert _hex(value) is None


class TestTheme:
    def test_no_branding_is_the_design_palette(self):
        assert _theme({}) == DEFAULT_THEME
        assert _theme({"branding": {}}) == DEFAULT_THEME
        assert DEFAULT_THEME.primary == DESIGN_GOLD

    def test_an_explicit_brand_is_used(self):
        theme = _theme({"branding": {"brand": {"primary": "#201853", "secondary": "#7E2362"}}})
        assert (theme.primary, theme.secondary) == ("201853", "7E2362")

    def test_a_malformed_brand_falls_back_whole(self):
        assert _theme({"branding": {"brand": {"primary": "navy"}}}) == DEFAULT_THEME

    def test_one_colour_given_means_one_colour_used(self):
        """Falling back to the design palette for the second would mix two unrelated
        identities in one document."""
        theme = _theme({"branding": {"brand": {"primary": "#201853"}}})
        assert theme.primary == theme.secondary == "201853"


class TestBrandIsOptIn:
    def test_an_unset_brand_is_not_passed_on(self, tmp_path):
        """The load-bearing one. EntityInfo.brand always has a value — the NoveAI
        defaults — so the builder can only tell 'unset' from 'set to navy' because
        pipeline.py checks model_fields_set."""
        entity = EntityInfo(name_ar="أ", name_en="A")
        assert "brand" not in _materialise_branding(entity, tmp_path)

    def test_an_explicit_brand_is_passed_on(self, tmp_path):
        entity = EntityInfo(name_ar="أ", name_en="A", brand={"primary": "#201853"})
        branding = _materialise_branding(entity, tmp_path)
        assert branding["brand"]["primary"] == "#201853"

    def test_explicitly_sending_the_defaults_counts_as_setting_them(self, tmp_path):
        """A caller that deliberately posts the NoveAI palette gets it."""
        entity = EntityInfo(
            name_ar="أ", name_en="A", brand={"primary": "#201853", "secondary": "#7E2362"}
        )
        assert _materialise_branding(entity, tmp_path)["brand"]["primary"] == "#201853"


class TestRenderedDocument:
    """End to end through the real Word builder, on a minimal report."""

    REPORT = {
        "document_name": "تقرير — Q1 2025",
        "sections": [
            {
                "id": "s1", "title": "1. القسم", "level": 1, "content": "نص",
                "tables": [{"columns": ["أ", "ب"], "rows": [{"أ": "1", "ب": "2"}]}],
                "charts": [], "subsections": [],
            }
        ],
    }

    @staticmethod
    def _colours(path: Path) -> collections.Counter:
        with zipfile.ZipFile(path) as archive:
            xml = b"".join(
                archive.read(n) for n in archive.namelist() if n.endswith(".xml")
            )
        return collections.Counter(
            m.decode().upper()
            for m in re.findall(rb'(?:val|fill)="([0-9A-Fa-f]{6})"', xml)
        )

    def _build(self, tmp_path: Path, branding: dict | None, name: str) -> collections.Counter:
        from noveintel_complaints.stages.build_report_ar import build_report

        data = json.loads(json.dumps(self.REPORT))
        if branding is not None:
            data["branding"] = branding
        source = tmp_path / f"{name}.json"
        source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        target = tmp_path / f"{name}.docx"
        build_report(source, target)
        return self._colours(target)

    def test_without_a_brand_the_document_is_gold(self, tmp_path):
        counts = self._build(tmp_path, None, "plain")
        assert counts[DESIGN_GOLD] > 0
        assert counts["201853"] == 0

    def test_with_a_brand_the_gold_is_gone(self, tmp_path):
        """Not merely 'navy appears' — no design gold may survive, or the document
        carries two identities at once."""
        counts = self._build(
            tmp_path, {"brand": {"primary": "#201853", "secondary": "#7E2362"}}, "branded"
        )
        assert counts["201853"] > 0
        assert counts[DESIGN_GOLD] == 0

    def test_table_headers_follow_the_brand(self, tmp_path):
        """The table header fill is the one that a partially threaded theme misses,
        because it comes from a style object rather than from the document config."""
        counts = self._build(tmp_path, {"brand": {"primary": "#201853"}}, "tables")
        assert counts[DESIGN_GOLD] == 0

    def test_a_malformed_brand_still_produces_a_readable_document(self, tmp_path):
        counts = self._build(tmp_path, {"brand": {"primary": "not-a-colour"}}, "bad")
        assert counts[DESIGN_GOLD] > 0
