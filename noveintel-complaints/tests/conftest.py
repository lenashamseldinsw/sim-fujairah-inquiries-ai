"""
Shared fixtures.

The service is self-contained: no test reaches outside it. (The Streamlit application
it was ported from has been removed from the ``noveintel`` branch, and with it the
parity tests that compared the vendored stages against it.)
"""
from __future__ import annotations

from typing import Any

import pytest

from noveintel_complaints.api.models import EntityInfo, ComplaintRecord, GenerateComplaintsReportRequest

@pytest.fixture
def entity() -> EntityInfo:
    """A tenant identity with no logo — the minimum a request must carry."""
    return EntityInfo(name_ar="شرطة الفجيرة", name_en="Fujairah Police")


@pytest.fixture
def record_dicts() -> list[dict[str, Any]]:
    """A small, valid payload in the snake_case form."""
    return [
        {
            "case_number": "2001",
            "case_details": "شكوى من تأخر معالجة طلب تجديد الرخصة",
            "resolution": "تمت المعالجة والاعتذار للمتعامل",
            "service": "تجديد رخصة القيادة",
            "date_opened": "2025-01-15",
            "date_closed": "2025-01-28",
            "service_channel": "هاتف",
            "severity": "طلب عادي",
            "general_administration": "الإدارة العامة للمرور",
        },
        {
            "case_number": "2002",
            "case_details": "خطأ تقني في المنصة أدى إلى خصم المبلغ مرتين",
            "resolution": "تم رد المبلغ",
            "service": "سداد مخالفة",
            "date_opened": "2025-02-20",
            "date_closed": "2025-02-25",
            "service_channel": "خدمة ذاتية",
            "severity": "طلب عاجل",
        },
        {
            "case_number": "2003",
            "case_details": "شكوى على عدم الرد على الاستفسارات",
            "resolution": "تم التواصل مع المتعامل",
            "service": "خدمة عامة",
            "date_opened": "2025-03-02",
            "service_channel": "بريد إلكتروني",
        },
    ]


@pytest.fixture
def request_body(record_dicts, entity) -> dict[str, Any]:
    """A ready-to-POST body."""
    return {
        "records": record_dicts,
        "entity": entity.model_dump(exclude_none=True),
        "options": {"include_english": False},
    }


@pytest.fixture
def analysis_request(record_dicts, entity) -> GenerateComplaintsReportRequest:
    """The same payload as a validated request model."""
    return GenerateComplaintsReportRequest(
        records=[ComplaintRecord(**row) for row in record_dicts], entity=entity
    )
