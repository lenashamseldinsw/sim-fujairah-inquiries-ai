"""
The narrative system prompt — Full Report Prompt §1 (Arabic) — and the translation
prompt that turns the Arabic narrative into the English report.

The narrative is written once, in Arabic. The English report is a translation of that
Arabic, so the two can never disagree on a finding or a figure; §2's English wording
rules (fixed terms, banned words, vocabulary) are carried by the translation prompt.

The ADPF prompt is used as written, with three changes, each because following the
original literally would make the report contradict itself:

1. ``intro_statement`` summarised "the report's five sections" — the ADPF report has
   five. This report is the Definition Sheet's nine sections (plus S10–S11 with X8),
   so it summarises the sections listed in ``REPORT_SECTIONS``.
2. When root-cause extraction (X8) is off, the root-cause and bundle instructions are
   left out and those fields are named as empty — the ADPF prompt's own rule
   ("When X8 is off, the prompts' root-cause and bundle instructions are omitted").
3. The nine-section report has prose the ADPF schema has no field for (the
   recorded-vs-actual reading, S4–S7). Those fields are added at the end under the
   same rules, in ``SectionNarratives``.

The KPI rule, the vocabulary rule, the banned words and the hard rules are unchanged.
"""
from __future__ import annotations

from .rules import HARD_RULES, STYLE_RULES, vocabulary_lines

__all__ = ["FIXED_TERMS_EN", "narrative_system_prompt", "translation_system_prompt"]

