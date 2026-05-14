# Claude Code Task Specification — Inquiries Report Pipeline Fixes
**Generated from:** docx comments + xlsx V2 corrections + full codebase review  
**Date:** 2026-05-13  
**Repo context:** Point Claude Code at the repo root. All file paths below are relative to the pipeline package directory (the folder containing `orchestrator.py`).

---

## TASK 1 — Fix closure date column mapping (comments 1 & 2)

**Files:** `stage1_validator.py`

**Bug:** `COLUMN_MAPPING` maps `'تاريخ إغلاق الطلب'` → `'تاريخ_الإنشاء'` (line ~38). This silently overwrites the case creation date with the closure date, or vice-versa. The reviewer's question "how do we know these are closed cases?" stems from this — the pipeline reports `total_cases` as closed cases because the fallback in `run_stage1` uses `total_cases` when `تاريخ_إغلاق_الطلب` is missing. But the column IS present in the input Excel, just misrouted.

**Fix:**

1. In `COLUMN_MAPPING`, change the mapping for the closure date to a distinct normalized name:
   ```python
   # BEFORE (wrong — overwrites creation date):
   'تاريخ إغلاق الطلب': 'تاريخ_الإنشاء',
   
   # AFTER (correct — separate column):
   'تاريخ إغلاق الطلب': 'تاريخ_إغلاق_الطلب',
   ```

2. Add `'تاريخ_إغلاق_الطلب'` to `OPTIONAL_COLUMNS` (not `REQUIRED_COLUMNS`).

3. In `run_stage1`, the block that sets `state.closed_cases_count` already references `'تاريخ_إغلاق_الطلب'` — once the mapping is fixed this will work correctly. Verify it still does.

4. In `state.py`, `CaseRow` has `date_opened` but no `date_closed`. Add:
   ```python
   date_closed: Optional[str] = None  # تاريخ_إغلاق_الطلب — empty string means not yet closed
   ```

5. In `stage2_rules.py` `run_stage2`, populate `date_closed` from `تاريخ_إغلاق_الطلب` alongside the existing `date_opened` from `تاريخ_الإنشاء`.

6. In `stage6_artifacts.py` `_populate_all_cases_sheet`, add `تاريخ_إغلاق_الطلب` as a passthrough column (read from `raw_df_lookup`, similar to how `الخدمة` is handled).

**Acceptance criteria:**
- `state.closed_cases_count` equals the count of rows where `تاريخ_إغلاق_الطلب` is non-empty/non-null in the input file.
- `state.total_cases` remains the total row count (all cases, open and closed).
- The Excel output sheets include a `تاريخ_إغلاق_الطلب` column.
- The cover page stat "إجمالي الحالات المغلقة: N حالة" uses `state.closed_cases_count`, not `state.total_cases`.
- `state.total_cases` and `state.closed_cases_count` are logged separately at the end of Stage 1.

---

## TASK 2 — Fix cover page and methodology to use `closed_cases_count` not `total_cases` (comments 1, 7, 11)

**Files:** `build_report_ar.py`, `stage6_artifacts.py`, `generate_workload_map_section.py`

**Bug:** Multiple places hard-reference `state.total_cases` for the "closed cases" headline figure, and the cover page says "إجمالي الحالات المغلقة: {total_cases} حالة". After Task 1, `total_cases` = all cases and `closed_cases_count` = actually closed. The report must distinguish these.

**Specifically:**

1. **`build_report_ar.py` `_extract_cover_stats`:** The cover stat "إجمالي الحالات المغلقة" is derived by summing rows from section 3.1's distribution table. This counts all classified cases, not just closed ones. Fix it to read `state.closed_cases_count` directly and pass it through the JSON report metadata, OR update the cover stat label to accurately reflect what is being counted.

   The cover line must read: `"إجمالي الحالات المغلقة: {closed_cases_count} حالة"` where `closed_cases_count` comes from the JSON metadata field.

2. **Add `closed_cases_count` to the report JSON metadata** in `stage6_json_report.py` `JSONReportBuilder.build_metadata`:
   ```python
   "closed_cases_count": self.state.closed_cases_count,
   ```

3. **`generate_workload_map_section.py`:** The `total_cases` variable is set to `state.closed_cases_count if state.closed_cases_count > 0 else len(all_classified)`. This is correct — keep it. But the prompt says `f"تحليل {total_cases} حالة مغلقة في {date_range}"`. After Task 1, this value will now correctly exclude unclosed cases.

4. **Section 3.1 intro paragraph:** The LLM prompt instructs `"تحليل {total_cases} حالة مغلقة في {date_range}"`. Verify the value passed is `closed_cases_count`, not `len(all_classified)`.

**Acceptance criteria:**
- Cover stat shows `closed_cases_count` (cases with non-empty `تاريخ_إغلاق_الطلب`).
- Section 3.1 intro says "تحليل N حالة مغلقة" where N = `closed_cases_count`.
- The reclassification section (3.2) still uses `total_cases` for "N من أصل N" comparisons because reclassification counts apply to all processed cases.
- `state.total_cases` and `state.closed_cases_count` are both present in the report JSON metadata.

