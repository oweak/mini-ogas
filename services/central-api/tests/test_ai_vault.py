from __future__ import annotations

from app.core.ai import vault as ai_vault
from app.core.ai.dispatcher import DispatchResult
from app.core.config import settings
from app.routers import ai, compat


def test_central_vault_unlock_delegates_without_returning_secret(monkeypatch) -> None:
    observed: list[str] = []
    monkeypatch.setattr(
        ai_vault.dispatcher_client,
        "unlock",
        lambda password: observed.append(password)
        or {
            "ok": True,
            "provider": "deepseek",
            "model": "deepseek-chat",
            "provider_model": "deepseek/deepseek-chat",
            "egress_origin": "https://api.deepseek.com",
        },
    )

    result = ai_vault.unlock_ai_runtime("test-password")

    assert observed == ["test-password"]
    assert result["provider_model"] == "deepseek/deepseek-chat"
    assert "api_key" not in result


def test_login_unlocks_dispatcher_vault_before_ai_smoke(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(compat, "vault_present", lambda: True)
    monkeypatch.setattr(
        compat,
        "_ai_runtime",
        lambda: {
            "configured": True,
            "reachable": True,
            "vault_present": True,
            "vault_unlocked": False,
            "source": "configured",
        },
    )
    monkeypatch.setattr(
        compat,
        "unlock_ai_runtime",
        lambda password: calls.append(password) or {"provider": "deepseek"},
    )
    monkeypatch.setattr(
        compat.dispatcher_client,
        "connectivity_probe",
        lambda: DispatchResult(
            "OK",
            None,
            {
                "request_id": "probe-1",
                "provider": "deepseek",
                "model": "deepseek-chat",
                "source": "api",
                "attempts": [],
                "latency_ms": 5,
            },
        ),
    )

    result = compat.login(
        compat._LoginBody(operator="admin", password=settings.api_access_token)
    )

    assert calls == [settings.api_access_token]
    assert result["ai_smoke"]["ok"] is True
    assert result["ai_smoke"]["source"] == "api"
    assert result["ai_smoke"]["provenance"]["request_id"] == "probe-1"


def test_runtime_status_is_owned_by_dispatcher(monkeypatch) -> None:
    monkeypatch.setattr(
        ai_vault.dispatcher_client,
        "status",
        lambda: {
            "owner": "ai-dispatcher",
            "reachable": True,
            "vault_present": True,
            "vault_unlocked": False,
            "provider": "rule_fallback",
            "model": "deterministic-rules",
        },
    )

    status = ai_vault.runtime_status()

    assert status["owner"] == "ai-dispatcher"
    assert status["vault_present"] is True
    assert status["vault_unlocked"] is False


def test_dispatcher_rule_fallback_is_the_only_model_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        ai.dispatcher_client,
        "diagnose",
        lambda **_kwargs: {
            "root_cause": "deterministic fallback",
            "recommended_action": "observe",
            "need_isolation": False,
            "confidence": 0.5,
            "source": "local-fallback",
            "provenance": {
                "request_id": "fallback-1",
                "provider": "rule_fallback",
                "model": "deterministic-rules",
                "provider_model": "rule_fallback/deterministic-rules",
                "source": "rule_fallback",
                "attempts": [],
                "latency_ms": 1,
            },
        },
    )

    result = ai.diagnose_via_dispatcher(
        ai.AiDiagnoseRequest(node_code="milling-workshop-01"),
        "test alert",
        "medium",
        None,
    )

    assert result is not None
    assert result["provenance"]["provider"] == "rule_fallback"