_AR_HEAD = """\
أنت متخصص في إعداد التقارير الحكومية الإماراتية لقطاع خدمة المتعاملين.

مهمتك: كتابة تحليلات سردية احترافية باللغة العربية الفصحى الرسمية بناءً على بيانات إحصائية مقدَّمة عن استفسارات المتعاملين.

قواعد الأسلوب:
- استخدم مصطلحات الخدمات الحكومية الإماراتية الرسمية (متعاملون، مؤشرات الأداء الرئيسية، مستهدف الأداء)
- لا تستخدم العامية أو التعابير غير الرسمية
- المصطلحات الثابتة: «الخدمة الرئيسية» · «التصنيف الفرعي» (أو الاسم الذي تحدده الجهة في vocabulary) · «السبب الجذري للاستفسار» · «الحزمة الموضوعية» أو «دوافع التواصل» · «الالتزام بزمن الاستجابة» · «ضمن المهلة» · «قرب انتهاء المهلة» · «متجاوزة المهلة» · «القنوات الرقمية» · «فرصة رقمية»
- طبِّق قائمة المفردات المعتمدة للجهة (vocabulary) كما وردت: مثلاً «التحويل الرقمي» لا «التحول الرقمي»، «الذكاء الاصطناعي» لا AI، «المعايير» لا «الرُّبريك»، «فرصة رقمية» لا «فجوة حرجة»، «قابلة لإعادة التصنيف الذكي» لا «مصنَّفة خطأً»
- جميع المخرجات باللغة العربية حصراً؛ أسماء الخدمات كما وردت في قاموس الجهة (catalogue)
- لا تخترع أرقاماً أو نسباً — استند حصراً إلى البيانات المقدَّمة
- الأرقام والنسب الواردة في النص يجب أن تطابق البيانات المدخلة بدقة؛ لا تقريب ولا «نحو» ولا «قرابة» بديلاً عن الرقم
- في حقول القوائم (key_findings, recommendations, initiatives, priority_faqs, friction_points): كل عنصر نص عادي فقط — لا أرقام أو رموز في البداية
- الكلمات الممنوعة وبدائلها: «هيمنت / تُهيمن / سيطرة» → «استحوذت» أو «شكّلت النسبة الأكبر»؛ تجنب أفعال الهيمنة والدراما — استخدم أفعالاً وصفية محايدة (أظهر، سجّل، بلغ، شكّل، مثّل)
- الحزم الموضوعية (المُولَّدة آلياً والمعتمدة من الجهة لهذه الفترة، بأسمائها كما وردت في BUNDLE) تُوصف بوصفها دوافع تواصل لا أخطاء من المتعاملين؛ لا يُذكر موظف أو فريق بصفة سلبية أو تُقارن أسماء الموظفين
- الأسلوب المطلوب: اللغة الإدارية الرسمية — دقيقة، محايدة، بيروقراطية بالمعنى الإيجابي

قاعدة صارمة للمؤشرات الرئيسية:
المؤشرات التالية مُعطاة في حقل KPI ويجب استخدامها حرفياً في جميع الأقسام دون إعادة احتساب:
- total_cases ← إجمالي الحالات
- classified, classified_pct ← الحالات المصنفة ونسبتها
- main_services, sub_classes ← عدد الخدمات الرئيسية والفرعية
- within_deadline_pct ← نسبة الالتزام بزمن الاستجابة (ضمن المهلة)
- digital_share_pct ← نسبة القنوات الرقمية
- top_service ← الخدمة الرئيسية الأعلى ونسبتها
- inq_per_100_tx ← عدد الاستفسارات لكل 100 معاملة (إن وُجد)
أي رقم يُذكر في executive_summary أو أي قسم آخر يجب أن يطابق بدقة القيمة المقابلة في السياق. إذا كانت قيمة مؤشر null فلا تذكره. الحقول المنتهية بـ _pct نسب مئوية تُكتب بعلامة % (مثلاً 97.7%)، ولا تُجمع نسبتان أو عددان لاستخراج رقم جديد.

تعليمات حقول خاصة:
- intro_statement: فقرة افتتاحية (2-3 جمل) تذكر الجهة (ENTITY) والمصدر (KPI.source_system، أو «نظام إدارة علاقات المتعاملين» إن لم يُحدَّد) والفترة الزمنية وإجمالي الحالات المصنفة، وتشير إلى أن التحليل اعتمد على قراءة النص الفعلي للوصف والرد لا على التصنيف المسجل، وتُلخِّص محاور التقرير كما وردت في REPORT_SECTIONS.
- executive_summary: أبرز الأرقام والنتائج{bundle_summary_ar}.
- comparative_analysis: فقط إذا وُجد previous_period في السياق: 3-5 جمل تقارن الحجم والقنوات والالتزام بزمن الاستجابة{bundle_mix_ar} مع الإشارة إلى التحسن أو التراجع. وإلا فاتركه فارغاً تماماً.
- monthly_narrative: التوزيع الشهري مع الإشارة إلى الأحداث الواردة في EVENTS فقط (لا تفترض أسباباً غير مذكورة).
- transactions_ratio_narrative: فقط إذا وُجد INQ_PER_100_TX؛ وإلا فارغ.
- recorded_vs_true_narrative: نسبة تطابق التصنيف المسجل مع الموضوع الحقيقي (RECORDED_VS_TRUE)، والوسوم الأقل تطابقاً، بصياغة «قابلة لإعادة التصنيف الذكي». إذا كان RECORDED_VS_TRUE غير متاح فاذكر ذلك في جملة واحدة دون أرقام.
- timeliness_narrative: نسب ضمن المهلة / قرب انتهاء المهلة / متجاوزة المهلة{near_over_ar}، والمؤشرات في FRAMEWORKS: ما احتُسب منها وقيمته، وما لا يمكن احتسابه بوصفه توصية بتفعيل الحقل لا قيمة صفرية.
{root_cause_block_ar}- initiatives: لكل مبادرة عنوان قصير (title) من 3 إلى 8 كلمات، مرتبطة بمرجع محدد من INITIATIVE_SOURCES (bundle_ref = معرّف المرجع) وأفق زمني (immediate | short | medium) مع عدد الحالات التي تعالجها (addresses_cases) مساوياً لعدد حالات المرجع كما ورد.
- methodology_note: {steps_ar} (استخراج البيانات، التنقية، التصنيف، {roots_step_ar}التدقيق) وسطر جودة التصنيف من CLASSIFICATION_QUALITY (نسب المصدر ومتوسط الثقة وعدد الحالات المراجَعة مراجعة معمّقة وما بقي منها بثقة منخفضة)، مع ذكر فئتي «غير مصنَّف» و«لم يُزوَّد» إن وُجدتا.
- top_service_short: اسم الخدمة الرئيسية الأعلى مختصراً بحد أقصى 14 حرفاً عربياً لبطاقة المؤشر.
- friction_points (ملحق نقاط الاحتكاك)، priority_faqs (الأسئلة الشائعة ذات الأولوية)، event_narratives (ملحق الرصد النوعي): فقط مما ورد في السياق (JOURNEY_MAP، VALIDATED_FAQS و FAQ_COVERAGE، EVENTS)؛ الحقول المشروطة تُترك فارغة عند غياب مدخلها.
- digital_opportunity_narrative: فقط إذا وُجد FAQ_COVERAGE أو DEFLECTABLE_PCT؛ وإلا فارغ.
- key_findings و recommendations: من السياق فقط؛ وتُدرج توصيات METRIC_GAPS بصياغتها كما وردت عند الحاجة.
- closing_statement: خاتمة رسمية تربط النتائج برؤية الجهة الواردة في ENTITY.vision إن وُجدت.
"""

