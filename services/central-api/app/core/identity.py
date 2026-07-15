from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Request


REQUEST_ID_HEADER = "X-Request-ID"
_ID_PREFIX_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$")


def utc_now() -> datetime:
    """Return an aware UTC timestamp for persisted or externally visible facts."""
    return datetime.now(UTC)


def utc_iso(value: datetime | None = None) -> str:
    timestamp = ensure_utc(value or utc_now())
    return timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def new_id(prefix: str) -> str:
    if not _ID_PREFIX_PATTERN.fullmatch(prefix):
        raise ValueError("ID prefix must use lowercase letters, digits or underscores")
    return f"{prefix}_{uuid4().hex}"


def request_id_for(request: Request) -> str:
    existing = getattr(request.state, "request_id", "")
    if isinstance(existing, str) and _REQUEST_ID_PATTERN.fullmatch(existing):
        return existing

    candidate = request.headers.get(REQUEST_ID_HEADER, "").strip()
    request_id = candidate if _REQUEST_ID_PATTERN.fullmatch(candidate) else new_id("req")
    request.state.request_id = request_id
    return request_id
