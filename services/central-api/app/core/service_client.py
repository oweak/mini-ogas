from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from .config import settings


def get_json(url: str, timeout: float | None = None) -> tuple[bool, Any]:
    request = Request(url, headers={"X-OGAS-Token": settings.api_access_token})
    try:
        with urlopen(request, timeout=timeout or settings.service_probe_timeout_seconds) as response:
            return True, json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return False, {"error": exc.__class__.__name__}


def post_json(url: str, payload: dict[str, Any], timeout: float | None = None) -> tuple[bool, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        url, data=data,
        headers={"Content-Type": "application/json", "X-OGAS-Token": settings.api_access_token},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout or settings.service_probe_timeout_seconds) as response:
            return True, json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return False, {"error": exc.__class__.__name__}
