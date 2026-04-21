"""Dynamic report display that adapts to any report structure.

Note: The real version uses AI-based analysis instead of extraction,
so this display component works with analyzed data structures directly.
"""

import streamlit as st
import json
from pathlib import Path
from typing import Dict, Any, List, Optional


# Neutral color palette: Gold/Bronze, Medium Gray, Dark Green, and additional grays
CHART_COLORS = [
    '#B68A35',  # Gold/Bronze
    '#808080',  # Medium Gray
    '#2D6B3C',  # Dark Green
    '#999999',  # Medium-Light Gray
    '#707070',  # Steel Gray
    '#666666',  # Dark Gray
    '#A0A0A0',  # Light Medium Gray
    '#5A5A5A',  # Darker Gray
    '#C0C0C0',  # Silver Gray
    '#8B8B8B',  # Dim Gray
    '#606060',  # Dark Steel Gray
    '#696969',  # Very Dim Gray
    '#787878',  # Slate Gray
    '#7F7F7F',  # Gray 50%
    '#737373',  # Dark Slate Gray
    '#909090',  # Light Steel Gray
]

# HTML table styling (unchanged from original)
HTML_STYLES = """
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
<style>
    * {
        font-family: 'Tajawal', sans-serif;
    }
    .report-table-wrapper {
        direction: rtl;
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
        text-align: center !important;
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
        text-align: center !important;
        direction: rtl;
        white-space: normal;
        word-wrap: break-word;
        overflow-wrap: break-word;
        word-break: keep-all;
        line-height: 1.6;
        min-height: 80px;
        vertical-align: middle;
        font-size: 14px;
    }

    .report-table td .cell-content {
        display: block;
        width: 100%;
        text-align: center !important;
        box-sizing: border-box;
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

    .section-content ul {
        direction: rtl;
        text-align: right;
        margin: 1rem 0;
        padding-right: 2rem;
        list-style: none;
    }

    .section-content ul li {
        direction: rtl;
        text-align: right;
        margin: 0.75rem 0;
        padding-right: 1.5rem;
        position: relative;
        color: #E4E4F0;
        line-height: 1.8;
    }

    .section-content ul li:before {
        content: "●";
        position: absolute;
        right: 0;
        color: #B68A35;
        font-weight: bold;
        font-size: 1.2em;
    }

    .section-content p {
        margin: 0.5rem 0;
        color: #E4E4F0;
    }
</style>

<script>
function adjustTableFontSizes() {
    const cells = document.querySelectorAll('.report-table td');
    cells.forEach(cell => {
        adjustCellFontSize(cell);
    });
}

function adjustCellFontSize(cell) {
    const content = cell.querySelector('.cell-content');
    if (!content) return;

    let fontSize = 14; // Start with default font size
    const minFontSize = 8;

    // Measure with no-wrap first to get natural width
    content.style.whiteSpace = 'nowrap';
    content.style.fontSize = fontSize + 'px';

    let iterations = 0;
    const maxIterations = 20;

    // Keep reducing font size until text fits on one line
    while (iterations < maxIterations && fontSize >= minFontSize) {
        content.style.fontSize = fontSize + 'px';

        // Force layout recalculation
        const _ = content.offsetHeight;

        // Switch back to normal wrapping to check actual height
        content.style.whiteSpace = 'normal';
        const _2 = content.offsetHeight;

        const actualHeight = content.offsetHeight;
        const lineHeight = parseFloat(window.getComputedStyle(content).lineHeight);

        // If height is approximately one line (with small margin), we're good
        if (actualHeight <= lineHeight * 1.3) {
            break;
        }

        // Text is wrapping, reduce font size
        fontSize -= 0.5;
        iterations++;
    }

    // Ensure normal wrapping behavior for display
    content.style.whiteSpace = 'normal';
}

// Use MutationObserver to watch for table additions (works better with Streamlit)
const observer = new MutationObserver(function(mutations) {
    // Check if any new tables were added
    mutations.forEach(function(mutation) {
        if (mutation.addedNodes.length) {
            for (let node of mutation.addedNodes) {
                if (node.querySelector && node.querySelector('.report-table')) {
                    setTimeout(adjustTableFontSizes, 50);
                    return;
                }
            }
        }
    });
});

// Start observing the document for changes
observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: false
});

// Also run immediately in case tables already exist
setTimeout(adjustTableFontSizes, 100);
setTimeout(adjustTableFontSizes, 500);  // Run again after a bit longer

// Run on window resize
window.addEventListener('resize', adjustTableFontSizes);
</script>
"""