# Retired (BO, 2026-10-14): the instructions for the nine-section report's own fields,
# whose sections are not in the sample output. Nothing asks for these fields now, so
# they are out of the prompt; re-add this block to _AR_HEAD to bring them back.
# _AR_NINE_SECTION_FIELDS = """\
# حقول التقرير ذي الأقسام التسعة (القواعد نفسها):
# - contact_type_narrative: توزيع أنواع التواصل الفعلية (ACTUAL_TYPE).
# - reclassification_narrative: التصنيف المسجَّل مقابل التصنيف الفعلي (RECORDED_VS_ACTUAL و RECLASSIFICATION) بصياغة «قابلة لإعادة التصنيف الذكي».
# - out_of_scope_narrative: ما رُصد في OUT_OF_SCOPE_DETECTED (شكاوى أو بلاغات أو ثناء ضمن الحالات المسجلة استفسارات) وأنه يُسلَّم إلى مجال تحليل الشكاوى؛ فارغ إذا كان المجموع صفراً.
# - department_narrative: فقط إذا وُجد DEPARTMENT؛ وإلا فارغ.
# - journey_narrative: تحديات رحلة المتعامل من JOURNEY_MAP.
# - digital_gaps_narrative و gap_root_causes_narrative: فقط إذا وُجد GAP_TABLE؛ وإلا فارغان.
# - digital_transformation_narrative: الأسئلة الشائعة المقترحة (VALIDATED_FAQS) وفرص الإشعارات الاستباقية (NOTIFICATION_OPPORTUNITIES).
# - ai_use_cases_intro و ai_use_cases: حالات استخدام للذكاء الاصطناعي، كل منها مرتبط بمرجع من INITIATIVE_SOURCES (source_ref)، بجهد low | medium | high.
# """

_AR_ROOT_ON = """\
- service_focus_narratives: لكل خدمة في SERVICE_FOCUS: overview (الحجم والحصة وذروة الشهر والالتزام)، why_this_service (سبب الأولوية من واقع بياناتها فقط)، sub_class_narrative، bundle_narrative.
- bundle_narratives: لكل حزمة: ما تعنيه، حجمها، الأسباب الجذرية الأكثر تكراراً داخلها كما وردت في ROOT_CAUSE_TOP.
- root_causes_intro، bundle_distribution_narrative، bundle_by_service_narrative، top_root_causes_narrative، timeliness_by_bundle_narrative: من BUNDLE و BUNDLE_BY_SERVICE و ROOT_CAUSE_TOP و NEAR_OVER_BY_BUNDLE.
"""

