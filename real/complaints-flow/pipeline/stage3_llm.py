"""
STAGE 3: LLM Classifier (Complaints Pipeline)

Classifies low-confidence complaint cases from Stage 2 using Claude API.
All cases are complaints (شكوى) — no multi-type taxonomy.
Uses 6 complaint sub-categories for fine-grained classification.
Cases with LLM confidence < 0.65 go to human_review_queue.
Uses Haiku for speed and cost efficiency on this high-volume task.
"""

import json
import anthropic
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List
from .state import PipelineState, CaseRow
from .stage2_rules import ALL_COMPLAINT_SUB_CATEGORIES

# Confidence threshold — lowered from 0.85. At 0.85, valid classifications (0.65–0.8) got discarded.
LLM_LOW_CONFIDENCE_THRESHOLD = 0.65

# Tool schema for batch classification — complaints only, 6 sub-categories
CLASSIFIER_TOOL = {
    "name": "classify_cases_batch",
    "description": "Classify a batch of complaint cases into 6 complaint sub-categories. Return one classification per case in order.",
    "input_schema": {
        "type": "object",
        "properties": {
            "classifications": {
                "type": "array",
                "description": "One entry per case, in the same order as the input",
                "items": {
                    "type": "object",
                    "properties": {
                        "case_number": {
                            "type": "string",
                            "description": "The case number exactly as provided"
                        },
                        "top_level": {
                            "type": "string",
                            "enum": ["شكوى"],
                            "description": "Top-level category (always شكوى for complaints)"
                        },
                        "sub_classification": {
                            "type": "string",
                            "enum": ALL_COMPLAINT_SUB_CATEGORIES,
                            "description": "Complaint sub-category (one of 6 types)"
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0
                        },
                        "reason": {
                            "type": "string",
                            "description": "1-2 sentence explanation in Arabic only"
                        }
                    },
                    "required": ["case_number", "top_level", "sub_classification", "confidence", "reason"]
                }
            }
        },
        "required": ["classifications"]
    }
}


