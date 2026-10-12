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

The classifier never sees a number about the population and never sees an
unredacted text.
"""
from __future__ import annotations

import json

from ..engine.taxonomy import TaxonomyIndex

__all__ = [
    "DEEP_REVIEW_INSTRUCTIONS",
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
Root-cause codebook (locked) — how to write root_cause:
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


def _taxonomy_block(tax: TaxonomyIndex) -> str:
    lines = ["Taxonomy — main_service (O) → sub_classification (N). Pick O first, then N under it:"]
    for main in tax.taxonomy.main_services:
        guidance = f" — {main.guidance}" if main.guidance else ""
        lines.append(f"• {main.name_ar}{guidance}")
        if main.signals:
            lines.append("    signals: " + "، ".join(main.signals[:14]))
        for sub in main.sub_classifications:
            lines.append(f"    – {sub.name_ar}")
    if tax.taxonomy.edge_cases:
        lines.append("Edge cases (codebook):")
        lines.extend(f"• {rule}" for rule in tax.taxonomy.edge_cases)
    return "\n".join(lines)


def examples_lines(examples: list, root_causes: bool) -> str:
    """Reviewed cases most similar to this batch — the reviewers' practice, shown not told."""
    if not examples:
        return ""
    lines = ["Reviewed cases similar to this batch — follow the reviewers' practice where the signals are ambiguous:"]
    for ex in examples:
        line = f"• H: {ex.description} | I: {ex.resolution} → {ex.main_service} / {ex.sub_classification}"
        if root_causes and ex.root_cause:
            line += f" | root_cause: {ex.root_cause}"
        lines.append(line)
    return "\n".join(lines)


def classifier_system_prompt(tax: TaxonomyIndex, *, root_causes: bool, entity: str,
                             recurring: list[tuple[str, str]] | None = None) -> str:
    """The Layer 2 classifier system prompt (Full Report Prompt §0 + the codebooks)."""
    other = tax.other_service or "أخرى"
    rc_field = (
        "- root_cause: an Arabic sentence of 6–14 words stating why the customer contacted the entity — "
        "the reason, not the story, not the service name — written to the root-cause codebook below.\n"
        if root_causes else ""
    )
    parts = [
        f"You are a case classifier for {entity or 'a UAE government entity'}'s customer inquiries. "
        "Read each case's redacted description (H) and resolution response (I) and return the labels below "
        "through the classify_cases tool, one entry per case.",
        "",
        "Governing rules (classification codebook — the golden rule):",
        "- Read only description and resolution_text. When they disagree, the resolution decides — classify by what was actually handled.",
        "- Never treat the CRM case title or the recorded service tag or recorded type as truth; they are context only.",
        "- actual_contact_type: exactly one of استفسار | طلب خدمة | شكوى | شكر وثناء — «طلب خدمة» only when the agent executed an action on the customer's account or the system; an explanation, a link or a referral is «استفسار».",
        f"- main_service: exactly one main service from the taxonomy (or «{other}» with the reason stated in classification_reason{' and root_cause' if root_causes else ''}).",
        "- sub_classification: exactly one sub-classification listed under the chosen main_service.",
        "- classification_reason: one short Arabic sentence pointing to what in H or I decided the labels.",
        rc_field.rstrip("\n"),
        "- true_type: inquiry | service_request | complaint | incident | compliment | out_of_scope — service_request only when the agent executed an action on the customer's account or the system; an explanation, link or referral is inquiry. Flag cases that are really complaints, incidents or compliments although recorded as inquiries.",
        "- confidence: 0–1, your certainty in actual_contact_type and sub_classification together.",
        "- evidence: one short sentence pointing to what in H or I decided the labels.",
        "- Fixed labels given for a case are already settled by a reviewer: repeat them unchanged and fill only the rest.",
        "- A rule-chain suggestion may be wrong; the rules above take precedence over it.",
        f"- «{other}» only when the case fits no main service at all; when torn between two, choose the closer one and lower the confidence instead.",
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
            "case_id": {"type": "string"},
            "actual_contact_type": {"type": "string", "enum": ["استفسار", "طلب خدمة", "شكوى", "شكر وثناء"]},
            "true_type": {
                "type": "string",
                "enum": ["inquiry", "service_request", "complaint", "incident", "compliment", "out_of_scope"],
            },
            "main_service": {"type": "string", "enum": tax.main_names},
            "sub_classification": {"type": "string", "enum": tax.sub_names},
            "classification_reason": {"type": "string"},
            "evidence": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": [
            "case_id", "actual_contact_type", "true_type", "main_service",
            "sub_classification", "classification_reason", "evidence", "confidence",
        ],
    }
    if root_causes:
        item["properties"]["root_cause"] = {"type": "string"}
        item["required"].append("root_cause")
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
        "Some root causes broke the root-cause codebook. For each case below, rewrite root_cause so it obeys "
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
- Root causes are given as ids (rc1, rc2, …); assign by id.
- Return the result through the cluster_root_causes tool only. Do not return case counts — the engine computes them from your assignment.
"""


def umbrella_system_prompt() -> str:
    return UMBRELLA_SYSTEM


def umbrella_tool() -> dict:
    return {
        "name": "cluster_root_causes",
        "description": "Umbrellas (existing reused, new flagged) and the root-cause → umbrella assignment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "umbrellas": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "ar": {"type": "string"},
                            "en": {"type": "string"},
                            "meaning_ar": {"type": "string"},
                            "meaning_en": {"type": "string"},
                            "new": {"type": "boolean"},
                        },
                        "required": ["id", "ar", "en", "meaning_ar", "meaning_en", "new"],
                    },
                },
                "assignment": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "root_cause": {"type": "string", "description": "The root cause id, e.g. rc12."},
                            "umbrella_id": {"type": "string"},
                        },
                        "required": ["root_cause", "umbrella_id"],
                    },
                },
            },
            "required": ["umbrellas", "assignment"],
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
