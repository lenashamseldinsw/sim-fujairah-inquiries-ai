"""Display report with exact Arabic headings and Chart.js visualizations."""

import streamlit as st
import pandas as pd
import json
from pathlib import Path
from typing import Dict, Any
from report_extractor import extract_full_report


# Simple HTML table styling
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
</style>
"""


def create_html_table(columns: list, rows: list) -> str:
    """Create simple HTML table with RTL support - keep column order as is."""

    html = '<div class="report-table-wrapper"><table class="report-table">'

    # Header - keep original column order
    html += '<thead><tr>'
    for col in columns:
        html += f'<th>{col}</th>'
    html += '</tr></thead>'

    # Body - keep original cell order
    html += '<tbody>'
    for row in rows:
        html += '<tr>'
        cells = [str(row.get(col, '')).replace('<', '&lt;').replace('>', '&gt;') for col in columns]
        for cell in cells:
            html += f'<td>{cell}</td>'
        html += '</tr>'
    html += '</tbody>'

    html += '</table></div>'
    return html


def create_bar_chart(chart_id: str, labels: list, data: list, title: str = '') -> str:
    """Create horizontal bar chart using Chart.js."""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js"></script>
    </head>
    <body style="background: transparent; margin: 0; padding: 0;">
        <div style="display: flex; justify-content: center; margin: 2rem 0; width: 100%;">
            <div style="width: 600px; height: 400px;">
                <canvas id="{chart_id}"></canvas>
            </div>
        </div>
        <script>
            setTimeout(function() {{
                var ctx = document.getElementById('{chart_id}');
                if (ctx) {{
                    new Chart(ctx, {{
                        type: 'bar',
                        data: {{
                            labels: {json.dumps(labels)},
                            datasets: [{{
                                label: 'عدد الحالات',
                                data: {json.dumps(data)},
                                backgroundColor: '#5BA4C8',
                                borderColor: '#2E86AB',
                                borderWidth: 1
                            }}]
                        }},
                        options: {{
                            indexAxis: 'y',
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {{
                                legend: {{
                                    labels: {{ color: '#FFFFFF' }}
                                }},
                                title: {{
                                    display: true,
                                    text: '{title}',
                                    color: '#FFFFFF',
                                    font: {{ size: 14 }}
                                }}
                            }},
                            scales: {{
                                x: {{
                                    ticks: {{ color: '#FFFFFF' }},
                                    grid: {{ color: 'rgba(201,150,60,0.1)' }}
                                }},
                                y: {{
                                    ticks: {{ color: '#FFFFFF' }},
                                    grid: {{ color: 'rgba(201,150,60,0.1)' }}
                                }}
                            }}
                        }}
                    }});
                }}
            }}, 100);
        </script>
    </body>
    </html>
    """
    return html


def display_report_tabs(lang: str):
    """Display all 8 sections with exact Arabic headings."""

    # Add styles
    st.markdown(HTML_STYLES, unsafe_allow_html=True)

    report_path = Path("outputs/تقرير تحليل استفسارات المتعاملين.docx")
    if not report_path.exists():
        st.warning("❌ لم يتم العثور على ملف التقرير" if lang == 'ar' else "❌ Report file not found")
        return

    # Extract report
    try:
        report = extract_full_report(str(report_path))
    except Exception as e:
        st.error(f"❌ خطأ في استخراج البيانات: {str(e)}" if lang == 'ar' else f"❌ Error: {str(e)}")
        return

    # Create 8 tabs with exact Arabic headings
    tab_titles = [
        "الملخص التنفيذي — التحليلات الاستراتيجية",
        "التحليل الأول — خريطة عبء العمل الحقيقي",
        "التحليل الثاني — التحديات في رحلة المتعامل",
        "التحليل الثالث — تحليل الفجوات الرقمية",
        "التحليل الرابع — استراتيجية التحويل الرقمي",
        "حالات الاستخدام المدعومة بالذكاء الاصطناعي",
        "خارطة الطريق الاستراتيجية المتكاملة",
        "الخلاصة — من البيانات إلى القرار"
    ]

    tabs = st.tabs(tab_titles)

    with tabs[0]:
        display_executive_summary(report, lang)
    with tabs[1]:
        display_analysis_1(report, lang)
    with tabs[2]:
        display_analysis_2(report, lang)
    with tabs[3]:
        display_analysis_3(report, lang)
    with tabs[4]:
        display_analysis_4(report, lang)
    with tabs[5]:
        display_use_cases(report, lang)
    with tabs[6]:
        display_roadmap(report, lang)
    with tabs[7]:
        display_conclusion(report, lang)


def display_table(table_data: dict, table_title: str = None):
    """Display HTML table with optional title."""
    if not table_data.get('rows'):
        return

    if table_title:
        st.markdown(f"#### {table_title}")

    columns = table_data.get('columns', [])
    rows = table_data.get('rows', [])

    html = create_html_table(columns, rows)
    st.markdown(html, unsafe_allow_html=True)


