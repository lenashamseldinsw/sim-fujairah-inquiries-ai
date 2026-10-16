"""
The HTTP contract, driven through ``TestClient`` with the job runner stubbed.

Everything but the run is real: the app, the error envelope, the models, the
job store writing to a temporary directory. What is replaced is the *run* — a genuine
one is minutes of model calls, and none of the promises tested here depend on what the
model says.

The failure modes are pinned deliberately (porting guide §7): a 422 for a bad body, a
422 naming every missing required input, a 401 when a key is configured, a 404
for an unknown job, and a failed job reported inside a 200 rather than as an HTTP
error.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from noveintel_inquiries.api.app import create_app
from noveintel_inquiries.api.deps import (
    get_api_settings,
    get_document_store,
    get_job_runner,
)
from noveintel_inquiries.models import JobError, JobStatus
from noveintel_inquiries.config import ApiSettings
from noveintel_inquiries.jobs import LocalJobStore
from noveintel_inquiries.storage import LocalDirectoryStore


class StubRunner:
    """Drives a job to a terminal state without running the pipeline.

    Duck-typed, like module 01's ``StubClient``: it has ``submit`` and nothing else,
    and does not subclass ``JobRunner``. Subclassing would inherit the semaphore and
    the thread hand-off, which is the machinery these tests are trying not to depend
    on.
    """

    def __init__(self, store, outcome: JobStatus = JobStatus.SUCCEEDED, error=None):
        self.store = store
        self.outcome = outcome
        self.error = error
        self.submitted: list[str] = []

    def submit(self, job_id, run):
        self.submitted.append(job_id)

        async def finish():
            state = await self.store.get(job_id)
            state.status = self.outcome
            state.finished_at = datetime.now(timezone.utc)
            state.error = self.error
            state.progress = 1.0 if self.outcome is JobStatus.SUCCEEDED else state.progress
            await self.store.update(state)

        asyncio.get_running_loop().create_task(finish())


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A fresh app per test, with its stores pointed at a temporary directory."""
    monkeypatch.setenv("CORE42_API_KEY", "test-key")
    app = create_app()
    store = LocalDirectoryStore(tmp_path / "storage")
    app.dependency_overrides[get_document_store] = lambda: store

    with TestClient(app) as test_client:
        # Replace the real job store with one under tmp_path, then the runner with a
        # stub that drives jobs it records into that same store.
        jobs = LocalJobStore(tmp_path / "jobs")
        app.state.job_store = jobs
        runner = StubRunner(jobs)
        app.dependency_overrides[get_job_runner] = lambda: runner
        test_client.runner = runner
        test_client.jobs = jobs
        yield test_client


def poll(client, job_id, attempts: int = 50):
    """Poll until the job is terminal, or give up and return the last state."""
    for _ in range(attempts):
        body = client.get(f"/v1/jobs/{job_id}").json()
        if body["status"] in ("succeeded", "failed", "cancelled"):
            return body
    return body


class TestOperations:
    def test_health_needs_nothing(self, client):
        assert client.get("/health").json() == {"status": "ok"}

    def test_health_answers_without_a_gateway_key(self, tmp_path, monkeypatch):
        """A liveness probe must not fail because something else is down."""
        monkeypatch.delenv("CORE42_API_KEY", raising=False)
        with TestClient(create_app()) as bare:
            assert bare.get("/health").status_code == 200

    def test_ready_reports_the_collaborators(self, client):
        body = client.get("/ready").json()
        assert body["status"] == "ready"
        assert body["storage"]["available"] is True
        assert body["jobs"]["available"] is True
        # No rates configured in the test environment, and that is reported honestly
        # rather than as a zero cost.
        assert body["pricing_configured"] is False


class TestValidateRoute:
    def test_a_good_payload_is_accepted(self, client, request_body):
        body = client.post("/v1/inquiries/validate", json=request_body).json()
        assert body["total_cases"] == len(request_body["records"])
        assert body["period"]["label_en"]

    def test_it_costs_no_model_call(self, client, request_body):
        """The whole point of the route: it answers before a job is ever started."""
        client.post("/v1/inquiries/validate", json=request_body)
        assert client.runner.submitted == []

    def test_it_returns_the_parse_log(self, client, request_body):
        body = client.post("/v1/inquiries/validate", json=request_body).json()
        assert body["parse_log"]["in_scope_total"] == len(request_body["records"])
        assert "case_id" in body["parse_log"]["columns_mapped"]

    def test_unreadable_dates_are_refused_up_front(self, client, request_body):
        for record in request_body["records"]:
            record["opened_datetime"] = "not a date"
        response = client.post("/v1/inquiries/validate", json=request_body)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "unprocessable_records"


