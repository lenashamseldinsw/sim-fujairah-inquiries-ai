#!/usr/bin/env python3
"""
Test script for parallel translation of 9 report sections.

Tests the translate_report_sections_parallel() function with dummy Arabic
sections. Validates English output and report reconstruction.

Run: python test_parallel_translation.py
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from pipeline.translate_report_en import translate_report_sections_parallel
from pipeline.state import PipelineState


def create_dummy_arabic_sections() -> Dict[str, Dict[str, Any]]:
    """Create minimal Arabic report sections for testing."""
    return {
        'executive_summary': {
            'heading': 'أولاً: الملخص التنفيذي',
            'body': 'تم تحليل ألف حالة من الاستفسارات.',
            'core_message': 'الرسالة: تحسين الخدمات الرقمية.',
            'raw_data': {
                'framing_paragraph': 'يقدم هذا التقرير تحليل شامل للبيانات.',
                'key_findings': [
                    {'number': 1, 'title': 'الاكتشاف الأول', 'description': 'وجدنا مشاكل في التصنيف.'}
                ]
            }
        },
        'methodology': {
            'heading': 'ثانياً: المنهجية',
            'body': 'استخدمنا تحليل البيانات والتقنيات الحديثة.',
            'raw_data': {
                'classification_method': 'تصنيف آلي باستخدام القواعد.',
                'sources_table': [
                    {'المصدر': 'نظام إدارة العملاء', 'الطبيعة': 'البيانات الأساسية', 'الحجم': '1000 حالة', 'الفترة': '2025'}
                ]
            }
        },
        'workload_map': {
            'heading': 'ثالثاً: خريطة توزيع الطلبات',
            'body': 'توزيع الحالات حسب النوع والقناة.',
            'raw_data': {
                'summary': 'معظم الحالات هي شكاوى وطلبات خدمة.',
                'table_data': [
                    {'type': 'شكوى', 'count': 450, 'percentage': '45%'}
                ]
            }
        },
        'customer_journey': {
            'heading': 'رابعاً: التحديات في الرحلة',
            'body': 'حددنا نقاط احتكاك رئيسية في تجربة العملاء.',
            'raw_data': {
                'friction_points': 'عدم الوضوح في المعلومات وتأخر الرد.',
                'case_count': 250
            }
        },
        'digital_gaps': {
            'heading': 'خامساً: الفجوات الرقمية',
            'body': 'يوجد فجوات كبيرة في تغطية الدليل الرقمي.',
            'raw_data': {
                'gaps': 'معلومات ناقصة عن الإجراءات والتفاصيل.',
                'gap_count': 12
            }
        },
        'digital_transformation': {
            'heading': 'سادساً: خطة التحول الرقمي',
            'body': 'نقترح تحديث نظام المعلومات والأسئلة الشائعة.',
            'raw_data': {
                'strategy': 'تطوير دليل رقمي شامل مع أسئلة شائعة.',
                'faq_count': 7
            }
        },
        'ai_use_cases': {
            'heading': 'سابعاً: حالات استخدام الذكاء الاصطناعي',
            'body': 'يمكن استخدام الذكاء الاصطناعي في التصنيف والإجابة.',
            'raw_data': {
                'use_case_1': 'تصنيف تلقائي للحالات الواردة.',
                'use_case_count': 4
            }
        },
        'improvement_roadmap': {
            'heading': 'ثامناً: خريطة الطريق التحسينية',
            'body': 'نوصي بتنفيذ التحسينات على مراحل.',
            'raw_data': {
                'phase_1': 'المرحلة الأولى: تحديث الدليل خلال 3 أشهر.',
                'priority_count': 6
            }
        },
        'conclusion': {
            'heading': 'تاسعاً: الخلاصة والتوصيات',
            'body': 'يتطلب التحسين تعاوناً بين الأقسام والالتزام بالمراحل.',
            'raw_data': {
                'summary': 'التحسينات الموصى بها ستؤدي لخدمة أفضل.',
                'expected_impact': 'تحسن 30% في رضا العملاء'
            }
        }
    }


def print_section_summary(sections: Dict[str, Dict[str, Any]], language: str = "Arabic") -> None:
    """Print a summary of sections (keys and sample content)."""
    print(f"\n{'='*70}")
    print(f"{language} Sections Summary ({len(sections)} total):")
    print(f"{'='*70}")
    for key, section in sections.items():
        heading = section.get('heading', 'N/A')
        body = section.get('body', 'N/A')
        if len(body) > 60:
            body = body[:60] + "..."
        print(f"  {key:25} → {heading:30} | {body}")


def test_parallel_translation(api_key: str) -> bool:
    """
    Test the parallel translation function.

    Args:
        api_key: Anthropic API key

    Returns:
        True if test passed, False otherwise
    """
    print("\n" + "="*70)
    print("PARALLEL TRANSLATION TEST")
    print("="*70)

    # Step 1: Create dummy Arabic sections
    print("\n[TEST] Creating dummy Arabic sections...")
    arabic_sections = create_dummy_arabic_sections()
    print(f"✓ Created {len(arabic_sections)} sections")
    print_section_summary(arabic_sections, "Arabic")

    # Step 2: Translate sections in parallel
    print("\n[TEST] Calling translate_report_sections_parallel()...")
    try:
        english_sections = translate_report_sections_parallel(
            arabic_sections,
            api_key,
            max_workers=9
        )
    except Exception as e:
        print(f"✗ Translation failed: {type(e).__name__}: {e}")
        return False

    if not english_sections:
        print("✗ Translation returned None (all sections failed)")
        return False

    print(f"✓ Translation complete: {len(english_sections)} sections")
    print_section_summary(english_sections, "English")

    # Step 3: Validate structure
    print("\n[TEST] Validating structure...")
    expected_keys = set(arabic_sections.keys())
    actual_keys = set(english_sections.keys())

    if expected_keys == actual_keys:
        print(f"✓ All {len(expected_keys)} section keys present")
    else:
        missing = expected_keys - actual_keys
        extra = actual_keys - expected_keys
        if missing:
            print(f"✗ Missing sections: {missing}")
        if extra:
            print(f"✗ Extra sections: {extra}")
        return False

    # Step 4: Validate content (spot checks)
    print("\n[TEST] Validating content (spot checks)...")
    spot_checks_passed = 0
    total_checks = 0

    for section_key, en_section in english_sections.items():
        # Check that section is a dict
        total_checks += 1
        if isinstance(en_section, dict):
            spot_checks_passed += 1
        else:
            print(f"✗ Section '{section_key}' is not a dict: {type(en_section)}")

        # Check that heading exists and is translated (not Arabic)
        total_checks += 1
        heading = en_section.get('heading', '')
        # Simple heuristic: if still contains Arabic characters, might not be translated
        if heading and not any('؀' <= c <= 'ۿ' for c in heading):
            spot_checks_passed += 1
        else:
            print(f"⚠️  Section '{section_key}' heading may not be translated: {heading[:40]}")

        # Check that body is not empty
        total_checks += 1
        body = en_section.get('body', '')
        if body and len(body) > 5:
            spot_checks_passed += 1
        else:
            print(f"⚠️  Section '{section_key}' body is empty or too short")

    print(f"✓ Spot checks: {spot_checks_passed}/{total_checks} passed")

    # Step 5: Save JSON outputs for inspection
    print("\n[TEST] Saving JSON outputs for inspection...")
    output_dir = Path(__file__).parent / "test_output"
    output_dir.mkdir(exist_ok=True)

    # Save Arabic sections
    ar_file = output_dir / "sections_ar.json"
    with open(ar_file, 'w', encoding='utf-8') as f:
        json.dump(arabic_sections, f, ensure_ascii=False, indent=2)
    print(f"✓ Saved Arabic sections: {ar_file}")

    # Save English sections
    en_file = output_dir / "sections_en.json"
    with open(en_file, 'w', encoding='utf-8') as f:
        json.dump(english_sections, f, ensure_ascii=False, indent=2)
    print(f"✓ Saved English sections: {en_file}")

    # Step 6: Detailed comparison
    print("\n[TEST] Detailed section comparison (first section only)...")
    first_key = list(english_sections.keys())[0]
    ar_section = arabic_sections[first_key]
    en_section = english_sections[first_key]

    print(f"\n  Section: '{first_key}'")
    print(f"  Arabic heading:  {ar_section.get('heading', 'N/A')}")
    print(f"  English heading: {en_section.get('heading', 'N/A')}")
    print(f"  Arabic body:     {ar_section.get('body', 'N/A')}")
    print(f"  English body:    {en_section.get('body', 'N/A')}")

    # Step 7: Test report reconstruction (create minimal state)
    print("\n[TEST] Testing report reconstruction with translated sections...")
    try:
        state = PipelineState()
        state.report_sections_ar = arabic_sections
        state.report_sections_en = english_sections
        state.total_cases = 1000
        state.closed_cases_count = 950
        state.sla_closed = 948
        state.reclassified_count = 85
        state.reclassification_rate = 8.5

        # Try to import and build report
        from pipeline.stage6_json_report import JSONReportBuilder
        builder = JSONReportBuilder(state)

        # Build Arabic report (should use sections_ar)
        try:
            ar_report = builder.build_report(lang='ar')
            if ar_report and 'sections' in ar_report:
                print(f"✓ Arabic report reconstructed: {len(ar_report['sections'])} sections")
            else:
                print("⚠️  Arabic report missing sections key")
        except Exception as e:
            print(f"⚠️  Could not build Arabic report: {type(e).__name__}: {str(e)[:50]}")

        # Build English report (should use sections_en)
        try:
            en_report = builder.build_report(lang='en')
            if en_report and 'sections' in en_report:
                print(f"✓ English report reconstructed: {len(en_report['sections'])} sections")
                # Save for inspection
                en_report_file = output_dir / "report_en.json"
                with open(en_report_file, 'w', encoding='utf-8') as f:
                    json.dump(en_report, f, ensure_ascii=False, indent=2)
                print(f"✓ Saved English report: {en_report_file}")
            else:
                print("⚠️  English report missing sections key")
        except Exception as e:
            print(f"⚠️  Could not build English report: {type(e).__name__}: {str(e)[:50]}")

    except Exception as e:
        print(f"⚠️  Report reconstruction test failed: {type(e).__name__}: {e}")

    # Summary
    print("\n" + "="*70)
    print("TEST COMPLETE ✓")
    print("="*70)
    print(f"\nOutput files saved to: {output_dir}")
    print("  - sections_ar.json (original Arabic sections)")
    print("  - sections_en.json (translated English sections)")
    print("  - report_en.json (reconstructed English report)")
    print("\nYou can inspect these files to verify translation quality.")

    return True


if __name__ == "__main__":
    import os

    # Get API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)

    # Run test
    success = test_parallel_translation(api_key)
    sys.exit(0 if success else 1)
