import streamlit as st
import time
import os
import json
import random
import importlib.util
import sys
from pathlib import Path
from report_display import display_report_tabs
from dotenv import load_dotenv
import zipfile
import io

# Load environment variables
load_dotenv()
APP_MODE = os.getenv('APP_MODE', 'demo').lower()

# Page configuration - must be first Streamlit command
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

# Complaints accent — steel blue
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
        'footer_sub':        'Fujairah Government · All Rights Reserved',
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
        'login_title':       'تسجيل الدخول',
        'login_subtitle':    'يرجى تسجيل الدخول للمتابعة',
        'username_label':    'اسم المستخدم',
        'password_label':    'كلمة المرور',
        'login_button':      'تسجيل الدخول',
        'cancel_button':     'إلغاء',
        'login_error':       'اسم المستخدم أو كلمة المرور غير صحيحة',
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
        'footer_sub':        'حكومة الفجيرة · جميع الحقوق محفوظة',
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
        'login_title':       'Login',
        'login_subtitle':    'Please login to continue',
        'username_label':    'Username',
        'password_label':    'Password',
        'login_button':      'Login',
        'cancel_button':     'Cancel',
        'login_error':       'Invalid username or password',
    }
}


# ── CSS ───────────────────────────────────────────────────────────────────────
def load_css(lang='ar'):
    DIR              = 'rtl' if lang == 'ar' else 'ltr'
    ALIGN            = 'right' if lang == 'ar' else 'left'
    FONT             = "'Tajawal', 'Cairo', sans-serif" if lang == 'ar' else "'Inter', 'Cairo', system-ui, sans-serif"
    BORDER_ACCENT    = 'right' if lang == 'ar' else 'left'
    LANG_ACTIVE_COL  = 'first-child' if lang == 'en' else 'last-child'

    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;500;600;700;900&family=Tajawal:wght@300;400;500;700&family=Inter:wght@300;400;500;600;700;900&display=swap');

    /* ── Base ── */
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

    /* ── Scrollbar ── */
    ::-webkit-scrollbar {{ width: 6px; }}
    ::-webkit-scrollbar-track {{ background: {BG_DEEP}; }}
    ::-webkit-scrollbar-thumb {{
        background: {GOLD_DARK};
        border-radius: 3px;
    }}

    /* ── NAV ── */
    .nav-bar {{
        background: rgba(8,8,15,0.92);
        backdrop-filter: blur(24px);
        -webkit-backdrop-filter: blur(24px);
        border-bottom: 1px solid {BORDER_G};
        padding: 0.85rem 2.5rem;
        position: sticky;
        top: 0;
        z-index: 999;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }}
    .nav-logo-wrap img {{
        height: 52px;
        width: auto;
        object-fit: contain;
    }}
    .nav-center-line {{
        height: 1px;
        flex: 1;
        background: linear-gradient(90deg, transparent, {BORDER_G2}, transparent);
        margin: 0 2rem;
    }}

    /* ── Language Toggle Switch ── */
    .stCheckbox {{
        direction: ltr !important;
        text-align: center !important;
    }}

    .stCheckbox label {{
        color: {TEXT} !important;
        font-size: 0.85rem !important;
        font-weight: 500 !important;
        direction: ltr !important;
        justify-content: center !important;
    }}

    .stCheckbox input[type="checkbox"] {{
        accent-color: {GOLD} !important;
    }}

    [data-testid="stCheckbox"] > label {{
        display: flex !important;
        flex-direction: row !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 0.5rem !important;
        direction: ltr !important;
    }}

    [data-testid="stCheckbox"] > label > div {{
        order: 1 !important;
        direction: ltr !important;
    }}

    [data-testid="stCheckbox"] > label > span {{
        order: 2 !important;
        direction: ltr !important;
    }}

    /* ── Nav Back Link ── */
    .nav-back-wrap {{
        text-align: center !important;
    }}
    .nav-back-wrap .stButton > button {{
        background: none !important;
        border: none !important;
        color: rgba(228,228,240,0.32) !important;
        font-family: {FONT} !important;
        font-weight: 400 !important;
        font-size: 0.82rem !important;
        letter-spacing: 0.5px !important;
        padding: 0.3rem 1rem !important;
        box-shadow: none !important;
        animation: none !important;
        transition: color 0.2s ease !important;
        width: auto !important;
        display: block !important;
        margin: 0 auto !important;
    }}
    .nav-back-wrap .stButton > button:hover {{
        background: none !important;
        color: {GOLD_LIGHT} !important;
        transform: none !important;
        box-shadow: none !important;
    }}
    .nav-back-wrap .stButton > button:focus,
    .nav-back-wrap .stButton > button:active {{
        background: none !important;
        box-shadow: none !important;
        outline: none !important;
    }}

    /* ── HERO ── */
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
    .hero-ring {{
        position: absolute;
        border-radius: 50%;
        border: 1px solid rgba(201,150,60,0.08);
        top: 50%; left: 50%;
        transform: translate(-50%, -50%);
        pointer-events: none;
    }}
    .hero-ring-1 {{ width: 500px; height: 500px; border-color: rgba(201,150,60,0.10); }}
    .hero-ring-2 {{ width: 750px; height: 750px; border-color: rgba(201,150,60,0.06); }}
    .hero-ring-3 {{ width: 1050px; height: 1050px; border-color: rgba(201,150,60,0.03); }}
    .hero-glow {{
        position: absolute;
        width: 640px; height: 340px;
        background: radial-gradient(ellipse, rgba(201,150,60,0.10) 0%, transparent 70%);
        top: 0; left: 50%;
        transform: translateX(-50%);
        pointer-events: none;
    }}
    .hero-content {{
        position: relative;
        z-index: 2;
        text-align: center !important;
        direction: {DIR} !important;
        max-width: 960px;
        margin: 0 auto;
    }}
    .hero-eyebrow {{
        display: inline-block;
        font-size: 0.85rem;
        font-weight: 600;
        letter-spacing: 3px;
        text-transform: uppercase;
        color: {GOLD};
        border: 1px solid {BORDER_G2};
        border-radius: 30px;
        padding: 0.4rem 1.4rem;
        margin-bottom: 1.8rem;
        background: rgba(201,150,60,0.06);
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
    .hero-badges {{
        display: flex;
        gap: 0.8rem;
        justify-content: center;
        flex-wrap: wrap;
        margin-bottom: 3rem;
        direction: {DIR} !important;
    }}
    .hero-badge {{
        background: rgba(201,150,60,0.08);
        border: 1px solid {BORDER_G};
        border-radius: 30px;
        padding: 0.5rem 1.3rem;
        color: rgba(228,228,240,0.85);
        font-size: 0.95rem;
        font-weight: 500;
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
    }}

    /* ── USE-CASE CARDS (landing) ── */
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
        transition: all 0.35s cubic-bezier(0.4,0,0.2,1);
        display: flex;
        flex-direction: column;
        align-items: center;
    }}
    .use-case-card::before {{
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 3px;
    }}
    .inquiries-card {{
        background: {BG_CARD};
        border: 1px solid {BORDER_G};
    }}
    .inquiries-card::before {{
        background: linear-gradient(90deg, transparent, {GOLD}, transparent);
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
    .complaints-card::before {{
        background: linear-gradient(90deg, transparent, {BLUE}, transparent);
    }}
    .complaints-card:hover {{
        border-color: {BORDER_B2};
        box-shadow: 0 24px 64px rgba(46,134,171,0.10);
        transform: translateY(-4px);
    }}
    .use-case-icon-wrap {{
        width: 72px; height: 72px;
        border-radius: 18px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 2.2rem;
        margin-bottom: 1.4rem;
    }}
    .inquiries-icon-wrap {{
        background: linear-gradient(135deg, rgba(201,150,60,0.15), rgba(201,150,60,0.04));
        border: 1px solid {BORDER_G2};
    }}
    .complaints-icon-wrap {{
        background: linear-gradient(135deg, rgba(46,134,171,0.15), rgba(46,134,171,0.04));
        border: 1px solid {BORDER_B2};
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
    .use-case-tags {{
        display: flex;
        gap: 0.5rem;
        flex-wrap: wrap;
        justify-content: center;
        margin-bottom: 1.8rem;
    }}
    .use-case-tag {{
        font-size: 0.8rem;
        font-weight: 600;
        border-radius: 20px;
        padding: 0.3rem 0.9rem;
    }}
    .inquiries-tag {{
        background: rgba(201,150,60,0.08);
        border: 1px solid {BORDER_G};
        color: {GOLD};
    }}
    .complaints-tag {{
        background: rgba(46,134,171,0.08);
        border: 1px solid {BORDER_B};
        color: {BLUE_LIGHT};
    }}

    /* ── PAGE HEADER (inquiries) ── */
    .page-header {{
        background: linear-gradient(180deg,
            rgba(201,150,60,0.07) 0%,
            transparent 100%);
        border-bottom: 1px solid {BORDER_G};
        padding: 3rem 2rem 2.5rem;
        text-align: center !important;
        direction: {DIR} !important;
        position: relative;
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
    .page-header-sub {{
        font-size: 1rem;
        color: {TEXT_MUTED};
        margin: 0;
        direction: {DIR} !important;
        text-align: center !important;
    }}
    .page-header-bar {{
        width: 60px; height: 3px;
        background: linear-gradient(90deg, {GOLD_DARK}, {GOLD_LIGHT});
        border-radius: 2px;
        margin: 1rem auto 0;
    }}

    /* ── PAGE HEADER (complaints) ── */
    .page-header-complaints {{
        background: linear-gradient(180deg,
            rgba(46,134,171,0.07) 0%,
            transparent 100%);
        border-bottom: 1px solid {BORDER_B};
        padding: 3rem 2rem 2.5rem;
        text-align: center !important;
        direction: {DIR} !important;
        position: relative;
    }}
    .page-header-complaints .page-header-tag {{ color: {BLUE_LIGHT}; }}
    .page-header-complaints .page-header-bar {{
        background: linear-gradient(90deg, {BLUE_DARK}, {BLUE_LIGHT});
    }}

    /* ── PANELS ── */
    .panel {{
        background: {BG_CARD};
        border: 1px solid {BORDER_G};
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
    .panel-subtitle {{
        font-size: 0.95rem;
        color: {TEXT_MUTED};
        margin: 0 0 1.8rem;
        direction: {DIR} !important;
        text-align: {ALIGN} !important;
    }}
    .panel-divider {{
        height: 1px;
        background: linear-gradient(90deg, {BORDER_G}, transparent);
        margin: 1.5rem 0;
    }}

    /* Panel — blue variant */
    .panel-blue {{
        background: {BG_CARD};
        border: 1px solid {BORDER_B};
        border-radius: 20px;
        padding: 2.5rem;
        margin: 0 auto 1.5rem;
        max-width: 820px;
        direction: {DIR} !important;
    }}
    .panel-blue .panel-title {{ color: {BLUE_LIGHT}; }}
    .panel-blue .panel-divider {{
        background: linear-gradient(90deg, {BORDER_B}, transparent);
    }}

    /* ── FILE UPLOADER ── */
    [data-testid="stFileUploader"] {{
        direction: {DIR} !important;
    }}
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
    [data-testid="stFileUploader"] label {{
        color: {TEXT} !important;
        font-weight: 600;
        direction: {DIR} !important;
    }}
    [data-testid="stFileUploader"] button {{
        display: none !important;
    }}
    [data-testid="stFileUploader"] button::before {{
        display: none !important;
    }}

    /* Blue uploader */
    .blue-uploader [data-testid="stFileUploader"] section {{
        background: rgba(46,134,171,0.03) !important;
        border-color: rgba(46,134,171,0.3) !important;
    }}
    .blue-uploader [data-testid="stFileUploader"] section:hover {{
        border-color: rgba(46,134,171,0.55) !important;
        background: rgba(46,134,171,0.05) !important;
    }}

    /* ── FILE INFO ── */
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
    .file-meta-row {{
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin: 0.35rem 0;
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

    /* ── BUTTONS ── */
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

    /* ── STAGE PANEL ── */
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
    .stage-badge {{
        display: inline-block;
        background: rgba(201,150,60,0.12);
        border: 1px solid {BORDER_G2};
        border-radius: 20px;
        padding: 0.3rem 1rem;
        font-size: 0.8rem;
        font-weight: 700;
        color: {GOLD};
        letter-spacing: 1px;
        margin-bottom: 1rem;
    }}
    .stage-badge-blue {{
        display: inline-block;
        background: rgba(46,134,171,0.12);
        border: 1px solid {BORDER_B2};
        border-radius: 20px;
        padding: 0.3rem 1rem;
        font-size: 0.8rem;
        font-weight: 700;
        color: {BLUE_LIGHT};
        letter-spacing: 1px;
        margin-bottom: 1rem;
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

    /* ── SUCCESS PANEL ── */
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

    /* ── DOWNLOAD BUTTON ── */
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

    /* ── FOOTER ── */
    .footer {{
        border-top: 1px solid {BORDER_G};
        padding: 2.5rem 2rem;
        text-align: center !important;
        direction: {DIR} !important;
        background: rgba(8,8,15,0.6);
        margin-top: 5rem;
    }}
    .footer-divider {{
        height: 1px;
        background: linear-gradient(90deg, transparent, {BORDER_G2}, transparent);
        max-width: 200px;
        margin: 1rem auto;
    }}
    .footer-text {{
        color: {TEXT_MUTED};
        font-size: 0.85rem;
        margin: 0.3rem 0;
        text-align: center !important;
    }}

    /* ── LANGUAGE TOGGLE BUTTON ── */
    [data-testid="stButton"]:has(button:contains("EN")),
    [data-testid="stButton"]:has(button:contains("العربية")) {{
        max-width: 60px !important;
    }}

    [data-testid="stButton"] button {{
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        padding: 0.5rem 0.75rem !important;
        min-height: auto !important;
        height: auto !important;
        background: linear-gradient(110deg, {GOLD_DARK} 0%, {GOLD} 50%, {GOLD_LIGHT} 100%) !important;
        color: {BG_DEEP} !important;
    }}

    /* ── MISC ── */
    h1, h2, h3, h4, h5, h6, p, span, div, label {{
        direction: {DIR} !important;
    }}
    .center-text {{
        text-align: center !important;
        direction: {DIR} !important;
    }}
    </style>
    """, unsafe_allow_html=True)


# ── Session State ─────────────────────────────────────────────────────────────
def init_session_state():
    defaults = {
        'page': 'landing',
        'language': 'ar',
        'uploaded_file': None,
        'processing': False,
        'completed': False,
        'progress': 0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── Analyzer Setup ────────────────────────────────────────────────────────────
def get_analyzer_for_flow(flow_type: str):
    """Get analyzer for the specified flow type."""
    try:
        print(f"[ANALYZER] Loading {flow_type} analyzer...")
        if flow_type == 'complaints':
            flow_path = Path(__file__).parent / "complaints-flow" / "analysis" / "__init__.py"
        else:
            flow_path = Path(__file__).parent / "inquiries-flow" / "analysis" / "__init__.py"

        print(f"[ANALYZER] Flow path: {flow_path}")
        print(f"[ANALYZER] File exists: {flow_path.exists()}")

        spec = importlib.util.spec_from_file_location(f"_{flow_type}_analysis", str(flow_path))
        flow_analysis = importlib.util.module_from_spec(spec)
        sys.modules[f"_{flow_type}_analysis"] = flow_analysis
        print(f"[ANALYZER] Loading module...")
        spec.loader.exec_module(flow_analysis)
        print(f"[ANALYZER] Module loaded. Creating RealAnalyzer instance...")

        # Get API key from Streamlit secrets and pass it to analyzer
        api_key = None
        try:
            api_key = st.secrets.get("ANTHROPIC_API_KEY")
            if api_key:
                print(f"[ANALYZER] ✓ API key loaded from Streamlit secrets: {api_key[:20]}...")
            else:
                print(f"[ANALYZER] ⚠ st.secrets.get() returned None")
                print(f"[ANALYZER] Available secrets keys: {list(st.secrets.keys())}")
        except Exception as e:
            print(f"[ANALYZER] Could not load from st.secrets: {e}, falling back to environment")
            api_key = None

        analyzer = flow_analysis.RealAnalyzer(api_key=api_key)
        print(f"[ANALYZER] ✓ {flow_type} analyzer created successfully")
        return analyzer
    except ValueError as e:
        error_msg = str(e)
        print(f"[ANALYZER] ✗ ValueError: {error_msg}")
        if "ANTHROPIC_API_KEY" in error_msg:
            raise ValueError("API key not configured. Please set ANTHROPIC_API_KEY in Streamlit secrets.")
        raise
    except Exception as e:
        print(f"[ANALYZER] ✗ Exception: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

def get_analyzer():
    """Get analyzer for inquiries flow (app_inq_comp is real-only)."""
    return get_analyzer_for_flow('inquiries')


# ── Validation ────────────────────────────────────────────────────────────────
def validate_file(uploaded_file, lang='ar'):
    tx = T[lang]
    analyzer = get_analyzer()
    is_valid, error_msg = analyzer.validate_file(uploaded_file)
    if not is_valid:
        return False, error_msg or tx['err_bad_type']
    return True, ""


# ── Processing ────────────────────────────────────────────────────────────────
def process_file(uploaded_files, flow_type='inquiries', lang='ar'):
    """Process file with appropriate analyzer for the flow."""
    tx = T[lang]

    if not uploaded_files:
        st.error(tx['err_no_file'])
        return None

    try:
        # Get analyzer for the selected flow
        print(f"\n[PROCESS] Starting {flow_type} flow processing")
        print(f"[PROCESS] Getting analyzer for {flow_type}...")
        analyzer = get_analyzer_for_flow(flow_type)
        print(f"[PROCESS] ✓ Analyzer loaded: {analyzer.__class__.__name__}")

        # Process the first file
        uploaded_file = uploaded_files[0]
        print(f"[PROCESS] Processing file: {uploaded_file.name} ({uploaded_file.size} bytes)")

        # Progress display
        progress_placeholder = st.empty()
        progress_bar = st.progress(0)

        def update_progress(pct, msg_ar, msg_en):
            msg = msg_ar if lang == 'ar' else msg_en
            progress_placeholder.markdown(f"""
            <div style="text-align:center;padding:1rem;color:#E4E4F0;">
                {msg}
            </div>
            """, unsafe_allow_html=True)
            progress_bar.progress(min(pct, 1.0))

        # Run analyzer
        print(f"[PROCESS] Starting analysis...")
        report = analyzer.analyze(uploaded_file, progress_callback=update_progress)
        print(f"[PROCESS] ✓ Analysis complete. Success: {report.get('success', False)}")

        # Clear progress
        progress_placeholder.empty()
        progress_bar.empty()

        if not report.get('success', False):
            error_msg = report.get('message', 'Analysis failed')
            print(f"[PROCESS] ✗ Analysis failed: {error_msg}")
            # Don't call st.error() here as it won't persist across rerun
            # Instead, return error info for caller to handle
            return {'error': error_msg, 'success': False}

        return report

    except ValueError as e:
        error_msg = str(e)
        print(f"[PROCESS] ✗ ValueError: {error_msg}")
        return {'error': error_msg, 'success': False}
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        print(f"[PROCESS] ✗ Exception: {error_msg}")
        import traceback
        print("[PROCESS] Full traceback:")
        traceback.print_exc()
        return {'error': error_msg, 'success': False}


# ── Landing Page ──────────────────────────────────────────────────────────────
def show_landing_page(lang):
    tx = T[lang]
    DIR = 'rtl' if lang == 'ar' else 'ltr'

    st.markdown(f"""
    <div class="hero-section">
        <div class="hero-glow"></div>
        <div class="hero-ring hero-ring-1"></div>
        <div class="hero-ring hero-hero-ring-2"></div>
        <div class="hero-ring hero-ring-3"></div>
        <div class="hero-content">
            <div class="hero-eyebrow">{tx['hero_eyebrow']}</div>
            <h1 class="hero-title">{tx['hero_title']}</h1>
            <p class="hero-subtitle">{tx['hero_subtitle']}</p>
            <div class="hero-badges">
                <span class="hero-badge">{tx['badge_speed']}</span>
                <span class="hero-badge">{tx['badge_accuracy']}</span>
                <span class="hero-badge">{tx['badge_security']}</span>
                <span class="hero-badge">{tx['badge_reports']}</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style="text-align:center;padding:2.5rem 0 1rem;direction:{DIR};">
        <div class="page-header-tag" style="color:{GOLD};">{tx['section_label']}</div>
        <h2 class="page-header-title">{tx['section_title']}</h2>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown(f"""
        <div class="use-case-card inquiries-card">
            <div style="font-size:2.2rem;margin-bottom:1rem;">📊</div>
            <h3 class="use-case-title">{tx['inq_card_title']}</h3>
            <p class="use-case-desc">{tx['inq_card_desc']}</p>
            <div class="use-case-tags">
                <span class="use-case-tag inquiries-tag">{tx['inq_tag1']}</span>
                <span class="use-case-tag inquiries-tag">{tx['inq_tag2']}</span>
                <span class="use-case-tag inquiries-tag">{tx['inq_tag3']}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        btn_inq = st.button(tx['btn_inq'], key='btn_inq_nav', use_container_width=True)
        if btn_inq:
            print(f"[Landing] Inquiries button clicked → navigating to inquiries page")
            st.session_state.page = 'inquiries'
            st.rerun()

    with col2:
        st.markdown(f"""
        <div class="use-case-card complaints-card">
            <div style="font-size:2.2rem;margin-bottom:1rem;">🗣️</div>
            <h3 class="use-case-title">{tx['cmp_card_title']}</h3>
            <p class="use-case-desc">{tx['cmp_card_desc']}</p>
            <div class="use-case-tags">
                <span class="use-case-tag complaints-tag">{tx['cmp_tag1']}</span>
                <span class="use-case-tag complaints-tag">{tx['cmp_tag2']}</span>
                <span class="use-case-tag complaints-tag">{tx['cmp_tag3']}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="blue-btn">', unsafe_allow_html=True)
        btn_cmp = st.button(tx['btn_cmp'], key='btn_cmp_nav', use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
        if btn_cmp:
            print(f"[Landing] Complaints button clicked → navigating to complaints page")
            st.session_state.page = 'complaints'
            st.rerun()

    st.markdown(f"""
    <div class="footer">
        <p class="footer-text" style="font-weight:600;">{tx['footer_copy']}</p>
        <div class="footer-divider"></div>
        <p class="footer-text">{tx['footer_sub']}</p>
    </div>
    """, unsafe_allow_html=True)


# ── Inquiries Page ────────────────────────────────────────────────────────────
def show_inquiries_page(lang):
    tx = T[lang]

    st.markdown(f"""
    <div class="page-header">
        <div class="page-header-tag">{tx['inq_header_tag']}</div>
        <h1 class="page-header-title">{tx['inq_header_title']}</h1>
        <p class="page-header-sub">{tx['inq_header_sub']}</p>
        <div class="page-header-bar"></div>
    </div>
    """, unsafe_allow_html=True)

    col_back = st.columns([1, 8, 1])
    with col_back[0]:
        if st.button(tx['nav_back'], key='back_inq'):
            st.session_state.page = 'landing'
            st.session_state.completed = False
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    if not st.session_state.completed:
        st.markdown(f"""
        <div class="panel">
            <h2 class="panel-title">{tx['inq_panel_title']}</h2>
            <p class="panel-subtitle">{tx['inq_panel_sub']}</p>
            <div class="panel-divider"></div>
        </div>
        """, unsafe_allow_html=True)

        uploaded_files = st.file_uploader(
            tx['uploader_label'],
            type=['xlsx', 'xls', 'pdf'],
            accept_multiple_files=False,
            key='inq_uploader'
        )

        if uploaded_files:
            st.session_state.uploaded_file = uploaded_files
            size_mb = uploaded_files.size / (1024 * 1024)
            size_str = f"{size_mb:.2f} {tx['size_mb']}" if size_mb >= 1 else f"{uploaded_files.size / 1024:.0f} {tx['size_kb']}"

            st.markdown(f"""
            <div class="file-meta">
                <div class="file-meta-row">
                    <span class="file-meta-key">{tx['file_key']}</span>
                    <span class="file-meta-val">{uploaded_files.name}</span>
                </div>
                <div class="file-meta-row">
                    <span class="file-meta-key">{tx['size_key']}</span>
                    <span class="file-meta-val">{size_str}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            if st.button(tx['btn_start_inq'], key='start_inq', use_container_width=True):
                st.session_state.processing = True
                st.rerun()

    if st.session_state.processing:
        st.markdown(f"""
        <div class="stage-panel">
            <span class="stage-badge">{tx['stage_badge_inq']}</span>
            <h2 class="stage-title">{tx['stage_title']}</h2>
            <p class="stage-desc">{tx['stage_desc_inq']}</p>
        </div>
        """, unsafe_allow_html=True)

        try:
            report = process_file([st.session_state.uploaded_file], flow_type='inquiries', lang=lang)

            if report and report.get('success', False):
                st.session_state.report_data = report
                st.session_state.processing = False
                st.session_state.completed = True
                st.session_state.analysis_error = None
                st.rerun()
            elif report and report.get('error'):
                # Error dict returned from process_file
                st.session_state.processing = False
                st.session_state.analysis_error = report.get('error', 'Unknown error')
                st.rerun()
            else:
                st.session_state.processing = False
                st.session_state.analysis_error = "Analysis failed: No response from analyzer"
                st.rerun()
        except Exception as e:
            print(f"[UI] Error during inquiries processing: {str(e)}")
            import traceback
            traceback.print_exc()
            st.session_state.processing = False
            st.session_state.analysis_error = f"Error: {str(e)}"
            st.rerun()

    if st.session_state.get('analysis_error'):
        st.error(f"❌ {tx['success_title_inq']}: {st.session_state.analysis_error}")
        if st.button(tx['btn_reset'], key='reset_inq_error', use_container_width=True):
            st.session_state.uploaded_file = None
            st.session_state.processing = False
            st.session_state.completed = False
            st.session_state.report_data = None
            st.session_state.analysis_error = None
            st.rerun()
        return

    if st.session_state.completed and st.session_state.get('report_data'):
        st.markdown(f"""
        <div class="success-panel">
            <h2 class="success-title">✅ {tx['success_title_inq']}</h2>
            <p class="success-sub">{tx['success_sub_inq']}</p>
        </div>
        """, unsafe_allow_html=True)

        display_report_tabs(lang, flow_type='inquiries')

        if st.session_state.report_data.get('word_path'):
            with open(st.session_state.report_data['word_path'], 'rb') as f:
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


# ── Complaints Page ───────────────────────────────────────────────────────────
def show_complaints_page(lang):
    tx = T[lang]

    st.markdown(f"""
    <div class="page-header-complaints">
        <div class="page-header-tag">{tx['cmp_header_tag']}</div>
        <h1 class="page-header-title">{tx['cmp_header_title']}</h1>
        <p class="page-header-sub">{tx['cmp_header_sub']}</p>
        <div class="page-header-bar"></div>
    </div>
    """, unsafe_allow_html=True)

    col_back = st.columns([1, 8, 1])
    with col_back[0]:
        if st.button(tx['nav_back'], key='back_cmp'):
            st.session_state.page = 'landing'
            st.session_state.completed = False
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    if not st.session_state.completed:
        st.markdown(f"""
        <div class="panel-blue">
            <h2 class="panel-title">{tx['cmp_panel_title']}</h2>
            <p class="panel-subtitle">{tx['cmp_panel_sub']}</p>
            <div class="panel-divider"></div>
        </div>
        """, unsafe_allow_html=True)

        uploaded_files = st.file_uploader(
            tx['uploader_label'],
            type=['xlsx', 'xls', 'pdf'],
            accept_multiple_files=False,
            key='cmp_uploader'
        )

        if uploaded_files:
            st.session_state.uploaded_file = uploaded_files
            size_mb = uploaded_files.size / (1024 * 1024)
            size_str = f"{size_mb:.2f} {tx['size_mb']}" if size_mb >= 1 else f"{uploaded_files.size / 1024:.0f} {tx['size_kb']}"

            st.markdown(f"""
            <div class="file-meta-blue">
                <div class="file-meta-row">
                    <span class="file-meta-key-blue">{tx['file_key']}</span>
                    <span class="file-meta-val">{uploaded_files.name}</span>
                </div>
                <div class="file-meta-row">
                    <span class="file-meta-key-blue">{tx['size_key']}</span>
                    <span class="file-meta-val">{size_str}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            if st.button(tx['btn_start_cmp'], key='start_cmp', use_container_width=True):
                st.session_state.processing = True
                st.rerun()

    if st.session_state.processing:
        st.markdown(f"""
        <div class="stage-panel-blue">
            <span class="stage-badge-blue">{tx['stage_badge_cmp']}</span>
            <h2 class="stage-title">{tx['stage_title']}</h2>
            <p class="stage-desc">{tx['stage_desc_cmp']}</p>
        </div>
        """, unsafe_allow_html=True)

        try:
            report = process_file([st.session_state.uploaded_file], flow_type='complaints', lang=lang)

            if report and report.get('success', False):
                st.session_state.report_data = report
                st.session_state.processing = False
                st.session_state.completed = True
                st.session_state.analysis_error = None
                st.rerun()
            elif report and report.get('error'):
                # Error dict returned from process_file
                st.session_state.processing = False
                st.session_state.analysis_error = report.get('error', 'Unknown error')
                st.rerun()
            else:
                st.session_state.processing = False
                st.session_state.analysis_error = "Analysis failed: No response from analyzer"
                st.rerun()
        except Exception as e:
            print(f"[UI] Error during complaints processing: {str(e)}")
            import traceback
            traceback.print_exc()
            st.session_state.processing = False
            st.session_state.analysis_error = f"Error: {str(e)}"
            st.rerun()

    if st.session_state.get('analysis_error'):
        st.error(f"❌ {tx['success_title_cmp']}: {st.session_state.analysis_error}")
        if st.button(tx['btn_reset'], key='reset_cmp_error', use_container_width=True):
            st.session_state.uploaded_file = None
            st.session_state.processing = False
            st.session_state.completed = False
            st.session_state.report_data = None
            st.session_state.analysis_error = None
            st.rerun()
        return

    if st.session_state.completed and st.session_state.get('report_data'):
        st.markdown(f"""
        <div class="success-panel">
            <h2 class="success-title">✅ {tx['success_title_cmp']}</h2>
            <p class="success-sub">{tx['success_sub_cmp']}</p>
        </div>
        """, unsafe_allow_html=True)

        display_report_tabs(lang, flow_type='complaints')

        if st.session_state.report_data.get('word_path'):
            with open(st.session_state.report_data['word_path'], 'rb') as f:
                st.download_button(
                    label=tx['btn_download_cmp'],
                    data=f,
                    file_name='complaints_report.docx',
                    mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    use_container_width=True
                )

        if st.button(tx['btn_reset'], key='reset_cmp', use_container_width=True):
            st.session_state.uploaded_file = None
            st.session_state.processing = False
            st.session_state.completed = False
            st.session_state.report_data = None
            st.rerun()


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    init_session_state()
    lang = st.session_state.language
    load_css(lang)

    # Language toggle
    col_left, col_right = st.columns([11, 1])
    with col_right:
        new_lang = 'ar' if lang == 'en' else 'en'
        button_text = 'العربية' if lang == 'en' else 'EN'
        if st.button(button_text, key='lang_toggle', use_container_width=True):
            st.session_state.language = new_lang
            st.rerun()

    # Page routing
    print(f"[Main] Current page: {st.session_state.page}")
    if st.session_state.page == 'landing':
        print(f"[Main] → Rendering landing page")
        show_landing_page(lang)
    elif st.session_state.page == 'inquiries':
        print(f"[Main] → Rendering inquiries page")
        show_inquiries_page(lang)
    elif st.session_state.page == 'complaints':
        print(f"[Main] → Rendering complaints page")
        show_complaints_page(lang)
    else:
        print(f"[Main] ✗ Unknown page: {st.session_state.page}")
        st.error(f"Unknown page: {st.session_state.page}")


if __name__ == "__main__":
    main()