def build_system_prompt() -> str:
    """Build system prompt with complaints-specific taxonomy and rules."""
    return """You are an expert customer service analyst for Fujairah Police.
Classify customer complaints using a complaints-specific taxonomy.

IMPORTANT: All cases provided are COMPLAINTS (شكوى). There is no multi-type taxonomy.
Your task is to classify each complaint into one of 6 sub-categories.

COMPLAINT SUB-CATEGORIES (6 types):

1. شكاوى مكررة (مرفوضة) [Repeated/Rejected Complaints]
   - Complaints flagged as duplicate or formally rejected (الحالة == 'طلب مرفوض')
   - Cases with clear "مكرر" / "مكررة" signals in resolution text
   - Complaints on identical issues from same person within short timeframe
   - Should be flagged for archival, not continued processing

2. شكاوى بلا تصنيف خدمي ("أخرى") [Unclassified Complaints]
   - Complaints with service field = 'أخرى' and no clear signal about which service
   - Generic complaints that don't match traffic, security, or certificate signals
   - Cases where service context is unclear or mixed
   - These cases lack clear service signals for further processing

3. شكاوى على الخدمات المرورية [Traffic Service Complaints]
   - Complaints about traffic fines, license disputes, vehicle registration
   - Examples: "مخالفة مروية غير صحيحة", "رخصة القيادة", "تجديد ملكية المركبة"
   - Traffic fine disputes vs. administrative corrections (not criminal)
   - Signal keywords: مخالفة, رخصة, مركبة, تجديد, مروري, لوحة, سائق

4. شكاوى أمنية وجنائية [Security/Criminal Complaints]
   - Complaints about criminal matters, security incidents, fraud reports
   - Examples: "بلاغ جنائي", "اعتداء", "سرقة", "احتيال", "نصب"
   - Filed through security department channels (فتح البلاغات الجنائية)
   - Signal keywords: بلاغ, جنائي, اعتداء, سرقة, احتيال, نصب, توقيف, اعتقال

5. شكاوى شهادات وتصاريح [Certificate/Permit Complaints]
   - Complaints about document issuance, permits, licenses
   - Examples: "شهادة حسن سيرة", "ترخيص سلاح", "جواز", "إقامة"
   - Service explicitly related to certificate issuance or permit processing
   - Signal keywords: شهادة, وثيقة, تصريح, جواز, إقامة, ترخيص سلاح

6. شكاوى خارج الاختصاص والأخرى [Out-of-Jurisdiction and Other Complaints]
   - Complaints that belong to other government entities (not Fujairah Police)
   - Examples: Ministry of Labor issues, prison administration, foreign affairs
   - Cases where resolution confirms "not our jurisdiction"
   - Signal keywords from resolution: ليس من اختصاص, خارج الاختصاص, وزارة العمل, جهة أخرى

CLASSIFICATION PRIORITY (in order):

Priority 1: Rejection Flag
   - If الحالة == 'طلب مرفوض' → ALWAYS "شكاوى مكررة (مرفوضة)" (confidence 0.95)
   - If resolution contains "مكرر" / "مكررة" → "شكاوى مكررة (مرفوضة)" (confidence 0.90)

Priority 2: Service Field Mapping
   - If الخدمة field has direct mapping (traffic, security, certificates, etc.)
   - Use that mapping with HIGH CONFIDENCE (0.90+)
   - Example: الخدمة = 'فتح البلاغات المرورية' → Traffic complaints

Priority 3: Text Signal Analysis (when الخدمة == 'أخرى')
   - Check تفاصيل_الطلب and الحل for domain-specific keywords
   - Traffic signals: مخالفة, رخصة, مركبة, تجديد, مروري, لوحة, سائق
   - Security signals: بلاغ, جنائي, اعتداء, سرقة, احتيال, نصب, توقيف, اعتقال
   - Certificate signals: شهادة, وثيقة, تصريح, جواز, إقامة, ترخيص سلاح
   - Out-of-jurisdiction signals (from resolution): ليس من اختصاص, خارج الاختصاص, وزارة العمل, جهة أخرى
   - Medium confidence for text signals (0.74-0.80)

Priority 4: Traffic Fine Disambiguation
   - If description mentions "مخالفة" but resolution shows no actual fine exists:
     → Focus on the complainant's underlying need (data correction? information?)
     → May become a request for data update, not a fine dispute
   - If description mentions fine AND resolution confirms fine exists or is disputed:
     → Traffic complaints category
   - Traffic disputes are SERVICE complaints, not CRIMINAL complaints

Priority 5: Default / Low Confidence
   - If no clear signal after analysis → "شكاوى بلا تصنيف خدمي ("أخرى")" with low confidence (0.40)
   - These are flagged for human review or further LLM processing

RULES AND EXAMPLES:

Rule A — Status-based rejection:
   Case Status: الحالة == 'طلب مرفوض'
   → Classify as "شكاوى مكررة (مرفوضة)" (confidence 0.95)
   Reason: رسمياً مرفوض حسب حقل الحالة

Rule B — Duplicate keyword in resolution:
   Resolution contains: "هذه شكوى مكررة" or "طلب مكرر على نفس الموضوع"
   → Classify as "شكاوى مكررة (مرفوضة)" (confidence 0.90)
   Reason: كلمة مكرر في نص الحل

Rule C — Direct service mapping (high confidence):
   Service: 'فتح البلاغات المرورية'
   → Classify as "شكاوى على الخدمات المرورية" (confidence 0.92)
   Reason: تطابق مباشر لحقل الخدمة

Rule D — Traffic signal in خدمة == 'أخرى':
   Service: 'أخرى'
   Description: "مخالفة مروية وصلتني بشكل خاطئة"
   → Classify as "شكاوى على الخدمات المرورية" (confidence 0.75)
   Reason: إشارات مرورية في الوصف (خدمة: أخرى)

Rule E — Security keyword signal:
   Service: 'أخرى'
   Description: "سرقة ممتلكاتي من الفندق"
   → Classify as "شكاوى أمنية وجنائية" (confidence 0.75)
   Reason: إشارات أمنية/جنائية في الوصف (خدمة: أخرى)

Rule F — Certificate/permit signals:
   Service: 'أخرى'
   Description: "تأخر في استخراج شهادة حسن سيرة"
   → Classify as "شكاوى شهادات وتصاريح" (confidence 0.74)
   Reason: إشارات شهادات/تصاريح في الوصف (خدمة: أخرى)

Rule G — Out-of-jurisdiction from resolution:
   Service: 'أخرى'
   Resolution: "هذا الموضوع من اختصاص وزارة العمل وليس من اختصاصنا"
   → Classify as "شكاوى خارج الاختصاص والأخرى" (confidence 0.80)
   Reason: الحل يشير إلى خارج الاختصاص

Rule H — Traffic fine with no actual fine:
   Description: "مخالفة وصلتني بشكل خاطئة"
   Resolution: "التدقيق تبين عدم وجود مخالفة في نظام المتعاملين"
   → If complaint is about the false fine → Traffic complaint
   → If complaint is about data integrity (wants correction) → Still Traffic
   Reason: الشكوى تتعلق بخدمات مرورية حتى لو تبين عدم وجود مخالفة فعلية

OUTPUT REQUIREMENTS:

- top_level: Always "شكوى" for all complaints
- sub_classification: One of the 6 complaint categories listed above
- confidence: 0.0–1.0 (reflect your certainty)
  * 0.90+ = direct service mapping or clear signals
  * 0.75-0.89 = text signals from description/resolution
  * 0.65-0.74 = weak signals, needs human review
  * Below 0.65 = flagged automatically for human review
- reason: 1-2 sentence explanation entirely in Arabic
- case_number: Return exactly as provided

SPECIAL INSTRUCTIONS:

- Do NOT apply multi-category taxonomy (that's only for inquiries pipeline)
- All top_level values must be "شكوى" — no exceptions
- Read both description (تفاصيل_الطلب) and resolution (الحل) together
- If resolution clarifies something not obvious in the description, use it to adjust classification
- Provide reasons ENTIRELY IN ARABIC only
- Return exactly one classification per case in input order"""


