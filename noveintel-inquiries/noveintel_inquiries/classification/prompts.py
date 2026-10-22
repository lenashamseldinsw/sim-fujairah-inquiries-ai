"""
The Layer 2 prompts — the classifier and the umbrella-discovery step.

Both are the Full Report Prompt's (§0 and §0b), merged with the two codebooks:

* the **classification codebook** — the golden rule (read H and I only, the
  resolution decides, the CRM title and tag are context), the O → N taxonomy with its
  assignment signals, and the edge cases;
* the **root-cause codebook** — rules R1–R7 and the recurring-situation wording,
  given only when root-cause extraction (X8) is on.

Two reconciliations, both recorded here so the prompt does not contradict itself:

1. The ADPF prompt asks for ``main_service`` only when root-cause extraction is on.
   The codebook nests every sub-classification under a main service (O → N), so a
   sub-classification cannot be chosen without one. ``main_service`` is therefore
   always returned, and the sub-classification is chosen *under the chosen main
   service* (the prompt's "under the chosen type" read as the codebook defines it).
2. The ADPF prompt says "Output JSON only". The service forces a tool call, which is
   that rule enforced by the API: the arguments are the JSON, and no prose survives.
3. The prompt lists ``evidence`` with the same definition as ``classification_reason``;
   the output schema beside it (``CaseLabels``) has only the reason, so only the reason
   is asked for — it was 26 of the 141 output tokens a case cost.

**Short output, same labels.** Output is billed at eight times the input rate, so the
answer is kept small: each case is referred to by a batch-local id (``c1``…), every
sub-classification has a code (``M3.1`` = the first sub-classification of the third
main service, in the taxonomy's own order), and the keys are short. The code names the
main service too, so a sub-classification can never land under the wrong one.
``model.ModelClassifier`` maps the answer back to the full names before anyone reads it.

The classifier never sees a number about the population and never sees an
unredacted text.
"""
from __future__ import annotations

import json

from ..engine.taxonomy import TaxonomyIndex

__all__ = [
    "DEEP_REVIEW_INSTRUCTIONS",
    "label_codes",
    "ROOT_CAUSE_RULES",
    "RECURRING_SITUATIONS_ADPF",
    "classifier_system_prompt",
    "classifier_tool",
    "examples_lines",
    "umbrella_system_prompt",
    "umbrella_tool",
    "root_cause_fix_prompt",
]

# ROOT_CAUSE_CODEBOOK (locked) — rules R1–R7.
ROOT_CAUSE_RULES = """\
Root-cause codebook (locked) — how to write the root cause (the cause field):
The bar: a root cause states WHY the customer contacted the entity — the underlying issue, not the story of the case and not the name of the service.
R1 — A cause is not a case summary. Never copy or truncate the description. No case or reference numbers, no names, no employer names, no dates, no amounts specific to one case. Target 6–14 Arabic words; longer only for the " + " form in R5.
  ✗ «متابعة للحالة السابقة [رقم التتبع] راجعت بنك أبوظبي الأول مرتين، وأبلغني…»  ✓ «متابعة حالة سابقة بخصوص تعذر إيداع مبلغ ضم مدة الخدمة السابقة لدى البنك»
R2 — Follow-ups name the underlying subject: «متابعة حالة سابقة بخصوص <the actual issue>» — never restate the prior case. Abstract the particulars, keep the issue specific.
R3 — The cause must agree with the sub-classification: it must not name a service other than the chosen sub_classification.
R4 — Purpose beats channel. When the customer asks how to reach the entity in order to do something, the cause is the something. Add «(جهة عمل)» when the caller is an employer.
  ✗ «الاستفسار عن كيفية التواصل مع الصندوق»  ✓ «الاستفسار عن كيفية إنهاء خدمة موظف في الصندوق (جهة عمل)»
R5 — Multiple asks are joined with " + ": «الاستفسار عن قيمة مكافأة نهاية الخدمة عند الاستقالة + أثر صرفها على مدد الخدمة السابقة»
R6 — Out of scope is stated with its reason: the cause says why the matter is outside the entity's remit. (The main service follows the taxonomy's own rule for out-of-remit cases — see its edge cases.)
R7 — Follow the question, not the service. The CRM service name is context, not the answer: a case filed under a payment service that asks where the branch is has a locations cause.
"""

