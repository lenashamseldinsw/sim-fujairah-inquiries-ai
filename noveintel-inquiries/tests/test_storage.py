"""The storage seam: keys, references, and refusing to write outside the container."""
from __future__ import annotations

import os
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



# ── Per-service defaults ──────────────────────────────────────────────────────
#
# The two services can share one storage account. With shared default names they
# would read each other's job records, pick up each other's queued runs, and file
# their reports in one container — so every name is derived from the flow.

import re as _re

FLOW = "inquiries"


class TestPerServiceDefaults:
    def test_container_is_named_for_this_service(self, monkeypatch):
        from noveintel_inquiries.config import StorageSettings

        monkeypatch.delenv("NOVEINQ_STORAGE_CONTAINER", raising=False)
        assert StorageSettings(_env_file=None).container == f"inquiries-reports"

    def test_table_and_queue_are_named_for_this_service(self, monkeypatch):
        from noveintel_inquiries.config import JobSettings

        for name in ("TABLE_NAME", "QUEUE_NAME"):
            monkeypatch.delenv(f"NOVEINQ_JOB_{name}", raising=False)
        settings = JobSettings(_env_file=None)
        assert settings.table_name == f"inquiriesjobs"
        assert settings.queue_name == f"inquiries-runs"

    def test_the_names_are_valid_azure_names(self, monkeypatch):
        """Azure rejects these at deploy time, not at import — so check them here.

        Tables: letters and digits only, starting with a letter, 3-63 characters.
        Queues and containers: lowercase letters, digits and single hyphens, 3-63,
        starting and ending with a letter or digit.
        """
        from noveintel_inquiries.config import JobSettings, StorageSettings

        jobs = JobSettings(_env_file=None)
        storage = StorageSettings(_env_file=None)
        assert _re.fullmatch(r"[A-Za-z][A-Za-z0-9]{2,62}", jobs.table_name)
        hyphenated = r"(?=.{3,63}$)[a-z0-9]+(-[a-z0-9]+)*"
        assert _re.fullmatch(hyphenated, jobs.queue_name)
        assert _re.fullmatch(hyphenated, f"{jobs.queue_name}-poison")
        assert _re.fullmatch(hyphenated, storage.container)


# ── The blob backend ──────────────────────────────────────────────────────────


