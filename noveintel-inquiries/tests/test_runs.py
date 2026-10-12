"""
One run among several: what keeps a run's accounting and failures its own.

A worker executes runs concurrently. These pin the seams that make that safe: a token
ledger per run that reaches into every thread pool the run starts, a gateway failure
reported as such rather than as a generic failure, exception text kept out of a
caller-readable job record, and stdout that can carry Arabic on Windows.
"""
from __future__ import annotations

import ast
import asyncio
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from noveintel_inquiries import pipeline
from noveintel_inquiries.core42 import tokens
from noveintel_inquiries.exceptions import StageFailure, UpstreamFailure


class TestLedgerPerRun:
    def test_overlapping_runs_count_only_their_own_calls(self, analysis_request, gateway):
        alone = asyncio.run(pipeline.generate_report(analysis_request)).usage.calls
        bigger = analysis_request.model_copy(deep=True)
        bigger.settings.root_cause_extraction = True

        alone_bigger = asyncio.run(pipeline.generate_report(bigger)).usage.calls

        async def both():
            return await asyncio.gather(pipeline.generate_report(analysis_request), pipeline.generate_report(bigger))

        first, second = asyncio.run(both())
        assert (first.usage.calls, second.usage.calls) == (alone, alone_bigger)
        assert alone != alone_bigger

    def test_outside_a_run_the_process_ledger_is_used(self):
        tokens.reset()
        tokens.track("gpt-test", 1, 1, "x")
        assert tokens.summary()["calls"] == 1
        tokens.reset()

    def test_no_module_starts_threads_that_drop_the_run(self):
        """Every pool the package starts must be ``ScopedThreadPoolExecutor``.

        A plain ``ThreadPoolExecutor`` runs its tasks without the submitter's context,
        so the calls made on it would be counted against no run at all.
        """
        import noveintel_inquiries

        root = Path(noveintel_inquiries.__file__).parent
        offenders = []
        for path in root.rglob("*.py"):
            if path.name == "tokens.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                    if name == "ThreadPoolExecutor":
                        offenders.append(f"{path.relative_to(root)}:{node.lineno}")
        assert offenders == []

    def test_the_ledger_names_the_model(self):
        with tokens.run_scope():
            for model in ("gpt-a", "gpt-b", "gpt-a"):
                tokens.track(model, 1, 1, "s")
            assert tokens.summary()["model"] == "gpt-a, gpt-b"

    def test_no_calls_means_no_model(self):
        with tokens.run_scope():
            usage, _ = pipeline._summarise_usage(tokens.summary())
        assert usage.model is None


def _response(model: str = "gpt-reported"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None), finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=4),
        model=model,
    )


class TestCore42Adapter:
    @pytest.fixture
    def messages(self, monkeypatch):
        from noveintel_inquiries.core42 import messages as module

        monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(resolve_model=lambda m: m))
        monkeypatch.setattr(module, "call_with_retry", lambda fn, label: fn())
        return module

    def test_the_reported_model_is_recorded_and_the_stage_named(self, messages, monkeypatch):
        monkeypatch.setattr(messages, "create_chat_completion", lambda **_: _response())
        client = messages._Messages(SimpleNamespace(model="gpt-requested"))
        with tokens.run_scope():
            client.create(messages=[{"role": "user", "content": "hi"}], stage="classification")
            ledger = tokens.summary()
        assert ledger["model"] == "gpt-reported"
        assert list(ledger["by_stage"]) == ["classification"]

    def test_a_gateway_failure_is_counted_on_the_run(self, messages, monkeypatch):
        import httpx
        from openai import APIConnectionError

        def down(**_):
            raise APIConnectionError(request=httpx.Request("POST", "https://gateway"))

        monkeypatch.setattr(messages, "create_chat_completion", down)
        client = messages._Messages(SimpleNamespace(model="gpt"))
        with tokens.run_scope():
            with pytest.raises(APIConnectionError):
                client.create(messages=[{"role": "user", "content": "hi"}])
            assert tokens.summary()["gateway_failures"] == 1


class TestFailures:
    def test_a_gateway_outage_is_an_upstream_failure(self, analysis_request, monkeypatch):
        from .fakes import FakeGateway, install

        class Down(FakeGateway):
            def create(self, **kwargs):
                tokens.track_failure()
                raise ConnectionError("the gateway echoed رقم الهوية 784-1990-1234567-1")

        install(monkeypatch, Down())
        with pytest.raises(UpstreamFailure) as caught:
            asyncio.run(pipeline.generate_report(analysis_request))
        assert caught.value.code == "upstream_error"
        assert caught.value.stage == "classification"
        assert "784" not in str(caught.value)

    def test_exception_text_does_not_reach_the_caller(self, analysis_request, monkeypatch):
        from .fakes import FakeGateway, install

        install(monkeypatch, FakeGateway())
        from noveintel_inquiries.report import assemble

        def boom(**_):
            raise RuntimeError("'محمد أحمد' leaked")

        monkeypatch.setattr(assemble, "assemble_report", boom)
        monkeypatch.setattr("noveintel_inquiries.report.assemble.assemble_report", boom)
        with pytest.raises(StageFailure) as caught:
            asyncio.run(pipeline.generate_report(analysis_request, run_id="run1"))
        assert caught.value.code == "stage_failed" and caught.value.stage == "documents"
        assert "محمد" not in str(caught.value) and "run1" in str(caught.value)

    def test_an_arabic_narrative_failure_fails_the_run(self, analysis_request, monkeypatch):
        from .fakes import FakeGateway, install

        install(monkeypatch, FakeGateway(fail_tools={"write_report_narratives"}))
        with pytest.raises(StageFailure) as caught:
            asyncio.run(pipeline.generate_report(analysis_request))
        assert caught.value.stage == "narratives"


class TestArabicOutput:
    """Windows encodes a redirected stdout in the ANSI code page, cp1252."""

    def test_a_cp1252_stream_cannot_take_arabic(self):
        stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        with pytest.raises(UnicodeEncodeError):
            print("رقم الطلب", file=stream)

    def test_validation_runs_on_a_cp1252_stdout(self, monkeypatch, analysis_request):
        raw = io.BytesIO()
        monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252"))
        result = pipeline.validate_records(analysis_request)
        print("رقم الطلب")
        sys.stdout.flush()
        assert result["total_cases"] == len(analysis_request.records)
        assert "رقم الطلب".encode() in raw.getvalue()

    def test_a_stream_that_cannot_be_reconfigured_is_left_alone(self, monkeypatch):
        monkeypatch.setattr(sys, "stdout", SimpleNamespace(encoding="cp1252"))
        pipeline._tolerate_arabic_output()


class TestRuntimeCeiling:
    def test_an_abandoned_run_stops_at_the_next_progress_report(self, analysis_request, gateway):
        from noveintel_inquiries.jobs.runner import RunAbandoned

        def progress(fraction, message_ar, message_en):
            if message_en.startswith("Stage 2"):
                raise RunAbandoned("ceiling")

        with pytest.raises(RunAbandoned):
            asyncio.run(pipeline.generate_report(analysis_request, progress=progress))
        assert "write_report_narratives" not in gateway.calls
