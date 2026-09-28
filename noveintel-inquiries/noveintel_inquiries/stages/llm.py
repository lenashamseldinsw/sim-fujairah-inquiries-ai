"""
The pipeline's door to Core42.

The shared Core42 integration is vendored into this package at
``..core42``, so the stages reach it by ordinary relative import. In the
Streamlit application this module existed to insert a path — the flows were
loaded by file path and their ``sys.modules`` entries purged between flows, so
a package-relative import was not available to them.

Here the service *is* one flow and the package is installed, so that problem
does not exist. The module is kept because every stage imports Core42 through
it: one seam to change if the gateway ever moves again.
"""

from __future__ import annotations

from ..core42 import (
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
