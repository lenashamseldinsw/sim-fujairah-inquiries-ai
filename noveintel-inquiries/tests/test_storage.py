"""The storage seam: keys, references, and refusing to write outside the container."""
from __future__ import annotations

from datetime import date

import pytest

from noveintel_inquiries.api.models import PeriodGranularity
from noveintel_inquiries.api.models.period import Period
from noveintel_inquiries.storage import LocalDirectoryStore, StorageError, build_key, slugify


@pytest.fixture
def period() -> Period:
    return Period(
        granularity=PeriodGranularity.QUARTERLY,
        index=1, year=2025, start=date(2025, 1, 1), end=date(2025, 3, 31),
        label_ar="الربع الأول 2025", label_en="Q1 2025",
    )


class TestKeys:
    def test_layout_is_widest_first(self, entity, period):
        key = build_key(entity, period, "abc123", "report_ar.docx")
        assert key == "fujairah-police/2025-01-01/abc123/report_ar.docx"

    def test_the_period_start_not_today(self, entity, period):
        """Re-running last quarter's analysis tomorrow still files under last quarter."""
        assert period.start.isoformat() in build_key(entity, period, "x", "a.docx")

    def test_two_runs_do_not_collide(self, entity, period):
        first = build_key(entity, period, "aaa", "report_ar.docx")
        second = build_key(entity, period, "bbb", "report_ar.docx")
        assert first != second

    def test_slugify_never_returns_empty(self):
        """An Arabic-only name collapses to nothing, which would make an unusable key."""
        assert slugify("شرطة الفجيرة") == "entity"


class TestLocalStore:
    async def test_put_then_get_round_trips(self, tmp_path):
        store = LocalDirectoryStore(tmp_path)
        ref = await store.put("a/b/report.docx", b"bytes", "application/octet-stream")
        assert ref.size_bytes == 5
        assert ref.filename == "report.docx"
        assert await store.get("a/b/report.docx") == b"bytes"

    async def test_url_is_a_file_uri_by_default(self, tmp_path):
        """Honest about being on the service's disk, and usable by anything co-located."""
        store = LocalDirectoryStore(tmp_path)
        ref = await store.put("a/report.docx", b"x", "application/octet-stream")
        assert ref.url.startswith("file://")
        assert ref.expires_at is None

    async def test_public_base_url_makes_it_fetchable(self, tmp_path):
        store = LocalDirectoryStore(tmp_path, public_base_url="http://host:10000/")
        ref = await store.put("a/report.docx", b"x", "application/octet-stream")
        assert ref.url == "http://host:10000/reports/a/report.docx"

    @pytest.mark.parametrize(
        "key", ["../escape.docx", "/absolute.docx", "a/../../escape.docx", "c:/win.docx"]
    )
    async def test_a_traversing_key_is_refused(self, tmp_path, key):
        """Not reachable today — keys are built from a slug, a date and a hex id — but
        the guard must not depend on someone remembering that."""
        with pytest.raises(StorageError, match="escapes the container"):
            await LocalDirectoryStore(tmp_path).put(key, b"x", "text/plain")

    async def test_a_missing_object_raises_storage_error(self, tmp_path):
        with pytest.raises(StorageError):
            await LocalDirectoryStore(tmp_path).get("nothing/here.docx")

    async def test_a_relative_root_still_produces_a_url(self, tmp_path, monkeypatch):
        """The default root is relative, and a relative path has no file: URI."""
        monkeypatch.chdir(tmp_path)
        ref = await LocalDirectoryStore("storage").put(
            "a.docx", b"x", "application/octet-stream"
        )
        assert ref.url.startswith("file://")
