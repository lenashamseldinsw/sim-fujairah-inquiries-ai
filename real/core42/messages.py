"""
``Core42Client`` — a Messages-shaped facade over Core42 chat completions.

The pipeline was written against ``anthropic.Anthropic``: it calls
``client.messages.create(model=..., max_tokens=..., system=..., tools=[...],
tool_choice={"type": "any"}, messages=[...])`` and then reads ``message.content``
as a list of blocks with ``.type`` / ``.text`` / ``.input``, plus
``message.stop_reason``.

Rather than rewrite thirty-four call sites and their response handling, this
module keeps that surface and maps it onto the OpenAI-compatible gateway:

    messages/system    -> OpenAI chat messages
    tools              -> OpenAI function tools
    tool_choice        -> "required" / "auto" / a named function
    max_tokens         -> max_completion_tokens (plus reasoning headroom)
    temperature        -> accepted, never sent (reasoning models reject it)
    tool_calls         -> synthetic ``tool_use`` blocks
    finish_reason      -> stop_reason

**Tool-call degradation.** If the deployment's model rejects function tools, the
call is retried once in JSON mode with the tool's schema inlined in the prompt,
and the parsed object is handed back as a ``tool_use`` block — so a gateway
without tool support costs quality, never a crash. The verdict is cached for the
process so the rejection is paid once, not on every call.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from openai import BadRequestError

from . import tokens as token_tracker
from .client import create_chat_completion, unpack_response
from .json_repair import loads_repaired
from .retry import call_with_retry
from .settings import get_settings

logger = logging.getLogger(__name__)

# "auto" (default) tries native tools and degrades on rejection; "native" never
# degrades; "json" goes straight to the JSON-mode emulation.
_TOOL_MODE = (os.environ.get("CORE42_TOOL_MODE") or "auto").strip().lower()
_tools_unsupported = _TOOL_MODE == "json"

_STOP_REASONS = {
    "stop": "end_turn",
    "length": "max_tokens",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "content_filter": "stop_sequence",
}


# ── Response blocks (the shape the pipeline already reads) ───────────────────

@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ToolUseBlock:
    name: str
    input: Dict[str, Any]
    id: str = "tool_use_0"
    type: str = "tool_use"


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class Core42Message:
    content: List[Any] = field(default_factory=list)
    stop_reason: Optional[str] = None
    model: str = ""
    usage: Usage = field(default_factory=Usage)
    id: str = "msg_core42"
    role: str = "assistant"
    type: str = "message"


# ── Request translation ──────────────────────────────────────────────────────

def _flatten_content(content: Any) -> str:
    """Anthropic message content is a string or a list of blocks; we need a string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_result":
                    parts.append(_flatten_content(block.get("content", "")))
                else:
                    parts.append(json.dumps(block, ensure_ascii=False))
            else:
                parts.append(str(block))
        return "\n".join(p for p in parts if p)
    return "" if content is None else str(content)


