"""Dynamic report display that adapts to any report structure."""

import streamlit as st
import json
from pathlib import Path
from typing import Dict, Any, List

from analysis.demo.adaptive_extractor import AdaptiveReportExtractor


# HTML table styling (unchanged from original)
HTML_STYLES = """
<style>
    .report-table-wrapper {
        direction: rtl;
        text-align: right;
        display: flex;
        justify-content: center;
        margin: 2rem 0;
        width: 100%;
    }

    .report-table {
        border-collapse: collapse;
        direction: rtl;
        width: 100%;
        max-width: 95%;
        border: 2px solid #B68A35;
        background-color: #111120;
        table-layout: auto;
    }

    .report-table th {
        background-color: rgba(201, 150, 60, 0.3);
        color: #B68A35;
        padding: 15px 12px;
        text-align: right;
        direction: rtl;
        border: 1px solid #555;
        font-weight: 700;
        font-size: 14px;
        white-space: normal;
        word-wrap: break-word;
        overflow-wrap: break-word;
    }

    .report-table td {
        padding: 15px 12px;
        border: 1px solid #444;
        color: #E4E4F0;
        text-align: right;
        direction: rtl;
        white-space: normal;
        word-wrap: break-word;
        overflow-wrap: break-word;
        word-break: break-word;
        line-height: 1.6;
        min-height: 80px;
        vertical-align: top;
    }

    .report-table tr:nth-child(even) {
        background-color: rgba(201, 150, 60, 0.05);
    }

    .report-table tr:hover {
        background-color: rgba(201, 150, 60, 0.12);
    }

    .section-content {
        direction: rtl;
        text-align: right;
        padding: 1rem;
        margin: 1rem 0;
        background: rgba(201, 150, 60, 0.05);
        border-radius: 0.5rem;
        border: 1px solid rgba(201, 150, 60, 0.2);
        color: #E4E4F0;
        line-height: 1.8;
    }
</style>
"""


