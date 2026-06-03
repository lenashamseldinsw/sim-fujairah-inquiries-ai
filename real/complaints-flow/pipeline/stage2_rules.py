"""
STAGE 2: Rule-based Classifier (Complaints Pipeline)

Classifies complaints into 6 sub-categories using:
  1. الحالة == 'طلب مرفوض' → مكررة (مرفوضة)
  2. الخدمة direct service → category mapping (high confidence)
  3. Text signals on الخدمة == 'أخرى' (medium confidence)
  4. Default to LLM queue

Low-confidence cases are queued for Stage 3 (LLM classifier).
"""

import re
import pandas as pd
from typing import Tuple
from .state import PipelineState, CaseRow
from .json_utils import extract_methodology_context

LOW_CONFIDENCE_THRESHOLD = 0.75

# Complaint sub-categories (6 types only)
ALL_COMPLAINT_SUB_CATEGORIES = [
    'شكاوى مكررة (مرفوضة)',
    'شكاوى بلا تصنيف خدمي ("أخرى")',
    'شكاوى على الخدمات المرورية',
    'شكاوى أمنية وجنائية',
    'شكاوى شهادات وتصاريح',
    'شكاوى خارج الاختصاص والأخرى',
]

# Direct mapping from الخدمة field value → output complaint sub-category
# Based on actual data analysis from Complaints_2025.xlsx
SERVICE_TO_CATEGORY = {
    # Criminal/Security
    'فتح البلاغات الجنائية': 'شكاوى أمنية وجنائية',
    'الاستعلام عن شكوى': 'شكاوى أمنية وجنائية',
    'تنظيم الزيارات بأنواعها لذوي النزلاء والمحاميين والسفارات': 'شكاوى أمنية وجنائية',
    'فتح بلاغ لإثبات حالة': 'شكاوى أمنية وجنائية',
    'استقبال الحالات الاجتماعية': 'شكاوى أمنية وجنائية',

    # Traffic
    'فتح البلاغات المرورية': 'شكاوى على الخدمات المرورية',
    'إعتراض على المخالفات المرورية': 'شكاوى على الخدمات المرورية',
    'دفع المخالفات المرورية': 'شكاوى على الخدمات المرورية',
    'تحديث الرمز المروري': 'شكاوى على الخدمات المرورية',
    'طلب تحويل المخالفات إلى رخصة القيادة': 'شكاوى على الخدمات المرورية',
    'تحديث بيانات الملف المروري': 'شكاوى على الخدمات المرورية',
    'توصيل رخصة القيادة': 'شكاوى على الخدمات المرورية',
    'تجديد ملكية مركبة': 'شكاوى على الخدمات المرورية',
    'عرقلة حركة السير': 'شكاوى على الخدمات المرورية',
    'التحقق من المخالفات المرورية': 'شكاوى على الخدمات المرورية',
    'تغيير بيان في بطاقة ملكية المركبة': 'شكاوى على الخدمات المرورية',

    # Certificates/Permits
    'شهادة حسن سيرة وسلوك - بحث الحالة الجنائية': 'شكاوى شهادات وتصاريح',
    'طلب ترخيص سلاح': 'شكاوى شهادات وتصاريح',
    'طلب الموافقة على ترخيص سلاح (سلاح جديد)': 'شكاوى شهادات وتصاريح',

    # Unclassified
    'التحقق من المعاملات المالية': 'شكاوى بلا تصنيف خدمي ("أخرى")',
    'تحديث البيانات الشخصية - ICP': 'شكاوى بلا تصنيف خدمي ("أخرى")',
    'التحقق من حالة الطلب': 'شكاوى بلا تصنيف خدمي ("أخرى")',

    # Route 'أخرى' to LLM
    'أخرى': None,  # → LLM queue
}


def normalize_arabic(text: str) -> str:
    """Normalize Arabic text for matching (remove diacritics, etc)."""
    if not text:
        return ""
    # Remove diacritics
    text = re.sub(r'[ً-ٟ]', '', text)
    return text.lower().strip()


