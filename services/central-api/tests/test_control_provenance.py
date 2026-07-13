from __future__ import annotations

from app.core.config import settings
from app.routers import control


def test_control_plan_reports_rule_engine_when_live_provider_falls_back(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(control.registry, "is_any_live_provider", lambda: True)
    monkeypatch.setattr(
        control.registry,
        "chat_with_provenance",
        lambda *_args, **_kwargs: ("fallback", "rule_fallback", ["deepseek: timeout"]),
    )

    plan, provider = control.plan_command("please inspect current production constraints")

    assert plan.action in control.ALLOWED_ACTIONS
    assert provider == "rule_engine"