class TestCreateRoute:
    def test_accepts_and_returns_a_job(self, client, request_body):
        response = client.post("/v1/inquiries", json=request_body)
        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "queued"
        assert body["poll_url"] == f"/v1/jobs/{body['job_id']}"
        assert body["estimated_seconds"] > 0

    def test_the_run_id_is_the_job_id(self, client, request_body):
        """One id ties the response, the log trail and the stored artefacts together."""
        job_id = client.post("/v1/inquiries", json=request_body).json()["job_id"]
        assert client.runner.submitted == [job_id]

    def test_two_identical_requests_get_different_ids(self, client, request_body):
        first = client.post("/v1/inquiries", json=request_body).json()["job_id"]
        second = client.post("/v1/inquiries", json=request_body).json()["job_id"]
        assert first != second

    def test_a_missing_required_column_is_named(self, client, request_body):
        for record in request_body["records"]:
            record.pop("resolution_text")
        response = client.post("/v1/inquiries", json=request_body)
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "missing_required_columns"
        assert error["message"].startswith("The following input field(s) were missing or unmapped:")
        assert [f["field"] for f in error["detail"]["fields"]] == ["resolution_text"]
        assert error["detail"]["fields"][0]["id"] == "U3"
        assert client.runner.submitted == []

    def test_missing_settings_and_taxonomy_are_named_together(self, client, request_body):
        request_body.pop("settings")
        request_body.pop("reference_lists")
        error = client.post("/v1/inquiries", json=request_body).json()["error"]
        assert error["code"] == "missing_required_columns"
        assert [f["id"] for f in error["detail"]["fields"]] == ["X2", "X3", "X4", "OCL"]

    def test_validate_names_missing_inputs_the_same_way(self, client, request_body):
        for record in request_body["records"]:
            record.pop("opened_datetime")
        error = client.post("/v1/inquiries/validate", json=request_body).json()["error"]
        assert error["code"] == "missing_required_columns" and "opened_datetime" in error["message"]

    def test_a_job_is_not_created_for_an_unreadable_period(self, client, request_body):
        for record in request_body["records"]:
            record["opened_datetime"] = "n/a date"
        response = client.post("/v1/inquiries", json=request_body)
        assert response.status_code == 400 and client.runner.submitted == []

    def test_a_validation_error_never_echoes_the_record(self, client, request_body):
        """A record is customer data. The offending row must not come back.

        The value is a distinctive string rather than a common word, so the check
        cannot pass or fail on wording that happens to appear in the error message.
        """
        secret = "784-1990-1234567-1"
        request_body["records"][0]["case_id"] = {"id": secret}
        response = client.post("/v1/inquiries", json=request_body)
        assert response.status_code == 422
        assert secret not in response.text
        # The field is still named, so the caller can find what to fix.
        assert "case_id" in response.text

    def test_a_coercion_failure_is_422_not_500(self, client, request_body):
        """A custom validator's error carries a non-serialisable exception in `ctx`;
        left in the response it renders as a 500 instead of the 422 it is."""
        request_body["records"][0]["description"] = ["a", "list"]
        response = client.post("/v1/inquiries", json=request_body)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_request"

    def test_a_malformed_body_is_422_not_500(self, client):
        assert client.post("/v1/inquiries", json={"records": "nonsense"}).status_code == 422

    def test_too_many_records_is_refused_up_front(self, client, request_body, monkeypatch):
        """Refused rather than accepted into a job that would run for hours."""
        app = client.app
        app.dependency_overrides[get_api_settings] = lambda: ApiSettings(max_records=1)
        request_body["records"] = request_body["records"] * 2
        response = client.post("/v1/inquiries", json=request_body)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "too_many_records"
        assert client.runner.submitted == []


