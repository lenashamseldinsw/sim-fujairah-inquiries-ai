# sword-word-builder — API Reference

A fluent Python library for generating rich Word (`.docx`) documents programmatically. Supports English and Arabic/RTL content, native charts, styled tables, cover pages, headers/footers, markdown, images, and hyperlinks.

---

## Installation

```python
pip install sword-word-builder
```

## Quick Start

```python
from sword_word_builder import WordBuilder, DocumentConfig, TextStyle, TableStyle

builder = WordBuilder(DocumentConfig(default_font="Calibri"))
builder.add_heading("My Report", level=1)
builder.add_paragraph("This is the introduction.")
builder.add_table(
    [{"Name": "Alice", "Score": 95}, {"Name": "Bob", "Score": 82}]
)
builder.save("report.docx")
```

---

## Public API Overview

| Class / Object | Purpose |
|---|---|
| `WordBuilder` | Main document builder — all `add_*` methods |
| `DocumentConfig` | Document-level settings (fonts, margins, colors, headers/footers) |
| `TextStyle` | Per-element text formatting overrides |
| `TableStyle` | Table appearance (colors, borders, padding, widths) |
| `ChartStyle` | Chart appearance (size, colors, font sizes, legend) |
| `CellStyle` | Per-cell overrides inside a table |
| `CellLine` | One styled paragraph inside a multi-paragraph table cell |
| `TocStyle` | Table of Contents styling (font, colors, RTL) |
| `CoverPage` | Composable canvas for building cover pages |

---

## `DocumentConfig`

Document-level settings passed to `WordBuilder()`. All fields have defaults.

```python
from sword_word_builder import DocumentConfig

config = DocumentConfig(
    page_size="A4",          # "A4" | "Letter" | "A3"
    margin_top=2.54,         # cm
    margin_bottom=2.54,
    margin_left=3.17,
    margin_right=3.17,
    default_font="Calibri",
    default_font_size=11,    # pt
    default_rtl=False,
)
```

### Page Geometry

| Field | Type | Default | Description |
|---|---|---|---|
| `page_size` | `"A4"` \| `"Letter"` \| `"A3"` | `"A4"` | Page dimensions |
| `margin_top` | `float` | `2.54` | Top margin in cm |
| `margin_bottom` | `float` | `2.54` | Bottom margin in cm |
| `margin_left` | `float` | `3.17` | Left margin in cm |
| `margin_right` | `float` | `3.17` | Right margin in cm |

### Typography

| Field | Type | Default | Description |
|---|---|---|---|
| `default_font` | `str` | `"Calibri"` | Body font for all text |
| `default_font_size` | `int` | `11` | Body font size in pt |
| `default_rtl` | `bool` | `False` | Enable RTL/Arabic direction globally |
| `line_spacing` | `float \| None` | `None` | Exact line spacing in pt; `None` = single |
| `default_paragraph_space_after` | `float` | `6.0` | Space after each paragraph in pt |

### Colors

All colors are 6-character hex strings, with or without `#` prefix (e.g. `"2E74B5"` or `"#2E74B5"`).

| Field | Default | Used for |
|---|---|---|
| `accent_color` | `"2E74B5"` | Heading 1, Heading 3, table headers |
| `body_color` | `"000000"` | Body text |
| `heading_color` | `"2E74B5"` | Cover page title |
| `secondary_color` | `"003366"` | Heading 2, cover subtitle |

### Heading Typography

| Field | Type | Default | Description |
|---|---|---|---|
| `heading_font` | `str \| None` | `None` | Override heading font; `None` = `default_font` |
| `heading_bold` | `bool` | `True` | Bold headings |
| `heading1_size` | `int` | `22` | Heading 1 size in pt |
| `heading2_size` | `int` | `16` | Heading 2 size in pt |
| `heading3_size` | `int` | `13` | Heading 3 size in pt |
| `heading1_separator` | `bool` | `True` | Bottom border under Heading 1 |
| `heading2_separator` | `bool` | `False` | Bottom border under Heading 2 |
| `heading3_separator` | `bool` | `False` | Bottom border under Heading 3 |

### Header Configuration

| Field | Type | Default | Description |
|---|---|---|---|
| `header_type` | `str` | `"none"` | `"none"` \| `"page_number"` \| `"text"` \| `"image"` \| `"text_and_page_number"` |
| `header_text` | `str` | `""` | Text for `"text"` and `"text_and_page_number"` types |
| `header_image_path` | `str \| None` | `None` | Image file path for `"image"` type |
| `header_image_height_cm` | `float` | `1.5` | Image height in cm |
| `header_alignment` | `str` | `"CENTER"` | `"LEFT"` \| `"CENTER"` \| `"RIGHT"` |
| `header_text_color` | `str \| None` | `None` | Override text color; `None` = `body_color` |
| `header_font_size` | `int \| None` | `None` | Override font size; `None` = `default_font_size` |
| `header_bottom_border_color` | `str \| None` | `None` | Draw a bottom border under the header; `None` = no border |
| `header_spacing_after` | `float` | `0.0` | Space after header paragraph in pt |

### Footer Configuration

| Field | Type | Default | Description |
|---|---|---|---|
| `footer_type` | `str` | `"page_number"` | `"none"` \| `"page_number"` \| `"text"` \| `"image"` \| `"text_and_page_number"` |
| `footer_text` | `str` | `""` | Text for `"text"` and `"text_and_page_number"` types |
| `footer_image_path` | `str \| None` | `None` | Image file path for `"image"` type |
| `footer_image_height_cm` | `float` | `1.0` | Image height in cm |
| `footer_alignment` | `str` | `"CENTER"` | `"LEFT"` \| `"CENTER"` \| `"RIGHT"` |
| `footer_text_color` | `str \| None` | `None` | Override text color; `None` = `body_color` |
| `footer_font_size` | `int \| None` | `None` | Override font size; `None` = `default_font_size` |
| `footer_top_border_color` | `str \| None` | `None` | Draw a top border above the footer; `None` = no border |
| `footer_spacing_before` | `float` | `0.0` | Space before footer paragraph in pt |
| `skip_first_page_header_footer` | `bool` | `True` | Hide header/footer on the first page (cover page) |