class TestBlobBackendWithoutAzure:
    """An on-prem install has no Azure SDK. The blob backend must not care."""

    def test_it_imports_and_constructs_with_no_sdk_needed(self):
        from noveintel_inquiries.storage import BlobDocumentStore

        store = BlobDocumentStore("UseDevelopmentStorage=true", "x-reports")
        assert store.container == "x-reports"

    def test_an_empty_connection_string_is_refused(self):
        from noveintel_inquiries.storage import BlobDocumentStore, StorageError

        with pytest.raises(StorageError, match="connection string"):
            BlobDocumentStore("  ", "x-reports")

    def test_the_factory_names_the_on_prem_alternative(self, monkeypatch):
        """Someone who set 'blob' by mistake on-prem should be told what to use."""
        from noveintel_inquiries.config import get_storage_settings
        from noveintel_inquiries.storage import StorageError, create_document_store

        monkeypatch.setenv("NOVEINQ_STORAGE_BACKEND", "blob")
        monkeypatch.setenv("NOVEINQ_STORAGE_CONNECTION_STRING", "")
        get_storage_settings.cache_clear()
        create_document_store.cache_clear()
        try:
            with pytest.raises(StorageError, match="BACKEND=local"):
                create_document_store()
        finally:
            get_storage_settings.cache_clear()
            create_document_store.cache_clear()

    def test_choosing_blob_without_the_sdk_fails_at_startup(self, monkeypatch):
        """Not minutes later, on the first upload of someone's first run.

        The lifespan catches this, logs it, and /ready reports the store as
        unavailable — so the misconfiguration is visible before any work is taken.
        """
        from noveintel_inquiries.config import get_storage_settings
        from noveintel_inquiries.storage import StorageError, create_document_store
        from noveintel_inquiries.storage import factory

        def missing():
            raise StorageError("azure-storage-blob is not installed")

        monkeypatch.setattr(factory, "_blob_sdk", missing)
        monkeypatch.setenv("NOVEINQ_STORAGE_BACKEND", "blob")
        monkeypatch.setenv("NOVEINQ_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
        get_storage_settings.cache_clear()
        create_document_store.cache_clear()
        try:
            with pytest.raises(StorageError, match="not installed"):
                create_document_store()
        finally:
            get_storage_settings.cache_clear()
            create_document_store.cache_clear()

    def test_local_is_still_the_default(self, monkeypatch):
        from noveintel_inquiries.config import StorageSettings

        monkeypatch.delenv("NOVEINQ_STORAGE_BACKEND", raising=False)
        assert StorageSettings(_env_file=None).backend == "local"

    @pytest.mark.parametrize("key", ["../escape.docx", "/abs.docx", "a\\b.docx"])
    async def test_it_refuses_the_same_keys_the_local_store_does(self, key):
        """Interchangeable backends: a key one accepts, the other accepts too."""
        from noveintel_inquiries.storage import BlobDocumentStore, StorageError

        with pytest.raises(StorageError, match="escapes the container"):
            await BlobDocumentStore("UseDevelopmentStorage=true", "c").put(key, b"x", "t")


class TestLocalDelete:
    async def test_delete_removes_the_file(self, tmp_path):
        store = LocalDirectoryStore(tmp_path)
        await store.put("a/b.json", b"{}", "application/json")
        await store.delete("a/b.json")
        with pytest.raises(StorageError):
            await store.get("a/b.json")

    async def test_deleting_something_already_gone_is_fine(self, tmp_path):
        await LocalDirectoryStore(tmp_path).delete("never/there.json")


AZURITE = os.environ.get("AZURITE_CONNECTION_STRING")


@pytest.mark.skipif(
    not AZURITE,
    reason="Set AZURITE_CONNECTION_STRING to run the blob backend against Azurite.",
)
class TestBlobBackendAgainstAzurite:
    """The real SDK against the storage emulator. Opt-in: it needs Azurite running."""

    async def test_put_get_delete_round_trip(self):
        from noveintel_inquiries.storage import BlobDocumentStore

        store = BlobDocumentStore(AZURITE, "test-reports", sas_ttl_sec=600)
        ref = await store.put("tenant/2025-01-01/run1/report_ar.docx", b"bytes",
                              "application/octet-stream")
        assert await store.get(ref.key) == b"bytes"
        assert ref.size_bytes == 5
        assert ref.filename == "report_ar.docx"
        await store.delete(ref.key)
        with pytest.raises(StorageError):
            await store.get(ref.key)

    async def test_the_link_is_signed_and_expires(self):
        """An account-key connection string gets a SAS link with a real expiry."""
        from noveintel_inquiries.storage import BlobDocumentStore

        store = BlobDocumentStore(AZURITE, "test-reports", sas_ttl_sec=600)
        ref = await store.put("tenant/x/run2/cases.xlsx", b"x", "application/octet-stream")
        assert ref.url.startswith("http")
        assert "sig=" in ref.url
        assert ref.expires_at is not None

    async def test_the_signed_link_downloads_without_credentials(self):
        """The point of the SAS: a caller holding only the URL can fetch the file."""
        import urllib.request

        from noveintel_inquiries.storage import BlobDocumentStore

        store = BlobDocumentStore(AZURITE, "test-reports", sas_ttl_sec=600)
        ref = await store.put("tenant/x/run3/report.json", b'{"ok":1}', "application/json")
        with urllib.request.urlopen(ref.url) as response:
            assert response.read() == b'{"ok":1}'
