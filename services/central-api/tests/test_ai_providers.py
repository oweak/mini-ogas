from __future__ import annotations

import json

from app.core.ai.providers.ollama import OllamaProvider


class _FakeResponse:
    status = 200

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        return False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def test_ollama_available_only_when_configured_model_exists(monkeypatch) -> None:
    def fake_urlopen(_request, timeout: int):
        assert timeout == 2
        return _FakeResponse({"models": [{"name": "deepseek-r1:7b-local"}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    assert OllamaProvider(model="deepseek-r1:7b-local").is_available() is True
    assert OllamaProvider(model="llama3").is_available() is False
