"""
The model tiers of the classifier — batched, forced-tool calls.

Two modes. The **first pass** runs on the fast tier in batches of 40 with up to 20
similar reviewed examples per batch. The **deep review** («يدوي - مُراجع») is the second
pass over the cases the first pass was unsure of: the reasoning tier, batches of 10,
more similar examples per case, the first pass's labels shown for scrutiny, and an
explicit instruction to weigh the alternatives before deciding.

**Cost.** Measured on 500 reviewed Q2 cases, a batch of 20 carried ≈ 6.8k fixed prompt
tokens (rules, taxonomy, tool, examples) and each case ≈ 141 output tokens, at eight
times the input rate. So batches are 40 (the fixed part is paid half as often), and
the answer is short: batch-local ids, sub-classification codes, short keys, no
``evidence`` (see ``prompts``). Answers are mapped back to full names here, so the
rest of the classifier reads ``actual_contact_type``, ``main_service`` … as before.

Each case goes in redacted and truncated, with its context (recorded service tag and
type, which the prompt says are not truth), any labels a reviewer already fixed, and
the rule chain's suggestion. One label set comes back per case. A case the model
drops or a batch that fails is returned as ``None`` and the caller keeps the rule
chain's labels and queues the case for review — never a guess dressed as a label.
"""
from __future__ import annotations

import logging
from concurrent.futures import as_completed
from typing import Any, Callable

from ..core42 import DEEP_MODEL, FAST_MODEL, Core42Client, get_settings, tool_input
from ..core42.tokens import ScopedThreadPoolExecutor
from ..engine.parse import Case
from ..engine.taxonomy import TaxonomyIndex
from ..engine.text import fold_text
from .prompts import (
    DEEP_REVIEW_INSTRUCTIONS,
    classifier_system_prompt,
    classifier_tool,
    examples_lines,
    label_codes,
    root_cause_fix_prompt,
)

__all__ = ["ModelClassifier"]

logger = logging.getLogger(__name__)

_TEXT_LIMIT = 700
BATCH_SIZE = 40
DEEP_BATCH_SIZE = 10
MAX_WORKERS = 5
EXAMPLES_PER_CASE = 3
EXAMPLES_PER_BATCH = 20

# Long label keys (what the rest of the classifier reads) → the short keys the model writes.
_SHORT = {"actual_contact_type": "type", "true_type": "tt", "classification_reason": "reason",
          "reason": "reason", "confidence": "conf", "root_cause": "cause"}


def _tokens(text: str) -> set[str]:
    return {w for w in fold_text(text).split() if len(w) >= 3}


def _clip(text: str) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= _TEXT_LIMIT else text[:_TEXT_LIMIT] + "…"