class DynamicReportDisplay:
    """
    Dynamically displays any report structure without hardcoded sections.

    Adapts to whatever sections and tables are found in the report.
    """

    def __init__(self, lang: str = 'ar'):
        """Initialize display with language preference."""
        self.lang = lang
        self.extractor = AdaptiveReportExtractor()

    def display_report(self, docx_path: str) -> None:
        """
        Display complete report with tabs for each detected section.

        Args:
            docx_path: Path to Word document
        """
        # Add styles
        st.markdown(HTML_STYLES, unsafe_allow_html=True)

        doc_path = Path(docx_path)
        if not doc_path.exists():
            st.warning(
                f"❌ لم يتم العثور على ملف التقرير: {docx_path}"
                if self.lang == 'ar'
                else f"❌ Report file not found: {docx_path}"
            )
            return

        # Extract report structure (with caching)
        try:
            report = self.extractor.extract_report(str(doc_path))
        except Exception as e:
            st.error(
                f"❌ خطأ في استخراج البيانات: {str(e)}"
                if self.lang == 'ar'
                else f"❌ Error extracting report: {str(e)}"
            )
            import traceback
            st.code(traceback.format_exc())
            return

        # Show metadata if available
        if report.get('metadata'):
            with st.expander("📄 معلومات الوثيقة" if self.lang == 'ar' else "📄 Document Info"):
                self._display_metadata(report['metadata'])

        # Create tabs dynamically based on detected sections
        sections = report.get('sections', [])

        if not sections:
            st.warning(
                "⚠️ لم يتم العثور على أقسام في التقرير"
                if self.lang == 'ar'
                else "⚠️ No sections found in report"
            )
            return

        # sections are already main sections only from the detector
        main_sections = sections

        # Generate tab titles from main section titles
        tab_titles = [
            section['title'] if self.lang == 'ar' else section.get('title_en', section['title'])
            for section in main_sections
        ]

        # Create tabs
        tabs = st.tabs(tab_titles)

        # Display each section in its tab
        for tab, section in zip(tabs, main_sections):
            with tab:
                # Use charts assigned to this section during extraction
                self._display_section(section, section.get('charts', []))

    def _display_section(self, section: Dict[str, Any], all_charts: List[Dict]) -> None:
        """
        Display a main section with its content, subsections, tables, and charts.

        Args:
            section: Main section data dictionary
            all_charts: List of all charts in document
        """
        # Display main section content if available (always visible, no expander)
        if section.get('content') and section['content'].strip():
            st.markdown(
                f'<div class="section-content">{section["content"]}</div>',
                unsafe_allow_html=True
            )

        # Display main section tables
        if section.get('tables'):
            for idx, table_data in enumerate(section['tables']):
                if idx > 0:
                    st.markdown("<br>", unsafe_allow_html=True)
                self._display_table(table_data)

        # Display subsections
        if section.get('subsections'):
            for subsec in section['subsections']:
                # Show subsection title
                st.markdown(f"### {subsec['title'] if self.lang == 'ar' else subsec.get('title_en', subsec['title'])}")

                # Show subsection content (always visible, no expander)
                if subsec.get('content') and subsec['content'].strip():
                    st.markdown(
                        f'<div class="section-content">{subsec["content"]}</div>',
                        unsafe_allow_html=True
                    )

                # Show subsection charts FIRST
                if subsec.get('charts'):
                    st.markdown("<br>", unsafe_allow_html=True)
                    for chart_data in subsec['charts']:
                        try:
                            if chart_data.get('is_image'):
                                st.info(f"📊 {chart_data.get('title', 'Image')}")
                                st.markdown("*Image content from document*")
                            else:
                                chart_html = self._render_chart(chart_data)
                                st.components.v1.html(chart_html, height=500)
                        except Exception as e:
                            st.error(f"Error displaying chart: {str(e)}")

                # Show subsection tables SECOND
                if subsec.get('tables'):
                    if subsec.get('charts'):
                        st.markdown("<br>", unsafe_allow_html=True)
                    for table_data in subsec['tables']:
                        self._display_table(table_data)
                        st.markdown("<br>", unsafe_allow_html=True)

        # Display charts (from the all_charts list passed to this section)
        if all_charts:
            st.markdown("<br>", unsafe_allow_html=True)
            for chart_data in all_charts:
                try:
                    # Check if this is an image or actual chart data
                    if chart_data.get('is_image'):
                        st.info(f"📊 {chart_data.get('title', 'Image')}")
                        st.markdown("*Image content from document*", help="Image extracted from original document")
                    else:
                        # Render as chart
                        chart_html = self._render_chart(chart_data)
                        st.components.v1.html(chart_html, height=500)
                except Exception as e:
                    st.error(f"Error displaying chart: {str(e)}")

    def _display_table(self, table_data: Dict[str, Any]) -> None:
        """Display table as HTML with RTL support."""
        if not table_data.get('rows'):
            return

        columns = table_data.get('columns', [])
        rows = table_data.get('rows', [])

        if not columns or not rows:
            return

        html = self._create_html_table(columns, rows)
        st.markdown(html, unsafe_allow_html=True)

    def _create_html_table(self, columns: list, rows: list) -> str:
        """Create HTML table with RTL support."""
        html = '<div class="report-table-wrapper"><table class="report-table">'

        # Header
        html += '<thead><tr>'
        for col in columns:
            html += f'<th>{col}</th>'
        html += '</tr></thead>'

        # Body
        html += '<tbody>'
        for row in rows:
            html += '<tr>'
            cells = [
                str(row.get(col, '')).replace('<', '&lt;').replace('>', '&gt;')
                for col in columns
            ]
            for cell in cells:
                html += f'<td>{cell}</td>'
            html += '</tr>'
        html += '</tbody>'

        html += '</table></div>'
        return html

    def _render_chart(self, chart_data: Dict) -> str:
        """
        Render chart as Chart.js visualization.

        Dispatches to RTL version for Arabic, LTR for English.
        """
        if self.lang == 'ar':
            return self._render_chart_js_rtl(chart_data)
        else:
            return self._render_chart_js(chart_data)

    def _render_chart_js(self, chart_data: Dict) -> str:
        """Render chart as Chart.js visualization (LTR - English)."""
        chart_type = chart_data.get('type', 'bar')
        title = chart_data.get('title', '')
        categories = chart_data.get('categories', [])
        series = chart_data.get('series', [])
        colors = chart_data.get('colors', ['#2E5090', '#87CEEB'])

        # Build datasets JSON
        datasets_json = json.dumps([{
            'label': ser['name'],
            'data': ser['data'],
            'backgroundColor': colors[idx] if idx < len(colors) else f'hsl({idx * 60}, 70%, 50%)',
            'borderColor': colors[idx] if idx < len(colors) else f'hsl({idx * 60}, 70%, 50%)',
            'borderWidth': 0
        } for idx, ser in enumerate(series)], ensure_ascii=False)

        categories_json = json.dumps(categories, ensure_ascii=False)
        title_json = json.dumps(title, ensure_ascii=False)

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js"></script>
</head>
<body style="background: transparent; margin: 0; padding: 0;">
    <div style="display: flex; justify-content: center; margin: 2rem 0; width: 100%;">
        <div style="width: 95%; max-width: 900px; height: 450px;">
            <canvas id="dynamic_chart_{hash(title)}"></canvas>
        </div>
    </div>
    <script>
        document.addEventListener('DOMContentLoaded', function() {{
            setTimeout(function() {{
                var ctx = document.getElementById('dynamic_chart_{hash(title)}');
                if (ctx) {{
                    new Chart(ctx, {{
                        type: '{chart_type}',
                        data: {{
                            labels: {categories_json},
                            datasets: {datasets_json}
                        }},
                        options: {{
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {{
                                title: {{
                                    display: true,
                                    text: {title_json},
                                    color: '#FFFFFF',
                                    font: {{ size: 14, weight: 'bold' }},
                                    padding: {{ top: 10, bottom: 20 }}
                                }},
                                legend: {{
                                    display: true,
                                    position: 'bottom',
                                    labels: {{
                                        padding: 20,
                                        font: {{ size: 12 }},
                                        color: '#FFFFFF',
                                        boxWidth: 15,
                                        boxHeight: 15
                                    }}
                                }}
                            }},
                            scales: {{
                                y: {{
                                    beginAtZero: true,
                                    ticks: {{ color: '#FFFFFF', font: {{ size: 11 }} }},
                                    grid: {{ color: 'rgba(0,0,0,0.05)' }}
                                }},
                                x: {{
                                    ticks: {{ color: '#FFFFFF', font: {{ size: 11 }} }},
                                    grid: {{ display: false }}
                                }}
                            }}
                        }}
                    }});
                }}
            }}, 100);
        }});
    </script>
