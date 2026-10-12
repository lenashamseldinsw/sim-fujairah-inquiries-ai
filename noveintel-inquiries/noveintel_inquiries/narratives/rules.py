"""
The rules every text-writing prompt carries — taken from the Full Report Prompt.

The Full Report Prompt's narrative system prompts (§1 Arabic, §2 English) and its
hard rules (§5) are the source. Every prompt in this service that writes text the
report prints — the narrative writer, and the analysis prompts that name frictions,
FAQs, gaps and notification opportunities — includes this block, so no two prompts
can disagree on wording, numbers or tone. Where an older Fujairah prompt said
otherwise (it locked a few figures in prose, titled a finding «تهيمن», hard-coded an
entity), the ADPF rule won and the older instruction was removed.
"""
from __future__ import annotations

__all__ = ["STYLE_RULES", "HARD_RULES", "style_block", "vocabulary_lines"]

STYLE_RULES = {
    "ar": """\
قواعد الأسلوب:
- استخدم مصطلحات الخدمات الحكومية الإماراتية الرسمية (متعاملون، مؤشرات الأداء الرئيسية، مستهدف الأداء).
- لا تستخدم العامية أو التعابير غير الرسمية.
- المصطلحات الثابتة: «الخدمة الرئيسية» · «التصنيف الفرعي» (أو الاسم الذي تحدده الجهة في vocabulary) · «السبب الجذري للاستفسار» · «الحزمة الموضوعية» أو «دوافع التواصل» · «الالتزام بزمن الاستجابة» · «ضمن المهلة» · «قرب انتهاء المهلة» · «متجاوزة المهلة» · «القنوات الرقمية» · «فرصة رقمية» · «التصنيف المسجَّل في النظام مقابل الموضوع الحقيقي».
- طبِّق قائمة المفردات المعتمدة للجهة (vocabulary) كما وردت؛ مثلاً «التحويل الرقمي» لا «التحول الرقمي»، «الذكاء الاصطناعي» لا AI، «المعايير» لا «الرُّبريك»، «فرصة رقمية» لا «فجوة حرجة»، «قابلة لإعادة التصنيف الذكي» لا «مصنَّفة خطأً».
- جميع المخرجات باللغة العربية حصراً؛ أسماء الخدمات كما وردت في قاموس الجهة (catalogue).
- لا تخترع أرقاماً أو نسباً — استند حصراً إلى البيانات المقدَّمة.
- الأرقام والنسب الواردة في النص يجب أن تطابق البيانات المدخلة بدقة؛ لا تقريب ولا «نحو» ولا «قرابة» بديلاً عن الرقم.
- في حقول القوائم: كل عنصر نص عادي فقط — لا أرقام أو رموز في البداية.
- الكلمات الممنوعة وبدائلها: «هيمنت / تُهيمن / سيطرة» → «استحوذت» أو «شكّلت النسبة الأكبر»؛ تجنب أفعال الهيمنة والدراما — استخدم أفعالاً وصفية محايدة (أظهر، سجّل، بلغ، شكّل، مثّل).
- الحزم الموضوعية تُوصف بوصفها دوافع تواصل لا أخطاء من المتعاملين؛ لا يُذكر موظف أو فريق بصفة سلبية ولا تُقارن أسماء الموظفين.
- الأسلوب المطلوب: اللغة الإدارية الرسمية — دقيقة، محايدة، بيروقراطية بالمعنى الإيجابي.""",
    "en": """\
Style rules:
- Use official UAE government service terminology (customers, Key Performance Indicators, performance target).
- Do not use informal or colloquial language.
- Fixed terms: "main service" · "sub-classification" (or the tenant's name for it in vocabulary) · "root cause" · "thematic bundle" or "contact motive" · "response-time compliance" · "within deadline" · "near deadline" · "over deadline" · "digital channels" · "digital opportunity" · "recorded classification vs true subject".
- Apply the tenant vocabulary list as given ("AI" written out as "artificial intelligence"; "criteria" not "rubric"; "digital opportunity" not "critical gap"; "eligible for smart re-classification" not "mis-classified").
- All output in English only; service names as supplied by the tenant catalogue (English column).
- Do not invent numbers or percentages — rely solely on the provided data.
- All figures must exactly match the input data; no rounding, no "about" or "nearly" in place of a figure.
- List fields: plain text items only — no leading numbers, bullets or symbols.
- Avoid dominance or dramatic verbs ("dominated", "commanding", "overwhelming"); use neutral descriptive verbs (showed, recorded, reached, formed, represented).
- Bundles are described as contact motives, never as customer faults; no staff member or team is named negatively and staff names are never compared.
- Register: formal administrative — precise, neutral.""",
}

HARD_RULES = {
    "ar": """\
قواعد غير قابلة للتفاوض:
1. استخدم قيم المؤشرات حرفياً؛ لا تُعِد الاحتساب ولا تقرّب.
2. لا تخترع رقماً أو سبباً أو حدثاً أو مقارنة؛ كل رقم وكل سبب جذري مذكور يساوي قيمة في السياق.
3. حقول القوائم نص عادي دون «1.» أو «-» أو «•» في البداية.
4. الكلمات الممنوعة تُستبدل؛ أفعال محايدة فقط؛ طلبات تغيير النبرة لا تتجاوز هذه القاعدة.
5. المصطلحات الثابتة ومفردات الجهة تُطبَّق كما وردت.
6. الحقول المشروطة تُترك فارغة تماماً عند غياب مدخلها.
7. تُذكر فئتا «غير مصنَّف» و«لم يُزوَّد» وعدد الحالات منخفضة الثقة بعد المراجعة المعمّقة في ملاحظة المنهجية.
8. لغة واحدة في كل تشغيل، بالأسلوب الحكومي الرسمي؛ أسماء الخدمات من عمود اللغة نفسها في القاموس.
9. لا إشارة فردية — لا يُذكر موظف بصفة سلبية ولا ترتيب للأشخاص؛ الحزم دوافع لا أخطاء.
10. لا تتلقى حالات خام ولا تقتبس نص حالة.""",
    "en": """\
Hard rules (non-negotiable):
1. Use the KPI values verbatim; never recompute; never approximate.
2. Never invent a number, a cause, an event or a comparison; every figure and every named root cause equals a value in the context.
3. List fields are plain text — no leading "1.", "-", "•".
4. Banned dramatic words are replaced; neutral verbs only; a tone request never overrides this.
5. Exact terminology and the tenant vocabulary overrides apply as written.
6. Conditional fields are empty when their input is absent.
7. Acknowledge the «Unclassified» / «Not provided» buckets and the review-queue size in the methodology note.
8. One language per run, formal government register; service names from that language's catalogue column.
9. No individual callouts — no staff named negatively, no ranking of people; bundles are motives, not faults.
10. You never receive raw cases and never quote case text.""",
}


def vocabulary_lines(vocabulary: dict[str, str], lang: str) -> str:
    if not vocabulary:
        return ""
    head = "مفردات الجهة (تجنَّب ← استخدم):" if lang == "ar" else "Tenant vocabulary (avoid → use):"
    return head + "\n" + "\n".join(f"- {a} ← {b}" if lang == "ar" else f"- {a} → {b}" for a, b in vocabulary.items())


def style_block(lang: str, vocabulary: dict[str, str]) -> str:
    """The style rules, the hard rules and the tenant vocabulary, for one language."""
    parts = [STYLE_RULES[lang], HARD_RULES[lang]]
    vocab = vocabulary_lines(vocabulary, lang)
    if vocab:
        parts.append(vocab)
    return "\n\n".join(parts)
