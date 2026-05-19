import streamlit as st
import time
import os
import json
import random
import traceback
import shutil
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
        'hero_subtitle':     'منصة ذكاء اصطناعي متقدمة لتحليل استفسارات المتعاملين واستخراج الرؤى والتوصيات لتحسين جودة الخدمات الحكومية',
        'badge_speed':       '⚡ معالجة فورية',
        'badge_accuracy':    '🎯 دقة عالية',
        'badge_security':    '🔒 بيانات آمنة',
        'badge_reports':     '📊 تقارير شاملة',
        'section_label':     'تحليل ذكي للاستفسارات',
        'section_title':     'استخرج الرؤى والتوصيات من استفسارات المتعاملين',
        'cmp_description':   'حول شكاوى المتعاملين إلى أفكار قابلة للتنفيذ باستخدام الذكاء الاصطناعي',
        'feat1_title':       'تصنيف تلقائي',
        'feat1_desc':        'صنّف الشكاوى حسب النوع والمجال والأولوية تلقائياً',
        'feat2_title':       'تحليل الأولويات',
        'feat2_desc':        'حدّد الشكاوى الحرجة والمتكررة والأنماط المهمة',
        'feat3_title':       'توصيات ذكية',
        'feat3_desc':        'احصل على توصيات قابلة للتطبيق لمعالجة الأسباب الجذرية',
        'how_label':         'كيف يعمل',
        'how_title':         'ثلاث خطوات بسيطة لتحليل شامل',
        'step1_title':       'ارفع الملف',
        'step1_sub':         'أرسل ملف الشكاوى (Excel أو PDF)',
        'step2_title':       'التحليل الفوري',
        'step2_sub':         'يقوم الذكاء الاصطناعي بالتحليل والتصنيف',
        'step3_title':       'التقرير الشامل',
        'step3_sub':         'احصل على تقرير مفصل مع التوصيات',
        'cta_btn':           'ابدأ تحليل الشكاوى الآن  ←',
        'cmp_card_title':    'تحليل الشكاوى',
        'cmp_card_desc':     'حلّل شكاوى المتعاملين وصنّفها حسب الأولوية والنوع واستخرج توصيات لمعالجة الأسباب الجذرية.',
        'cmp_tag1':          'Excel / PDF',
        'cmp_tag2':          'تقرير Word',
        'cmp_tag3':          'نتائج فورية',
        'inq_card_title':    'تحليل الاستفسارات',
        'inq_card_desc':     'حلّل استفسارات المتعاملين واستخرج الأنماط والتوجهات لتحسين مستوى الخدمة وسرعة الاستجابة.',
        'inq_tag1':          'Excel / PDF',
        'inq_tag2':          'تقرير Word',
        'inq_tag3':          'نتائج فورية',
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
        'artifacts_generating': 'جاري إعداد الملفات...',
    },
    'en': {
        'nav_back':          '← Back to Home',
        'hero_eyebrow':      'Fujairah Police · Smart Services',
        'hero_title':        'Fujairah Pulse',
        'hero_subtitle':     'Advanced AI platform for analyzing citizen inquiries and extracting insights and recommendations to improve government service quality',
        'badge_speed':       '⚡ Instant Processing',
        'badge_accuracy':    '🎯 High Accuracy',
        'badge_security':    '🔒 Secure Data',
        'badge_reports':     '📊 Comprehensive Reports',
        'section_label':     'Smart Inquiries Analysis',
        'section_title':     'Extract insights and recommendations from citizen inquiries',
        'cmp_description':   'Turn citizen complaints into actionable intelligence using advanced AI',
        'feat1_title':       '🔍 Automatic Classification',
        'feat1_desc':        'Classify complaints by type, category, and priority automatically',
        'feat2_title':       '📊 Priority Analysis',
        'feat2_desc':        'Identify critical, recurring, and high-impact complaints instantly',
        'feat3_title':       '💡 Smart Recommendations',
        'feat3_desc':        'Get actionable recommendations to address root causes',
        'how_label':         'How it Works',
        'how_title':         'Three simple steps to comprehensive analysis',
        'step1_title':       'Upload File',
        'step1_sub':         'Submit your complaints file (Excel or PDF)',
        'step2_title':       'Instant Analysis',
        'step2_sub':         'AI analyzes and classifies complaints',
        'step3_title':       'Full Report',
        'step3_sub':         'Get detailed report with recommendations',
        'cta_btn':           'Start Complaints Analysis Now  →',
        'cmp_card_title':    'Complaints Analysis',
        'cmp_card_desc':     'Analyze citizen complaints, classify by priority and type, and extract recommendations to address root causes.',
        'cmp_tag1':          'Excel / PDF',
        'cmp_tag2':          'Word Report',
        'cmp_tag3':          'Instant Results',
        'inq_card_title':    'Inquiries Analysis',
        'inq_card_desc':     'Analyze citizen inquiries and extract patterns and trends to improve service quality and response speed.',
        'inq_tag1':          'Excel / PDF',
        'inq_tag2':          'Word Report',
        'inq_tag3':          'Instant Results',
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
        'artifacts_generating': 'Preparing artifacts...',
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
        display: block;
        font-size: 1.35rem;
        font-weight: 400;
        color: rgba(228,228,240,0.75);
        max-width: 780px;
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
        display: block;
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
        height: 100%;
        text-align: center;
        align-items: center;
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
        margin: 0 auto 1.4rem;
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
    button, .stButton button, .stButton > button {{
        background-color: transparent !important;
    }}
    .stButton > button {{
        background: linear-gradient(
            110deg,
            {GOLD_DARK} 0%,
            {GOLD}      28%,
            {GOLD_LIGHT} 52%,
            {GOLD_PALE}  66%,
            {GOLD_LIGHT} 80%,
            {GOLD}      100%
        ) !important;
        background-size: 260% 260% !important;
        animation: gradientFlow 5s ease infinite !important;
        color: {BG_DEEP} !important;
        font-family: {FONT} !important;
        font-weight: 700 !important;
        font-size: 1.05rem !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 0.85rem 2rem !important;
        width: 100% !important;
        cursor: pointer !important;
        position: relative !important;
        overflow: hidden !important;
        transition: transform 0.25s cubic-bezier(0.4,0,0.2,1),
                    box-shadow 0.25s ease !important;
        box-shadow: 0 4px 20px rgba(201,150,60,0.28) !important;
        direction: {DIR} !important;
        letter-spacing: 0.3px !important;
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
        transform: translateY(-3px) !important;
        box-shadow: 0 10px 38px rgba(201,150,60,0.52) !important;
        animation: gradientFlow 2.2s ease infinite !important;
        color: {BG_DEEP} !important;
    }}
    .stButton > button:hover::before {{
        animation: shimmerSweep 0.85s ease forwards !important;
    }}
    .stButton > button:active {{
        transform: translateY(0) !important;
        box-shadow: 0 3px 14px rgba(201,150,60,0.35) !important;
    }}

    /* ── FORM SUBMIT BUTTONS ── */
    [data-testid="stForm"] button {{
        background: linear-gradient(
            110deg,
            {GOLD_DARK} 0%,
            {GOLD}      28%,
            {GOLD_LIGHT} 52%,
            {GOLD_PALE}  66%,
            {GOLD_LIGHT} 80%,
            {GOLD}      100%
        ) !important;
        background-size: 260% 260% !important;
        color: {BG_DEEP} !important;
        font-weight: 700 !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 0.7rem 1.5rem !important;
        cursor: pointer !important;
        box-shadow: 0 4px 20px rgba(201,150,60,0.28) !important;
    }}
    [data-testid="stForm"] button:hover {{
        box-shadow: 0 10px 38px rgba(201,150,60,0.52) !important;
        transform: translateY(-2px) !important;
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
    .custom-progress-wrapper {{
        width: 100%;
        height: 8px;
        background: rgba(255,255,255,0.05);
        border-radius: 10px;
        overflow: hidden;
        margin: 1.5rem 0;
        display: flex;
    }}
    .custom-progress-bar {{
        height: 100%;
        background: linear-gradient(90deg, {GOLD_DARK}, {GOLD}, {GOLD_LIGHT});
        border-radius: 10px;
        transition: width 0.4s ease;
        width: 0%;
    }}
    .custom-progress-bar.rtl {{
        margin-left: auto;
        border-radius: 10px 0 0 10px;
        transform: scaleX(-1);
    }}
    /* Hide default Streamlit progress bar and replace with custom */
    .stProgress {{
        display: none !important;
    }}
    /* Blue progress bar */
    .blue-progress .custom-progress-bar {{
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

    /* ── COMPLAINTS SHOWCASE SECTION ── */
    .complaints-showcase {{
        max-width: 900px;
        margin: 3rem auto 2rem;
        padding: 0 1rem;
        text-align: center !important;
        direction: {DIR} !important;
    }}
    .complaints-feature-card {{
        background: {BG_CARD};
        border: 1.5px solid {BORDER_B};
        border-radius: 24px;
        padding: 3rem 2.5rem;
        text-align: center !important;
        direction: {DIR} !important;
        position: relative;
        overflow: hidden;
        margin-bottom: 3rem;
    }}
    .complaints-feature-card::before {{
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 3px;
        background: linear-gradient(90deg, transparent, {BLUE}, transparent);
    }}
    .complaints-feature-card:hover {{
        border-color: {BORDER_B2};
        box-shadow: 0 24px 80px rgba(46,134,171,0.15);
        transform: translateY(-4px);
    }}
    .complaints-feature-card .title {{
        font-size: 1.8rem;
        font-weight: 800;
        color: {BLUE_LIGHT};
        margin: 0 0 1rem;
        text-align: center !important;
    }}
    .complaints-feature-card .desc {{
        color: {TEXT_MUTED};
        font-size: 1.05rem;
        line-height: 1.8;
        margin: 0;
        text-align: center !important;
    }}

    /* ── BLUE FEATURE CARDS ── */
    .blue-feature-card {{
        background: {BG_CARD};
        border: 1px solid {BORDER_B};
        border-radius: 20px;
        padding: 2.5rem 2rem;
        position: relative;
        overflow: hidden;
        transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
        direction: {DIR} !important;
        display: flex;
        flex-direction: column;
        text-align: center !important;
        min-height: 270px;
    }}
    .blue-feature-card::before {{
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 2px;
        background: linear-gradient(90deg, transparent, {BLUE}, transparent);
        opacity: 0.6;
    }}
    .blue-feature-card:hover {{
        border-color: {BORDER_B2};
        box-shadow: 0 24px 64px rgba(46,134,171,0.09), 0 0 0 1px {BORDER_B};
        transform: translateY(-4px);
    }}
    .blue-feature-card .feature-icon-wrap {{
        width: 58px; height: 58px;
        background: linear-gradient(135deg, rgba(46,134,171,0.15), rgba(46,134,171,0.04));
        border: 1px solid {BORDER_B2};
        border-radius: 14px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.8rem;
        margin: 0 auto 1.4rem;
    }}
    .blue-feature-card .feature-title {{
        color: {BLUE_LIGHT};
        font-size: 1.25rem;
        font-weight: 700;
        margin: 0 0 0.7rem;
        direction: {DIR} !important;
        text-align: center !important;
    }}
    .blue-feature-card .feature-desc {{
        color: {TEXT_MUTED};
        font-size: 1rem;
        line-height: 1.8;
        margin: 0;
        direction: {DIR} !important;
        flex: 1;
        text-align: center !important;
    }}

    /* ── BLUE STEP CARDS ── */
    .blue-step-card {{
        background: {BG_CARD};
        border: 1px solid {BORDER_B};
        border-radius: 16px;
        padding: 2rem 1.5rem;
        text-align: center !important;
        direction: {DIR} !important;
        position: relative;
        transition: all 0.3s ease;
        display: flex;
        flex-direction: column;
    }}
    .blue-step-card:hover {{
        border-color: {BORDER_B2};
        box-shadow: 0 12px 40px rgba(46,134,171,0.07);
    }}
    .blue-step-card .step-number {{
        font-size: 2.6rem;
        font-weight: 900;
        background: linear-gradient(135deg, {BORDER_B2}, rgba(46,134,171,0.1));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        line-height: 1;
        margin-bottom: 0.6rem;
        text-align: center !important;
    }}
    .blue-step-card .step-icon {{
        font-size: 2rem;
        margin-bottom: 0.8rem;
        text-align: center !important;
    }}
    .blue-step-card .step-title {{
        color: {TEXT};
        font-size: 1.05rem;
        font-weight: 600;
        margin: 0 0 0.5rem;
        text-align: center !important;
        direction: {DIR} !important;
    }}
    .blue-step-card .step-desc {{
        color: {TEXT_MUTED};
        font-size: 0.9rem;
        line-height: 1.7;
        margin: 0;
        text-align: center !important;
        direction: {DIR} !important;
        flex: 1;
    }}

    /* ── CTA SECTION ── */
    .cta-section {{
        max-width: 480px;
        margin: 3rem auto 3rem;
        padding: 0 1rem;
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
    [data-testid="stHorizontalBlock"] > [data-testid="column"] {{
        display: flex !important;
        flex-direction: column !important;
    }}
    .feature-card, .step-card {{
        height: 100% !important;
        display: flex !important;
        flex-direction: column !important;
        box-sizing: border-box !important;
        align-items: center !important;
        justify-content: flex-start !important;
    }}
    .feature-icon-wrap {{
        margin-left: auto !important;
        margin-right: auto !important;
    }}
    .feature-title, .step-title {{
        width: 100% !important;
        text-align: center !important;
    }}
    .feature-desc, .step-desc {{
        flex: 1 !important;
        width: 100% !important;
        text-align: center !important;
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
        'selected_period_inq': None,
        'selected_period_cmp': None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── Authentication ────────────────────────────────────────────────────────────
def load_credentials():
    # Try to load from Streamlit secrets first (for deployment)
    try:
        if hasattr(st, 'secrets') and 'users' in st.secrets:
            print("[Auth] Loading credentials from st.secrets")
            users = []
            users_section = st.secrets.users
            print(f"[Auth] Found users section with keys: {list(users_section.keys())[:5]}...")

            # Load admin user
            if 'admin_username' in users_section:
                users.append({
                    "username": users_section['admin_username'],
                    "password": users_section['admin_password'],
                    "center": users_section.get('admin_center', 'مركز الإدارة المركزية')
                })

            # Load demo user
            if 'demo_username' in users_section:
                users.append({
                    "username": users_section['demo_username'],
                    "password": users_section['demo_password'],
                    "center": users_section.get('demo_center', 'مركز التجريب والعروض التوضيحية')
                })

            # Load fujairah-user
            if 'fujairah_username' in users_section:
                users.append({
                    "username": users_section['fujairah_username'],
                    "password": users_section['fujairah_password'],
                    "center": users_section.get('fujairah_center', 'مركز الفجيرة الرئيسي')
                })

            # Load Fujairah Police Center users
            user_configs = [
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
                if email_key in users_section and password_key in users_section:
                    users.append({
                        "username": users_section[email_key],
                        "password": users_section[password_key],
                        "center": users_section.get(center_key, "Unknown Center")
                    })

            if users:
                print(f"[Auth] Successfully loaded {len(users)} users from secrets")
                return {"users": users}
            else:
                print("[Auth] No users loaded from secrets")
    except Exception as e:
        print(f"[Auth] Error loading credentials from secrets: {e}")
        import traceback
        traceback.print_exc()

    # Fallback: return empty users list
    print("[Auth] Returning empty users list")
    return {"users": []}

def verify_credentials(username, password):
    creds = load_credentials()
    print(f"[Login] Verifying credentials for username: '{username}' with password: '{password}'")
    print(f"[Login] Available users: {[u.get('username') for u in creds.get('users', [])]}")
    for user in creds.get("users", []):
        print(f"[Login] Checking user '{user['username']}' against input '{username}' (match: {user['username'] == username})")
        if user["username"] == username:
            print(f"[Login] Username matched! Checking password: '{user['password']}' vs '{password}' (match: {user['password'] == password})")
        if user["username"] == username and user["password"] == password:
            print(f"[Login] ✅ Credentials matched for {username}")
            return user  # Return the full user object with center name
    print(f"[Login] ❌ No matching credentials found for {username}")
    return None

# ── Period Folder Management ──────────────────────────────────────────────────
def get_period_folders(flow_type: str = 'inquiries'):
    """Get list of period folders from the output directory.

    Args:
        flow_type: 'inquiries' or 'complaints'

    Returns:
        List of period folder names sorted, excluding cache folder
    """
    script_dir = Path(__file__).parent
    if flow_type == 'complaints':
        output_path = script_dir / "complaints-output"
    else:
        output_path = script_dir / "inquiries-output"

    if not output_path.exists():
        return []

    # Get all subdirectories except cache
    folders = [
        d.name for d in output_path.iterdir()
        if d.is_dir() and d.name != 'cache'
    ]
    return sorted(folders)


def get_report_files_in_period(flow_type: str, period: str, lang: str = 'ar'):
    """Get the report and Excel files for a specific period.

    Args:
        flow_type: 'inquiries' or 'complaints'
        period: The period folder name
        lang: Language preference ('ar' or 'en'). For complaints flow in English, looks in english-output folder.

    Returns:
        Tuple of (docx_path, xlsx_path) or (None, None) if not found
    """
    script_dir = Path(__file__).parent
    if flow_type == 'complaints':
        # For English mode in complaints, look in english-output subfolder
        if lang == 'en':
            period_path = script_dir / "complaints-output" / period / "english-output"
        else:
            period_path = script_dir / "complaints-output" / period
    else:
        period_path = script_dir / "inquiries-output" / period

    if not period_path.exists():
        return None, None

    # Find .docx and .xlsx files (excluding temp files starting with ~$)
    docx_files = [f for f in period_path.glob("*.docx") if not f.name.startswith("~$")]
    xlsx_files = [f for f in period_path.glob("*.xlsx")]

    docx_path = docx_files[0] if docx_files else None
    xlsx_path = xlsx_files[0] if xlsx_files else None

    return docx_path, xlsx_path

# ── Analyzer Setup ────────────────────────────────────────────────────────────
@st.cache_resource
def get_analyzer():
    """Get the real analyzer (cached for performance)."""
    return RealAnalyzer()

# ── Validation ────────────────────────────────────────────────────────────────
def validate_file(uploaded_file, lang='ar'):
    tx = T[lang]
    is_valid, error_msg = get_analyzer().validate_file(uploaded_file)
    if not is_valid:
        return False, error_msg or tx['err_bad_type']
    return True, ""


# ── Process Files with Analyzer ───────────────────────────────────────────────
def process_with_analyzer(uploaded_files, lang='ar'):
    """
    Process uploaded files through the real analyzer pipeline.
    
    Args:
        uploaded_files: List of Streamlit UploadedFile objects
        lang: Language preference ('ar' or 'en')
    
    Returns:
        Dictionary containing report structure with sections and tables
    """
    import streamlit as st
    
    if not uploaded_files:
        raise ValueError("No files provided for processing")
    
    # For now, process the first file (single file analysis)
    # TODO: Support multiple file processing if needed
    uploaded_file = uploaded_files[0] if isinstance(uploaded_files, list) else uploaded_files
    
    print(f"[process_with_analyzer] Starting analysis for: {uploaded_file.name}")
    
    # Progress callback for real-time UI updates
    progress_placeholder = st.empty()
    progress_bar = st.progress(0)

    # Initialize progress display immediately with custom RTL progress bar
    progress_placeholder.markdown(f"""
    <div style="text-align:center;padding:1rem;color:#E4E4F0;font-size:1.1rem;font-weight:600;margin-bottom:0.5rem;">
        جاري تحليل الملف...
    </div>
    <div class="custom-progress-wrapper">
        <div class="custom-progress-bar rtl" id="progress-bar" style="width: 1%;"></div>
    </div>
    <div style="text-align:center;padding:0.5rem;color:#999;font-size:0.9rem;">
        0%
    </div>
    """, unsafe_allow_html=True)

    def update_progress(progress_pct, msg_ar, msg_en):
        """Update UI with progress from pipeline stages."""
        msg = msg_ar if lang == 'ar' else msg_en
        pct_display = int(progress_pct * 100)
        print(f"[Progress] {pct_display}% - {msg_ar}")

        # Determine which stage based on progress percentage
        stages = [
            ('1', 'التحقق من صيغة الملف', 'File Validation', 0, 10),
            ('2', 'تصنيف القواعد', 'Rule Classification', 10, 30),
            ('3', 'معالجة الذكاء الاصطناعي', 'AI Classification', 30, 50),
            ('4', 'تحليل الأنماط', 'Pattern Analysis', 50, 70),
            ('5', 'تحليل الفجوات', 'Gap Analysis', 70, 85),
            ('6', 'توليد التقرير', 'Report Generation', 85, 100),
        ]

        current_stage = '1'
        for stage_num, stage_ar, stage_en, start, end in stages:
            if start <= pct_display <= end:
                current_stage = stage_num
                break

        # Build stage indicators
        stage_html = '<div style="display:flex;gap:0.5rem;justify-content:center;margin-bottom:1rem;">'
        for stage_num, stage_ar, stage_en, _, _ in stages:
            is_current = stage_num == current_stage
            is_complete = int(current_stage) > int(stage_num)

            if is_complete:
                badge_style = f"background-color:{GREEN_OK};color:#000;border:2px solid {GREEN_OK};"
                badge_text = "✓"
            elif is_current:
                badge_style = f"background-color:{GOLD};color:#000;border:2px solid {GOLD};animation:pulse 1s infinite;"
                badge_text = stage_num
            else:
                badge_style = f"background-color:{BG_CARD};color:{TEXT_MUTED};border:2px solid {BORDER_G};"
                badge_text = stage_num

            stage_html += f'<div style="width:2.5rem;height:2.5rem;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:bold;{badge_style}">{badge_text}</div>'

        stage_html += '</div>'

        progress_placeholder.markdown(f"""
        <style>
            @keyframes pulse {{
                0% {{ opacity: 1; }}
                50% {{ opacity: 0.7; }}
                100% {{ opacity: 1; }}
            }}
        </style>
        {stage_html}
        <div class="custom-progress-wrapper">
            <div class="custom-progress-bar rtl" style="width: {pct_display}%;"></div>
        </div>
        <div style="text-align:center;padding:0.5rem;color:#E4E4F0;font-size:1.1rem;font-weight:600;margin-bottom:0.5rem;">
            {msg}
        </div>
        <div style="text-align:center;padding:0.5rem;color:{TEXT_MUTED};font-size:0.9rem;">
            {pct_display}%
        </div>
        """, unsafe_allow_html=True)
        progress_bar.progress(min(progress_pct, 1.0))
    
    try:
        # Call the analyzer's analyze method with progress callback
        report = get_analyzer().analyze(uploaded_file, progress_callback=update_progress)
        
        # Clear progress indicators
        progress_placeholder.empty()
        progress_bar.empty()
        
        print(f"[process_with_analyzer] Analysis complete! Report has {len(report.get('sections', {}))} sections")
        return report
        
    except Exception as e:
        # Clear progress indicators on error
        progress_placeholder.empty()
        progress_bar.empty()
        
        print(f"[process_with_analyzer] ERROR: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise


# ── Display Report ─────────────────────────────────────────────────────────────
def display_report_tabs(lang: str = 'ar', flow_type: str = 'inquiries', period: str = None):
    """Display report from JSON data in session state with section dropdown.

    Args:
        lang: Language preference ('ar' or 'en')
        flow_type: 'inquiries' or 'complaints' - determines which output folder to use
        period: The period folder name (e.g. '2025', 'Q1_2026'). If None, uses root folder.
    """
    try:
        # Try to use report_data from session state first
        report_data = st.session_state.get('report_data')

        if report_data:
            cache_dir = None
            if flow_type == 'complaints':
                cache_dir = str(Path(__file__).parent / "complaints-output" / "cache")
            else:
                cache_dir = str(Path(__file__).parent / "inquiries-output" / "cache")

            display = DynamicReportDisplay(lang=lang, cache_dir=cache_dir)
            # Use the English JSON when the UI is set to English and translation exists
            if lang == 'en' and report_data.get('report_json_en'):
                display.display_from_json(report_data['report_json_en'])
            else:
                display.display_from_json(report_data)
            return

        # Fallback: look for existing report files (for legacy compatibility)
        script_dir = Path(__file__).parent

        if flow_type == 'complaints':
            if lang == 'en':
                if period:
                    outputs_path = script_dir / "complaints-output" / period / "english-output"
                else:
                    outputs_path = script_dir / "complaints-output"
                cache_dir = str(script_dir / "complaints-output" / "cache" / "english-cache")
                search_keywords = ['complaints']
            else:
                if period:
                    outputs_path = script_dir / "complaints-output" / period
                else:
                    outputs_path = script_dir / "complaints-output"
                cache_dir = str(script_dir / "complaints-output" / "cache")
                search_keywords = ['تقرير', 'شكاوى']
        else:
            if period:
                outputs_path = script_dir / "inquiries-output" / period
            else:
                outputs_path = script_dir / "inquiries-output"
            search_keywords = ['تقرير', 'استفسارات']
            cache_dir = str(script_dir / "inquiries-output" / "cache")

        if not outputs_path.exists():
            st.error(f"❌ {outputs_path.name} folder not found at {outputs_path}")
            return

        docx_files = [f for f in outputs_path.glob("*.docx") if not f.name.startswith("~$")]

        if not docx_files:
            st.error(f"❌ No .docx files found in {outputs_path.name}/")
            return

        report_path = None
        for docx_file in docx_files:
            if all(keyword in docx_file.name for keyword in search_keywords):
                report_path = docx_file
                break

        if report_path is None:
            st.error(f"❌ Report file not found. Files: {', '.join([f.name for f in docx_files])}")
            return

        display = DynamicReportDisplay(lang=lang, cache_dir=cache_dir)
        display.display_report(str(report_path))
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
        st.code(traceback.format_exc())


# ── Handle Generated Output Files ────────────────────────────────────────────
def _handle_generated_outputs(excel_path: str, word_path: str, lang: str = 'ar', word_path_en: str = None):
    """
    Handle generated output files from RealAnalyzer.

    Copies files from temp directory to output folder and updates session state.

    Args:
        excel_path: Path to generated Excel file
        word_path: Path to generated Arabic Word document
        lang: Language preference
        word_path_en: Path to generated English Word document (optional)
    """
    output_dir = Path(__file__).parent / "inquiries-output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Store original paths in session state for direct access if needed
    if 'output_files' not in st.session_state:
        st.session_state.output_files = {}

    # Copy Excel file
    print(f"[Output] Checking Excel: path={excel_path}, exists={Path(excel_path).exists() if excel_path else False}")
    if excel_path and Path(excel_path).exists():
        try:
            dest_excel = output_dir / "Fujairah_Police_Inquiry_Triage_Detail.xlsx"
            shutil.copy2(excel_path, dest_excel)
            st.session_state.output_files['excel_ready'] = True
            st.session_state.output_files['excel_path'] = str(dest_excel)
            print(f"[Output] ✓ Excel file copied to {dest_excel}")
        except Exception as e:
            print(f"[Output] ✗ Error copying Excel: {e}")
            st.session_state.output_files['excel_ready'] = False
    else:
        print(f"[Output] ✗ Excel file not found at {excel_path}")
        st.session_state.output_files['excel_ready'] = False

    # Copy Arabic Word document
    print(f"[Output] Checking Word: path={word_path}, exists={Path(word_path).exists() if word_path else False}")
    if word_path and Path(word_path).exists():
        try:
            dest_word = output_dir / "تقرير تحليل استفسارات المتعاملين .docx"
            shutil.copy2(word_path, dest_word)
            st.session_state.output_files['word_ready'] = True
            st.session_state.output_files['word_path'] = str(dest_word)
            print(f"[Output] ✓ Word document copied to {dest_word}")
        except Exception as e:
            print(f"[Output] ✗ Error copying Word: {e}")
            st.session_state.output_files['word_ready'] = False
    else:
        print(f"[Output] ✗ Word document not found at {word_path}")
        st.session_state.output_files['word_ready'] = False

    # Copy English Word document (generated alongside the Arabic one with _en suffix)
    print(f"[Output] Checking English Word: path={word_path_en}, exists={Path(word_path_en).exists() if word_path_en else False}")
    if word_path_en and Path(word_path_en).exists():
        try:
            dest_word_en = output_dir / "Inquiries Analysis Report.docx"
            shutil.copy2(word_path_en, dest_word_en)
            st.session_state.output_files['word_en_ready'] = True
            st.session_state.output_files['word_en_path'] = str(dest_word_en)
            print(f"[Output] ✓ English Word document copied to {dest_word_en}")
        except Exception as e:
            print(f"[Output] ✗ Error copying English Word: {e}")
            st.session_state.output_files['word_en_ready'] = False
    else:
        print(f"[Output] ✗ English Word document not found at {word_path_en}")
        st.session_state.output_files['word_en_ready'] = False


# ── Create ZIP with multiple files ────────────────────────────────────────────
def create_download_zip(flow_type: str = 'inquiries', period: str = None, lang: str = 'ar'):
    """Create a ZIP file containing the Word report and Excel file

    Args:
        flow_type: 'inquiries' or 'complaints' - determines which output folder to use
        period: The period folder name. If None, uses root folder (legacy behavior).
        lang: Language preference ('ar' or 'en'). For complaints flow in English, uses english-output folder.
    """
    script_dir = Path(__file__).parent
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        if flow_type == 'inquiries':
            # First check session state for newly generated files
            output_files = st.session_state.get('output_files', {})
            excel_path = output_files.get('excel_path')
            word_path = output_files.get('word_path')

            # Fall back to standard output folder locations if not in session state
            if not excel_path or not Path(excel_path).exists():
                if period:
                    report_path, excel_path = get_report_files_in_period('inquiries', period, lang=lang)
                else:
                    excel_path = script_dir / "inquiries-output" / "Fujairah_Police_Inquiry_Triage_Detail.xlsx"
                    excel_path = excel_path if excel_path.exists() else None

            if not word_path or not Path(word_path).exists():
                if period:
                    report_path, _ = get_report_files_in_period('inquiries', period, lang=lang)
                    word_path = report_path
                else:
                    word_path = script_dir / "inquiries-output" / "تقرير تحليل استفسارات المتعاملين .docx"
                    word_path = word_path if word_path.exists() else None

            # Add files to zip if they exist
            if word_path and Path(word_path).exists():
                word_file = Path(word_path)
                zip_file.write(word_file, word_file.name)

            # Include English Word report when available
            word_en_path = output_files.get('word_en_path')
            if word_en_path and Path(word_en_path).exists():
                word_en_file = Path(word_en_path)
                zip_file.write(word_en_file, word_en_file.name)

            if excel_path and Path(excel_path).exists():
                excel_file = Path(excel_path)
                zip_file.write(excel_file, excel_file.name)

        else:  # complaints flow
            if period:
                report_path, excel_path = get_report_files_in_period('complaints', period, lang=lang)
                if report_path:
                    zip_file.write(report_path, report_path.name)
                if excel_path:
                    zip_file.write(excel_path, excel_path.name)
            else:
                # Legacy behavior - look in root
                report_path = script_dir / "complaints-output" / "تقرير تحليل شكاوى المتعاملين.docx"
                if report_path.exists():
                    zip_file.write(report_path, "تقرير تحليل شكاوى المتعاملين.docx")

                excel_path = script_dir / "complaints-output" / "تصنيف شكاوى المتعاملين — حسب النوع 2025.xlsx"
                if excel_path.exists():
                    zip_file.write(excel_path, "تصنيف شكاوى المتعاملين — حسب النوع 2025.xlsx")

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
def simulate_period_processing(lang='ar'):
    """Simulate processing for a selected period (no file upload)."""
    progress_container = st.empty()
    pct_container = st.empty()

    total_duration = random.randint(30, 60)  # Random 30-60 seconds
    # total_duration = 1
    update_interval = 0.5
    total_steps = int(total_duration / update_interval)

    analyzer_stages = get_analyzer().get_processing_stages()

    for step in range(total_steps + 1):
        elapsed = step * update_interval
        current_pct = min(1.0, elapsed / total_duration)

        progress_container.markdown(
            create_custom_progress_bar(current_pct, lang),
            unsafe_allow_html=True,
        )

        current_stage = next(
            (s for s in analyzer_stages
             if s.get('percent_start', 0) <= current_pct * 100 < s.get('percent_end', 100)),
            analyzer_stages[0] if analyzer_stages else None
        )

        if current_stage:
            stage_label = current_stage.get('label_en', current_stage.get('label', 'Processing...')) if lang == 'en' else current_stage.get('label', 'Processing...')
            pct_container.markdown(
                f"<div class='pct-display'>"
                f"{int(current_pct * 100)}% — {stage_label}"
                f"</div>",
                unsafe_allow_html=True,
            )

        time.sleep(update_interval)

    progress_container.markdown(
        create_custom_progress_bar(1.0, lang),
        unsafe_allow_html=True,
    )
    pct_container.empty()


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

    # ── Inquiries Showcase Section ──
    st.markdown(f"""
    <div style="display:flex;justify-content:center;align-items:center;flex-direction:column;padding:2.5rem 0 1rem;direction:{DIR};">
        <div class="section-label">{tx['section_label']}</div>
        <h2 class="section-title">{tx['section_title']}</h2>
        <div class="section-ornament">
            <span class="ornament-line"></span>
            <span class="ornament-diamond">◆</span>
            <span class="ornament-line right"></span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Main feature card
    st.markdown(f"""
    <div class="complaints-showcase">
        <div class="complaints-feature-card">
            <div class="title">📋 {tx['inq_card_title']}</div>
            <div class="desc">{tx['inq_card_desc']}</div>
            <div style="margin-top: 1.8rem; display: flex; gap: 0.8rem; flex-wrap: wrap; justify-content: center;">
                <span class="use-case-tag inquiries-tag">{tx['inq_tag1']}</span>
                <span class="use-case-tag inquiries-tag">{tx['inq_tag2']}</span>
                <span class="use-case-tag inquiries-tag">{tx['inq_tag3']}</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Feature Highlights ──
    st.markdown(f"""
    <div style="display:flex;justify-content:center;align-items:center;flex-direction:column;padding:2rem 0 1rem;direction:{DIR};">
        <div class="section-label">{tx['how_label']}</div>
    </div>
    """, unsafe_allow_html=True)

    # Feature cards row
    feat_col1, feat_col2, feat_col3 = st.columns([1, 1, 1], gap="medium")
    with feat_col1:
        st.markdown(f"""
        <div class="feature-card">
            <div class="feature-icon-wrap">🔍</div>
            <div class="feature-title">{tx['feat1_title']}</div>
            <div class="feature-desc">{tx['feat1_desc']}</div>
        </div>
        """, unsafe_allow_html=True)

    with feat_col2:
        st.markdown(f"""
        <div class="feature-card">
            <div class="feature-icon-wrap">📊</div>
            <div class="feature-title">{tx['feat2_title']}</div>
            <div class="feature-desc">{tx['feat2_desc']}<br><br></div>
        </div>
        """, unsafe_allow_html=True)

    with feat_col3:
        st.markdown(f"""
        <div class="feature-card">
            <div class="feature-icon-wrap">💡</div>
            <div class="feature-title">{tx['feat3_title']}</div>
            <div class="feature-desc">{tx['feat3_desc']}</div>
        </div>
        """, unsafe_allow_html=True)

    # ── How It Works ──
    st.markdown(f"""
    <div style="display:flex;justify-content:center;align-items:center;flex-direction:column;padding:2rem 0 1rem;direction:{DIR};">
        <h3 style="font-size: 2rem; font-weight: 700; color: {TEXT}; margin: 2rem 0 0.5rem;">{tx['how_title']}</h3>
        <div class="section-ornament">
            <span class="ornament-line"></span>
            <span class="ornament-diamond">◆</span>
            <span class="ornament-line right"></span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    step_col1, step_col2, step_col3 = st.columns([1, 1, 1], gap="medium")
    with step_col1:
        st.markdown(f"""
        <div class="step-card">
            <div class="step-number">1</div>
            <div class="step-icon">📤</div>
            <div class="step-title">{tx['step1_title']}</div>
            <div class="step-desc">{tx['step1_sub']}</div>
        </div>
        """, unsafe_allow_html=True)

    with step_col2:
        st.markdown(f"""
        <div class="step-card">
            <div class="step-number">2</div>
            <div class="step-icon">⚙️</div>
            <div class="step-title">{tx['step2_title']}</div>
            <div class="step-desc">{tx['step2_sub']}</div>
        </div>
        """, unsafe_allow_html=True)

    with step_col3:
        st.markdown(f"""
        <div class="step-card">
            <div class="step-number">3</div>
            <div class="step-icon">📥</div>
            <div class="step-title">{tx['step3_title']}</div>
            <div class="step-desc">{tx['step3_sub']}</div>
        </div>
        """, unsafe_allow_html=True)

    # ── CTA Button ──
    st.markdown('<div class="cta-section">', unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button(tx['btn_inq'], key="cta_inquiries", use_container_width=True):
            if st.session_state.authenticated:
                st.session_state.page = 'inquiries'
                st.rerun()
            else:
                st.session_state.show_login = True
                st.session_state.pending_page = 'inquiries'
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

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
    DIR = 'rtl' if lang == 'ar' else 'ltr'

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
            print(f"[Upload-INQ] Stored {len(uploaded_files)} file(s) in session state")

        files_to_display = st.session_state.get('uploaded_file', []) if uploaded_files or st.session_state.get('uploaded_file') else []

        if files_to_display:
            for uploaded_file in files_to_display:
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
                        for uploaded_file in files_to_display:
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

            try:
                files_to_process = st.session_state.get('uploaded_file', [])
                if not files_to_process:
                    st.error("❌ No files to process. Please upload files first.")
                    st.session_state.processing = False
                    st.rerun()

                report = process_with_analyzer(files_to_process, lang)
                st.session_state.processing = False
                st.session_state.completed = True

                if report:
                    st.session_state.report_data = report

                    # Check for errors in the report itself
                    if report.get('success') is False:
                        st.session_state.analysis_error = f"Pipeline error: {report.get('error', 'Unknown error')}"
                    else:
                        st.session_state.analysis_error = None

                    # Handle generated output files (from RealAnalyzer)
                    print(f"[Main] Report: success={report.get('success')}, excel={report.get('excel_path')}, word={report.get('word_path')}, word_en={report.get('word_path_en')}")
                    if report.get('success') and report.get('excel_path') and report.get('word_path'):
                        _handle_generated_outputs(report.get('excel_path'), report.get('word_path'), lang, word_path_en=report.get('word_path_en'))
                else:
                    st.session_state.analysis_error = "Analysis returned no data"
            except Exception as e:
                st.session_state.processing = False
                st.session_state.completed = False
                st.session_state.analysis_error = f"Analysis failed: {str(e)}"
                import traceback
                st.session_state.error_traceback = traceback.format_exc()
                print(f"[Main] Exception: {str(e)}\n{traceback.format_exc()}")

            st.markdown('</div>', unsafe_allow_html=True)
            st.rerun()

    else:
        if st.session_state.get('analysis_error'):
            st.markdown(f"""
            <div class="error-panel">
                <div style="font-size:1.8rem;margin-bottom:0.4rem;">❌</div>
                <div style="font-weight:bold;font-size:1.1rem;">Analysis Failed</div>
            </div>
            """, unsafe_allow_html=True)
            st.error(f"**Error:** {st.session_state.analysis_error}")
            if st.session_state.get('error_traceback'):
                with st.expander("📋 Technical Details"):
                    st.code(st.session_state.error_traceback, language='python')

            st.markdown('<div style="max-width:820px;margin:2.5rem auto 0;">', unsafe_allow_html=True)
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button(tx['btn_reset'], use_container_width=True, key="inq_reset_error"):
                    st.session_state.uploaded_file = None
                    st.session_state.processing = False
                    st.session_state.completed = False
                    st.session_state.analysis_error = None
                    st.session_state.error_traceback = None
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="success-panel">
                <div style="font-size:1.8rem;margin-bottom:0.4rem;">✅</div>
                <div class="success-title">{tx['success_title_inq']}</div>
                <div class="success-sub">{tx['success_sub_inq']}</div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown('<div style="max-width:900px;margin:2rem auto;">', unsafe_allow_html=True)
            display_report_tabs(lang, flow_type='inquiries')
            st.markdown('</div>', unsafe_allow_html=True)

            # Download button
            output_files = st.session_state.get('output_files', {})
            excel_path = output_files.get('excel_path')
            word_path = output_files.get('word_path')

            st.markdown('<div style="max-width:820px;margin:2rem auto 0;">', unsafe_allow_html=True)
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                zip_data = create_download_zip(flow_type='inquiries')
                if zip_data:
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
        if st.session_state.page in ('inquiries',):
            st.markdown('<div class="nav-back-wrap">', unsafe_allow_html=True)
            if st.button(T[lang]['nav_back'], key="nav_back"):
                st.session_state.page          = 'landing'
                st.session_state.uploaded_file = None
                st.session_state.processing    = False
                st.session_state.completed     = False
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    with col_r:
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

        st.markdown('<div style="direction: ltr; display: flex; justify-content: center;">', unsafe_allow_html=True)

        is_arabic = st.toggle(
            "عربي" if lang == "ar" else "Arabic",
            value=st.session_state.get("language", "en") == "ar",
            key="lang_toggle",
            help="Toggle to switch between English and Arabic"
        )

        st.markdown('</div>', unsafe_allow_html=True)

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

    st.markdown(f"""
    <div style="height:1px;background:linear-gradient(90deg,transparent,{BORDER_G2},transparent);
                margin-bottom:0;"></div>
    """, unsafe_allow_html=True)

    if st.session_state.show_login:
        show_login_modal(lang)
        st.stop()

    if st.session_state.page == 'landing':
        landing_page(lang)
    elif st.session_state.page == 'inquiries':
        inquiries_page(lang)


if __name__ == "__main__":
    main()
