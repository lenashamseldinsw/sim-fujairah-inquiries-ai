"""
Umbrella discovery — the run-level Layer 2 step (Full Report Prompt §0b, BO ruling
2026-09-22).

Umbrellas are not a platform taxonomy. After every in-scope case has a root cause,
this step groups the run's distinct root causes into umbrellas — contact motives,
named in Arabic and English — reusing the tenant's carried-forward set first and
proposing new ones only for what fits none. The Domain Admin then confirms, renames,
merges or splits them, and the confirmed set comes back next period as
``reference_lists.umbrellas``. A carried umbrella with no cases this period is kept
at zero, never dropped, so comparisons hold.

A quarter can have thousands of distinct root causes (ADPF Q2 2026: 5,766), so they
are sent in chunks, most frequent first, each chunk seeing every umbrella defined so
far. If the run ends above the target range, one merge call folds the *new* umbrellas
together; carried ones are never merged away.

Counts are the engine's: the model assigns root causes by id and never returns a
number about the population (hard rule 10).
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Callable

from ..core42 import CHAT_MODEL, LIGHT_MODEL, Core42Client, tool_input
from ..engine.compute import Umbrella
from ..engine.parse import Case
from ..engine.text import clean_label, fold_text
from .labels import UmbrellaRegistry
from .prompts import umbrella_system_prompt, umbrella_tool, umbrella_user_message

__all__ = ["discover_umbrellas", "UNASSIGNED_ID"]

logger = logging.getLogger(__name__)

CHUNK = 350
UNASSIGNED_ID = "unassigned"

_MERGE_TOOL = {
    "name": "merge_umbrellas",
    "description": "Fold the new umbrellas into fewer, keeping every carried one.",
    "input_schema": {
        "type": "object",
        "properties": {
            "mapping": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"from_id": {"type": "string"}, "to_id": {"type": "string"}},
                    "required": ["from_id", "to_id"],
                },
            }
        },
        "required": ["mapping"],
    },
}


def _call(client: Core42Client, model: str, user: str) -> dict:
    message = client.messages.create(
        model=model,
        max_tokens=12000,
        system=umbrella_system_prompt(),
        tools=[umbrella_tool()],
        tool_choice={"type": "any"},
        stage="umbrella_discovery",
        messages=[{"role": "user", "content": user}],
    )
    return tool_input(message) or {}


def discover_umbrellas(
    cases: list[Case],
    registry: UmbrellaRegistry,
    target: tuple[int, int],
    *,
    client: Core42Client | None = None,
    progress: Callable[[int, int], None] | None = None,
    service_names: list[str] | None = None,
) -> list[str]:
    """Assign every unbundled case with a root cause to an umbrella. Returns warnings."""
    warnings: list[str] = []
    pending = [c for c in cases if c.root_cause and not c.bundle]
    if not pending:
        return warnings

    # A root cause already bundled on a frozen case keeps that umbrella.
    known: dict[str, str] = {}
    for c in cases:
        if c.root_cause and c.bundle:
            known.setdefault(fold_text(c.root_cause), c.bundle)

    counts = Counter(clean_label(c.root_cause) for c in pending if fold_text(c.root_cause) not in known)
    distinct = [rc for rc, _ in counts.most_common()]
    assignment: dict[str, str] = {}
    client = client or Core42Client()
    chunks = [distinct[i:i + CHUNK] for i in range(0, len(distinct), CHUNK)]

    for index, chunk in enumerate(chunks):
        remaining = chunk
        # Up to three passes: listing member ids is cheap but a model can leave some out,
        # so what is missing is sent again (only the missing ids) before anything falls
        # into the unassigned bucket.
        for attempt in range(3):
            if not remaining:
                break
            ids = {f"rc{n + 1}": rc for n, rc in enumerate(remaining)}
            carried = [
                {"id": u.id, "ar": u.name_ar, "en": u.name_en, "meaning": u.meaning_ar or u.meaning_en}
                for u in registry.umbrellas if u.id != UNASSIGNED_ID
            ]
            user = umbrella_user_message(
                [(rid, rc, counts[rc]) for rid, rc in ids.items()], carried, target, service_names
            )
            try:
                # The first chunk defines and names the umbrellas (reasoning tier); later chunks
                # mostly file root causes under them (light tier — measured to hold).
                result = _call(client, CHAT_MODEL if index == 0 and attempt == 0 else LIGHT_MODEL, user)
            except Exception as exc:
                logger.warning("Umbrella discovery chunk %d failed: %s", index + 1, exc)
                result = {}
            id_map = _absorb_umbrellas(result.get("umbrellas") or [], registry)
            rows = [(rid, item.get("id")) for item in result.get("umbrellas") or [] for rid in item.get("root_causes") or []]
            rows += [(r.get("root_cause"), r.get("umbrella_id")) for r in result.get("assignment") or []]  # older shape
            for rid, given in rows:
                rc = ids.get(str(rid or "").strip())
                uid = id_map.get(str(given or "").strip())
                if rc and uid and rc not in assignment:
                    assignment[rc] = uid
            remaining = [rc for rc in remaining if rc not in assignment]
        if progress:
            progress(index + 1, len(chunks))

    leftover = [rc for rc in distinct if rc not in assignment]
    if leftover:
        fallback = registry.get(UNASSIGNED_ID)
        if fallback is None:
            fallback = Umbrella(
                id=UNASSIGNED_ID, name_ar="أسباب غير مسندة إلى حزمة", name_en="Root causes not assigned to an umbrella",
                meaning_ar="أسباب لم يتمكن خطوة التجميع من إسنادها؛ تحتاج إلى مراجعة مسؤول المجال.",
                meaning_en="Causes the clustering step could not place; they need the Domain Admin's review.",
                new=True,
            )
            registry.umbrellas.append(fallback)
        for rc in leftover:
            assignment[rc] = UNASSIGNED_ID
        warnings.append(f"{len(leftover)} root cause(s) could not be assigned to an umbrella.")

    _merge_if_over(registry, assignment, counts, target, client, warnings)

    for c in pending:
        key = fold_text(c.root_cause)
        c.bundle = known.get(key) or assignment.get(clean_label(c.root_cause))
    return warnings


def _absorb_umbrellas(proposed: list[dict], registry: UmbrellaRegistry) -> dict[str, str]:
    """Register the model's umbrellas; map the ids it used to registry ids."""
    id_map: dict[str, str] = {u.id: u.id for u in registry.umbrellas}
    for item in proposed:
        given = str(item.get("id", "")).strip()
        if given in id_map:
            existing = registry.get(id_map[given])
            if existing and not existing.name_en and item.get("en"):
                existing.name_en = clean_label(item["en"])
            continue
        name = clean_label(item.get("ar"))
        if not name:
            continue
        uid = registry.id_for(name, new=True)
        umbrella = registry.get(uid)
        if umbrella and umbrella.new:
            umbrella.name_en = umbrella.name_en or clean_label(item.get("en"))
            umbrella.meaning_ar = umbrella.meaning_ar or clean_label(item.get("meaning_ar") or item.get("meaning"))
            umbrella.meaning_en = umbrella.meaning_en or clean_label(item.get("meaning_en"))
        id_map[given] = uid
    return id_map


