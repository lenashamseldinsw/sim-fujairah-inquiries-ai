"""
TOC (Table of Contents) XML construction for sword-word-builder.

Ported and generalised from examples/fujairah_toc.py.
"""
from __future__ import annotations

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree

from .config import TocStyle


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_el(tag: str, attribs: dict | None = None, text: str | None = None):
    el = OxmlElement(tag)
    if attribs:
        for k, v in attribs.items():
            el.set(k, v)
    if text is not None:
        el.text = text
    return el


def _rpr(font_ascii=None, font_cs=None, bold=False, color=None,
         rtl=False, no_proof=False, web_hidden=False, r_style=None, sz=None):
    el = OxmlElement("w:rPr")
    if r_style:
        el.append(_make_el("w:rStyle", {qn("w:val"): r_style}))
    if font_ascii or font_cs:
        a = {}
        if font_ascii:
            a[qn("w:ascii")] = font_ascii
            a[qn("w:hAnsi")] = font_ascii
        if font_cs:
            a[qn("w:cs")] = font_cs
        el.append(_make_el("w:rFonts", a))
    if bold:
        el.append(OxmlElement("w:b"))
        el.append(OxmlElement("w:bCs"))
    if color:
        el.append(_make_el("w:color", {qn("w:val"): color}))
    if sz:
        el.append(_make_el("w:sz",   {qn("w:val"): str(sz)}))
        el.append(_make_el("w:szCs", {qn("w:val"): str(sz)}))
    if no_proof:
        el.append(OxmlElement("w:noProof"))
    if web_hidden:
        el.append(OxmlElement("w:webHidden"))
    if rtl:
        el.append(OxmlElement("w:rtl"))
    return el


def _r_text(text: str, **rpr_kw):
    r = OxmlElement("w:r")
    r.append(_rpr(**rpr_kw))
    t = OxmlElement("w:t")
    if text.startswith(" ") or text.endswith(" "):
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = text
    r.append(t)
    return r


def _r_tab(**rpr_kw):
    r = OxmlElement("w:r")
    r.append(_rpr(**rpr_kw))
    r.append(OxmlElement("w:tab"))
    return r


def _r_fld_begin():
    r = OxmlElement("w:r")
    r.append(_make_el("w:fldChar", {qn("w:fldCharType"): "begin"}))
    return r


def _r_fld_instr(instr: str):
    r = OxmlElement("w:r")
    el = OxmlElement("w:instrText")
    el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    el.text = instr
    r.append(el)
    return r


def _r_fld_sep(**rpr_kw):
    r = OxmlElement("w:r")
    if rpr_kw:
        r.append(_rpr(**rpr_kw))
    r.append(_make_el("w:fldChar", {qn("w:fldCharType"): "separate"}))
    return r


