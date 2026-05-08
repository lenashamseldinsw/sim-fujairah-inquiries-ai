"""
STAGE 2: Rule-based Classifier

Applies priority decision tree to classify cases using two-level Fujairah Police taxonomy.
Low-confidence cases are queued for Stage 3 (LLM classifier).

Confidence threshold: 0.75 (tunable)
Taxonomy: 4 top-level types with domain-specific sub-classifications.
"""

import re
from typing import Tuple
from .state import PipelineState, CaseRow

# Tunable confidence threshold — adjust based on Stage 2 test results
LOW_CONFIDENCE_THRESHOLD = 0.75

# Two-level taxonomy for Fujairah Police
TOP_LEVEL_TYPES = {
    'complaint': 'شكوى',
    'inquiry': 'استفسار',
    'request': 'طلب',
    'praise': 'شكر وثناء',
}

SUB_CLASSIFICATIONS = {
    'شكوى': [
        'تقديم بلاغ أمني أو مروري',
        'اعتراض على مخالفة مرورية',
        'شكوى عامة',
        'شكوى عن مخالفة مشكوك فيها',
        'شكوى على خطأ تقني أو في النظام',
        'شكوى عن عدم استلام الخدمة',
        'شكوى على عدم الرد',
        'شكوى على تأخر المعالجة',
    ],
    'طلب': [
        'طلب توصيل أو استلام',
        'طلب خدمة عام',
        'طلب تصريح سلاح أو ترخيص',
        'طلب تجديد رخصة أو ملكية',
        'طلب إصدار شهادة أو وثيقة',
        'طلب سداد مخالفة',
        'طلب فتح ملف أو بلاغ',
        'طلب تعديل أو تحديث بيانات',
        'طلب تصريح خاص',
        'متابعة طلب مقدم',
    ],
    'استفسار': [
        'استفسار عام',
        'استفسار عن الرخص والمركبات',
        'استفسار عن الإجراءات والمتطلبات',
        'استفسار تقني',
        'استفسار عن البلاغات الأمنية',
        'استفسار عن الأسلحة والتراخيص',
    ],
    'شكر وثناء': [
        'شكر وتقدير عام',
    ],
}


def normalize_arabic(text: str) -> str:
    """Normalize Arabic text for matching (remove diacritics, etc)."""
    if not text:
        return ""
    # Remove diacritics
    text = re.sub(r'[ً-ٟ]', '', text)
    return text.lower().strip()


