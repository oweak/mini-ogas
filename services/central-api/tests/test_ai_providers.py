from __future__ import annotations

import json

import pytest
from app.core.ai.dispatcher import DispatcherClient, DispatcherError


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_dispatcher_status_identifies_single_model_call_owner(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.core.ai.dispatcher.urlopen",
        lambda *_args, **_kwargs: _FakeResponse(
            {
                "status": "configured",
                "provider": "deepseek",
                "model": "deepseek-chat",
                "configured": True,
                "providers": [],
            }
        ),
    )

    status = DispatcherClient().status()

    assert status["reachable"] is True
    assert status["owner"] == "ai-dispatcher"
    assert status["provider"] == "deepseek"


def test_inference_provenance_reports_actual_dispatcher_provider(monkeypatch) -> None:
    payload = {
        "content": "Ollama served the request.",
        "structured_output": None,
        "provenance": {
            "request_id": "req-1",
            "provider": "ollama",
            "model": "deepseek-r1:7b-local",
            "provider_model": "ollama/deepseek-r1:7b-local",
            "source": "api",
            "attempts": [
                {"provider": "deepseek", "status": "failed"},
                {"provider": "ollama", "status": "succeeded"},
            ],
            "latency_ms": 42,
        },
    }
    monkeypatch.setattr(
        "app.core.ai.dispatcher.urlopen",
        lambda *_args, **_kwargs: _FakeResponse(payload),
    )

    result = DispatcherClient().infer(
        [{"role": "user", "content": "diagnose"}],
        task_type="chat",
    )

    assert result.live is True
    assert result.provider == "ollama"
    assert result.model == "deepseek-r1:7b-local"
    assert result.provenance["attempts"][0]["provider"] == "deepseek"


def test_inference_rejects_missing_provenance_fields(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.core.ai.dispatcher.urlopen",
        lambda *_args, **_kwargs: _FakeResponse(
            {"content": "not auditable", "structured_output": None, "provenance": {}}
        ),
    )

    with pytest.raises(DispatcherError, match="incomplete_inference_provenance"):
        DispatcherClient().infer(
            [{"role": "user", "content": "diagnose"}],
            task_type="chat",
        )


def test_connectivity_probe_reserves_enough_output_for_reasoning_models(monkeypatch) -> None:
    client = DispatcherClient()
    captured: dict[str, object] = {}

    def fake_request(method, path, payload=None, **kwargs):
        captured.update(
            {"method": method, "path": path, "payload": payload, "timeout": kwargs.get("timeout")}
        )
        return {
            "content": "OK",
            "structured_output": None,
            "provenance": {
                "request_id": "probe-128",
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
                "source": "api",
                "attempts": [],
                "latency_ms": 10,
            },
        }

    monkeypatch.setattr(client, "_request", fake_request)

    result = client.connectivity_probe()

    assert result.live is True
    assert captured["method"] == "POST"
    assert captured["path"] == "/v1/inference"
    assert captured["payload"]["max_tokens"] == 128