def _r_fld_end(**rpr_kw):
    r = OxmlElement("w:r")
    if rpr_kw:
        r.append(_rpr(**rpr_kw))
    r.append(_make_el("w:fldChar", {qn("w:fldCharType"): "end"}))
    return r


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def inject_toc_styles(doc, style: TocStyle, text_width_twips: int = 9016) -> None:
    """Inject TOCHeading, TOC1–TOC3, and Hyperlink styles into the document.

    text_width_twips: usable text column width in twips — drives tab stop placement.
    """
    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    styles_el = doc.styles.element

    for style_id in ("TOCHeading", "TOC1", "TOC2", "TOC3", "Hyperlink"):
        for existing in styles_el.findall(f"{{{W}}}style"):
            if existing.get(f"{{{W}}}styleId") == style_id:
                styles_el.remove(existing)

    # With w:bidi=1, jc=left renders physically RIGHT (RTL start). §17.18.44.
    # For LTR (no bidi), jc=left is physical left — also correct.
    jc_val = "left"
    bidi_tag = "<w:bidi/>" if style.rtl else ""
    rtl_run_tag = "<w:rtl/>" if style.rtl else ""

    # Tab stop just inside the right edge of the text column.
    # In RTL bidi Word interprets this position symmetrically, placing the
    # page number near the LEFT side with a dot leader to the right.
    # Keeping the same absolute position for all TOC levels (no per-level
    # offset) ensures the page numbers form a single vertical column.
    pg_tab = text_width_twips - 50

    new_styles_xml = f"""<root xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">

  <w:style w:type="paragraph" w:styleId="TOCHeading">
    <w:name w:val="TOC Heading"/>
    <w:basedOn w:val="Heading1"/>
    <w:next w:val="Normal"/>
    <w:uiPriority w:val="39"/>
    <w:unhideWhenUsed/>
    <w:qFormat/>
    <w:pPr>
      <w:shd w:val="clear" w:color="auto" w:fill="{style.heading_bg_color}"/>
      {bidi_tag}
      <w:spacing w:before="0" w:line="240" w:lineRule="auto"/>
      <w:ind w:left="0"/>
      <w:jc w:val="{jc_val}"/>
    </w:pPr>
    <w:rPr>
      <w:rFonts w:ascii="{style.heading_font}" w:hAnsi="{style.heading_font}" w:cs="{style.heading_font}"/>
      <w:b/>
      <w:bCs/>
      <w:color w:val="{style.heading_text_color}"/>
      {rtl_run_tag}
    </w:rPr>
  </w:style>

  <w:style w:type="paragraph" w:styleId="TOC1">
    <w:name w:val="toc 1"/>
    <w:basedOn w:val="Normal"/>
    <w:next w:val="Normal"/>
    <w:autoRedefine/>
    <w:uiPriority w:val="39"/>
    <w:unhideWhenUsed/>
    <w:pPr>
      <w:tabs>
        <w:tab w:val="right" w:leader="dot" w:pos="{pg_tab}"/>
      </w:tabs>
      {bidi_tag}
      <w:spacing w:after="100"/>
      <w:jc w:val="{jc_val}"/>
    </w:pPr>
    <w:rPr>
      <w:rFonts w:cs="{style.entry_font}"/>
    </w:rPr>
  </w:style>

  <w:style w:type="paragraph" w:styleId="TOC2">
    <w:name w:val="toc 2"/>
    <w:basedOn w:val="Normal"/>
    <w:next w:val="Normal"/>
    <w:autoRedefine/>
    <w:uiPriority w:val="39"/>
    <w:unhideWhenUsed/>
    <w:pPr>
      <w:tabs>
        <w:tab w:val="right" w:leader="dot" w:pos="{pg_tab}"/>
      </w:tabs>
      {bidi_tag}
      <w:spacing w:after="100"/>
      <w:jc w:val="{jc_val}"/>
    </w:pPr>
    <w:rPr>
      <w:rFonts w:cs="{style.entry_font}"/>
    </w:rPr>
  </w:style>

  <w:style w:type="paragraph" w:styleId="TOC3">
    <w:name w:val="toc 3"/>
    <w:basedOn w:val="Normal"/>
    <w:next w:val="Normal"/>
    <w:autoRedefine/>
    <w:uiPriority w:val="39"/>
    <w:unhideWhenUsed/>
    <w:pPr>
      <w:tabs>
        <w:tab w:val="right" w:leader="dot" w:pos="{pg_tab}"/>
      </w:tabs>
      {bidi_tag}
      <w:spacing w:after="100"/>
      <w:jc w:val="{jc_val}"/>
    </w:pPr>
    <w:rPr>
      <w:rFonts w:cs="{style.entry_font}"/>
    </w:rPr>
  </w:style>

  <w:style w:type="character" w:styleId="Hyperlink">
    <w:name w:val="Hyperlink"/>
    <w:basedOn w:val="DefaultParagraphFont"/>
    <w:uiPriority w:val="99"/>
    <w:unhideWhenUsed/>
    <w:rPr>
      <w:color w:val="0563C1"/>
      <w:u w:val="single"/>
    </w:rPr>
  </w:style>

</root>"""

    root = etree.fromstring(new_styles_xml.encode("utf-8"))
    for style_el in root:
        styles_el.append(style_el)


