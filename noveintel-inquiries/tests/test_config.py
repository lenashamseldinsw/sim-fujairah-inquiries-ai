"""
Settings an operator declared but left blank.

A copied ``local.settings.json`` template and an empty deployment-slot setting both
look like this. Read as a value, a blank number is unparseable and takes its whole
settings group down: a 503 on every run, and on Azure a host that will not load,
because ``function_app.py`` reads the job settings at import.
"""
from __future__ import annotations

import pytest

from noveintel_inquiries.config import (
    ApiSettings,
    JobSettings,
    PricingSettings,
    Settings,
    StorageSettings,
)

BLANKABLE = [
    (Settings, "CORE42_REQUEST_TIMEOUT", "request_timeout"),
    (StorageSettings, "NOVEINQ_STORAGE_SAS_TTL_SEC", "sas_ttl_sec"),
    (JobSettings, "NOVEINQ_JOB_TTL_SEC", "ttl_sec"),
    (JobSettings, "NOVEINQ_JOB_MAX_RUNTIME_SEC", "max_runtime_sec"),
    (JobSettings, "NOVEINQ_JOB_MAX_CONCURRENT", "max_concurrent"),
    (ApiSettings, "NOVEINQ_MAX_RECORDS", "max_records"),
    (JobSettings, "NOVEINQ_JOB_BACKEND", "backend"),
    (JobSettings, "NOVEINQ_JOB_DIR", "dir"),
    (PricingSettings, "CORE42_INPUT_COST_PER_1M", "input_cost_per_1m"),
    (ApiSettings, "NOVEINQ_LOG_LEVEL", "log_level"),
]


@pytest.mark.parametrize(("group", "variable", "field"), BLANKABLE)
@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_variable_means_unset(group, variable, field, blank, monkeypatch):
    monkeypatch.setenv("CORE42_API_KEY", "test-key")
    monkeypatch.delenv(variable, raising=False)
    unset = getattr(group(), field)

    monkeypatch.setenv(variable, blank)
    assert getattr(group(), field) == unset


def test_a_bad_value_is_still_refused(monkeypatch):
    """Blank is "not this one"; a typo is still a typo."""
    monkeypatch.setenv("NOVEINQ_JOB_MAX_CONCURRENT", "two")
    with pytest.raises(ValueError):
        JobSettings()


class TestDeepReviewReasoning:
    """gpt-5.1 does no reasoning unless asked, so the deep review must ask."""

    def test_defaults_to_the_main_model_at_low_effort(self, monkeypatch):
        from noveintel_inquiries.core42 import DEEP_MODEL, reload_settings

        monkeypatch.setenv("CORE42_MODEL", "gpt-5.1")
        monkeypatch.delenv("CORE42_MODEL_DEEP", raising=False)
        monkeypatch.delenv("LLM_DEEP_REASONING_EFFORT", raising=False)
        try:
            s = reload_settings()
            assert s.resolve_model(DEEP_MODEL) == "gpt-5.1" and s.deep_reasoning_effort == "low"
            monkeypatch.setenv("CORE42_MODEL_DEEP", "o4-mini")
            monkeypatch.setenv("LLM_DEEP_REASONING_EFFORT", "none")
            s = reload_settings()
            assert s.resolve_model(DEEP_MODEL) == "o4-mini" and s.deep_reasoning_effort == ""
            monkeypatch.setenv("LLM_DEEP_REASONING_EFFORT", "extreme")
            with pytest.raises(ValueError, match="LLM_DEEP_REASONING_EFFORT"):
                reload_settings()
        finally:
            monkeypatch.delenv("CORE42_MODEL_DEEP", raising=False)
            monkeypatch.delenv("LLM_DEEP_REASONING_EFFORT", raising=False)
            reload_settings()

    def test_a_model_rejecting_the_effort_is_asked_again_without_it(self, monkeypatch):
        import httpx
        from openai import BadRequestError

        from noveintel_inquiries.core42 import messages as m

        sent = []

        class _Resp:
            choices = [type("C", (), {"message": type("M", (), {"content": "ok", "tool_calls": None})(),
                                      "finish_reason": "stop"})()]
            usage = type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})()
            model = "x"

        def fake_create(**kwargs):
            sent.append(kwargs.get("reasoning_effort"))
            if kwargs.get("reasoning_effort"):
                raise BadRequestError("Unsupported parameter: 'reasoning_effort'",
                                      response=httpx.Response(400, request=httpx.Request("POST", "http://x")), body=None)
            return _Resp()

        monkeypatch.setenv("CORE42_API_KEY", "test-key")
        monkeypatch.setattr(m, "create_chat_completion", fake_create)
        monkeypatch.setattr(m, "_effort_unsupported", set())
        client = m.Core42Client(api_key="k", model="gpt-4.1")
        for _ in range(2):
            client.messages.create(model="gpt-4.1", max_tokens=10, messages=[{"role": "user", "content": "hi"}],
                                   reasoning_effort="medium")
        assert sent == ["medium", None, None]  # rejected once, then never sent to that model again