def classify_case(case_row: dict, additional_oor_keywords: list = None) -> Tuple[str, str, str, float]:
    """
    Classify a single complaint into one of 6 sub-categories using sophisticated rules.

    Matches the inquiries flow classification sophistication while handling 6 complaint categories.

    Classification priority:
      1. الحالة == 'طلب مرفوض' → always مكررة (مرفوضة)
      2. الخدمة exact match in SERVICE_TO_CATEGORY → high confidence
      3. Priority text signals (traffic disputes, security reports, etc.)
      4. Resolution-based classification
      5. Text signals on الخدمة == 'أخرى' (medium confidence)
      6. Out-of-jurisdiction detection
      7. Default → LLM queue

    Args:
        case_row: Dict of case data
        additional_oor_keywords: Optional list of additional out-of-jurisdiction keywords from methodology

    Returns: (top_level, sub_category, reason, confidence)
    top_level is always 'شكوى'.
    """
    if additional_oor_keywords is None:
        additional_oor_keywords = []
    # FIX: normalize None status to empty string (str(None) = "None" breaks classification)
    _s = case_row.get('الحالة', '')
    status = '' if (_s is None or (isinstance(_s, float) and pd.isna(_s))) else str(_s).strip()
    service = str(case_row.get('الخدمة', '')).strip()
    title = str(case_row.get('تفاصيل_الطلب', ''))
    resolution = str(case_row.get('الحل', ''))

    title_norm = normalize_arabic(title)
    res_norm = normalize_arabic(resolution)

    # REMOVED: PRIORITY 0 preservation of raw نوع_الشكوى
    # Why: This caused case 211919 to be locked into wrong classification (خارج الاختصاص)
    # when it should be (بلا تصنيف خدمي) based on actual content analysis.
    # The raw field can be stale or incorrectly pre-populated from prior runs.
    # Classification should be determined by current case content, not cached raw values.

    # --- PRIORITY 1: Formal rejection flag ---
    if status == 'طلب مرفوض':
        return ('شكوى', 'شكاوى مكررة (مرفوضة)',
                'الحالة = طلب مرفوض', 0.95)

    # Also catch "مكرر" keyword in resolution text (backup for edge cases)
    if any(normalize_arabic(k) in res_norm
           for k in ['مكرر', 'مكررة', 'شكوى مكررة', 'طلب مكرر']):
        return ('شكوى', 'شكاوى مكررة (مرفوضة)',
                'كلمة مكرر في نص الحل', 0.90)

    # --- PRIORITY 2: Direct service → category lookup ---
    # Highest confidence when service field exactly matches our taxonomy
    mapped = SERVICE_TO_CATEGORY.get(service)
    if mapped is not None:
        return ('شكوى', mapped,
                f'تطابق مباشر لحقل الخدمة: {service}', 0.92)

    # --- PRIORITY 3: Traffic Dispute Signals (similar to inquiries logic) ---
    # Traffic fine disputes require explicit contest language
    arabic_contest = normalize_arabic('اعتراض') in title_norm
    english_contest = any(k in title_norm for k in ['incorrect', 'dispute', 'contest', 'disagree', 'wrong fine', 'objection'])
    has_contest = arabic_contest or english_contest

    arabic_fine = (normalize_arabic('مخالفة') in title_norm
               or normalize_arabic('مخالفه') in title_norm
               or normalize_arabic('مخالفات') in title_norm)
    english_fine = any(k in title.lower() for k in ['fine', 'traffic fine', 'speeding', 'violation', 'ticket'])
    has_fine = arabic_fine or english_fine

    if has_contest and has_fine:
        return ('شكوى', 'شكاوى على الخدمات المرورية',
                'اعتراض صريح على مخالفة مرورية', 0.90)

    # --- PRIORITY 3b: Disputed Fine (customer asserts innocence without contest words) ---
    disputed_fine_signals_ar = [
        'لم أكون متواجد', 'لم اكن متواجد', 'لم أكن في', 'لم اكن في',
        'صورة المخالفة', 'رقم اللوحة خاطئ', 'لوحة غير لوحتي',
        'خطأ في اللوحة', 'ليست سيارتي', 'ليست مركبتي',
        'مخالفة بشكل خاطئ', 'تحرير مخالفة بشكل خاطئ',
        'عدم خصم', 'نقاط خاطئة',
    ]
    disputed_fine_signals_en = [
        'not my vehicle', 'not my car', 'i was not in', 'i did not go to',
        'was not there', 'wrong plate', 'wrong car', 'by mistake',
    ]
    has_arabic_dispute = any(k in title_norm for k in [normalize_arabic(w) for w in disputed_fine_signals_ar])
    has_english_dispute = any(k in title.lower() for k in disputed_fine_signals_en)
    if (has_arabic_dispute or has_english_dispute) and has_fine:
        return ('شكوى', 'شكاوى على الخدمات المرورية',
                'صورة المركبة في الإشعار تُظهر مركبة مختلفة — خطأ في مطابقة اللوحات', 0.87)

    # --- PRIORITY 4: Security/Criminal Reports (filing, scam, fraud, etc.) ---
    # Matches inquiries Priority 2
    report_keywords_ar = ['فتح بلاغ', 'تقديم بلاغ', 'سرقة', 'حادث', 'بلاغ جنائي',
                          'تعرضت للضرب', 'تعرضي للضرب', 'اعتداء', 'نصب', 'احتيال']
    report_keywords_en = ['i got scammed', 'scammed', 'fraud', 'fake iphone', 'took money from me',
                          'he took', 'she took', 'stolen', 'assault', 'attacked', 'robbery']
    has_ar_report = any(k in title_norm for k in [normalize_arabic(w) for w in report_keywords_ar])
    has_en_report = any(k in title.lower() for k in report_keywords_en)
    if has_ar_report or has_en_report:
        return ('شكوى', 'شكاوى أمنية وجنائية',
                'بلاغ أمني أو جنائي مباشر', 0.89)

    # --- PRIORITY 5: Weapon/Certificate Permits ---
    # Matches inquiries Priority 4
    weapons_keywords = ['تصريح سلاح', 'ذخيرة', 'ترخيص سلاح', 'طلب سلاح']
    if any(k in title_norm for k in [normalize_arabic(w) for w in weapons_keywords]):
        return ('شكوى', 'شكاوى شهادات وتصاريح',
                'طلب تصريح سلاح أو ترخيص', 0.89)

    # Certificate/document signals
    cert_kw = ['حسن سيرة', 'شهادة', 'وثيقة', 'تصريح', 'جواز', 'إقامة']
    if any(k in title_norm for k in [normalize_arabic(w) for w in cert_kw]):
        return ('شكوى', 'شكاوى شهادات وتصاريح',
                'إشارات شهادات/تصاريح في الوصف', 0.82)

    # --- PRIORITY 6: Service Delivery Issues ---
    # Service not received
    delivery_keywords = [
        'لم استلم', 'لم أستلم', 'لم تصلني', 'لم يتم التسليم',
        'لم تصل الرخصة', 'لم تصل الرخصه', 'لم يتم التوصيل',
        'حتى الان لم', 'حتى الآن لم', 'لم يتم ارسال', 'لم يرسل',
    ]
    vehicle_keywords = ['رخصة', 'مركبة', 'مركبه', 'ملكية', 'لوحة']
    if any(k in title_norm for k in [normalize_arabic(w) for w in delivery_keywords]):
        if has_fine or any(k in title_norm for k in [normalize_arabic(w) for w in vehicle_keywords]):
            return ('شكوى', 'شكاوى على الخدمات المرورية',
                    'خدمة مرورية لم تُستقبل', 0.81)

    # --- PRIORITY 7: System/Technical Errors ---
    # Matches inquiries Priority 6
    system_keywords = [
        'عطل', 'خطأ في النظام', 'خصم مرتين', 'لم يصدر', 'خطأ تقني',
        'دفع مرتين', 'دفع مبلغ مرتين', 'خصمت مرتين',
        'بدون اصدار', 'دون اصدار',
    ]
    user_error_signals = ['أجريت إجراء خاطئ', 'إجراء غير صحيح', 'بدلاً من', 'اجريت اجراء خاطئ']
    has_user_error = any(normalize_arabic(k) in title_norm for k in user_error_signals)
    if not has_user_error and any(k in title_norm for k in [normalize_arabic(w) for w in system_keywords]):
        return ('شكوى', 'شكاوى بلا تصنيف خدمي ("أخرى")',
                'خلل تقني أو خطأ في النظام', 0.80)

    # --- PRIORITY 8: Resolution-Based Classification ---
    # Analyze resolution text to determine complaint category (similar to inquiries Priority 9)

    # Fine-related resolution keywords
    fine_confirmed_valid_keywords = [
        'المخالفة صحيحة', 'المخالفات صحيحة', 'تم التحقق',
        'مخالفة قانونية', 'النقاط صحيحة', 'صحت المخالفة',
        'تجاوز الحد', 'ثبت ارتكاب',
    ]
    fine_found_erroneous_keywords = [
        'لا توجد مخالفة', 'تم الإلغاء', 'خطأ في البيانات',
        'لم تدخل', 'ليست مركبته', 'خطأ في اللوحة',
        'إلغاء المخالفة',
    ]

    fine_confirmed_valid = any(k in res_norm for k in [normalize_arabic(w) for w in fine_confirmed_valid_keywords])
    fine_found_erroneous = any(k in res_norm for k in [normalize_arabic(w) for w in fine_found_erroneous_keywords])

    if (has_fine or arabic_fine) and fine_confirmed_valid:
        return ('شكوى', 'شكاوى على الخدمات المرورية',
                'مخالفة مؤكدة من نص الحل', 0.84)

    if (has_fine or arabic_fine) and fine_found_erroneous:
        return ('شكوى', 'شكاوى على الخدمات المرورية',
                'مخالفة خاطئة من نص الحل', 0.84)

    # --- PRIORITY 9: Out-of-Jurisdiction Detection ---
    # Include both built-in keywords and any from methodology
    oor_kw = ['ليس من اختصاص', 'خارج الاختصاص', 'وزارة العمل',
              'جهة أخرى', 'تحويل أموال للنزلاء', 'السجن', 'المنشأة العقابية',
              'خارج نطاق', 'جهة حكومية أخرى']
    oor_kw.extend(additional_oor_keywords)
    if any(k in res_norm for k in [normalize_arabic(w) for w in oor_kw]):
        return ('شكوى', 'شكاوى خارج الاختصاص والأخرى',
                'الحل يشير إلى خارج الاختصاص', 0.85)

    # --- PRIORITY 10: Text Signals for Unclassified (service == 'أخرى') ---
    # Only applied when الخدمة is 'أخرى' — enhanced with more keywords

    # Traffic signals (expanded)
    traffic_kw = ['مخالفة', 'مخالفه', 'رخصة', 'رخصه', 'مركبة', 'مركبه',
                  'تجديد', 'مروري', 'لوحة', 'لوحه', 'سائق', 'تحويل ملف',
                  'fine', 'traffic', 'license', 'vehicle', 'violation', 'speeding']
    if any(k in title_norm for k in [normalize_arabic(w) for w in traffic_kw]) or \
       any(k in title.lower() for k in ['fine', 'traffic', 'license', 'vehicle', 'violation']):
        return ('شكوى', 'شكاوى على الخدمات المرورية',
                'إشارات مرورية في الوصف (خدمة: أخرى)', 0.76)

    # Criminal/security signals (expanded)
    security_kw = ['بلاغ', 'جنائي', 'اعتداء', 'سرقة', 'احتيال', 'نصب',
                   'توقيف', 'مباحث', 'نيابة', 'حفظ البلاغ', 'اعتقال',
                   'scam', 'assault', 'stolen', 'fraud', 'crime']
    if any(k in title_norm for k in [normalize_arabic(w) for w in security_kw]) or \
       any(k in title.lower() for k in ['scam', 'assault', 'stolen', 'fraud']):
        return ('شكوى', 'شكاوى أمنية وجنائية',
                'إشارات أمنية/جنائية في الوصف (خدمة: أخرى)', 0.76)

    # Certificate/permit signals
    cert_kw = ['حسن سيرة', 'شهادة', 'وثيقة', 'تصريح', 'جواز', 'إقامة',
               'ترخيص سلاح', 'سلاح']
    if any(k in title_norm for k in [normalize_arabic(w) for w in cert_kw]):
        return ('شكوى', 'شكاوى شهادات وتصاريح',
                'إشارات شهادات/تصاريح في الوصف (خدمة: أخرى)', 0.75)

    # --- DEFAULT: route to LLM (Stage 3) ---
    # This covers 'أخرى' cases with no clear text signal or unmapped services
    return ('شكوى', 'شكاوى بلا تصنيف خدمي ("أخرى")',
            'تصنيف افتراضي — يحتاج مراجعة LLM', 0.40)


