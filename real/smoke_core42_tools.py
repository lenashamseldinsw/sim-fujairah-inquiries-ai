"""
Smoke test: does this Core42 deployment support function calling?

Stages 3, 4 and 5 force a tool call and read the arguments back as structured
data — it is how the pipeline avoids parsing prose. If the deployment's model
rejects tools, the adapter degrades to a JSON-mode emulation, which works but is
flakier and costs a schema restatement in every prompt. This script tells you
which path the pipeline will actually take, before a run does.

    cd real && python smoke_core42_tools.py

Section 1 forces a tool call. Section 2 runs the same request the JSON-mode way,
so a deployment that fails section 1 still shows whether the fallback is sound.
"""

import json
import os
import sys

from dotenv import load_dotenv
from openai import BadRequestError, OpenAI

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

load_dotenv()

API_KEY = os.environ.get("CORE42_API_KEY", "")
BASE_URL = os.environ.get("CORE42_BASE_URL", "https://api.core42.ai/v1").strip().rstrip("/")
if BASE_URL.endswith("/chat/completions"):
    BASE_URL = BASE_URL[: -len("/chat/completions")].rstrip("/")
MODEL = os.environ.get("CORE42_MODEL_FAST") or os.environ.get("CORE42_MODEL", "gpt-5.1")

if not API_KEY:
    print("CORE42_API_KEY is not set. Fill it in real/.env and re-run.")
    raise SystemExit(1)

client = OpenAI(
    base_url=BASE_URL, api_key=API_KEY, default_headers={"api-key": API_KEY},
    timeout=float(os.environ.get("LLM_TIMEOUT", "240")), max_retries=0,
)

# The real Stage 3 tool, cut down to two cases: same shape, same Arabic enums,
# small enough to read in a terminal.
SCHEMA = {
    "type": "object",
    "properties": {
        "classifications": {
            "type": "array",
            "description": "One entry per case, in the same order as the input",
            "items": {
                "type": "object",
                "properties": {
                    "case_number": {"type": "string"},
                    "top_level": {
                        "type": "string",
                        "enum": ["شكوى", "استفسار", "طلب", "شكر وثناء"],
                    },
                    "confidence": {"type": "number"},
                },
                "required": ["case_number", "top_level", "confidence"],
            },
        }
    },
    "required": ["classifications"],
}

CASES = (
    "Case Number: C-1\nDescription: لم أستلم الخدمة رغم مرور أسبوعين\n\n"
    "Case Number: C-2\nDescription: ما هي الأوراق المطلوبة لتجديد الرخصة؟"
)
SYSTEM = "You classify government customer service cases into the Arabic taxonomy."

print(f"base_url : {BASE_URL}")
print(f"model    : {MODEL}\n")

# ── 1. Native function calling ───────────────────────────────────────────────
print("--- 1. native tool calling (tool_choice=required) ---")
try:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": f"Classify these cases.\n\n{CASES}"}],
        tools=[{"type": "function", "function": {
            "name": "classify_cases_batch",
            "description": "Classify a batch of cases using the two-level taxonomy.",
            "parameters": SCHEMA,
        }}],
        tool_choice="required",
        max_completion_tokens=4000,
        stream=False,
    )
except BadRequestError as exc:
    print(f"REJECTED: {exc}")
    print("-> The adapter will run every tool call through the JSON-mode emulation.")
    print("   Set CORE42_TOOL_MODE=json in .env to skip the one-time rejection.\n")
else:
    calls = getattr(response.choices[0].message, "tool_calls", None) or []
    if not calls:
        print("ACCEPTED the request but returned NO tool call — the tool was ignored.")
        print(f"   Content instead: {(response.choices[0].message.content or '')[:300]}")
        print("-> The adapter will retry such calls in JSON mode.\n")
    else:
        args = calls[0].function.arguments
        print(f"OK — {len(calls)} tool call(s), {len(args)} chars of arguments")
        try:
            parsed = json.loads(args)
        except json.JSONDecodeError as exc:
            print(f"   arguments did not parse ({exc}); the repair layer would run here")
        else:
            print(f"   {json.dumps(parsed, ensure_ascii=False)[:400]}")
        print(f"   finish_reason: {response.choices[0].finish_reason}\n")

# ── 2. The JSON-mode fallback ────────────────────────────────────────────────
print("--- 2. JSON-mode emulation (the fallback path) ---")
response = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "system", "content": SYSTEM + (
            "\n\nOUTPUT FORMAT\nReply with a single JSON object and nothing else, "
            "conforming exactly to this JSON schema:\n"
            + json.dumps(SCHEMA, ensure_ascii=False)
        )},
        {"role": "user", "content": f"Classify these cases.\n\n{CASES}"},
    ],
    response_format={"type": "json_object"},
    max_completion_tokens=4000,
    stream=False,
)
text = (response.choices[0].message.content or "").strip()
print(f"{len(text)} chars, finish_reason={response.choices[0].finish_reason}")
try:
    print(json.dumps(json.loads(text), ensure_ascii=False)[:400])
except json.JSONDecodeError as exc:
    print(f"did not parse raw ({exc}) — the repair layer would run here")
    print(text[:400])
