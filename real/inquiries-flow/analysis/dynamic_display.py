"""Dynamic report display that adapts to any report structure.

Supports two input modes:
  1. JSON file / dict  — call display_from_json(report) or display_from_json_file(path)
  2. Word document     — call display_report(docx_path)  (requires AdaptiveReportExtractor)
"""

import json
import streamlit as st
from pathlib import Path
from typing import Dict, Any, List, Optional


# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Shared CSS / JS injected once per page
# ---------------------------------------------------------------------------

HTML_STYLES = """
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
<style>
    * { font-family: 'Tajawal', sans-serif; }

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
        background-color: rgba(201,150,60,0.3);
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
    .report-table tr:nth-child(even) { background-color: rgba(201,150,60,0.05); }
    .report-table tr:hover            { background-color: rgba(201,150,60,0.12); }

    .section-content {
        direction: rtl;
        text-align: right;
        padding: 1rem;
        margin: 1rem 0;
        background: rgba(201,150,60,0.05);
        border-radius: 0.5rem;
        border: 1px solid rgba(201,150,60,0.2);
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
    .section-content p { margin: 0.5rem 0; color: #E4E4F0; }
</style>

<script>
function adjustTableFontSizes() {
    document.querySelectorAll('.report-table td').forEach(cell => {
        const content = cell.querySelector('.cell-content');
        if (!content) return;
        let fontSize = 14;
        const minFontSize = 8;
        content.style.whiteSpace = 'nowrap';
        content.style.fontSize = fontSize + 'px';
        let iterations = 0;
        while (iterations < 20 && fontSize >= minFontSize) {
            content.style.fontSize = fontSize + 'px';
            void content.offsetHeight;
            content.style.whiteSpace = 'normal';
            void content.offsetHeight;
            const lineHeight = parseFloat(window.getComputedStyle(content).lineHeight);
            if (content.offsetHeight <= lineHeight * 1.3) break;
            fontSize -= 0.5;
            iterations++;
        }
        content.style.whiteSpace = 'normal';
    });
}

const _observer = new MutationObserver(mutations => {
    mutations.forEach(m => {
        if (m.addedNodes.length) {
            for (let node of m.addedNodes) {
                if (node.querySelector && node.querySelector('.report-table')) {
                    setTimeout(adjustTableFontSizes, 50);
                    return;
                }
            }
        }
    });
});
_observer.observe(document.body, { childList: true, subtree: true });
setTimeout(adjustTableFontSizes, 100);
setTimeout(adjustTableFontSizes, 500);
window.addEventListener('resize', adjustTableFontSizes);
</script>
"""


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class DynamicReportDisplay:
    """
    Dynamically displays any report structure without hardcoded sections.

    Input options
    -------------
    • JSON dict / file  →  display_from_json() / display_from_json_file()
    • Word document      →  display_report()   (requires AdaptiveReportExtractor)
    """

    def __init__(self, lang: str = 'ar', cache_dir: Optional[str] = None):
        self.lang = lang
        self.cache_dir = cache_dir
        self._extractor = None   # lazy-loaded only when needed for .docx path

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def display_from_json_file(self, json_path: str) -> None:
        """
        Load a pre-extracted JSON file and render it.

        Args:
            json_path: Path to the .json file produced by the extraction pipeline.
        """
        path = Path(json_path)
        if not path.exists():
            st.error(f"❌ لم يتم العثور على ملف JSON: {json_path}"
                     if self.lang == 'ar' else f"❌ JSON file not found: {json_path}")
            return
        try:
            with open(path, encoding='utf-8') as f:
                report = json.load(f)
        except Exception as e:
            st.error(f"❌ خطأ في قراءة ملف JSON: {e}"
                     if self.lang == 'ar' else f"❌ Error reading JSON: {e}")
            return
        self.display_from_json(report)

    def display_from_json(self, report: Dict[str, Any]) -> None:
        """
        Render a report from an already-loaded dict.

        Args:
            report: Dict matching the extraction schema (sections, charts, metadata …).
        """
        st.markdown(HTML_STYLES, unsafe_allow_html=True)
        self._render_report(report)

    def display_report(self, docx_path: str) -> None:
        """
        Extract a Word document and render it (original behaviour).

        Falls back gracefully when AdaptiveReportExtractor is unavailable.

        Args:
            docx_path: Path to the .docx file.
        """
        st.markdown(HTML_STYLES, unsafe_allow_html=True)

        doc_path = Path(docx_path)
        if not doc_path.exists():
            st.warning(f"❌ لم يتم العثور على ملف التقرير: {docx_path}"
                       if self.lang == 'ar' else f"❌ Report file not found: {docx_path}")
            return

        # Try to import and use the extractor
        try:
            if self._extractor is None:
                from .adaptive_extractor import AdaptiveReportExtractor
                self._extractor = AdaptiveReportExtractor(cache_dir=self.cache_dir)
            report = self._extractor.extract_report(str(doc_path))
        except ImportError:
            st.error("❌ AdaptiveReportExtractor غير متاح. استخدم display_from_json_file() بدلاً من ذلك."
                     if self.lang == 'ar'
                     else "❌ AdaptiveReportExtractor not available. Use display_from_json_file() instead.")
            return
        except Exception as e:
            st.error(f"❌ خطأ في استخراج البيانات: {e}"
                     if self.lang == 'ar' else f"❌ Error extracting report: {e}")
            import traceback
            st.code(traceback.format_exc())
            return

        self._render_report(report)

    # ------------------------------------------------------------------
    # Core rendering
    # ------------------------------------------------------------------

    def _render_report(self, report: Dict[str, Any]) -> None:
        """Shared rendering logic for any input mode."""
        sections = report.get('sections', [])
        if not sections:
            st.warning("⚠️ لم يتم العثور على أقسام في التقرير"
                       if self.lang == 'ar' else "⚠️ No sections found in report")
            return

        tab_titles = [s['title'] for s in sections]

        if 'current_section' not in st.session_state:
            st.session_state.current_section = 0

        st.markdown(f"""
        <div style="display:flex;align-items:center;direction:rtl;margin-bottom:1rem;">
            <span style="color:#B68A35;font-weight:bold;margin-left:8px;white-space:nowrap;">
                {'القسم:' if self.lang == 'ar' else 'Section:'}
            </span>
        </div>
        """, unsafe_allow_html=True)

        selected = st.selectbox(
            "اختر قسم" if self.lang == 'ar' else "Select section",
            options=range(len(tab_titles)),
            index=st.session_state.current_section,
            format_func=lambda i: f"{i + 1}. {tab_titles[i]}",
            label_visibility="collapsed",
            key="section_selector",
        )
        st.session_state.current_section = selected
        st.markdown("---")

        current = sections[st.session_state.current_section]
        # Merge section charts with report-level charts
        all_charts = (current.get('charts', []) or []) + (report.get('charts', []) or [])
        self._display_section(current, all_charts)

    # ------------------------------------------------------------------
    # Section / subsection rendering
    # ------------------------------------------------------------------

    def _display_section(self, section: Dict[str, Any], all_charts: List[Dict]) -> None:
        if section.get('content') and section['content'].strip():
            html = self._convert_content_to_html(section['content'])
            st.markdown(f'<div class="section-content">{html}</div>', unsafe_allow_html=True)

        for idx, table_data in enumerate(section.get('tables', [])):
            if idx > 0:
                st.markdown("<br>", unsafe_allow_html=True)
            self._display_table(table_data)

        for subsec in section.get('subsections', []):
            st.markdown(f"### {subsec['title']}")

            if subsec.get('content') and subsec['content'].strip():
                html = self._convert_content_to_html(subsec['content'])
                st.markdown(f'<div class="section-content">{html}</div>', unsafe_allow_html=True)

            if subsec.get('charts'):
                st.markdown("<br>", unsafe_allow_html=True)
                self._display_charts_with_pie_priority(subsec['charts'])

            if subsec.get('tables'):
                if subsec.get('charts'):
                    st.markdown("<br>", unsafe_allow_html=True)
                for table_data in subsec['tables']:
                    self._display_table(table_data)
                    st.markdown("<br>", unsafe_allow_html=True)

        if all_charts:
            st.markdown("<br>", unsafe_allow_html=True)
            self._display_charts_with_pie_priority(all_charts)

    # ------------------------------------------------------------------
    # Chart rendering
    # ------------------------------------------------------------------

    def _display_charts_with_pie_priority(self, charts: List[Dict]) -> None:
        pie_charts   = [c for c in charts if c.get('type') in ('pie', 'doughnut')]
        other_charts = [c for c in charts if c.get('type') not in ('pie', 'doughnut')]

        if pie_charts:
            num_cols = min(len(pie_charts), 3)
            cols = st.columns(num_cols)
            for idx, chart_data in enumerate(pie_charts):
                try:
                    with cols[idx % num_cols]:
                        st.components.v1.html(self._render_chart(chart_data), height=500)
                except Exception as e:
                    st.error(f"Error displaying chart: {e}")

        if other_charts:
            if pie_charts:
                st.markdown("<br>", unsafe_allow_html=True)
            for chart_data in other_charts:
                try:
                    st.components.v1.html(self._render_chart(chart_data), height=500)
                except Exception as e:
                    st.error(f"Error displaying chart: {e}")

    def _get_colors_for_chart(self,
                               chart_type: str,
                               num_items: int,
                               provided_colors: Optional[list] = None,
                               num_series: Optional[int] = None) -> list:
        if chart_type in ('bar', 'horizontalBar', 'column'):
            if num_series and num_series <= 1:
                return ['#B68A35'] * num_items
            bar_colors = ['#B68A35', '#E5E5E5']
            return [bar_colors[i % len(bar_colors)] for i in range(num_items)]
        elif chart_type in ('pie', 'doughnut'):
            if provided_colors and len(provided_colors) >= num_items:
                return provided_colors[:num_items]
            return [CHART_COLORS[i % len(CHART_COLORS)] for i in range(num_items)]
        elif provided_colors:
            return provided_colors
        return ['#2E5090', '#87CEEB']

    def _render_chart(self, chart_data: Dict) -> str:
        chart_type = chart_data.get('type', 'bar')
        # Normalize chart types: Chart.js uses 'bar' for vertical columns
        if chart_type == 'column':
            chart_type = 'bar'
            chart_data = {**chart_data, 'type': chart_type}
        if chart_type in ('pie', 'doughnut'):
            return (self._render_pie_chart_highcharts_rtl(chart_data)
                    if self.lang == 'ar'
                    else self._render_pie_chart_highcharts(chart_data))
        return (self._render_chart_js_rtl(chart_data)
                if self.lang == 'ar'
                else self._render_chart_js(chart_data))

    # ---- Highcharts pie (shared core) ----

    def _pie_highcharts_html(self, chart_data: Dict, rtl: bool) -> str:
        chart_type = chart_data.get('type', 'pie')
        title      = chart_data.get('title', '')
        categories = chart_data.get('categories', [])
        series     = chart_data.get('series', [])
        provided   = chart_data.get('colors', [])

        colors      = self._get_colors_for_chart(chart_type, len(categories), provided or None)
        data_values = series[0]['data'] if series else []
        series_data = [
            {'name': categories[i], 'y': data_values[i], 'color': colors[i]}
            for i in range(len(categories))
        ]
        series_json = json.dumps(series_data, ensure_ascii=False)
        inner_size  = '80' if chart_type == 'doughnut' else '0'
        dir_attr    = 'dir="rtl"' if rtl else ''
        dir_style   = 'direction:rtl;' if rtl else ''

        return f"""<!DOCTYPE html>
<html {dir_attr}>
<head>
<meta charset="utf-8">
<script src="https://code.highcharts.com/highcharts.js"></script>
<script src="https://code.highcharts.com/modules/exporting.js"></script>
<style>
  body {{ background:transparent; margin:0; padding:0; {dir_style} }}
  .chart-container {{ display:flex; flex-direction:column; align-items:center;
                      justify-content:center; width:100%; margin:2rem 0; }}
  .chart-title {{ color:#FFFFFF; font-size:16px; font-weight:bold;
                  margin-bottom:1rem; text-align:center; }}
  #pie-chart {{ width:95%; max-width:900px; height:450px; }}
</style>
</head>
<body>
<div class="chart-container">
  <div class="chart-title">{title}</div>
  <div id="pie-chart"></div>
</div>
<script>
Highcharts.setOptions({{ colors: {series_json}.map(d => d.color) }});
Highcharts.chart('pie-chart', {{
  chart: {{ type:'pie', backgroundColor:'transparent',
            style:{{ fontFamily:'Arial,sans-serif' }} }},
  title: {{ text:null }},
  tooltip: {{
    backgroundColor:'rgba(0,0,0,0.8)', borderColor:'rgba(0,0,0,0.8)',
    style:{{ color:'#FFFFFF', fontSize:'12px' }},
    headerFormat:'',
    pointFormat:'<b>{{point.name}}</b>: {{point.y:,.0f}} ({{point.percentage:.1f}}%)'
  }},
  plotOptions: {{
    pie: {{
      innerSize: '{inner_size}', depth:45, allowPointSelect:true, cursor:'pointer',
      dataLabels: {{
        enabled:true,
        formatter: function() {{
          return Math.round(this.percentage) + '%';
        }},
        style:{{ fontSize:'9px', fontWeight:'bold', color:'#FFFFFF',
                 textShadow:'0 0 3px rgba(0,0,0,0.8)' }},
        connectorColor:'#FFFFFF'
      }},
      events: {{ legendItemClick: function() {{ return false; }} }}
    }}
  }},
  series: [{{ name:'', colorByPoint:true, data:{series_json} }}],
  legend: {{
    enabled:true, layout:'horizontal', align:'center', verticalAlign:'bottom',
    itemStyle:{{ color:'#FFFFFF', fontSize:'12px' }}, symbolRadius:2
  }},
  credits:{{ enabled:false }},
  exporting:{{ enabled:false }}
}});
</script>
</body>
</html>"""

    def _render_pie_chart_highcharts(self, chart_data: Dict) -> str:
        return self._pie_highcharts_html(chart_data, rtl=False)

    def _render_pie_chart_highcharts_rtl(self, chart_data: Dict) -> str:
        return self._pie_highcharts_html(chart_data, rtl=True)

    # ---- Chart.js bar / other (shared core) ----

    def _chartjs_html(self, chart_data: Dict, rtl: bool) -> str:
        chart_type = chart_data.get('type', 'bar')
        title      = chart_data.get('title', '')
        categories = chart_data.get('categories', [])
        series     = chart_data.get('series', [])
        provided   = chart_data.get('colors', [])

        # Chart.js v3 uses 'bar' for vertical bar charts; normalize 'column'
        js_type = 'bar' if chart_type == 'column' else chart_type

        # For RTL bar charts reverse axes
        if rtl and chart_type not in ('pie', 'doughnut'):
            categories = list(reversed(categories))
            series = [{'name': s['name'], 'data': list(reversed(s['data']))} for s in series]

        # Build datasets
        if chart_type in ('bar', 'horizontalBar', 'column'):
            colors = self._get_colors_for_chart(chart_type, len(series),
                                                provided or None, num_series=len(series))
            datasets = []
            for i, ser in enumerate(series):
                c = colors[i]
                datasets.append({
                    'label': ser['name'],
                    'data': ser['data'],
                    'backgroundColor': [c] * len(ser['data']),
                    'borderColor':     [c] * len(ser['data']),
                    'borderWidth': 0
                })
        else:
            colors = self._get_colors_for_chart(chart_type, len(series), provided or None)
            datasets = [{
                'label': ser['name'],
                'data': ser['data'],
                'backgroundColor': colors[i] if i < len(colors) else f'hsl({i*60},70%,50%)',
                'borderColor':     colors[i] if i < len(colors) else f'hsl({i*60},70%,50%)',
                'borderWidth': 0
            } for i, ser in enumerate(series)]

        datasets_json  = json.dumps(datasets,   ensure_ascii=False)
        categories_json = json.dumps(categories, ensure_ascii=False)
        title_json     = json.dumps(title,       ensure_ascii=False)

        show_scales = chart_type not in ('pie', 'doughnut')
        y_position  = "'right'" if rtl else "'left'"
        dir_attr    = 'dir="rtl"' if rtl else ''
        dir_style   = 'direction:rtl;' if rtl else ''
        chart_id    = f"chart_{abs(hash(title + str(rtl)))}"

        return f"""<!DOCTYPE html>
<html {dir_attr}>
<head>
<meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js"></script>
</head>
<body style="background:transparent;margin:0;padding:0;{dir_style}">
<div style="display:flex;justify-content:center;margin:2rem 0;width:100%;">
  <div style="width:95%;max-width:900px;height:450px;">
    <canvas id="{chart_id}"></canvas>
  </div>
</div>
<script>
document.addEventListener('DOMContentLoaded', function() {{
  setTimeout(function() {{
    var ctx = document.getElementById('{chart_id}');
    if (!ctx) return;
    new Chart(ctx, {{
      type: '{js_type}',
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
            font: {{ size:14, weight:'bold' }},
            padding: {{ top:10, bottom:50 }}
          }},
          legend: {{
            display: true,
            position: 'bottom',
            labels: {{
              padding: 20,
              font: {{ size:12, weight:'bold' }},
              color: '#FFFFFF',
              boxWidth: 18, boxHeight: 18,
              borderRadius: 4,
              generateLabels: function(chart) {{
                var datasets = chart.data.datasets;
                var type = chart.config.type;
                if (type === 'bar' || type === 'horizontalBar') {{
                  return datasets.map((ds, i) => ({{
                    text: ds.label,
                    fillStyle: ds.backgroundColor[0],
                    hidden: false, index: i
                  }}));
                }}
                return chart.data.labels.map((label, i) => ({{
                  text: label,
                  fillStyle: datasets[0].backgroundColor[i],
                  hidden: false, index: i
                }}));
              }}
            }},
            maxHeight: 200, fullSize: true
          }}
        }},
        scales: {{
          y: {{
            display: {str(show_scales).lower()},
            beginAtZero: true,
            position: {y_position},
            ticks: {{ color:'#FFFFFF', font:{{ size:11 }} }},
            grid:  {{ color:'rgba(0,0,0,0.05)' }}
          }},
          x: {{
            display: {str(show_scales).lower()},
            ticks: {{ color:'#FFFFFF', font:{{ size:11 }} }},
            grid:  {{ display:false }}
          }}
        }}
      }}
    }});
  }}, 100);
}});
</script>
</body>
</html>"""

    def _render_chart_js(self, chart_data: Dict) -> str:
        return self._chartjs_html(chart_data, rtl=False)

    def _render_chart_js_rtl(self, chart_data: Dict) -> str:
        return self._chartjs_html(chart_data, rtl=True)

    # ------------------------------------------------------------------
    # Table rendering
    # ------------------------------------------------------------------

    def _display_table(self, table_data: Dict[str, Any]) -> None:
        columns = table_data.get('columns', [])
        rows    = table_data.get('rows',    [])
        if not columns or not rows:
            return
        st.markdown(self._create_html_table(columns, rows), unsafe_allow_html=True)

    def _create_html_table(self, columns: list, rows: list) -> str:
        html = '<div class="report-table-wrapper"><table class="report-table">'
        html += '<thead><tr>'
        for col in columns:
            html += f'<th>{col}</th>'
        html += '</tr></thead><tbody>'
        for row in rows:
            html += '<tr>'
            for col in columns:
                cell = str(row.get(col, '')).replace('<', '&lt;').replace('>', '&gt;')
                html += f'<td><div class="cell-content">{cell}</div></td>'
            html += '</tr>'
        html += '</tbody></table></div>'
        return html

    # ------------------------------------------------------------------
    # Content → HTML
    # ------------------------------------------------------------------

    def _convert_content_to_html(self, content: str) -> str:
        import re
        lines     = content.split('\n')
        html_parts = []
        in_list   = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if in_list:
                    html_parts.append('</ul>')
                    in_list = False
                continue

            decorative = {'─', '—', '–', '_', '-', '=', '━', '═', '▬', '▭', ' ', '\t'}
            if all(c in decorative for c in stripped):
                continue

            is_bullet   = False
            bullet_text = stripped

            if stripped.startswith(('←', '→', '-', '•', '▪')):
                is_bullet   = True
                bullet_text = stripped.lstrip('←→-•▪').strip()
            elif (stripped.startswith('الشكوى ') and '—' in stripped
                  and re.search(r'خلال\s+\d+\s+(ساعة|ساعات|يوم|أيام)', stripped)):
                is_bullet = True

            if is_bullet:
                if not in_list:
                    html_parts.append('<ul>')
                    in_list = True
                html_parts.append(f'<li>{bullet_text}</li>')
            else:
                if in_list:
                    html_parts.append('</ul>')
                    in_list = False
                html_parts.append(f'<p>{stripped}</p>')

        if in_list:
            html_parts.append('</ul>')

        return '\n'.join(html_parts)

    # ------------------------------------------------------------------
    # Metadata (optional helper)
    # ------------------------------------------------------------------

    def _display_metadata(self, metadata: Dict[str, Any]) -> None:
        cols = st.columns(2)
        with cols[0]:
            if metadata.get('title'):
                st.write(f"**العنوان:** {metadata['title']}"
                         if self.lang == 'ar' else f"**Title:** {metadata['title']}")
            if metadata.get('author'):
                st.write(f"**المؤلف:** {metadata['author']}"
                         if self.lang == 'ar' else f"**Author:** {metadata['author']}")
        with cols[1]:
            if metadata.get('total_paragraphs'):
                st.write(f"**عدد الفقرات:** {metadata['total_paragraphs']}"
                         if self.lang == 'ar' else f"**Paragraphs:** {metadata['total_paragraphs']}")
            if metadata.get('total_tables'):
                st.write(f"**عدد الجداول:** {metadata['total_tables']}"
                         if self.lang == 'ar' else f"**Tables:** {metadata['total_tables']}")