def run_stage2(state: PipelineState) -> PipelineState:
    """
    Stage 2: Rule-based classifier for complaints.

    Input: state with raw_df
    Output: state with rule_classified and llm_queue
    """
    if state.raw_df is None:
        raise ValueError("raw_df not populated. Run Stage 1 first.")

    # DIAGNOSTIC: Inspect date_closed column types and values before processing
    print("[Stage2] DIAGNOSTIC: Inspecting تاريخ_الإغلاق column...")
    date_col = state.raw_df.get('تاريخ_الإغلاق', None)
    if date_col is not None:
        type_counts = {}
        for val in date_col:
            vtype = type(val).__name__
            type_counts[vtype] = type_counts.get(vtype, 0) + 1
        print(f"[Stage2]   Value type distribution: {type_counts}")

        # Show first few values and their pd.isna() status
        print("[Stage2]   Sample values (case#, raw_value, type, pd.isna()):")
        for idx, (i, row) in enumerate(state.raw_df.iterrows()):
            if idx >= 5:  # Show first 5
                break
            case_num = str(row.get('رقم_الطلب', ''))
            val = row.get('تاريخ_الإغلاق', '')
            vtype = type(val).__name__
            is_na = pd.isna(val)
            print(f"[Stage2]     {case_num}: {repr(val)} (type={vtype}, pd.isna={is_na})")

    # Extract additional out-of-jurisdiction keywords from methodology if present
    additional_oor_kw = []
    if state.complaints_methodology:
        methodology_context = extract_methodology_context(
            state.complaints_methodology,
            ["5_procedures.5_3_classification"]
        )
        classification_section = methodology_context.get("5_3_classification", {})
        for complaint_type in classification_section.get("types", []):
            if complaint_type.get("type") == "الشكوى المعقدة":
                desc = complaint_type.get("description", "")
                # Extract keywords: "تعدد مقدمي الخدمة" and "متداخلة إجراءاتها مع أكثر من جهة"
                if "تعدد مقدمي الخدمة" in desc:
                    additional_oor_kw.append("تعدد مقدمي الخدمة")
                if "متداخلة إجراءاتها مع أكثر من جهة" in desc:
                    additional_oor_kw.append("متداخلة")
                    additional_oor_kw.append("أكثر من جهة")
        if additional_oor_kw:
            print(f"[Stage2] Loaded {len(additional_oor_kw)} OOR keywords from methodology")

    rule_classified = []
    llm_queue = []
    rejected_count = 0
    diagnostic_count = 0  # Limit diagnostic output to first 50 cases

    for idx, row in state.raw_df.iterrows():
        top_level, sub_classification, reason, confidence = classify_case(row.to_dict(), additional_oor_kw)

        # Clean department name to match stage1 processing (remove "الفجيرة - " prefix)
        dept_raw = str(row.get('الإدارة_العامة', '') or row.get('الإداره_العامة', '')).strip()
        dept_clean = re.sub(r'^الفجيرة\s*-\s*', '', dept_raw).strip()

        # FIX: Extract and normalize case_status (None → '')
        _s = row.get('الحالة', '')
        case_status = '' if (_s is None or (isinstance(_s, float) and pd.isna(_s))) else str(_s).strip()

        # TASK 2 FIX: Handle date_closed serialization properly
        # Must preserve datetime objects as ISO strings (not datetime objects)
        # to avoid loss during JSON serialization/deserialization in llm_queue path
        date_closed_raw = row.get('تاريخ_الإغلاق', '')
        case_num = str(row.get('رقم_الطلب', ''))

        # DIAGNOSTIC: Log the raw value and its type for date_closed
        raw_type = type(date_closed_raw).__name__
        is_na = pd.isna(date_closed_raw)

        if pd.isna(date_closed_raw):
            date_closed_value = ""
        else:
            # Convert datetime/Timestamp to ISO string explicitly (prevents Pydantic coercion loss)
            if hasattr(date_closed_raw, 'isoformat'):
                date_closed_value = date_closed_raw.isoformat()
            else:
                date_closed_value = str(date_closed_raw)

            # Strip and validate
            date_closed_str = date_closed_value.strip()
            # Check for 'nan'/'nat'/'none' strings or whitespace-only
            if date_closed_str.lower() in ('nan', 'nat', 'none', ''):
                date_closed_value = ""
            else:
                date_closed_value = date_closed_str

        # DIAGNOSTIC: Log EVERY case with date processing details (first 50 cases)
        if diagnostic_count < 50:
            str_raw = str(date_closed_raw) if date_closed_raw is not None else 'None'
            print(
                f"[Stage2] Case {case_num}: "
                f"raw={repr(date_closed_raw)[:50]} (type={raw_type}, pd.isna={is_na}, str={repr(str_raw)[:30]}) "
                f"→ value={repr(date_closed_value)[:30]}"
            )
            diagnostic_count += 1

        # Also log if we're losing a non-empty date
        if date_closed_raw is not None and not pd.isna(date_closed_raw):
            str_raw = str(date_closed_raw).strip()
            if str_raw and str_raw.lower() not in ('nan', 'nat', 'none', '') and not date_closed_value:
                print(
                    f"[Stage2] ⚠ LOST DATE: Case {case_num} had date in raw but lost it — "
                    f"raw={repr(date_closed_raw)} → value={repr(date_closed_value)}"
                )

        case = CaseRow(
            case_number=str(row.get('رقم_الطلب', '')),
            case_title=str(row.get('تفاصيل_الطلب', '')),
            date_opened=str(row.get('تاريخ_الإنشاء', '')),
            date_closed=date_closed_value,
            case_channel=str(row.get('قناة_تقديم_الخدمة', '')).strip(),
            description=str(row.get('تفاصيل_الطلب', '')),
            resolution_response=str(row.get('الحل', '')),
            severity_raw=str(row.get('شدة_الطلب', '')),
            case_type=str(row.get('نوع_المكالمة', '')),  # always 'شكاوى' — keep for audit
            service_name=str(row.get('الخدمة_الرئيسية', '') or row.get('الخدمة_الرئيسيه', '')),
            actual_contact_type=top_level,
            classification_reason=reason,
            confidence=confidence,
            misclassification='OK',
            top_level=top_level,
            sub_classification=sub_classification,
            admin=dept_clean,
            # New complaints fields
            severity=str(row.get('شدة_الطلب', '')),
            complaint_category=sub_classification,
            resolved_by=str(row.get('تم_الحل_بواسطة', '')),
            owner=str(row.get('المالك', '')).strip(),  # CRITICAL: must be populated for stage6
            applicant_name=str(row.get('اسم_مقدم_الطلب', '')),
            nationality=str(row.get('الجنسية', '')),
            id_number=str(row.get('رقم_الهوية', '')),
            mobile=str(row.get('الهاتف_الجوال', '')),
            employee_number=str(row.get('الرقم_الوظيفي', '')),
            sla_closed_on_time=str(row.get('إغلاق_الطلب_خلال_الوقت_المحدد', '')),
            emirate=str(row.get('الإمارة', '')),
            case_status=case_status,  # Use normalized status (None → '') from classify_case logic
        )

        # Track rejection
        if 'مكررة' in (sub_classification or ''):
            rejected_count += 1

        if confidence < LOW_CONFIDENCE_THRESHOLD:
            # Queue for LLM review
            llm_queue.append(case.model_dump())
        else:
            rule_classified.append(case)

    state.rule_classified = rule_classified
    state.llm_queue = llm_queue
    state.zero_rejection_flag = (rejected_count == 0)

    # DIAGNOSTIC: Summary of closure status after Stage 2
    closed_count = sum(1 for c in rule_classified if c.date_closed and str(c.date_closed).strip())
    open_count = sum(1 for c in rule_classified if not c.date_closed or not str(c.date_closed).strip())

    print(
        f"[Stage2] CLOSURE SUMMARY: {len(rule_classified)} rule_classified, "
        f"{closed_count} closed ({100*closed_count/len(rule_classified):.1f}%), "
        f"{open_count} open"
    )

    # Also check llm_queue for comparison
    if llm_queue:
        llm_closed = sum(1 for c in llm_queue if c.get('date_closed') and str(c.get('date_closed')).strip())
        llm_open = len(llm_queue) - llm_closed
        print(
            f"[Stage2] LLM_QUEUE: {len(llm_queue)} cases, "
            f"{llm_closed} closed, {llm_open} open"
        )

    return state
