#!/usr/bin/env python
"""
End-to-end against a running service and the live Core42 gateway.

**This spends money and takes minutes.** It starts a real run: every case classified,
the patterns and gaps analysed, nine report sections written. Point it at a small
fixture first.

    uv run python scripts/smoke.py fixtures/happy.json
    uv run python scripts/smoke.py fixtures/happy.json --url http://localhost:8000
    uv run python scripts/smoke.py fixtures/happy.json --key "$NOVE_KEY" --english

It validates, submits, polls until the job is terminal, then prints what came back:
the period, the case counts, which artefacts were stored, what the run cost, and any
warnings. On failure it prints the stage and the error.

Personal data is never printed. The complaints contract carries names and identity
numbers, and a smoke run's output ends up pasted into tickets and chat.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

POLL_INTERVAL_SEC = 10.0
TERMINAL = {"succeeded", "failed", "cancelled"}


def headers(key: str | None) -> dict[str, str]:
    return {"X-API-Key": key} if key else {}


def check_ready(client: httpx.Client) -> None:
    """Refuse to start a paid run against a service that is not configured."""
    response = client.get("/ready")
    if response.status_code != 200:
        raise SystemExit(
            f"/ready answered {response.status_code}: {response.text}\n"
            "Fix the configuration before spending a run."
        )
    body = response.json()
    print(f"  model            {body['model']}")
    print(f"  storage          {'available' if body['storage']['available'] else 'MISSING'}")
    print(f"  pricing          {'configured' if body['pricing_configured'] else 'not configured'}")
    if not body["storage"]["available"]:
        print("  warning: no document store — the run will produce no retrievable files.")


def validate(client: httpx.Client, body: dict[str, Any], key: str | None) -> None:
    """The cheap check, always run first. No model call, no cost."""
    response = client.post(
        f"/v1/inquiries/validate", json=body, headers=headers(key)
    )
    if response.status_code != 200:
        raise SystemExit(f"Validation rejected the payload:\n{_pretty(response)}")
    result = response.json()
    period = result.get("period")
    print(f"  records          {result['total_cases']}")
    print(f"  columns          {len(result['columns'])}")
    print(f"  period           {period['label_en'] if period else result['period_error']}")


def submit(client: httpx.Client, body: dict[str, Any], key: str | None) -> str:
    response = client.post(f"/v1/inquiries", json=body, headers=headers(key))
    if response.status_code != 202:
        raise SystemExit(f"The run was not accepted:\n{_pretty(response)}")
    accepted = response.json()
    estimate = accepted.get("estimated_seconds")
    print(f"  job              {accepted['job_id']}")
    print(f"  estimate         ~{estimate}s" if estimate else "  estimate         unknown")
    return accepted["job_id"]


def wait(client: httpx.Client, job_id: str, key: str | None, timeout: float) -> dict:
    started = time.monotonic()
    last = None
    while True:
        elapsed = time.monotonic() - started
        if elapsed > timeout:
            raise SystemExit(
                f"Gave up after {elapsed:.0f}s. The run may still be going — poll "
                f"/v1/jobs/{job_id} yourself."
            )
        response = client.get(f"/v1/jobs/{job_id}", headers=headers(key))
        if response.status_code != 200:
            raise SystemExit(f"Polling failed:\n{_pretty(response)}")
        state = response.json()
        marker = (state.get("stage"), state.get("message"))
        if marker != last:
            print(
                f"  [{elapsed:>6.0f}s] {state['status']:<10} "
                f"{state.get('progress', 0) * 100:>3.0f}%  {state.get('message') or ''}"
            )
            last = marker
        if state["status"] in TERMINAL:
            return state
        time.sleep(POLL_INTERVAL_SEC)


def report(state: dict) -> int:
    if state["status"] != "succeeded":
        error = state.get("error") or {}
        print(f"\nFAILED — {error.get('code')} at {error.get('stage') or 'no stage'}")
        print(f"  {error.get('message')}")
        return 1

    bundle = state["result"]
    usage = bundle["usage"]
    documents = bundle["documents"]

    print(f"\nSUCCEEDED — run {bundle['run_id']}")
    print(f"  period           {bundle['period']['label_en']}")
    print(f"  cases            {bundle['total_cases']}")
    print(f"  charts           {[c['key'] for c in bundle['charts']]}")
    print(f"  report data      {sorted(bundle['report'])}")

    print("  artefacts")
    for language, ref in sorted(documents.get("report", {}).items()):
        print(f"    report {language}       {ref['size_bytes'] / 1024:>8.1f} KiB  {ref['url']}")
    if documents.get("workbook"):
        ref = documents["workbook"]
        print(f"    workbook        {ref['size_bytes'] / 1024:>8.1f} KiB  {ref['url']}")
    for language, ref in sorted(documents.get("report_data", {}).items()):
        print(f"    data {language}         {ref['size_bytes'] / 1024:>8.1f} KiB  {ref['url']}")

    cost = "unpriced" if usage["cost"] is None else f"${usage['cost']:.4f}"
    print(f"  usage            {usage['tokens']} tokens, {usage['calls']} calls, {cost}")
    for stage, figures in sorted(usage.get("by_stage", {}).items()):
        stage_cost = "" if figures["cost"] is None else f"  ${figures['cost']:.4f}"
        print(
            f"    {stage:<14} {figures['calls']:>3} call(s)  "
            f"{figures['input_tokens'] + figures['output_tokens']:>8} tokens{stage_cost}"
        )

    for warning in bundle.get("warnings", []):
        print(f"  warning          {warning['code']}: {warning['message']}")

    return 0


def _pretty(response: httpx.Response) -> str:
    try:
        return json.dumps(response.json(), ensure_ascii=False, indent=2)
    except ValueError:
        return f"{response.status_code} {response.text[:500]}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("body", type=Path, help="A request body, from make_fixtures.py.")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--key", default=None, help="X-API-Key, if the service needs one.")
    parser.add_argument(
        "--english", action="store_true",
        help="Produce the English report too. Roughly doubles cost and wall clock.",
    )
    parser.add_argument("--timeout", type=float, default=3600.0)
    args = parser.parse_args()

    if not args.body.is_file():
        raise SystemExit(f"No such file: {args.body}")
    body = json.loads(args.body.read_text(encoding="utf-8"))
    body.setdefault("options", {})["include_english"] = args.english

    with httpx.Client(base_url=args.url.rstrip("/"), timeout=60.0) as client:
        print(f"Service {args.url}")
        check_ready(client)
        print("\nValidating (free)")
        validate(client, body, args.key)
        print("\nSubmitting — this spends money")
        job_id = submit(client, body, args.key)
        print("\nPolling")
        state = wait(client, job_id, args.key, args.timeout)
        return report(state)


if __name__ == "__main__":
    sys.exit(main())
