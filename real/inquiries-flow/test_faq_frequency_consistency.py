"""
Test: FAQ Frequency Consistency

Ensures that FAQ frequencies shown in Section 6.1 (Digital Transformation) match:
1. The validated_faqs frequency from Stage 5 (authoritative source)
2. Actual case counts in state.all_classified (ground truth)
3. Consistent calculation across both inquiries and complaints flows

This prevents the issue where different sections show different frequency values
for the same FAQ.
"""

import pytest
from typing import List
from collections import defaultdict

from pipeline.state import PipelineState, FAQCandidate, CaseRow
from pipeline.generate_digital_transformation_section import (
    _build_faq_rows_for_transform,
    _build_faq_prompt_context,
)


class TestFAQFrequencyConsistency:
    """Test suite for FAQ frequency consistency across the report."""

    @pytest.fixture
    def sample_state(self):
        """Create sample state with test FAQs and cases."""
        state = PipelineState()

        # Create test cases with sub_classifications
        state.all_classified = [
            CaseRow(
                case_number="1", case_title="Case 1", date_opened="2024-01-01",
                case_channel="app", description="Test", resolution_response="OK",
                sla_color="نعم", case_type="طلب", service_name="Service",
                actual_contact_type="طلب", classification_reason="test",
                confidence=0.9, misclassification="لا",
                sub_classification="طلب تجديد رخصة أو ملكية"
            ),
            CaseRow(
                case_number="2", case_title="Case 2", date_opened="2024-01-01",
                case_channel="app", description="Test", resolution_response="OK",
                sla_color="نعم", case_type="طلب", service_name="Service",
                actual_contact_type="طلب", classification_reason="test",
                confidence=0.9, misclassification="لا",
                sub_classification="طلب تجديد رخصة أو ملكية"
            ),
            CaseRow(
                case_number="3", case_title="Case 3", date_opened="2024-01-01",
                case_channel="app", description="Test", resolution_response="OK",
                sla_color="نعم", case_type="طلب", service_name="Service",
                actual_contact_type="طلب", classification_reason="test",
                confidence=0.9, misclassification="لا",
                sub_classification="طلب تجديد رخصة أو ملكية"
            ),
            CaseRow(
                case_number="4", case_title="Case 4", date_opened="2024-01-01",
                case_channel="app", description="Test", resolution_response="OK",
                sla_color="نعم", case_type="طلب", service_name="Service",
                actual_contact_type="طلب", classification_reason="test",
                confidence=0.9, misclassification="لا",
                sub_classification="متابعة طلب مقدم"
            ),
            CaseRow(
                case_number="5", case_title="Case 5", date_opened="2024-01-01",
                case_channel="app", description="Test", resolution_response="OK",
                sla_color="نعم", case_type="طلب", service_name="Service",
                actual_contact_type="طلب", classification_reason="test",
                confidence=0.9, misclassification="لا",
                sub_classification="متابعة طلب مقدم"
            ),
            CaseRow(
                case_number="6", case_title="Case 6", date_opened="2024-01-01",
                case_channel="app", description="Test", resolution_response="OK",
                sla_color="نعم", case_type="شكوى", service_name="Service",
                actual_contact_type="شكوى", classification_reason="test",
                confidence=0.9, misclassification="لا",
                sub_classification="شكوى عن عدم استلام الخدمة"
            ),
        ]

        # Create validated FAQs with frequencies matching actual case counts
        # These should be reconciled in Stage 5
        state.validated_faqs = [
            FAQCandidate(
                question="كيفية تجديد الرخصة؟",
                question_ar="كيفية تجديد الرخصة؟",
                answer="يمكنك تجديد الرخصة عبر الموقع",
                answer_ar="يمكنك تجديد الرخصة عبر الموقع",
                frequency=3,  # Matches 3 cases with this sub_classification
                validation_status="OK",
                sub_classification="طلب تجديد رخصة أو ملكية",
                top_level="طلب",
            ),
            FAQCandidate(
                question="أين متابعة الطلب؟",
                question_ar="أين متابعة الطلب؟",
                answer="يمكنك متابعة طلبك في التطبيق",
                answer_ar="يمكنك متابعة طلبك في التطبيق",
                frequency=2,  # Matches 2 cases with this sub_classification
                validation_status="OK",
                sub_classification="متابعة طلب مقدم",
                top_level="طلب",
            ),
            FAQCandidate(
                question="لم لم أستقبل الخدمة؟",
                question_ar="لم لم أستقبل الخدمة؟",
                answer="تتبع شحنتك",
                answer_ar="تتبع شحنتك",
                frequency=1,  # Matches 1 case with this sub_classification
                validation_status="OK",
                sub_classification="شكوى عن عدم استلام الخدمة",
                top_level="شكوى",
            ),
            FAQCandidate(
                question="سؤال بدون حالات",
                question_ar="سؤال بدون حالات",
                answer="جواب بدون حالات",
                answer_ar="جواب بدون حالات",
                frequency=0,  # Should be EXCLUDED (no matching cases)
                validation_status="OK",
                sub_classification="غير موجود",
                top_level="استفسار",
            ),
        ]

        state.total_cases = len(state.all_classified)
        return state

    def test_faq_rows_use_validated_frequency(self, sample_state):
        """Test that FAQ table rows use frequency from validated_faqs, not LLM-invented values."""
        rows = _build_faq_rows_for_transform(sample_state)

        # Should have 3 rows (frequency > 0)
        assert len(rows) == 3, f"Expected 3 rows (frequency > 0), got {len(rows)}"

        # Extract frequencies from display rows
        displayed_freqs = [int(row["التكرار"]) for row in rows]

        # Should match the validated_faqs frequencies in descending order
        expected_freqs = [3, 2, 1]  # Sorted descending
        assert displayed_freqs == expected_freqs, (
            f"Displayed frequencies {displayed_freqs} don't match "
            f"validated_faqs frequencies {expected_freqs}"
        )

    def test_faq_prompt_context_uses_same_frequency(self, sample_state):
        """Test that LLM prompt context uses the same frequency values."""
        prompt_context = _build_faq_prompt_context(sample_state)

        # Should have 3 entries (frequency > 0)
        assert len(prompt_context) == 3, f"Expected 3 entries, got {len(prompt_context)}"

        # Extract frequencies from prompt context
        prompt_freqs = [entry["frequency"] for entry in prompt_context]

        # Should match the validated_faqs frequencies in descending order
        expected_freqs = [3, 2, 1]
        assert prompt_freqs == expected_freqs, (
            f"Prompt context frequencies {prompt_freqs} don't match "
            f"validated_faqs frequencies {expected_freqs}"
        )

    def test_faq_display_and_context_frequencies_match(self, sample_state):
        """Test that display rows and prompt context show the same frequencies."""
        rows = _build_faq_rows_for_transform(sample_state)
        context = _build_faq_prompt_context(sample_state)

        # Both should have same count
        assert len(rows) == len(context), (
            f"Display rows ({len(rows)}) and context entries ({len(context)}) "
            f"should be equal"
        )

        # Frequencies should match
        for i, (row, ctx) in enumerate(zip(rows, context)):
            display_freq = int(row["التكرار"])
            context_freq = ctx["frequency"]
            assert display_freq == context_freq, (
                f"Row {i}: Display frequency {display_freq} != "
                f"Context frequency {context_freq}"
            )

    def test_zero_frequency_faqs_excluded(self, sample_state):
        """Test that FAQs with frequency=0 are excluded from display."""
        rows = _build_faq_rows_for_transform(sample_state)
        context = _build_faq_prompt_context(sample_state)

        # The 4th FAQ has frequency=0 and should NOT appear
        assert len(rows) == 3, "FAQ with frequency=0 should be excluded"
        assert len(context) == 3, "FAQ with frequency=0 should be excluded from context"

        # Verify no zero frequencies in output
        for row in rows:
            freq = int(row["التكرار"])
            assert freq > 0, f"Found zero frequency in display rows: {row}"

        for entry in context:
            freq = entry["frequency"]
            assert freq > 0, f"Found zero frequency in context: {entry}"

    def test_faq_frequency_matches_actual_case_count(self, sample_state):
        """Test that FAQ frequencies match actual counts in all_classified."""
        # Build actual sub_classification counts
        actual_counts = defaultdict(int)
        for case in sample_state.all_classified:
            if case.sub_classification:
                actual_counts[case.sub_classification] += 1

        # Get FAQ prompt context (which has both frequency and sub_classification)
        context = _build_faq_prompt_context(sample_state)

        # For each FAQ, verify frequency matches actual case count for its sub_classification
        for entry in context:
            sub_class = entry["sub_classification"]
            faq_freq = entry["frequency"]
            actual_count = actual_counts.get(sub_class, 0)

            assert faq_freq == actual_count, (
                f"FAQ sub_classification '{sub_class}': "
                f"frequency={faq_freq} but actual case count={actual_count}"
            )

    def test_faq_frequency_sorted_descending(self, sample_state):
        """Test that FAQs are sorted by frequency in descending order."""
        rows = _build_faq_rows_for_transform(sample_state)
        freqs = [int(row["التكرار"]) for row in rows]

        # Should be in descending order
        sorted_freqs = sorted(freqs, reverse=True)
        assert freqs == sorted_freqs, (
            f"Frequencies {freqs} are not in descending order. "
            f"Expected {sorted_freqs}"
        )

    def test_faq_fallback_to_candidates(self, sample_state):
        """Test that FAQ rows fall back to faq_candidates if validated_faqs empty."""
        sample_state.validated_faqs = []
        sample_state.faq_candidates = [
            FAQCandidate(
                question="Fallback FAQ",
                question_ar="سؤال بديل",
                answer="Answer",
                answer_ar="إجابة",
                frequency=5,
                validation_status="OK",
                sub_classification="test",
                top_level="استفسار",
            ),
        ]

        rows = _build_faq_rows_for_transform(sample_state)
        assert len(rows) == 1, "Should fall back to faq_candidates"
        assert int(rows[0]["التكرار"]) == 5, "Should use candidate frequency"

    def test_empty_faq_sources(self, sample_state):
        """Test handling of empty FAQ sources."""
        sample_state.validated_faqs = []
        sample_state.faq_candidates = []

        rows = _build_faq_rows_for_transform(sample_state)
        context = _build_faq_prompt_context(sample_state)

        assert len(rows) == 0, "Should return empty rows for no FAQs"
        assert len(context) == 0, "Should return empty context for no FAQs"

    def test_max_faq_rows_cap(self, sample_state):
        """Test that FAQ output is capped at MAX_FAQ_ROWS."""
        # Add more FAQs to exceed the cap (currently 7)
        for i in range(10):
            sample_state.validated_faqs.append(
                FAQCandidate(
                    question=f"FAQ {i+5}",
                    question_ar=f"سؤال {i+5}",
                    answer=f"Answer {i+5}",
                    answer_ar=f"إجابة {i+5}",
                    frequency=10 - i,  # Decreasing frequency
                    validation_status="OK",
                    sub_classification=f"sub_{i}",
                    top_level="استفسار",
                )
            )

        rows = _build_faq_rows_for_transform(sample_state)
        context = _build_faq_prompt_context(sample_state)

        # Should be capped at 7 (MAX_FAQ_ROWS)
        assert len(rows) <= 7, f"Rows exceed max cap: {len(rows)}"
        assert len(context) <= 7, f"Context exceeds max cap: {len(context)}"


