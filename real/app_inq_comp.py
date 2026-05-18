"""
Unified Fujairah Pulse app - supports both inquiries and complaints flows.
Run with: streamlit run app_inq_comp.py
"""

import streamlit as st
import time
import os
import json
import traceback
from pathlib import Path
from report_display import display_report_tabs
from analysis import get_analyzer_for_flow, get_display_for_flow
from dotenv import load_dotenv
import zipfile
import io

# Load environment variables
load_dotenv()
APP_MODE = os.getenv('APP_MODE', 'real').lower()

# Page configuration
st.set_page_config(
    page_title="Fujairah Pulse · Smart Services",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── Color Palette ─────────────────────────────────────────────────────────────
GOLD        = "#B68A35"
GOLD_LIGHT  = "#E2B95A"
GOLD_PALE   = "#F0D080"
GOLD_DARK   = "#B68A35"
BG_DEEP     = "#08080F"
BG_MAIN     = "#0D0D1A"
BG_CARD     = "#111120"
BG_CARD2    = "#17172A"
GREEN       = "#1a6b3c"
GREEN_OK    = "#3DD68C"
TEXT        = "#E4E4F0"
TEXT_MUTED  = "#7070A0"
WHITE       = "#FFFFFF"
BORDER_G    = "rgba(201,150,60,0.18)"
BORDER_G2   = "rgba(201,150,60,0.35)"

# Complaints colors
BLUE        = "#2E86AB"
BLUE_LIGHT  = "#5BA4C8"
BLUE_PALE   = "#A8D4E8"
BLUE_DARK   = "#1A6080"
BORDER_B    = "rgba(46,134,171,0.18)"
BORDER_B2   = "rgba(46,134,171,0.35)"

# ── Translations ──────────────────────────────────────────────────────────────
T = {
    'ar': {
        'nav_back':          '← العودة للرئيسية',
        'hero_eyebrow':      'شرطة الفجيرة · الخدمات الذكية',
        'hero_title':        'نبض الفجيرة',
        'hero_subtitle':     'منصة ذكاء اصطناعي لتحليل استفسارات وشكاوى المتعاملين وتحسين جودة الخدمات الحكومية',
        'badge_speed':       '⚡ معالجة فورية',
        'badge_accuracy':    '🎯 دقة عالية',
        'badge_security':    '🔒 بيانات آمنة',
        'badge_reports':     '📊 تقارير شاملة',
        'section_label':     'اختر الخدمة',
        'section_title':     'ماذا تريد أن تحلل؟',
        'inq_card_title':    'تحليل الاستفسارات',
        'inq_card_desc':     'حلّل استفسارات المتعاملين واستخرج الأنماط والتوجهات لتحسين مستوى الخدمة وسرعة الاستجابة.',
        'inq_tag1':          'Excel / PDF',
        'inq_tag2':          'تقرير Word',
        'inq_tag3':          'نتائج فورية',
        'cmp_card_title':    'تحليل الشكاوى',
        'cmp_card_desc':     'حلّل شكاوى المتعاملين وصنّفها حسب الأولوية والنوع واستخرج توصيات لمعالجة الأسباب الجذرية.',
        'cmp_tag1':          'Excel / PDF',
        'cmp_tag2':          'تقرير Word',
        'cmp_tag3':          'نتائج فورية',
        'btn_inq':           'ابدأ تحليل الاستفسارات  ←',
        'btn_cmp':           'ابدأ تحليل الشكاوى  ←',
        'footer_copy':       '© 2026 شرطة الفجيرة · جميع الحقوق محفوظة',
        'inq_header_tag':    'تحليل الاستفسارات',
        'inq_header_title':  'رفع وتحليل الملفات',
        'inq_header_sub':    'ارفع ملفك واترك الذكاء الاصطناعي يقوم بالباقي',
        'inq_panel_title':   'رفع الملف',
        'inq_panel_sub':     'ادعم صيغ Excel و PDF · الحد الأقصى 200 ميجابايت',
        'uploader_label':    'اختر ملف Excel (.xlsx, .xls) أو PDF',
        'uploader_help':     'الحد الأقصى لحجم الملف: 200 ميجابايت',
        'file_key':          'الملف:',
        'size_key':          'الحجم:',
        'type_key':          'النوع:',
        'size_kb':           'كيلوبايت',
        'size_mb':           'ميجابايت',
        'btn_start_inq':     'بدء التحليل والمعالجة  ←',
        'stage_badge_inq':   'تحليل جارٍ',
        'stage_title':       'يرجى الانتظار',
        'stage_desc_inq':    'نقوم بتحليل الاستفسارات وإنشاء تقريرك الشامل...',
        'success_title_inq': 'تم إنشاء التقرير بنجاح',
        'success_sub_inq':   'تم تحليل جميع الاستفسارات — التقرير جاهز للتحميل',
        'btn_download_inq':  '📥  تحميل تقرير الاستفسارات',
        'btn_reset':         'تحليل ملف جديد',
        'cmp_header_tag':    'تحليل الشكاوى',
        'cmp_header_title':  'رفع وتحليل الشكاوى',
        'cmp_header_sub':    'ارفع ملف الشكاوى واستخرج الرؤى والتوصيات تلقائياً',
        'cmp_panel_title':   'رفع ملف الشكاوى',
        'cmp_panel_sub':     'ادعم صيغ Excel و PDF · الحد الأقصى 200 ميجابايت',
        'btn_start_cmp':     'بدء تحليل الشكاوى  ←',
        'stage_badge_cmp':   'تحليل جارٍ',
        'stage_desc_cmp':    'نقوم بتحليل الشكاوى وإعداد التوصيات اللازمة...',
        'success_title_cmp': 'تم إنشاء تقرير الشكاوى بنجاح',
        'success_sub_cmp':   'تم تحليل جميع الشكاوى — التقرير جاهز للتحميل',
        'btn_download_cmp':  '📥  تحميل تقرير الشكاوى',
        'err_no_file':       'يرجى رفع ملف أولاً',
        'err_bad_type':      'نوع الملف غير مدعوم. يرجى رفع ملف Excel (.xlsx, .xls) أو PDF',
    },
    'en': {
        'nav_back':          '← Back to Home',
        'hero_eyebrow':      'Fujairah Police · Smart Services',
        'hero_title':        'Fujairah Pulse',
        'hero_subtitle':     'An AI platform for analyzing citizen inquiries and complaints to improve government service quality.',
        'badge_speed':       '⚡ Instant Processing',
        'badge_accuracy':    '🎯 High Accuracy',
        'badge_security':    '🔒 Secure Data',
        'badge_reports':     '📊 Comprehensive Reports',
        'section_label':     'Choose a Service',
        'section_title':     'What would you like to analyze?',
        'inq_card_title':    'Inquiries Analysis',
        'inq_card_desc':     'Analyze citizen inquiries and extract patterns and trends to improve service quality and response speed.',
        'inq_tag1':          'Excel / PDF',
        'inq_tag2':          'Word Report',
        'inq_tag3':          'Instant Results',
        'cmp_card_title':    'Complaints Analysis',
        'cmp_card_desc':     'Analyze citizen complaints, classify by priority and type, and extract recommendations to address root causes.',
        'cmp_tag1':          'Excel / PDF',
        'cmp_tag2':          'Word Report',
        'cmp_tag3':          'Instant Results',
        'btn_inq':           'Start Inquiries Analysis  →',
        'btn_cmp':           'Start Complaints Analysis  →',
        'footer_copy':       '© 2026 Fujairah Police · All Rights Reserved',
        'inq_header_tag':    'Inquiries Analysis',
        'inq_header_title':  'Upload & Analyze Files',
        'inq_header_sub':    'Upload your file and let AI do the rest',
        'inq_panel_title':   'Upload File',
        'inq_panel_sub':     'Supports Excel & PDF · Max 200 MB',
        'uploader_label':    'Choose Excel (.xlsx, .xls) or PDF file',
        'uploader_help':     'Maximum file size: 200 MB',
        'file_key':          'File:',
        'size_key':          'Size:',
        'type_key':          'Type:',
        'size_kb':           'KB',
        'size_mb':           'MB',
        'btn_start_inq':     'Start Analysis  →',
        'stage_badge_inq':   'Processing...',
        'stage_title':       'Please Wait',
        'stage_desc_inq':    'Analyzing inquiries and generating your comprehensive report...',
        'success_title_inq': 'Report Generated Successfully',
        'success_sub_inq':   'All inquiries analyzed — Report ready for download',
        'btn_download_inq':  '📥  Download Inquiries Report',
        'btn_reset':         'Analyze New File',
        'cmp_header_tag':    'Complaints Analysis',
        'cmp_header_title':  'Upload & Analyze Complaints',
        'cmp_header_sub':    'Upload your complaints file and extract insights and recommendations automatically',
        'cmp_panel_title':   'Upload Complaints File',
        'cmp_panel_sub':     'Supports Excel & PDF · Max 200 MB',
        'btn_start_cmp':     'Start Complaints Analysis  →',
        'stage_badge_cmp':   'Processing...',
        'stage_desc_cmp':    'Analyzing complaints and preparing recommendations...',
        'success_title_cmp': 'Complaints Report Generated Successfully',
        'success_sub_cmp':   'All complaints analyzed — Report ready for download',
        'btn_download_cmp':  '📥  Download Complaints Report',
        'err_no_file':       'Please upload a file first',
        'err_bad_type':      'Unsupported file type. Please upload Excel (.xlsx, .xls) or PDF',
    }
}

# ── Session State ─────────────────────────────────────────────────────────────
def init_session_state():
    defaults = {
        'page': 'landing',
        'language': 'ar',
        'uploaded_file': None,
        'processing': False,
        'completed': False,
        'progress': 0,
        'report_data': None,
        'output_files': {},
        'analysis_error': None,
        'flow_type': 'inquiries',
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session_state()

# ── CSS ───────────────────────────────────────────────────────────────────────
def load_css(lang='ar'):
    DIR              = 'rtl' if lang == 'ar' else 'ltr'
    ALIGN            = 'right' if lang == 'ar' else 'left'
    FONT             = "'Tajawal', 'Cairo', sans-serif" if lang == 'ar' else "'Inter', 'Cairo', system-ui, sans-serif"
    BORDER_ACCENT    = 'right' if lang == 'ar' else 'left'

    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;500;600;700;900&family=Tajawal:wght@300;400;500;700&family=Inter:wght@300;400;500;600;700;900&display=swap');

    /* Base */
    *, *::before, *::after {{
        direction: {DIR} !important;
        text-align: {ALIGN} !important;
        box-sizing: border-box;
        font-family: {FONT} !important;
    }}
    html, body {{
        font-family: {FONT} !important;
        background: {BG_DEEP} !important;
    }}
    .stApp, [data-testid="stApp"],
    [data-testid="stAppViewContainer"] {{
        background: {BG_DEEP} !important;
    }}
    .main, section.main {{
        background: {BG_DEEP} !important;
        padding: 0 !important;
    }}
    [data-testid="stVerticalBlock"] {{
        gap: 0 !important;
    }}
    .block-container {{
        max-width: 1320px !important;
        padding-left: 3.5rem !important;
        padding-right: 3.5rem !important;
        padding-top: 0 !important;
        padding-bottom: 0 !important;
        margin-left: auto !important;
        margin-right: auto !important;
    }}
    #MainMenu, footer, header {{ visibility: hidden; }}

    /* Buttons */
    .stButton > button {{
        background: linear-gradient(110deg, {GOLD_DARK} 0%, {GOLD} 28%, {GOLD_LIGHT} 52%, {GOLD_PALE} 66%, {GOLD_LIGHT} 80%, {GOLD} 100%);
        background-size: 260% 260%;
        color: {BG_DEEP} !important;
        font-family: {FONT} !important;
        font-weight: 700;
        font-size: 1.05rem;
        border: none !important;
        border-radius: 12px;
        padding: 0.85rem 2rem;
        width: 100%;
        cursor: pointer;
        position: relative;
        overflow: hidden;
        transition: transform 0.25s ease, box-shadow 0.25s ease;
        box-shadow: 0 4px 20px rgba(201,150,60,0.28);
        direction: {DIR} !important;
        letter-spacing: 0.3px;
    }}
    .stButton > button:hover {{
        transform: translateY(-3px);
        box-shadow: 0 10px 38px rgba(201,150,60,0.52);
        color: {BG_DEEP} !important;
    }}
    .stButton > button:active {{
        transform: translateY(0);
        box-shadow: 0 3px 14px rgba(201,150,60,0.35);
    }}

    .blue-btn .stButton > button {{
        background: linear-gradient(110deg, {BLUE_DARK} 0%, {BLUE} 30%, {BLUE_LIGHT} 55%, {BLUE_PALE} 70%, {BLUE_LIGHT} 82%, {BLUE} 100%) !important;
        background-size: 260% 260% !important;
        box-shadow: 0 4px 20px rgba(46,134,171,0.28) !important;
    }}
    .blue-btn .stButton > button:hover {{
        box-shadow: 0 10px 38px rgba(46,134,171,0.52) !important;
    }}

    /* Hero Section */
    .hero-section {{
        position: relative;
        min-height: 70vh;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
        background: radial-gradient(ellipse 110% 80% at 50% -10%,
                        rgba(201,150,60,0.12) 0%,
                        rgba(13,13,26,0.95) 55%,
                        {BG_DEEP} 100%);
        padding: 5rem 2rem 3rem;
    }}
    .hero-title {{
        font-size: 5.5rem;
        font-weight: 900;
        line-height: 1.1;
        letter-spacing: 2px;
        margin: 0 0 1.2rem 0;
        background: linear-gradient(160deg, {GOLD_PALE} 0%, {GOLD_LIGHT} 40%, {GOLD} 75%, {GOLD_DARK} 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        text-align: center !important;
        direction: {DIR} !important;
    }}
    .hero-subtitle {{
        font-size: 1.35rem;
        font-weight: 400;
        color: rgba(228,228,240,0.75);
        max-width: 640px;
        margin: 0 auto 2.5rem;
        line-height: 1.9;
        text-align: center !important;
        direction: {DIR} !important;
    }}

    /* Cards */
    .use-case-grid {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 2rem;
        max-width: 860px;
        margin: 0.5rem auto 0;
        padding: 0 1rem;
    }}
    .use-case-card {{
        border-radius: 24px;
        padding: 2.8rem 2rem 1.8rem;
        text-align: center !important;
        direction: {DIR} !important;
        position: relative;
        overflow: hidden;
        transition: all 0.35s ease;
        display: flex;
        flex-direction: column;
        align-items: center;
    }}
    .inquiries-card {{
        background: {BG_CARD};
        border: 1px solid {BORDER_G};
    }}
    .inquiries-card:hover {{
        border-color: {BORDER_G2};
        box-shadow: 0 24px 64px rgba(201,150,60,0.10);
        transform: translateY(-4px);
    }}
    .complaints-card {{
        background: {BG_CARD};
        border: 1px solid {BORDER_B};
    }}
    .complaints-card:hover {{
        border-color: {BORDER_B2};
        box-shadow: 0 24px 64px rgba(46,134,171,0.10);
        transform: translateY(-4px);
    }}
    .use-case-title {{
        font-size: 1.6rem;
        font-weight: 800;
        margin: 0 0 0.8rem;
        text-align: center !important;
    }}
    .inquiries-card .use-case-title {{ color: {GOLD_LIGHT}; }}
    .complaints-card .use-case-title {{ color: {BLUE_LIGHT}; }}
    .use-case-desc {{
        color: {TEXT_MUTED};
        font-size: 0.98rem;
        line-height: 1.8;
        margin: 0 0 1.8rem;
        flex: 1;
        text-align: center !important;
    }}

    /* Panel */
    .panel {{
        background: {BG_CARD};
        border: 1px solid {BORDER_G};
        border-radius: 20px;
        padding: 2.5rem;
        margin: 0 auto 1.5rem;
        max-width: 820px;
        direction: {DIR} !important;
    }}
    .panel-blue {{
        background: {BG_CARD};
        border: 1px solid {BORDER_B};
        border-radius: 20px;
        padding: 2.5rem;
        margin: 0 auto 1.5rem;
        max-width: 820px;
        direction: {DIR} !important;
    }}
    .panel-title {{
        font-size: 1.3rem;
        font-weight: 700;
        color: {GOLD_LIGHT};
        margin: 0 0 0.4rem;
        direction: {DIR} !important;
        text-align: {ALIGN} !important;
    }}
    .panel-blue .panel-title {{ color: {BLUE_LIGHT}; }}
    .panel-subtitle {{
        font-size: 0.95rem;
        color: {TEXT_MUTED};
        margin: 0 0 1.8rem;
        direction: {DIR} !important;
        text-align: {ALIGN} !important;
    }}

    /* File Uploader */
    [data-testid="stFileUploader"] section {{
        background: rgba(201,150,60,0.03) !important;
        border: 1.5px dashed rgba(201,150,60,0.3) !important;
        border-radius: 14px !important;
        padding: 1.5rem !important;
        transition: all 0.25s ease;
    }}
    [data-testid="stFileUploader"] section:hover {{
        border-color: rgba(201,150,60,0.55) !important;
        background: rgba(201,150,60,0.05) !important;
    }}
    .blue-uploader [data-testid="stFileUploader"] section {{
        background: rgba(46,134,171,0.03) !important;
        border-color: rgba(46,134,171,0.3) !important;
    }}
    .blue-uploader [data-testid="stFileUploader"] section:hover {{
        border-color: rgba(46,134,171,0.55) !important;
        background: rgba(46,134,171,0.05) !important;
    }}

    /* File Meta */
    .file-meta {{
        background: rgba(201,150,60,0.04);
        border: 1px solid {BORDER_G};
        border-{BORDER_ACCENT}: 3px solid {GOLD};
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        margin: 1.2rem 0;
        direction: {DIR} !important;
    }}
    .file-meta-blue {{
        background: rgba(46,134,171,0.04);
        border: 1px solid {BORDER_B};
        border-{BORDER_ACCENT}: 3px solid {BLUE};
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        margin: 1.2rem 0;
        direction: {DIR} !important;
    }}
    .file-meta-key {{
        color: {GOLD};
        font-weight: 600;
        font-size: 0.9rem;
    }}
    .file-meta-key-blue {{
        color: {BLUE_LIGHT};
        font-weight: 600;
        font-size: 0.9rem;
    }}
    .file-meta-val {{
        color: {TEXT_MUTED};
        font-size: 0.9rem;
    }}

    /* Page Header */
    .page-header {{
        background: linear-gradient(180deg, rgba(201,150,60,0.07) 0%, transparent 100%);
        border-bottom: 1px solid {BORDER_G};
        padding: 3rem 2rem 2.5rem;
        text-align: center !important;
        direction: {DIR} !important;
    }}
    .page-header-tag {{
        display: inline-block;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 3px;
        color: {GOLD};
        text-transform: uppercase;
        margin-bottom: 0.7rem;
    }}
    .page-header-title {{
        font-size: 2.8rem;
        font-weight: 800;
        color: {TEXT};
        margin: 0 0 0.6rem;
        direction: {DIR} !important;
        text-align: center !important;
    }}
    .page-header-complaints {{
        background: linear-gradient(180deg, rgba(46,134,171,0.07) 0%, transparent 100%);
        border-bottom: 1px solid {BORDER_B};
        padding: 3rem 2rem 2.5rem;
        text-align: center !important;
        direction: {DIR} !important;
    }}
    .page-header-complaints .page-header-tag {{ color: {BLUE_LIGHT}; }}

    /* Progress */
    .stProgress > div > div > div > div {{
        background: linear-gradient(90deg, {GOLD_DARK}, {GOLD}, {GOLD_LIGHT});
        border-radius: 10px;
    }}
    .blue-progress .stProgress > div > div > div > div {{
        background: linear-gradient(90deg, {BLUE_DARK}, {BLUE}, {BLUE_LIGHT}) !important;
    }}

    /* Stage Panel */
    .stage-panel {{
        background: {BG_CARD};
        border: 1px solid {BORDER_G};
        border-radius: 16px;
        padding: 2rem;
        text-align: center !important;
        direction: {DIR} !important;
        max-width: 820px;
        margin: 0 auto;
    }}
    .stage-panel-blue {{
        background: {BG_CARD};
        border: 1px solid {BORDER_B};
        border-radius: 16px;
        padding: 2rem;
        text-align: center !important;
        direction: {DIR} !important;
        max-width: 820px;
        margin: 0 auto;
    }}
    .stage-title {{
        font-size: 1.4rem;
        font-weight: 700;
        color: {TEXT};
        margin: 0.5rem 0 0.3rem;
        direction: {DIR} !important;
        text-align: center !important;
    }}
    .stage-desc {{
        font-size: 0.95rem;
        color: {TEXT_MUTED};
        direction: {DIR} !important;
        text-align: center !important;
    }}

    /* Success Panel */
    .success-panel {{
        background: rgba(61,214,140,0.06);
        border: 1px solid rgba(61,214,140,0.2);
        border-radius: 16px;
        padding: 1.2rem;
        text-align: center !important;
        direction: {DIR} !important;
        max-width: 820px;
        margin: 0 auto 2rem;
    }}
    .success-title {{
        font-size: 1.8rem;
        font-weight: 700;
        color: {GREEN_OK};
        margin: 0.5rem 0 0.3rem;
        text-align: center !important;
    }}
    .success-sub {{
        color: {TEXT_MUTED};
        font-size: 0.95rem;
        text-align: center !important;
    }}

    /* Download Button */
    .stDownloadButton > button {{
        background: transparent !important;
        border: 1.5px solid {GOLD} !important;
        color: {GOLD} !important;
        font-family: {FONT} !important;
        font-weight: 600;
        font-size: 1.05rem;
        border-radius: 12px;
        padding: 0.85rem 2rem;
        width: 100%;
        position: relative;
        overflow: hidden;
        transition: transform 0.25s ease, color 0.25s ease;
        direction: {DIR} !important;
    }}
    .stDownloadButton > button:hover {{
        color: {BG_DEEP} !important;
        border-color: transparent !important;
        box-shadow: 0 10px 36px rgba(201,150,60,0.48) !important;
        transform: translateY(-3px);
        background: linear-gradient(110deg, {GOLD_DARK}, {GOLD}, {GOLD_LIGHT}) !important;
    }}
    .blue-download .stDownloadButton > button {{
        border-color: {BLUE} !important;
        color: {BLUE_LIGHT} !important;
    }}
    .blue-download .stDownloadButton > button:hover {{
        background: linear-gradient(110deg, {BLUE_DARK}, {BLUE}, {BLUE_LIGHT}) !important;
        color: {BG_DEEP} !important;
        border-color: transparent !important;
    }}
    </style>
    """, unsafe_allow_html=True)

load_css(st.session_state.get('language', 'ar'))

# ── Analyzer Setup ────────────────────────────────────────────────────────────
def get_analyzer_for_flow(flow_type: str):
    """Get analyzer instance for the current flow."""
    from analysis import get_analyzer_for_flow as get_analyzer
    return get_analyzer(flow_type)

# ── Process File ──────────────────────────────────────────────────────────────
def process_file_with_analyzer(uploaded_file, flow_type: str, lang='ar'):
    """Process file through the appropriate analyzer pipeline."""
    lang_t = T[lang]

    try:
        analyzer = get_analyzer_for_flow(flow_type)

        # Validate file
        is_valid, error_msg = analyzer.validate_file(uploaded_file)
        if not is_valid:
            st.session_state.analysis_error = error_msg or lang_t['err_bad_type']
            return None

        # Progress tracking
        progress_placeholder = st.empty()
        progress_bar = st.progress(0)

        def update_progress(progress_pct, msg_ar, msg_en):
            msg = msg_ar if lang == 'ar' else msg_en
            progress_placeholder.markdown(f"""
            <div style="text-align:center;padding:1rem;color:#E4E4F0;font-size:1.1rem;font-weight:600;margin-bottom:0.5rem;">
                {msg}
            </div>
            """, unsafe_allow_html=True)
            progress_bar.progress(min(progress_pct, 1.0))

        # Run analyzer
        report = analyzer.analyze(uploaded_file, progress_callback=update_progress)

        # Clear progress
        progress_placeholder.empty()
        progress_bar.empty()

        if not report.get('success', False):
            st.session_state.analysis_error = report.get('message', 'Analysis failed')
            return None

        return report

    except Exception as e:
        st.session_state.analysis_error = str(e)
        import traceback
        st.session_state.error_traceback = traceback.format_exc()
        return None

# ── Landing Page ──────────────────────────────────────────────────────────────
def show_landing_page():
    """Display the landing page with flow selection."""
    lang = st.session_state.language
    tx = T[lang]

    st.markdown(f"""
    <div class="hero-section">
        <h1 class="hero-title">{tx['hero_title']}</h1>
        <p class="hero-subtitle">{tx['hero_subtitle']}</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style="text-align:center;padding:3rem 0 2rem;">
        <p style="font-size:0.78rem;font-weight:700;letter-spacing:3px;color:{GOLD};text-transform:uppercase;margin-bottom:1rem;">
            {tx['section_label']}
        </p>
        <h2 style="font-size:2.6rem;font-weight:700;color:{TEXT};margin:0 0 2rem;text-align:center;">{tx['section_title']}</h2>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown(f"""
        <div class="use-case-card inquiries-card">
            <h3 class="use-case-title">{tx['inq_card_title']}</h3>
            <p class="use-case-desc">{tx['inq_card_desc']}</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button(tx['btn_inq'], key='btn_inquiries', use_container_width=True):
            st.session_state.page = 'inquiries'
            st.session_state.flow_type = 'inquiries'
            st.rerun()

    with col2:
        st.markdown(f"""
        <div class="use-case-card complaints-card">
            <h3 class="use-case-title">{tx['cmp_card_title']}</h3>
            <p class="use-case-desc">{tx['cmp_card_desc']}</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button(tx['btn_cmp'], key='btn_complaints', use_container_width=True):
            st.session_state.page = 'complaints'
            st.session_state.flow_type = 'complaints'
            st.rerun()

# ── Inquiries Page ────────────────────────────────────────────────────────────
def show_inquiries_page():
    """Display inquiries analysis page."""
    lang = st.session_state.language
    tx = T[lang]
    flow_type = 'inquiries'

    # Header
    st.markdown(f"""
    <div class="page-header">
        <div class="page-header-tag">{tx['inq_header_tag']}</div>
        <h1 class="page-header-title">{tx['inq_header_title']}</h1>
        <p style="color:{TEXT_MUTED};margin:0;font-size:1rem;text-align:center;direction:{'rtl' if lang=='ar' else 'ltr'};">{tx['inq_header_sub']}</p>
    </div>
    """, unsafe_allow_html=True)

    # Back button
    col_back = st.columns([1, 8, 1])
    with col_back[0]:
        if st.button('← ' + tx['nav_back'], key='back_inq'):
            st.session_state.page = 'landing'
            st.session_state.uploaded_file = None
            st.session_state.processing = False
            st.session_state.completed = False
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # File upload or report display
    if not st.session_state.completed:
        st.markdown(f"""
        <div class="panel">
            <h2 class="panel-title">{tx['inq_panel_title']}</h2>
            <p class="panel-subtitle">{tx['inq_panel_sub']}</p>
        </div>
        """, unsafe_allow_html=True)

        uploaded_file = st.file_uploader(
            tx['uploader_label'],
            type=['xlsx', 'xls', 'pdf'],
            help=tx['uploader_help'],
            key='inq_uploader'
        )

        if uploaded_file:
            st.session_state.uploaded_file = uploaded_file

            # File info
            size_mb = uploaded_file.size / (1024 * 1024)
            size_display = f"{size_mb:.2f} {tx['size_mb']}" if size_mb >= 1 else f"{uploaded_file.size / 1024:.0f} {tx['size_kb']}"

            st.markdown(f"""
            <div class="file-meta">
                <div class="file-meta-row">
                    <span class="file-meta-key">{tx['file_key']}</span>
                    <span class="file-meta-val">{uploaded_file.name}</span>
                </div>
                <div class="file-meta-row">
                    <span class="file-meta-key">{tx['size_key']}</span>
                    <span class="file-meta-val">{size_display}</span>
                </div>
                <div class="file-meta-row">
                    <span class="file-meta-key">{tx['type_key']}</span>
                    <span class="file-meta-val">{uploaded_file.type}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            if st.button(tx['btn_start_inq'], key='start_inq', use_container_width=True):
                st.session_state.processing = True
                st.session_state.completed = False
                st.session_state.analysis_error = None
                st.rerun()

    if st.session_state.processing:
        st.markdown(f"""
        <div class="stage-panel">
            <span style="display:inline-block;background:rgba(201,150,60,0.12);border:1px solid rgba(201,150,60,0.35);border-radius:20px;padding:0.3rem 1rem;font-size:0.8rem;font-weight:700;color:{GOLD};letter-spacing:1px;margin-bottom:1rem;">
                {tx['stage_badge_inq']}
            </span>
            <h2 class="stage-title">{tx['stage_title']}</h2>
            <p class="stage-desc">{tx['stage_desc_inq']}</p>
        </div>
        """, unsafe_allow_html=True)

        # Process file
        report_data = process_file_with_analyzer(st.session_state.uploaded_file, flow_type, lang)

        if report_data:
            st.session_state.report_data = report_data
            st.session_state.output_files = {
                'word': report_data.get('word_path'),
                'excel': report_data.get('excel_path'),
                'word_en': report_data.get('word_path_en'),
            }
            st.session_state.processing = False
            st.session_state.completed = True
            st.rerun()
        else:
            st.session_state.processing = False
            st.rerun()

    if st.session_state.completed and st.session_state.report_data:
        st.markdown(f"""
        <div class="success-panel">
            <h2 class="success-title">✅ {tx['success_title_inq']}</h2>
            <p class="success-sub">{tx['success_sub_inq']}</p>
        </div>
        """, unsafe_allow_html=True)

        # Display report
        display_report_tabs(lang, flow_type)

        # Download buttons
        if st.session_state.output_files.get('word'):
            with open(st.session_state.output_files['word'], 'rb') as f:
                st.download_button(
                    label=tx['btn_download_inq'],
                    data=f,
                    file_name='inquiries_report.docx',
                    mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    use_container_width=True
                )

        if st.button(tx['btn_reset'], key='reset_inq', use_container_width=True):
            st.session_state.uploaded_file = None
            st.session_state.processing = False
            st.session_state.completed = False
            st.session_state.report_data = None
            st.rerun()

    if st.session_state.analysis_error:
        st.error(f"**Error:** {st.session_state.analysis_error}")

# ── Complaints Page ───────────────────────────────────────────────────────────
def show_complaints_page():
    """Display complaints analysis page."""
    lang = st.session_state.language
    tx = T[lang]
    flow_type = 'complaints'

    # Header
    st.markdown(f"""
    <div class="page-header-complaints">
        <div class="page-header-tag">{tx['cmp_header_tag']}</div>
        <h1 class="page-header-title">{tx['cmp_header_title']}</h1>
        <p style="color:{TEXT_MUTED};margin:0;font-size:1rem;text-align:center;direction:{'rtl' if lang=='ar' else 'ltr'};">{tx['cmp_header_sub']}</p>
    </div>
    """, unsafe_allow_html=True)

    # Back button
    col_back = st.columns([1, 8, 1])
    with col_back[0]:
        if st.button('← ' + tx['nav_back'], key='back_cmp'):
            st.session_state.page = 'landing'
            st.session_state.uploaded_file = None
            st.session_state.processing = False
            st.session_state.completed = False
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # File upload or report display
    if not st.session_state.completed:
        st.markdown(f"""
        <div class="panel-blue">
            <h2 class="panel-title">{tx['cmp_panel_title']}</h2>
            <p class="panel-subtitle">{tx['cmp_panel_sub']}</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="blue-uploader">', unsafe_allow_html=True)
        uploaded_file = st.file_uploader(
            tx['uploader_label'],
            type=['xlsx', 'xls', 'pdf'],
            help=tx['uploader_help'],
            key='cmp_uploader'
        )
        st.markdown('</div>', unsafe_allow_html=True)

        if uploaded_file:
            st.session_state.uploaded_file = uploaded_file

            # File info
            size_mb = uploaded_file.size / (1024 * 1024)
            size_display = f"{size_mb:.2f} {tx['size_mb']}" if size_mb >= 1 else f"{uploaded_file.size / 1024:.0f} {tx['size_kb']}"

            st.markdown(f"""
            <div class="file-meta-blue">
                <div class="file-meta-row">
                    <span class="file-meta-key-blue">{tx['file_key']}</span>
                    <span class="file-meta-val">{uploaded_file.name}</span>
                </div>
                <div class="file-meta-row">
                    <span class="file-meta-key-blue">{tx['size_key']}</span>
                    <span class="file-meta-val">{size_display}</span>
                </div>
                <div class="file-meta-row">
                    <span class="file-meta-key-blue">{tx['type_key']}</span>
                    <span class="file-meta-val">{uploaded_file.type}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown('<div class="blue-btn">', unsafe_allow_html=True)
            if st.button(tx['btn_start_cmp'], key='start_cmp', use_container_width=True):
                st.session_state.processing = True
                st.session_state.completed = False
                st.session_state.analysis_error = None
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state.processing:
        st.markdown(f"""
        <div class="stage-panel-blue">
            <span style="display:inline-block;background:rgba(46,134,171,0.12);border:1px solid rgba(46,134,171,0.35);border-radius:20px;padding:0.3rem 1rem;font-size:0.8rem;font-weight:700;color:{BLUE_LIGHT};letter-spacing:1px;margin-bottom:1rem;">
                {tx['stage_badge_cmp']}
            </span>
            <h2 class="stage-title">{tx['stage_title']}</h2>
            <p class="stage-desc">{tx['stage_desc_cmp']}</p>
        </div>
        """, unsafe_allow_html=True)

        # Process file
        report_data = process_file_with_analyzer(st.session_state.uploaded_file, flow_type, lang)

        if report_data:
            st.session_state.report_data = report_data
            st.session_state.output_files = {
                'word': report_data.get('word_path'),
                'excel': report_data.get('excel_path'),
                'word_en': report_data.get('word_path_en'),
            }
            st.session_state.processing = False
            st.session_state.completed = True
            st.rerun()
        else:
            st.session_state.processing = False
            st.rerun()

    if st.session_state.completed and st.session_state.report_data:
        st.markdown(f"""
        <div class="success-panel">
            <h2 class="success-title">✅ {tx['success_title_cmp']}</h2>
            <p class="success-sub">{tx['success_sub_cmp']}</p>
        </div>
        """, unsafe_allow_html=True)

        # Display report
        display_report_tabs(lang, flow_type)

        # Download buttons
        if st.session_state.output_files.get('word'):
            with open(st.session_state.output_files['word'], 'rb') as f:
                st.markdown('<div class="blue-download">', unsafe_allow_html=True)
                st.download_button(
                    label=tx['btn_download_cmp'],
                    data=f,
                    file_name='complaints_report.docx',
                    mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    use_container_width=True
                )
                st.markdown('</div>', unsafe_allow_html=True)

        if st.button(tx['btn_reset'], key='reset_cmp', use_container_width=True):
            st.session_state.uploaded_file = None
            st.session_state.processing = False
            st.session_state.completed = False
            st.session_state.report_data = None
            st.rerun()

    if st.session_state.analysis_error:
        st.error(f"**Error:** {st.session_state.analysis_error}")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    # Language toggle
    lang = st.session_state.language

    col_lang = st.columns([12, 1])
    with col_lang[1]:
        new_lang = 'ar' if lang == 'en' else 'en'
        if st.button('EN / العربية', key='lang_toggle'):
            st.session_state.language = new_lang
            st.rerun()

    # Page routing
    if st.session_state.page == 'landing':
        show_landing_page()
    elif st.session_state.page == 'inquiries':
        show_inquiries_page()
    elif st.session_state.page == 'complaints':
        show_complaints_page()

if __name__ == "__main__":
    main()
