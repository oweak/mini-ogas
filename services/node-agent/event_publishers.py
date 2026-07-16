from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from abc import ABC, abstractmethod


class EventPublisher(ABC):
    """Transport boundary for node events sent to the central control plane."""

    @abstractmethod
    def publish_heartbeat(self, payload: dict) -> dict:
        raise NotImplementedError


class HTTPPublisher(EventPublisher):
    """Current HTTP implementation; future transports can replace this class."""

    def __init__(self, base_url: str, api_token: str, timeout_seconds: int = 3) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.timeout_seconds = timeout_seconds

    def publish_heartbeat(self, payload: dict) -> dict:
        request_id = str(uuid.uuid4())
        node_code = str(payload.get("node_code") or "")
        request = urllib.request.Request(
            f"{self.base_url}/api/agents/{node_code}/heartbeat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-OGAS-Token": self.api_token,
                "X-Request-ID": request_id,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                ok = 200 <= response.status < 300
                return {
                    "synced": ok,
                    "request_id": request_id,
                    "http_status": response.status,
                    "error": "",
                }
        except urllib.error.HTTPError as error:
            try:
                detail = error.read().decode("utf-8", errors="replace")
            except OSError:
                detail = ""
            return {
                "synced": False,
                "request_id": request_id,
                "http_status": error.code,
                "error": detail or str(error),
            }
        except (urllib.error.URLError, TimeoutError) as error:
            return {
                "synced": False,
                "request_id": request_id,
                "http_status": 0,
                "error": str(error),
            }