### Arabic / RTL

| Field | Type | Default | Description |
|---|---|---|---|
| `apply_arabic_reshaping` | `bool` | `False` | Apply Unicode Arabic reshaping; most fonts don't need it |
| `arabic_auto_bold_phrases` | `list[str]` | See below | Phrases that are automatically bolded in Arabic paragraphs |

Default auto-bold phrases:
```
"الإطار الزمني:", "التأثير المتوقع:", "الموارد المطلوبة:", "الأولوية:", "النتيجة المتوقعة:"
```

### Full Example

```python
config = DocumentConfig(
    page_size="A4",
    default_font="Arial",
    default_font_size=11,
    default_rtl=True,          # Arabic document
    accent_color="0D2D5E",
    secondary_color="B89A00",
    heading1_size=20,
    heading1_separator=True,
    header_type="text",
    header_text="التقرير الرسمي",
    header_alignment="RIGHT",
    header_text_color="0D2D5E",
    header_font_size=9,
    header_bottom_border_color="B89A00",
    footer_type="text_and_page_number",
    footer_text="صفحة",
    footer_alignment="CENTER",
    footer_text_color="0D2D5E",
    footer_font_size=9,
    footer_top_border_color="0D2D5E",
    skip_first_page_header_footer=True,
)
builder = WordBuilder(config)
```

---

## `WordBuilder`

The main entry point. Instantiate with an optional `DocumentConfig`, then call `add_*` methods in any order, and finish with `save()` or `build()`.

```python
builder = WordBuilder()                        # default config
builder = WordBuilder(DocumentConfig(...))     # custom config
```

All `add_*` methods return `self`, enabling optional method chaining:

```python
builder.add_heading("Title").add_paragraph("Body text.").save("out.docx")
```

---

### `add_heading(text, level=1, style=None, rtl=None, separator=None)`

Add a heading at levels 1–6. Levels 1–3 have configured sizes and colors from `DocumentConfig`; levels 4–6 fall back to `default_font_size + 2` pt and `accent_color` with no separator support.

| Param | Type | Default | Description |
|---|---|---|---|
| `text` | `str` | — | Heading text |
| `level` | `int` | `1` | Heading level 1–6 |
| `style` | `TextStyle \| None` | `None` | Style overrides |
| `rtl` | `bool \| None` | `None` | Override RTL direction; `None` inherits `DocumentConfig.default_rtl` |
| `separator` | `bool \| None` | `None` | Draw bottom border; `None` uses `DocumentConfig.heading{level}_separator` |

Colors and sizes come from `DocumentConfig`: level 1 and 3 use `accent_color`, level 2 uses `secondary_color`.

```python
builder.add_heading("Chapter 1: Introduction", level=1)
builder.add_heading("Background", level=2)
builder.add_heading("النتائج الرئيسية", level=1, rtl=True)
builder.add_heading("Section Title", level=1, separator=True)  # force separator
builder.add_heading("Small Section", level=3,
                    style=TextStyle(color="FF0000", size=15))
```

---

### `add_paragraph(text, style=None, rtl=None, bold=False, italic=False, alignment=None, space_after=None, keep_with_next=False)`

Add a body paragraph.

| Param | Type | Default | Description |
|---|---|---|---|
| `text` | `str` | — | Paragraph text |
| `style` | `TextStyle \| None` | `None` | Full style override |
| `rtl` | `bool \| None` | `None` | RTL direction |
| `bold` | `bool` | `False` | Bold shorthand |
| `italic` | `bool` | `False` | Italic shorthand |
| `alignment` | `str \| None` | `None` | `"LEFT"` \| `"CENTER"` \| `"RIGHT"` \| `"JUSTIFY"` |
| `space_after` | `float \| None` | `None` | Space after in pt; `None` = config default |
| `keep_with_next` | `bool` | `False` | Keep with the next paragraph (prevents orphaned headings) |

```python
builder.add_paragraph("This is body text.")
builder.add_paragraph("Bold and centered", bold=True, alignment="CENTER")
builder.add_paragraph("هذا نص عربي", rtl=True)
builder.add_paragraph(
    "Styled text",
    style=TextStyle(font="Georgia", size=13, color="333333", italic=True),
)
builder.add_paragraph("Caption text", space_after=2.0)
```

---

### `add_markdown(markdown_text, rtl=None, base_style=None)`

Render a markdown string into the document. Supports headings (`#` through `######`, capped at level 3 styling), bold (`**`), italic (`*`), bold+italic (`***`), inline links (`[text](url)`), bare URLs, bullet lists (`-`, `*`, `•`), and numbered lists.

> **Note:** `---` is **not** a horizontal rule — it renders as the literal text `---`. Use `add_horizontal_separator()` instead.
>
> RTL paragraphs and numbered list items are always `JUSTIFY`-aligned regardless of `base_style`.
>
> The `base_style` parameter is accepted but currently has no effect.

| Param | Type | Default | Description |
|---|---|---|---|
| `markdown_text` | `str` | — | Markdown source |
| `rtl` | `bool \| None` | `None` | RTL direction for all rendered elements |
| `base_style` | `TextStyle \| None` | `None` | Reserved — currently unused |

```python
builder.add_markdown("""
# Section Title

This is a paragraph with **bold text**, *italic text*, and ***bold italic***.

- First bullet item
- Second bullet item

1. Numbered first
2. Numbered second

Visit [our site](https://example.com) or https://example.com
""")
```

---

### `add_hyperlink(url, display_text, paragraph=None, rtl=None)`

