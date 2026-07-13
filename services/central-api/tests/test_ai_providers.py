from __future__ import annotations

import json

from app.core.ai.base import DiagnosisResult
from app.core.ai.registry import ProviderRegistry
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


class _DiagnosisProvider:
    def __init__(self, name: str, *, result: DiagnosisResult | None = None, error: str = "") -> None:
        self.name = name
        self._model = f"{name}-model"
        self._result = result
        self._error = error

    def is_available(self) -> bool:
        return True

    def diagnose(self, _prompt: str, timeout: float | None = None) -> DiagnosisResult:
        if self._error:
            raise RuntimeError(self._error)
        assert self._result is not None
        return self._result


def _registry_with(*providers: _DiagnosisProvider) -> ProviderRegistry:
    registry = ProviderRegistry.__new__(ProviderRegistry)
    registry._providers = list(providers)
    registry._verified_provider = None
    return registry


def test_diagnosis_provenance_reports_actual_live_provider() -> None:
    result = DiagnosisResult("bearing wear", "inspect spindle", 0.82)
    registry = _registry_with(
        _DiagnosisProvider("deepseek", error="timeout"),
        _DiagnosisProvider("ollama", result=result),
    )

    diagnosis, provider, errors = registry.diagnose_with_provenance("diagnose")

    assert diagnosis == result
    assert provider == "ollama"
    assert errors == ["deepseek: timeout"]
    assert registry.verified_provider() == "ollama"
    assert registry.model_for(provider) == "ollama-model"


def test_diagnosis_provenance_never_marks_rule_fallback_as_live() -> None:
    fallback = DiagnosisResult("rule result", "manual review", 0.5)
    registry = _registry_with(
        _DiagnosisProvider("deepseek", error="unavailable"),
        _DiagnosisProvider("rule_fallback", result=fallback),
    )

    diagnosis, provider, errors = registry.diagnose_with_provenance("diagnose")

    assert diagnosis == fallback
    assert provider == "rule_fallback"
    assert errors == ["deepseek: unavailable"]
    assert registry.verified_provider() is None