# The ROOT_CAUSE_CODEBOOK's recurring-situation table — ADPF wording.
RECURRING_SITUATIONS_ADPF = [
    ("Jan 2026 double payment being recovered", "الاستفسار عن سبب استقطاع مبلغ شهري من المعاش نتيجة صرف معاش شهر يناير مرتين بالخطأ"),
    ("Pension paid by the fund, not visible at the bank", "الاستفسار عن عدم استلام المعاش التقاعدي رغم صرفه من الصندوق"),
    ("Pension held — annual declaration expired", "الاستفسار عن إيقاف المعاش التقاعدي بسبب عدم تجديد الإقرار السنوي"),
    ("Contributions unpaid → Nafis support stopped", "الاستفسار عن عدم سداد جهة العمل للاشتراكات التقاعدية وأثره على دعم نافس"),
    ("Pension stopped — working after retirement", "الاستفسار عن إيقاف المعاش التقاعدي نتيجة الالتحاق بالعمل بعد التقاعد"),
    ("Beneficiary share cancelled — employment / marriage", "الاستفسار عن إلغاء استحقاق المستحق من المعاش نتيجة العمل / ... نتيجة الزواج"),
    ("Entitlement under the Dec-2023 amendments", "الاستفسار عن شروط استحقاق التقاعد بعد تعديلات القانون النافذة من ديسمبر 2023"),
    ("Employer routed to 024140131", "الاستفسار عن كيفية <purpose> في الصندوق (جهة عمل)"),
]


def label_codes(tax: TaxonomyIndex) -> dict[str, tuple[str, str]]:
    """Code → (main service, sub-classification), canonical names, in taxonomy order."""
    codes: dict[str, tuple[str, str]] = {}
    for i, main in enumerate(tax.main_names, 1):
        for j, sub in enumerate(tax.main_to_subs.get(main, []), 1):
            codes[f"M{i}.{j}"] = (main, sub)
    return codes


def _taxonomy_block(tax: TaxonomyIndex) -> str:
    lines = ["Taxonomy — main service (O) → sub-classification (N), with the code you return. "
             "Pick O first, then N under it:"]
    by_name = {m.name_ar: m for m in tax.taxonomy.main_services}
    for i, name in enumerate(tax.main_names, 1):
        main = by_name.get(name)
        guidance = f" — {main.guidance}" if main is not None and main.guidance else ""
        lines.append(f"• M{i} {name}{guidance}")
        if main is not None and main.signals:
            lines.append("    signals: " + "، ".join(main.signals[:14]))
        for j, sub in enumerate(tax.main_to_subs.get(name, []), 1):
            lines.append(f"    – M{i}.{j} {sub}")
    if tax.taxonomy.edge_cases:
        lines.append("Edge cases (codebook):")
        lines.extend(f"• {rule}" for rule in tax.taxonomy.edge_cases)
    return "\n".join(lines)


def examples_lines(examples: list, root_causes: bool, code_of: dict[tuple[str, str], str] | None = None) -> str:
    """Reviewed cases most similar to this batch — the reviewers' practice, shown not told."""
    if not examples:
        return ""
    lines = ["Reviewed cases similar to this batch — follow the reviewers' practice where the signals are ambiguous:"]
    for ex in examples:
        code = (code_of or {}).get((ex.main_service, ex.sub_classification))
        label = code or f"{ex.main_service} / {ex.sub_classification}"
        line = f"• H: {ex.description} | I: {ex.resolution} → {label}"
        if root_causes and ex.root_cause:
            line += f" | cause: {ex.root_cause}"
        lines.append(line)
    return "\n".join(lines)