</body>
</html>"""
        return html

    def _render_chart_js_rtl(self, chart_data: Dict) -> str:
        """
        Render chart as Chart.js visualization in RTL format (Arabic).

        Features:
        - Y-axis positioned on the right
        - X-axis categories reversed (right to left)
        - Dataset values reversed to match axis direction
        """
        chart_type = chart_data.get('type', 'bar')
        title = chart_data.get('title', '')
        categories = chart_data.get('categories', [])
        series = chart_data.get('series', [])
        colors = chart_data.get('colors', ['#2E5090', '#87CEEB'])

        # Reverse categories for RTL display
        categories_rtl = list(reversed(categories))

        # Reverse data in each series to match reversed categories
        series_rtl = []
        for ser in series:
            series_rtl.append({
                'name': ser['name'],
                'data': list(reversed(ser['data']))
            })

        # Build datasets JSON with reversed data
        datasets_json = json.dumps([{
            'label': ser['name'],
            'data': ser['data'],
            'backgroundColor': colors[idx] if idx < len(colors) else f'hsl({idx * 60}, 70%, 50%)',
            'borderColor': colors[idx] if idx < len(colors) else f'hsl({idx * 60}, 70%, 50%)',
            'borderWidth': 0
        } for idx, ser in enumerate(series_rtl)], ensure_ascii=False)

        categories_json = json.dumps(categories_rtl, ensure_ascii=False)
        title_json = json.dumps(title, ensure_ascii=False)

        html = f"""<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="utf-8">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js"></script>
