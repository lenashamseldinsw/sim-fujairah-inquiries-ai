"""
The report's static text, in both languages (Prerequisites §4).

Section titles, table headers, category names and data notes — everything the
report prints that no model writes. Kept in one place so the Arabic and English
reports cannot drift, and so a wording ruling is a one-line change.
"""
from __future__ import annotations

from ..api.models.enums import SECTION_TITLES as _SECTION_TITLES

__all__ = ["SECTION_TITLES", "SECTION_NUMBER", "T", "CATEGORY", "GAP_TYPE", "GUIDEBOOK_STATUS", "PRIORITY",
           "HORIZON", "EFFORT", "FAQ_STATUS", "t"]

# The section titles are part of the contract (a request names sections by them).
SECTION_TITLES = _SECTION_TITLES

# "القسم 01 — …" / "Section 01 — …", numbered among the shown numbered sections.
SECTION_NUMBER = {"ar": "القسم {n:02d} — {title}", "en": "Section {n:02d} — {title}"}

# Every other fixed string, keyed for lookup with ``t(key, lang)``.
T: dict[str, dict[str, str]] = {
    "doc_title": {"ar": "تقرير تحليل استفسارات المتعاملين", "en": "Customer Inquiries Analysis Report"},
    "footer": {"ar": "سري — للاستخدام الداخلي  |  صفحة ", "en": "Confidential — Internal Use Only  |  Page "},
    "end_of_report": {"ar": "نهاية التقرير", "en": "End of report"},
    "toc": {"ar": "المحتويات", "en": "Contents"},
    "prepared_by": {"ar": "تحليل NoveIntelligence", "en": "Analysis by NoveIntelligence"},
    # KPI tiles (S0)
    "kpi_total": {"ar": "إجمالي الحالات", "en": "Total cases"},
    "kpi_closed": {"ar": "الحالات المغلقة", "en": "Closed cases"},
    "kpi_classified": {"ar": "الحالات المصنفة", "en": "Classified cases"},
    "kpi_reclass": {"ar": "نسبة إعادة التصنيف", "en": "Reclassification rate"},
    "kpi_within": {"ar": "الالتزام بزمن الاستجابة (ضمن المهلة)", "en": "Response-time compliance (within deadline)"},
    "kpi_digital": {"ar": "نسبة القنوات الرقمية", "en": "Digital-channel share"},
    "kpi_top": {"ar": "الخدمة الرئيسية الأعلى", "en": "Top main service"},
    "kpi_main": {"ar": "الخدمات الرئيسية", "en": "Main services"},
    "kpi_sub": {"ar": "التصنيفات الفرعية", "en": "Sub-classifications"},
    "kpi_tx": {"ar": "الاستفسارات لكل 100 معاملة", "en": "Inquiries per 100 transactions"},
    "kpi_bundles": {"ar": "الحزم الموضوعية", "en": "Thematic bundles"},
    "kpi_queue": {"ar": "حالات بثقة منخفضة بعد المراجعة", "en": "Low-confidence cases after review"},
    "indicator": {"ar": "المؤشر", "en": "Indicator"},
    "value": {"ar": "القيمة", "en": "Value"},
    # Common headers
    "count": {"ar": "العدد", "en": "Count"},
    "cases": {"ar": "الحالات", "en": "Cases"},
    "share": {"ar": "النسبة", "en": "Share"},
    "month": {"ar": "الشهر", "en": "Month"},
    "change": {"ar": "التغير", "en": "Change"},
    "channel": {"ar": "القناة", "en": "Channel"},
    "digital": {"ar": "رقمية", "en": "Digital"},
    "yes": {"ar": "نعم", "en": "Yes"},
    "no": {"ar": "لا", "en": "No"},
    "main_service": {"ar": "الخدمة الرئيسية", "en": "Main service"},
    "sub_classification": {"ar": "التصنيف الفرعي", "en": "Sub-classification"},
    "contact_type": {"ar": "نوع التواصل", "en": "Contact type"},
    "recorded": {"ar": "التصنيف المسجَّل", "en": "Recorded"},
    "actual": {"ar": "التصنيف الصحيح", "en": "Actual"},
    "case_id": {"ar": "رقم الطلب", "en": "Case ID"},
    "evidence": {"ar": "الدليل", "en": "Evidence"},
    "recorded_tag": {"ar": "الوسم المسجَّل", "en": "Recorded tag"},
    "match": {"ar": "نسبة التطابق", "en": "Match rate"},
    "status": {"ar": "الحالة", "en": "Status"},
    "target": {"ar": "المستهدف", "en": "Target"},
    "framework": {"ar": "الإطار", "en": "Framework"},
    "recommendation": {"ar": "التوصية", "en": "Recommendation"},
    "department": {"ar": "الإدارة", "en": "Department"},
    "dominant_type": {"ar": "النوع الغالب", "en": "Main contact type"},
    "severity": {"ar": "شدة الطلب", "en": "Severity"},
    "friction": {"ar": "نقطة الاحتكاك", "en": "Friction point"},
    "root_cause_category": {"ar": "فئة السبب الجذري", "en": "Root-cause category"},
    "remedy": {"ar": "الإجراء التحسيني", "en": "Improvement action"},
    "topic": {"ar": "الموضوع", "en": "Topic"},
    "guidebook_status": {"ar": "وضعه في دليل الخدمات", "en": "Guidebook status"},
    "excerpt": {"ar": "مقتطف من الدليل", "en": "Guidebook excerpt"},
    "gap_type": {"ar": "نوع الفجوة", "en": "Gap type"},
    "priority": {"ar": "الأولوية", "en": "Priority"},
    "question": {"ar": "السؤال", "en": "Question"},
    "answer": {"ar": "الإجابة المقترحة", "en": "Proposed answer"},
    "frequency": {"ar": "التكرار", "en": "Frequency"},
    "faq_status": {"ar": "الحالة في القائمة المعتمدة", "en": "Catalogue status"},
    "notification": {"ar": "نوع الإشعار", "en": "Notification"},
    "trigger": {"ar": "الحدث المُطلِق", "en": "Trigger"},
    "sample_message": {"ar": "نموذج الرسالة", "en": "Sample message"},
    "eliminable": {"ar": "حالات ضمن مجموعات قابلة للمعالجة بالإشعار", "en": "Cases in groups a notification addresses"},
    "use_case": {"ar": "حالة الاستخدام", "en": "Use case"},
    "function": {"ar": "الوظيفة", "en": "Function"},
    "source_ref": {"ar": "المرجع", "en": "Source"},
    "effort": {"ar": "الجهد", "en": "Effort"},
    "impact_cases": {"ar": "الحالات المستهدفة", "en": "Cases addressed"},
    "initiative": {"ar": "المبادرة", "en": "Initiative"},
    "horizon": {"ar": "الأفق الزمني", "en": "Horizon"},
    "description": {"ar": "الوصف", "en": "Description"},
    "bundle": {"ar": "الحزمة الموضوعية", "en": "Thematic bundle"},
    "root_cause": {"ar": "السبب الجذري", "en": "Root cause"},
    "near_over": {"ar": "قرب انتهاء المهلة أو تجاوزها", "en": "Near or over deadline"},
    "inquiries": {"ar": "الاستفسارات", "en": "Inquiries"},
    "transactions": {"ar": "المعاملات", "en": "Transactions"},
    "per_100": {"ar": "لكل 100 معاملة", "en": "Per 100 transactions"},
    "howto_cases": {"ar": "حالات «الكيفية»", "en": "How-to cases"},
    "coverage": {"ar": "تغطية الأسئلة الشائعة", "en": "FAQ coverage"},
    "provenance": {"ar": "مصدر التصنيف", "en": "Classification source"},
    "previous": {"ar": "الفترة السابقة", "en": "Previous period"},
    "current": {"ar": "الفترة الحالية", "en": "This period"},
    "owner": {"ar": "المالك", "en": "Owner"},
    "source": {"ar": "المصدر", "en": "Source"},
    "nature": {"ar": "الطبيعة", "en": "Nature"},
    "size": {"ar": "الحجم", "en": "Size"},
    "period": {"ar": "الفترة", "en": "Period"},
    "field": {"ar": "الحقل", "en": "Field"},
    "role": {"ar": "الدور في التحليل", "en": "Role in the analysis"},
    "step": {"ar": "الخطوة", "en": "Step"},
    "item": {"ar": "البند", "en": "Item"},
    "finding": {"ar": "النتيجة", "en": "Finding"},
    # Subsection titles
    "s1_findings": {"ar": "أبرز المؤشرات", "en": "Headline indicators"},
    # The sample output's subsection titles.
    "comparison_with": {"ar": "المقارنة مع {period}", "en": "Comparison with {period}"},
    "st_monthly": {"ar": "التوزيع الشهري للحالات", "en": "Monthly distribution of cases"},
    "st_services": {"ar": "التوزيع حسب الخدمة الرئيسية", "en": "Distribution by main service"},
    "st_tx": {"ar": "الاستفسارات مقابل المعاملات", "en": "Inquiries against transactions"},
    "st_channels": {"ar": "توزيع القنوات", "en": "Channel distribution"},
    "st_recorded_true": {"ar": "التصنيف المسجل في النظام مقابل الموضوع الحقيقي", "en": "Recorded classification against the true subject"},
    "st_timeliness": {"ar": "الالتزام بزمن الاستجابة", "en": "Response-time compliance"},
    "rc_matrix": {"ar": "ارتباط الحزم بالخدمات الرئيسية", "en": "Bundles by main service"},
    "rc_per_bundle": {"ar": "الحزم بالتفصيل", "en": "Bundles in detail"},
    "rc_top": {"ar": "الأسباب الجذرية الأكثر تكراراً", "en": "Most frequent root causes"},
    "rc_timeliness": {"ar": "الالتزام بزمن الاستجابة حسب الحزمة", "en": "Response-time compliance by bundle"},
    "dc_howto": {"ar": "خريطة أسئلة «الكيفية» حسب الخدمة", "en": "How-to questions by service"},
    "dc_priority_faqs": {"ar": "الأسئلة الشائعة ذات الأولوية", "en": "Priority frequently asked questions"},
    "rm_immediate": {"ar": "الأفق الفوري — أول 30 يوماً", "en": "Immediate horizon — the first 30 days"},
    "rm_short": {"ar": "الأفق القصير — من شهر إلى ثلاثة أشهر", "en": "Short horizon — one to three months"},
    "rm_medium": {"ar": "الأفق المتوسط — من ثلاثة إلى ستة أشهر", "en": "Medium horizon — three to six months"},
    "cn_findings": {"ar": "أبرز النتائج", "en": "Key findings"},
    "cn_recommendations": {"ar": "التوصيات", "en": "Recommendations"},
    "ap_methodology": {"ar": "منهجية التحليل", "en": "Analysis methodology"},
    "ap_events": {"ar": "رصد نوعي", "en": "Qualitative observations"},
    "ap_frictions": {"ar": "نقاط الاحتكاك في رحلة المتعامل", "en": "Friction points in the customer journey"},
    "ap_sources": {"ar": "المصادر المُحلَّلة", "en": "Sources analysed"},
    "ap_method": {"ar": "منهجية التصنيف", "en": "Classification method"},
    "ap_fields": {"ar": "الحقول المُحلَّلة", "en": "Fields analysed"},
    "ap_quality": {"ar": "جودة التصنيف", "en": "Classification quality"},
    "s1_comparison": {"ar": "المقارنة مع الفترة السابقة", "en": "Comparison with the previous period"},
    "s2_sources": {"ar": "2.1 المصادر المُحلَّلة", "en": "2.1 Sources analysed"},
    "s2_method": {"ar": "2.2 منهجية التصنيف", "en": "2.2 Classification method"},
    "s2_fields": {"ar": "2.3 الحقول المُحلَّلة", "en": "2.3 Fields analysed"},
    "s2_quality": {"ar": "2.4 جودة التصنيف", "en": "2.4 Classification quality"},
    "s2_note": {"ar": "2.5 ملاحظة المنهجية", "en": "2.5 Methodology note"},
    "s3_overview": {"ar": "3.1 الإحصاءات العامة والتوزيع الشهري", "en": "3.1 Overview and monthly distribution"},
    "s3_types": {"ar": "3.2 التوزيع الفعلي لأنواع التواصل وإعادة التصنيف", "en": "3.2 Actual contact types and reclassification"},
    "s3_services": {"ar": "3.3 الخدمات الرئيسية والتصنيفات الفرعية", "en": "3.3 Main services and sub-classifications"},
    "s3_by_type": {"ar": "3.4 التصنيفات الفرعية حسب نوع التواصل", "en": "3.4 Sub-classifications by contact type"},
    "s3_recorded_true": {"ar": "3.5 التصنيف المسجَّل في النظام مقابل الموضوع الحقيقي", "en": "3.5 Recorded classification vs true subject"},
    "s3_channels": {"ar": "3.6 القنوات", "en": "3.6 Channels"},
    "s3_timeliness": {"ar": "3.7 الالتزام بزمن الاستجابة", "en": "3.7 Response-time compliance"},
    "s3_tx": {"ar": "3.8 الاستفسارات مقابل المعاملات", "en": "3.8 Inquiries vs transactions"},
    "s3_oos": {"ar": "3.9 حالات خارج النطاق (تُسلَّم إلى تحليل الشكاوى)", "en": "3.9 Out-of-scope cases (handed to complaints analytics)"},
    "s3_severity": {"ar": "3.10 شدة الطلب", "en": "3.10 Severity"},
    "s3_departments": {"ar": "3.11 التوزيع حسب الإدارات", "en": "3.11 Distribution by department"},
    "s3_agents": {"ar": "3.12 التوزيع على مستوى الموظفين", "en": "3.12 Owner-level distribution"},
    "s4_frictions": {"ar": "4.1 نقاط الاحتكاك", "en": "4.1 Friction points"},
    "s5_gaps": {"ar": "5.1 جدول الفجوات الرقمية", "en": "5.1 Digital gap table"},
    "s5_roots": {"ar": "5.2 الأسباب الجذرية لاستمرار المشكلات", "en": "5.2 Root causes behind the gaps"},
    "s5_opportunity": {"ar": "5.3 فرص المحتوى الرقمي", "en": "5.3 Digital-content opportunities"},
    "s6_faqs": {"ar": "6.1 الأسئلة الشائعة المقترحة", "en": "6.1 Proposed FAQs"},
    "s6_notifications": {"ar": "6.2 فرص الإشعارات الاستباقية", "en": "6.2 Proactive-notification opportunities"},
    "s7_comparison": {"ar": "المقارنة مع الفترة السابقة", "en": "Period comparison"},
    "s9_findings": {"ar": "النتائج الرئيسية", "en": "Key findings"},
    "s9_recommendations": {"ar": "التوصيات", "en": "Recommendations"},
    "s9_kpis": {"ar": "المؤشرات الرئيسية", "en": "Key indicators"},
    "s10_bundles": {"ar": "10.1 توزيع الحزم الموضوعية", "en": "10.1 Bundle distribution"},
    "s10_matrix": {"ar": "10.2 الحزم حسب الخدمة الرئيسية", "en": "10.2 Bundles by main service"},
    "s10_per_bundle": {"ar": "10.3 الحزم بالتفصيل", "en": "10.3 Bundles in detail"},
    "s10_top": {"ar": "10.4 الأسباب الجذرية الأكثر تكراراً", "en": "10.4 Most frequent root causes"},
    "s10_timeliness": {"ar": "10.5 الالتزام بزمن الاستجابة حسب الحزمة", "en": "10.5 Timeliness by bundle"},
    "data_note": {"ar": "ملاحظة البيانات", "en": "Data note"},
    "omitted": {"ar": "لم يُدرج هذا القسم لعدم تزويد مدخله", "en": "This section is omitted because its input was not provided"},
}

