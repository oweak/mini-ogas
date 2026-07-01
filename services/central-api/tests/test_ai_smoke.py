from __future__ import annotations

from app.core.config import settings
from app.routers import compat


def test_login_smoke_reports_actual_provider_provenance(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(compat.registry, "is_any_live_provider", lambda: True)
    monkeypatch.setattr(compat.registry, "chat_with_provenance", lambda *_args, **_kwargs: ("OK", "deepseek", []))
    monkeypatch.setattr(compat.registry, "verified_provider", lambda: "deepseek")

    result = compat.login(compat._LoginBody(password=settings.api_access_token))

    assert result["ai_smoke"]["ok"] is True
    assert result["ai_smoke"]["source"] == "api"
    assert result["ai_smoke"]["provider"] == "deepseek"
    assert result["runtime"]["source"] == "api"


def test_login_smoke_reports_rule_fallback_when_provider_call_fails(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(compat.registry, "is_any_live_provider", lambda: True)
    monkeypatch.setattr(
        compat.registry,
        "chat_with_provenance",
        lambda *_args, **_kwargs: ("fallback", "rule_fallback", ["deepseek: timeout"]),
    )
    monkeypatch.setattr(compat.registry, "verified_provider", lambda: None)

    result = compat.login(compat._LoginBody(password=settings.api_access_token))

    assert result["ai_smoke"]["ok"] is False
    assert result["ai_smoke"]["source"] == "rule_fallback"
    assert result["ai_smoke"]["status"] == "api_error"