Add a clickable hyperlink. By default, creates a new paragraph. Arabic display text is auto-detected and made RTL.

| Param | Type | Default | Description |
|---|---|---|---|
| `url` | `str` | — | The target URL |
| `display_text` | `str` | — | Visible link text |
| `paragraph` | paragraph object \| `None` | `None` | Existing paragraph to append to |
| `rtl` | `bool \| None` | `None` | RTL override |

```python
builder.add_hyperlink("https://example.com", "Visit our website")
builder.add_hyperlink("https://example.com", "زيارة موقعنا")   # auto RTL
```

---

### `add_table(data, headers=None, style=None, rtl=None, caption=None, table_type="data")`

Add a table. Accepts multiple data formats.

| Param | Type | Default | Description |
|---|---|---|---|
| `data` | `list[dict]` \| `list[list]` \| `list[tuple]` \| `dict` | — | Table data (`dict` supported for `table_type="metrics"`) |
| `headers` | `list[str] \| None` | `None` | Column header labels; required for `list[list]` |
| `style` | `TableStyle \| None` | `None` | Table styling |
| `rtl` | `bool \| None` | `None` | RTL direction |
| `caption` | `str \| None` | `None` | Caption text below the table |
| `table_type` | `"data"` \| `"metrics"` | `"data"` | `"metrics"` for label-value pairs |

#### Data formats

**`list[dict]`** — headers auto-extracted from keys:
```python
builder.add_table([
    {"Name": "Alice", "Score": 95, "Grade": "A"},
    {"Name": "Bob",   "Score": 82, "Grade": "B"},
])
```

**`list[list]` or `list[tuple]`** — requires `headers=`:
```python
builder.add_table(
    [["Alice", 95, "A"], ["Bob", 82, "B"]],
    headers=["Name", "Score", "Grade"],
)
```

**`"metrics"` table** — label/value pairs. The label column (0) is always right-aligned and the value column (1) is always left-aligned; `TableStyle.text_alignment` has no effect on metrics tables.

```python
builder.add_table(
    {"Total Cases": 1024, "Resolved": 987, "Pending": 37},
    table_type="metrics",
    headers=["Metric", "Value"],  # override default "Label"/"Value"
)
# or as list of tuples:
builder.add_table(
    [("Total Cases", 1024), ("Resolved", 987)],
    table_type="metrics",
)
```

#### Per-cell styling with `CellStyle`

Wrap any cell value as `(value, CellStyle(...))` to override colors, bold, and font size for that specific cell:

```python
from sword_word_builder import CellStyle

builder.add_table([
    {
        "Status": ("Pass ✔", CellStyle(bg_color="1E7B4E", text_color="FFFFFF", bold=True)),
        "Score":  (95, CellStyle(bold=True)),
        "Note":   "Excellent",
    },
    {
        "Status": ("Fail ✗", CellStyle(bg_color="C00000", text_color="FFFFFF")),
        "Score":  (42, CellStyle(text_color="C00000")),
        "Note":   "Needs improvement",
    },
])
```

#### Multi-paragraph cells with `CellLine`

Use a `list[CellLine]` as a cell value to stack multiple paragraphs inside one cell (useful for KPI tiles):

```python
from sword_word_builder import CellLine, TableStyle

builder.add_table(
    data=[],
    headers=[[
        [CellLine("1,024", font_size=22, bold=True, color="FFFFFF", alignment="CENTER"),
         CellLine("Total Cases", font_size=9, color="CCCCCC", alignment="CENTER")],
        [CellLine("987",  font_size=22, bold=True, color="FFFFFF", alignment="CENTER"),
         CellLine("Resolved",    font_size=9, color="CCCCCC", alignment="CENTER")],
        [CellLine("37",   font_size=22, bold=True, color="FFFFFF", alignment="CENTER"),
         CellLine("Pending",     font_size=9, color="CCCCCC", alignment="CENTER")],
    ]],
    style=TableStyle(
        header_bg_color="0D2D5E",
        header_bg_colors=["0D2D5E", "1A5276", "117A65"],  # per-column colors
        show_inner_borders=False,
        show_outer_border=False,
        table_alignment="CENTER",
        column_widths=[1/3, 1/3, 1/3],
    ),
)
```

**Key pattern**: Put CellLine data in `headers=[]` with `data=[]` to produce a single header row — this avoids creating an extra data row from dict key extraction.

#### With a caption

```python
builder.add_table(data, caption="Table 1: Monthly Performance")
```

---

### `add_chart(data, chart_type="column", style=None, rtl=None)`

Add a native Word chart, fully editable in Word with embedded Excel data.

| Param | Type | Default | Description |
|---|---|---|---|
| `data` | `dict` | — | Chart data (see format below) |
| `chart_type` | `str` | `"column"` | `"column"` \| `"bar"` \| `"line"` \| `"pie"` |
| `style` | `ChartStyle \| None` | `None` | Chart appearance |
| `rtl` | `bool \| None` | `None` | RTL direction |

#### Chart data format

```python
{
    "title": "Monthly Revenue",        # optional chart title
    "categories": ["Jan", "Feb", "Mar", "Apr"],
    "series": [
        {
            "name": "Revenue",
            "values": [120, 145, 132, 158],
            "color": "4472C4",         # single hex color for the whole series
        },
        {
            "name": "Target",
            "values": [130, 130, 140, 150],
            "color": "ED7D31",
        },
    ],
}
```

#### Per-bar / per-slice colors

Set `"color"` to a `list[str]` to assign a different color to each bar (or pie slice). The list cycles if shorter than the values list:

```python
{
    "title": "Cases by Category",
    "categories": ["Theft", "Fraud", "Traffic", "Other"],
    "series": [
        {
            "name": "Cases",
            "values": [320, 215, 480, 95],
            "color": ["4472C4", "ED7D31", "A9D18E", "FFC000"],  # one color per bar
        }
    ],
}
```