def display_executive_summary(report: dict, lang: str):
    """Display Executive Summary tab with tables first, then charts."""
    sec = report['sections']['executive_summary']

    if sec.get('key_message'):
        st.markdown(f"""
        <div style="padding: 1.5rem; border-radius: 0.5rem; background: rgba(201, 150, 60, 0.05); border: 1px solid rgba(201, 150, 60, 0.2); max-width: 95%; margin: 1.5rem auto; direction: rtl; text-align: right;">
            <p style="margin: 0; color: #E4E4F0; font-size: 0.95rem; line-height: 1.8;">
                <strong style="color: #B68A35;">الرسالة الجوهرية:</strong><br>{sec['key_message']}
            </p>
        </div>
        """, unsafe_allow_html=True)

    # Display tables first
    if sec.get('tables'):
        for table_data in sec['tables']:
            display_table(table_data, 'النتائج الرئيسية')

    # Display charts second
    if report.get('charts'):
        st.markdown("<br>", unsafe_allow_html=True)
        for chart_data in report['charts']:
            try:
                chart_html = render_chart_js(chart_data)
                st.components.v1.html(chart_html, height=500)
            except Exception as e:
                st.error(f"Error displaying chart: {str(e)}")


def render_chart_js(chart_data: Dict) -> str:
    """Render extracted chart data as Chart.js visualization matching Word document."""
    chart_type = chart_data['type']
    title = chart_data['title']
    categories = chart_data['categories']
    series = chart_data['series']
    colors = chart_data['colors']

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
            <canvas id="native_chart"></canvas>
        </div>
    </div>
    <script>
        document.addEventListener('DOMContentLoaded', function() {{
            setTimeout(function() {{
                var ctx = document.getElementById('native_chart');
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


def display_analysis_1(report: dict, lang: str):
    """Display Analysis 1 tab with subsections."""
    sec = report['sections']['analysis_1']

    subsection_titles = {
        'Communication Types': '2.1 التوزيع الفعلي لأنواع الاستفسارات',
        'Misclassified Cases Examples': '2.2 دقة التصنيف —26% من الاستفسارات تم إعادة تصنيفها',
    }

    if sec.get('tables'):
        for idx, table_data in enumerate(sec['tables']):
            original_title = table_data['title']
            display_title = subsection_titles.get(original_title, original_title)
            display_table(table_data, display_title)

            if idx < len(sec['tables']) - 1:
                st.markdown("<br>", unsafe_allow_html=True)


def display_analysis_2(report: dict, lang: str):
    """Display Analysis 2 tab."""
    sec = report['sections']['analysis_2']

    if sec.get('tables'):
        for table_data in sec['tables']:
            display_table(table_data)


def display_analysis_3(report: dict, lang: str):
    """Display Analysis 3 tab with subsections."""
    sec = report['sections']['analysis_3']

    subsection_titles = {
        'Digital Gaps': '4.1 جدول الفجوات المُدمج (ربط الاستفسار بالفجوة)',
        'Root Causes': '4.2 الأسباب الجذرية لاستمرار المشكلات',
    }

    if sec.get('tables'):
        for table_data in sec['tables']:
            original_title = table_data['title']
            display_title = subsection_titles.get(original_title, original_title)
            display_table(table_data, display_title)


def display_analysis_4(report: dict, lang: str):
    """Display Analysis 4 tab with subsections."""
    sec = report['sections']['analysis_4']

    subsection_titles = {
        'FAQ Questions': '5.1 الأسئلة الشائعة ذات الأولوية (مستخرجة من بيانات الاستفسارات)',
        'Notification Strategy': '5.2 مسار إلغاء 162 حالة تواصل بالإشعار الاستباقي',
    }

    if sec.get('tables'):
        for table_data in sec['tables']:
            original_title = table_data['title']
            display_title = subsection_titles.get(original_title, original_title)
            display_table(table_data, display_title)


def display_use_cases(report: dict, lang: str):
    """Display AI Use Cases tab."""
    sec = report['sections']['use_cases']

    if sec.get('tables'):
        for table_data in sec['tables']:
            display_table(table_data)


def display_roadmap(report: dict, lang: str):
    """Display Strategic Roadmap tab."""
    sec = report['sections']['roadmap']

    if sec.get('tables'):
        for table_data in sec['tables']:
            display_table(table_data)


def display_conclusion(report: dict, lang: str):
    """Display Conclusion tab."""
    sec = report['sections']['conclusion']

    if sec.get('tables'):
        for table_data in sec['tables']:
            original_title = table_data['title']
            display_title = None
            if original_title == 'Transformation Axes':
                display_title = 'المحاور الثلاثة للتحول'
            display_table(table_data, display_title)