class ModelClassifier:
    """Batches cases through the classifier tool and returns label sets by case id."""

    def __init__(self, tax: TaxonomyIndex, *, root_causes: bool, entity: str,
                 recurring: list[tuple[str, str]] | None = None,
                 client: Core42Client | None = None, deep: bool = False) -> None:
        self.tax = tax
        self.root_causes = root_causes
        self.client = client or Core42Client()
        self.deep = deep
        self.model = DEEP_MODEL if deep else FAST_MODEL
        self.batch_size = DEEP_BATCH_SIZE if deep else BATCH_SIZE
        self.examples_per_case = 6 if deep else EXAMPLES_PER_CASE
        self.system = classifier_system_prompt(
            tax, root_causes=root_causes, entity=entity, recurring=recurring
        ) + (("\n\n" + DEEP_REVIEW_INSTRUCTIONS) if deep else "")
        self.tool = classifier_tool(tax, root_causes=root_causes)
        self.codes = label_codes(tax)
        self.code_of = {pair: code for code, pair in self.codes.items()}
        self.examples = list(tax.taxonomy.examples)
        self._example_tokens = [_tokens(f"{e.description} {e.resolution}") for e in self.examples]

    def _similar_examples(self, cases: list[Case]) -> list:
        """The reviewed examples closest to this batch, a few per case (by word overlap)."""
        if not self.examples:
            return []
        chosen: list[int] = []
        for case in cases:
            words = _tokens(f"{case.description} {case.resolution_text}")
            if not words:
                continue
            scored = sorted(
                ((len(words & ex) / ((len(words) * len(ex)) ** 0.5 or 1), i) for i, ex in enumerate(self._example_tokens)),
                reverse=True,
            )
            for score, i in scored[:self.examples_per_case]:
                if score > 0 and i not in chosen:
                    chosen.append(i)
            if len(chosen) >= EXAMPLES_PER_BATCH:
                break
        return [self.examples[i] for i in chosen[:EXAMPLES_PER_BATCH]]

    def _short(self, labels: dict[str, Any]) -> dict[str, Any]:
        """Labels as the model writes them: a sub-classification code, short keys."""
        out: dict[str, Any] = {}
        main, sub = labels.get("main_service"), labels.get("sub_classification")
        if main or sub:
            code = self.code_of.get((self.tax.main(main), self.tax.sub(sub)))
            out["sub"] = code or " / ".join(x for x in (main, sub) if x)
        for key, value in labels.items():
            if key in _SHORT and value not in (None, ""):
                out[_SHORT[key]] = value
        return out

    def _long(self, answer: dict[str, Any], case_id: str) -> dict[str, Any]:
        """A short answer back in the classifier's own field names."""
        out: dict[str, Any] = {"case_id": case_id}
        code = str(answer.get("sub") or "").strip().split(" ")[0]  # «M3.1 <name>» → M3.1
        if code in self.codes:
            out["main_service"], out["sub_classification"] = self.codes[code]
        for long_key, short_key in (("actual_contact_type", "type"), ("true_type", "tt"),
                                    ("classification_reason", "reason"), ("confidence", "conf"),
                                    ("root_cause", "cause")):
            if short_key in answer:
                out[long_key] = answer[short_key]
        return out

    def _case_block(self, case: Case, suggestion: dict[str, Any] | None,
                    fixed: dict[str, Any], note: str | None = None, ref: str | None = None) -> str:
        lines = [
            f"id: {ref or case.case_id}",
            f"H (description): {_clip(case.description) or '«لم يُزوَّد»'}",
            f"I (resolution): {_clip(case.resolution_text) or '«لم يُزوَّد»'}",
        ]
        context = []
        if case.crm_service:
            context.append(f"recorded service tag: {case.crm_service}")
        if case.case_type_raw:
            context.append(f"recorded type: {case.case_type_raw}")
        if context:
            lines.append("context (not truth): " + "; ".join(context))
        if fixed:
            lines.append("fixed labels (keep unchanged): " + "; ".join(f"{k}={v}" for k, v in self._short(fixed).items()))
        if suggestion:
            head = (
                "first-pass labels (scrutinise — keep only if they are the best fit): " if self.deep
                else "rule-chain suggestion (may be wrong): "
            )
            lines.append(head + "; ".join(f"{k}={v}" for k, v in self._short(suggestion).items()))
        if note:
            lines.append(("why it is under review: " if self.deep else "FIX: ") + note)
        return "\n".join(lines)

    def _call(self, blocks: list[str], instruction: str, examples: list | None = None) -> list[dict[str, Any]]:
        shown = examples_lines(examples or [], self.root_causes, self.code_of)
        if shown:
            instruction = shown + "\n\n" + instruction
        message = self.client.messages.create(
            model=self.model,
            max_tokens=7000 if self.root_causes else 5000,
            system=self.system,
            tools=[self.tool],
            tool_choice={"type": "any"},
            stage="deep_review" if self.deep else "classification",
            # The deep review is told to reason; the first pass is not (bulk, cheap).
            reasoning_effort=(get_settings().deep_reasoning_effort or None) if self.deep else None,
            messages=[{
                "role": "user",
                "content": instruction + "\n\n" + "\n\n---\n\n".join(blocks),
            }],
        )
        cases = (tool_input(message) or {}).get("cases") or []  # every tool call, not only the first
        return [c for c in cases if isinstance(c, dict)]

    def classify(
        self,
        items: list[tuple[Case, dict[str, Any] | None, dict[str, Any], str | None]],
        progress: Callable[[int, int], None] | None = None,
        *,
        fixing: bool = False,
    ) -> dict[str, dict[str, Any]]:
        """Label sets by case id. ``items``: (case, rule suggestion, fixed labels, fix note)."""
        if not items:
            return {}
        batches = [items[i:i + self.batch_size] for i in range(0, len(items), self.batch_size)]
        instruction = (
            root_cause_fix_prompt() if fixing
            else "Review these {n} cases as the second reviewer. Return exactly one entry per case_id." if self.deep
            else "Classify these {n} cases. Return exactly one entry per case_id."
        )
        results: dict[str, dict[str, Any]] = {}
        done = 0

        def run(batch):
            refs = {f"c{i}": c.case_id for i, (c, *_) in enumerate(batch, 1)}
            blocks = [self._case_block(c, s, f, n, ref=f"c{i}") for i, (c, s, f, n) in enumerate(batch, 1)]
            examples = self._similar_examples([c for c, *_ in batch])
            try:
                answers = self._call(blocks, instruction.replace("{n}", str(len(batch))), examples)
            except Exception as exc:  # a failed batch costs its cases, not the run
                logger.warning("Classifier batch of %d failed: %s", len(batch), exc)
                if _is_gateway_outage(exc):
                    raise
                return []
            return [self._long(a, refs[str(a.get("id", "")).strip()]) for a in answers
                    if str(a.get("id", "")).strip() in refs]

        with ScopedThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = [pool.submit(run, batch) for batch in batches]
            try:
                for future in as_completed(futures):
                    for item in future.result():
                        cid = str(item.get("case_id", "")).strip()
                        if cid:
                            results[cid] = item
                    done += 1
                    if progress:
                        progress(done, len(batches))
            except BaseException:
                # A stopped run (runtime ceiling, gateway outage) must not keep paying
                # for the batches still queued behind it.
                for future in futures:
                    future.cancel()
                raise
        # One more pass for the cases no answer came back for (a batch that failed, or a
        # model that left some out), before the caller falls back to the rule chain's or
        # the first pass's labels.
        missing = [item for item in items if item[0].case_id not in results]
        if missing:
            logger.warning("%s: no answer for %d of %d case(s); asking once more.",
                           "Deep review" if self.deep else "Classifier", len(missing), len(items))
            retry = [missing[i:i + self.batch_size] for i in range(0, len(missing), self.batch_size)]
            with ScopedThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                for answers in pool.map(run, retry):
                    for item in answers:
                        cid = str(item.get("case_id", "")).strip()
                        if cid:
                            results.setdefault(cid, item)
        return results


def _is_gateway_outage(exc: Exception) -> bool:
    """Authentication and configuration failures fail every batch alike — stop."""
    from ..core42 import AuthenticationError

    return isinstance(exc, AuthenticationError)