---

## TASK 3 — Fix "49 closed on time, not 50" — SLA section uses wrong denominator (comments 6, 8)

**Files:** `stage6_artifacts.py` (`_populate_summary_sheet`), `stage6_json_report.py` (`_build_pre_computed_findings`), `build_report_ar.py` (`_extract_cover_stats`)

**Bug:** Finding #5 in the executive summary reads "تم إغلاق 49 من 50 حالة في الوقت المحدد (معدل 98.0%)". The reviewer confirms 49/50 is correct but notes the word "مغلقة" next to "50" is wrong — only 49 were actually closed within SLA. The cover stat "معدل الإغلاق في الوقت المحدد: 98%" is correct.

**What needs to change:**

The real issue is that section 3.1 and the methodology describe "50 حالة مغلقة" but the SLA table shows 49 closed on time and 1 overdue — meaning 50 were processed but the 1 overdue case was NOT closed in time. The word "مغلقة" in "50 حالة مغلقة" must be removed per the reviewer (comment 19, handled in Task 5 below).

For the SLA finding specifically: the text is correct as-is (49/50, 98%). **No code change needed here beyond what Task 2 already fixes.**

However, verify that `_populate_summary_sheet` in `stage6_artifacts.py` computes SLA correctly:
```python
on_time = sum(1 for c in state.all_classified if str(c.sla_color).strip() == 'نعم')
```
The SLA field is `الحالة_SLA` (mapped from `إغلاق الطلب خلال الوقت المحدد` in the input). Confirm this column is being read into `case.sla_color` in `run_stage2`. The input Excel has both `الحالة SLA` (status color) and `إغلاق الطلب خلال الوقت المحدد` (yes/no compliance). The pipeline maps `إغلاق الطلب خلال الوقت المحدد` → `سلا_امتثال` and uses it as `sla_color`. This is correct — keep it.

**Acceptance criteria:**
- SLA summary sheet row shows 49 on-time, 1 overdue (for the sample dataset).
- Finding #5 in the executive summary JSON shows "49 من {total_cases}" where the specific counts come from live computation, not hard-coded values.

---

## TASK 4 — Remove "مغلقة" from section 3.1 intro (comment 19) and section header (comment 11)

**Files:** `generate_workload_map_section.py`

**Bug:** The LLM prompt for section 3.1 instructs the model to open with:
```
f'- Open: "تحليل {total_cases} حالة مغلقة في {date_range}..."'
```
The reviewer wants "مغلقة" removed. The sentence should read "تحليل {total_cases} حالة في {date_range}...".

**Fix:** In `generate_workload_map_section.py`, in the `prompt` string (around line ~190 of that file), change:

```python
# BEFORE:
f'  - Open: "تحليل {total_cases} حالة مغلقة في {date_range}..."\n'

# AFTER:
f'  - Open: "تحليل {total_cases} حالة في {date_range}..."\n'
```

Also check the `reclassification_insight` instruction in the same prompt — if it says "حالة مغلقة" anywhere, remove "مغلقة" there too.

**Acceptance criteria:**
- Section 3.1 generated text does not contain "حالة مغلقة".
- Section 3.2 generated text does not contain "حالة مغلقة" (it should say "حالة" when referring to the 50 cases).
- The methodology section sources table row for the CRM source (`generate_methodology_section` in `stage6_artifacts.py`) currently hardcodes `f"{closed_count} حالة مغلقة"` — update this to `f"{closed_count} حالة"` as well.

---

## TASK 5 — Fix section 2.2 formatting: newline separators between decision tree tests (comment 9)

**Files:** `stage6_artifacts.py` (`generate_methodology_section`)

**Bug:** Section 2.2 (classification methodology) is hardcoded in `generate_methodology_section` as a single string. The reviewer wants each test and each classification rule on its own line. Currently the hardcoded value is:

```python
classification_method_hardcoded = (
    "يعتمد التحليل على شجرة قرار من أربعة مستويات، حيث طبيعة المطلوب وليس الصياغة هي المعيار الفاصل. يُطرح على كل حالة اختباران متتاليان: "
    "(1) الاختبار الأول: هل يُعبّر النص عن استياء، أو إبلاغ عن إخفاق، أو رغبة في تقديم بلاغ رسمي أو اعتراض؟ "
    "(2) الاختبار الثاني: هل يطلب النص تنفيذ إجراء محدد كتقديم خدمة أو متابعة طلب أو تعديل بيانات، وليس مجرد الحصول على معلومة؟\n"
    "قواعد التصنيف:\n"
    ...
)
```

The report renderer in `build_report_ar.py` `_render_section` splits content on `\n` and renders each non-empty line as a separate paragraph:
```python
for para in content.split("\n"):
    para = para.strip()
    if para:
        builder.add_paragraph(para, ...)
```