def make_toc_entry(anchor_id: str, title: str, level: int, style: TocStyle):
    """Build a <w:p> TOC entry paragraph for the given heading."""
    level = max(1, min(level, 3))
    style_id = f"TOC{level}"

    p = OxmlElement("w:p")

    pPr = OxmlElement("w:pPr")
    pPr.append(_make_el("w:pStyle", {qn("w:val"): style_id}))
    p.append(pPr)

    hl = OxmlElement("w:hyperlink")
    hl.set(qn("w:anchor"),  anchor_id)
    hl.set(qn("w:history"), "1")

    # Arabic title
    hl.append(_r_text(title, r_style="Hyperlink",
                      font_ascii=style.entry_font, font_cs=style.entry_font,
                      no_proof=True, rtl=style.rtl))

    # Tab before page number
    hl.append(_r_tab(no_proof=True, web_hidden=True))

    # PAGEREF field: begin / instr / sep / placeholder / end
    hl.append(_r_fld_begin())
    hl.append(_r_fld_instr(f" PAGEREF {anchor_id} \\h "))
    hl.append(_r_fld_sep(no_proof=True, web_hidden=True))
    hl.append(_r_text("1", no_proof=True, web_hidden=True, rtl=style.rtl))
    hl.append(_r_fld_end(no_proof=True, web_hidden=True))

    p.append(hl)
    return p


def build_toc_sdt(
    headings: list[tuple[str, int, str]],
    style: TocStyle,
):
    """Build the <w:sdt> element containing the full TOC.

    headings: list of (text, level, anchor_id)
    """
    sdt = OxmlElement("w:sdt")

    sdtPr = OxmlElement("w:sdtPr")
    docPartObj = OxmlElement("w:docPartObj")
    docPartObj.append(_make_el("w:docPartGallery", {qn("w:val"): "Table of Contents"}))
    docPartObj.append(OxmlElement("w:docPartUnique"))
    sdtPr.append(docPartObj)
    sdt.append(sdtPr)

    sdt.append(OxmlElement("w:sdtEndPr"))

    sdtContent = OxmlElement("w:sdtContent")

    # TOCHeading paragraph
    heading_p = OxmlElement("w:p")
    hPr = OxmlElement("w:pPr")
    hPr.append(_make_el("w:pStyle", {qn("w:val"): "TOCHeading"}))
    heading_p.append(hPr)

    h_run = OxmlElement("w:r")
    h_rPr = _rpr(font_ascii=style.heading_font, font_cs=style.heading_font,
                 color=style.heading_text_color, rtl=style.rtl)
    h_run.insert(0, h_rPr)
    t = OxmlElement("w:t")
    t.text = style.heading_text
    h_run.append(t)
    heading_p.append(h_run)
    sdtContent.append(heading_p)

    if not headings:
        sdt.append(sdtContent)
        return sdt

    entry_paragraphs = [
        make_toc_entry(anchor_id, text, level, style)
        for text, level, anchor_id in headings
    ]

    # Inject outer TOC field into the first entry paragraph
    first_p = entry_paragraphs[0]
    hl = first_p.find(qn("w:hyperlink"))
    idx = list(first_p).index(hl)
    first_p.insert(idx, _r_fld_sep())
    first_p.insert(idx, _r_fld_instr(' TOC \\o "1-3" \\h \\z \\u '))
    first_p.insert(idx, _r_fld_begin())

    for p in entry_paragraphs:
        sdtContent.append(p)

    # Close outer TOC field on last entry paragraph
    last_p = entry_paragraphs[-1]
    r_end = OxmlElement("w:r")
    r_end.append(_make_el("w:fldChar", {qn("w:fldCharType"): "end"}))
    last_p.append(r_end)

    sdt.append(sdtContent)
    return sdt
