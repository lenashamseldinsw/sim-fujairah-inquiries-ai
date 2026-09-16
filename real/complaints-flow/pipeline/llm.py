"""
The pipeline's door to Core42.

The shared client lives in ``real/core42/`` so both flows run the same
integration, but a pipeline module can only rely on relative imports: the flows
are loaded by path and their ``sys.modules`` entries are purged between flows to
stop the inquiries and complaints pipelines from importing each other's stages.

So every stage imports Core42 from here — ``from .llm import Core42Client,
CHAT_MODEL`` — and this module does the one path insertion needed to reach the
shared package. ``core42`` is deliberately named so it matches none of the
purge patterns, which means the client singleton, the concurrency gate and the
token ledger survive a flow switch.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REAL_ROOT = str(Path(__file__).resolve().parents[2])
if _REAL_ROOT not in sys.path:
    sys.path.insert(0, _REAL_ROOT)

from core42 import (  # noqa: E402  (path must be set up first)
    APIError,
    CHAT_MODEL,
    FAST_MODEL,
    Core42Client,
    RateLimitError,
    clean_llm_json,
    get_settings,
    loads_repaired,
    reset_token_tracking,
    token_summary,
)

__all__ = [
    "APIError",
    "CHAT_MODEL",
    "FAST_MODEL",
    "Core42Client",
    "RateLimitError",
    "clean_llm_json",
    "get_settings",
    "loads_repaired",
    "reset_token_tracking",
    "token_summary",
]
