"""
Case groups — the unit the qualitative analysis reasons over and the engine counts.

A group is one (main service, sub-classification) pair over the labelled cases. The
analysis model sees each group's size, its contact-type mix, a few redacted sample
cases and, with X8, its most frequent root causes; it then assigns whole groups to the
items it names (a friction, a notification opportunity). The engine sums the group
sizes. So every count in S4–S6 is a sum of frozen labels, and the model never emits a
number (R6, hard rule 10).
"""
from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field

from ..engine.parse import Case

__all__ = ["CaseGroup", "build_groups", "group_payload"]

SAMPLES_PER_GROUP = 6
MAX_GROUPS = 40
_CLIP = 240


@dataclass
class CaseGroup:
    id: str
    main_service: str
    sub_classification: str
    cases: list[Case] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.cases)

    def case_ids(self, limit: int | None = None) -> list[str]:
        ids = [c.case_id for c in self.cases]
        return ids[:limit] if limit else ids


def build_groups(cases: list[Case]) -> list[CaseGroup]:
    """Groups by (main service, sub-classification), largest first, capped."""
    buckets: dict[tuple[str, str], list[Case]] = {}
    for case in cases:
        if case.main_service and case.sub_classification:
            buckets.setdefault((case.main_service, case.sub_classification), []).append(case)
    ordered = sorted(buckets.items(), key=lambda kv: -len(kv[1]))[:MAX_GROUPS]
    return [
        CaseGroup(id=f"g{i + 1}", main_service=k[0], sub_classification=k[1], cases=v)
        for i, (k, v) in enumerate(ordered)
    ]


def _clip(text: str) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= _CLIP else text[:_CLIP] + "…"


def group_payload(group: CaseGroup, *, seed: int = 7, samples: int = SAMPLES_PER_GROUP) -> dict:
    """What the analysis model sees of one group. Redacted text only."""
    rng = random.Random(f"{seed}:{group.id}")
    with_text = [c for c in group.cases if c.description or c.resolution_text]
    picked = rng.sample(with_text, min(samples, len(with_text)))
    payload = {
        "group_id": group.id,
        "main_service": group.main_service,
        "sub_classification": group.sub_classification,
        "cases": group.size,
        "contact_types": dict(Counter(c.contact_type for c in group.cases if c.contact_type).most_common()),
        "samples": [
            {"case_id": c.case_id, "description": _clip(c.description), "resolution": _clip(c.resolution_text)}
            for c in picked
        ],
    }
    roots = Counter(c.root_cause for c in group.cases if c.root_cause)
    if roots:
        payload["top_root_causes"] = [rc for rc, _ in roots.most_common(5)]
    return payload