def classify_case(case_row: dict) -> Tuple[str, str, str, float]:
    """
    Classify a single case using the priority decision tree.

    Args:
        case_row: Dict with case data

    Returns:
        (top_level, sub_classification, reason, confidence)

    CLASSIFICATION RULE D — Resolution reveals the true nature:
    Always consider the Resolution Response (الحل) when classifying. If resolution
    shows a refund issued, system error corrected, service failure acknowledged, or
    escalation required to fix a problem, classify as شكوى (complaint) regardless of
    neutral phrasing in the description. Service failure + resolution = complaint.
    """
    # BUG FIX 1: Read from تفاصيل_الطلب (actual description), not نوع_المكالمة (CRM label)
    title = str(case_row.get('تفاصيل_الطلب', ''))
    resolution = str(case_row.get('الحل', ''))
    case_type = str(case_row.get('التصنيف_الفرعي', ''))
    crm_label = str(case_row.get('نوع_المكالمة', ''))  # Keep for fallback only

    title_norm = normalize_arabic(title)
    res_norm = normalize_arabic(resolution)
    case_type_norm = normalize_arabic(case_type)

    # --- PRIORITY 1: Traffic Fine Disputes (Contesting a fine, not filing) ---
    # Require اعتراض or خطأ alongside مخالفة to avoid shadowing "filing a report" cases
    # Also check for English equivalents: incorrect, dispute, contest, disagree, wrong, object
    arabic_contest = any(k in title_norm for k in [normalize_arabic(w) for w in ['اعتراض', 'خطأ في اللوحة']])
    english_contest = any(k in title_norm for k in ['incorrect', 'dispute', 'contest', 'disagree', 'wrong fine', 'objection'])
    has_contest = arabic_contest or english_contest

    # Bug #2: also catch informal spelling مخالفه and English ticket
    arabic_fine = normalize_arabic('مخالفة') in title_norm or normalize_arabic('مخالفه') in title_norm
    english_fine = any(k in title.lower() for k in ['fine', 'traffic fine', 'speeding', 'violation', 'ticket'])
    has_fine = arabic_fine or english_fine

    if has_contest and has_fine:
        return 'شكوى', 'اعتراض على مخالفة مرورية', 'اعتراض صريح على مخالفة مرورية', 0.92

    # --- PRIORITY 1b: Disputed Fine — Customer Was Not Present / Wrong Vehicle ---
    # Catches cases where customer asserts they didn't commit the fine (wrong vehicle, not in emirate,
    # fine issued by mistake) without using the exact "contest/objection" words of Priority 1.
    # تحرير مخالفة بشكل خاطئ is handled here, NOT in Priority 2, because it is always a disputed fine.
    disputed_fine_signals_ar = [
        'لم أكون متواجد', 'لم اكن متواجد', 'لم أكن في', 'لم اكن في',
        'صورة المخالفة', 'رقم اللوحة خاطئ', 'لوحة غير لوحتي',
        'خطأ في اللوحة', 'ليست سيارتي', 'ليست مركبتي',
        'مخالفة بشكل خاطىء', 'مخالفة بشكل خاطئ',
        'تحرير مخالفة بشكل خاطىء', 'تحرير مخالفة بشكل خاطئ',
        'عدم خصم', 'نقاط خاطئة',
    ]
    disputed_fine_signals_en = [
        'not my vehicle', 'not my car', 'i was not in', 'i did not go to',
        'was not there', 'was in al ain', 'wrong plate', 'wrong car',
        'photo is not my', 'picture is not my', 'by mistake',
        'third time getting fine', 'getting fine by mistake',
    ]
    has_arabic_dispute = any(k in title_norm for k in [normalize_arabic(w) for w in disputed_fine_signals_ar])
    has_english_dispute = any(k in title.lower() for k in disputed_fine_signals_en)
    fine_also_mentioned = has_fine or any(k in title.lower() for k in ['fine', 'violation', 'ticket', 'مخالفة', 'مخالفه'])
    if (has_arabic_dispute or has_english_dispute) and fine_also_mentioned:
        return 'شكوى', 'شكوى عن مخالفة مشكوك فيها', 'شكوى صريحة عن مخالفة خاطئة', 0.88

    # --- PRIORITY 2: Security/Traffic Reports (filing, issuing, etc.) ---
    # Bug #8: 'تحرير مخالفة' removed — ambiguous, now handled by Priority 1b (disputed fine rule)
    # Bug #5: added English fraud/crime/scam signals
    report_keywords_ar = ['فتح بلاغ', 'تقديم بلاغ', 'سرقة', 'حادث', 'بلاغ جنائي',
                          'تعرضت للضرب', 'تعرضي للضرب', 'اعتداء', 'نصب', 'احتيال']
    report_keywords_en = ['i got scammed', 'scammed', 'fraud', 'fake iphone', 'took money from me',
                          'he took', 'she took', 'stolen', 'assault', 'attacked', 'robbery']
    has_ar_report = any(k in title_norm for k in [normalize_arabic(w) for w in report_keywords_ar])
    has_en_report = any(k in title.lower() for k in report_keywords_en)
    if has_ar_report or has_en_report:
        return 'شكوى', 'تقديم بلاغ أمني أو مروري', 'بلاغ أمني أو مروري مباشر', 0.90

    # --- PRIORITY 3: Processing Delay (moved earlier to catch delayed requests) ---
    # FIX 1: Remove generic time words; use compound phrases to match only delay complaints
    # 'لعدم رد' removed — too generic, appears in neutral contexts
    delay_keywords = ['تأخير', 'لم يتم البت', 'لم يتم الرد', 'أشهر ولم', 'سنة ولم']
    if any(k in title_norm for k in [normalize_arabic(w) for w in delay_keywords]):
        return 'شكوى', 'شكوى على تأخر المعالجة', 'شكوى تأخر معالجة الطلب', 0.84

    # --- PRIORITY 4: Weapons Permits ---
    # FIX 3: Remove bare 'سلاح' — keep only compound phrases to avoid matching delay complaints
    weapons_keywords = ['تصريح سلاح', 'ذخيرة', 'ترخيص سلاح', 'طلب سلاح']
    if any(k in title_norm for k in [normalize_arabic(w) for w in weapons_keywords]):
        return 'طلب', 'طلب تصريح سلاح أو ترخيص', 'طلب تصريح سلاح مباشر', 0.91

    # --- PRIORITY 5: License/Vehicle Delivery Not Received ---
    # Bug #3: expanded with all attested Arabic forms including informal/typo variants
    delivery_keywords = [
        'لم استلم', 'لم أستلم', 'لم تصلني', 'لم يتم التسليم',
        'لم تصل الرخصة', 'لم تصل الرخصه', 'لم يتم التوصيل',
        'لم استلام', 'لم استلمت',
        'حتى الان لم', 'حتى الآن لم',
        'لم يتم ارسال', 'لم يرسل',
    ]
    if any(k in title_norm for k in [normalize_arabic(w) for w in delivery_keywords]):
        return 'شكوى', 'شكوى عن عدم استلام الخدمة', 'شكوى عدم استقبال وثيقة أو خدمة', 0.86

    # --- PRIORITY 5b: Paid But Not Received (English) ---
    # Bug #3: catch English cases where customer paid fees but hasn't received the service/document
    english_paid_not_received = (
        any(k in title.lower() for k in ['paid', 'already paid', 'paid the fee', 'paid renewal'])
        and any(k in title.lower() for k in ['not received', "haven't received", 'have not received', 'not delivered', 'not yet'])
    )
    if english_paid_not_received:
        return 'شكوى', 'شكوى عن عدم استلام الخدمة', 'دفع الرسوم ولم يستلم الخدمة', 0.85

    # --- PRIORITY 6: System/Technical Errors ---
    # Bug #9: added double-charge and paid-without-issuance keywords
    system_keywords = [
        'عطل', 'خطأ في النظام', 'خصم مرتين', 'لم يصدر', 'خطأ تقني',
        'دفع مرتين', 'دفع مبلغ مرتين', 'خصمت مرتين',
        'بدون اصدار', 'دون اصدار',
    ]
    if any(k in title_norm for k in [normalize_arabic(w) for w in system_keywords]):
        return 'شكوى', 'شكوى على خطأ تقني أو في النظام', 'خلل تقني أو خطأ في النظام', 0.87

    # --- PRIORITY 6a: Renewal/Service Requests (BUG FIX 4) ---
    # Action-intent framing for renewals — returns 'طلب' not 'استفسار'
    renewal_request_keywords = ['اريد تجديد', 'أريد تجديد', 'لا استطيع تجديد', 'لا أستطيع تجديد', 'طلب تجديد', 'أطلب تجديد']
    if any(k in title_norm for k in [normalize_arabic(w) for w in renewal_request_keywords]):
        return 'طلب', 'طلب تجديد رخصة أو ملكية', 'طلب تجديد صريح', 0.85

    # --- PRIORITY 6b: Follow-up on Existing Request ---
    # Bug #4: cases where the customer is following up on a previously submitted request/case
    followup_keywords_ar = [
        'رقم الطلب', 'شكوى رقم', 'بلاغ رقم',
        'وللحين ما', 'وللحين لم', 'ولم يتم حتى',
        'رجاء التواصل', 'الرجاء التواصل',
        'لعدم ردي', 'لعدم الرد',
        'متابعة طلبي', 'بخصوص طلبي السابق',
        'لازال معلق', 'لا يزال معلق', 'قيد الانتظار',
    ]
    followup_keywords_en = [
        'my previous request', 'follow up on', 'reference number',
        'case number', 'ticket number', "what's the problem",
        'what i need to do', 'still pending', 'no response yet',
    ]
    has_ar_followup = any(k in title_norm for k in [normalize_arabic(w) for w in followup_keywords_ar])
    has_en_followup = any(k in title.lower() for k in followup_keywords_en)
    is_formal_complaint = any(k in title_norm for k in [normalize_arabic(w) for w in ['أتقدم بشكوى', 'أقدم شكوى', 'شكوى رسمية', 'مشكلة']])
    if (has_ar_followup or has_en_followup) and not is_formal_complaint:
        return 'طلب', 'متابعة طلب مقدم', 'متابعة طلب مقدم سابقاً', 0.80

    # --- PRIORITY 7: License/Vehicle Inquiries ---
    # FIX 2: Remove bare 'تجديد' and 'استفسار' — use compound phrases to avoid catch-all
    vehicle_keywords = ['رخصة قيادة', 'مركبة', 'ترخيص المركبة', 'تجديد الملكية', 'تجديد الرخصة']
    if any(k in title_norm for k in [normalize_arabic(w) for w in vehicle_keywords]):
        return 'استفسار', 'استفسار عن الرخص والمركبات', 'استفسار عن الرخص والمركبات', 0.85

    # --- PRIORITY 8: Praise/Compliments ---
    # ISSUE 5 FIX: Only classify as praise if no complaint/request signals present
    # (bare 'شكر' and 'تقدير' appear in polite closings of complaints/requests)
    praise_keywords = ['شكر وثناء', 'ثناء', 'ممتاز', 'شكرا جزيلا', 'نشكر', 'نتقدم بالشكر', 'تقديم الشكر']
    complaint_request_signals = ['مخالفة', 'شكوى', 'بلاغ', 'لم', 'مشكلة', 'خطأ', 'عطل']

    has_complaint_signal = any(k in title_norm for k in [normalize_arabic(w) for w in complaint_request_signals])
    if not has_complaint_signal and any(k in title_norm for k in [normalize_arabic(w) for w in praise_keywords]):
        return 'شكر وثناء', 'شكر وتقدير عام', 'شكر وتقدير صريح', 0.93

    # --- PRIORITY 9: Resolution-Based Fine Classification ---
    # Distinguish "اعتراض على مخالفة مرورية" from "شكوى عن مخالفة مشكوك فيها"
    # based on whether resolution confirms fine validity or reveals error.
    #
    # Catches cases where title mentions fine (has_fine=True) but no explicit contest language (has_contest=False).
    # Resolution signals determine the actual sub-classification.
    #
    # If resolution confirms fine is valid, classify as "اعتراض" (objection to valid fine)
    # If resolution confirms fine was erroneous, classify as "مشكوك فيها" (complaint about error)

    fine_confirmed_valid_keywords = [
        'المخالفة صحيحة',           # Fine is correct
        'تم التحقق',                # Verified
        'مخالفة قانونية',          # Legal fine
        'النقاط صحيحة',             # Points are correct
        'صحت المخالفة',             # Fine was correct
        'النقاط المخصومة صحيحة',    # Deducted points are correct
        'تجاوز الحد',                # Exceeded limit
        'ثبت ارتكاب',               # Proven to have committed
        'تم إثبات',                  # Proven/confirmed
    ]
    fine_found_erroneous_keywords = [
        'لا توجد مخالفة',           # No fine exists
        'تم الإلغاء',                # Was cancelled
        'خطأ في البيانات',          # Error in data
        'لم تدخل',                   # Did not enter (speeding zone)
        'ليست مركبته',              # Not his vehicle
        'خطأ في اللوحة',            # License plate error
        'مركبة غير عائدة',          # Vehicle not belonging (to owner)
        'إلغاء المخالفة',           # Fine cancelled
    ]

    fine_confirmed_valid = any(k in res_norm for k in [normalize_arabic(w) for w in fine_confirmed_valid_keywords])
    fine_found_erroneous = any(k in res_norm for k in [normalize_arabic(w) for w in fine_found_erroneous_keywords])

    if has_fine and fine_confirmed_valid:
        # Customer mentioned fine, and resolution confirms it was correct
        print(f"[Stage2] Case {case_row.get('رقم_الطلب', 'UNKNOWN')}: Priority 9 fine_confirmed_valid → اعتراض على مخالفة مرورية")
        return 'شكوى', 'اعتراض على مخالفة مرورية', 'اعتراض على مخالفة صحيحة (من الحل)', 0.82

    if has_fine and fine_found_erroneous:
        # Customer mentioned fine, and resolution confirms it was an error
        print(f"[Stage2] Case {case_row.get('رقم_الطلب', 'UNKNOWN')}: Priority 9 fine_found_erroneous → شكوى عن مخالفة مشكوك فيها")
        return 'شكوى', 'شكوى عن مخالفة مشكوك فيها', 'شكوى عن مخالفة خاطئة (من الحل)', 0.85

    # --- PRIORITY 10: Data Update/Correction Requests (English) ---
    # Bug #6: English cases requesting info updates not caught by Arabic keyword rules
    data_update_keywords_en = [
        'update my information', 'update my info', 'change my photo',
        'wrong photo', 'wrong picture', 'another person photo',
        'update my details', 'correct my name', 'wrong name on',
        'pls update', 'please update', 'change my number', 'update my number',
    ]
    if any(k in title.lower() for k in data_update_keywords_en):
        return 'طلب', 'طلب تعديل أو تحديث بيانات', 'طلب تحديث بيانات بالإنجليزية', 0.83

    # --- DEFAULT FALLTHROUGH ---
    # Map CRM label to taxonomy if available (last resort).
    # Bug #1: استفسار fallthrough confidence lowered to 0.45 — the CRM frequently mislabels
    # complaints and requests as استفسار, so every unmatched استفسار must go to LLM (Stage 3).
    crm_label_norm = normalize_arabic(crm_label)
    if crm_label_norm == 'شكوى' or crm_label_norm == 'complaint':
        return 'شكوى', 'شكوى عامة', 'تصنيف CRM: شكوى عامة', 0.75
    elif crm_label_norm == 'طلب' or crm_label_norm == 'request':
        return 'طلب', 'طلب خدمة عام', 'تصنيف CRM: طلب عام', 0.75
    elif crm_label_norm == 'استفسار' or crm_label_norm == 'inquiry':
        return 'استفسار', 'استفسار عام', 'تصنيف CRM: يحتاج مراجعة LLM', 0.45
    else:
        return 'استفسار', 'استفسار عام', 'تصنيف افتراضي', 0.70


