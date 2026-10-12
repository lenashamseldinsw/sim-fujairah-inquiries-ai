"""
The model tiers of the classifier — batched, forced-tool calls.

Two modes. The **first pass** runs on the fast tier in batches of 20 with a few similar
reviewed examples per case. The **deep review** («يدوي - مُراجع») is the second pass
over the cases the first pass was unsure of: the reasoning tier, batches of 5, twice
as many similar examples, the first pass's labels shown for scrutiny, and an explicit
instruction to weigh the alternatives before deciding.

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

from ..core42 import DEEP_MODEL, FAST_MODEL, Core42Client, get_settings
from ..core42.tokens import ScopedThreadPoolExecutor
from ..engine.parse import Case
from ..engine.taxonomy import TaxonomyIndex
from ..engine.text import fold_text
from .prompts import (
    DEEP_REVIEW_INSTRUCTIONS,
    classifier_system_prompt,
    classifier_tool,
    examples_lines,
    root_cause_fix_prompt,
)

__all__ = ["ModelClassifier"]

logger = logging.getLogger(__name__)

_TEXT_LIMIT = 700
BATCH_SIZE = 20
MAX_WORKERS = 5
EXAMPLES_PER_CASE = 3
EXAMPLES_PER_BATCH = 30


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
        self.batch_size = 5 if deep else BATCH_SIZE
        self.examples_per_case = 6 if deep else EXAMPLES_PER_CASE
        self.system = classifier_system_prompt(
            tax, root_causes=root_causes, entity=entity, recurring=recurring
        ) + (("\n\n" + DEEP_REVIEW_INSTRUCTIONS) if deep else "")
        self.tool = classifier_tool(tax, root_causes=root_causes)
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

    def _case_block(self, case: Case, suggestion: dict[str, Any] | None,
                    fixed: dict[str, Any], note: str | None = None) -> str:
        lines = [
            f"case_id: {case.case_id}",
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
            lines.append("fixed labels (keep unchanged): " + "; ".join(f"{k}={v}" for k, v in fixed.items()))
        if suggestion:
            head = (
                "first-pass labels (scrutinise — keep only if they are the best fit): " if self.deep
                else "rule-chain suggestion (may be wrong): "
            )
            lines.append(head + "; ".join(f"{k}={v}" for k, v in suggestion.items() if v not in (None, "")))
        if note:
            lines.append(("why it is under review: " if self.deep else "FIX: ") + note)
        return "\n".join(lines)

    def _call(self, blocks: list[str], instruction: str, examples: list | None = None) -> list[dict[str, Any]]:
        shown = examples_lines(examples or [], self.root_causes)
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
        for block in message.content:
            if getattr(block, "type", "") == "tool_use":
                cases = (block.input or {}).get("cases") or []
                return [c for c in cases if isinstance(c, dict)]
        return []

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
            blocks = [self._case_block(c, s, f, n) for c, s, f, n in batch]
            examples = self._similar_examples([c for c, *_ in batch])
            try:
                return self._call(blocks, instruction.replace("{n}", str(len(batch))), examples)
            except Exception as exc:  # a failed batch costs its cases, not the run
                logger.warning("Classifier batch of %d failed: %s", len(batch), exc)
                if _is_gateway_outage(exc):
                    raise
                return []

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
        return results


def _is_gateway_outage(exc: Exception) -> bool:
    """Authentication and configuration failures fail every batch alike — stop."""
    from ..core42 import AuthenticationError

    return isinstance(exc, AuthenticationError)
