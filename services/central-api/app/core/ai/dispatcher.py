from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..config import settings


class DispatcherError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail[:240]


@dataclass(frozen=True)
class DispatchResult:
    content: str
    structured_output: dict[str, Any] | None
    provenance: dict[str, Any]

    @property
    def provider(self) -> str:
        return str(self.provenance.get("provider") or "rule_fallback")

    @property
    def model(self) -> str:
        return str(self.provenance.get("model") or "deterministic-rules")

    @property
    def source(self) -> str:
        return str(self.provenance.get("source") or "rule_fallback")

    @property
    def live(self) -> bool:
        return self.source == "api"


class DispatcherClient:
    """The only Central API gateway to model-serving behavior."""

    def status(self) -> dict[str, Any]:
        try:
            data = self._request("GET", "/runtime/status")
        except DispatcherError as exc:
            return self._offline_status(exc.code)
        if not isinstance(data, dict):
            return self._offline_status("invalid_dispatcher_status")
        return {
            **data,
            "reachable": True,
            "owner": "ai-dispatcher",
        }

    def unlock(self, password: str) -> dict[str, Any]:
        data = self._request(
            "POST",
            "/runtime/unlock",
            {"password": password},
            timeout=max(10.0, min(float(settings.ai_timeout_seconds), 60.0)),
        )
        if not isinstance(data, dict) or not data.get("ok"):
            raise DispatcherError("vault_unlock_failed")
        return data

    def infer(
        self,
        messages: list[dict[str, str]],
        *,
        task_type: str,
        response_format: str = "text",
        max_tokens: int | None = None,
        correlation_id: str = "",
        timeout: float | None = None,
    ) -> DispatchResult:
        payload = {
            "task_type": task_type,
            "messages": messages,
            "response_format": response_format,
            "max_tokens": max_tokens or settings.ai_chat_max_tokens,
            "correlation_id": correlation_id,
        }
        data = self._request("POST", "/v1/inference", payload, timeout=timeout)
        return self._dispatch_result(data)

    def diagnose(
        self,
        *,
        node_code: str,
        alert_type: str,
        severity: str,
        description: str,
        recent_metrics: list[dict[str, Any]],
        correlation_id: str = "",
        timeout: float | None = None,
    ) -> dict[str, Any]:
        data = self._request(
            "POST",
            "/diagnose",
            {
                "node_code": node_code,
                "alert_type": alert_type,
                "severity": severity,
                "description": description,
                "recent_metrics": recent_metrics,
                "correlation_id": correlation_id,
            },
            timeout=timeout,
        )
        if not isinstance(data, dict) or not isinstance(data.get("provenance"), dict):
            raise DispatcherError("invalid_diagnosis_contract")
        return data

    def connectivity_probe(self) -> DispatchResult:
        return self.infer(
            [
                {"role": "system", "content": "You are a Mini-OGAS connectivity probe."},
                {"role": "user", "content": "Reply with exactly: OK"},
            ],
            task_type="connectivity_probe",
            max_tokens=128,
            timeout=max(10.0, min(float(settings.ai_timeout_seconds), 60.0)),
        )

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            settings.ai_dispatcher_url.rstrip("/") + path,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-OGAS-Token": settings.ai_dispatcher_token,
            },
            method=method,
        )
        try:
            with urlopen(
                request,
                timeout=timeout or max(1.0, float(settings.ai_timeout_seconds)),
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = ""
            try:
                parsed = json.loads(exc.read().decode("utf-8"))
                detail = str(parsed.get("detail") or "") if isinstance(parsed, dict) else ""
            except (UnicodeDecodeError, json.JSONDecodeError):
                detail = ""
            raise DispatcherError(f"dispatcher_http_{exc.code}", detail) from exc
        except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise DispatcherError(f"dispatcher_{exc.__class__.__name__.lower()}") from exc

    @staticmethod
    def _dispatch_result(data: Any) -> DispatchResult:
        if not isinstance(data, dict):
            raise DispatcherError("invalid_inference_contract")
        content = data.get("content")
        provenance = data.get("provenance")
        structured = data.get("structured_output")
        if not isinstance(content, str) or not isinstance(provenance, dict):
            raise DispatcherError("invalid_inference_contract")
        if structured is not None and not isinstance(structured, dict):
            raise DispatcherError("invalid_inference_contract")
        required = {"request_id", "provider", "model", "source", "attempts", "latency_ms"}
        if not required.issubset(provenance):
            raise DispatcherError("incomplete_inference_provenance")
        return DispatchResult(content, structured, provenance)

    @staticmethod
    def _offline_status(error: str) -> dict[str, Any]:
        return {
            "status": "unavailable",
            "source": "rule_fallback",
            "provider": "rule_fallback",
            "model": "deterministic-rules",
            "provider_model": "rule_fallback/deterministic-rules",
            "configured": False,
            "vault_present": False,
            "vault_unlocked": False,
            "providers": [],
            "reachable": False,
            "owner": "ai-dispatcher",
            "error": error,
        }


dispatcher_client = DispatcherClient()
