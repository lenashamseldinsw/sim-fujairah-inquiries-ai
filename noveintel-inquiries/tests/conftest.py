"""
Shared fixtures.

The service is self-contained: no test reaches outside this project. Model calls are
answered by ``tests.fakes.FakeGateway``, so the suite needs no network and no key.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import pytest

from noveintel_inquiries.models import EntityInfo, GenerateInquiriesReportRequest

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PROJECT_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

SETTINGS: dict[str, Any] = {
    "timeliness_target_working_days": 2,
    "timeliness_framework": "entity_process_kpi",
    "case_type_scope": "inquiries_and_service_requests",
}


@pytest.fixture
def entity() -> EntityInfo:
    """A tenant identity with no logo — the minimum a request must carry."""
    return EntityInfo(name_ar="صندوق أبوظبي للتقاعد", name_en="Abu Dhabi Pension Fund")


@pytest.fixture
def record_dicts() -> list[dict[str, Any]]:
    """A small payload keyed by the universal column names."""
    return [
        {
            "case_id": "260630-7987523",
            "opened_datetime": "2026-06-30T23:37:48",
            "case_type": "Information - معلومات",
            "channel": "Phone",
            "description": "كيف يمكنني ضم مدة خدمة سابقة؟",
            "resolution_text": "من خلال هذه الخدمة يمكن للمؤمن عليه تقديم طلب ضم مدة خدمته السابقة https://www.tamm.abudhabi/x",
            "sla_status": "🟢 Green",
            "status": "Closed",
            "crm_service": "Add Previous Service Period-ضم مدة خدمة سابقة",
        },
        {
            "case_id": "260630-7987318",
            "opened_datetime": "2026-05-12T10:00:00",
            "case_type": "Request for Service - طلب الخدمة",
            "channel": "Live Chat",
            "description": "أود الحصول على شهادة مكافأة نهاية الخدمة مع اسم البنك",
            "resolution_text": "تم إصدار الشهادة المطلوبة وإرسالها",
            "sla_status": "🟡 Amber",
            "status": "Closed",
            "crm_service": "Gratuity Calculation - آلية إحتساب مكافأة نهاية الخدمة",
        },
        {
            "case_id": "260410-1000001",
            "opened_datetime": "2026-04-10T09:00:00",
            "case_type": "Information - معلومات",
            "channel": "Self Service",
            "description": "متى موعد صرف المعاش التقاعدي لهذا الشهر",
            "resolution_text": "نفيدكم بأن موعد صرف المعاش التقاعدي في الأسبوع الأخير من الشهر",
            "sla_status": "🔴 Red",
            "status": "Closed",
            "crm_service": "Pension Disbursement - صرف المعاشات التقاعدية",
        },
    ]


@pytest.fixture
def request_body(record_dicts, entity) -> dict[str, Any]:
    """A ready-to-POST body."""
    return {
        "records": record_dicts,
        "settings": dict(SETTINGS),
        "reference_lists": {"taxonomy": "adpf_codebook_v1"},
        "entity": entity.model_dump(exclude_none=True),
        "options": {"include_english": False},
    }


@pytest.fixture
def analysis_request(request_body) -> GenerateInquiriesReportRequest:
    return GenerateInquiriesReportRequest.model_validate(request_body)


@pytest.fixture
def gateway(monkeypatch):
    """Every Core42 call answered locally."""
    from .fakes import install

    return install(monkeypatch)


@pytest.fixture(scope="session")
def adpf_labelled() -> list[dict[str, Any]]:
    """The ADPF Q2 2026 labelled master, mapped to the universal columns.

    The labels, timestamps, channels, SLA colours and service tags of all 10,630 cases;
    no free text and no owner, which the engine tests do not read.
    """
    path = FIXTURES / "adpf_q2_2026_labels.json.gz"
    if not path.is_file():
        pytest.skip("The ADPF labelled master fixture is not in this checkout.")
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)
