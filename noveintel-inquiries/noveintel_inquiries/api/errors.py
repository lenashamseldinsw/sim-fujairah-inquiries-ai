"""
One error shape for every failure.

A caller should be able to tell three things apart without reading prose: their
request was wrong, our upstream was wrong, or something broke on our side. Those map
to distinct status codes and a stable ``code`` string; the human-readable ``message``
is for the operator reading logs, not for branching on.

Everything the service raises deliberately becomes an ``ApiError`` before it reaches
the client, so there is exactly one renderer and no route returns a bare
``{"detail": ...}``.

A missing required input — a column absent from every record, a required setting
(X2–X4) or the taxonomy — is answered as one ``missing_required_columns`` error whose
message reads "The following input field(s) were missing or unmapped: …" and whose
``detail.fields`` names each one with its U-/X-id. Required is decided per column,
not per record, so this is checked once per request (``pipeline.check_inputs``).

**Records are never echoed back.** A pydantic error carries the offending record as
``input``, and a record is customer data; ``input`` and ``ctx`` are stripped before a
validation error goes over the wire.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..exceptions import MissingInputs, StageFailure

__all__ = [
    "ApiError",
    "ErrorBody",
    "ErrorResponse",
    "MISSING_COLUMNS_CODE",
    "StageFailure",
    "UpstreamError",
    "missing_inputs_error",
    "register_exception_handlers",
]

logger = logging.getLogger(__name__)

MISSING_COLUMNS_CODE = "missing_required_columns"

class ErrorBody(BaseModel):
    """The failure itself."""

    code: str = Field(description="Stable machine-readable identifier for the failure.")
    message: str = Field(description="What went wrong, in one sentence.")
    detail: Any | None = Field(
        default=None,
        description=(
            "Structured context where there is any — which columns were missing and "
            "how many records lacked them, for instance. Never the records themselves."
        ),
    )


class ErrorResponse(BaseModel):
    """The body returned by every failing request."""

    error: ErrorBody


class ApiError(Exception):
    """A failure with a status code already decided."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        detail: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail

    def response(self) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorBody(code=self.code, message=self.message, detail=self.detail)
        )
        return JSONResponse(
            status_code=self.status_code, content=jsonable_encoder(body)
        )


class UpstreamError(ApiError):
    """The model gateway answered, but not with something usable.

    Raised in place of the ``ValueError`` a Core42 call throws when the model refuses,
    is cut off, or returns JSON that survives neither parsing nor repair. Those are
    upstream faults wearing a ``ValueError``'s clothes; without this they would be
    indistinguishable from the pipeline refusing a caller's records.
    """

    def __init__(self, message: str) -> None:
        super().__init__(status.HTTP_502_BAD_GATEWAY, "upstream_error", message)


def missing_inputs_error(exc: MissingInputs) -> ApiError:
    """The 422 for a request missing required inputs, naming every one."""
    return ApiError(
        422,
        MISSING_COLUMNS_CODE,
        str(exc),
        detail={
            "fields": [
                {"field": m.field, "id": m.uid, "label": m.label} for m in exc.missing
            ]
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the handlers that render every failure through ``ErrorResponse``."""

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        # 5xx is ours to explain; 4xx is the caller's to fix, and logging it as an
        # error would bury the ones that matter.
        log = logger.error if exc.status_code >= 500 else logger.info
        log("%s (%d): %s", exc.code, exc.status_code, exc.message)
        return exc.response()

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()

        # Three keys are dropped before this goes over the wire.
        #
        # `input` is the caller's own row on a record-level error — customer data,
        # and for the complaints module a named person with an identity number.
        #
        # `ctx` carries the raising exception object for a custom validator, which
        # is not JSON-serialisable: left in, a coercion failure renders as a 500
        # instead of the 422 it is. It can also hold the offending value.
        #
        # `url` is pydantic's documentation link, and is noise.
        redacted = [
            {k: v for k, v in error.items() if k not in ("input", "ctx", "url")}
            for error in errors
        ]
        return ApiError(
            # Spelled out: Starlette renamed the constant for this code and
            # deprecated the old name, so neither spelling is stable to import.
            422,
            "invalid_request",
            "The request body did not match the expected schema.",
            detail=redacted,
        ).response()

    @app.exception_handler(MissingInputs)
    async def _missing_inputs(_: Request, exc: MissingInputs) -> JSONResponse:
        error = missing_inputs_error(exc)
        logger.info("%s: %s", error.code, error.message)
        return error.response()

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return ApiError(exc.status_code, "http_error", str(exc.detail)).response()

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # The message is deliberately not the exception's: an unhandled failure can
        # carry anything, including a fragment of the request, and this goes over the
        # wire. The traceback belongs in the logs.
        logger.exception("Unhandled error: %s", type(exc).__name__)
        return ApiError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            "The service failed to complete the request.",
        ).response()