Cycling example — 2 colors, 4 bars (colors repeat):
```python
"color": ["4472C4", "ED7D31"]  # bar 0=blue, 1=orange, 2=blue, 3=orange
```

#### Pie chart

For pie charts, use `series_colors` in `ChartStyle` to set slice colors, **or** use the per-bar `list[str]` color on the single series:

```python
builder.add_chart(
    {
        "title": "Age Distribution",
        "categories": ["18-30", "31-45", "46-60", "60+"],
        "series": [{"name": "Count", "values": [320, 450, 180, 95]}],
    },
    chart_type="pie",
    style=ChartStyle(
        series_colors=["4472C4", "ED7D31", "A9D18E", "FFC000"],
        show_data_labels=True,
        show_legend=True,
        legend_position="r",
        width_cm=12,
        height_cm=8,
    ),
)
```

#### Full column chart example

```python
from sword_word_builder import ChartStyle

builder.add_chart(
    {
        "title": "Quarterly Performance",
        "categories": ["Q1", "Q2", "Q3", "Q4"],
        "series": [
            {"name": "Revenue", "values": [120, 145, 132, 158], "color": "4472C4"},
            {"name": "Expenses", "values": [95, 110, 102, 115], "color": "ED7D31"},
        ],
    },
    chart_type="column",
    style=ChartStyle(
        width_cm=14,
        height_cm=9,
        show_legend=True,
        legend_position="b",    # "r" | "l" | "t" | "b"
        show_data_labels=False,
        show_gridlines=True,
        x_axis_title="Quarter",
        y_axis_title="USD (thousands)",
        title_font_size=14,
        axis_font_size=10,
        legend_font_size=10,
    ),
)
```

---

### `add_picture(image_path, width_cm=None, height_cm=None, alignment="CENTER", caption=None)`

Insert an image file.

| Param | Type | Default | Description |
|---|---|---|---|
| `image_path` | `str \| Path` | — | Path to image file (PNG, JPG, etc.) |
| `width_cm` | `float \| None` | `None` | Width in cm; `None` = original size |
| `height_cm` | `float \| None` | `None` | Height in cm |
| `alignment` | `str` | `"CENTER"` | `"LEFT"` \| `"CENTER"` \| `"RIGHT"` |
| `caption` | `str \| None` | `None` | Caption text below image |

At least one of `width_cm` / `height_cm` should be set to avoid oversized images. Aspect ratio is preserved when only one dimension is specified.

```python
builder.add_picture("logo.png", width_cm=6, alignment="CENTER")
builder.add_picture("chart_export.png", width_cm=14, caption="Figure 1: Monthly trend")
builder.add_picture("photo.jpg", height_cm=8)
```

---

### `add_banner(text, bg_color="2E74B5", text_color="FFFFFF", font_size=14, bold=True, rtl=None)`

Add a full-width single-row colored banner, typically used as a section separator.

| Param | Type | Default | Description |
|---|---|---|---|
| `text` | `str` | — | Banner label text |
| `bg_color` | `str` | `"2E74B5"` | Background hex color |
| `text_color` | `str` | `"FFFFFF"` | Text hex color |
| `font_size` | `int` | `14` | Font size in pt |
| `bold` | `bool` | `True` | Bold text |
| `rtl` | `bool \| None` | `None` | RTL direction; `None` inherits `DocumentConfig.default_rtl` |

```python
builder.add_banner("Section 1: Demographics")
builder.add_banner(
    "أولاً  التحليل الديموغرافي",
    bg_color="0D2D5E",
    text_color="B89A00",
    rtl=True,
)
builder.add_banner("Executive Summary", bg_color="1A5276", font_size=16)
```

---

### `add_horizontal_separator(color=None, native=False)`

Add a visual separator line.

| Param | Type | Default | Description |
|---|---|---|---|
| `color` | `str \| None` | `None` | Hex color; `None` = `body_color` |
| `native` | `bool` | `False` | `True` = real Word paragraph border (cleaner in print/PDF); `False` = 50 Unicode `─` chars |

```python
builder.add_horizontal_separator()                          # Unicode dashes
builder.add_horizontal_separator(native=True)               # Word border
builder.add_horizontal_separator(native=True, color="2E74B5")
```

---

### `add_spacer(height_pt=12.0)`

Insert an empty paragraph for vertical spacing.

```python
builder.add_spacer()           # 12pt gap
builder.add_spacer(24.0)       # 24pt gap
builder.add_spacer(5)          # 5pt gap
```

---

### `add_page_break()`

Insert a hard page break.

```python
builder.add_page_break()
```

---

### `add_section(orientation="portrait")`

Add a new section break (useful for mixing portrait and landscape pages).

> **Note:** New sections inherit page margins from `DocumentConfig` but get no header or footer. Neither `DocumentConfig` header/footer settings nor `set_header()`/`set_footer()` apply to sections added here.

```python
builder.add_section(orientation="landscape")
# ... add wide tables or charts ...
builder.add_section(orientation="portrait")
```

---

### `set_header(header_type, text="", image_path=None, image_height_cm=1.5, alignment="CENTER", skip_first_page=None)`

Override the header after construction (overrides `DocumentConfig` defaults).

> **Note:** Only configures the first section (`sections[0]`). Headers for additional sections added via `add_section()` are not set and will be blank.

```python
builder.set_header(header_type="text", text="Confidential", alignment="RIGHT")
builder.set_header(header_type="image", image_path="letterhead.png", image_height_cm=2)
builder.set_header(header_type="page_number", alignment="CENTER")
```

---

### `set_footer(footer_type, text="", image_path=None, image_height_cm=1.0, alignment="CENTER", skip_first_page=None)`

Override the footer after construction.

> **Note:** Only configures the first section (`sections[0]`). Footers for additional sections added via `add_section()` are not set and will be blank.