So adding `\n` before each test and each rule will produce separate visual lines in the Word doc.

**Fix:** Reformat `classification_method_hardcoded` with explicit `\n` before each numbered test and each `→` rule:

```python
classification_method_hardcoded = (
    "يعتمد التحليل على شجرة قرار من أربعة مستويات، حيث طبيعة المطلوب وليس الصياغة هي المعيار الفاصل. يُطرح على كل حالة اختباران متتاليان:\n"
    "(1) الاختبار الأول: هل يُعبّر النص عن استياء، أو إبلاغ عن إخفاق، أو رغبة في تقديم بلاغ رسمي أو اعتراض؟\n"
    "(2) الاختبار الثاني: هل يطلب النص تنفيذ إجراء محدد كتقديم خدمة أو متابعة طلب أو تعديل بيانات، وليس مجرد الحصول على معلومة؟\n"
    "قواعد التصنيف:\n"
    "→ إن كان الجواب نعم على الأول: شكوى (حتى لو تضمّن النص طلباً لاتخاذ إجراء)؛\n"
    "→ إن كان الجواب نعم على الثاني فقط: طلب (دون أن يكون الغرض إبلاغاً عن مشكلة)؛\n"
    "→ إن كان الغرض سؤالاً أو استعلاماً عن معلومة: استفسار؛\n"
    "→ إن كان التعبير عن رضا وثناء: شكر وثناء."
)
```

**Acceptance criteria:**
- In the generated Word document, section 2.2 shows each test on its own paragraph/line.
- Each `→` rule is on its own paragraph/line.
- No other section content is affected.

---

## TASK 6 — Remove `الجنسية` from section 2.3 analyzed fields (comment 10)

**Files:** `stage6_artifacts.py` (`generate_methodology_section`)

**Bug:** The hardcoded `analyzed_fields_text` in `generate_methodology_section` lists `الجنسية` as a structured analyzed field. The reviewer confirmed this field is NOT present in the source data and should be removed.

```python
# Current (wrong):
analyzed_fields_text = (
    "الحقول المنظمة المستخدمة في التحليل: رقم الطلب، الخدمة الرئيسية، نوع المكالمة الأصلي، "
    "حالة الطلب، قناة التواصل، الجنسية، والإدارة المختصة. "
    ...
)
```

Also check the LLM prompt's `analyzed_fields.structured` list (in the same function), which includes `الجنسية`. Remove it there too.

**Fix:** Remove `الجنسية` from both:
1. The hardcoded `analyzed_fields_text` string.
2. The YAML-style list in the prompt (`analyzed_fields.structured` section).

Also remove it from `COLUMN_MAPPING` in `stage1_validator.py` if it is present there — the validator should not try to map a column that doesn't exist in the source.

**Acceptance criteria:**
- Section 2.3 in the generated report does not mention `الجنسية`.
- The pipeline does not error if `الجنسية` is absent from the input file.
- If `الجنسية` somehow appears in a future input file it is simply ignored (no mapping, no error).

---

## TASK 7 — Fix section 3.4 scope: requests only, not inquiries (comment 13)

**Files:** `stage6_json_report.py` (`JSONReportBuilder.build_workload_map_section`), `generate_workload_map_section.py`

**Bug:** Section 3.4 is scoped to requests (`طلب`) but the LLM sometimes places inquiry sub-categories there. There is already a defensive filter in `build_workload_map_section`:
```python
request_rows = [
    row for row in request_rows
    if not (row.get("الفئة الفرعية", "").startswith("استفسار"))
]
```
But the LLM prompt is not explicit enough about the separation.

**Fix:**

1. In `generate_workload_map_section.py`, in the prompt, add an explicit rule after the `requests_table` instruction:
   ```
   - requests_table: ONLY طلب sub-classifications. Do NOT include any استفسار sub-classifications here.
     استفسار sub-classifications belong ONLY in inquiries_table (3.5).
   ```

2. In `build_workload_map_section` (in `stage6_json_report.py`), make the filter more robust — also filter out rows whose `الفئة الفرعية` is found in the inquiry sub-classifications list from `stage2_rules.SUB_CLASSIFICATIONS['استفسار']`:
   ```python
   from .stage2_rules import SUB_CLASSIFICATIONS
   inquiry_subs = set(SUB_CLASSIFICATIONS.get('استفسار', []))
   request_rows = [
       row for row in request_rows
       if row.get("الفئة الفرعية", "") not in inquiry_subs
   ]
   ```

3. Add the symmetric filter for `inquiries_table`: filter out any row whose `الفئة الفرعية` is in `SUB_CLASSIFICATIONS['طلب']`.

**Acceptance criteria:**
- Section 3.4 table contains only rows with `الفئة الفرعية` from `SUB_CLASSIFICATIONS['طلب']`.
- Section 3.5 table contains only rows with `الفئة الفرعية` from `SUB_CLASSIFICATIONS['استفسار']`.
- No sub-classification appears in both 3.4 and 3.5.