def _to_openai_messages(system: Optional[str], messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    if system:
        out.append({"role": "system", "content": _flatten_content(system)})
    for msg in messages or []:
        out.append({
            "role": msg.get("role", "user"),
            "content": _flatten_content(msg.get("content", "")),
        })
    return out


def _to_openai_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Anthropic tools use ``input_schema``; OpenAI nests ``parameters`` under ``function``."""
    converted = []
    for tool in tools or []:
        converted.append({
            "type": "function",
            "function": {
                "name": tool.get("name", "tool"),
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
            },
        })
    return converted


def _to_openai_tool_choice(tool_choice: Any, tools: List[Dict[str, Any]]) -> Any:
    """``{"type": "any"}`` means "you must call a tool" — OpenAI spells that "required"."""
    if not tool_choice:
        return None
    if isinstance(tool_choice, str):
        return tool_choice
    kind = tool_choice.get("type")
    if kind in ("any", "required"):
        return "required"
    if kind == "auto":
        return "auto"
    if kind == "tool" and tool_choice.get("name"):
        return {"type": "function", "function": {"name": tool_choice["name"]}}
    return "required" if tools else None


# ── Response translation ─────────────────────────────────────────────────────

def _tool_use_blocks(message: Any) -> List[ToolUseBlock]:
    """Turn ``tool_calls`` into ``tool_use`` blocks, repairing the argument JSON.

    Arguments arrive as a JSON *string*, and a gateway model truncates or fences
    it the same way it does any other JSON — so the repair layer runs here too
    rather than a bare ``json.loads``.
    """
    blocks: List[ToolUseBlock] = []
    for index, call in enumerate(getattr(message, "tool_calls", None) or []):
        function = getattr(call, "function", None)
        name = getattr(function, "name", None) or "tool"
        raw_args = getattr(function, "arguments", None) or ""
        parsed = loads_repaired(raw_args)
        if parsed is None:
            logger.error(
                "Core42 tool call %r returned unparseable arguments (%d chars); "
                "the block is dropped so the caller's fallback path runs.",
                name, len(raw_args),
            )
            continue
        blocks.append(
            ToolUseBlock(name=name, input=parsed, id=getattr(call, "id", f"tool_use_{index}"))
        )
    return blocks


def _build_message(unpacked: Dict[str, Any], model: str) -> Core42Message:
    message = unpacked.get("message")
    blocks: List[Any] = []

    tool_blocks = _tool_use_blocks(message) if message is not None else []
    text = unpacked.get("text") or ""
    if text:
        blocks.append(TextBlock(text=text))
    blocks.extend(tool_blocks)

    finish_reason = unpacked.get("finish_reason")
    stop_reason = _STOP_REASONS.get(finish_reason or "", "end_turn")
    if tool_blocks and stop_reason == "end_turn":
        stop_reason = "tool_use"

    return Core42Message(
        content=blocks,
        stop_reason=stop_reason,
        model=model,
        usage=Usage(
            input_tokens=unpacked.get("input_tokens", 0),
            output_tokens=unpacked.get("output_tokens", 0),
        ),
    )


# ── JSON-mode emulation of a forced tool call ────────────────────────────────

_JSON_TOOL_INSTRUCTION = (
    "\n\nOUTPUT FORMAT\n"
    "Reply with a single JSON object and nothing else — no prose, no markdown "
    "fence, no explanation. The object must conform exactly to this JSON schema:\n"
    "{schema}\n"
    "Every property named in the schema's \"required\" list must be present. Use "
    "null for a value you genuinely cannot determine, never an empty string."
)


def _emulate_tool_call(
    *,
    model: str,
    system: Optional[str],
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    max_tokens: Optional[int],
    stage: str,
) -> Core42Message:
    """Force a tool-shaped answer out of a model that will not take tools.

    Every tool call site in this pipeline passes exactly one tool with
    ``tool_choice={"type": "any"}``, so the emulation only has to handle the
    single-forced-tool case: inline that tool's schema, ask for JSON mode, and
    hand the parsed object back as a ``tool_use`` block.
    """
    tool = tools[0]
    schema = json.dumps(tool.get("input_schema") or {}, ensure_ascii=False)
    instruction = _JSON_TOOL_INSTRUCTION.format(schema=schema)
    openai_messages = _to_openai_messages((system or "") + instruction, messages)

    resp = call_with_retry(
        lambda: create_chat_completion(
            model=model,
            messages=openai_messages,
            max_output_tokens=max_tokens,
            response_format={"type": "json_object"},
        ),
        label=f"core42:{stage}:json-tool",
    )
    unpacked = unpack_response(resp, max_tokens)
    token_tracker.track(model, unpacked["input_tokens"], unpacked["output_tokens"], stage)

    parsed = loads_repaired(unpacked.get("text") or "")
    message = _build_message(unpacked, model)
    if parsed is None:
        logger.error(
            "[%s] JSON-mode tool emulation returned no parseable object; the caller's "
            "no-tool fallback will run.", stage,
        )
        return message
    message.content = [ToolUseBlock(name=tool.get("name", "tool"), input=parsed)]
    message.stop_reason = "tool_use" if unpacked.get("finish_reason") != "length" else "max_tokens"
    return message


def _looks_like_tool_rejection(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(
        token in text
        for token in ("tool", "function call", "function_call", "functions")
    )


# ── The client ───────────────────────────────────────────────────────────────

class _Messages:
    def __init__(self, client: "Core42Client") -> None:
        self._client = client

    def create(
        self,
        *,
        model: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        max_tokens: Optional[int] = None,
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        temperature: Optional[float] = None,  # accepted, never sent
        stage: Optional[str] = None,
        **ignored: Any,
    ) -> Core42Message:
        """Create one message. Signature-compatible with ``messages.create``."""
        global _tools_unsupported

        if ignored:
            logger.debug("Core42 adapter ignoring unsupported parameter(s): %s",
                         ", ".join(sorted(ignored)))

        settings = get_settings()
        resolved_model = settings.resolve_model(model or self._client.model)
        label = stage or _caller_label()

        if tools and (_tools_unsupported or _TOOL_MODE == "json"):
            return _emulate_tool_call(
                model=resolved_model, system=system, messages=messages or [],
                tools=tools, max_tokens=max_tokens, stage=label,
            )

        openai_messages = _to_openai_messages(system, messages or [])
        openai_tools = _to_openai_tools(tools) if tools else None
        choice = _to_openai_tool_choice(tool_choice, tools or []) if tools else None

        def _call():
            return create_chat_completion(
                model=resolved_model,
                messages=openai_messages,
                max_output_tokens=max_tokens,
                tools=openai_tools,
                tool_choice=choice,
            )

        try:
            resp = call_with_retry(_call, label=f"core42:{label}")
        except BadRequestError as exc:
            # A schema or tool-support rejection must not take the stage down: fall
            # back to JSON mode. ERROR, because a persistent fallback means every
            # tool call is now paying for the flakier path and someone should look.
            if not tools or _TOOL_MODE == "native" or not _looks_like_tool_rejection(exc):
                raise
            logger.error(
                "[%s] Core42 rejected native tool calling (%s); falling back to JSON mode "
                "for the rest of this process: %s", label, type(exc).__name__, exc,
            )
            _tools_unsupported = True
            return _emulate_tool_call(
                model=resolved_model, system=system, messages=messages or [],
                tools=tools, max_tokens=max_tokens, stage=label,
            )

        unpacked = unpack_response(resp, max_tokens)
        token_tracker.track(resolved_model, unpacked["input_tokens"], unpacked["output_tokens"], label)
        message = _build_message(unpacked, resolved_model)

        # A forced tool call that came back as prose means the gateway accepted the
        # request and ignored the tool. Emulation is the only way to get structure.
        if tools and tool_choice and not any(getattr(b, "type", "") == "tool_use" for b in message.content):
            logger.warning(
                "[%s] Forced tool call returned no tool_use block; retrying in JSON mode.", label,
            )
            return _emulate_tool_call(
                model=resolved_model, system=system, messages=messages or [],
                tools=tools, max_tokens=max_tokens, stage=label,
            )
        return message


def _caller_label() -> str:
    """Name the calling module, so token spend is attributed per pipeline stage."""
    try:
        return sys._getframe(2).f_globals.get("__name__", "unknown").split(".")[-1]
    except Exception:
        return "unknown"


class Core42Client:
    """Drop-in replacement for ``anthropic.Anthropic`` over the Core42 gateway.

    ``api_key`` is accepted for call-site compatibility. Passing one overrides
    the environment for this process; the usual path is to leave it None and let
    ``CORE42_API_KEY`` (env or Streamlit secrets) configure the shared client.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        if api_key:
            os.environ["CORE42_API_KEY"] = api_key
            from .settings import reload_settings
            from .client import reset_client

            reload_settings()
            reset_client()
        settings = get_settings()
        settings.require_configured()
        self.api_key = settings.api_key
        self.model = model or settings.model
        self.messages = _Messages(self)
