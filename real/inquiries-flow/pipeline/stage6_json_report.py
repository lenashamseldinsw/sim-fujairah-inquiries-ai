"""
STAGE 6: JSON Report Dictionary Generator

Transforms pipeline outputs (stages 1-5) + report_sections into a dictionary
matching demo cache structure. NO FILE I/O — returns dict for passing through functions.

Structure:
- metadata: Document info (title, author, dates, counts)
- charts: Array of chart definitions
- sections: Array of report sections with subsections, tables, charts

Each section has:
- id: Unique identifier (section_<num>_<slug>)
- title: Section title (language-appropriate for AR/EN versions)
- level: Heading level (1-3)
- content: Narrative text
- tables: Array of data tables
- charts: Array of embedded charts
- subsections: Nested sections
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import Counter, defaultdict
from .state import PipelineState, CaseRow


class JSONReportBuilder:
    """Builds demo-compatible report dictionary from pipeline state."""

    def __init__(self, state: PipelineState):
        self.state = state
        self.section_counter = 0
        self.table_counter = 0

    def next_section_id(self, slug: str) -> str:
        """Generate unique section ID."""
        self.section_counter += 1
        return f"section_{self.section_counter}_{slug}"

    def next_table_index(self) -> int:
        """Get next table index."""
        idx = self.table_counter
        self.table_counter += 1
        return idx

    def build_metadata(self) -> Dict[str, Any]:
        """Build document metadata."""
        return {
            "extraction_version": 1,
            "document_name": f"تقرير تحليل استفسارات المتعاملين — {self.state.month_year or 'Q1 2026'}",
            "document_path": "",
            "metadata": {
                "title": f"تقرير تحليل استفسارات المتعاملين — {self.state.month_year or 'Q1 2026'}",
                "author": "AI Analysis Pipeline",
                "created": datetime.now().isoformat(),
                "modified": datetime.now().isoformat(),
                "total_paragraphs": len(self.state.all_classified),
                "total_tables": len(self.state.gap_table) + 3
            }
        }

    def build_classification_chart(self) -> Optional[Dict[str, Any]]:
        """Build bar chart comparing original vs actual classification."""
        if not self.state.all_classified:
            return None

        # Count classifications
        # FIX 1: Use case.case_type directly — no string parsing needed
        original_counts = defaultdict(int)
        actual_counts = defaultdict(int)

        for case in self.state.all_classified:
            actual_counts[case.actual_contact_type] += 1
            original_counts[case.case_type] += 1

        # Categories in order
        categories = ["شكوى", "استفسار", "طلب", "شكر وثناء"]

        return {
            "type": "bar",
            "title": "التصنيف الأصلي مقارنةً بالتصنيف الصحيح",
            "categories": categories,
            "series": [
                {
                    "name": "التصنيف الأصلي",
                    "data": [float(original_counts.get(c, 0)) for c in categories]
                },
                {
                    "name": "التصنيف الصحيح",
                    "data": [float(actual_counts.get(c, 0)) for c in categories]
                }
            ],
            "colors": ["#2E5090", "#B68A35"]
        }

    def build_executive_summary_section(self, lang: str = "ar") -> Dict[str, Any]:
        """BUG 3: Build executive summary section by reading from language-specific dict."""
        # Read from correct language dict
        report_sections = (
            self.state.report_sections_ar if lang == "ar"
            else self.state.report_sections_en
        )
        exec_data = report_sections.get('executive_summary', {})

        # Use language-appropriate content from state
        body = exec_data.get('body', '')
        # Don't show Arabic stub in English output
        if lang == 'en' and body and not any(c.isascii() for c in body[:20]):
            body = ''
        # Fall back to computed summary if body is empty or stub
        if not body or body.startswith('جاري') or body.startswith('Generating'):
            total = len(self.state.all_classified)
            complaint_count = sum(
                1 for c in self.state.all_classified
                if c.actual_contact_type == 'شكوى'
            )
            complaint_rate = (complaint_count / total * 100) if total > 0 else 0
            if lang == 'ar':
                body = (
                    f"يُقدّم هذا التقرير تحليلاً ذكياً مُندمجاً لـ {total} حالة مغلقة "
                    f"من بيانات CRM لشرطة الفجيرة "
                    f"{self.state.month_year or 'الربع الأول 2026'}. "
                    f"الهدف ليس عرض الأرقام، بل تحويل البيانات إلى قرارات ورؤى قابلة للتنفيذ. "
                    f"المُستجد الجوهري: بعد تطبيق معايير التصنيف الدقيقة، "
                    f"الشكاوى باتت تُمثّل {complaint_rate:.1f}% من عبء العمل الفعلي."
                )
            else:
                body = (
                    f"This report presents an intelligent analysis of {total} closed cases "
                    f"from Fujairah Police CRM "
                    f"({self.state.month_year or 'Q1 2026'}). "
                    f"After applying precise classification criteria, complaints represent "
                    f"{complaint_rate:.1f}% of the actual workload."
                )
        content = body

        core_message = (
            exec_data.get('core_message')
            or exec_data.get('raw_data', {}).get('core_message_ar', '')
        )

        # Read key_findings from tables[0] (stored as raw list by artifacts)
        # or from raw_data if available
        raw_findings = []
        raw_data = exec_data.get('raw_data', {})
        if raw_data and raw_data.get('key_findings'):
            raw_findings = raw_data['key_findings']
        elif exec_data.get('tables') and exec_data['tables']:
            candidate = exec_data['tables'][0]
            if isinstance(candidate, list):
                raw_findings = candidate

        # Build language-appropriate findings table from raw_findings
        findings_table = None
        if raw_findings and isinstance(raw_findings, list) and len(raw_findings) > 0:
            if lang == 'ar':
                rows = [{
                    '#': str(f.get('number', i+1)),
                    'الاكتشاف': f.get('title_ar', ''),
                    'الوصف': f.get('description_ar', ''),
                    'مستوى الأهمية': f.get('importance_ar', '🔴 حرجة')
                } for i, f in enumerate(raw_findings)]
                columns = ['#', 'الاكتشاف', 'الوصف', 'مستوى الأهمية']
            else:
                rows = [{
                    '#': str(f.get('number', i+1)),
                    'Discovery': f.get('title_en', ''),
                    'Description': f.get('description_en', ''),
                    'Importance': f.get('importance_en', '🔴 Critical')
                } for i, f in enumerate(raw_findings)]
                columns = ['#', 'Discovery', 'Description', 'Importance']

            findings_table = {
                'columns': columns,
                'rows': rows,
                'row_count': len(rows),
                'col_count': 4,
                'original_index': self.next_table_index()
            }

        # Fall back to computed findings table if LLM data unavailable
        if not findings_table:
            findings_table = self._build_key_findings_table()

        # Build section structure
        result = {
            "id": self.next_section_id(
                "أولا_الملخص_التنفيذي" if lang == "ar" else "executive_summary"
            ),
            "title": (
                "أولاً: الملخص التنفيذي — التحليلات الرئيسية"
                if lang == "ar" else "Executive Summary — Key Analyses"
            ),
            "level": 2,
            "content": content,
            "tables": [],
            "charts": [],
            "subsections": []
        }

        if findings_table:
            result["subsections"] = [{
                "id": self.next_section_id(
                    "النتائج_الرئيسية" if lang == "ar" else "key_findings"
                ),
                "title": "النتائج الرئيسية" if lang == "ar" else "Key Findings",
                "level": 2,
                "content": core_message,
                "tables": [findings_table],
                "charts": []
            }]

        return result

    def _build_key_findings_table(self) -> Optional[Dict[str, Any]]:
        """Build key findings table."""
        if not self.state.all_classified:
            return None

        total = len(self.state.all_classified)
        # FIX 1: Use centralized reclassification count from state
        misclassified = self.state.reclassified_count
        misclassification_rate = self.state.reclassification_rate
        complaint_count = sum(1 for c in self.state.all_classified if c.actual_contact_type == "شكوى")

        rows = [
            {
                "#": "1",
                "الاكتشاف": f"تصنيف غير دقيق بنسبة {misclassification_rate:.1f}%",
                "الوصف": f"{misclassified} من {total} حالة كانت مُصنَّفة أصلاً بشكل غير صحيح.",
                "مستوى الأهمية": "🔴 حرجة"
            },
            {
                "#": "2",
                "الاكتشاف": f"الشكاوى تهيمن بـ {(complaint_count/total*100):.1f}% على عبء العمل",
                "الوصف": f"الشكاوى تُمثّل {complaint_count} حالة ({(complaint_count/total*100):.1f}%) من العبء الفعلي.",
                "مستوى الأهمية": "🔴 حرجة"
            }
        ]

        return {
            "columns": ["#", "الاكتشاف", "الوصف", "مستوى الأهمية"],
            "rows": rows,
            "row_count": len(rows),
            "col_count": 4,
            "original_index": self.next_table_index()
        }

    def build_classification_analysis_section(self) -> Dict[str, Any]:
        """Build detailed classification analysis section."""
        total = len(self.state.all_classified)

        # Count by type
        type_counts = Counter(c.actual_contact_type for c in self.state.all_classified)

        distribution_text = f"تحليل {total} حالة مغلقة يكشف صورةً مغايرةً تماماً للتصنيف الأصلي. بعد تطبيق معيار التمييز الدقيق بين الشكوى والطلب والاستفسار:"

        distribution_table = self._build_distribution_table(type_counts, total)
        classification_chart = self.build_classification_chart()

        return {
            "id": self.next_section_id("ثالثا_التحليل_الأول"),
            "title": "ثالثاً: التحليل الأول — خريطة تصنيف الطلبات",
            "level": 2,
            "content": "",
            "tables": [],
            "charts": [],
            "subsections": [
                {
                    "id": self.next_section_id("31_التوزيع_الفعلي"),
                    "title": "3.1 التوزيع الفعلي لأنواع التواصل",
                    "level": 2,
                    "content": distribution_text,
                    "tables": [distribution_table] if distribution_table else [],
                    "charts": [classification_chart] if classification_chart else [],
                    "subsections": []
                }
            ]
        }

    def _build_distribution_table(self, type_counts: Counter, total: int) -> Optional[Dict[str, Any]]:
        """Build classification distribution table."""
        categories = ["شكوى", "استفسار", "طلب", "شكر وثناء"]

        rows = []
        for cat in categories:
            count = type_counts.get(cat, 0)
            pct = (count / total * 100) if total > 0 else 0

            rows.append({
                "نوع التواصل": cat,
                "العدد": str(count),
                "النسبة": f"{pct:.1f}%",
                "تغيُّر التصنيف": f"تم إعادة تصنيف {count} حالة",
                "قابلية التحويل الرقمي": "مسار رقمي" if cat == "شكوى" else "خدمة ذاتية"
            })

        return {
            "columns": ["نوع التواصل", "العدد", "النسبة", "تغيُّر التصنيف", "قابلية التحويل الرقمي"],
            "rows": rows,
            "row_count": len(rows),
            "col_count": 5,
            "original_index": self.next_table_index()
        }

    def build_gap_analysis_section(self) -> Optional[Dict[str, Any]]:
        """Build gap analysis section from Stage 5."""
        if not self.state.gap_table:
            return None

        gap_rows = []
        for gap in self.state.gap_table:
            # FIX 2: Use Arabic fields with fallback to English
            gap_rows.append({
                "الموضوع": gap.topic_ar or gap.topic,
                "الحالات": str(gap.case_count),
                "وضع التطبيق / الموقع الحالي": gap.guidebook_status,
                "نوع الفجوة": "🔴 حرجة" if gap.severity == "Critical" else "🟡 عالية" if gap.severity == "Medium" else "🟢 كافية",
                "التوصية": gap.recommendation_ar or gap.recommendation
            })

        gap_table = {
            "columns": ["الموضوع", "الحالات", "وضع التطبيق / الموقع الحالي", "نوع الفجوة", "التوصية"],
            "rows": gap_rows,
            "row_count": len(gap_rows),
            "col_count": 5,
            "original_index": self.next_table_index()
        }

        return {
            "id": self.next_section_id("خامسا_التحليل_الثالث"),
            "title": "خامساً: التحليل الثالث — تحليل الفجوات الرقمية",
            "level": 2,
            "content": "تحليل الفجوات الرقمية في الخدمات المتاحة.",
            "tables": [gap_table],
            "charts": [],
            "subsections": []
        }

    def build_faq_section(self) -> Optional[Dict[str, Any]]:
        """Build FAQ section from validated FAQs."""
        if not self.state.validated_faqs:
            return None

        faq_rows = []
        for i, faq in enumerate(self.state.validated_faqs[:7], 1):
            # FIX 2: Use Arabic fields with fallback to English
            faq_rows.append({
                "#": str(i),
                "السؤال": faq.question_ar or faq.question,
                "الإجابة المقترحة": faq.answer_ar or faq.answer,
                "التكرار": str(faq.frequency)
            })

        faq_table = {
            "columns": ["#", "السؤال", "الإجابة المقترحة", "التكرار"],
            "rows": faq_rows,
            "row_count": len(faq_rows),
            "col_count": 4,
            "original_index": self.next_table_index()
        }

        return {
            "id": self.next_section_id("سادسا_التحليل_الرابع"),
            "title": "سادساً: التحليل الرابع — الأسئلة الشائعة",
            "level": 2,
            "content": "الأسئلة الشائعة المستخرجة من بيانات المتعاملين.",
            "tables": [faq_table],
            "charts": [],
            "subsections": []
        }

    def build_methodology_section(self, lang: str = "ar") -> Optional[Dict[str, Any]]:
        """Build methodology section from stage6 report generation with language support."""
        report_sections = self.state.report_sections_en if lang == "en" else self.state.report_sections_ar
        if not report_sections or 'methodology' not in report_sections:
            return None

        method_data = report_sections['methodology']
        subsections = []

        # 2.1 Sources table — read from flat structure with list rows
        sources_table = None
        if method_data.get('tables') and len(method_data['tables']) > 0:
            candidate = method_data['tables'][0]
            # Validate it's a proper table dict with a list for rows
            if (isinstance(candidate, dict)
                    and isinstance(candidate.get('rows'), list)
                    and len(candidate.get('rows', [])) > 0):
                sources_table = candidate

        if sources_table:
            subsections.append({
                "id": self.next_section_id("21_المصادر_المحللة" if lang == "ar" else "21_sources_analyzed"),
                "title": "2.1  المصادر المُحلَّلة" if lang == "ar" else "2.1  Sources Analyzed",
                "level": 2,
                "content": "",
                "tables": [sources_table],
                "charts": []
            })

        # 2.2 Classification methodology — read from language-appropriate dict
        classification_content = (
            method_data.get('classification_method') or
            method_data.get('body', '')
        )
        subsections.append({
            "id": self.next_section_id("22_منهجية_التصنيف" if lang == "ar" else "22_classification_methodology"),
            "title": "2.2 منهجية التصنيف" if lang == "ar" else "2.2 Classification Methodology",
            "level": 2,
            "content": classification_content,
            "tables": [],
            "charts": []
        })

        # 2.3 Analyzed fields — read from language-appropriate dict
        fields_content = (
            method_data.get('analyzed_fields') or
            method_data.get('body', '')
        )
        subsections.append({
            "id": self.next_section_id("23_الحقول_المحللة" if lang == "ar" else "23_analyzed_fields"),
            "title": "2.3 الحقول المُحلَّلة" if lang == "ar" else "2.3 Analyzed Fields",
            "level": 2,
            "content": fields_content,
            "tables": [],
            "charts": []
        })

        return {
            "id": self.next_section_id("ثانيا_المنهجية_وطبيعة" if lang == "ar" else "methodology"),
            "title": "ثانياً: المنهجية وطبيعة المصادر" if lang == "ar" else "Methodology and Data Sources",
            "level": 2,
            "content": "",
            "tables": [],
            "charts": [],
            "subsections": subsections
        }

    def build_patterns_section(self) -> Optional[Dict[str, Any]]:
        """ISSUE 2: Build patterns section split by top_level type."""
        if not self.state.patterns:
            return None

        # Group patterns by top_level
        patterns_by_type = {}
        for pattern in self.state.patterns:
            top_level = pattern.top_level or pattern.cluster  # Use top_level field with fallback to cluster
            if top_level not in patterns_by_type:
                patterns_by_type[top_level] = []
            patterns_by_type[top_level].append(pattern)

        # Build separate tables per type with threshold of 3+ cases
        subsections = []
        all_tables = []

        for top_level, patterns_list in sorted(patterns_by_type.items()):
            if len(patterns_list) < 3:
                continue  # Skip types with < 3 patterns

            # Calculate total for this type
            type_total = sum(p.case_count for p in patterns_list)

            # Build table for this type
            pattern_rows = []
            for pattern in patterns_list[:10]:  # Limit to 10 per type
                pattern_rows.append({
                    "الفئة الفرعية": pattern.cluster_ar or pattern.cluster,
                    "العدد": str(pattern.case_count),
                    "النسبة": f"{(pattern.case_count / type_total * 100):.1f}%",  # ISSUE 2: Fixed percentage calculation
                    "الوصف": pattern.sub_theme_ar or pattern.sub_theme
                })

            pattern_table = {
                "columns": ["الفئة الفرعية", "العدد", "النسبة", "الوصف"],
                "rows": pattern_rows,
                "row_count": len(pattern_rows),
                "col_count": 4,
                "original_index": self.next_table_index()
            }

            # Map top_level to Arabic title
            type_titles = {
                "شكوى": "أنماط الشكاوى",
                "طلب": "أنماط الطلبات",
                "استفسار": "أنماط الاستفسارات",
            }
            type_title = type_titles.get(top_level, f"أنماط {top_level}")

            subsections.append({
                "id": self.next_section_id(f"3_{len(subsections)+1}_أنماط_{top_level}"),
                "title": f"3.{len(subsections)+1} {type_title}",
                "level": 2,
                "content": f"أنماط {type_title} الرئيسية ({type_total} حالة إجمالية)",
                "tables": [pattern_table],
                "charts": [],
                "subsections": []
            })
            all_tables.append(pattern_table)

        if not subsections:
            return None

        return {
            "id": self.next_section_id("ثالثا_تحليل_الأنماط"),
            "title": "ثالثاً: تفصيل الأنماط حسب نوع التصنيف",
            "level": 2,
            "content": "الأنماط الرئيسية المكتشفة في البيانات، مجمعة حسب نوع التصنيف (شكوى، طلب، استفسار).",
            "tables": [],
            "charts": [],
            "subsections": subsections
        }

    def build_report(self, lang: str = "ar") -> Dict[str, Any]:
        """BUG 1: Build complete report JSON for specified language."""
        report = self.build_metadata()

        # Sections
        sections = []

        # 1. Executive Summary
        sections.append(self.build_executive_summary_section(lang=lang))

        # ISSUE 3: 2. Methodology (inserted after Executive Summary)
        methodology_section = self.build_methodology_section(lang=lang)
        if methodology_section:
            sections.append(methodology_section)

        # 3. Classification Analysis
        sections.append(self.build_classification_analysis_section())

        # ISSUE 2: 4. Patterns (fixed to split by top_level type)
        patterns_section = self.build_patterns_section()
        if patterns_section:
            sections.append(patterns_section)

        # 5. Gap Analysis
        gap_section = self.build_gap_analysis_section()
        if gap_section:
            sections.append(gap_section)

        # 6. FAQ Section
        faq_section = self.build_faq_section()
        if faq_section:
            sections.append(faq_section)

        # Charts
        charts = []
        chart = self.build_classification_chart()
        if chart:
            charts.append(chart)

        report["charts"] = charts
        report["sections"] = sections

        return report


def generate_json_report(state: PipelineState) -> Dict[str, Any]:
    """
    BUG 1: Generate report dictionaries for both languages from pipeline state.

    Combines pipeline outputs (stages 1-5) with report_sections to build
    demo-compatible dictionary structures for both Arabic and English.

    Args:
        state: PipelineState from stages 1-5 with populated report_sections_ar/en

    Returns:
        Dict with structure: {
            'ar': {...report structure for Arabic...},
            'en': {...report structure for English...}
        }
        Ready to pass to DynamicReportDisplay.display_report_from_dict()
    """
    builder = JSONReportBuilder(state)
    return {
        'ar': builder.build_report(lang='ar'),
        'en': builder.build_report(lang='en'),
    }