---

## TASK 8 — Fix section 3.4 request count: 12 → 13 (comment 14)

**Files:** `stage6_json_report.py` (`JSONReportBuilder.build_workload_map_section`)

**Bug:** Section 3.4 heading shows 12 requests but the Excel `طلبات` sheet has 13 rows. The count in the heading is derived from `corrected_dist.get("طلب", 0)` which counts all cases with `actual_contact_type == "طلب"`. If the pipeline classified 13 cases as `طلب`, the heading must say 13.

The mismatch suggests the defensive filter in Task 7 (filtering out inquiry sub-types from `request_rows`) is removing a row that shouldn't be removed. Case `2025278919` with sub-type `استفسار عن الأسلحة والتراخيص` is correctly classified as `طلب` at the top level (`actual_contact_type = 'طلب'`) but its sub-type name starts with "استفسار" — which causes the filter to remove it.

**Fix:** The filter added in Task 7 must check against the canonical inquiry sub-classification list, NOT against the string prefix "استفسار". The sub-type `استفسار عن الأسلحة والتراخيص` IS in `SUB_CLASSIFICATIONS['استفسار']`, so a case with `top_level = 'طلب'` and `sub_classification = 'استفسار عن الأسلحة والتراخيص'` represents a classification inconsistency that should be surfaced, not silently dropped.

The real fix: do NOT filter request rows by sub-classification name at all. The table should include every case with `actual_contact_type == 'طلب'`, regardless of sub-type. If a case has an inquiry sub-type but a request top-level, it indicates a classification issue to be fixed at Stage 2/3 — not silently suppressed here.

Remove the sub-classification-based filter from `request_rows` entirely. The heading count will then match the actual `طلب` case count.

**Acceptance criteria:**
- Section 3.4 heading count matches `corrected_dist.get("طلب", 0)` exactly.
- Case `2025278919` appears in section 3.4 breakdown table.
- The section 3.4 table row count equals the number of distinct `sub_classification` values among cases with `actual_contact_type == 'طلب'`.

---

## TASK 9 — Fix pain point description: "missing photo" → "wrong vehicle in photo" (comments 33, 39, 41, 48)

**Files:** `stage4_analysis.py`, `generate_customer_journey_section.py`, `generate_digital_gaps_section.py`

**Bug:** The pipeline generates the friction point description as: "يتلقى المتعامل إشعار مخالفة **دون إرفاق صورة واضحة للمركبة المخالفة**". The reviewer corrects this to: "**الصورة موجودة لكنها تُظهر مركبة مختلفة** (لون/نوع/لوحة مختلفة)".

The root cause label is also wrong — currently "غياب الإشعار الاستباقي" (`no_proactive_notification`) but should be "خطأ في نظام مطابقة لوحات الرادار" which maps to `platform_bug`.

This error originates from Stage 4 (the LLM analysis) and propagates into the customer journey section and gap analysis. The fix is to improve the Stage 4 prompt so the LLM correctly identifies this pattern.

**Fix:**

1. **`stage4_analysis.py` `build_analysis_system_prompt`:** Add a disambiguation rule in the JOURNEY MAP section:

   ```
   CRITICAL DISAMBIGUATION — Traffic Fine Friction Points:
   When cases show a citizen disputing a fine because "the photo shows a different vehicle",
   the friction point is NOT "missing vehicle photo in notification".
   The correct friction point is: "the vehicle photo IS present but shows the WRONG vehicle
   (wrong colour/model/plate)".
   The correct root_cause_category is "platform_bug" (radar plate-matching system error),
   NOT "no_proactive_notification".
   Do NOT classify this as a notification gap — the notification exists; the system data is wrong.
   ```

2. **`generate_customer_journey_section.py`** and **`generate_digital_gaps_section.py`:** In both prompts, add the same disambiguation note before the friction table instructions. This catches cases where Stage 4's journey_map already contains the wrong description.

