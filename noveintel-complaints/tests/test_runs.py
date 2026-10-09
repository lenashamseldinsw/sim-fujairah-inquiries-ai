"""
One run among several: what keeps a run's accounting and failures its own.

A worker executes runs concurrently, and the vendored Core42 layer was written for a
process that ran one pipeline at a time. These pin the seams that make it safe to
share: a token ledger per run that reaches into the stages' thread pools, a gateway
failure reported as such rather than as a generic stage failure, exception text kept
out of a caller-readable job record, and stdout that can carry Arabic on Windows.
"""
from __future__ import annotations

import inspect
import io
import sys
import threading
from types import SimpleNamespace

import pytest

from noveintel_complaints import pipeline
from noveintel_complaints.core42 import tokens
from noveintel_complaints.exceptions import StageFailure, UpstreamFailure


@pytest.fixture
def core42_env(monkeypatch):
    """The stages read a gateway key at construction; any value will do here."""
    from noveintel_complaints.core42 import reload_settings

    monkeypatch.setenv("CORE42_API_KEY", "test-key")
    reload_settings()
    yield
    monkeypatch.undo()
    reload_settings()


def _stub_pipeline(monkeypatch, body):
    """Replace the six stages with ``body(orchestrator)``, which returns their result."""
    from noveintel_complaints.stages.orchestrator import PipelineOrchestrator

    def run_full_pipeline(self, **_):
        return body(self)

    monkeypatch.setattr(PipelineOrchestrator, "run_full_pipeline", run_full_pipeline)


def _fan_out(calls: int) -> None:
    """Make ``calls`` model calls from a stage's own thread pool, as the English
    translation does."""
    from noveintel_complaints.stages import translate_report_en

    with translate_report_en.ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(
            lambda _: tokens.track("gpt-test", 10, 5, "translate_report_en"), range(calls)
        ))


class TestLedgerPerRun:
    def test_overlapping_runs_count_only_their_own_calls(
        self, monkeypatch, core42_env, analysis_request, tmp_path
    ):
        """Each run resets the ledger as it starts. With one ledger per process, the
        second run's reset wiped the first's calls and both read the sum."""
        both_started = threading.Barrier(2, timeout=5)
        both_counted = threading.Barrier(2, timeout=5)
        calls_by_run = {"a": 5, "b": 2}

        def body(orchestrator):
            both_started.wait()  # both runs have reset their ledgers
            _fan_out(calls_by_run[threading.current_thread().name])
            both_counted.wait()  # both runs have counted before either reads
            return {"success": True, "stages": {}}

        _stub_pipeline(monkeypatch, body)
        ledgers = {}

        def run(name):
            _, _, ledgers[name] = pipeline._run_stages(
                analysis_request, name, tmp_path / name, {}, None
            )

        threads = [threading.Thread(target=run, args=(n,), name=n) for n in calls_by_run]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert ledgers["a"]["calls"] == 5
        assert ledgers["b"]["calls"] == 2

    def test_outside_a_run_the_process_ledger_is_used(self):
        """The Streamlit app and the smoke scripts never open a scope."""
        tokens.reset()
        tokens.track("gpt-test", 1, 1, "smoke")
        assert tokens.summary()["calls"] == 1
        with tokens.run_scope():
            assert tokens.summary()["calls"] == 0
        tokens.reset()

    def test_every_stage_thread_pool_carries_the_run(self):
        """A stage that fans out on an executor this does not cover would have its
        calls counted against no run — silently under-reporting the spend."""
        from noveintel_complaints import stages
        from noveintel_complaints.core42.tokens import ScopedThreadPoolExecutor

        pipeline._scope_stage_executors()
        import importlib
        import pkgutil

        for info in pkgutil.iter_modules(stages.__path__):
            module = importlib.import_module(f"{stages.__name__}.{info.name}")
            source = inspect.getsource(module)
            assert "threading.Thread(" not in source, info.name
            assert "futures.ThreadPoolExecutor(" not in source, info.name
            if "ThreadPoolExecutor" in source:
                assert module.ThreadPoolExecutor is ScopedThreadPoolExecutor, info.name


class TestModelReported:
    def test_the_ledger_names_the_model(self):
        with tokens.run_scope():
            tokens.track("gpt-a", 1, 1, "s")
            tokens.track("gpt-b", 1, 1, "s")
            tokens.track("gpt-a", 1, 1, "s")
            assert tokens.summary()["model"] == "gpt-a, gpt-b"

    def test_the_bundle_carries_it(self):
        with tokens.run_scope():
            tokens.track("gpt-a", 1, 1, "s")
            usage, _ = pipeline._summarise_usage(tokens.summary())
        assert usage.model == "gpt-a"

    def test_no_calls_means_no_model(self):
        with tokens.run_scope():
            usage, _ = pipeline._summarise_usage(tokens.summary())
        assert usage.model is None


