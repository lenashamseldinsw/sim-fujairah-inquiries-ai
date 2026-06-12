"""
generate_digital_transformation_section — stage6_artifacts.py companion

Generates Section 6: "سادساً: التحليل الرابع — خطة التحويل الرقمي"

INTEGRATION
───────────
1. stage6_artifacts.py — _generate_report_sections(), after digital_gaps block:

    from .generate_digital_transformation_section import generate_digital_transformation_section

    print("[Report Gen] Generating Digital Transformation section...")
    digital_transformation = generate_digital_transformation_section(state, api_key)
    state.report_sections_ar['digital_transformation'] = {
        'heading': 'سادساً: التحليل الرابع — خطة التحويل الرقمي',
        'raw_data': digital_transformation,
    }

2. stage6_json_report.py — JSONReportBuilder:

    a) Import at top:
       from .generate_digital_transformation_section import (
           _build_faq_rows_for_transform,
           _build_notification_rows,
       )

    b) Paste build_digital_transformation_section as a method on JSONReportBuilder.

    c) In build_report(), after build_digital_gaps_section():
        sections.append(self.build_digital_transformation_section(lang=lang))

SECTION STRUCTURE:
──────────────────
Intro paragraph: states the digital transformation vision grounded in pipeline data.

Sub-section 6.1 — الأسئلة الشائعة (FAQ)
  Table columns: # | السؤال | الإجابة الصحيحة | التكرار
  Data source: state.validated_faqs and state.faq_candidates (from Stage 4/5)
  Frequency: Actual case counts from pipeline, never LLM-invented
  Sorting: By frequency (descending) — most impactful FAQs first

Sub-section 6.2 — فرص الإخطار الاستباقي
  Table columns: نوع الإشعار | الحالات المُلغاة | محتوى الإشعار (مثال) | القناة | الأثر المتوقع
  Data source: state.notification_opportunities (from Stage 5)
  Case counts: Actual values from pipeline, never LLM-invented

DATA SOURCING — no new computation, only state reads
─────────────────────────────────────────────────────
• validated_faqs        → validated FAQ entries (Stage 4/5)
• faq_candidates        → candidate FAQ entries (Stage 4/5)
• notification_opportunities → proactive notification scenarios (Stage 5)
• month_year            → report date range

ERROR POLICY
────────────
No fallbacks. No placeholder returns. Every failure raises so the caller
(_generate_report_sections) sees and logs the real exception.
"""

import json
from typing import Dict, Any, List, Optional
import anthropic

from .state import PipelineState, convert_month_year_to_arabic
from .json_utils import parse_json_response


def _build_faq_rows_for_transform(state: PipelineState) -> List[Dict[str, str]]:
    """
    Build FAQ rows from validated FAQs for the transformation section.

    COLUMNS (Section 6.1 FAQ table):
    #, السؤال, الإجابة الصحيحة, التكرار

    SOURCE: state.validated_faqs (from Stage 5, post-reconciliation).
    ACCURACY: Frequency values are actual case counts from the pipeline (reconciled in Stage 5),
              never LLM-invented. FAQs with frequency=0 are skipped (no matching cases found).

    CRITICAL: Frequencies must be >= 1 to be included. FAQs with reconciled frequency=0
              indicate no actual cases matched the FAQ question/answer, so they're excluded.

    Args:
        state: Pipeline state containing validated_faqs

    Returns:
        List of row dicts with FAQ columns, sorted by frequency (descending)
    """
    rows = []
    counter = 1

    # Use validated_faqs only (these have already been reconciled with actual case counts in Stage 5)
    all_faqs = list(state.validated_faqs) if state.validated_faqs else []

    # Sort by frequency (descending) to show most impactful FAQs first
    all_faqs.sort(
        key=lambda f: (
            f.get('frequency', 0)
            if isinstance(f, dict)
            else getattr(f, 'frequency', 0)
        ),
        reverse=True
    )

    # Build rows, capped at 6 (matching the screenshot)
    for faq in all_faqs:
        if counter > 6:
            break

        # Extract fields (handle both dict and object access)
        q_ar = faq.get('question_ar') if isinstance(faq, dict) else getattr(faq, 'question_ar', '')
        a_ar = faq.get('answer_ar') if isinstance(faq, dict) else getattr(faq, 'answer_ar', '')
        freq = faq.get('frequency', 0) if isinstance(faq, dict) else getattr(faq, 'frequency', 0)

        # Include FAQs with frequency >= 1 (supported by at least one case)
        # Lower frequencies indicate emerging patterns and should not be filtered out
        if q_ar and a_ar and freq >= 1:
            rows.append({
                '#': str(counter),
                'السؤال': q_ar,
                'الإجابة الصحيحة': a_ar,
                'التكرار': str(int(freq)),
            })
            counter += 1

    return rows


