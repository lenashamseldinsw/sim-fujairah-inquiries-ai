"""
Core42 configuration.

Reads the environment once and caches it. Everything the two Core42 endpoints
need lives here, so a deployment is configured in exactly one place.

Settings are cached (``lru_cache``) and the chat client is a module-level
singleton, so editing ``.env`` while the process runs changes nothing — the
process must be fully restarted. Error messages say so, because the
"I fixed it and it's still broken" loop is expensive.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, Optional

try:  # optional: the app already ships python-dotenv
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is a declared dependency
    def load_dotenv(*_args, **_kwargs):
        return False


# Model *tiers*, not deployments. Call sites ask for a tier and the settings map
# it onto whatever CORE42_MODEL / CORE42_MODEL_FAST name the deployment uses.
CHAT_MODEL = "core42-chat"   # reasoning tier: analysis, gap analysis, report prose
FAST_MODEL = "core42-fast"   # bulk tier: per-case classification

_RESTART_HINT = (
    "Set them in the .env file next to the app (or as environment variables of "
    "the same name, or in .streamlit/secrets.toml) and fully restart the "
    "process: settings are cached and the OpenAI client is a module-level "
    "singleton, so an in-place edit does not take effect until restart."
)


def _normalize_base_url(value: str) -> str:
    """Strip a trailing '/chat/completions' and any trailing slashes.

    Deployments frequently hand out a base URL with the chat path already
    appended. The OpenAI SDK appends the path itself, so that form works for
    chat completions only by accident of the gateway and breaks the Responses
    API. Normalising once here means both endpoints can read the same value.
    """
    cleaned = (value or "").strip().rstrip("/")
    if cleaned.endswith("/chat/completions"):
        cleaned = cleaned[: -len("/chat/completions")]
    return cleaned.rstrip("/")


def _env(name: str, default: str = "", snapshot: Optional[Dict[str, str]] = None) -> str:
    """Read a setting from the environment, then from Streamlit secrets.

    Streamlit Community Cloud has no .env file — secrets.toml is the only way to
    supply credentials there — so the secrets store is checked as a fallback.
    Importing streamlit here is safe: it is a hard dependency of the app, and the
    lookup is wrapped because st.secrets raises when no secrets file exists.

    ``snapshot`` is the environment as it stood *before* anything touched
    ``st.secrets``, and reading it is not optional: loading Streamlit's secrets
    copies every top-level value into ``os.environ``, so a blank
    ``CORE42_API_KEY = ""`` left in secrets.toml overwrites the real key from
    .env the moment any other setting falls through to secrets.
    """
    source = snapshot if snapshot is not None else os.environ
    value = source.get(name)
    if value:
        return value
    try:
        import streamlit as st  # noqa: PLC0415 - optional, runtime-only lookup

        secret = st.secrets.get(name)
        if secret:
            return str(secret)
    except Exception:
        pass
    return default


def _env_float(name: str, default: float, snapshot: Optional[Dict[str, str]] = None) -> float:
    raw = _env(name, "", snapshot)
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _env_int(name: str, default: int, snapshot: Optional[Dict[str, str]] = None) -> int:
    raw = _env(name, "", snapshot)
    try:
        return int(float(raw)) if raw else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Core42Settings:
    api_key: str = ""
    base_url: str = "https://api.core42.ai/v1"

    # Two tiers, mirroring the pipeline's original Sonnet/Haiku split: the
    # reasoning model for analysis and report prose, the fast model for bulk
    # per-case classification.
    model: str = "gpt-5.1"
    model_fast: str = "gpt-5.1"
    websearch_model: str = "gpt-5.1"

    max_output_tokens: int = 32768
    # Reasoning models spend part of the output budget on reasoning tokens that
    # never reach `content`, so a call site asking for 8000 visible tokens needs
    # headroom or it truncates mid-JSON.
    output_token_headroom: float = 1.5
    timeout: float = 240.0

    # In-flight Core42 requests PER PROCESS (0 = uncapped). Stage 3 fans out to
    # 5 threads and Stage 6 to 7-9, so without a cap the gateway sees far more
    # concurrency than it tolerates and answers with 429s.
    max_concurrency: int = 4

    max_retries: int = 2
    retry_delay: float = 2.0

    # Accepted and NOT sent: gpt-5.1-class reasoning models reject a non-default
    # temperature. Kept so call sites and the setting need no churn.
    temperature: float = 0.2

    # Model-name aliases, so a stray legacy slug still resolves to a real model.
    aliases: Dict[str, str] = field(default_factory=dict)

    def resolve_model(self, name: Optional[str]) -> str:
        """Map a requested model name onto a configured Core42 deployment.

        Call sites name a *tier* (``CHAT_MODEL`` / ``FAST_MODEL``) rather than a
        deployment, so switching model is one environment variable and never a
        code change. The tier names are resolved here rather than at import time,
        because settings are not readable when the pipeline modules are imported.
        """
        if not name:
            return self.model
        if name == CHAT_MODEL:
            return self.model
        if name == FAST_MODEL:
            return self.model_fast
        if name in self.aliases:
            return self.aliases[name]
        lowered = name.lower()
        if lowered.startswith("claude-"):
            # Legacy Anthropic slug: the fast tier kept the bulk work.
            return self.model_fast if "haiku" in lowered else self.model
        return name

    def require_configured(self) -> None:
        missing = [
            name
            for name, value in (
                ("CORE42_API_KEY", self.api_key),
                ("CORE42_BASE_URL", self.base_url),
            )
            if not (value or "").strip()
        ]
        if missing:
            raise ValueError(
                f"Core42 is not configured — missing: {', '.join(missing)}. {_RESTART_HINT}"
            )


@lru_cache(maxsize=1)
def get_settings() -> Core42Settings:
    load_dotenv()
    # Snapshot the environment before any secrets lookup can mutate it — see _env.
    env = dict(os.environ)
    model = _env("CORE42_MODEL", "gpt-5.1", env)
    return Core42Settings(
        api_key=_env("CORE42_API_KEY", "", env).strip(),
        base_url=_normalize_base_url(_env("CORE42_BASE_URL", "https://api.core42.ai/v1", env)),
        model=model,
        model_fast=_env("CORE42_MODEL_FAST", "", env) or model,
        websearch_model=_env("CORE42_WEBSEARCH_MODEL", "", env) or model,
        max_output_tokens=_env_int("LLM_MAX_OUTPUT_TOKENS", 32768, env),
        output_token_headroom=_env_float("LLM_OUTPUT_TOKEN_HEADROOM", 1.5, env),
        timeout=_env_float("LLM_TIMEOUT", 240.0, env),
        max_concurrency=_env_int("LLM_MAX_CONCURRENCY", 4, env),
        max_retries=_env_int("LLM_MAX_RETRIES", 2, env),
        retry_delay=_env_float("LLM_RETRY_DELAY", 2.0, env),
        temperature=_env_float("LLM_TEMPERATURE", 0.2, env),
    )


def reload_settings() -> Core42Settings:
    """Drop the cached settings so the next read sees the current environment."""
    get_settings.cache_clear()
    return get_settings()