def _response(model: str = "gpt-reported"):
    """The fields of an OpenAI completion the adapter reads."""
    return SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content="ok", tool_calls=None), finish_reason="stop"
        )],
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=4),
        model=model,
    )


class TestCore42Adapter:
    @pytest.fixture
    def messages(self, monkeypatch):
        from noveintel_complaints.core42 import messages as module

        monkeypatch.setattr(
            module, "get_settings", lambda: SimpleNamespace(resolve_model=lambda m: m)
        )
        monkeypatch.setattr(module, "call_with_retry", lambda fn, label: fn())
        return module

    def test_the_reported_model_is_recorded_and_the_caller_named(self, messages, monkeypatch):
        """The stage label is read off the caller's frame, so wrapping ``create``
        must not shift it onto the adapter's own method."""
        monkeypatch.setattr(messages, "create_chat_completion", lambda **_: _response())
        client = messages._Messages(SimpleNamespace(model="gpt-requested"))
        with tokens.run_scope():
            client.create(messages=[{"role": "user", "content": "hi"}])
            ledger = tokens.summary()
        assert ledger["model"] == "gpt-reported"
        assert list(ledger["by_stage"]) == [__name__.rsplit(".", 1)[-1]]

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


class TestStageFailures:
    def test_a_gateway_outage_is_an_upstream_failure(
        self, monkeypatch, core42_env, analysis_request, tmp_path
    ):
        def body(orchestrator):
            tokens.track_failure()
            return {"success": False, "stages": {"stage3": {
                "success": False,
                "message": "API error: the gateway echoed رقم الهوية 784-1990-1234567-1",
            }}}

        _stub_pipeline(monkeypatch, body)
        with pytest.raises(UpstreamFailure) as caught:
            pipeline._run_stages(analysis_request, "run1", tmp_path, {}, None)
        assert caught.value.code == "upstream_error"
        assert caught.value.stage == "stage3"
        assert "784" not in str(caught.value)

    def test_the_orchestrators_api_error_label_is_enough(
        self, monkeypatch, core42_env, analysis_request, tmp_path
    ):
        """A gateway error that reached the orchestrator without passing through the
        Core42 adapter is not on the ledger, but the orchestrator still labels it."""
        def body(orchestrator):
            return {"success": False, "stages": {"stage3": {
                "success": False, "message": "API error: Connection error.",
            }}}

        _stub_pipeline(monkeypatch, body)
        with pytest.raises(UpstreamFailure) as caught:
            pipeline._run_stages(analysis_request, "run1", tmp_path, {}, None)
        assert caught.value.stage == "stage3"

    def test_wrapped_exception_text_does_not_reach_the_caller(
        self, monkeypatch, core42_env, analysis_request, tmp_path
    ):
        def body(orchestrator):
            return {"success": False, "stages": {"stage4": {
                "success": False, "message": "Stage 4 error: 'محمد أحمد'",
            }}}

        _stub_pipeline(monkeypatch, body)
        with pytest.raises(StageFailure) as caught:
            pipeline._run_stages(analysis_request, "run1", tmp_path, {}, None)
        assert caught.value.code == "stage_failed"
        assert "محمد" not in str(caught.value)
        assert "run1" in str(caught.value)

    def test_an_authored_stage_message_is_kept(
        self, monkeypatch, core42_env, analysis_request, tmp_path
    ):
        def body(orchestrator):
            return {"success": False, "stages": {"stage5": {
                "success": False, "message": "Could not find guidebook JSON",
            }}}

        _stub_pipeline(monkeypatch, body)
        with pytest.raises(StageFailure, match="Could not find guidebook JSON"):
            pipeline._run_stages(analysis_request, "run1", tmp_path, {}, None)


class TestArabicOutput:
    """Windows encodes a redirected stdout in the ANSI code page, cp1252 on an English
    install, and the stages print Arabic."""

    @staticmethod
    def _cp1252(monkeypatch) -> io.BytesIO:
        raw = io.BytesIO()
        monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252"))
        return raw

    def test_a_cp1252_stream_cannot_take_arabic(self):
        """The failure being guarded against, so the test below means something."""
        stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        with pytest.raises(UnicodeEncodeError):
            print("رقم الطلب", file=stream)

    def test_stage_1_runs_on_a_cp1252_stdout(self, monkeypatch, analysis_request):
        raw = self._cp1252(monkeypatch)
        result = pipeline.validate_records(analysis_request)
        sys.stdout.flush()
        assert result["total_cases"] == len(analysis_request.records)
        assert "[Stage1]".encode() in raw.getvalue()

    def test_a_stream_that_cannot_be_reconfigured_is_left_alone(self, monkeypatch):
        monkeypatch.setattr(sys, "stdout", SimpleNamespace(encoding="cp1252"))
        pipeline._tolerate_arabic_output()