def _process_batch(client: anthropic.Anthropic, batch: List[Dict], batch_num: int, total_batches: int) -> List[Dict]:
    """
    Process a single batch of complaint cases against the Haiku classifier.

    Designed to be called from a thread pool — no shared mutable state is read or
    written; all inputs are passed by value and the return value is a plain list.

    Args:
        client: Anthropic API client (thread-safe for concurrent requests)
        batch: Slice of case dicts for this batch
        batch_num: 1-based batch index (for logging only)
        total_batches: Total number of batches (for logging only)

    Returns:
        List of classification dicts for every case in the batch
    """
    print(f"[Stage3] Batch {batch_num}/{total_batches} ({len(batch)} cases)...")

    cases_text = "\n\n".join([
        f"Case Number: {case.get('case_number', 'N/A')}\n"
        f"Description: {case.get('description', '').strip()}\n"
        f"Resolution: {case.get('resolution_response', '').strip()}\n"
        f"Service: {case.get('service_name', '')}\n"
        f"Channel: {case.get('case_channel', '')}\n"
        f"Stage 2 suggestion (may be wrong — all rules above take precedence): "
        f"{case.get('top_level', 'N/A')} > {case.get('sub_classification', 'N/A')}"
        for case in batch
    ])

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",  # Haiku for speed/cost on bulk classification
            max_tokens=8000,  # Need room for 25 case classifications (each ~150 tokens)
            system=build_system_prompt(),
            tools=[CLASSIFIER_TOOL],
            tool_choice={"type": "any"},  # Force tool use — no free-text fallback
            messages=[{
                "role": "user",
                "content": (
                    f"Classify these {len(batch)} complaint cases into the 6 complaint sub-categories. "
                    f"Return exactly one entry per case in the classifications array.\n\n"
                    f"{cases_text}"
                )
            }]
        )

        tool_calls = [b for b in message.content if b.type == "tool_use"]

        if message.stop_reason == "max_tokens":
            print(f"[Stage3] ERROR: Batch {batch_num} response was truncated (hit max_tokens limit)")
            print(f"[Stage3] Current max_tokens: 8000. Consider increasing further or reducing batch_size.")

        if tool_calls:
            classifications = tool_calls[0].input.get("classifications", [])

            if len(classifications) < len(batch):
                print(f"[Stage3] WARNING: Batch {batch_num} incomplete — got {len(classifications)}/{len(batch)} classifications")
                print(f"[Stage3] stop_reason: {message.stop_reason}")

            batch_results = list(classifications)

            # Fallback for any case the LLM missed
            classified_numbers = {c["case_number"] for c in classifications}
            for case in batch:
                cn = case.get("case_number", "")
                if cn not in classified_numbers:
                    print(f"[Stage3] WARNING: Case {cn} missing from batch {batch_num} response")
                    batch_results.append({
                        "case_number": cn,
                        "top_level": "شكوى",
                        "sub_classification": 'شكاوى بلا تصنيف خدمي ("أخرى")',
                        "confidence": 0.4,
                        "reason": "لم يتم إرجاع الحالة في رد الدفعة"
                    })

            return batch_results

        else:
            print(f"[Stage3] WARNING: No tool call in batch {batch_num}")
            return [
                {
                    "case_number": case.get("case_number", ""),
                    "top_level": "شكوى",
                    "sub_classification": 'شكاوى بلا تصنيف خدمي ("أخرى")',
                    "confidence": 0.3,
                    "reason": "لم يتم استدعاء أداة تصنيف في هذه الدفعة"
                }
                for case in batch
            ]

    except Exception as e:
        print(f"[Stage3] Error in batch {batch_num}: {e}")
        return [
            {
                "case_number": case.get("case_number", ""),
                "top_level": "شكوى",
                "sub_classification": 'شكاوى بلا تصنيف خدمي ("أخرى")',
                "confidence": 0.4,
                "reason": f"خطأ في معالجة الدفعة: {str(e)}"
            }
            for case in batch
        ]


