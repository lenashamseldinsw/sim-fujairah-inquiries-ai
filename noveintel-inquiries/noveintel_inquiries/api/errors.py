"""
One error shape for every failure.

A caller should be able to tell three things apart without reading prose: their
request was wrong, our upstream was wrong, or something broke on our side. Those map
to distinct status codes and a stable ``code`` string; the human-readable ``message``
is for the operator reading logs, not for branching on.

Everything the service raises deliberately becomes an ``ApiError`` before it reaches
the client, so there is exactly one renderer and no route returns a bare
``{"detail": ...}``.

One validation failure is singled out from the rest. A required column arriving absent
is the commonest way a real export is wrong, and pydantic reports it per record — a
hundred thousand rows with no ``الحل`` column produce a hundred thousand identical
errors, which is a useless answer to a simple question. ``_missing_columns`` folds
those into one ``missing_required_columns`` error naming the columns and the records
that failed.

**Records are never echoed back.** Each pydantic error carries the offending record as
``input``, and a record is customer data — for the complaints module it is a named
person with an identity-document number. The folded error reports indices and counts,
never values.
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

from ..exceptions import StageFailure
from .models.records import HARD_REQUIRED_COLUMNS, InquiryRecord

__all__ = [
    "ApiError",
    "ErrorBody",
    "ErrorResponse",
    "MISSING_COLUMNS_CODE",
    "StageFailure",
    "UpstreamError",
    "register_exception_handlers",
]

logger = logging.getLogger(__name__)

MISSING_COLUMNS_CODE = "missing_required_columns"

# Pydantic reports a missing field by its **alias** when the model declares one, so a
# record missing ``case_number`` comes back located at ``رقم_الطلب``. Folding on the
# snake_case name alone would therefore never match, and every real missing-column
# payload would fall through to the generic per-record error — which is the failure
# this fold exists to prevent. Both spellings are accepted, and the message names the
# snake_case one because that is what a caller building a payload wrote.
_ALIAS_TO_FIELD: dict[str, str] = {
    (field.alias or name): name
    for name, field in InquiryRecord.model_fields.items()
}
_REQUIRED_LOCATIONS: dict[str, str] = {
    spelling: field
    for field in HARD_REQUIRED_COLUMNS
    for spelling in (field, InquiryRecord.model_fields[field].alias or field)
}

# How many offending record indices to name. Enough to find the problem in a
# hand-built payload; bounded because a file with a column missing has *every* record
# offending, and echoing a hundred thousand indices answers nothing the count does not.
MAX_REPORTED_RECORDS = 20


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


def _missing_columns(errors: list[dict[str, Any]]) -> ApiError | None:
    """Fold per-record missing-key failures into one error naming the columns.

    Returns ``None`` when nothing in ``errors`` is a required column arriving absent,
    in which case the caller renders the ordinary validation error.

    A required field pydantic never received arrives as ``type="missing"`` at
    ``("body", "records", <i>, "<column>")``, which carries the column and the record
    index already — spelled with the model's alias, which is why ``_REQUIRED_LOCATIONS``
    maps both spellings back to the snake_case field name.

    Errors of other kinds are counted rather than echoed: a payload with a missing
    column usually has the same wrong shape throughout, and the columns are what the
    caller has to fix first.
    """
    columns: set[str] = set()
    records: set[int] = set()
    others = 0

    for error in errors:
        loc = error.get("loc") or ()
        if len(loc) < 4 or loc[0] != "body" or loc[1] != "records":
            others += 1
            continue
        index = loc[2]
        if not isinstance(index, int):
            others += 1
            continue
        field = _REQUIRED_LOCATIONS.get(str(loc[3]))
        if error.get("type") == "missing" and field is not None:
            columns.add(field)
            records.add(index)
        else:
            others += 1

    if not columns:
        return None

    named = sorted(columns)
    reported = sorted(records)
    detail: dict[str, Any] = {
        "columns": named,
        "records": reported[:MAX_REPORTED_RECORDS],
        "records_total": len(reported),
    }
    if others:
        detail["other_error_count"] = others

    plural = "columns" if len(named) > 1 else "column"
    return ApiError(
        422,
        MISSING_COLUMNS_CODE,
        f"{len(reported)} record(s) are missing the required {plural} "
        f"{', '.join(named)}. Every record must carry these keys — the pipeline's "
        "first stage refuses a run without them. Either the snake_case name or the "
        "normalised Arabic column name is accepted.",
        detail=detail,
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
        missing = _missing_columns(errors)
        if missing is not None:
            logger.info("%s: %s", missing.code, missing.message)
            return missing.response()

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
