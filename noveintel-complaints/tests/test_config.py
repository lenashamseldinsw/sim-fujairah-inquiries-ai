"""
Settings an operator declared but left blank.

A copied ``local.settings.json`` template and an empty deployment-slot setting both
look like this. Read as a value, a blank number is unparseable and takes its whole
settings group down: a 503 on every run, and on Azure a host that will not load,
because ``function_app.py`` reads the job settings at import.
"""
from __future__ import annotations

import pytest

from noveintel_complaints.config import (
    ApiSettings,
    JobSettings,
    PricingSettings,
    Settings,
    StorageSettings,
)

BLANKABLE = [
    (Settings, "CORE42_REQUEST_TIMEOUT", "request_timeout"),
    (StorageSettings, "NOVECOMP_STORAGE_SAS_TTL_SEC", "sas_ttl_sec"),
    (JobSettings, "NOVECOMP_JOB_TTL_SEC", "ttl_sec"),
    (JobSettings, "NOVECOMP_JOB_MAX_RUNTIME_SEC", "max_runtime_sec"),
    (JobSettings, "NOVECOMP_JOB_MAX_CONCURRENT", "max_concurrent"),
    (ApiSettings, "NOVECOMP_MAX_RECORDS", "max_records"),
    (JobSettings, "NOVECOMP_JOB_BACKEND", "backend"),
    (JobSettings, "NOVECOMP_JOB_DIR", "dir"),
    (PricingSettings, "CORE42_INPUT_COST_PER_1M", "input_cost_per_1m"),
    (ApiSettings, "NOVECOMP_LOG_LEVEL", "log_level"),
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
    monkeypatch.setenv("NOVECOMP_JOB_MAX_CONCURRENT", "two")
    with pytest.raises(ValueError):
        JobSettings()
