from __future__ import annotations

import json

import pytest
from app.core.ai.dispatcher import DispatcherClient, DispatcherError
from app.core.config import settings


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _valid_response(content: str = "ok") -> dict[str, object]:
    return {
        "content": content,
        "structured_output": None,
        "provenance": {
            "request_id": "req-budget",
            "provider": "deepseek",
            "model": "deepseek-chat",
            "source": "api",
            "attempts": [],
            "latency_ms": 1,
        },
    }


def test_central_sends_response_budget_to_dispatcher_not_provider(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(settings, "ai_chat_max_tokens", 4_096)
    monkeypatch.setattr(settings, "api_access_token", "external-api-token")
    monkeypatch.setattr(settings, "ai_dispatcher_token", "dispatcher-only-token")

    def fake_urlopen(request, **_kwargs):
        captured.update(json.loads(request.data.decode("utf-8")))
        captured["service_token"] = request.get_header("X-ogas-token")
        return _FakeResponse(_valid_response())

    monkeypatch.setattr("app.core.ai.dispatcher.urlopen", fake_urlopen)

    DispatcherClient().infer(
        [{"role": "user", "content": "diagnose"}],
        task_type="chat",
    )

    assert captured["max_tokens"] == 4_096
    assert captured["service_token"] == "dispatcher-only-token"
    assert "provider" not in captured
    assert "api_key" not in captured


def test_central_rejects_empty_dispatcher_content(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.core.ai.dispatcher.urlopen",
        lambda *_args, **_kwargs: _FakeResponse(
            {**_valid_response(""), "content": None}
        ),
    )

    with pytest.raises(DispatcherError, match="invalid_inference_contract"):
        DispatcherClient().infer(
            [{"role": "user", "content": "diagnose"}],
            task_type="chat",
        )
