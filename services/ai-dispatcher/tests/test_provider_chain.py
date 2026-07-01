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