# ---------------------------------------------------------------------------
# Convenience functions (backward-compatible)
# ---------------------------------------------------------------------------

def display_report_from_json(json_path: str, lang: str = 'ar') -> None:
    """
    Standalone function to render a report directly from a JSON file.

    Usage in your Streamlit app:
        from dynamic_display import display_report_from_json
        display_report_from_json("report_final_ar_20260507_130557.json")
    """
    DynamicReportDisplay(lang=lang).display_from_json_file(json_path)


def display_report_tabs(lang: str = 'ar', flow_type: str = 'inquiries') -> None:
    """
    Backward-compatible helper that auto-detects JSON vs. docx.

    Looks for a pre-extracted JSON file first; falls back to the .docx
    + AdaptiveReportExtractor path if no JSON is found.
    """
    app_dir = Path(__file__).parent.parent
    display = DynamicReportDisplay(lang=lang)

    if flow_type == 'complaints':
        json_path = app_dir / "complaints-output"  / "cache" / "report_extracted.json"
        docx_path = app_dir / "complaints-output"  / "تقرير تحليل شكاوى المتعاملين .docx"
        cache_dir = str(app_dir / "complaints-output" / "cache")
    else:
        json_path = app_dir / "inquiries-output" / "cache" / "report_extracted.json"
        docx_path = app_dir / "inquiries-output" / "تقرير تحليل استفسارات المتعاملين.docx"
        cache_dir = str(app_dir / "inquiries-output" / "cache")

    if json_path.exists():
        display.display_from_json_file(str(json_path))
    else:
        display.cache_dir = cache_dir
        display.display_report(str(docx_path))