3. **`stage2_rules.py` `classify_case`:** The comment in Priority 1b says `disputed_fine_signals_ar` catches "صورة المخالفة". This is correct classification-wise (it's a `شكوى عن مخالفة مشكوك فيها`), but the `classification_reason` string should say "صورة المركبة تُظهر مركبة مختلفة" rather than implying the photo is absent. Update the reason string in the return value:
   ```python
   # BEFORE:
   return 'شكوى', 'شكوى عن مخالفة مشكوك فيها', 'شكوى صريحة عن مخالفة خاطئة', 0.88
   
   # AFTER (more precise reason):
   return 'شكوى', 'شكوى عن مخالفة مشكوك فيها', 'صورة المركبة في الإشعار تُظهر مركبة مختلفة — خطأ في مطابقة اللوحات', 0.88
   ```

**Acceptance criteria:**
- In the generated report, section 4 (customer journey) friction table does NOT contain any row with the phrase "دون إرفاق صورة" or "غياب صورة المركبة".
- The friction row for this pain point contains "مركبة مختلفة" or "خطأ في مطابقة اللوحات" in either `friction_point_ar` or `cluster_ar`.
- The `root_cause_category` for this friction point in `state.journey_map` is `platform_bug`, not `no_proactive_notification`.
- Section 5 (gap analysis) gap table does NOT describe this issue as a notification gap.
- The roadmap (section 8) recommendation for this item does NOT say "إرفاق صورة المركبة في الإشعار" — it should reference fixing the radar matching system.

---

## TASK 10 — Improve LLM classification prompt to reduce CRM label over-weighting (comments 4, 5, 16, 17)

**Files:** `stage3_llm.py` (`build_system_prompt`), `stage2_rules.py`

**Context:** Comments 4–5 provided case IDs as examples of misclassification. These are calibration examples, not hard-coded fixes. The root cause is that the LLM (and Stage 2 rules) over-weight `نوع_المكالمة` (the CRM label, always "استفسار") when the actual case content clearly signals a different type.

**Specific patterns to fix:**

- **4 cases reclassified from `استفسار` → `طلب` in xlsx V2:** Cases where the citizen is requesting a specific action (licence transfer, fine discount confirmation, vehicle data correction, fine removal) but the CRM label is "استفسار".

- **1 case reclassified from `طلب` → `شكوى` (2025279073):** Stone damage to car window — citizen requested a damage certificate. Classified as `طلب > طلب إصدار شهادة` but should be `شكوى` per reviewer. (Note: current `stage3_llm.py` Rule E explicitly says "damage + certificate issued = طلب". The reviewer disagrees. Clarify with the reviewer before changing Rule E — it may depend on whether the damage was caused by a government action or was a neutral incident. **Leave Rule E unchanged for now** and note this as a known open question.)

**Fix — Stage 3 LLM prompt:**

In `stage3_llm.py` `build_system_prompt`, strengthen the existing guidance on CRM label de-weighting. After the existing "UNRESOLVED FOLLOW-UP ISSUES" section, add:

```
4. CRM LABEL OVERRIDE:
   The نوع_المكالمة field (CRM label) is almost always "استفسار" regardless of actual content.
   It reflects the intake channel, NOT the customer's true intent.
   NEVER let نوع_المكالمة determine the final classification.
   Always classify based on تفاصيل_الطلب and الحل content.
   
   If تفاصيل_الطلب contains an explicit ACTION REQUEST (أطلب، أريد، أرجو + specific action),
   and the action is NOT about expressing grievance → طلب, even if CRM says استفسار.
   
   Examples of explicit action requests that must be طلب:
   - Requesting transfer of driving licence between emirates
   - Requesting confirmation that a fine discount is applied in the system  
   - Requesting correction of vehicle data (category, plate, owner)
   - Requesting removal of a fine from a traffic record
```

**Fix — Stage 2 rules (`stage2_rules.py`):**

The `PRIORITY 7` vehicle keywords rule returns `استفسار` for any case mentioning "رخصة قيادة" or "مركبة". This is too broad — it catches cases that should be `طلب` (e.g., requesting a licence transfer).

Tighten Priority 7 to only match when the text is purely informational (no explicit action request):
```python
# --- PRIORITY 7: License/Vehicle Inquiries (PURE INFORMATION REQUESTS ONLY) ---
# Only classify as استفسار if NO action-request signals are present
action_request_signals = ['أطلب', 'اطلب', 'أريد', 'اريد', 'أرجو', 'ارجو', 'نقل رخصة', 'تحويل رخصة', 'تعديل', 'تصحيح', 'إلغاء']
has_action_request = any(normalize_arabic(k) in title_norm for k in action_request_signals)
if not has_action_request and any(k in title_norm for k in [normalize_arabic(w) for w in vehicle_keywords]):
    return 'استفسار', 'استفسار عن الرخص والمركبات', 'استفسار عن الرخص والمركبات', 0.85
```

**Acceptance criteria:**
- A case with تفاصيل_الطلب containing "أطلب نقل رخصة قيادة" is classified as `طلب`, not `استفسار`.
- A case with تفاصيل_الطلب containing "أرجو تعديل بيانات المركبة" is classified as `طلب`, not `استفسار`.
- A case with تفاصيل_الطلب containing "ما هي متطلبات تجديد الرخصة؟" (pure inquiry, no action request) is still classified as `استفسار`.
- The Stage 2 `classify_case` unit tests (if they exist) continue to pass.

---

## TASK 11 — Fix section 5 intro paragraph number conflicts (comment 38)

**Files:** `generate_digital_gaps_section.py`

**Bug:** The section 5 intro paragraph hard-references case counts that conflict with the gap table totals. Specifically, the text "يمكن تحويل 21 حالة (42.0% من الإجمالي) عبر إشعار SMS/بريد إلكتروني استباقي" is generated by the LLM but the real `proactive_case_count` from `state.notification_opportunities` may differ.

**Fix:** In `generate_digital_gaps_section.py`, the `proactive_instruction` variable is already pre-computed:
```python
proactive_instruction = (
    f'   - Add: يمكن تحويل {proactive_case_count} حالة '
    f'({proactive_pct}% من الإجمالي) عبر إشعار SMS/بريد إلكتروني استباقي دون أي تغيير في البنية التحتية.\n'
    if proactive_case_count > 0 else ''
)
```

This is correct — the number comes from `state`. The problem is the LLM may still hallucinate a different number in its prose. Add a hard constraint to the prompt:

```
CRITICAL NUMBER CONSTRAINT for section_body:
If you mention proactive notification cases, use EXACTLY: {proactive_case_count} حالة ({proactive_pct}%)
Do NOT use any other number for this claim. This is pre-computed and locked.
```

Also add a post-generation validation in `generate_digital_gaps_section.py`: after parsing the LLM result, check if `section_body` contains a number that is larger than `total_cases` and raise a warning if so (not a hard failure, but log it).

**Acceptance criteria:**
- The section 5 intro paragraph's proactive-notification case count matches `sum(g.case_count for g in state.gap_table if g.proactive_notification_opportunity)`.
- The section 5 gap table totals and section 5 intro paragraph cite the same case counts for the same topics.
- No number in section 5 intro exceeds `total_cases`.

---

## TASK 12 — Fix FAQ frequency counts: make them dynamic not hard-coded (comments 42–43, 53–55)

**Files:** `generate_digital_transformation_section.py` (`_build_faq_rows_for_transform`)

**Bug:** The FAQ frequency column (`التكرار`) in section 6.1 shows inflated counts. The reviewer corrected them:

| FAQ rank | Topic | Was | Should be |
|---|---|---|---|
| 1 | Wrong-vehicle fine | 11+ | 4 |
| 2 | Fujairah licence validity | 6+ | 1 |
| 4 | Document not received after payment | 4+ | 1 |
| 5 | Double deduction from MOI app | 4+ | 1 |
| 6 | Cannot register vehicle from other emirate | 3+ | 1 |

The frequency values come from `faq.frequency` in `state.validated_faqs` (or `faq_candidates`). These are set by the Stage 4 LLM in `stage4_analysis.py`. The Stage 4 LLM is over-counting.

**Fix — Two-part:**

**Part A (Stage 4 prompt — `stage4_analysis.py` `build_analysis_system_prompt`):**

Add a grounding instruction to the FAQ extraction section:

```
3. FAQs — Questions answered repeatedly in the resolution
   ...
   FREQUENCY COUNTING RULE:
   Set frequency = the EXACT count of cases in the dataset where this specific question
   was the primary driver of the customer contact. Count each case only once.
   Do NOT extrapolate or estimate beyond the cases provided.
   Do NOT add "+" to frequencies — return the exact integer count.
   A frequency of 1 means exactly 1 case. Only assign frequency > 1 if multiple distinct
   cases show the SAME question as their primary concern.
```

**Part B (reconciliation in `generate_digital_transformation_section.py`):**

After building `faq_context`, add a cross-check: for each FAQ, look up how many cases in `state.all_classified` match the FAQ's sub_classification (from the `top_level` field on the FAQ). If the FAQ's `frequency` exceeds the actual case count for that sub-classification, cap it:

```python
# Build sub_classification counts from all_classified
sub_counts = defaultdict(int)
for case in (state.all_classified or []):
    sub_counts[case.sub_classification] += 1

# Cap FAQ frequency against actual case count for that sub-classification
for faq in faq_context:
    top_level_sub = faq.get("top_level", "")
    if top_level_sub and top_level_sub in sub_counts:
        faq["frequency"] = min(faq["frequency"], sub_counts[top_level_sub])
```

**Acceptance criteria:**
- FAQ frequency values in the generated report are never larger than the actual count of cases in `state.all_classified` for the relevant sub-classification.
- FAQ frequencies are computed from live case data, not hard-coded.
- The `التكرار` column in the section 6.1 table shows corrected values.

---

---

## TASK 13 — Fix reclassification: case 2025270869 should be `إستفسار` not `شكوى` (xlsx V2 diff, شكاوى sheet row 30)

**Files:** `stage3_llm.py` (`build_system_prompt`), `stage2_rules.py`

**Bug:** Case `2025270869` — citizen says: "I made an incorrect action during vehicle registration, paid 426 AED instead of 500 AED, will the amount be refunded?" The pipeline classified this as `شكوى > شكوى على خطأ تقني أو في النظام`. The reviewer corrected it to `إستفسار` in V2.

Reading the case text carefully: the citizen made their own mistake (not a system error), paid the wrong fee, and is **asking a question** ("هل سيرد المبلغ؟" — "will the amount be refunded?"). This is not a complaint about a system failure — it's an inquiry about a refund procedure. The resolution shows the agent called back and got no answer, which doesn't confirm any error occurred.

**Root cause in code:** `stage2_rules.py` Priority 6 catches `'دفع مرتين'` and `'دفع مبلغ مرتين'` as system error signals. But this case only says "تم دفع رسوم 426 درهم" (paid 426 AED) — no double-charge. The system_keywords list is over-broad. The LLM classifier also misapplied Rule C ("paid without service = complaint") when in fact the citizen got the service but paid the wrong amount themselves.

**Fix — Stage 3 LLM prompt (`stage3_llm.py`):**

Sharpen Rule C to distinguish "system charged me by mistake" from "I made an error and am asking about the procedure":

```
Rule C — Payment issues (REVISED):
   - "دفعت مبلغ X دون استلام الخدمة" (paid, service not received) → شكوى
   - "النظام خصم مني مرتين" (system double-charged me) → شكوى  
   - "أجريت إجراء خاطئاً ودفعت المبلغ الخاطئ، هل يُسترد؟" (I made an error, asking about refund) → استفسار
   - KEY DISTINCTION: If the CITIZEN caused the payment issue (not the system), and they are
     ASKING A QUESTION about the outcome (no explicit grievance), classify as استفسار.
```

**Fix — Stage 2 rules (`stage2_rules.py`):**

The `system_keywords` list at Priority 6 includes `'دفع مرتين'` and `'دفع مبلغ مرتين'`. These are correct signals for system double-charge complaints. However, add a guard: if the text also contains phrases suggesting the user made their own error (`'أجريت إجراء خاطئ'`, `'إجراء غير صحيح'`, `'بدلاً من'`), do NOT trigger the system error path — let it fall through to the LLM.

**Acceptance criteria:**
- Case `2025270869` is classified as `استفسار`, not `شكوى`.
- It appears in the `استفسارات` sheet in the Excel output.
- Cases with genuine system double-charge (e.g., "خصمت مني مرتين دون إصدار الوثيقة") are still classified as `شكوى > شكوى على خطأ تقني`.

---

## TASK 14 — Fix reclassification: case 2025279073 should be `شكوى` not `طلب` (xlsx V2 diff, طلبات sheet row 10)

**Files:** `stage3_llm.py` (`build_system_prompt`)

**Bug:** Case `2025279073` — "stones fell on the car and broke the window". The pipeline classified it as `طلب > طلب إصدار شهادة أو وثيقة` using Rule E. The reviewer corrected it to `شكوى` in V2.

**Resolution:** The Task 10 spec currently flags this as an "open question — leave Rule E unchanged". Based on the reviewer's V2 correction, this is a definitive fix: Rule E needs a guard condition.

**The distinction:**
- Rule E is correct when the citizen **proactively contacts support to request** a damage certificate (e.g., "I need a damage certificate for my insurance").
- Rule E does NOT apply when the citizen contacts support to **report an incident/complaint**, and the agent happens to issue a certificate as part of the resolution. The citizen's intent was reporting harm, not requesting a certificate.

In this case: "سقوط بعض الحجارة على السيارة أدت إلى كسر النافذة" — the citizen is reporting an incident (stones fell, window broke). The resolution shows the agent discovered the citizen wanted a damage certificate and issued one. The citizen's **primary intent was reporting harm**, not requesting a document.

**Fix — Stage 3 LLM prompt (`stage3_llm.py`), Rule E:**

```python
# BEFORE:
"""Rule E — Physical damage reports requesting a certificate:
   If a customer describes physical damage ... AND the resolution shows a certificate was issued
   → طلب > طلب إصدار شهادة أو وثيقة
   Do NOT classify these as شكوى unless the customer is explicitly complaining about a service failure."""

# AFTER (add guard):
"""Rule E — Physical damage reports requesting a certificate:
   If a customer PROACTIVELY REQUESTS a certificate for physical damage (e.g., 'أريد شهادة ضرر')
   AND the resolution shows a certificate was issued → طلب > طلب إصدار شهادة أو وثيقة
   
   EXCEPTION: If the customer's PRIMARY INTENT is REPORTING an incident (e.g., 'سقطت حجارة على سيارتي')
   without explicitly requesting a certificate, classify as:
   → شكوى > تقديم بلاغ أمني أو مروري
   Even if the resolution incidentally issued a certificate — the initial contact was a complaint/report.
   
   KEY: Ask — did the citizen come to REQUEST something, or to REPORT something?
   'سقوط حجارة / حادث / تلف' without 'أريد شهادة' → شكوى (report)
   'أحتاج شهادة ضرر / أطلب وثيقة' → طلب (request)"""
```

**Acceptance criteria:**
- Case `2025279073` ("stones fell, window broke") is classified as `شكوى`, appears in `شكاوى` sheet.
- A case with text "أريد شهادة ضرر لسيارتي" (explicit certificate request) is still classified as `طلب > طلب إصدار شهادة أو وثيقة`.
- `stage3_llm.py` Rule E comment is updated to reflect the guard condition.

---

## TASK 15 — Fix section 3.3 complaints table: include all sub-classifications (comment 36)

**Files:** `stage6_json_report.py` (`JSONReportBuilder.build_workload_map_section`), `generate_workload_map_section.py`

**Bug:** Comment 36 — anchored to the gap analysis table — states: "The table gives the impression of comprehensive coverage but drops 20% of cases. Most notably missing: Security reports (4 cases = 8%), service quality issues (2 cases), and individual cases (4 cases)."

While the comment is anchored to section 5 (gap analysis), its substance is about the **section 3.3 complaints breakdown table** — which the LLM generates via `generate_workload_map_section`. The Stage 4 analysis groups patterns by clusters with a minimum case threshold (`min 5 cases per cluster`). Sub-classifications with fewer than 5 cases are excluded from the pattern clusters and therefore from the section 3.3 table.

This affects:
- `تقديم بلاغ أمني أو مروري` (4 cases) — not appearing in complaints breakdown
- Low-count sub-classifications like `شكوى على تأخر المعالجة` (1 case), `شكوى على عدم الرد` (1 case)

**Fix:**

1. **`generate_workload_map_section.py` prompt:** The `pre_computed_complaint_sub_classifications` already passes ALL sub-types regardless of count (computed from `_sub_classification_breakdown` which has no threshold). However, the prompt's `validate_and_fix_table` function checks that returned rows match expected rows, and adds missing ones — but it only adds them without a `الوصف` field, which causes a validation error.

   Update `validate_and_fix_table` to add a placeholder description for any row that was added because it was missing from the LLM response:
   ```python
   table_rows.append({
       **expected_row,
       "الوصف": f"حالات {expected_row.get('الفئة الفرعية', '')} المُسجَّلة خلال الفترة."
   })
   ```

2. **`generate_workload_map_section.py` prompt instruction:** Add an explicit rule that ALL sub-classifications must appear in the breakdown table, even low-count ones:
   ```
   CRITICAL: complaints_table must include EVERY sub-classification from
   pre_computed_complaint_sub_classifications, even those with count = 1.
   Do NOT omit low-count rows. The reviewer specifically flagged that
   sub-classifications like 'تقديم بلاغ أمني أو مروري' (4 cases) were missing.
   ```

3. **`stage4_analysis.py` `build_analysis_system_prompt`:** The pattern clustering instruction says "min 5 cases per cluster". This threshold is appropriate for pattern analysis but must NOT cause sub-classifications to disappear from the section 3.3 table. The section 3.3 table is built independently from `_sub_classification_breakdown` (which uses `state.all_classified` directly), not from patterns. So the Stage 4 threshold does not directly cause the issue — but add a note to the Stage 4 prompt clarifying that low-count sub-classifications are still valid and must not be suppressed in analysis output.

**Acceptance criteria:**
- Section 3.3 complaints breakdown table includes `تقديم بلاغ أمني أو مروري` with count 4.
- Section 3.3 includes ALL `شكوى` sub-classifications that appear at least once in `state.all_classified`.
- The total of counts in section 3.3 equals `corrected_dist.get("شكوى", 0)`.
- No sub-classification is silently dropped due to low count.

---

## Summary of Acceptance Test (End-to-End)

Run the pipeline with `Inquiries_2025.xlsx` as input and verify:

1. `state.closed_cases_count` < `state.total_cases` (there are unclosed cases in the data).
2. Cover page stat "إجمالي الحالات المغلقة" = `state.closed_cases_count`.
3. Section 3.1 intro does NOT contain "مغلقة".
4. Section 2.2 in the Word doc shows each decision-tree test and each `→` rule on its own line.
5. Section 2.3 does NOT mention "الجنسية".
6. Section 3.4 contains only `طلب` sub-types; section 3.5 contains only `استفسار` sub-types.
7. Section 3.4 heading count = `len([c for c in state.all_classified if c.actual_contact_type == 'طلب'])` distinct sub-types (should include case `2025278919`).
8. Section 3.3 complaints breakdown includes ALL `شكوى` sub-classifications present in the data, including `تقديم بلاغ أمني أو مروري` (4 cases). The sub-classification counts in 3.3 sum to the total `شكوى` count.
9. The traffic fine friction point in section 4 describes "مركبة مختلفة في الصورة" not "غياب الصورة".
10. The `root_cause_category` for the wrong-vehicle friction point in `state.journey_map` is `platform_bug`.
11. Section 5 intro proactive-notification count matches `state.notification_opportunities` sum.
12. FAQ frequencies in section 6.1 are capped at actual sub-classification case counts.
13. Case `2025270869` ("paid wrong fee, asking about refund") is classified as `استفسار`.
14. Case `2025279073` ("stones fell on car, broke window") is classified as `شكوى`.
15. Cases `240590`, `2025252341`, `2025278589`, `227631` (explicit action requests) are classified as `طلب`.
16. A case with "أطلب نقل رخصة قيادة" is classified as `طلب`, not `استفسار`.