class TestAuth:
    def test_unset_key_means_unenforced(self, client, request_body):
        assert client.post("/v1/inquiries", json=request_body).status_code == 202

    def test_a_configured_key_is_required(self, client, request_body):
        client.app.dependency_overrides[get_api_settings] = lambda: ApiSettings(
            api_key="secret"
        )
        assert client.post("/v1/inquiries", json=request_body).status_code == 401
        ok = client.post(
            "/v1/inquiries", json=request_body, headers={"X-API-Key": "secret"}
        )
        assert ok.status_code == 202

    def test_a_wrong_key_is_401(self, client, request_body):
        client.app.dependency_overrides[get_api_settings] = lambda: ApiSettings(
            api_key="secret"
        )
        response = client.post(
            "/v1/inquiries", json=request_body, headers={"X-API-Key": "wrong"}
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"

    def test_health_is_never_gated(self, client):
        client.app.dependency_overrides[get_api_settings] = lambda: ApiSettings(
            api_key="secret"
        )
        assert client.get("/health").status_code == 200


class TestPolling:
    def test_a_finished_job_reports_succeeded(self, client, request_body):
        job_id = client.post("/v1/inquiries", json=request_body).json()["job_id"]
        assert poll(client, job_id)["status"] == "succeeded"

    def test_an_unknown_job_is_404(self, client):
        response = client.get("/v1/jobs/nosuchjob")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "job_not_found"

    def test_a_failed_run_is_a_200_describing_a_failure(
        self, client, request_body, tmp_path
    ):
        """A poll that finds a failed job is a successful poll. The failure belongs
        to the run, not to the request asking about it."""
        client.runner.outcome = JobStatus.FAILED
        client.runner.error = JobError(
            code="stage_failed", message="narratives failed.", stage="narratives"
        )
        job_id = client.post("/v1/inquiries", json=request_body).json()["job_id"]
        body = poll(client, job_id)
        assert body["status"] == "failed"
        assert body["error"]["code"] == "stage_failed"
        assert body["error"]["stage"] == "narratives"
        assert body["result"] is None


class TestPackageBoundaries:
    def test_no_module_level_import_of_a_hosting_or_ui_package(self):
        """Rule 1: importing the package must not require a hosting or UI SDK.

        Checked by parsing, not by searching the text. A substring scan flags its own
        documentation — this very file discusses ``azure`` — and prose is not an
        import. The AST says what the module actually does.

        Module level specifically. ``jobs/table_storage.py`` imports the Azure tables
        SDK *inside* a method on purpose: that is what lets the module be imported,
        and the rest of the package tested, on a machine with no Azure libraries.
        Hoisting it to the top would break exactly the property this protects.
        """
        import ast
        from pathlib import Path

        import noveintel_inquiries

        banned = ("azure", "streamlit")
        root = Path(noveintel_inquiries.__file__).parent
        offenders = []

        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in tree.body:  # module level only
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                for name in names:
                    if name.split(".")[0] in banned:
                        offenders.append(f"{path.relative_to(root)}:{node.lineno}: {name}")

        assert not offenders, offenders

    def test_the_package_imports_with_those_packages_unavailable(self):
        """The invariant the rule exists for, asserted end to end.

        The AST check above can be satisfied by a lazy import that still runs on the
        import path. This one proves the thing that matters: with ``azure`` and
        ``streamlit`` poisoned in ``sys.modules``, the package — including the job
        layer and its table backend — still imports.
        """
        import subprocess
        import sys

        code = (
            "import sys;"
            "sys.modules['azure'] = None; sys.modules['streamlit'] = None;"
            "import noveintel_inquiries;"
            "import noveintel_inquiries.jobs;"
            "from noveintel_inquiries.jobs import TableStorageJobStore;"
            "assert TableStorageJobStore('UseDevelopmentStorage=true')"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr

    def test_the_engine_imports_without_the_api_package(self):
        """Layer 1 is built on the contract, never on the HTTP layer."""
        import subprocess
        import sys

        code = (
            "import sys;"
            "sys.modules['noveintel_inquiries.api'] = None;"
            "import noveintel_inquiries.engine.compute, noveintel_inquiries.engine.parse,"
            " noveintel_inquiries.engine.frameworks, noveintel_inquiries.engine.taxonomy,"
            " noveintel_inquiries.pipeline"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr

    def test_the_contract_imports_without_fastapi_or_pandas(self):
        """``models`` must be usable by a caller who will never run the service."""
        import subprocess
        import sys

        code = (
            "import sys;"
            "sys.modules['fastapi'] = None; sys.modules['pandas'] = None;"
            "import noveintel_inquiries.models as m;"
            "assert m.EntityInfo(name_ar='a', name_en='b')"
        )
        assert subprocess.run([sys.executable, "-c", code]).returncode == 0
