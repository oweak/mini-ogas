from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from .identity import request_id_for, utc_iso


DEFAULT_ERROR_CODES = {
    400: "INVALID_ARGUMENT",
    401: "UNAUTHENTICATED",
    403: "PERMISSION_DENIED",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    503: "UNAVAILABLE",
}


def problem_response(
    request: Request,
    status_code: int,
    detail: Any,
    *,
    code: str | None = None,
    title: str | None = None,
) -> JSONResponse:
    """Build the Phase 1 error envelope while preserving legacy ``detail``."""
    resolved_code = code or DEFAULT_ERROR_CODES.get(status_code, "REQUEST_FAILED")
    resolved_title = title or HTTPStatus(status_code).phrase
    content = {
        "type": f"urn:mini-ogas:error:{resolved_code.lower().replace('_', '-')}",
        "title": resolved_title,
        "status": status_code,
        "code": resolved_code,
        "detail": jsonable_encoder(detail),
        "instance": request.url.path,
        "request_id": request_id_for(request),
        "timestamp": utc_iso(),
    }
    return JSONResponse(
        status_code=status_code,
        content=content,
        media_type="application/problem+json",
    )