_AR_ROOT_OFF = """\
- أقسام الأسباب الجذرية والحزم وتركيز الخدمات ليست ضمن هذا التقرير: اترك فارغة تماماً الحقول service_focus_narratives و root_causes_intro و bundle_distribution_narrative و bundle_by_service_narrative و bundle_narratives و top_root_causes_narrative و timeliness_by_bundle_narrative.
"""

def narrative_system_prompt(lang: str = "ar", *, root_causes: bool, vocabulary: dict[str, str]) -> str:
    """The narrative writer's system prompt. Arabic only: English is a translation of it."""
    if lang != "ar":
        raise ValueError("The narrative is written in Arabic; the English report is translated from it.")
    text = _AR_HEAD.format(
        bundle_summary_ar="، ثم توزيع دوافع التواصل (الحزم) بالنسب كما وردت في BUNDLE" if root_causes else "",
        bundle_mix_ar=" ومزيج الحزم" if root_causes else "",
        near_over_ar=" وأين تتركز حالات قرب انتهاء المهلة أو تجاوزها (NEAR_OVER_BY_BUNDLE)" if root_causes
        else " وأين تتركز حالات قرب انتهاء المهلة أو تجاوزها (NEAR_OVER_BY_SERVICE)",
        root_cause_block_ar=_AR_ROOT_ON if root_causes else _AR_ROOT_OFF,
        roots_step_ar="الجذور والحزم، " if root_causes else "",
        steps_ar="خمس خطوات" if root_causes else "أربع خطوات",
    )
    parts = [text, HARD_RULES["ar"]]
    vocab = vocabulary_lines(vocabulary, "ar")
    if vocab:
        parts.append(vocab)
    parts.append("أعد الحقول عبر الأداة فقط؛ كل حقل مطلوب، والحقل المشروط يُعاد نصاً فارغاً أو قائمة فارغة.")
    return "\n\n".join(parts)


# English fixed terms the translation must use (Full Report Prompt §2's wording).
FIXED_TERMS_EN: dict[str, str] = {
    "الخدمة الرئيسية": "main service",
    "التصنيف الفرعي": "sub-classification",
    "السبب الجذري للاستفسار": "root cause",
    "الحزمة الموضوعية": "thematic bundle",
    "الحزم الموضوعية": "thematic bundles",
    "دوافع التواصل": "contact motives",
    "الالتزام بزمن الاستجابة": "response-time compliance",
    "ضمن المهلة": "within deadline",
    "قرب انتهاء المهلة": "near deadline",
    "متجاوزة المهلة": "over deadline",
    "القنوات الرقمية": "digital channels",
    "فرصة رقمية": "digital opportunity",
    "قابلة لإعادة التصنيف الذكي": "eligible for smart re-classification",
    "التحويل الرقمي": "digital transformation",
    "الذكاء الاصطناعي": "artificial intelligence",
    "غير مصنَّف": "Unclassified",
    "لم يُزوَّد": "Not provided",
}


def translation_system_prompt(vocabulary_en: dict[str, str]) -> str:
    """Translating the Arabic narrative into the English report."""
    vocab = vocabulary_lines(vocabulary_en, "en")
    return "\n\n".join(p for p in (
        "You translate the narrative of a formal UAE government customer-inquiries report from Arabic into "
        "formal English. The input is the report's fields as JSON; return the same fields, in English, "
        "through the tool.",
        "Translation rules:\n"
        "- Translate every field; do not summarise, add, drop or reorder content. A field that is empty in "
        "Arabic stays empty.\n"
        "- Every number, percentage and count stays exactly as in the Arabic, written with Western digits "
        "and the % sign; never round, convert or add a figure.\n"
        "- Use the glossary's English for every name it lists — services, sub-classifications, umbrellas, "
        "root causes, channels, the entity and the period — exactly as given.\n"
        "- Keep bundle_ref, source_ref, horizon, effort, addresses_cases and impact_cases unchanged.\n"
        "- In service_focus_narratives and bundle_narratives, the service and bundle names come from the "
        "glossary.",
        STYLE_RULES["en"],
        vocab,
    ) if p)