def _merge_if_over(registry, assignment, counts, target, client, warnings) -> None:
    live = [u for u in registry.umbrellas if u.id != UNASSIGNED_ID]
    if len(live) <= target[1]:
        return
    sizes = Counter()
    for rc, uid in assignment.items():
        sizes[uid] += counts.get(rc, 0)
    payload = {
        "target_range": f"{target[0]}-{target[1]}",
        "instruction": "Fold umbrellas with new=true into others so the total is within the target range. "
                       "Carried umbrellas (new=false) must map to themselves.",
        "umbrellas": [
            {"id": u.id, "ar": u.name_ar, "en": u.name_en, "meaning": u.meaning_ar, "new": u.new, "size_rank": rank + 1}
            for rank, u in enumerate(sorted(live, key=lambda u: -sizes.get(u.id, 0)))
        ],
    }
    try:
        message = client.messages.create(
            model=CHAT_MODEL, max_tokens=4000, system=umbrella_system_prompt(),
            tools=[_MERGE_TOOL], tool_choice={"type": "any"}, stage="umbrella_discovery",
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        )
        mapping = (tool_input(message) or {}).get("mapping") or []
    except Exception as exc:
        warnings.append(f"Umbrella merge failed ({exc}); {len(live)} umbrellas kept.")
        return
    valid = {u.id for u in registry.umbrellas}
    remap = {}
    for row in mapping:
        src, dst = str(row.get("from_id", "")), str(row.get("to_id", ""))
        source = registry.get(src)
        if source and source.new and dst in valid and dst != src:
            remap[src] = dst
    for rc, uid in list(assignment.items()):
        while uid in remap:
            uid = remap[uid]
        assignment[rc] = uid
    registry.umbrellas[:] = [u for u in registry.umbrellas if u.id not in remap]