def run_stage2(state: PipelineState) -> PipelineState:
    """
    Stage 2: Rule-based classifier with two-level taxonomy.

    Input: state with raw_df
    Output: state with rule_classified and llm_queue
    """
    if state.raw_df is None:
        raise ValueError("raw_df not populated. Run Stage 1 first.")

    rule_classified = []
    llm_queue = []

    for idx, row in state.raw_df.iterrows():
        top_level, sub_classification, reason, confidence = classify_case(row.to_dict())

        # Use SLA compliance field (نعم/لا) if available, else fall back to status
        sla_value = str(row.get('سلا_امتثال', '')).strip() or str(row.get('الحالة_SLA', '')).strip()

        case = CaseRow(
            case_number=str(row.get('رقم_الطلب', '')),
            case_title=str(row.get('تفاصيل_الطلب', '')),
            date_opened=str(row.get('تاريخ_الإنشاء', '')),
            case_channel=str(row.get('قناة_تقديم_الخدمة', '')),
            description=str(row.get('تفاصيل_الطلب', '')),  # Actual description, not CRM label
            resolution_response=str(row.get('الحل', '')),
            sla_color=sla_value,
            case_type=str(row.get('نوع_المكالمة', '')),  # Original CRM label for tracking
            service_name=str(row.get('الخدمة_الرئيسية', '')),
            actual_contact_type=top_level,
            classification_reason=reason,
            confidence=confidence,
            misclassification='OK',
            top_level=top_level,
            sub_classification=sub_classification,
            admin=str(row.get('الإدارة_العامة', '')),
        )

        # Check for misclassification — use actual_contact_type (consistent with Stage 6 reclassified_count)
        if case.case_type and case.actual_contact_type != case.case_type:
            case.misclassification = f"Reclassified: {case.case_type} → {case.actual_contact_type}"

        if confidence < LOW_CONFIDENCE_THRESHOLD:
            # Queue for LLM review
            llm_queue.append(case.model_dump())
        else:
            rule_classified.append(case)

    state.rule_classified = rule_classified
    state.llm_queue = llm_queue

    return state
