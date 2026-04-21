import streamlit as st
import time
import os
import json
import random
import threading
from pathlib import Path
from analysis import RealAnalyzer, DynamicReportDisplay
from dotenv import load_dotenv
import zipfile
import io

# Load environment variables
load_dotenv()
APP_MODE = os.getenv('APP_MODE', 'real').lower()

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
        'hero_subtitle':     'An AI platform for analyzing citizen inquiries and complaints to improve government service quality',
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
    /* Style the toggle switch to match the gold theme */
    .stCheckbox {{
        direction: ltr !important;
        text-align: center !important;
    }}
    
    /* Style the toggle label */
    .stCheckbox label {{
        color: {TEXT} !important;
        font-size: 0.85rem !important;
        font-weight: 500 !important;
        direction: ltr !important;
        justify-content: center !important;
    }}
    
    /* Style the toggle switch itself */
    .stCheckbox input[type="checkbox"] {{
        accent-color: {GOLD} !important;
    }}
    
    /* Override default checkbox styling for toggle */
    [data-testid="stCheckbox"] > label {{
        display: flex !important;
        flex-direction: row !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 0.5rem !important;
        direction: ltr !important;
    }}
    
    /* Ensure toggle switch stays LTR even in RTL mode */
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

    /* ── CARD GRIDS ── */
    .cards-grid-3 {{
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 1.5rem;
        margin-bottom: 1rem;
    }}
    .cards-grid-4 {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 1.2rem;
        margin-bottom: 1rem;
    }}

    /* ── SECTION HEADER ── */
    .section-header {{
        text-align: center !important;
        direction: {DIR} !important;
        padding: 4rem 0 2.5rem;
    }}
    .section-label {{
        display: inline-block;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 3px;
        color: {GOLD};
        text-transform: uppercase;
        margin-bottom: 0.8rem;
    }}
    .section-title {{
        font-size: 2.6rem;
        font-weight: 700;
        color: {TEXT};
        margin: 0 0 1rem;
        direction: {DIR} !important;
        text-align: center !important;
    }}
    .section-ornament {{
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 1rem;
        margin-top: 1.2rem;
    }}
    .ornament-line {{
        height: 1px;
        width: 80px;
        background: linear-gradient(90deg, transparent, {GOLD});
    }}
    .ornament-line.right {{
        background: linear-gradient(90deg, {GOLD}, transparent);
    }}
    .ornament-diamond {{
        color: {GOLD};
        font-size: 0.6rem;
    }}

    /* ── FEATURE CARDS ── */
    .feature-card {{
        background: {BG_CARD};
        border: 1px solid {BORDER_G};
        border-radius: 20px;
        padding: 2.5rem 2rem;
        position: relative;
        overflow: hidden;
        transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
        direction: {DIR} !important;
        display: flex;
        flex-direction: column;
    }}
    .feature-card::before {{
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 2px;
        background: linear-gradient(90deg, transparent, {GOLD}, transparent);
        opacity: 0.6;
    }}
    .feature-card:hover {{
        border-color: {BORDER_G2};
        box-shadow: 0 24px 64px rgba(201,150,60,0.09), 0 0 0 1px {BORDER_G};
        transform: translateY(-4px);
    }}
    .feature-icon-wrap {{
        width: 58px; height: 58px;
        background: linear-gradient(135deg, rgba(201,150,60,0.15), rgba(201,150,60,0.04));
        border: 1px solid {BORDER_G2};
        border-radius: 14px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.7rem;
        margin-bottom: 1.4rem;
    }}
    .feature-title {{
        color: {GOLD_LIGHT};
        font-size: 1.25rem;
        font-weight: 700;
        margin: 0 0 0.7rem;
        direction: {DIR} !important;
    }}
    .feature-desc {{
        color: {TEXT_MUTED};
        font-size: 1rem;
        line-height: 1.8;
        margin: 0;
        direction: {DIR} !important;
        flex: 1;
    }}

    /* ── STEPS ── */
    .step-card {{
        background: {BG_CARD};
        border: 1px solid {BORDER_G};
        border-radius: 16px;
        padding: 2rem 1.5rem;
        text-align: center !important;
        direction: {DIR} !important;
        position: relative;
        transition: all 0.3s ease;
        display: flex;
        flex-direction: column;
    }}
    .step-card:hover {{
        border-color: {BORDER_G2};
        box-shadow: 0 12px 40px rgba(201,150,60,0.07);
    }}
    .step-number {{
        font-size: 2.6rem;
        font-weight: 900;
        background: linear-gradient(135deg, {BORDER_G2}, rgba(201,150,60,0.1));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        line-height: 1;
        margin-bottom: 0.6rem;
        text-align: center !important;
    }}
    .step-icon {{
        font-size: 2rem;
        margin-bottom: 0.8rem;
        text-align: center !important;
    }}
    .step-title {{
        color: {TEXT};
        font-size: 1.05rem;
        font-weight: 600;
        margin: 0 0 0.5rem;
        text-align: center !important;
        direction: {DIR} !important;
    }}
    .step-desc {{
        color: {TEXT_MUTED};
        font-size: 0.9rem;
        line-height: 1.7;
        margin: 0;
        text-align: center !important;
        direction: {DIR} !important;
        flex: 1;
    }}

    /* ── BUTTON KEYFRAMES ── */
    @keyframes gradientFlow {{
        0%   {{ background-position: 0% 50%; }}
        50%  {{ background-position: 100% 50%; }}
        100% {{ background-position: 0% 50%; }}
    }}
    @keyframes shimmerSweep {{
        0%   {{ transform: translateX(-160%) skewX(-14deg); opacity: 0; }}
        15%  {{ opacity: 1; }}
        85%  {{ opacity: 1; }}
        100% {{ transform: translateX(260%) skewX(-14deg); opacity: 0; }}
    }}
    @keyframes borderPulse {{
        0%, 100% {{ box-shadow: 0 0 0 0 rgba(201,150,60,0.08),
                                0 4px 18px rgba(201,150,60,0.15); }}
        50%       {{ box-shadow: 0 0 0 5px rgba(201,150,60,0.10),
                                0 4px 26px rgba(201,150,60,0.28); }}
    }}
    @keyframes borderPulseBlue {{
        0%, 100% {{ box-shadow: 0 0 0 0 rgba(46,134,171,0.08),
                                0 4px 18px rgba(46,134,171,0.15); }}
        50%       {{ box-shadow: 0 0 0 5px rgba(46,134,171,0.10),
                                0 4px 26px rgba(46,134,171,0.28); }}
    }}

    /* ── GOLD BUTTONS (default) ── */
    .stButton > button {{
        background: linear-gradient(
            110deg,
            {GOLD_DARK} 0%,
            {GOLD}      28%,
            {GOLD_LIGHT} 52%,
            {GOLD_PALE}  66%,
            {GOLD_LIGHT} 80%,
            {GOLD}      100%
        );
        background-size: 260% 260%;
        animation: gradientFlow 5s ease infinite;
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
        transition: transform 0.25s cubic-bezier(0.4,0,0.2,1),
                    box-shadow 0.25s ease;
        box-shadow: 0 4px 20px rgba(201,150,60,0.28);
        direction: {DIR} !important;
        letter-spacing: 0.3px;
    }}
    .stButton > button::before {{
        content: '';
        position: absolute;
        top: 0; left: 0; bottom: 0;
        width: 42%;
        background: linear-gradient(
            90deg,
            transparent,
            rgba(255,255,255,0.24),
            transparent
        );
        transform: translateX(-160%) skewX(-14deg);
        animation: shimmerSweep 4.5s ease infinite 2s;
        pointer-events: none;
    }}
    .stButton > button:hover {{
        transform: translateY(-3px);
        box-shadow: 0 10px 38px rgba(201,150,60,0.52);
        animation: gradientFlow 2.2s ease infinite;
        color: {BG_DEEP} !important;
    }}
    .stButton > button:hover::before {{
        animation: shimmerSweep 0.85s ease forwards;
    }}
    .stButton > button:active {{
        transform: translateY(0);
        box-shadow: 0 3px 14px rgba(201,150,60,0.35);
    }}

    /* ── BLUE BUTTON (complaints) ── */
    .blue-btn .stButton > button {{
        background: linear-gradient(
            110deg,
            {BLUE_DARK} 0%,
            {BLUE}      30%,
            {BLUE_LIGHT} 55%,
            {BLUE_PALE}  70%,
            {BLUE_LIGHT} 82%,
            {BLUE}      100%
        ) !important;
        background-size: 260% 260% !important;
        box-shadow: 0 4px 20px rgba(46,134,171,0.28) !important;
    }}
    .blue-btn .stButton > button:hover {{
        box-shadow: 0 10px 38px rgba(46,134,171,0.52) !important;
    }}

    /* Download button — outlined with pulse, fills on hover */
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
        transition: transform 0.25s ease, color 0.25s ease,
                    border-color 0.25s ease;
        animation: borderPulse 3s ease infinite;
        direction: {DIR} !important;
    }}
    .stDownloadButton > button::before {{
        content: '';
        position: absolute;
        inset: 0;
        background: linear-gradient(
            110deg,
            {GOLD_DARK} 0%,
            {GOLD}      28%,
            {GOLD_LIGHT} 52%,
            {GOLD_PALE}  66%,
            {GOLD_LIGHT} 80%,
            {GOLD}      100%
        );
        background-size: 260% 260%;
        opacity: 0;
        transition: opacity 0.28s ease;
        animation: gradientFlow 4s ease infinite;
        pointer-events: none;
    }}
    .stDownloadButton > button:hover {{
        color: {BG_DEEP} !important;
        border-color: transparent !important;
        box-shadow: 0 10px 36px rgba(201,150,60,0.48) !important;
        transform: translateY(-3px);
        animation: none;
    }}
    .stDownloadButton > button:hover::before {{
        opacity: 1;
        animation: gradientFlow 2.5s ease infinite;
    }}
    .stDownloadButton > button:active {{
        transform: translateY(0);
    }}

    /* Blue download button variant */
    .blue-download .stDownloadButton > button {{
        border-color: {BLUE} !important;
        color: {BLUE_LIGHT} !important;
        animation: borderPulseBlue 3s ease infinite;
    }}
    .blue-download .stDownloadButton > button::before {{
        background: linear-gradient(
            110deg,
            {BLUE_DARK} 0%,
            {BLUE}      30%,
            {BLUE_LIGHT} 55%,
            {BLUE_PALE}  70%,
            {BLUE_LIGHT} 82%,
            {BLUE}      100%
        ) !important;
    }}
    .blue-download .stDownloadButton > button:hover {{
        box-shadow: 0 10px 36px rgba(46,134,171,0.48) !important;
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

    /* ── PROGRESS ── */
    .progress-container {{
        direction: {DIR} !important;
        width: 100%;
        margin: 1.5rem 0;
    }}
    .stProgress {{
        direction: {DIR} !important;
    }}
    .stProgress > div > div > div > div {{
        background: linear-gradient(90deg, {GOLD_DARK}, {GOLD}, {GOLD_LIGHT});
        border-radius: 10px;
        transition: width 0.4s ease;
    }}
    .stProgress > div > div > div {{
        background: rgba(255,255,255,0.05);
        border-radius: 10px;
    }}
    .stProgress > div > div {{
        border-radius: 10px;
    }}
    /* Blue progress bar */
    .blue-progress .stProgress > div > div > div > div {{
        background: linear-gradient(90deg, {BLUE_DARK}, {BLUE}, {BLUE_LIGHT}) !important;
    }}

    /* ── STAGE INDICATOR ── */
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
    .pct-display {{
        font-size: 2rem;
        font-weight: 900;
        background: linear-gradient(135deg, {GOLD_LIGHT}, {GOLD});
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        text-align: {ALIGN} !important;
        direction: {DIR} !important;
        margin: 1rem 0 0;
        letter-spacing: -1px;
    }}
    .pct-display-blue {{
        font-size: 2rem;
        font-weight: 900;
        background: linear-gradient(135deg, {BLUE_LIGHT}, {BLUE});
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        text-align: {ALIGN} !important;
        direction: {DIR} !important;
        margin: 1rem 0 0;
        letter-spacing: -1px;
    }}

    /* ── SUCCESS / ERROR ── */
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
    .error-panel {{
        background: rgba(239,68,68,0.06);
        border: 1px solid rgba(239,68,68,0.2);
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        color: #FC8181;
        font-weight: 500;
        font-size: 0.95rem;
        direction: {DIR} !important;
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

    /* ── EQUAL-HEIGHT CARD ROWS ── */
    [data-testid="stHorizontalBlock"] {{
        align-items: stretch !important;
    }}
    [data-testid="stHorizontalBlock"] > [data-testid="column"] {{
        display: flex !important;
        flex-direction: column !important;
    }}
    [data-testid="stHorizontalBlock"] > [data-testid="column"] > div {{
        flex: 1 !important;
        display: flex !important;
        flex-direction: column !important;
        min-height: 0;
    }}
    [data-testid="stHorizontalBlock"] > [data-testid="column"]
        [data-testid="stVerticalBlock"] {{
        flex: 1 !important;
        display: flex !important;
        flex-direction: column !important;
        min-height: 0;
    }}
    [data-testid="stHorizontalBlock"] > [data-testid="column"]
        .element-container {{
        flex: 1 !important;
        display: flex !important;
        flex-direction: column !important;
        min-height: 0;
    }}
    [data-testid="stHorizontalBlock"] > [data-testid="column"]
        [data-testid="stMarkdownContainer"] {{
        flex: 1 !important;
        display: flex !important;
        flex-direction: column !important;
        min-height: 0;
    }}
    [data-testid="stHorizontalBlock"] > [data-testid="column"]
        [data-testid="stMarkdownContainer"] > div {{
        flex: 1 !important;
        display: flex !important;
        flex-direction: column !important;
        min-height: 0;
    }}
    .feature-card, .step-card {{
        height: 100% !important;
        display: flex !important;
        flex-direction: column !important;
        box-sizing: border-box !important;
    }}
    .feature-desc, .step-desc {{
        flex: 1 !important;
    }}

    /* ── ANIMATIONS ── */
    @keyframes fadeUp {{
        from {{ opacity: 0; transform: translateY(24px); }}
        to   {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes goldPulse {{
        0%, 100% {{ box-shadow: 0 0 0 0 rgba(201,150,60,0); }}
        50%       {{ box-shadow: 0 0 0 8px rgba(201,150,60,0.06); }}
    }}
    .hero-title    {{ animation: fadeUp 0.8s ease both; }}
    .hero-subtitle {{ animation: fadeUp 0.8s 0.15s ease both; }}
    .hero-badges   {{ animation: fadeUp 0.8s 0.25s ease both; }}
    .panel         {{ animation: fadeUp 0.5s ease both; }}

    /* ── MISC DIRECTION FIXES ── */
    h1, h2, h3, h4, h5, h6, p, span, div, label {{
        direction: {DIR} !important;
    }}
    .center-text {{
        text-align: center !important;
        direction: {DIR} !important;
    }}
    [data-testid="column"] img {{
        max-width: 100%;
        height: auto;
    }}

    /* ── LOGIN MODAL ── */
    .login-overlay {{
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(8,8,15,0.85);
        backdrop-filter: blur(8px);
        -webkit-backdrop-filter: blur(8px);
        z-index: 9999;
        display: flex;
        align-items: center;
        justify-content: center;
        animation: fadeIn 0.3s ease;
    }}
    @keyframes fadeIn {{
        from {{ opacity: 0; }}
        to {{ opacity: 1; }}
    }}
    .login-modal {{
        background: {BG_CARD};
        border: 1px solid {BORDER_G2};
        border-radius: 24px;
        padding: 3rem 2.5rem;
        max-width: 420px;
        width: 90%;
        box-shadow: 0 24px 80px rgba(201,150,60,0.15);
        animation: slideUp 0.4s ease;
        direction: {DIR} !important;
    }}
    @keyframes slideUp {{
        from {{ opacity: 0; transform: translateY(30px); }}
        to {{ opacity: 1; transform: translateY(0); }}
    }}
    .login-header {{
        text-align: center !important;
        margin-bottom: 1rem;
        direction: {DIR} !important;
    }}
    .login-icon {{
        font-size: 3rem;
        margin-bottom: 1rem;
    }}
    .login-title {{
        font-size: 1.8rem;
        font-weight: 700;
        color: {GOLD_LIGHT};
        margin: 0 0 0.5rem;
        text-align: center !important;
        direction: inherit !important;
    }}
    .login-subtitle {{
        font-size: 0.95rem;
        color: {TEXT_MUTED};
        margin: 0;
        text-align: center !important;
        direction: inherit !important;
    }}
    .login-form {{
        margin-top: 2.5rem;
        margin-bottom: 1.5rem;
        direction: {DIR} !important;
    }}
    .login-form label {{
        color: {TEXT} !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        margin-bottom: 0.5rem !important;
        display: block !important;
        direction: {DIR} !important;
        text-align: {ALIGN} !important;
    }}
    .login-form input {{
        width: 100% !important;
        padding: 0.75rem 1rem !important;
        background: rgba(201,150,60,0.04) !important;
        border: 1px solid {BORDER_G} !important;
        border-radius: 10px !important;
        color: {TEXT} !important;
        font-family: {FONT} !important;
        font-size: 0.95rem !important;
        transition: all 0.2s ease !important;
        direction: {DIR} !important;
        text-align: {ALIGN} !important;
    }}
    .login-form input:focus {{
        outline: none !important;
        border-color: {GOLD} !important;
        background: rgba(201,150,60,0.08) !important;
        box-shadow: 0 0 0 3px rgba(201,150,60,0.1) !important;
    }}
    .login-buttons {{
        display: flex;
        gap: 1rem;
        margin-top: 2rem;
        direction: {DIR} !important;
    }}
    .login-error {{
        background: rgba(239,68,68,0.08);
        border: 1px solid rgba(239,68,68,0.3);
        border-radius: 10px;
        padding: 0.75rem 1rem;
        color: #FC8181;
        font-size: 0.9rem;
        margin-bottom: 1rem;
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
        'authenticated': False,
        'show_login': False,
        'pending_page': None,
        'current_user_center': None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── Authentication ────────────────────────────────────────────────────────────
def load_credentials():
    # Try to load from Streamlit secrets first (for deployment)
    try:
        if hasattr(st, 'secrets') and 'users' in st.secrets:
            users = []
            # Load admin user
            if 'admin_username' in st.secrets.users:
                users.append({
                    "username": st.secrets.users.admin_username,
                    "password": st.secrets.users.admin_password,
                    "center": st.secrets.users.get('admin_center', 'مركز الإدارة المركزية')
                })
            # Load demo user
            if 'demo_username' in st.secrets.users:
                users.append({
                    "username": st.secrets.users.demo_username,
                    "password": st.secrets.users.demo_password,
                    "center": st.secrets.users.get('demo_center', 'مركز التجريب والعروض التوضيحية')
                })
            # Load fujairah-user
            if 'fujairah_username' in st.secrets.users:
                users.append({
                    "username": st.secrets.users.fujairah_username,
                    "password": st.secrets.users.fujairah_password,
                    "center": st.secrets.users.get('fujairah_center', 'مركز الفجيرة الرئيسي')
                })
            # Load Fujairah Police Center users (20 total: 10 existing + 10 new)
            user_configs = [
                # Existing users
                ('myaalali_email', 'myaalali_password', 'myaalali_center'),
                ('umahmed_email', 'umahmed_password', 'umahmed_center'),
                ('kh17878_email', 'kh17878_password', 'kh17878_center'),
                ('meznar_email', 'meznar_password', 'meznar_center'),
                ('alkendi_email', 'alkendi_password', 'alkendi_center'),
                ('alhyah_email', 'alhyah_password', 'alhyah_center'),
                ('shaheen_email', 'shaheen_password', 'shaheen_center'),
                ('fatima_email', 'fatima_password', 'fatima_center'),
                ('saeed_al_soghairi_email', 'saeed_al_soghairi_password', 'saeed_al_soghairi_center'),
                ('ahmed_al_hammadi_email', 'ahmed_al_hammadi_password', 'ahmed_al_hammadi_center'),
                # New users
                ('abdul_sief_albadi_email', 'abdul_sief_albadi_password', 'abdul_sief_albadi_center'),
                ('sulaiman_saeed_email', 'sulaiman_saeed_password', 'sulaiman_saeed_center'),
                ('fahd_suwaidi_email', 'fahd_suwaidi_password', 'fahd_suwaidi_center'),
                ('abdullah_sulaiman_email', 'abdullah_sulaiman_password', 'abdullah_sulaiman_center'),
                ('ali_sultan_email', 'ali_sultan_password', 'ali_sultan_center'),
                ('ali_hassan_email', 'ali_hassan_password', 'ali_hassan_center'),
                ('nayif_taniji_email', 'nayif_taniji_password', 'nayif_taniji_center'),
                ('aisha_safsouf_email', 'aisha_safsouf_password', 'aisha_safsouf_center'),
                ('ibrahim_taniji_email', 'ibrahim_taniji_password', 'ibrahim_taniji_center'),
                ('khams_alhamar_email', 'khams_alhamar_password', 'khams_alhamar_center'),
            ]
            for email_key, password_key, center_key in user_configs:
                if email_key in st.secrets.users and password_key in st.secrets.users:
                    users.append({
                        "username": st.secrets.users[email_key],
                        "password": st.secrets.users[password_key],
                        "center": st.secrets.users.get(center_key, "Unknown Center")
                    })
            return {"users": users}
    except Exception:
        pass

    # No local fallback - credentials must be in Streamlit secrets
    return {"users": []}

def verify_credentials(username, password):
    creds = load_credentials()
    for user in creds.get("users", []):
        if user["username"] == username and user["password"] == password:
            return user  # Return the full user object with center name
    return None

# ── Analyzer Setup ────────────────────────────────────────────────────────────
def get_analyzer():
    """Get the real analyzer."""
    return RealAnalyzer()

ANALYZER = get_analyzer()

# ── Validation ────────────────────────────────────────────────────────────────
def validate_file(uploaded_file, lang='ar'):
    tx = T[lang]
    is_valid, error_msg = ANALYZER.validate_file(uploaded_file)
    if not is_valid:
        return False, error_msg or tx['err_bad_type']
    return True, ""


# ── Display Report ─────────────────────────────────────────────────────────────
def display_report_tabs(lang: str = 'ar', flow_type: str = 'inquiries'):
    """Display report from analyzer output.

    Displays the report generated by the RealAnalyzer in the real flow.
    Args:
        lang: Language preference ('ar' or 'en')
        flow_type: 'inquiries' or 'complaints'
    """
    try:
        # Use report data from session state (generated by analyzer)
        if 'report_data' in st.session_state and st.session_state.report_data:
            report = st.session_state.report_data
            display = DynamicReportDisplay(lang=lang)
            display.display_report_from_dict(report)
        else:
            st.info("ℹ️ No report data available. Please process a file first.")
    except Exception as e:
        st.error(f"❌ Error displaying report: {str(e)}")
        import traceback
        st.code(traceback.format_exc())


# ── Create ZIP with multiple files ────────────────────────────────────────────
def create_download_zip(flow_type: str = 'inquiries'):
    """Create a ZIP file containing analysis outputs.

    For real flow: Uses dynamically generated files from analyzer.
    For demo flow: Uses pre-existing report files.

    Args:
        flow_type: 'inquiries' or 'complaints'
    """
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Try to get output paths from session state (real flow)
        output_files = st.session_state.get('output_files', {})

        if flow_type == 'complaints':
            # Real flow: generated files from analyzer
            if 'word_path' in output_files:
                word_path = Path(output_files['word_path'])
                if word_path.exists():
                    zip_file.write(str(word_path), "تقرير_تحليل_شكاوى_المتعاملين.docx")

            if 'excel_path' in output_files:
                excel_path = Path(output_files['excel_path'])
                if excel_path.exists():
                    zip_file.write(str(excel_path), "تصنيف_شكاوى_المتعاملين.xlsx")

            # Fallback: Demo flow - look for static files
            demo_report = Path("complaints-output/تقرير تحليل شكاوى المتعاملين.docx")
            if demo_report.exists() and 'word_path' not in output_files:
                zip_file.write(str(demo_report), "تقرير تحليل شكاوى المتعاملين.docx")

            demo_excel = Path("complaints-output/تصنيف شكاوى المتعاملين — حسب النوع 2025.xlsx")
            if demo_excel.exists() and 'excel_path' not in output_files:
                zip_file.write(str(demo_excel), "تصنيف شكاوى المتعاملين — حسب النوع 2025.xlsx")
        else:
            # Real flow: generated files from analyzer
            if 'word_path' in output_files:
                word_path = Path(output_files['word_path'])
                if word_path.exists():
                    zip_file.write(str(word_path), "تقرير_تحليل_استفسارات_المتعاملين.docx")

            if 'excel_path' in output_files:
                excel_path = Path(output_files['excel_path'])
                if excel_path.exists():
                    zip_file.write(str(excel_path), "تحليل_استفسارات_المتعاملين.xlsx")

            # Fallback: Demo flow - look for static files
            demo_report = Path("inquiries-output/تقرير تحليل استفسارات المتعاملين .docx")
            if demo_report.exists() and 'word_path' not in output_files:
                zip_file.write(str(demo_report), "تقرير تحليل استفسارات المتعاملين .docx")

            demo_excel = Path("inquiries-output/Fujairah_Police_Inquiry_Triage_Detail.xlsx")
            if demo_excel.exists() and 'excel_path' not in output_files:
                zip_file.write(str(demo_excel), "Fujairah_Police_Inquiry_Triage_Detail.xlsx")

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


# ── Processing Stages ─────────────────────────────────────────────────────────
INQUIRIES_STAGES = [
    {"start": 0,    "end": 7.5,  "progress_start": 0,  "progress_end": 25},
    {"start": 7.5,  "end": 15,   "progress_start": 25, "progress_end": 50},
    {"start": 15,   "end": 22.5, "progress_start": 50, "progress_end": 75},
    {"start": 22.5, "end": 30,   "progress_start": 75, "progress_end": 100},
]

# ── Custom Progress Bar for RTL/LTR Support ──────────────────────────────────
def create_custom_progress_bar(current_pct=0, lang='ar'):
    """Create a custom HTML progress bar that supports RTL/LTR."""
    DIR = 'rtl' if lang == 'ar' else 'ltr'
    percentage = current_pct * 100

    progress_html = f"""
    <div style="direction: {DIR}; width: 100%; margin: 0;">
        <div style="
            width: 100%;
            height: 10px;
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
            overflow: hidden;
        ">
            <div style="
                height: 100%;
                background: linear-gradient(90deg, #B68A35, #E2B95A, #F0D080);
                width: {percentage}%;
                border-radius: 10px;
                transition: width 0.4s ease;
            "></div>
        </div>
    </div>
    """
    return progress_html

# ── Processing ───────────────────────────────────────────────────────────────
def _monitor_pipeline_progress(progress_container, pct_container, analyzer_stages, lang):
    """Monitor pipeline progress and update UI in real-time."""
    stage_sequence = [
        'stage1_validation',
        'stage2_classification',
        'stage3_llm',
        'stage4_patterns',
        'stage4_faqs',
        'stage5_gaps',
        'stage5_validated_faqs',
        'stage6_artifacts',
    ]

    last_section_count = 0
    check_interval = 0.2  # Check progress every 200ms

    while True:
        try:
            # Check if analyzer is still running by looking at session state
            if 'report_data' in st.session_state and st.session_state.report_data:
                report = st.session_state.report_data
                completed_sections = list(report.get('sections', {}).keys())
                num_completed = len([s for s in stage_sequence if s in completed_sections])

                # Only update if progress changed
                if num_completed != last_section_count:
                    last_section_count = num_completed
                    current_pct = min(1.0, num_completed / len(stage_sequence))

                    # Update progress bar
                    progress_container.markdown(
                        create_custom_progress_bar(current_pct, lang),
                        unsafe_allow_html=True,
                    )

                    # Update stage label
                    current_stage_idx = min(int(current_pct * len(analyzer_stages)), len(analyzer_stages) - 1)
                    if current_stage_idx >= 0 and current_stage_idx < len(analyzer_stages):
                        current_stage = analyzer_stages[current_stage_idx]
                        stage_label = current_stage.get('label_en', current_stage.get('label', 'Processing...')) if lang == 'en' else current_stage.get('label', 'Processing...')
                        pct_container.markdown(
                            f"<div class='pct-display'>{int(current_pct * 100)}% — {stage_label}</div>",
                            unsafe_allow_html=True,
                        )

            time.sleep(check_interval)
        except Exception:
            time.sleep(check_interval)


def process_with_analyzer(uploaded_files, lang='ar'):
    """Process files using analyzer with real-time progress tracking."""
    tx = T[lang]

    # Display custom progress bar and stage display
    progress_container = st.empty()
    pct_container = st.empty()

    try:
        # Process first file
        uploaded_file = uploaded_files[0] if uploaded_files else None
        if not uploaded_file:
            st.error(tx['err_no_file'])
            return None

        # Get analyzer's processing stages
        analyzer_stages = ANALYZER.get_processing_stages()

        # Start progress monitor thread
        monitor_thread = threading.Thread(
            target=_monitor_pipeline_progress,
            args=(progress_container, pct_container, analyzer_stages, lang),
            daemon=True
        )
        monitor_thread.start()

        # Run the analyzer in main thread - this updates session state as stages complete
        report = ANALYZER.analyze(uploaded_file)

        # Final progress update to 100%
        progress_container.markdown(
            create_custom_progress_bar(1.0, lang),
            unsafe_allow_html=True,
        )

        if analyzer_stages:
            final_stage = analyzer_stages[-1]
            stage_label = final_stage.get('label_en', final_stage.get('label', 'Complete')) if lang == 'en' else final_stage.get('label', 'Complete')
            pct_container.markdown(
                f"<div class='pct-display'>100% — {stage_label}</div>",
                unsafe_allow_html=True,
            )

        # Brief pause before clearing
        time.sleep(0.3)
        pct_container.empty()

        return report

    except Exception as e:
        st.error(f"Error during processing: {str(e)}")
        progress_container.empty()
        pct_container.empty()
        import traceback
        st.code(traceback.format_exc())
        return None


def simulate_processing_legacy(stages, pct_class="pct-display"):
    """Legacy function for backwards compatibility - delegates to analyzer."""
    progress_bar  = st.progress(0)
    pct_container = st.empty()

    total_duration   = 5
    update_interval  = 0.5
    total_steps      = int(total_duration / update_interval)

    for step in range(total_steps + 1):
        elapsed = step * update_interval
        current = next((s for s in stages if s["start"] <= elapsed < s["end"]), None)
        if current is None and elapsed >= total_duration:
            current = stages[-1]

        if current:
            stage_pct = (elapsed - current["start"]) / (current["end"] - current["start"])
            overall   = current["progress_start"] + stage_pct * (current["progress_end"] - current["progress_start"])
            overall   = min(100, max(0, overall))
            progress_bar.progress(int(overall) / 100)

            pct_container.markdown(
                f'<div class="{pct_class}">{int(overall)}%</div>',
                unsafe_allow_html=True,
            )

        time.sleep(update_interval)

    progress_bar.progress(1.0)
    pct_container.empty()


# ── Login Modal ───────────────────────────────────────────────────────────────
def show_login_modal(lang):
    tx = T[lang]
    DIR = 'rtl' if lang == 'ar' else 'ltr'
    
    # Add modal styling
    st.markdown(f"""
    <style>
    .login-modal-overlay {{
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(8,8,15,0.92);
        backdrop-filter: blur(12px);
        z-index: 999;
        pointer-events: none;
    }}
    .login-modal-content {{
        position: relative;
        z-index: 1000;
        pointer-events: auto;
    }}
    /* Lift Streamlit form elements above the overlay */
    [data-testid="stForm"],
    [data-testid="stVerticalBlock"],
    [data-testid="stTextInput"],
    [data-testid="stTextInputRootElement"],
    .stTextInput,
    .stForm,
    .stAlert {{
        position: relative !important;
        z-index: 1001 !important;
    }}
    </style>
    <div class="login-modal-overlay"></div>
    """, unsafe_allow_html=True)
    
    # Add spacing from top
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    
    # Center the login form
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown(f"""
        <div class="login-modal-content" style="
            background: {BG_CARD};
            border: 2px solid {BORDER_G2};
            border-radius: 24px;
            padding: 2.5rem 2rem 3rem 2rem;
            box-shadow: 0 24px 80px rgba(201,150,60,0.25);
            direction: {DIR};
            margin-bottom: 1.5rem;
        ">
            <div style="margin-bottom: 2.5rem; direction: {DIR}; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; width: 100%;">
                <div style="font-size: 3rem; margin-bottom: 0.8rem; text-align: center;">🔐</div>
                <h2 style="color: {GOLD_LIGHT}; font-size: 1.8rem; font-weight: 700; margin: 0 0 0.5rem 0; text-align: center;">{tx['login_title']}</h2>
                <p style="color: {TEXT_MUTED}; font-size: 0.95rem; margin: 0; text-align: center; padding: 0 1rem; max-width: 90%;">{tx['login_subtitle']}</p>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        if 'login_error' in st.session_state and st.session_state.login_error:
            st.error(f"❌ {tx['login_error']}")
        
        with st.form("login_form", clear_on_submit=False, border=False):
            username = st.text_input(
                tx['username_label'],
                key="login_username",
                placeholder=tx['username_label']
            )
            
            password = st.text_input(
                tx['password_label'],
                type="password",
                key="login_password",
                placeholder=tx['password_label']
            )
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            btn_col1, btn_col2 = st.columns(2)
            
            with btn_col1:
                submit = st.form_submit_button(tx['login_button'], use_container_width=True, type="primary")
            
            with btn_col2:
                cancel = st.form_submit_button(tx['cancel_button'], use_container_width=True)
            
            if submit:
                if username and password:
                    user = verify_credentials(username, password)
                    if user:
                        st.session_state.authenticated = True
                        st.session_state.show_login = False
                        st.session_state.login_error = False
                        st.session_state.current_user_center = user.get("center", "")
                        if st.session_state.pending_page:
                            st.session_state.page = st.session_state.pending_page
                            st.session_state.pending_page = None
                        st.rerun()
                    else:
                        st.session_state.login_error = True
                        st.rerun()
                else:
                    st.session_state.login_error = True
                    st.rerun()
            
            if cancel:
                st.session_state.show_login = False
                st.session_state.login_error = False
                st.session_state.pending_page = None
                st.rerun()


# ── Landing Page ──────────────────────────────────────────────────────────────
def landing_page(lang):
    tx  = T[lang]
    DIR = 'rtl' if lang == 'ar' else 'ltr'

    # ── Hero ──
    st.markdown(f"""
    <div class="hero-section">
        <div class="hero-glow"></div>
        <div class="hero-ring hero-ring-1"></div>
        <div class="hero-ring hero-ring-2"></div>
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

    # ── Use-case selection ──
    st.markdown(f"""
    <div style="text-align:center;padding:2.5rem 0 1rem;direction:{DIR};">
        <div class="section-label">{tx['section_label']}</div>
        <h2 class="section-title">{tx['section_title']}</h2>
        <div class="section-ornament">
            <span class="ornament-line"></span>
            <span class="ornament-diamond">◆</span>
            <span class="ornament-line right"></span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class="use-case-grid">
        <div class="use-case-card inquiries-card">
            <div class="use-case-icon-wrap inquiries-icon-wrap">📋</div>
            <div class="use-case-title">{tx['inq_card_title']}</div>
            <p class="use-case-desc">{tx['inq_card_desc']}</p>
            <div class="use-case-tags">
                <span class="use-case-tag inquiries-tag">{tx['inq_tag1']}</span>
                <span class="use-case-tag inquiries-tag">{tx['inq_tag2']}</span>
                <span class="use-case-tag inquiries-tag">{tx['inq_tag3']}</span>
            </div>
        </div>
        <div class="use-case-card complaints-card">
            <div class="use-case-icon-wrap complaints-icon-wrap">📣</div>
            <div class="use-case-title">{tx['cmp_card_title']}</div>
            <p class="use-case-desc">{tx['cmp_card_desc']}</p>
            <div class="use-case-tags">
                <span class="use-case-tag complaints-tag">{tx['cmp_tag1']}</span>
                <span class="use-case-tag complaints-tag">{tx['cmp_tag2']}</span>
                <span class="use-case-tag complaints-tag">{tx['cmp_tag3']}</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Buttons below the cards
    col1, col2 = st.columns([1, 1], gap="medium")
    with col1:
        if st.button(tx['btn_inq'], key="cta_inquiries", use_container_width=True):
            if st.session_state.authenticated:
                st.session_state.page = 'inquiries'
                st.rerun()
            else:
                st.session_state.show_login = True
                st.session_state.pending_page = 'inquiries'
                st.rerun()
    with col2:
        if st.button(tx['btn_cmp'], key="cta_complaints", use_container_width=True):
            if st.session_state.authenticated:
                st.session_state.page = 'complaints'
                st.rerun()
            else:
                st.session_state.show_login = True
                st.session_state.pending_page = 'complaints'
                st.rerun()

    # ── Footer ──
    st.markdown(f"""
    <div class="footer">
        <p class="footer-text" style="font-weight:600;color:{TEXT_MUTED};">
            {tx['footer_copy']}
        </p>
        <div class="footer-divider"></div>
        <p class="footer-text">{tx['footer_sub']}</p>
    </div>
    """, unsafe_allow_html=True)


# ── Inquiries Page ─────────────────────────────────────────────────────────────
def inquiries_page(lang):
    tx = T[lang]

    st.markdown(f"""
    <div class="page-header">
        <div class="page-header-tag">{tx['inq_header_tag']}</div>
        <h1 class="page-header-title">{tx['inq_header_title']}</h1>
        <p class="page-header-sub">{tx['inq_header_sub']}</p>
        <div class="page-header-bar"></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div style="padding: 2rem 2rem 0;">', unsafe_allow_html=True)

    if not st.session_state.completed:

        st.markdown(f"""
        <div class="panel">
            <div class="panel-title">{tx['inq_panel_title']}</div>
            <div class="panel-subtitle">{tx['inq_panel_sub']}</div>
            <div class="panel-divider"></div>
        </div>
        """, unsafe_allow_html=True)

        with st.container():
            st.markdown('<div style="max-width:820px;margin:0 auto;">', unsafe_allow_html=True)
            uploaded_files = st.file_uploader(
                tx['uploader_label'],
                type=['xlsx', 'xls', 'pdf'],
                help=tx['uploader_help'],
                label_visibility="collapsed",
                key="inq_uploader",
                accept_multiple_files=True,
            )
            st.markdown('</div>', unsafe_allow_html=True)

        if uploaded_files:
            st.session_state.uploaded_file = uploaded_files
            
            for uploaded_file in uploaded_files:
                file_size = uploaded_file.size / 1024
                size_str  = (f"{file_size:.1f} {tx['size_kb']}" if file_size < 1024
                             else f"{file_size/1024:.2f} {tx['size_mb']}")

                st.markdown(f"""
                <div class="file-meta" style="max-width:820px;margin:0.8rem auto;">
                    <div class="file-meta-row">
                        <span class="file-meta-key">{tx['file_key']}</span>
                        <span class="file-meta-val">{uploaded_file.name}</span>
                    </div>
                    <div class="file-meta-row">
                        <span class="file-meta-key">{tx['size_key']}</span>
                        <span class="file-meta-val">{size_str}</span>
                    </div>
                    <div class="file-meta-row">
                        <span class="file-meta-key">{tx['type_key']}</span>
                        <span class="file-meta-val">{uploaded_file.type}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            if not st.session_state.processing:
                st.markdown('<div style="max-width:820px;margin:1.5rem auto 0;">', unsafe_allow_html=True)
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    if st.button(tx['btn_start_inq'], use_container_width=True, type="primary", key="inq_start"):
                        all_valid = True
                        error_msg = ""
                        for uploaded_file in uploaded_files:
                            ok, msg = validate_file(uploaded_file, lang)
                            if not ok:
                                all_valid = False
                                error_msg = msg
                                break
                        if all_valid:
                            st.session_state.processing = True
                            st.rerun()
                        else:
                            st.markdown(f'<div class="error-panel">❌ {error_msg}</div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

        if st.session_state.processing:
            st.markdown('<div style="max-width:820px;margin:1.5rem auto 0;">', unsafe_allow_html=True)
            st.markdown(f"""
            <div class="stage-panel">
                <div class="stage-badge">{tx['stage_badge_inq']}</div>
                <div class="stage-title">{tx['stage_title']}</div>
                <div class="stage-desc">{tx['stage_desc_inq']}</div>
            </div>
            """, unsafe_allow_html=True)
            report = process_with_analyzer(uploaded_files, lang)
            st.markdown('</div>', unsafe_allow_html=True)

            st.session_state.processing = False
            st.session_state.completed  = True
            if report:
                st.session_state.report_data = report
            st.rerun()

    else:
        st.markdown(f"""
        <div class="success-panel">
            <div style="font-size:1.8rem;margin-bottom:0.4rem;">✅</div>
            <div class="success-title">{tx['success_title_inq']}</div>
            <div class="success-sub">{tx['success_sub_inq']}</div>
        </div>
        """, unsafe_allow_html=True)

        # Display report outputs in tabs
        st.markdown('<div style="max-width:900px;margin:2rem auto;">', unsafe_allow_html=True)
        display_report_tabs(lang, flow_type='inquiries')
        st.markdown('</div>', unsafe_allow_html=True)

        # For real flow, check if report was generated; for demo, check static files
        has_report = (
            'report_data' in st.session_state and st.session_state.report_data
        ) or Path("inquiries-output/تقرير تحليل استفسارات المتعاملين .docx").exists()

        if has_report:
            zip_data = create_download_zip(flow_type='inquiries')
            if zip_data:
                st.markdown('<div style="max-width:820px;margin:0 auto;">', unsafe_allow_html=True)
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    st.download_button(
                        label=tx['btn_download_inq'],
                        data=zip_data,
                        file_name="تقرير_تحليل_استفسارات_المتعاملين.zip",
                        mime="application/zip",
                        use_container_width=True,
                        key="inq_download",
                    )
                st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div style="max-width:820px;margin:2.5rem auto 0;">', unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button(tx['btn_reset'], use_container_width=True, key="inq_reset"):
                st.session_state.uploaded_file = None
                st.session_state.processing    = False
                st.session_state.completed     = False
                st.session_state.progress      = 0
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(f"""
    <div class="footer">
        <p class="footer-text" style="font-weight:600;color:{TEXT_MUTED};">
            {tx['footer_copy']}
        </p>
        <div class="footer-divider"></div>
        <p class="footer-text">{tx['footer_sub']}</p>
    </div>
    """, unsafe_allow_html=True)


# ── Complaints Page ────────────────────────────────────────────────────────────
def complaints_page(lang):
    tx = T[lang]

    st.markdown(f"""
    <div class="page-header-complaints page-header">
        <div class="page-header-tag">{tx['cmp_header_tag']}</div>
        <h1 class="page-header-title">{tx['cmp_header_title']}</h1>
        <p class="page-header-sub">{tx['cmp_header_sub']}</p>
        <div class="page-header-bar"></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div style="padding: 2rem 2rem 0;">', unsafe_allow_html=True)

    if not st.session_state.completed:

        st.markdown(f"""
        <div class="panel-blue panel">
            <div class="panel-title">{tx['cmp_panel_title']}</div>
            <div class="panel-subtitle">{tx['cmp_panel_sub']}</div>
            <div class="panel-divider"></div>
        </div>
        """, unsafe_allow_html=True)

        with st.container():
            st.markdown('<div class="blue-uploader" style="max-width:820px;margin:0 auto;">', unsafe_allow_html=True)
            uploaded_files = st.file_uploader(
                tx['uploader_label'],
                type=['xlsx', 'xls', 'pdf'],
                help=tx['uploader_help'],
                label_visibility="collapsed",
                key="cmp_uploader",
                accept_multiple_files=True,
            )
            st.markdown('</div>', unsafe_allow_html=True)

        if uploaded_files:
            st.session_state.uploaded_file = uploaded_files
            
            for uploaded_file in uploaded_files:
                file_size = uploaded_file.size / 1024
                size_str  = (f"{file_size:.1f} {tx['size_kb']}" if file_size < 1024
                             else f"{file_size/1024:.2f} {tx['size_mb']}")

                st.markdown(f"""
                <div class="file-meta-blue" style="max-width:820px;margin:0.8rem auto;">
                    <div class="file-meta-row">
                        <span class="file-meta-key-blue">{tx['file_key']}</span>
                        <span class="file-meta-val">{uploaded_file.name}</span>
                    </div>
                    <div class="file-meta-row">
                        <span class="file-meta-key-blue">{tx['size_key']}</span>
                        <span class="file-meta-val">{size_str}</span>
                    </div>
                    <div class="file-meta-row">
                        <span class="file-meta-key-blue">{tx['type_key']}</span>
                        <span class="file-meta-val">{uploaded_file.type}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            if not st.session_state.processing:
                st.markdown('<div style="max-width:820px;margin:1.5rem auto 0;">', unsafe_allow_html=True)
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    st.markdown('<div class="blue-btn">', unsafe_allow_html=True)
                    if st.button(tx['btn_start_cmp'], use_container_width=True, key="cmp_start"):
                        all_valid = True
                        error_msg = ""
                        for uploaded_file in uploaded_files:
                            ok, msg = validate_file(uploaded_file, lang)
                            if not ok:
                                all_valid = False
                                error_msg = msg
                                break
                        if all_valid:
                            st.session_state.processing = True
                            st.rerun()
                        else:
                            st.markdown(f'<div class="error-panel">❌ {error_msg}</div>', unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

        if st.session_state.processing:
            st.markdown('<div class="blue-progress" style="max-width:820px;margin:1.5rem auto 0;">', unsafe_allow_html=True)
            st.markdown(f"""
            <div class="stage-panel-blue">
                <div class="stage-badge-blue">{tx['stage_badge_cmp']}</div>
                <div class="stage-title">{tx['stage_title']}</div>
                <div class="stage-desc">{tx['stage_desc_cmp']}</div>
            </div>
            """, unsafe_allow_html=True)
            report = process_with_analyzer(uploaded_files, lang)
            st.markdown('</div>', unsafe_allow_html=True)
            st.session_state.processing = False
            st.session_state.completed  = True
            if report:
                st.session_state.report_data = report
            st.rerun()

    else:
        st.markdown(f"""
        <div class="success-panel">
            <div style="font-size:1.8rem;margin-bottom:0.4rem;">✅</div>
            <div class="success-title">{tx['success_title_cmp']}</div>
            <div class="success-sub">{tx['success_sub_cmp']}</div>
        </div>
        """, unsafe_allow_html=True)

        # Display report outputs in tabs
        st.markdown('<div style="max-width:900px;margin:2rem auto;">', unsafe_allow_html=True)
        display_report_tabs(lang, flow_type='complaints')
        st.markdown('</div>', unsafe_allow_html=True)

        # For real flow, check if report was generated; for demo, check static files
        has_report = (
            'report_data' in st.session_state and st.session_state.report_data
        ) or Path("complaints-output/تقرير تحليل شكاوى المتعاملين.docx").exists()

        if has_report:
            zip_data = create_download_zip(flow_type='complaints')
            if zip_data:
                st.markdown('<div class="blue-download" style="max-width:820px;margin:0 auto;">', unsafe_allow_html=True)
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    st.download_button(
                        label=tx['btn_download_cmp'],
                        data=zip_data,
                        file_name="تقرير_تحليل_شكاوى_المتعاملين.zip",
                        mime="application/zip",
                        use_container_width=True,
                        key="cmp_download",
                    )
                st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div style="max-width:820px;margin:2.5rem auto 0;">', unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown('<div class="blue-btn">', unsafe_allow_html=True)
            if st.button(tx['btn_reset'], use_container_width=True, key="cmp_reset"):
                st.session_state.uploaded_file = None
                st.session_state.processing    = False
                st.session_state.completed     = False
                st.session_state.progress      = 0
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(f"""
    <div class="footer">
        <p class="footer-text" style="font-weight:600;color:{TEXT_MUTED};">
            {tx['footer_copy']}
        </p>
        <div class="footer-divider"></div>
        <p class="footer-text">{tx['footer_sub']}</p>
    </div>
    """, unsafe_allow_html=True)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    init_session_state()
    lang = st.session_state.language
    load_css(lang)

    left_logo_path = Path("assets/Pictureee1.png")

    # Nav bar
    col_l, col_c, col_r = st.columns([2, 6, 2])

    with col_l:
        if left_logo_path.exists():
            st.image(str(left_logo_path), width=160)

    with col_c:
        if st.session_state.page in ('inquiries', 'complaints'):
            st.markdown('<div class="nav-back-wrap">', unsafe_allow_html=True)
            if st.button(T[lang]['nav_back'], key="nav_back"):
                st.session_state.page          = 'landing'
                st.session_state.uploaded_file = None
                st.session_state.processing    = False
                st.session_state.completed     = False
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    with col_r:
        # Language Toggle - wrapped in container to control direction
        st.markdown(
            """
            <div style='
                font-weight: 700;
                margin-bottom: 0.5rem;
                color: #B68A35;
                font-size: 0.75rem;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                text-align: center;
                direction: ltr;
            '>🌐 Language</div>
            """,
            unsafe_allow_html=True
        )

        # Wrap toggle in a div to force LTR
        st.markdown('<div style="direction: ltr; display: flex; justify-content: center;">', unsafe_allow_html=True)

        # Toggle switch for language
        is_arabic = st.toggle(
            "عربي" if lang == "ar" else "Arabic",
            value=st.session_state.get("language", "en") == "ar",
            key="lang_toggle",
            help="Toggle to switch between English and Arabic"
        )

        st.markdown('</div>', unsafe_allow_html=True)

        # Display user's center name if authenticated
        if st.session_state.authenticated and st.session_state.current_user_center:
            st.markdown(
                f"""
                <div style='
                    font-size: 0.7rem;
                    color: #B68A35;
                    text-align: center;
                    margin-top: 0.4rem;
                    font-weight: 500;
                '>{st.session_state.current_user_center}</div>
                """,
                unsafe_allow_html=True
            )

        new_lang_code = "ar" if is_arabic else "en"
        if new_lang_code != st.session_state.get("language", "en"):
            st.session_state.language = new_lang_code
            st.rerun()

    # Gold separator line under nav
    st.markdown(f"""
    <div style="height:1px;background:linear-gradient(90deg,transparent,{BORDER_G2},transparent);
                margin-bottom:0;"></div>
    """, unsafe_allow_html=True)

    # Show login modal if needed (blocks other content)
    if st.session_state.show_login:
        show_login_modal(lang)
        st.stop()
    
    if st.session_state.page == 'landing':
        landing_page(lang)
    elif st.session_state.page == 'inquiries':
        inquiries_page(lang)
    else:
        complaints_page(lang)


if __name__ == "__main__":
    main()
