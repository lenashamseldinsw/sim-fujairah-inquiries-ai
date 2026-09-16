"""
Core42 chat-completions client.

Core42 is an OpenAI-compatible gateway: it is driven with the official ``openai``
SDK by overriding ``base_url``. The deviations that cost a day each if found the
hard way, and how they are handled here:

  * the chat-completions path wants an ``api-key`` header **in addition to** the
    SDK's ``Authorization: Bearer`` — both are set;
  * ``max_tokens`` is deprecated on the compatible surface —
    ``max_completion_tokens`` is sent instead;
  * gpt-5.1-class reasoning models reject a non-default ``temperature`` — it is
    accepted at the call site and never sent;
  * 429s reflect shared-capacity pressure rather than per-second rate limiting,
    so their back-off floor is 10s (see ``retry.py``).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from openai import OpenAI

from .concurrency import llm_slot
from .settings import get_settings

logger = logging.getLogger(__name__)

# Module-level singleton, constructed lazily on first use — never at import time.
# Import-time construction would make this module unimportable without
# credentials, which breaks every test and any code that merely mentions it.
_client: Optional[OpenAI] = None


def get_core42_client() -> OpenAI:
    """Return (or lazily create) the shared Core42 chat-completions client.

    ``max_retries=0`` keeps our own retry layer as the single retry owner; nested
    retry loops multiply into ~9 API calls per logical failure.
    """
    global _client
    if _client is None:
        s = get_settings()
        s.require_configured()
        _client = OpenAI(
            base_url=s.base_url,
            api_key=s.api_key,
            default_headers={"api-key": s.api_key},  # gateway-specific, chat path only
            timeout=s.timeout,
            max_retries=0,                           # single retry owner
        )
    return _client


def reset_client() -> None:
    """Drop the cached client so the next call rebuilds it from current settings."""
    global _client
    _client = None


def effective_output_tokens(requested: Optional[int]) -> int:
    """Turn a call site's visible-token budget into an output ceiling to send.

    Reasoning models spend part of the output budget on reasoning tokens that
    never appear in ``content``, so a call site asking for 8000 visible tokens
    truncates mid-JSON without headroom. The headroom multiplier and the hard
    ceiling are both configurable.
    """
    s = get_settings()
    if not requested or requested <= 0:
        return s.max_output_tokens
    return min(int(requested * max(s.output_token_headroom, 1.0)), s.max_output_tokens)


def create_chat_completion(
    *,
    model: str,
    messages: List[Dict[str, Any]],
    max_output_tokens: Optional[int] = None,
    response_format: Optional[Dict[str, Any]] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Any] = None,
) -> Any:
    """Make one chat-completions request. No retries, no parsing — just the call.

    Everything that can differ between call sites is a keyword, and the global
    in-flight cap wraps the network call only, so a caller that backs off after a
    failure releases its slot while it waits.
    """
    client = get_core42_client()
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        # max_completion_tokens, NOT max_tokens: the latter is deprecated in the
        # OpenAI-compatible surface and is rejected or ignored by newer gateway
        # models. "unsupported parameter" errors point here.
        "max_completion_tokens": effective_output_tokens(max_output_tokens),
        "stream": False,  # some gateways default to streaming
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    if tools:
        kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice

    with llm_slot("chat.completions"):
        return client.chat.completions.create(**kwargs)


def generate_json(
    *,
    model: str,
    system_instruction: Optional[str],
    user_contents: str,
    temperature: float = 0.2,          # accepted and NOT sent
    max_output_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """Generate strict JSON using ``response_format={"type": "json_object"}``.

    Returns:
      { "text": str, "raw": ChatCompletion, "input_tokens": int,
        "output_tokens": int, "finish_reason": str | None }
    """
    messages: List[Dict[str, str]] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": user_contents})

    resp = create_chat_completion(
        model=model,
        messages=messages,
        max_output_tokens=max_output_tokens,
        response_format={"type": "json_object"},
    )
    return unpack_response(resp, max_output_tokens)


def unpack_response(resp: Any, max_output_tokens: Optional[int] = None) -> Dict[str, Any]:
    """Pull text, usage and finish reason off a completion, defensively.

    Each guard here has fired in production: ``choices`` can be empty,
    ``message.content`` can be None on a content-filtered or tool-only reply, and
    ``usage`` can be absent *or* present with None fields — hence both a getattr
    default and ``or 0``.
    """
    choice = resp.choices[0] if getattr(resp, "choices", None) else None
    message = getattr(choice, "message", None) if choice else None
    text = (getattr(message, "content", None) or "") if message else ""
    finish_reason = getattr(choice, "finish_reason", None) if choice else None

    if finish_reason == "length":
        logger.warning(
            "Core42 response truncated by the output token limit (finish_reason=length, "
            "max_completion_tokens=%s). The JSON repair layer will attempt to close open "
            "structures; some values may be incomplete.",
            effective_output_tokens(max_output_tokens),
        )

    usage = getattr(resp, "usage", None)
    return {
        "text": text,
        "raw": resp,
        "message": message,
        "input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
        "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
        "finish_reason": finish_reason,
    }
