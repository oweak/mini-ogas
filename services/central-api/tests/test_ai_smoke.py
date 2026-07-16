from __future__ import annotations

from app.core.ai.dispatcher import DispatchResult
from app.core.config import settings
from app.core.security import ActorInfo
from app.routers import compat


def test_login_smoke_reports_actual_provider_provenance(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(compat, "_preflight_payload", lambda: {"ok": True, "checks": []})
    monkeypatch.setattr(compat, "vault_present", lambda: False)
    monkeypatch.setattr(
        compat,
        "_ai_runtime",
        lambda: {"configured": True, "reachable": True, "source": "api"},
    )
    monkeypatch.setattr(
        compat.dispatcher_client,
        "connectivity_probe",
        lambda: DispatchResult(
            "OK",
            None,
            {
                "request_id": "probe-live",
                "provider": "deepseek",
                "model": "deepseek-chat",
                "source": "api",
                "attempts": [],
                "latency_ms": 4,
            },
        ),
    )

    result = compat.login(compat._LoginBody(password=settings.api_access_token))

    assert result["ai_smoke"]["ok"] is True
    assert result["ai_smoke"]["source"] == "api"
    assert result["ai_smoke"]["provider"] == "deepseek"
    assert result["ai_smoke"]["model"] == "deepseek-chat"
    assert result["preflight"]["ok"] is True
    assert result["runtime"]["source"] == "api"


def test_login_smoke_reports_rule_fallback_when_provider_call_fails(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(compat, "_preflight_payload", lambda: {"ok": True, "checks": []})
    monkeypatch.setattr(compat, "vault_present", lambda: False)
    monkeypatch.setattr(
        compat,
        "_ai_runtime",
        lambda: {"configured": True, "reachable": True, "source": "configured"},
    )
    monkeypatch.setattr(
        compat.dispatcher_client,
        "connectivity_probe",
        lambda: DispatchResult(
            "fallback",
            None,
            {
                "request_id": "probe-fallback",
                "provider": "rule_fallback",
                "model": "deterministic-rules",
                "source": "rule_fallback",
                "attempts": [{"provider": "deepseek", "status": "failed"}],
                "latency_ms": 8,
            },
        ),
    )

    result = compat.login(compat._LoginBody(password=settings.api_access_token))

    assert result["ai_smoke"]["ok"] is False
    assert result["ai_smoke"]["source"] == "rule_fallback"
    assert result["ai_smoke"]["status"] == "api_error"


def test_compat_diagnosis_reports_actual_rule_fallback_provenance(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(
        compat.dispatcher_client,
        "diagnose",
        lambda **_kwargs: {
            "root_cause": "rule root cause",
            "recommended_action": "manual review",
            "confidence": 0.55,
            "need_isolation": False,
            "provenance": {
                "request_id": "diag-fallback",
                "provider": "rule_fallback",
                "model": "deterministic-rules",
                "provider_model": "rule_fallback/deterministic-rules",
                "source": "rule_fallback",
                "attempts": [{"provider": "deepseek", "status": "failed"}],
                "latency_ms": 10,
            },
        },
    )

    result = compat.diagnose_by_issue_id(
        "truth-node-compat-provider-fallback",
        ActorInfo(role="system_admin", permissions={"ai:diagnose"}),
    )

    assert result["used_deepseek"] is False
    assert result["provider"] == "rule_fallback"
    assert result["source"] == "rule_fallback"
    assert result["status"] == "local-fallback"
    assert result["model_name"] == "rule_fallback/deterministic-rules"