```python
builder.set_footer(footer_type="page_number", alignment="CENTER")
builder.set_footer(footer_type="text_and_page_number", text="Page", alignment="CENTER")
builder.set_footer(footer_type="text", text="© 2025 My Company")
```

---

### `add_toc(style=None)`

Add a Table of Contents placeholder at the current position. The TOC is automatically populated with all headings added via `add_heading()` and rendered during `save()` / `build()`. A page break is inserted after the TOC automatically.

| Param | Type | Default | Description |
|---|---|---|---|
| `style` | `TocStyle \| None` | `None` | TOC appearance; `None` uses `TocStyle` defaults |

```python
from sword_word_builder import TocStyle

builder.add_toc()   # default Arabic RTL style

# Custom style
builder.add_toc(TocStyle(
    heading_text="Contents",
    heading_bg_color="2E74B5",
    heading_text_color="FFFFFF",
    heading_font="Calibri",
    entry_font="Calibri",
    levels=2,
    rtl=False,
))
```

The TOC is placed wherever `add_toc()` is called. Add it after the cover page and before content headings:

```python
builder.add_cover_page(cover)
builder.add_toc()             # appears on its own page before chapter content
builder.add_heading("Chapter 1", level=1)
```

---

### `add_cover_page(cover)`

Render a `CoverPage` canvas into the document and append an automatic page break.

```python
cover = CoverPage()
cover.add_spacer(40)
cover.add_heading("Annual Report 2025", level=1,
                  style=TextStyle(size=32, alignment="CENTER"))
cover.add_horizontal_separator(native=True)
cover.add_paragraph("Strategy & Planning Division",
                     style=TextStyle(size=14, italic=True, alignment="CENTER"))
builder.add_cover_page(cover)
```

---

### `save(path)` / `build()`

```python
builder.save("output.docx")          # write to file

buf = builder.build()                 # returns io.BytesIO
with open("output.docx", "wb") as f:
    f.write(buf.read())
```

---

## `TextStyle`

Per-element text style override. `None` values inherit from `DocumentConfig`.

```python
from sword_word_builder import TextStyle

style = TextStyle(
    font="Georgia",
    size=14,               # pt
    bold=True,
    italic=False,
    underline=False,
    color="2E74B5",        # 6-char hex
    alignment="CENTER",    # "LEFT" | "CENTER" | "RIGHT" | "JUSTIFY"
    rtl=None,              # None = inherit DocumentConfig.default_rtl
    space_before=6.0,      # pt
    space_after=6.0,       # pt
    keep_with_next=False,
)
```

| Field | Type | Default | Description |
|---|---|---|---|
| `font` | `str \| None` | `None` | Font name; `None` = `default_font` |
| `size` | `int \| None` | `None` | Font size in pt |
| `bold` | `bool` | `False` | Bold |
| `italic` | `bool` | `False` | Italic |
| `underline` | `bool` | `False` | Underline |
| `color` | `str \| None` | `None` | Text color (hex); `None` = `body_color` |
| `alignment` | `str` | `"LEFT"` | Paragraph alignment |
| `rtl` | `bool \| None` | `None` | RTL override |
| `space_before` | `float \| None` | `None` | Space before in pt |
| `space_after` | `float \| None` | `None` | Space after in pt |
| `keep_with_next` | `bool` | `False` | Keep with next paragraph |

```python
# Usage examples
builder.add_paragraph("Large red text",
                       style=TextStyle(size=18, color="C00000", bold=True))
builder.add_heading("Centered heading",
                    style=TextStyle(alignment="CENTER"))
builder.add_paragraph("Justified body text",
                       style=TextStyle(alignment="JUSTIFY", space_after=8.0))
```

---

## `TableStyle`

Controls the visual appearance of a table.

```python
from sword_word_builder import TableStyle

style = TableStyle(
    header_bg_color="2E74B5",      # header row background
    header_text_color="FFFFFF",
    header_bold=True,
    header_font_size=11,           # None = document default
    header_bg_colors=None,         # per-column header bg (list, one per column)

    row_bg_color="FFFFFF",
    alt_row_bg_color="D6E4F7",     # None to disable alternating rows
    cell_text_color="000000",

    border_color="BFBFBF",
    border_width_pt=0.5,
    show_inner_borders=True,
    show_outer_border=True,

    cell_padding_top=3.0,          # pt
    cell_padding_bottom=3.0,
    cell_padding_left=5.4,
    cell_padding_right=5.4,

    column_widths=None,            # [0.2, 0.5, 0.3] = fractions summing to ≤ 1.0
    font_size=None,                # cell font size; None = document default
    text_alignment="LEFT",         # cell text alignment
    auto_align_numbers=True,       # right-align int/float values automatically
    rtl=None,                      # None = inherit DocumentConfig.default_rtl

    table_alignment="LEFT",        # "LEFT" | "CENTER" | "RIGHT"
    metrics_label_bold=False,      # bold the label column in metrics tables
)
```

### Key fields explained

**`column_widths`** — list of fractions (must sum ≤ 1.0). Omit for equal column widths:
```python
column_widths=[0.45, 0.275, 0.275]   # 45% / 27.5% / 27.5%
column_widths=[0.2, 0.4, 0.2, 0.2]  # 4-column table
```

**`header_bg_colors`** — per-column header background override. Useful for KPI tiles where each column has a distinct color:
```python
header_bg_colors=["0D2D5E", "1A5276", "117A65", "1E8449"]
```

**`alt_row_bg_color`** — set `None` to disable alternating row colors:
```python
alt_row_bg_color=None        # solid white rows
alt_row_bg_color="F4F8FD"    # subtle light blue alternating
```

**`table_alignment`** — controls horizontal table position on the page:
```python
table_alignment="CENTER"     # center-align the table
```

**`auto_align_numbers`** — automatically right-aligns integer and float values:
```python
auto_align_numbers=True   # default: numbers right-aligned, strings left-aligned
```

