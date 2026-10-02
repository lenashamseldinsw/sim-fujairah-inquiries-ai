"""
The Azure wrapper, and the seam it uses to hand the app a queue dispatcher.

Regression tests for a defect that shipped once. ``function_app.py`` had replaced
``AsgiFunctionApp`` with a hand-written HTTP function that built a fresh ASGI adapter
per request. That adapter never ran the FastAPI lifespan, so on Azure the job and
document stores were never built and every /v1 route answered 503 — while /health,
which needs neither, kept answering 200 and made the deployment look healthy.
"""
from __future__ import annotations

import importlib.util

import pytest
from fastapi.testclient import TestClient

from noveintel_inquiries.api.app import create_app
from noveintel_inquiries.jobs import JobRunner


class _Recorder:
    """A stand-in queue dispatcher: records that it was built, runs nothing."""

    needs_stored_request = True

    def __init__(self, store):
        self.store = store

    def submit(self, job_id, run):
        pass

    async def shutdown(self, timeout=10.0):
        pass


@pytest.fixture
def queue_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CORE42_API_KEY", "test-key")
    monkeypatch.setenv("NOVEINQ_JOB_DISPATCH", "queue")
    monkeypatch.setenv("NOVEINQ_JOB_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("NOVEINQ_STORAGE_DIR", str(tmp_path / "storage"))
    from noveintel_inquiries.config import get_job_settings, get_storage_settings
    from noveintel_inquiries.jobs.factory import create_job_store
    from noveintel_inquiries.storage import create_document_store

    caches = (get_job_settings, get_storage_settings, create_job_store, create_document_store)
    for cached in caches:
        cached.cache_clear()
    yield
    for cached in caches:
        cached.cache_clear()


class TestRunnerFactorySeam:
    def test_the_lifespan_uses_the_hosts_factory(self, queue_env):
        app = create_app()
        app.state.job_runner_factory = _Recorder
        with TestClient(app):
            assert isinstance(app.state.job_runner, _Recorder)
            # Built with the job store the lifespan made, not some other one.
            assert app.state.job_runner.store is app.state.job_store

    def test_without_a_factory_runs_stay_in_process(self, queue_env):
        app = create_app()
        with TestClient(app):
            assert isinstance(app.state.job_runner, JobRunner)

    def test_a_failing_factory_falls_back_rather_than_losing_the_job_store(self, queue_env):
        """A broken queue client must not take the job store down with it."""
        def broken(store):
            raise RuntimeError("queue unreachable")

        app = create_app()
        app.state.job_runner_factory = broken
        with TestClient(app) as client:
            assert isinstance(app.state.job_runner, JobRunner)
            assert client.get("/ready").status_code == 200

    def test_the_factory_is_ignored_when_dispatch_is_inprocess(self, queue_env, monkeypatch):
        monkeypatch.setenv("NOVEINQ_JOB_DISPATCH", "inprocess")
        from noveintel_inquiries.config import get_job_settings
        get_job_settings.cache_clear()
        app = create_app()
        app.state.job_runner_factory = _Recorder
        with TestClient(app):
            assert isinstance(app.state.job_runner, JobRunner)


def _has_azure_functions() -> bool:
    """Whether the Azure Functions SDK is installed.

    Not a bare ``find_spec("azure.functions")``: that imports the parent package
    first and *raises* when ``azure`` is absent altogether — which is exactly the
    on-prem install this needs to skip on.
    """
    try:
        return importlib.util.find_spec("azure.functions") is not None
    except ModuleNotFoundError:
        return False


@pytest.mark.skipif(
    not _has_azure_functions(),
    reason="azure-functions is only installed with the 'azure' extra.",
)
class TestFunctionApp:
    """The wrapper itself. Only importable where the Azure extra is installed."""

    @pytest.fixture(scope="class")
    def wrapper(self):
        import function_app

        return function_app

    def test_it_is_an_asgi_function_app(self, wrapper):
        """The type that runs the lifespan. A plain FunctionApp with a hand-written
        HTTP function is exactly what broke every /v1 route."""
        import azure.functions as func

        assert isinstance(wrapper.app, func.AsgiFunctionApp)

    def test_it_registers_the_api_the_worker_and_the_poison_handler(self, wrapper):
        names = sorted(f.get_function_name() for f in wrapper.app.get_functions())
        assert names == ["http_app", "run_analysis_job", "run_analysis_job_poison"]

    def test_it_hands_the_app_a_queue_dispatcher_factory(self, wrapper):
        assert callable(getattr(wrapper.fastapi_app.state, "job_runner_factory", None))

    def test_the_queue_names_are_this_services(self, wrapper):
        assert wrapper.QUEUE_NAME == "inquiries-runs"
        assert wrapper.POISON_QUEUE == "inquiries-runs-poison"
        assert wrapper.CONNECTION_SETTING == "NOVEINQ_JOB_CONNECTION_STRING"