class DynamicReportDisplay:
    """
    Dynamically displays any report structure without hardcoded sections.

    Adapts to whatever sections and tables are found in the report.
    """

    def __init__(self, lang: str = 'ar', cache_dir: str = None):
        """
        Initialize display with language preference.

        Args:
            lang: Language preference ('ar' or 'en')
            cache_dir: Not used in real version (AI provides analysis directly)
        """
        self.lang = lang
        # Real version uses AI-based analysis, not extraction
        self.extractor = None

    def _get_colors_for_chart(self, chart_type: str, num_items: int, provided_colors: list = None, num_series: int = None) -> list:
        """
        Get appropriate colors for chart type.

        For bar charts:
            - If 1 or 0 series: all bars gold
            - If 2+ series: gold and gray alternating
        For pie/doughnut charts: uses custom color palette.
        For other charts, uses provided colors or defaults.

        Args:
            chart_type: Type of chart ('pie', 'doughnut', 'bar', 'horizontalBar', etc.)
            num_items: Number of colors needed (series for pie, data points for bar)
            provided_colors: Colors extracted from document (optional)
            num_series: Number of series (for bar chart logic)

        Returns:
            List of hex color codes
        """
        if chart_type in ('bar', 'horizontalBar'):
            # For bar charts: check number of series
            if num_series and num_series <= 1:
                # If 1 or 0 series: all bars gold
                return ['#B68A35'] * num_items
            else:
                # If 2+ series: alternate between gold and gray
                bar_colors = ['#B68A35', '#E5E5E5']  # Gold and Light Gray
                return [bar_colors[i % len(bar_colors)] for i in range(num_items)]
        elif chart_type in ('pie', 'doughnut'):
            # For pie/doughnut charts, use extracted colors if provided, otherwise use custom palette
            if provided_colors and len(provided_colors) >= num_items:
                return provided_colors[:num_items]
            else:
                return [CHART_COLORS[i % len(CHART_COLORS)] for i in range(num_items)]
        elif provided_colors:
            return provided_colors
        else:
            # Default colors for other chart types
            return ['#2E5090', '#87CEEB']

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

        # Real version uses AI analysis instead of extraction
        if self.extractor is None:
            st.error(
                "❌ لم يتم تطبيق عرض التقارير للإصدار الحقيقي بعد."
                if self.lang == 'ar'
                else "❌ Report display not yet implemented for real analyzer. Implementation in progress..."
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

        # Generate tab titles from main section titles (always in original language)
        tab_titles = [
            section['title']
            for section in main_sections
        ]

        # Initialize session state for current section
        if "current_section" not in st.session_state:
            st.session_state.current_section = 0

        # Create the gold-styled dropdown with RTL layout using HTML for tight spacing
        st.markdown(f"""
        <div style="display: flex; align-items: center; direction: rtl; margin-bottom: 1rem;">
            <span style="color: #B68A35; font-weight: bold; margin-left: 8px; white-space: nowrap;">
                {'القسم:' if self.lang == 'ar' else 'Section:'}
            </span>
        </div>
        """, unsafe_allow_html=True)

        selected_section = st.selectbox(
            "اختر قسم" if self.lang == 'ar' else "Select section",
            options=range(len(tab_titles)),
            index=st.session_state.current_section,
            format_func=lambda i: f"{i + 1}. {tab_titles[i]}",
            label_visibility="collapsed",
            key="section_selector"
        )
        st.session_state.current_section = selected_section

        st.markdown("---")

        # Display only the selected section
        current_section = main_sections[st.session_state.current_section]
        self._display_section(current_section, current_section.get('charts', []))

    def display_report_from_dict(self, report: Dict[str, Any]) -> None:
        """
        Display report directly from a dictionary (from analyzer output).

        Args:
            report: Report dictionary with structure {'sections': [...], 'charts': [...], 'metadata': {...}}
        """
        # Add styles
        st.markdown(HTML_STYLES, unsafe_allow_html=True)

        # Display metadata if present
        if 'metadata' in report and report['metadata']:
            with st.expander(
                "📊 معلومات التقرير" if self.lang == 'ar' else "📊 Report Information",
                expanded=False
            ):
                self._display_metadata(report['metadata'])

        # Get sections and charts
        sections = report.get('sections', {})
        all_charts = report.get('charts', [])

        if not sections:
            st.info(
                "ℹ️ لا توجد أقسام في التقرير"
                if self.lang == 'ar'
                else "ℹ️ No sections in report"
            )
            return

        # Convert sections dict to list if needed
        section_list = []
        if isinstance(sections, dict):
            for key, section_data in sections.items():
                if isinstance(section_data, dict):
                    section_list.append({
                        'title': section_data.get('title', key),
                        'content': section_data.get('content', ''),
                        'data': section_data.get('data', []),
                        'tables': section_data.get('tables', [])
                    })
        elif isinstance(sections, list):
            section_list = sections

        if not section_list:
            st.info(
                "ℹ️ لا توجد أقسام في التقرير"
                if self.lang == 'ar'
                else "ℹ️ No sections in report"
            )
            return

        # Generate tab titles
        tab_titles = [section.get('title', f'Section {i}') for i, section in enumerate(section_list)]

        # Initialize session state
        if "current_section" not in st.session_state:
            st.session_state.current_section = 0

        # Section selector
        st.markdown(f"""
        <div style="display: flex; align-items: center; direction: rtl; margin-bottom: 1rem;">
            <span style="color: #B68A35; font-weight: bold; margin-left: 8px; white-space: nowrap;">
                {'القسم:' if self.lang == 'ar' else 'Section:'}
            </span>
        </div>
        """, unsafe_allow_html=True)

        selected_section = st.selectbox(
            "اختر قسم" if self.lang == 'ar' else "Select section",
            options=range(len(tab_titles)),
            index=st.session_state.current_section,
            format_func=lambda i: f"{i + 1}. {tab_titles[i]}",
            label_visibility="collapsed",
        )
        st.session_state.current_section = selected_section

        st.markdown("---")

        # Display selected section
        current_section = section_list[st.session_state.current_section]

        # Display section content
        if current_section.get('content'):
            st.markdown(self._convert_content_to_html(current_section['content']), unsafe_allow_html=True)

        # Display section data
        if current_section.get('data'):
            data = current_section['data']
            if isinstance(data, list) and data:
                st.write(data)
            elif isinstance(data, dict) and data:
                st.json(data)

        # Display charts for this section if linked
        for chart in all_charts:
            if chart.get('section') == current_section.get('title'):
                self._render_chart(chart)

    def _convert_content_to_html(self, content: str) -> str:
        """
        Convert content with bullet points to formatted HTML.

        Detects lines that are bullet points and converts them to <ul><li> items.
        Also wraps regular paragraphs in <p> tags.

        Recognizes bullet points in multiple formats:
        - Lines starting with bullet markers (←, -, •, ▪)
        - Lines matching complaint type patterns (from section 2.2)

        Args:
            content: Raw content text potentially containing bullet points

        Returns:
            HTML-formatted content with proper list formatting
        """
        if not content:
            return content

        import re

        lines = content.split('\n')
        html_parts = []
        in_list = False

        for line in lines:
            stripped = line.strip()
            is_bullet = False
            bullet_text = stripped

            if not stripped:
                # Empty line - close list if open
                if in_list:
                    html_parts.append('</ul>')
                    in_list = False
                continue

            # Check if this line is a bullet point with marker
            if stripped.startswith('←') or stripped.startswith('-') or \
               stripped.startswith('•') or stripped.startswith('▪'):
                is_bullet = True
                bullet_text = stripped.lstrip('←-•▪').strip()

            # Also check for complaint type patterns: "الشكوى ... — إغلاق خلال ..."
            elif (stripped.startswith('الشكوى ') and '—' in stripped and
                  re.search(r'خلال\s+\d+\s+(ساعة|ساعات|يوم|أيام)', stripped)):
                is_bullet = True
                bullet_text = stripped

            if is_bullet:
                # Start list if not already in one
                if not in_list:
                    html_parts.append('<ul>')
                    in_list = True

                html_parts.append(f'<li>{bullet_text}</li>')
            else:
                # Regular paragraph text
                if in_list:
                    html_parts.append('</ul>')
                    in_list = False

                html_parts.append(f'<p>{stripped}</p>')

        # Close any open list
        if in_list:
            html_parts.append('</ul>')

        return '\n'.join(html_parts)

    def _display_section(self, section: Dict[str, Any], all_charts: List[Dict]) -> None:
        """
        Display a main section with its content, subsections, tables, and charts.

        Args:
            section: Main section data dictionary
            all_charts: List of all charts in document
        """
        # Display main section content if available (always visible, no expander)
        if section.get('content') and section['content'].strip():
            formatted_content = self._convert_content_to_html(section["content"])
            st.markdown(
                f'<div class="section-content">{formatted_content}</div>',
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
                # Show subsection title (always in original language)
                st.markdown(f"### {subsec['title']}")

                # Show subsection content (always visible, no expander)
                if subsec.get('content') and subsec['content'].strip():
                    formatted_content = self._convert_content_to_html(subsec["content"])
                    st.markdown(
                        f'<div class="section-content">{formatted_content}</div>',
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
        """Create HTML table with RTL support and dynamic font sizing."""
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
                html += f'<td><div class="cell-content">{cell}</div></td>'
            html += '</tr>'
        html += '</tbody>'

        html += '</table></div>'
        return html

    def _render_chart(self, chart_data: Dict) -> str:
        """
        Render chart using appropriate library.

        - Pie/doughnut charts: Use Highcharts
        - Other charts: Use Chart.js
        - Dispatches to RTL version for Arabic, LTR for English.
        """
        chart_type = chart_data.get('type', 'bar')

        if chart_type in ('pie', 'doughnut'):
            if self.lang == 'ar':
                return self._render_pie_chart_highcharts_rtl(chart_data)
            else:
                return self._render_pie_chart_highcharts(chart_data)
        else:
            if self.lang == 'ar':
                return self._render_chart_js_rtl(chart_data)
            else:
                return self._render_chart_js(chart_data)

    def _render_pie_chart_highcharts(self, chart_data: Dict) -> str:
        """Render pie/doughnut chart using Highcharts (LTR - English)."""
        chart_type = chart_data.get('type', 'pie')
        title = chart_data.get('title', '')
        categories = chart_data.get('categories', [])
        series = chart_data.get('series', [])
        provided_colors = chart_data.get('colors', [])

        # Get colors
        colors = self._get_colors_for_chart(chart_type, len(categories), provided_colors or None)

        # Prepare data for Highcharts
        data_values = series[0]['data'] if series else []

        # Create series data for Highcharts
        series_data = [
            {'name': categories[i], 'y': data_values[i], 'color': colors[i]}
            for i in range(len(categories))
        ]
        series_json = json.dumps(series_data, ensure_ascii=False)
        title_json = json.dumps(title, ensure_ascii=False)

        # Determine inner radius for doughnut
        inner_radius = '80' if chart_type == 'doughnut' else '0'

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <script src="https://code.highcharts.com/highcharts.js"></script>
    <script src="https://code.highcharts.com/modules/exporting.js"></script>
    <style>
        body {{ background: transparent; margin: 0; padding: 0; }}
        .chart-container {{ display: flex; flex-direction: column; align-items: center; justify-content: center; width: 100%; margin: 2rem 0; }}
        .chart-title {{ color: #FFFFFF; font-size: 16px; font-weight: bold; margin-bottom: 1rem; text-align: center; }}
        #pie-chart {{ width: 95%; max-width: 900px; height: 450px; }}
    </style>
</head>
<body>
    <div class="chart-container">
        <div class="chart-title">{title}</div>
        <div id="pie-chart"></div>
    </div>
    <script>
        const seriesData = {series_json};
        const chartType = '{chart_type}';
        const innerRadius = {inner_radius};

        Highcharts.setOptions({{
            colors: seriesData.map(d => d.color)
        }});

        Highcharts.chart('pie-chart', {{
            chart: {{
                type: 'pie',
                backgroundColor: 'transparent',
                style: {{ fontFamily: 'Arial, sans-serif' }}
            }},
            title: {{
                text: null
            }},
            tooltip: {{
                backgroundColor: 'rgba(0, 0, 0, 0.8)',
                borderColor: 'rgba(0, 0, 0, 0.8)',
                style: {{ color: '#FFFFFF', fontSize: '12px' }},
                headerFormat: '',
                pointFormat: '<b>{{point.name}}</b>: {{point.y:,.0f}} ({{point.percentage:.1f}}%)',
                shared: false
            }},
            plotOptions: {{
                pie: {{
                    innerSize: innerRadius,
                    depth: 45,
                    allowPointSelect: true,
                    cursor: 'pointer',
                    dataLabels: {{
                        enabled: true,
                        format: '{{point.percentage:.1f}}%',
                        style: {{
                            fontSize: '12px',
                            fontWeight: 'bold',
                            color: '#FFFFFF',
                            textShadow: '0 0 3px rgba(0, 0, 0, 0.8)'
                        }},
                        connectorColor: '#FFFFFF'
                    }},
                    events: {{
                        legendItemClick: function() {{
                            return false;
                        }}
                    }}
                }}
            }},
            series: [{{
                name: '',
                colorByPoint: true,
                data: seriesData
            }}],
            legend: {{
                enabled: true,
                layout: 'horizontal',
                align: 'center',
                verticalAlign: 'bottom',
                itemStyle: {{
                    color: '#FFFFFF',
                    fontSize: '12px'
                }},
                symbolRadius: 2
            }},
            credits: {{
                enabled: false
            }},
            exporting: {{
                enabled: false
            }}
        }});
    </script>
</body>
</html>"""
        return html

    def _render_pie_chart_highcharts_rtl(self, chart_data: Dict) -> str:
        """Render pie/doughnut chart using Highcharts in RTL format (Arabic)."""
        chart_type = chart_data.get('type', 'pie')
        title = chart_data.get('title', '')
        categories = chart_data.get('categories', [])
        series = chart_data.get('series', [])
        provided_colors = chart_data.get('colors', [])

        # Get colors
        colors = self._get_colors_for_chart(chart_type, len(categories), provided_colors or None)

        # Prepare data for Highcharts
        data_values = series[0]['data'] if series else []

        # Create series data for Highcharts
        series_data = [
            {'name': categories[i], 'y': data_values[i], 'color': colors[i]}
            for i in range(len(categories))
        ]
        series_json = json.dumps(series_data, ensure_ascii=False)
        title_json = json.dumps(title, ensure_ascii=False)

        # Determine inner radius for doughnut
        inner_radius = '80' if chart_type == 'doughnut' else '0'

        html = f"""<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="utf-8">
    <script src="https://code.highcharts.com/highcharts.js"></script>
    <script src="https://code.highcharts.com/modules/exporting.js"></script>
    <style>
        body {{ background: transparent; margin: 0; padding: 0; direction: rtl; }}
        .chart-container {{ display: flex; flex-direction: column; align-items: center; justify-content: center; width: 100%; margin: 2rem 0; }}
        .chart-title {{ color: #FFFFFF; font-size: 16px; font-weight: bold; margin-bottom: 1rem; text-align: center; }}
        #pie-chart {{ width: 95%; max-width: 900px; height: 450px; }}
    </style>
</head>
<body>
    <div class="chart-container">
        <div class="chart-title">{title}</div>
        <div id="pie-chart"></div>
    </div>
    <script>
        const seriesData = {series_json};
        const chartType = '{chart_type}';
        const innerRadius = {inner_radius};

        Highcharts.setOptions({{
            colors: seriesData.map(d => d.color)
        }});

        Highcharts.chart('pie-chart', {{
            chart: {{
                type: 'pie',
                backgroundColor: 'transparent',
                style: {{ fontFamily: 'Arial, sans-serif' }}
            }},
            title: {{
                text: null
            }},
            tooltip: {{
                backgroundColor: 'rgba(0, 0, 0, 0.8)',
                borderColor: 'rgba(0, 0, 0, 0.8)',
                style: {{ color: '#FFFFFF', fontSize: '12px' }},
                headerFormat: '',
                pointFormat: '<b>{{point.name}}</b>: {{point.y:,.0f}} ({{point.percentage:.1f}}%)',
                shared: false
            }},
            plotOptions: {{
                pie: {{
                    innerSize: innerRadius,
                    depth: 45,
                    allowPointSelect: true,
                    cursor: 'pointer',
                    dataLabels: {{
                        enabled: true,
                        format: '{{point.percentage:.1f}}%',
                        style: {{
                            fontSize: '12px',
                            fontWeight: 'bold',
                            color: '#FFFFFF',
                            textShadow: '0 0 3px rgba(0, 0, 0, 0.8)'
                        }},
                        connectorColor: '#FFFFFF'
                    }},
                    events: {{
                        legendItemClick: function() {{
                            return false;
                        }}
                    }}
                }}
            }},
            series: [{{
                name: '',
                colorByPoint: true,
                data: seriesData
            }}],
            legend: {{
                enabled: true,
                layout: 'horizontal',
                align: 'center',
                verticalAlign: 'bottom',
                itemStyle: {{
                    color: '#FFFFFF',
                    fontSize: '12px'
                }},
                symbolRadius: 2
            }},
            credits: {{
                enabled: false
            }},
            exporting: {{
                enabled: false
            }}
        }});
    </script>
</body>
</html>"""
        return html

    def _render_chart_js(self, chart_data: Dict) -> str:
        """Render chart as Chart.js visualization (LTR - English).

        Note: Pie/doughnut charts are handled by _render_pie_chart_highcharts instead.
        This method only handles bar and other non-pie chart types.
        """
        chart_type = chart_data.get('type', 'bar')
        title = chart_data.get('title', '')
        categories = chart_data.get('categories', [])
        series = chart_data.get('series', [])
        provided_colors = chart_data.get('colors', [])

        # Build datasets JSON
        if chart_type in ('pie', 'doughnut'):
            # For pie/doughnut charts: each data point gets its own color
            colors = self._get_colors_for_chart(chart_type, len(categories), provided_colors or None)
            datasets_json = json.dumps([{
                'label': ser['name'],
                'data': ser['data'],
                'backgroundColor': colors[:len(ser['data'])],
                'borderColor': colors[:len(ser['data'])],
                'borderWidth': 0
            } for ser in series], ensure_ascii=False)
        elif chart_type in ('bar', 'horizontalBar'):
            # For bar charts: each series gets one color
            colors = self._get_colors_for_chart(chart_type, len(series), provided_colors or None, num_series=len(series))
            datasets = []
            for ser_idx, ser in enumerate(series):
                # All bars in this series get the same color
                series_color = colors[ser_idx]
                bar_colors = [series_color] * len(ser['data'])
                datasets.append({
                    'label': ser['name'],
                    'data': ser['data'],
                    'backgroundColor': bar_colors,
                    'borderColor': bar_colors,
                    'borderWidth': 0
                })
            datasets_json = json.dumps(datasets, ensure_ascii=False)
        else:
            # For other charts: each series gets its own color
            colors = self._get_colors_for_chart(chart_type, len(series), provided_colors or None)
            datasets_json = json.dumps([{
                'label': ser['name'],
                'data': ser['data'],
                'backgroundColor': colors[idx] if idx < len(colors) else f'hsl({idx * 60}, 70%, 50%)',
                'borderColor': colors[idx] if idx < len(colors) else f'hsl({idx * 60}, 70%, 50%)',
                'borderWidth': 0
            } for idx, ser in enumerate(series)], ensure_ascii=False)

        categories_json = json.dumps(categories, ensure_ascii=False)
        title_json = json.dumps(title, ensure_ascii=False)

        # Determine if scales should be displayed (not for pie/doughnut charts)
        show_scales = chart_type not in ('pie', 'doughnut')

        # Build tooltip and plugin configuration for pie/doughnut charts
        tooltip_config = ""
        plugin_config = ""
        if chart_type in ('pie', 'doughnut'):
            tooltip_config = """
                            tooltip: {
                                backgroundColor: 'rgba(0, 0, 0, 0.8)',
                                padding: 12,
                                titleFont: { size: 12, weight: 'bold' },
                                bodyFont: { size: 12 },
                                displayColors: false,
                                callbacks: {
                                    label: function(context) {
                                        var value = context.raw;
                                        return 'Value: ' + value.toLocaleString();
                                    }
                                }
                            },"""
            plugin_config = """
                            // Empty plugin - percentages are rendered via HTML overlays
                            {
                                id: 'piePercentages'
                            }"""

        # Non-pie charts use standard Chart.js rendering
        if chart_type not in ('pie', 'doughnut'):
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
                        plugins: [{plugin_config}],
                        options: {{
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {{
                                title: {{
                                    display: true,
                                    text: {title_json},
                                    color: '#FFFFFF',
                                    font: {{ size: 14, weight: 'bold' }},
                                    padding: {{ top: 10, bottom: 50 }}
                                }},
                                {tooltip_config}
                                legend: {{
                                    display: true,
                                    position: 'bottom',
                                    labels: {{
                                        padding: 20,
                                        font: {{ size: 12, weight: 'bold' }},
                                        color: '#FFFFFF',
                                        boxWidth: 18,
                                        boxHeight: 18,
                                        usePointStyle: {str(chart_type in ('pie', 'doughnut')).lower()},
                                        borderRadius: 4,
                                        generateLabels: function(chart) {{
                                            var datasets = chart.data.datasets;
                                            var chartType = chart.config.type;

                                            // For bar charts, use dataset labels; for pie/doughnut, use category labels
                                            if (chartType === 'bar' || chartType === 'horizontalBar') {{
                                                return datasets.map((dataset, i) => {{
                                                    return {{
                                                        text: dataset.label,
                                                        fillStyle: dataset.backgroundColor[0],
                                                        hidden: false,
                                                        index: i
                                                    }};
                                                }});
                                            }} else {{
                                                var labels = chart.data.labels;
                                                return labels.map((label, i) => {{
                                                    return {{
                                                        text: label,
                                                        fillStyle: datasets[0].backgroundColor[i],
                                                        hidden: false,
                                                        index: i
                                                    }};
                                                }});
                                            }}
                                        }}
                                    }},
                                    maxHeight: 200,
                                    fullSize: true
                                }}
                            }},
                            scales: {{
                                y: {{
                                    display: {str(show_scales).lower()},
                                    beginAtZero: true,
                                    ticks: {{ color: '#FFFFFF', font: {{ size: 11 }} }},
                                    grid: {{ color: 'rgba(0,0,0,0.05)' }}
                                }},
                                x: {{
                                    display: {str(show_scales).lower()},
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

        Note: Pie/doughnut charts are handled by _render_pie_chart_highcharts_rtl instead.
        This method only handles bar and other non-pie chart types.

        Features (for non-pie charts):
        - Y-axis positioned on the right
        - X-axis categories reversed (right to left)
        - Dataset values reversed to match axis direction
        """
        chart_type = chart_data.get('type', 'bar')
        title = chart_data.get('title', '')
        categories = chart_data.get('categories', [])
        series = chart_data.get('series', [])
        provided_colors = chart_data.get('colors', [])

        # Get appropriate colors for this chart type
        colors = self._get_colors_for_chart(chart_type, len(series), provided_colors or None)

        # Reverse categories and data for RTL display (but not for pie charts)
        if chart_type in ('pie', 'doughnut'):
            # Pie charts: keep original order
            categories_rtl = categories
            series_rtl = series
        else:
            # Bar charts: reverse for RTL axes
            categories_rtl = list(reversed(categories))
            series_rtl = []
            for ser in series:
                series_rtl.append({
                    'name': ser['name'],
                    'data': list(reversed(ser['data']))
                })

        # Build datasets JSON
        if chart_type in ('pie', 'doughnut'):
            # For pie/doughnut charts: keep original data and colors in sync
            colors = self._get_colors_for_chart(chart_type, len(categories), provided_colors or None)
            datasets_json = json.dumps([{
                'label': ser['name'],
                'data': ser['data'],
                'backgroundColor': colors[:len(ser['data'])],
                'borderColor': colors[:len(ser['data'])],
                'borderWidth': 0
            } for ser in series], ensure_ascii=False)
        elif chart_type in ('bar', 'horizontalBar'):
            # For bar charts: each series gets one color
            colors = self._get_colors_for_chart(chart_type, len(series), provided_colors or None, num_series=len(series))
            datasets = []
            for ser_idx, ser in enumerate(series_rtl):
                # All bars in this series get the same color
                series_color = colors[ser_idx]
                bar_colors = [series_color] * len(ser['data'])
                datasets.append({
                    'label': ser['name'],
                    'data': ser['data'],
                    'backgroundColor': bar_colors,
                    'borderColor': bar_colors,
                    'borderWidth': 0
                })
            datasets_json = json.dumps(datasets, ensure_ascii=False)
        else:
            # For other charts: each series gets its own color
            datasets_json = json.dumps([{
                'label': ser['name'],
                'data': ser['data'],
                'backgroundColor': colors[idx] if idx < len(colors) else f'hsl({idx * 60}, 70%, 50%)',
                'borderColor': colors[idx] if idx < len(colors) else f'hsl({idx * 60}, 70%, 50%)',
                'borderWidth': 0
            } for idx, ser in enumerate(series_rtl)], ensure_ascii=False)

        categories_json = json.dumps(categories_rtl, ensure_ascii=False)
        title_json = json.dumps(title, ensure_ascii=False)

        # Determine if scales should be displayed (not for pie/doughnut charts)
        show_scales = chart_type not in ('pie', 'doughnut')

        # Build tooltip and plugin configuration for pie/doughnut charts
        tooltip_config = ""
        plugin_config = ""
        if chart_type in ('pie', 'doughnut'):
            tooltip_config = """
                            tooltip: {
                                backgroundColor: 'rgba(0, 0, 0, 0.8)',
                                padding: 12,
                                titleFont: { size: 12, weight: 'bold' },
                                bodyFont: { size: 12 },
                                displayColors: false,
                                callbacks: {
                                    label: function(context) {
                                        var value = context.raw;
                                        return 'القيمة: ' + value.toLocaleString();
                                    }
                                }
                            },"""
            plugin_config = """
                            // Empty plugin - percentages are rendered via HTML overlays
                            {
                                id: 'piePercentages'
                            }"""

        # Non-pie charts use standard Chart.js rendering
        if chart_type not in ('pie', 'doughnut'):
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
                        plugins: [{plugin_config}],
                        options: {{
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {{
                                title: {{
                                    display: true,
                                    text: {title_json},
                                    color: '#FFFFFF',
                                    font: {{ size: 14, weight: 'bold' }},
                                    padding: {{ top: 10, bottom: 50 }}
                                }},
                                {tooltip_config}
                                legend: {{
                                    display: true,
                                    position: 'bottom',
                                    labels: {{
                                        padding: 20,
                                        font: {{ size: 12, weight: 'bold' }},
                                        color: '#FFFFFF',
                                        boxWidth: 18,
                                        boxHeight: 18,
                                        usePointStyle: {str(chart_type in ('pie', 'doughnut')).lower()},
                                        borderRadius: 4,
                                        generateLabels: function(chart) {{
                                            var datasets = chart.data.datasets;
                                            var chartType = chart.config.type;

                                            // For bar charts, use dataset labels; for pie/doughnut, use category labels
                                            if (chartType === 'bar' || chartType === 'horizontalBar') {{
                                                return datasets.map((dataset, i) => {{
                                                    return {{
                                                        text: dataset.label,
                                                        fillStyle: dataset.backgroundColor[0],
                                                        hidden: false,
                                                        index: i
                                                    }};
                                                }});
                                            }} else {{
                                                var labels = chart.data.labels;
                                                return labels.map((label, i) => {{
                                                    return {{
                                                        text: label,
                                                        fillStyle: datasets[0].backgroundColor[i],
                                                        hidden: false,
                                                        index: i
                                                    }};
                                                }});
                                            }}
                                        }}
                                    }},
                                    maxHeight: 200,
                                    fullSize: true
                                }}
                            }},
                            scales: {{
                                y: {{
                                    display: {str(show_scales).lower()},
                                    beginAtZero: true,
                                    position: 'right',
                                    ticks: {{ color: '#FFFFFF', font: {{ size: 11 }} }},
                                    grid: {{ color: 'rgba(0,0,0,0.05)' }}
                                }},
                                x: {{
                                    display: {str(show_scales).lower()},
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
def display_report_tabs(lang: str = 'ar', flow_type: str = 'inquiries'):
    """
    Display report tabs dynamically based on detected structure.

    This maintains backward compatibility with the old API while using
    the new dynamic display system.

    Args:
        lang: Language preference ('ar' or 'en')
        flow_type: Type of flow ('inquiries' or 'complaints')
    """
    # Get the parent directory (app folder) containing this module
    app_dir = Path(__file__).parent.parent

    if flow_type == 'complaints':
        report_path = app_dir / "complaints-output" / "تقرير تحليل شكاوى المتعاملين .docx"
        cache_dir = str(app_dir / "complaints-output" / "cache")
    else:
        report_path = app_dir / "inquiries-output" / "تقرير تحليل استفسارات المتعاملين.docx"
        cache_dir = str(app_dir / "inquiries-output" / "cache")

    display = DynamicReportDisplay(lang=lang, cache_dir=cache_dir)
    display.display_report(str(report_path))
