#!/usr/bin/env python3
"""
Direct test of _build_roadmap_rows() with mock state.

This bypasses the full pipeline and directly tests the roadmap row generation
to diagnose the issue with hardcoded المصدر and الجهد values.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pipeline.state import PipelineState, JourneyFriction, GapRow
from pipeline.generate_improvement_roadmap_section import _build_roadmap_rows


def create_mock_state():
    """Create a mock state with sample data from all 4 sources."""
    state = PipelineState()
    state.month_year = "Q1 2026"
    state.total_cases = 200

    # SOURCE 1: Notification opportunities
    state.notification_opportunities = [
        {
            "notification_type": "تذكير بالموعد المحدد",
            "cases_eliminated": 15,
            "content_summary": "إرسال SMS قبل انتهاء المهلة بـ 3 أيام",
            "channel": "SMS"
        },
        {
            "notification_type": "تأكيد استقبال الشكوى",
            "cases_eliminated": 10,
            "content_summary": "إشعار فوري بنجاح التسجيل",
            "channel": "SMS"
        }
    ]

    # SOURCE 2: Critical gaps (with varying case counts)
    state.gap_table = [
        GapRow(
            topic="عدم وضوح خطوات معالجة الشكوى",
            topic_ar="عدم وضوح خطوات معالجة الشكوى",
            case_count=80,  # Will cause effort="مرتفع"
            severity="Critical",
            recommendation_ar="توفير دليل خطوات معالجة واضح على البوابة",
            recommendation="",
            gap_type="Missing documentation",
            gap_type_ar="وثائق ناقصة",
            guidebook_status="Missing",
            guidebook_match_confidence=0.0,
            proactive_notification_opportunity=False,
        ),
        GapRow(
            topic="تأخر الرد على الاستفسارات",
            topic_ar="تأخر الرد على الاستفسارات",
            case_count=2,  # Will cause effort="منخفض"
            severity="Critical",
            recommendation_ar="تفعيل نظام إجابات سريعة للأسئلة الشائعة",
            recommendation="",
            gap_type="No proactive notification",
            gap_type_ar="عدم وجود إشعار استباقي",
            guidebook_status="Partially Covered",
            guidebook_match_confidence=0.6,  # Will set source to "كلا المصدرين"
            proactive_notification_opportunity=True,
        ),
        GapRow(
            topic="نموذج الشكوى معقد",
            topic_ar="نموذج الشكوى معقد",
            case_count=25,  # Will cause effort="متوسط"
            severity="Medium",  # Not Critical, should be skipped for SOURCE 2
            recommendation_ar="تبسيط النموذج إلى 5 حقول إلزامية فقط",
            recommendation="",
            gap_type="UX issue",
            gap_type_ar="مشكلة التجربة",
            guidebook_status="Missing",
            guidebook_match_confidence=0.0,
            proactive_notification_opportunity=False,
        )
    ]

    # SOURCE 3: Journey map friction points
    state.journey_map = [
        JourneyFriction(
            friction_point="عدم معرفة أماكن تقديم الشكوى",
            friction_point_ar="عدم معرفة أماكن تقديم الشكوى",
            cluster="accessibility_issue",
            cluster_ar="مشكلة وصول",
            case_count=35,
            root_cause_category="inaccessible_info",  # → effort="متوسط" normally
            sub_classification="شكاوى على الخدمات المرورية"
        ),
        JourneyFriction(
            friction_point="عدم وضوح الخطوات المطلوبة",
            friction_point_ar="عدم وضوح الخطوات المطلوبة",
            cluster="clarity_issue",
            cluster_ar="مشكلة وضوح",
            case_count=28,
            root_cause_category="missing_info",  # → effort="منخفض" normally
            sub_classification="شكاوى بشأن العملية"
        ),
    ]

    # SOURCE 4: AI use cases
    state.report_sections_ar = {
        "ai_use_cases": {
            "raw_data": {
                "use_cases_table": [
                    {
                        "tool_id": "sentiment_analysis",
                        "الأداة": "تحليل المشاعر الآلي",
                        "الأثر المتوقع": "تحديد الشكاوى ذات الأولوية",
                        "تقييم التنفيذ": "متطلب متقدم جداً — يحتاج نموذج مُدرب خاص",
                    },
                    {
                        "tool_id": "ocr_extraction",
                        "الأداة": "استخراج البيانات من الوثائق",
                        "الأثر المتوقع": "اختصار وقت الإدخال اليدوي",
                        "تقييم التنفيذ": "سهل — مكتبات OCR معروفة موجودة",
                    }
                ]
            }
        }
    }

    return state


def main():
    print("=" * 80)
    print("ROADMAP ROW GENERATION TEST (Mock State)")
    print("=" * 80)

    state = create_mock_state()

    # Check state before generation
    print("\n[INPUT STATE]")
    print(f"  Notification opportunities: {len(state.notification_opportunities)}")
    print(f"  Gap table: {len(state.gap_table)} (Critical: {sum(1 for g in state.gap_table if g.severity == 'Critical')})")
    print(f"  Journey map: {len(state.journey_map)}")
    print(f"  AI use cases: {len(state.report_sections_ar['ai_use_cases']['raw_data']['use_cases_table'])}")

    # Generate roadmap rows
    print("\n[GENERATING ROADMAP ROWS]")
    try:
        rows = _build_roadmap_rows(state)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Analyze results
    print("\n" + "=" * 80)
    print("ANALYSIS")
    print("=" * 80)

    # Source attribution
    sources_found = {}
    for row in rows:
        row_id = row.get('row_id', '')
        for prefix in ['notif_', 'gap_', 'journey_', 'ai_']:
            if row_id.startswith(prefix):
                sources_found[prefix.rstrip('_')] = sources_found.get(prefix.rstrip('_'), 0) + 1
                break

    print("\n[ROW SOURCES]")
    for source, count in sorted(sources_found.items()):
        print(f"  {source}: {count} rows")

    # Check المصدر values
    source_values = [row.get('source', '') for row in rows]
    unique_sources = set(source_values)
    print(f"\n[المصدر VALUES]")
    print(f"  Unique values: {unique_sources}")
    if len(unique_sources) == 1:
        print(f"  ⚠️  ALL ROWS HAVE SAME VALUE: '{list(unique_sources)[0]}'")
    else:
        print(f"  ✅ Values vary")
        for val in unique_sources:
            print(f"     '{val}': {source_values.count(val)} rows")

    # Check الجهد values
    effort_values = [row.get('effort', '') for row in rows]
    unique_efforts = set(effort_values)
    print(f"\n[الجهد VALUES]")
    print(f"  Unique values: {unique_efforts}")
    if len(unique_efforts) == 1:
        print(f"  ⚠️  ALL ROWS HAVE SAME VALUE: '{list(unique_efforts)[0]}'")
    else:
        print(f"  ✅ Values vary")
        for val in unique_efforts:
            print(f"     '{val}': {effort_values.count(val)} rows")

    # Detailed breakdown
    print("\n[DETAILED ROWS]")
    for i, row in enumerate(rows, 1):
        print(f"\n  Row {i}:")
        print(f"    ID: {row.get('row_id')}")
        print(f"    Horizon: {row.get('horizon')}")
        print(f"    Effort: {row.get('effort')}")
        print(f"    Source: {row.get('source')}")
        print(f"    Case count: {row.get('case_count')}")

    # Diagnosis
    print("\n" + "=" * 80)
    print("DIAGNOSIS")
    print("=" * 80)

    # Check if only notifications made it through
    if 'notification' in sources_found and len(sources_found) == 1:
        print("\n❌ PROBLEM: Only notification rows made it to the roadmap!")
        print(f"   Rows generated: {sources_found}")
        print("\n   This explains why all rows have المصدر='التحليل' and الجهد='منخفض'")
        print("   (those are the hardcoded values for notifications)\n")

        # Check why others didn't make it
        print("   Why other sources didn't contribute:")
        print(f"   - Critical gaps: {sum(1 for g in state.gap_table if g.severity == 'Critical')} available")
        print("     → These SHOULD have been included")
        print(f"   - Journey friction: {len(state.journey_map)} available")
        print("     → These SHOULD have been included")
        print(f"   - AI use cases: {len(state.report_sections_ar['ai_use_cases']['raw_data']['use_cases_table'])} available")
        print("     → These SHOULD have been included")

    elif len(unique_sources) > 1 and len(unique_efforts) > 1:
        print("\n✅ GOOD: Data varies across all 4 sources as expected!")
        print("   The issue in your actual output may be caused by:")
        print("   - state.gap_table having no 'Critical' severity gaps")
        print("   - state.journey_map being empty")
        print("   - state.notification_opportunities dominating (most impactful)")
        print("   - Semantic deduplication removing similar items")

    else:
        print(f"\n⚠️  PARTIAL: Values vary but may not cover all sources")
        print(f"   Sources found: {sources_found}")
        print(f"   Unique sources: {unique_sources}")
        print(f"   Unique efforts: {unique_efforts}")

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