def classifier_system_prompt(tax: TaxonomyIndex, *, root_causes: bool, entity: str,
                             recurring: list[tuple[str, str]] | None = None) -> str:
    """The Layer 2 classifier system prompt (Full Report Prompt §0 + the codebooks)."""
    other = tax.other_service or "أخرى"
    rc_field = (
        "- cause (the root cause): an Arabic sentence of 6–14 words stating why the customer contacted the "
        "entity — the reason, not the story, not the service name — written to the root-cause codebook below.\n"
        if root_causes else ""
    )
    parts = [
        f"You are a case classifier for {entity or 'a UAE government entity'}'s customer inquiries. "
        "Read each case's redacted description (H) and resolution response (I) and return the labels below "
        "through the classify_cases tool, one entry per case, under the case's id (c1, c2, …).",
        "",
        "Governing rules (classification codebook — the golden rule):",
        "- Read only description and resolution_text. When they disagree, the resolution decides — classify by what was actually handled.",
        "- Never treat the CRM case title or the recorded service tag or recorded type as truth; they are context only.",
        "- type (actual contact type): exactly one of استفسار | طلب خدمة | شكوى | شكر وثناء — «طلب خدمة» only when the agent executed an action on the customer's account or the system; an explanation, a link or a referral is «استفسار».",
        f"- sub (main service and sub-classification): the code of exactly one sub-classification, chosen under the right main service — e.g. M3.1 (or a code under «{other}» with the reason stated in reason{' and cause' if root_causes else ''}).",
        "- reason (classification reason): at most 5 Arabic words naming the decisive fact in I (or H) — what the agent did or said that settles the labels, e.g. «أحال إلى رابط الخدمة في تم» or «نفّذ تعديل الحساب المصرفي» or «يلزم الحضور الشخصي للمركز». Not the topic: never start with «استفسار عن» or «سؤال عن».",
        rc_field.rstrip("\n"),
        "- tt (true type): inquiry | service_request | complaint | incident | compliment | out_of_scope — service_request only when the agent executed an action on the customer's account or the system; an explanation, link or referral is inquiry. Flag cases that are really complaints, incidents or compliments although recorded as inquiries.",
        "- conf (confidence): 0–1, your certainty in type and sub together.",
        "- Fixed labels given for a case are already settled by a reviewer: repeat them unchanged and fill only the rest.",
        "- A rule-chain suggestion may be wrong; the rules above take precedence over it.",
        f"- «{other}» only when the case fits no main service at all; when torn between two, choose the closer one and lower conf instead.",
        "- Return nothing outside the tool call. Never return a number about the population of cases.",
        "",
        _taxonomy_block(tax),
    ]
    if root_causes:
        parts += ["", ROOT_CAUSE_RULES]
        if recurring:
            parts.append("Recurring situations — use this wording:")
            parts.extend(f"• {situation}: «{wording}»" for situation, wording in recurring)
    return "\n".join(p for p in parts if p is not None)


def classifier_tool(tax: TaxonomyIndex, *, root_causes: bool) -> dict:
    item = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "The case's id in this batch (c1, c2, …)."},
            "type": {"type": "string", "enum": ["استفسار", "طلب خدمة", "شكوى", "شكر وثناء"]},
            "tt": {
                "type": "string",
                "enum": ["inquiry", "service_request", "complaint", "incident", "compliment", "out_of_scope"],
            },
            "sub": {"type": "string", "enum": list(label_codes(tax))},
            "reason": {"type": "string"},
            "conf": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["id", "type", "tt", "sub", "reason", "conf"],
    }
    if root_causes:
        item["properties"]["cause"] = {"type": "string"}
        item["required"].append("cause")
    return {
        "name": "classify_cases",
        "description": "Return one label set per case, in input order.",
        "input_schema": {
            "type": "object",
            "properties": {"cases": {"type": "array", "items": item}},
            "required": ["cases"],
        },
    }


