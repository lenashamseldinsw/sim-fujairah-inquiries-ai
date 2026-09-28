"""
Shared fixtures.

**This is the only file allowed to reach outside the service.** The porting guide's
rule: the new service must not import from the Streamlit application, and only the
parity tests may break that — from here, where it is visible. ``legacy_root`` is what
does it, and every other module in this package imports noveintel_inquiries and nothing else.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from noveintel_inquiries.api.models import EntityInfo, InquiryRecord, GenerateInquiriesReportRequest

# The repository the service was ported out of. Two levels up from tests/.
REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_FLOW = REPO_ROOT / "real" / "inquiries-flow"


@pytest.fixture(scope="session")
def legacy_root() -> Path:
    """Put the legacy application on the path, for parity tests only.

    Skips rather than fails when the checkout is not there: a deployed service has no
    ``real/`` directory, and a parity test that cannot find its reference has nothing
    to say — it is not a failure of the code under test.
    """
    if not LEGACY_FLOW.is_dir():
        pytest.skip(f"The legacy flow is not in this checkout ({LEGACY_FLOW}).")
    for path in (str(REPO_ROOT), str(LEGACY_FLOW)):
        if path not in sys.path:
            sys.path.insert(0, path)
    return LEGACY_FLOW


@pytest.fixture
def entity() -> EntityInfo:
    """A tenant identity with no logo — the minimum a request must carry."""
    return EntityInfo(name_ar="شرطة الفجيرة", name_en="Fujairah Police")


@pytest.fixture
def record_dicts() -> list[dict[str, Any]]:
    """A small, valid payload in the snake_case form."""
    return [
        {
            "case_number": "1001",
            "case_details": "استفسار عن تجديد رخصة القيادة",
            "contact_type": "استفسار",
            "resolution": "تم توجيه المتعامل إلى الخدمة الذاتية",
            "date_opened": "2025-01-15",
            "date_closed": "2025-01-16",
            "service_channel": "هاتف",
            "main_service": "تجديد رخصة القيادة",
            "general_administration": "الإدارة العامة للمرور",
        },
        {
            "case_number": "1002",
            "case_details": "شكوى من تأخر معالجة الطلب",
            "contact_type": "شكوى",
            "resolution": "تمت المعالجة والاعتذار للمتعامل",
            "date_opened": "2025-02-20",
            "date_closed": "2025-02-28",
            "service_channel": "بريد إلكتروني",
            "main_service": "سداد مخالفة",
        },
        {
            "case_number": "1003",
            "case_details": "طلب إصدار شهادة حسن سيرة وسلوك",
            "contact_type": "طلب",
            "resolution": "تم إصدار الشهادة",
            "date_opened": "2025-03-02",
            "service_channel": "خدمة ذاتية",
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
def analysis_request(record_dicts, entity) -> GenerateInquiriesReportRequest:
    """The same payload as a validated request model."""
    return GenerateInquiriesReportRequest(
        records=[InquiryRecord(**row) for row in record_dicts], entity=entity
    )
