from __future__ import annotations

import json

import pytest

from app.core.ai.providers.deepseek import DeepSeekProvider


def test_deepseek_chat_uses_configured_response_budget(monkeypatch) -> None:
    provider = DeepSeekProvider(
        api_key="test-key",
        base_url="https://example.invalid",
        model="deepseek-v4-pro",
        chat_max_tokens=4096,
    )
    captured: dict = {}

    def fake_raw_call(body: dict, timeout=None) -> str:
        captured.update(body)
        return "ok"

    monkeypatch.setattr(provider, "_raw_call", fake_raw_call)

    assert provider.chat([{"role": "user", "content": "diagnose"}]) == "ok"
    assert captured["max_tokens"] == 4096


def test_deepseek_raw_call_rejects_empty_content(monkeypatch) -> None:
    provider = DeepSeekProvider(
        api_key="test-key",
        base_url="https://example.invalid",
        model="deepseek-v4-pro",
    )
    payload = {
        "choices": [{
            "finish_reason": "length",
            "message": {"content": "", "reasoning_content": "internal reasoning"},
        }]
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: FakeResponse())

    with pytest.raises(RuntimeError, match="empty content field"):
        provider.chat([{"role": "user", "content": "diagnose"}])