DEEP_REVIEW_INSTRUCTIONS = """\
Deep review — you are the second reviewer («يدوي - مُراجع»).
These cases were labelled by a first pass that was not confident, or whose labels broke a rule. For each case:
- Re-read H and I in full. The resolution decides when the two disagree.
- Name to yourself the two most likely main services and, under each, the most likely sub-classification; compare them against the signals, the edge cases and the reviewed examples; then decide.
- Keep a first-pass label only if it is still the best fit after that comparison; otherwise replace it.
- If the case has a root cause, check it against the root-cause codebook and rewrite it if it breaks a rule.
- Set confidence honestly for your final labels: below 0.65 only when the text genuinely supports more than one reading.
"""


def root_cause_fix_prompt() -> str:
    return (
        "Some root causes broke the root-cause codebook. For each case below, rewrite cause so it obeys "
        "the named rule, keeping every other label exactly as given. Return them through classify_cases."
    )


# ── Umbrella discovery (§0b) ─────────────────────────────────────────────────

UMBRELLA_SYSTEM = """\
You cluster the root causes of a UAE government entity's customer inquiries into "umbrellas" — thematic bundles that state the actual motive for contact.

Inputs: this period's distinct root causes with counts; the tenant's confirmed umbrellas from previous periods (may be empty); the target count range.

Rules:
- Assign each root cause to an existing confirmed umbrella when one fits; propose a new umbrella only for a cluster that fits none.
- An umbrella is a contact motive (why the customer contacted the entity), never a service name or a case type: "Procedures & requirements", "Eligibility & entitlement conditions", "Payment dates" — not "Pension service", not "Complaint".
- So an umbrella's name never contains a main-service or sub-classification name from service_names: a motive cuts across services (one umbrella holds the procedures questions of every service).
- Total umbrellas within the target range; previously confirmed umbrellas remain even with zero cases.
- Per umbrella: a concise formal Arabic name (3–6 words), the English equivalent, a one-sentence meaning in Arabic and in English, and new = true when proposed this period.
- Every root cause goes to exactly one umbrella; none left unassigned; never invent a root cause not in the input.
- Root causes are given as ids (rc1, rc2, …): list each umbrella's root-cause ids in its root_causes. An existing umbrella that gets root causes is returned with its id and root_causes only.
- Return the result through the cluster_root_causes tool only. Do not return case counts — the engine computes them from your assignment.
"""


def umbrella_system_prompt() -> str:
    return UMBRELLA_SYSTEM


def umbrella_tool() -> dict:
    return {
        "name": "cluster_root_causes",
        "description": "Umbrellas (existing reused, new flagged), each with the ids of its root causes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "umbrellas": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "ar": {"type": "string", "description": "New umbrellas only."},
                            "en": {"type": "string", "description": "New umbrellas only."},
                            "meaning_ar": {"type": "string", "description": "New umbrellas only."},
                            "meaning_en": {"type": "string", "description": "New umbrellas only."},
                            "new": {"type": "boolean"},
                            # Member ids under each umbrella (≈ 3 tokens a root cause) rather than one
                            # {"root_cause", "umbrella_id"} object per root cause (≈ 15): output is billed
                            # at eight times the input rate, and a quarter has thousands of root causes.
                            "root_causes": {"type": "array", "items": {"type": "string"},
                                            "description": "The ids of the root causes assigned to this umbrella."},
                        },
                        "required": ["id", "new", "root_causes"],
                    },
                },
            },
            "required": ["umbrellas"],
        },
    }


def umbrella_user_message(root_causes: list[tuple[str, str, int]], carried: list[dict],
                          target: tuple[int, int], service_names: list[str] | None = None) -> str:
    payload = {
        "target_range": f"{target[0]}-{target[1]}",
        "service_names": service_names or [],
        "carried_umbrellas": carried,
        "root_causes": [{"id": rid, "text": text, "count": count} for rid, text, count in root_causes],
    }
    return json.dumps(payload, ensure_ascii=False)