### Common presets

**Borderless banner / KPI table:**
```python
TableStyle(
    header_bg_color="0D2D5E",
    header_text_color="FFFFFF",
    show_inner_borders=False,
    show_outer_border=False,
    alt_row_bg_color=None,
    table_alignment="CENTER",
)
```

**Minimal data table:**
```python
TableStyle(
    header_bg_color="F2F2F2",
    header_text_color="000000",
    row_bg_color="FFFFFF",
    alt_row_bg_color=None,
    border_color="CCCCCC",
    border_width_pt=0.5,
)
```

**RTL Arabic table:**
```python
TableStyle(
    header_bg_color="0D2D5E",
    header_text_color="FFFFFF",
    text_alignment="RIGHT",
    rtl=True,
    column_widths=[0.25, 0.25, 0.25, 0.25],
)
```

---

## `ChartStyle`

Controls the visual appearance and typography of charts.

```python
from sword_word_builder import ChartStyle

style = ChartStyle(
    width_cm=14.0,
    height_cm=9.0,
    show_legend=True,
    legend_position="r",           # "r" | "l" | "t" | "b"
    show_data_labels=False,
    show_gridlines=True,

    series_colors=["4472C4", "ED7D31", "A9D18E", "FFC000", "FF0000", "00B0F0"],

    x_axis_title=None,
    y_axis_title=None,
    background_color="FFFFFF",
    font=None,                     # None = document default font

    title_font_size=None,          # pt; chart title text
    axis_font_size=None,           # pt; axis tick labels and category labels
    legend_font_size=None,         # pt; legend entry labels
)
```

| Field | Type | Default | Description |
|---|---|---|---|
| `width_cm` | `float` | `14.0` | Chart width in cm |
| `height_cm` | `float` | `9.0` | Chart height in cm |
| `show_legend` | `bool` | `True` | Display the legend |
| `legend_position` | `str` | `"r"` | Legend position: `"r"` right, `"l"` left, `"t"` top, `"b"` bottom |
| `show_data_labels` | `bool` | `False` | Show value labels on bars/lines/slices |
| `show_gridlines` | `bool` | `True` | Show gridlines on value axis |
| `series_colors` | `list[str]` | 6 blues/oranges | Cycle of hex colors applied to each series. Also used as pie slice colors. |
| `x_axis_title` | `str \| None` | `None` | Label below the category axis |
| `y_axis_title` | `str \| None` | `None` | Label beside the value axis |
| `background_color` | `str` | `"FFFFFF"` | Chart plot area background |
| `font` | `str \| None` | `None` | Font for all chart text; `None` = document default |
| `title_font_size` | `int \| None` | `None` | Font size in pt for the chart title |
| `axis_font_size` | `int \| None` | `None` | Font size in pt for axis tick/category labels |
| `legend_font_size` | `int \| None` | `None` | Font size in pt for legend entries |

```python
# Compact chart with custom font sizes
builder.add_chart(data, chart_type="bar", style=ChartStyle(
    width_cm=12,
    height_cm=7,
    title_font_size=13,
    axis_font_size=9,
    legend_font_size=9,
    show_data_labels=True,
    series_colors=["0D2D5E", "B89A00", "117A65"],
))
```

---

## `TocStyle`

Styling for a Table of Contents created via `WordBuilder.add_toc()`.

```python
from sword_word_builder import TocStyle

style = TocStyle(
    heading_text="المحتويات",     # TOC heading label
    heading_bg_color="B68A35",    # heading row background
    heading_text_color="FFFFFF",  # heading text color
    heading_font="TheSans",       # font for the TOC heading
    entry_font="Sakkal Majalla",  # font for TOC entries
    levels=3,                     # reserved — currently unused
    rtl=True,                     # RTL layout for Arabic TOCs
)
```

| Field | Type | Default | Description |
|---|---|---|---|
| `heading_text` | `str` | `"المحتويات"` | Label displayed as the TOC heading |
| `heading_bg_color` | `str` | `"B68A35"` | Background hex color for the TOC heading paragraph |
| `heading_text_color` | `str` | `"FFFFFF"` | Text hex color for the TOC heading |
| `heading_font` | `str` | `"TheSans"` | Font for the TOC heading |
| `entry_font` | `str` | `"Sakkal Majalla"` | Font for TOC entry lines |
| `levels` | `int` | `3` | Reserved — currently unused; the TOC always includes levels 1–3 |
| `rtl` | `bool` | `True` | RTL direction for the TOC (set `False` for English documents) |

```python
# English document TOC
builder.add_toc(TocStyle(
    heading_text="Table of Contents",
    heading_bg_color="2E74B5",
    heading_text_color="FFFFFF",
    heading_font="Calibri",
    entry_font="Calibri",
    levels=3,
    rtl=False,
))
```

---

## `CellStyle`

Per-cell style override. Wrap any cell value as `(value, CellStyle(...))`.

```python
from sword_word_builder import CellStyle

CellStyle(
    bg_color=None,       # 6-char hex; overrides row background for this cell
    text_color=None,     # 6-char hex; overrides cell_text_color
    bold=None,           # True/False/None; None = table default
    font_size=None,      # pt; None = table default
)
```

Only non-`None` fields are applied. Unset fields fall back to the enclosing `TableStyle`.

```python
# Status column with color-coded cells
data = [
    {
        "Name": "Alice",
        "Score": (95, CellStyle(bold=True)),
        "Status": ("Pass ✔", CellStyle(bg_color="1E7B4E", text_color="FFFFFF", bold=True)),
    },
    {
        "Name": "Bob",
        "Score": (42, CellStyle(text_color="C00000")),
        "Status": ("Fail ✗", CellStyle(bg_color="C00000", text_color="FFFFFF", bold=True)),
    },
]
builder.add_table(data)
```

---

## `CellLine`