def classify_with_llm(client: anthropic.Anthropic, cases: List[Dict], progress_callback=None) -> List[Dict]:
    """
    Classify complaint cases using Claude Haiku with array tool-use for proper batch handling.

    Batches run concurrently (max 5 threads) for a ~5x speedup on large datasets.
    Each batch is a fully independent API call — no cross-batch dependencies — so
    threading has zero effect on classification quality.

    Args:
        client: Anthropic API client
        cases: List of case dicts
        progress_callback: Optional function(pct, msg_ar, msg_en) for UI updates

    Returns:
        List of classification results {case_number, top_level, sub_classification, confidence, reason}
    """
    batch_size = 25  # Balances efficiency with response completeness (each ~150 tokens = 2250 total, safe margin under 8000 max)
    batches = [cases[i:i + batch_size] for i in range(0, len(cases), batch_size)]
    total_batches = len(batches)
    print(f"[Stage3] Processing {len(cases)} cases in {total_batches} batches of {batch_size} (max_workers=5)")

    results = []
    completed_lock = threading.Lock()
    completed_count = 0

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_batch = {
            executor.submit(_process_batch, client, batch, batch_num, total_batches): batch_num
            for batch_num, batch in enumerate(batches, 1)
        }

        for future in as_completed(future_to_batch):
            batch_results = future.result()
            with completed_lock:
                results.extend(batch_results)
                completed_count += 1
                if progress_callback:
                    pct = 0.30 + (completed_count / total_batches * 0.10)  # Progress spans 30% to 40%
                    progress_callback(
                        pct,
                        f"معالجة الدفعات {completed_count}/{total_batches}",
                        f"Processing batches {completed_count}/{total_batches}"
                    )

    return results


