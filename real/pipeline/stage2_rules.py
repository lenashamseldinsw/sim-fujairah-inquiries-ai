"""
STAGE 2: Rule-based Classifier

Applies priority decision tree to classify cases.
Low-confidence cases are queued for Stage 3 (LLM classifier).

Confidence threshold: 0.75 (tunable)
Contact type taxonomy: 8 categories with priority ordering.
"""

import re
from typing import Optional, Tuple
from .state import PipelineState, CaseRow

# Tunable confidence threshold — adjust based on Stage 2 test results
LOW_CONFIDENCE_THRESHOLD = 0.75


# Contact type taxonomy
CONTACT_TYPES = {
    'technical_incident': 'بلاغ تقني',
    'location_inquiry': 'استفسار عن الموقع',
    'cross_entity_confusion': 'خلط بين الجهات',
    'status_followup': 'متابعة حالة',
    'service_request': 'طلب خدمة',
    'complex_financial': 'استفسار مالي معقد',
    'pure_information': 'استفسار معلومات',
    'complaint': 'شكوى',
}


def normalize_arabic(text: str) -> str:
    """Normalize Arabic text for matching (remove diacritics, etc)."""
    if not text:
        return ""
    # Remove diacritics
    text = re.sub(r'[\u064B-\u065F]', '', text)
    return text.lower().strip()


def classify_case(case_row: dict) -> Tuple[str, str, float]:
    """
    Classify a single case using the priority decision tree.

    Args:
        case_row: Dict with case data

    Returns:
        (contact_type, reason, confidence)
    """
    desc = str(case_row.get('نوع_المكالمة', ''))
    resolution = str(case_row.get('الحل', ''))
    case_type = str(case_row.get('التصنيف_الفرعي', ''))
    title = str(case_row.get('تفاصيل_الطلب', ''))

    desc_norm = normalize_arabic(desc)
    res_norm = normalize_arabic(resolution)
    case_type_norm = normalize_arabic(case_type)

    # --- PRIORITY 1: Technical Incident ---
    if case_type_norm.startswith('incident') or 'بلاغ' in case_type_norm:
        if any(x in desc_norm for x in ['خطأ', 'عطل', 'شاشة بيضاء', 'خلل تقني', 'error', 'bug', 'crash']):
            if any(x in res_norm for x in ['بلاغ تقني', 'الدعم الفني', 'technical support']):
                return 'بلاغ تقني', 'بلاغ تقني محدد بواضحة', 0.97

    # --- PRIORITY 2: Location/Branch Inquiry ---
    location_keywords = ['أين يقع', 'أين مقر', 'أين موقع', 'where is', 'where are']
    location_answers = ['maps.app.goo.gl', 'google.com/maps', 'بني ياس', 'مدينة خليفة', 'محمد بن زايد']

    if any(x in desc_norm for x in [normalize_arabic(k) for k in location_keywords]):
        return 'استفسار عن الموقع', 'استفسار صريح عن الموقع الجغرافي', 0.98

    if any(x in res_norm for x in [normalize_arabic(a) for a in location_answers]):
        return 'استفسار عن الموقع', 'توفر رابط خريطة أو موقع محدد في الحل', 0.96

    # --- PRIORITY 3: Cross-Entity Confusion ---
    cross_entity = ['هيئة المعاشات', 'الهيئة العامة للمعاشات', 'gpssa', 'خارج اختصاص', 'federal pension']
    if any(x in desc_norm for x in [normalize_arabic(k) for k in cross_entity]):
        return 'خلط بين الجهات', 'الاستفسار متعلق بجهة أخرى', 0.94

    # --- PRIORITY 4: Status Follow-up ---
    tracking_pattern = r'(?:MTEP|MTDP|AD20\d\d|ISU20)\w+'
    if re.search(tracking_pattern, desc):
        return 'متابعة حالة', 'رقم تتبع محدد في الاستفسار', 0.96

    followup_keywords = ['رقم التتبع', 'بالرجوع للحالة', 'متابعة طلب', 'following up', 'tracking number']
    if any(x in desc_norm for x in [normalize_arabic(k) for k in followup_keywords]):
        return 'متابعة حالة', 'طلب متابعة صريح لحالة سابقة', 0.95

    # --- PRIORITY 5: Service Request vs Information (complex logic) ---

    # Test A: Strong Service Request signals
    service_patterns = [
        (r'(?:برقم التتبع|tracking)\s*[A-Z0-9]{5,}', 'Tracking number issued'),
        (r'تم (?:انجاز|إنجاز|انهاء) (?:معاملتك|طلبك)', 'Request completed'),
        (r'تم صرف (?:مكافأة|المعاش|الراتب)', 'Payment disbursed'),
        (r'تم (?:إصدار|اصدار) (?:شهادة|الشهادة)', 'Certificate issued'),
        (r'تم (?:تعديل|تحديث) (?:بياناتك|بيانات)', 'Data modified'),
        (r'تم (?:إيقاف|ايقاف|استئناف|إعادة صرف)', 'Status changed'),
        (r'تم التصعيد|تم التنسيق مع', 'Escalated internally'),
    ]

    for pattern, label in service_patterns:
        if re.search(pattern, resolution):
            # Apply false-positive filters
            # Check for conditional frames in 60 chars before match
            match_pos = re.search(pattern, resolution).start()
            context_start = max(0, match_pos - 60)
            context = resolution[context_start:match_pos]

            conditional_frames = ['في حال', 'في حالة', 'إذا', 'عند', 'بعد', 'لو', 'إن']
            has_conditional = any(cf in context for cf in conditional_frames)

            template_markers = ['شروط', 'الخطوات', 'يمكنك', 'بإمكان', 'للحصول على']
            has_template = any(tm in resolution for tm in template_markers)

            customer_pronouns = ['طلبك', 'معاملتك', 'حسابك', 'بياناتك']
            has_pronoun = any(cp in resolution for cp in customer_pronouns)

            if has_conditional and has_template and not has_pronoun:
                # Skip this pattern (explanatory, not action)
                continue
            else:
                # Genuine Service Request
                tracking_match = re.search(r'(?:برقم التتبع|tracking)\s*[A-Z0-9]{5,}', resolution)
                confidence = 0.96 if tracking_match else 0.87
                return 'طلب خدمة', 'طلب خدمة واضح مع دليل تنفيذ', confidence

    # Test B: Complex Financial Inquiry
    financial_pattern = r'\d[\d,]*\s*(?:درهم|AED|%)'
    financial_keywords = ['خصم', 'استقطاع', 'اقتطاع', 'تكلفة']

    if re.search(financial_pattern, desc):
        if any(k in desc_norm for k in [normalize_arabic(fk) for fk in financial_keywords]):
            return 'استفسار مالي معقد', 'استفسار مالي يتطلب توضيح الحسابات', 0.88

    # Test C: Default fallthrough — Pure Information Inquiry
    if case_type_norm == 'استفسار' or case_type_norm == 'information':
        return 'استفسار معلومات', 'استفسار عام عن معلومات أو خدمات', 0.82
    elif case_type_norm == 'شكوى' or case_type_norm == 'complaint':
        return 'شكوى', 'شكوى مباشرة من المتعامل', 0.90
    else:
        return 'استفسار معلومات', 'تصنيف افتراضي — معلومات', 0.72