One styled paragraph inside a multi-paragraph cell. Use a `list[CellLine]` as a cell value to stack multiple lines with independent typography.

```python
from sword_word_builder import CellLine

CellLine(
    text="",                  # paragraph text
    font_size=None,           # pt; None = TableStyle.font_size
    color=None,               # hex; None = TableStyle.cell_text_color
    bold=None,                # None = False
    italic=None,              # None = False
    alignment=None,           # "LEFT" | "CENTER" | "RIGHT" | "JUSTIFY"; None = TableStyle.text_alignment
    rtl=None,                 # None = table/document rtl
)
```

#### KPI tile pattern

The most common use case is a metric card with a large number and a small label:

```python
kpi_cell = [
    CellLine("1,024", font_size=24, bold=True, color="FFFFFF", alignment="CENTER"),
    CellLine("Total Cases", font_size=9, color="CCCCCC", alignment="CENTER"),
]
```

Combined with the `data=[], headers=[...]` pattern for full control:

```python
from sword_word_builder import CellLine, TableStyle

def kpi(number, label):
    return [
        CellLine(number, font_size=22, bold=True, color="FFFFFF", alignment="CENTER"),
        CellLine(label,  font_size=9,  color="CCCCCC",           alignment="CENTER"),
    ]

builder.add_table(
    data=[],
    headers=[[kpi("1,024", "Total"), kpi("987", "Resolved"), kpi("37", "Pending")]],
    style=TableStyle(
        header_bg_colors=["0D2D5E", "1A5276", "117A65"],
        show_inner_borders=False,
        show_outer_border=False,
        cell_padding_top=12, cell_padding_bottom=12,
        table_alignment="CENTER",
        column_widths=[1/3, 1/3, 1/3],
    ),
)
```

---

## `CoverPage`

A composable canvas for building a cover page. Mirrors the full `WordBuilder` content API — all components can be placed in any order. Operations are deferred and executed when `builder.add_cover_page(cover)` is called.

### Free-form canvas

```python
from sword_word_builder import CoverPage, TextStyle, TableStyle, CellLine

cover = CoverPage()

# Logo at top
cover.add_picture("logo.png", width_cm=4, alignment="CENTER")
cover.add_spacer(30)

# Title
cover.add_heading(
    "Annual Performance Report 2025",
    level=1,
    style=TextStyle(size=28, alignment="CENTER"),
)
cover.add_horizontal_separator(native=True, color="2E74B5")

# Subtitle
cover.add_paragraph(
    "Strategy & Planning Division",
    style=TextStyle(size=14, italic=True, alignment="CENTER", color="555555"),
)
cover.add_spacer(20)

# KPI summary table
cover.add_table(
    data=[],
    headers=[[
        [CellLine("2,450", font_size=20, bold=True, color="FFFFFF", alignment="CENTER"),
         CellLine("Total Records", font_size=9, color="CCCCCC", alignment="CENTER")],
        [CellLine("94.2%", font_size=20, bold=True, color="FFFFFF", alignment="CENTER"),
         CellLine("Completion Rate", font_size=9, color="CCCCCC", alignment="CENTER")],
    ]],
    style=TableStyle(
        header_bg_colors=["0D2D5E", "1A5276"],
        show_inner_borders=False,
        show_outer_border=False,
        table_alignment="CENTER",
        cell_padding_top=12, cell_padding_bottom=12,
        column_widths=[0.5, 0.5],
    ),
)

cover.add_spacer(20)
cover.add_paragraph(
    "January 2025",
    style=TextStyle(size=12, alignment="CENTER", color="888888"),
)

builder.add_cover_page(cover)
```

### Preset layout

```python
cover = CoverPage.preset(
    title="Quarterly Report Q1 2025",
    subtitle="Operations Division",
    metadata={
        "Author": "Data Analytics Team",
        "Date": "January 2025",
        "Classification": "Internal",
    },
)
builder.add_cover_page(cover)
```

The preset produces: 5 spacer paragraphs → large centered title → decorative `━━ ◆ ━━` separator → subtitle → 3 spacers → metadata key-value rows.

### Available methods on `CoverPage`

All methods mirror their `WordBuilder` equivalents:

- `add_spacer(height_pt)`
- `add_heading(text, level, style, rtl, separator)`
- `add_paragraph(text, style, rtl, bold, italic, alignment, space_after, keep_with_next)`
- `add_markdown(markdown_text, rtl, base_style)`
- `add_hyperlink(url, display_text, rtl)`
- `add_picture(image_path, width_cm, height_cm, alignment, caption)`
- `add_table(data, headers, style, rtl, caption, table_type)`
- `add_chart(data, chart_type, style, rtl)`
- `add_horizontal_separator(color, native)`
- `add_banner(text, bg_color, text_color, font_size, bold, rtl)`
- `add_page_break()` — inserts an extra break within the cover canvas (note: `add_cover_page` already appends one break after the canvas)

---

## Complete Examples

### English report with charts and tables

