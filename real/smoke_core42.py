"""
Smoke test: Core42 chat completions.

Deliberately standalone — it reads .env directly and talks to the gateway with a
bare openai client, so it proves the credentials, the base URL, the api-key
header and the model name *independently of any application code*. When
something breaks, this says in five seconds whether the problem is ours or the
gateway's. That is worth the duplication.

    cd real && python smoke_core42.py
"""

import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

# Search results and Arabic replies routinely contain non-ASCII punctuation. The
# Windows console defaults to cp1252 and raises UnicodeEncodeError on those,
# which looks exactly like a failed API call.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

load_dotenv()

API_KEY = os.environ.get("CORE42_API_KEY", "")
BASE_URL = os.environ.get("CORE42_BASE_URL", "https://api.core42.ai/v1")
# Strip the chat path if the deployment handed one out: the SDK appends it, and
# the leftover suffix is what breaks every non-chat endpoint.
BASE_URL = BASE_URL.strip().rstrip("/")
if BASE_URL.endswith("/chat/completions"):
    BASE_URL = BASE_URL[: -len("/chat/completions")].rstrip("/")
MODEL = os.environ.get("CORE42_MODEL", "gpt-5.1")
MODEL_FAST = os.environ.get("CORE42_MODEL_FAST", MODEL)

if not API_KEY:
    print("CORE42_API_KEY is not set. Fill it in real/.env and re-run.")
    raise SystemExit(1)

print(f"base_url : {BASE_URL}")
print(f"model    : {MODEL}")
print(f"fast     : {MODEL_FAST}")
print()

client = OpenAI(
    base_url=BASE_URL,
    api_key=API_KEY,
    # The gateway wants this header on the chat-completions path, in addition to
    # the Authorization: Bearer header the SDK sends. Its absence is a 401 here
    # and nowhere else.
    default_headers={"api-key": API_KEY},
    timeout=float(os.environ.get("LLM_TIMEOUT", "240")),
    max_retries=0,
)

for label, model in (("chat", MODEL), ("fast", MODEL_FAST)):
    if label == "fast" and MODEL_FAST == MODEL:
        continue
    print(f"--- {label} tier: {model} ---")
    response = client.chat.completions.create(
        model=model,
        messages=[{
            "role": "user",
            "content": "Reply with one short sentence in Arabic confirming you are working.",
        }],
        # max_completion_tokens, NOT max_tokens: the latter is deprecated on the
        # compatible surface. "unsupported parameter" errors point here.
        max_completion_tokens=2000,
        stream=False,
    )
    choice = response.choices[0] if response.choices else None
    message = getattr(choice, "message", None)
    print((getattr(message, "content", None) or "(empty)").strip())
    usage = getattr(response, "usage", None)
    print(f"  input tokens  : {getattr(usage, 'prompt_tokens', 0) or 0}")
    print(f"  output tokens : {getattr(usage, 'completion_tokens', 0) or 0}")
    print(f"  finish reason : {getattr(choice, 'finish_reason', None)}")
    print()

print("--- JSON mode ---")
response = client.chat.completions.create(
    model=MODEL,
    messages=[{
        "role": "user",
        "content": 'Return the JSON object {"status": "ok", "arabic": "<the word for success in Arabic>"}.',
    }],
    response_format={"type": "json_object"},
    max_completion_tokens=2000,
    stream=False,
)
print((response.choices[0].message.content or "(empty)").strip())
print()
print("Chat completions reachable.")
