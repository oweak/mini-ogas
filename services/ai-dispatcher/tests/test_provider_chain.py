from __future__ import annotations

import asyncio

from app import main


def _request() -> main.DiagnosisRequest:
    return main.DiagnosisRequest(
        node_code="milling-workshop-01",
        alert_type="QUALITY_DRIFT",
        severity=main.Severity.medium,
        description="controlled provider-chain test",
    )


def test_chain_uses_next_provider_after_first_provider_fails(monkeypatch) -> None:
    monkeypatch.setattr(main, "_provider_chain", lambda: ["deepseek", "ollama"])
    monkeypatch.setattr(main, "_provider_configured", lambda _name: True)

    async def fake_call(_client, provider: str, _req):
        if provider == "deepseek":
            raise ValueError("simulated DeepSeek outage")
        return {
            "root_cause": "local queue imbalance",
            "recommended_action": "reduce intake rate",
            "need_isolation": False,
            "summary": "Ollama served the diagnosis.",
        }

    monkeypatch.setattr(main, "_call_provider", fake_call)
    result = asyncio.run(main.diagnose_with_chain(_request()))

    assert result.source == "ollama"
    assert result.attempted_providers == ["deepseek", "ollama"]
    assert result.provider_errors[0].startswith("deepseek:")


def test_chain_reaches_local_fallback_only_after_all_providers_fail(monkeypatch) -> None:
    monkeypatch.setattr(main, "_provider_chain", lambda: ["deepseek", "groq"])
    monkeypatch.setattr(main, "_provider_configured", lambda _name: True)

    async def failing_call(_client, provider: str, _req):
        raise ValueError(f"{provider} unavailable")

    monkeypatch.setattr(main, "_call_provider", failing_call)
    result = asyncio.run(main.diagnose_with_chain(_request()))

    assert result.source == "local-fallback"
    assert result.attempted_providers == ["deepseek", "groq"]
    assert len(result.provider_errors) == 2


def test_ollama_configured_requires_selected_model(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"models": [{"name": "deepseek-r1:7b-local"}]}

    monkeypatch.setenv("OLLAMA_MODEL", "deepseek-r1:7b-local")
    monkeypatch.setattr(main.httpx, "get", lambda *_args, **_kwargs: FakeResponse())

    assert main._provider_configured("ollama") is True

    monkeypatch.setenv("OLLAMA_MODEL", "llama3")

    assert main._provider_configured("ollama") is False


def test_lm_studio_configured_requires_reachable_server(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(main.httpx, "get", lambda *_args, **_kwargs: FakeResponse())

    assert main._provider_configured("lm_studio") is True

    def fail_get(*_args, **_kwargs):
        raise main.httpx.ConnectError("connection refused")

    monkeypatch.setattr(main.httpx, "get", fail_get)

    assert main._provider_configured("lm_studio") is False