```python
from sword_word_builder import (
    WordBuilder, DocumentConfig, TextStyle, TableStyle, ChartStyle, CoverPage
)

config = DocumentConfig(
    default_font="Calibri",
    accent_color="2E74B5",
    header_type="text",
    header_text="Confidential",
    header_alignment="RIGHT",
    footer_type="page_number",
    skip_first_page_header_footer=True,
)
builder = WordBuilder(config)

# Cover page
cover = CoverPage.preset(
    "Sales Performance Report",
    subtitle="Q1 2025",
    metadata={"Author": "Analytics Team", "Date": "March 2025"},
)
builder.add_cover_page(cover)

# Section
builder.add_heading("Executive Summary", level=1)
builder.add_paragraph(
    "This report covers Q1 2025 performance across all regions.",
    style=TextStyle(alignment="JUSTIFY"),
)

# Table
builder.add_table(
    [
        {"Region": "North", "Revenue": 1_200_000, "Target": 1_100_000, "Achievement": "109%"},
        {"Region": "South", "Revenue":   980_000, "Target": 1_000_000, "Achievement":  "98%"},
        {"Region": "East",  "Revenue": 1_450_000, "Target": 1_300_000, "Achievement": "112%"},
    ],
    style=TableStyle(column_widths=[0.3, 0.25, 0.25, 0.2], table_alignment="CENTER"),
    caption="Table 1: Regional Revenue vs Target",
)

# Chart
builder.add_chart(
    {
        "title": "Revenue by Region",
        "categories": ["North", "South", "East"],
        "series": [
            {"name": "Revenue", "values": [1_200, 980, 1_450], "color": "4472C4"},
            {"name": "Target",  "values": [1_100, 1_000, 1_300], "color": "ED7D31"},
        ],
    },
    chart_type="column",
    style=ChartStyle(width_cm=14, height_cm=8, show_data_labels=True, legend_position="b"),
)

builder.save("sales_report.docx")
```

---

### Arabic (RTL) report

```python
from sword_word_builder import (
    WordBuilder, DocumentConfig, TextStyle, TableStyle, CoverPage, CellLine
)

config = DocumentConfig(
    default_font="Arial",
    default_rtl=True,
    accent_color="0D2D5E",
    secondary_color="B89A00",
    header_type="text",
    header_text="الشرطة - سري",
    header_alignment="RIGHT",
    header_text_color="0D2D5E",
    header_font_size=9,
    header_bottom_border_color="B89A00",
    footer_type="text_and_page_number",
    footer_text="صفحة",
    footer_alignment="CENTER",
    footer_text_color="0D2D5E",
    footer_font_size=9,
    footer_top_border_color="0D2D5E",
    skip_first_page_header_footer=True,
)
builder = WordBuilder(config)

# Cover
cover = CoverPage()
cover.add_spacer(40)
cover.add_heading(
    "تقرير الأداء السنوي 2025",
    level=1,
    style=TextStyle(size=28, alignment="CENTER"),
    rtl=True,
)
cover.add_horizontal_separator(native=True, color="B89A00")
cover.add_paragraph(
    "إدارة التخطيط والاستراتيجية",
    style=TextStyle(size=14, italic=True, alignment="CENTER"),
    rtl=True,
)
builder.add_cover_page(cover)

# Section banner
builder.add_banner("أولاً  التحليل الديموغرافي", bg_color="0D2D5E", text_color="B89A00", rtl=True)

# Data table
builder.add_table(
    [
        {"الفئة": "18-30", "العدد": 320, "النسبة": "29.2%"},
        {"الفئة": "31-45", "العدد": 450, "النسبة": "41.1%"},
        {"الفئة": "46-60", "العدد": 218, "النسبة": "19.9%"},
        {"الفئة": "60+",   "العدد": 107, "النسبة": "9.8%"},
    ],
    style=TableStyle(
        column_widths=[0.4, 0.3, 0.3],
        text_alignment="CENTER",
        rtl=True,
    ),
    rtl=True,
)

builder.save("arabic_report.docx")
```

---

### Metrics / KPI document

```python
from sword_word_builder import WordBuilder, TableStyle, CellLine

builder = WordBuilder()
builder.add_heading("Key Metrics Dashboard", level=1)

# Metrics table (label/value pairs)
builder.add_table(
    {
        "Total Users":     "12,450",
        "Active Users":    "9,832",
        "New This Month":  "1,204",
        "Churn Rate":      "2.1%",
        "NPS Score":       "72",
    },
    table_type="metrics",
    headers=["Metric", "Value"],
    style=TableStyle(
        column_widths=[0.6, 0.4],
        metrics_label_bold=True,
        text_alignment="LEFT",
    ),
)

# KPI tiles row
def kpi(value, label):
    return [
        CellLine(value, font_size=20, bold=True, color="FFFFFF", alignment="CENTER"),
        CellLine(label, font_size=9,  color="CCCCCC",            alignment="CENTER"),
    ]

from sword_word_builder import TableStyle
builder.add_table(
    data=[],
    headers=[[
        kpi("12,450", "Total Users"),
        kpi("9,832",  "Active"),
        kpi("2.1%",   "Churn Rate"),
        kpi("72",     "NPS"),
    ]],
    style=TableStyle(
        header_bg_colors=["0D2D5E", "1A5276", "117A65", "B89A00"],
        show_inner_borders=False,
        show_outer_border=False,
        cell_padding_top=12, cell_padding_bottom=12,
        table_alignment="CENTER",
        column_widths=[0.25, 0.25, 0.25, 0.25],
    ),
)
builder.save("metrics.docx")
```

---

## RTL / Arabic Tips

1. **Set `default_rtl=True`** in `DocumentConfig` for fully Arabic documents. This applies to all text, tables, and paragraphs by default.

2. **Per-element override**: Pass `rtl=True` to any `add_*` method to override direction for that element only.

3. **Table RTL**: Also set `rtl=True` on `add_table()` and `TableStyle(rtl=True, text_alignment="RIGHT")`.

4. **Page number in Arabic footer**: Use `footer_type="text_and_page_number"` with `footer_text="صفحة"`. The library automatically adds Unicode RTL marks around the page number field for correct bidirectional rendering.

5. **`CellLine` alignment in RTL cells**: Alignment works correctly regardless of RTL direction. `alignment="CENTER"` always produces a centered paragraph.

6. **Font choice**: Arabic text typically renders best with fonts like `"Arial"`, `"Calibri"`, `"Tahoma"`, or `"Amiri"`.

---

## Page Sizes Reference

| Name | Width × Height |
|---|---|
| `"A4"` | 21 × 29.7 cm (portrait) |
| `"Letter"` | 21.59 × 27.94 cm |
| `"A3"` | 29.7 × 42 cm |
