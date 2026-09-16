"""
Core42 integration for the real pipelines.

Core42 is an OpenAI-compatible gateway, driven with the official ``openai`` SDK
over a custom ``base_url``. This package holds everything the pipelines need:

  ``settings``    — environment config, base-URL normalisation, fail-fast checks
  ``client``      — the chat-completions client (lazy singleton, no SDK retries)
  ``messages``    — ``Core42Client``, a Messages-shaped facade the pipeline calls
  ``json_repair`` — the repair cascade for truncated / fenced / fenced-prose JSON
  ``retry``       — error classification and the 10s floor for 429s
  ``concurrency`` — one process-wide in-flight cap for every outbound call
  ``tokens``      — per-stage token and cost tracking

Typical use, unchanged from the call sites' point of view:

    from core42 import Core42Client, CHAT_MODEL, APIError

    client = Core42Client(api_key=api_key)
    message = client.messages.create(
        model=CHAT_MODEL, max_tokens=8000, system=..., messages=[...],
    )
    text = message.content[0].text
"""

from openai import APIError, AuthenticationError, BadRequestError, RateLimitError

from .client import generate_json, get_core42_client, reset_client
from .json_repair import clean_llm_json, close_truncated_json, loads_repaired
from .messages import Core42Client, Core42Message, TextBlock, ToolUseBlock
from .settings import CHAT_MODEL, FAST_MODEL, Core42Settings, get_settings, reload_settings
from .tokens import summary as token_summary
from .tokens import reset as reset_token_tracking

__all__ = [
    "APIError",
    "AuthenticationError",
    "BadRequestError",
    "RateLimitError",
    "CHAT_MODEL",
    "FAST_MODEL",
    "Core42Client",
    "Core42Message",
    "Core42Settings",
    "TextBlock",
    "ToolUseBlock",
    "clean_llm_json",
    "close_truncated_json",
    "generate_json",
    "get_core42_client",
    "get_settings",
    "loads_repaired",
    "reload_settings",
    "reset_client",
    "reset_token_tracking",
    "token_summary",
]
