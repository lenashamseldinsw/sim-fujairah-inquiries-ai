"""
Branding (Prerequisites §5): the tenant's brand when sent, NoveAI Navy / Magenta when
not, and the status colours locked whatever the brand.
"""
from __future__ import annotations

from noveintel_inquiries.models import TIMELINESS_COLORS, EntityInfo
from noveintel_inquiries.report.assemble import categorical_palette
from noveintel_inquiries.report.word import DEFAULT_THEME, Theme, theme_of


def test_no_brand_is_the_documented_default():
    assert theme_of({}) == DEFAULT_THEME == Theme("201853", "7E2362")


def test_a_brand_is_applied():
    assert theme_of({"branding": {"brand": {"primary": "#0a7a3d", "secondary": "#abc"}}}) == Theme("0A7A3D", "AABBCC")


def test_one_colour_fills_both_slots():
    assert theme_of({"branding": {"brand": {"primary": "#0A7A3D"}}}) == Theme("0A7A3D", "0A7A3D")


def test_a_malformed_colour_falls_back_to_the_default():
    assert theme_of({"branding": {"brand": {"primary": "navy"}}}) == DEFAULT_THEME


def test_status_colours_are_locked():
    assert TIMELINESS_COLORS == {"within": "#2E8B6B", "near": "#C68A2E", "over": "#B5393F", "unspecified": "#9AA0A6"}


def test_the_categorical_palette_leads_with_the_brand():
    palette = categorical_palette("#111111", "#222222")
    assert palette[:2] == ["#111111", "#222222"] and len(palette) == 10


def test_the_pipeline_passes_the_entitys_brand(tmp_path):
    from noveintel_inquiries.pipeline import _materialise_branding

    default = _materialise_branding(EntityInfo(name_ar="أ", name_en="A"), tmp_path)
    assert default["brand"] == {"primary": "#201853", "secondary": "#7E2362"}
    custom = _materialise_branding(EntityInfo(name_ar="أ", name_en="A", brand={"primary": "#0A7A3D"}), tmp_path)
    assert custom["brand"]["primary"] == "#0A7A3D"