def run_stage2(state: PipelineState) -> PipelineState:
    """
    Stage 2: Rule-based classifier.

    Input: state with raw_df
    Output: state with rule_classified and llm_queue
    """
    if state.raw_df is None:
        raise ValueError("raw_df not populated. Run Stage 1 first.")

    rule_classified = []
    llm_queue = []

    for idx, row in state.raw_df.iterrows():
        contact_type, reason, confidence = classify_case(row.to_dict())

        # Use SLA compliance field (نعم/لا) if available, else fall back to status
        sla_value = str(row.get('سلا_امتثال', '')).strip() or str(row.get('الحالة_SLA', '')).strip()

        case = CaseRow(
            case_number=str(row.get('رقم_الطلب', '')),
            case_title=str(row.get('تفاصيل_الطلب', '')),
            date_opened=str(row.get('تاريخ_الإنشاء', '')),
            case_channel=str(row.get('قناة_تقديم_الخدمة', '')),
            description=str(row.get('نوع_المكالمة', '')),
            resolution_response=str(row.get('الحل', '')),
            sla_color=sla_value,
            case_type=str(row.get('نوع_المكالمة', '')),  # Original CRM label (استفسار, شكوى, طلب)
            service_name=str(row.get('الخدمة_الرئيسية', '')),
            actual_contact_type=contact_type,
            classification_reason=reason,
            confidence=confidence,
            misclassification='OK'  # Will be updated if case_type doesn't match
        )

        # Check for misclassification
        if case.case_type != contact_type and case.case_type:
            case.misclassification = f"Over-classified: {case.case_type} → {contact_type}"

        if confidence < LOW_CONFIDENCE_THRESHOLD:
            # Queue for LLM review
            llm_queue.append(case.model_dump())
        else:
            rule_classified.append(case)

    state.rule_classified = rule_classified
    state.llm_queue = llm_queue

    return state