</head>
<body style="background: transparent; margin: 0; padding: 0; direction: rtl;">
    <div style="display: flex; justify-content: center; margin: 2rem 0; width: 100%;">
        <div style="width: 95%; max-width: 900px; height: 450px;">
            <canvas id="dynamic_chart_{hash(title)}"></canvas>
        </div>
    </div>
    <script>
        document.addEventListener('DOMContentLoaded', function() {{
            setTimeout(function() {{
                var ctx = document.getElementById('dynamic_chart_{hash(title)}');
                if (ctx) {{
                    new Chart(ctx, {{
                        type: '{chart_type}',
                        data: {{
                            labels: {categories_json},
                            datasets: {datasets_json}
                        }},
                        options: {{
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {{
                                title: {{
                                    display: true,
                                    text: {title_json},
                                    color: '#FFFFFF',
                                    font: {{ size: 14, weight: 'bold' }},
                                    padding: {{ top: 10, bottom: 20 }}
                                }},
                                legend: {{
                                    display: true,
                                    position: 'bottom',
                                    labels: {{
                                        padding: 20,
                                        font: {{ size: 12 }},
                                        color: '#FFFFFF',
                                        boxWidth: 15,
                                        boxHeight: 15
                                    }}
                                }}
                            }},
                            scales: {{
                                y: {{
                                    beginAtZero: true,
                                    position: 'right',
                                    ticks: {{ color: '#FFFFFF', font: {{ size: 11 }} }},
                                    grid: {{ color: 'rgba(0,0,0,0.05)' }}
                                }},
                                x: {{
                                    ticks: {{ color: '#FFFFFF', font: {{ size: 11 }} }},
                                    grid: {{ display: false }}
                                }}
                            }}
                        }}
                    }});
                }}
            }}, 100);
        }});
    </script>
</body>
</html>"""
        return html

    def _display_metadata(self, metadata: Dict[str, Any]) -> None:
        """Display document metadata in a nice format."""
        cols = st.columns(2)

        with cols[0]:
            if metadata.get('title'):
                st.write(f"**العنوان:** {metadata['title']}" if self.lang == 'ar' else f"**Title:** {metadata['title']}")
            if metadata.get('author'):
                st.write(f"**المؤلف:** {metadata['author']}" if self.lang == 'ar' else f"**Author:** {metadata['author']}")

        with cols[1]:
            if metadata.get('total_paragraphs'):
                st.write(f"**عدد الفقرات:** {metadata['total_paragraphs']}" if self.lang == 'ar' else f"**Paragraphs:** {metadata['total_paragraphs']}")
            if metadata.get('total_tables'):
                st.write(f"**عدد الجداول:** {metadata['total_tables']}" if self.lang == 'ar' else f"**Tables:** {metadata['total_tables']}")


# Backward compatible function
def display_report_tabs(lang: str = 'ar'):
    """
    Display report tabs dynamically based on detected structure.

    This maintains backward compatibility with the old API while using
    the new dynamic display system.

    Args:
        lang: Language preference ('ar' or 'en')
    """
    report_path = Path("outputs/تقرير تحليل استفسارات المتعاملين.docx")

    display = DynamicReportDisplay(lang=lang)
    display.display_report(str(report_path))