def _build_notification_rows(state: PipelineState) -> List[Dict[str, str]]:
    """
    Build notification opportunity rows for proactive alerts.

    DATA SOURCE: state.notification_opportunities from Stage 4 analysis (LLM-generated).

    COLUMNS (matching section 6.2 screenshot):
    1. نوع الإشعار - notification_type (e.g., "إشعار فوري استلام")
    2. الحالات المُلغاة - cases_eliminated (actual count from pipeline reconciliation)
    3. محتوى الإشعار (مثال) - content_summary (concrete example message)
    4. القناة - channel (delivery method, e.g., "SMS + Push تلقائي")
    5. الأثر المتوقع - expected_impact (business outcome grounded in case analysis)

    ACCURACY GUARANTEE:
    - cases_eliminated values come from Stage 4 reconciliation against ground-truth case counts
    - expected_impact must be grounded in actual case evidence, never LLM-hallucinated
    - No invented percentages or unmeasured benefits

    Args:
        state: Pipeline state containing notification_opportunities

    Returns:
        List of row dicts with section 6.2 table columns
    """
    rows = []

    if hasattr(state, 'notification_opportunities') and state.notification_opportunities:
        for notif in state.notification_opportunities:
            if isinstance(notif, dict):
                # Direct field mapping from Stage 4 notification_opportunities
                # Fields: notification_type, cases_eliminated, channel, content_summary, expected_impact
                # All 5 fields must be present in the LLM response (required by schema) and non-empty
                notification_type = notif.get('notification_type', '')
                cases_eliminated = notif.get('cases_eliminated', '')
                content_summary = notif.get('content_summary', '')
                channel = notif.get('channel', '')
                expected_impact = notif.get('expected_impact', '')

                # STRICT VALIDATION: Only include rows where ALL required fields are present and non-empty
                # This ensures table quality:
                # - notification_type: must describe what notification (إشعار استلام, تحديث حالة, etc)
                # - cases_eliminated: must be positive integer (count of preventable cases)
                # - channel: must specify delivery method (SMS, Push, بريد إلكتروني, etc)
                # - content_summary: must describe WHEN and WHAT info the notification sends
                # - expected_impact: must describe business outcome grounded in actual case analysis
                if notification_type and cases_eliminated and channel and content_summary and expected_impact:
                    row = {
                        'نوع الإشعار': notification_type,
                        'الحالات المُلغاة': str(cases_eliminated),
                        'محتوى الإشعار (مثال)': content_summary,
                        'القناة': channel,
                        'الأثر المتوقع': expected_impact,
                    }
                    rows.append(row)
                elif notif:
                    # Log when opportunities are filtered out due to incomplete fields
                    missing = []
                    if not notification_type:
                        missing.append('notification_type')
                    if not cases_eliminated:
                        missing.append('cases_eliminated')
                    if not channel:
                        missing.append('channel')
                    if not content_summary:
                        missing.append('content_summary')
                    if not expected_impact:
                        missing.append('expected_impact')
                    print(f"[DigitalTransform] Filtered incomplete notification: missing={missing}")

    return rows


def generate_digital_transformation_section(state: PipelineState, api_key: str) -> Dict[str, Any]:
    """
    Generate the Digital Transformation section (Section 6) for the report.

    This section presents:
    - FAQ section addressing common citizen questions
    - Proactive notification opportunities
    - Vision for digital maturity

    Args:
        state: Pipeline state with validated FAQs and notification opportunities
        api_key: Anthropic API key for LLM calls (if needed for refinement)

    Returns:
        ISSUE 4 FIX: Dict with 'section_body', 'faq_table', 'notification_table' keys
        as expected by build_digital_transformation_section in stage6_json_report.py
    """
    # Build FAQ rows
    faq_rows = _build_faq_rows_for_transform(state)

    # Build notification rows
    notif_rows = _build_notification_rows(state)

    # Generate section body (intro paragraph)
    month_year = convert_month_year_to_arabic(state.month_year) if state.month_year else 'الفترة الحالية'
    section_body = (
        f"تمثل خطة التحويل الرقمي رؤية شاملة لتحسين تجربة المتعاملين من خلال الخدمات الرقمية. "
        f"بناءً على تحليل البيانات من {month_year}، تم تحديد الأولويات التالية:"
    )

    # Return structure matching what build_digital_transformation_section expects
    return {
        'section_body': section_body,
        'faq_table': faq_rows,  # List of dicts with 'السؤال' and 'الإجابة' keys
        'notification_table': notif_rows,  # List of dicts with notification details
    }