CATEGORY = {
    "missing_info": {"ar": "معلومات غير متوفرة", "en": "Missing information"},
    "inaccessible_info": {"ar": "معلومات يصعب الوصول إليها", "en": "Hard-to-reach information"},
    "no_proactive_notification": {"ar": "غياب الإشعار الاستباقي", "en": "No proactive notification"},
    "platform_bug": {"ar": "خلل تقني في المنصة", "en": "Platform defect"},
    "policy_complexity": {"ar": "تعقيد الإجراءات أو السياسات", "en": "Procedure or policy complexity"},
}
GAP_TYPE = {
    "missing_content": {"ar": "محتوى غير متوفر", "en": "Missing content"},
    "unclear_content": {"ar": "محتوى غير واضح", "en": "Unclear content"},
    "not_digital": {"ar": "خدمة غير مرقمنة", "en": "Not digitised"},
    "not_proactive": {"ar": "غياب الإشعار الاستباقي", "en": "Not proactive"},
    "policy_complexity": {"ar": "تعقيد السياسات", "en": "Policy complexity"},
}
GUIDEBOOK_STATUS = {
    "Covered": {"ar": "مغطى", "en": "Covered"},
    "Partially Covered": {"ar": "مغطى جزئياً", "en": "Partially covered"},
    "Missing": {"ar": "غير مغطى", "en": "Not covered"},
}
PRIORITY = {
    "high": {"ar": "فرصة رقمية ذات أولوية عالية", "en": "High-priority digital opportunity"},
    "medium": {"ar": "فرصة رقمية ذات أولوية متوسطة", "en": "Medium-priority digital opportunity"},
    "low": {"ar": "مغطى — للمتابعة", "en": "Covered — monitor"},
}
HORIZON = {
    "immediate": {"ar": "فوري (30 يوماً)", "en": "Immediate (30 days)"},
    "short": {"ar": "قصير (1–3 أشهر)", "en": "Short (1–3 months)"},
    "medium": {"ar": "متوسط (3–6 أشهر)", "en": "Medium (3–6 months)"},
}
EFFORT = {
    "low": {"ar": "منخفض", "en": "Low"},
    "medium": {"ar": "متوسط", "en": "Medium"},
    "high": {"ar": "مرتفع", "en": "High"},
}
FAQ_STATUS = {
    "new": {"ar": "جديد — غير منشور", "en": "New — not published"},
    "in_catalogue": {"ar": "موجود في قائمة الأسئلة المعتمدة", "en": "In the FAQ catalogue"},
    "in_guidebook": {"ar": "موجود في دليل الخدمات", "en": "In the guidebook"},
}


def t(key: str, lang: str) -> str:
    return T[key][lang]