class TestCrossFlowConsistency:
    """Test consistency between inquiries and complaints flow FAQ implementations."""

    def test_inquiries_faq_structure_matches_complaints(self):
        """
        Test that inquiries flow FAQ structure matches complaints flow.

        Both should return rows with same columns:
        - # (row number)
        - التكرار (frequency as string integer)
        """
        state = PipelineState()
        state.validated_faqs = [
            FAQCandidate(
                question="Test",
                question_ar="اختبار",
                answer="Answer",
                answer_ar="إجابة",
                frequency=5,
                validation_status="OK",
                sub_classification="test",
                top_level="استفسار",
            ),
        ]
        state.all_classified = [
            CaseRow(
                case_number="1", case_title="Case 1", date_opened="2024-01-01",
                case_channel="app", description="Test", resolution_response="OK",
                sla_color="نعم", case_type="استفسار", service_name="Service",
                actual_contact_type="استفسار", classification_reason="test",
                confidence=0.9, misclassification="لا", sub_classification="test"
            ),
            CaseRow(
                case_number="2", case_title="Case 2", date_opened="2024-01-01",
                case_channel="app", description="Test", resolution_response="OK",
                sla_color="نعم", case_type="استفسار", service_name="Service",
                actual_contact_type="استفسار", classification_reason="test",
                confidence=0.9, misclassification="لا", sub_classification="test"
            ),
        ]

        rows = _build_faq_rows_for_transform(state)

        # Verify structure
        assert len(rows) > 0
        assert "#" in rows[0], "Missing row number column"
        assert "التكرار" in rows[0], "Missing frequency column"
        assert isinstance(rows[0]["#"], str), "Row number should be string"
        assert isinstance(rows[0]["التكرار"], str), "Frequency should be string"
        assert rows[0]["التكرار"].isdigit(), "Frequency should be numeric string"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