def normalize_classification(top_level: str, sub_classification: str) -> tuple[str, str]:
    """
    Normalize classification to canonical values.

    For complaints pipeline:
    - top_level must always be "شكوى"
    - sub_classification must be one of the 6 complaint categories

    Args:
        top_level: Raw top_level from LLM or Stage 2
        sub_classification: Raw sub_classification from LLM or Stage 2

    Returns:
        (normalized_top_level, normalized_sub_classification)
    """
    # Complaints pipeline: top_level is always "شكوى"
    canonical_top_level = "شكوى"
    canonical_subs = ALL_COMPLAINT_SUB_CATEGORIES

    # Normalize top_level to "شكوى" (with validation)
    if top_level != canonical_top_level:
        print(f"[Stage3] TAXONOMY FIX: top_level '{top_level}' is not valid for complaints — forcing to '{canonical_top_level}'")
        top_level = canonical_top_level

    # Normalize sub_classification with keyword-based matching
    if sub_classification not in canonical_subs:
        sc_lower = sub_classification.lower().strip()

        # Build keyword map for fuzzy matching (key words → canonical string)
        keyword_map = {}
        for canonical in canonical_subs:
            canonical_lower = canonical.lower()
            # Extract key words from canonical (split by common delimiters)
            words = [w for w in canonical_lower.replace('أو', ' ').replace('و', ' ').split() if w]
            for word in words:
                if len(word) > 2:  # Skip short words
                    keyword_map[word] = canonical

        # Try to match using keywords
        matched = False
        for keyword, canonical in keyword_map.items():
            if keyword in sc_lower:
                sub_classification = canonical
                matched = True
                break

        if not matched:
            # Fallback to unclassified
            sub_classification = 'شكاوى بلا تصنيف خدمي ("أخرى")'
            print(f"[Stage3] TAXONOMY FIX: sub_classification '{sub_classification}' not valid — reset to unclassified")

    return top_level, sub_classification


def run_stage3(state: PipelineState, api_key: str, progress_callback=None) -> PipelineState:
    """
    Stage 3: LLM classifier for complaints.

    Input: state with llm_queue from Stage 2
    Output: state with llm_classified and human_review_queue
    """
    if not state.llm_queue:
        state.llm_classified = []
        state.human_review_queue = []
        return state

    client = anthropic.Anthropic(api_key=api_key)
    llm_results = classify_with_llm(client, state.llm_queue, progress_callback=progress_callback)

    # Index results by case_number for fast lookup
    results_by_number = {r["case_number"]: r for r in llm_results}

    llm_classified = []
    human_review = []

    for orig_case in state.llm_queue:
        cn = orig_case.get("case_number", "")
        result = results_by_number.get(cn)

        if not result:
            print(f"[Stage3] WARNING: Case {cn} has no result after all batches")
            human_review.append(orig_case)
            continue

        # Normalize classifications to canonical values
        top_level, sub_classification = normalize_classification(
            result.get("top_level", "شكوى"),
            result.get("sub_classification", 'شكاوى بلا تصنيف خدمي ("أخرى")')
        )

        case = CaseRow(
            case_number=cn,
            case_title=orig_case.get("case_title", ""),
            date_opened=orig_case.get("date_opened", ""),
            case_channel=orig_case.get("case_channel", ""),
            description=orig_case.get("description", ""),
            resolution_response=orig_case.get("resolution_response", ""),
            sla_color=orig_case.get("sla_color", ""),
            case_type=orig_case.get("case_type", ""),
            service_name=orig_case.get("service_name", ""),
            actual_contact_type=top_level,
            classification_reason=result["reason"],
            confidence=result["confidence"],
            misclassification="OK",
            top_level=top_level,
            sub_classification=sub_classification,
            admin=orig_case.get('admin', ''),
            # Carry forward complaints-specific fields
            severity=orig_case.get('severity', ''),
            complaint_category=sub_classification,
            resolved_by=orig_case.get('resolved_by', ''),
            owner=orig_case.get('owner', ''),
            applicant_name=orig_case.get('applicant_name', ''),
            nationality=orig_case.get('nationality', ''),
            id_number=orig_case.get('id_number', ''),
            mobile=orig_case.get('mobile', ''),
            employee_number=orig_case.get('employee_number', ''),
            sla_closed_on_time=orig_case.get('sla_closed_on_time', ''),
            emirate=orig_case.get('emirate', ''),
        )

        # Check for misclassification — use actual_contact_type (consistent with Stage 6 reclassified_count)
        if case.case_type and case.actual_contact_type != case.case_type:
            case.misclassification = f"Reclassified: {case.case_type} → {case.actual_contact_type}"

        if case.confidence < LLM_LOW_CONFIDENCE_THRESHOLD:
            human_review.append(case.model_dump())
        else:
            llm_classified.append(case)

    state.llm_classified = llm_classified
    state.human_review_queue = human_review

    print(f"[Stage3] Done — {len(llm_classified)} classified, {len(human_review)} to human review")
    return state
