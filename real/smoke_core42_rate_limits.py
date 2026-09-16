"""
Smoke test: where should LLM_MAX_CONCURRENCY actually be set?

Ramps concurrency upward, sending requests at each level and reporting
success/429 counts, latency spread and any rate-limit headers. Stops at the
first level that produces a 429, so it locates the ceiling without hammering
through it.

    cd real && python smoke_core42_rate_limits.py                 # cheap probe
    cd real && python smoke_core42_rate_limits.py --realistic     # ~8k-token prompts
    cd real && python smoke_core42_rate_limits.py --levels 1,2,4  # custom ramp
    cd real && python smoke_core42_rate_limits.py --requests 10   # per level

Two honest limits on what the result means:

  * **Small prompts measure REQUESTS per minute.** Real pipeline calls run
    roughly 8-14k tokens and a shared gateway is usually capped on *tokens* per
    minute too, so the binding constraint is more likely TPM than RPM.
    ``--realistic`` pads each prompt to a representative size to probe that
    dimension, at real token cost.
  * **Capacity is shared, so this is a snapshot of one moment.** A ceiling found
    at 02:00 is not the ceiling at 14:00.

Remember the cap is per *process*: several Streamlit workers multiply it.
"""

import argparse
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

load_dotenv()

# Headers an OpenAI-compatible gateway MAY expose. Absent on some deployments,
# which is itself worth reporting: without them, 429s are the only signal.
RATE_LIMIT_HEADERS = (
    "x-ratelimit-limit-requests", "x-ratelimit-remaining-requests",
    "x-ratelimit-limit-tokens", "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens",
    "retry-after", "retry-after-ms",
)


def build_client() -> OpenAI:
    api_key = os.environ.get("CORE42_API_KEY", "")
    base_url = os.environ.get("CORE42_BASE_URL", "https://api.core42.ai/v1").strip().rstrip("/")
    if base_url.endswith("/chat/completions"):
        base_url = base_url[: -len("/chat/completions")].rstrip("/")
    if not api_key:
        print("CORE42_API_KEY is not set. Fill it in real/.env and re-run.")
        raise SystemExit(1)
    return OpenAI(
        base_url=base_url, api_key=api_key, default_headers={"api-key": api_key},
        timeout=float(os.environ.get("LLM_TIMEOUT", "240")), max_retries=0,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--levels", default="1,2,4,8", help="concurrency ramp, comma separated")
    parser.add_argument("--requests", type=int, default=6, help="requests per level")
    parser.add_argument("--realistic", action="store_true",
                        help="pad prompts to ~8k tokens, like a real pipeline call")
    args = parser.parse_args()

    client = build_client()
    model = os.environ.get("CORE42_MODEL", "gpt-5.1")
    levels = [int(x) for x in args.levels.split(",") if x.strip()]

    prompt = "Reply with the single word: ok."
    if args.realistic:
        # ~8k tokens of filler, matching the size of a real Stage 4 prompt.
        prompt = ("Context line for load testing. " * 2000) + "\n\nReply with the single word: ok."
        total = len(levels) * args.requests
        print(f"--realistic sends ~8k-token prompts: up to {total} of them, at real token cost.")
        if input("Continue? [y/N] ").strip().lower() != "y":
            return

    print(f"\nmodel: {model}   levels: {levels}   requests per level: {args.requests}\n")

    def one_request() -> tuple:
        started = time.monotonic()
        try:
            resp = client.chat.completions.with_raw_response.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=2000,
                stream=False,
            )
            return "ok", time.monotonic() - started, dict(resp.headers)
        except RateLimitError as exc:
            headers = dict(getattr(getattr(exc, "response", None), "headers", {}) or {})
            return "429", time.monotonic() - started, headers
        except Exception as exc:
            return f"error: {type(exc).__name__}: {exc}", time.monotonic() - started, {}

    for level in levels:
        print(f"--- concurrency {level} ---")
        with ThreadPoolExecutor(max_workers=level) as pool:
            results = list(pool.map(lambda _: one_request(), range(args.requests)))

        ok = [r for r in results if r[0] == "ok"]
        throttled = [r for r in results if r[0] == "429"]
        errors = [r for r in results if r[0] not in ("ok", "429")]
        latencies = [r[1] for r in ok]

        print(f"  ok: {len(ok)}   429: {len(throttled)}   other errors: {len(errors)}")
        if latencies:
            print(f"  latency  min {min(latencies):.1f}s  median "
                  f"{statistics.median(latencies):.1f}s  max {max(latencies):.1f}s")
        for status, _, _ in errors[:3]:
            print(f"  {status}")

        headers = next((h for _, _, h in results if h), {})
        exposed = {k: v for k, v in headers.items() if k.lower() in RATE_LIMIT_HEADERS}
        if exposed:
            print(f"  rate-limit headers: {exposed}")
        else:
            print("  rate-limit headers: none exposed — 429s are the only signal")

        if throttled:
            print(f"\nCeiling found at concurrency {level}.")
            print(f"Set LLM_MAX_CONCURRENCY below it — and divide by the number of "
                  f"Streamlit workers, since the cap is per process.")
            return
        print()

    print(f"No 429s up to concurrency {max(levels)}. "
          f"LLM_MAX_CONCURRENCY can sit at or below that, per process.")


if __name__ == "__main__":
    main()
