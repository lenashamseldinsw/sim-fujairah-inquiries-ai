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
  Table columns: السؤال | الإجابة
  Pre-computed from state: faq_candidates, validated_faqs
  LLM-written: refined Q&A

Sub-section 6.2 — فرص الإخطار الاستباقي
  Table columns: نوع الإخطار | السيناريو | الفائدة المتوقعة
  Pre-computed from state: notification_opportunities
  LLM-written: detailed scenarios and benefits

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
    Build FAQ rows from validated FAQs and candidates for the transformation section.

    ISSUE 4 FIX: Return rows matching build_digital_transformation_section columns:
    #, السؤال, الإجابة المقترحة, التكرار

    Args:
        state: Pipeline state containing validated_faqs and faq_candidates

    Returns:
        List of row dicts with FAQ columns
    """
    rows = []
    counter = 1

    # Add validated FAQs first (higher confidence)
    if state.validated_faqs:
        for faq in state.validated_faqs:
            if counter > 5:
                break
            q = faq.get('question') if isinstance(faq, dict) else getattr(faq, 'question', '')
            a = faq.get('answer') if isinstance(faq, dict) else getattr(faq, 'answer', '')
            freq = faq.get('frequency', faq.get('case_count', '')) if isinstance(faq, dict) else getattr(faq, 'frequency', '')
            if q and a:
                rows.append({
                    '#': str(counter),
                    'السؤال': q,
                    'الإجابة المقترحة': a,
                    'التكرار': str(freq) if freq else '—',
                })
                counter += 1

    # Add candidates as fallback
    if state.faq_candidates and counter <= 5:
        for candidate in state.faq_candidates:
            if counter > 5:
                break
            q = candidate.get('question') if isinstance(candidate, dict) else getattr(candidate, 'question', '')
            a = candidate.get('answer') if isinstance(candidate, dict) else getattr(candidate, 'answer', '')
            freq = candidate.get('frequency', candidate.get('case_count', '')) if isinstance(candidate, dict) else getattr(candidate, 'frequency', '')
            if q and a:
                rows.append({
                    '#': str(counter),
                    'السؤال': q,
                    'الإجابة المقترحة': a,
                    'التكرار': str(freq) if freq else '—',
                })
                counter += 1

    return rows


def _build_notification_rows(state: PipelineState) -> List[Dict[str, str]]:
    """
    Build notification opportunity rows for proactive alerts.

    ISSUE 4 FIX: Return rows matching build_digital_transformation_section columns:
    نوع الإشعار, الحالات المُلغاة, محتوى الإشعار (مثال), القناة, الأثر المتوقع

    Args:
        state: Pipeline state containing notification_opportunities

    Returns:
        List of row dicts with notification columns
    """
    rows = []

    if hasattr(state, 'notification_opportunities') and state.notification_opportunities:
        for notif in state.notification_opportunities:
            if isinstance(notif, dict):
                # Map state notification fields to expected row columns
                row = {
                    'نوع الإشعار': notif.get('type', notif.get('notification_type', '')),
                    'الحالات المُلغاة': str(notif.get('cases_eliminated', notif.get('case_count', ''))),
                    'محتوى الإشعار (مثال)': notif.get('content', notif.get('example_message', '')),
                    'القناة': notif.get('channel', notif.get('delivery_channel', '')),
                    'الأثر المتوقع': notif.get('expected_benefit', notif.get('expected_impact', '')),
                }
                rows.append(row)

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
