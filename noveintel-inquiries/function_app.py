"""
Azure Functions wrapper.

The service is the FastAPI app; this only puts it on a platform. Azure's ASGI adapter
hands the app each request and returns its response, so nothing about the routes, the
models or the pipeline changes — and nothing under ``noveintel_inquiries/`` imports
``azure.functions``. Delete this file and ``host.json`` and the service is untouched.

Three things are easy to get wrong here:

* ``host.json`` must set ``routePrefix`` to an empty string. The default prefixes
  every route with ``/api``, which FastAPI knows nothing about, so every request
  would 404.
* ``AuthLevel.FUNCTION`` makes the platform check a function key before a request
  reaches the app, which is why ``NOVEINQ_API_KEY`` is normally left unset here.
  Setting both simply means a caller presents two keys.
* **Runs are held in the worker's memory.** A job is accepted by one instance and
  polled from whichever instance the load balancer picks, so this must run on a
  single always-on instance — or behind sticky routing, or with a shared job store
  behind ``noveintel_inquiries.jobs.JobStore``. On a Consumption plan an idle worker is recycled
  and a running job dies with it. ``README.md`` has the deployment notes.
"""
from __future__ import annotations

import azure.functions as func

from noveintel_inquiries.api.app import app as fastapi_app

app = func.AsgiFunctionApp(app=fastapi_app, http_auth_level=func.AuthLevel.FUNCTION)
