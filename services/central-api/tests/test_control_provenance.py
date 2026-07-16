from __future__ import annotations

from app.core.ai.dispatcher import DispatchResult
from app.core.config import settings
from app.routers import control


def test_control_plan_reports_rule_engine_when_live_provider_falls_back(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(
        control.dispatcher_client,
        "infer",
        lambda *_args, **_kwargs: DispatchResult(
            "fallback",
            None,
            {
                "request_id": "control-fallback",
                "provider": "rule_fallback",
                "model": "deterministic-rules",
                "source": "rule_fallback",
                "attempts": [],
                "latency_ms": 1,
            },
        ),
    )

    plan, provider = control.plan_command("please inspect current production constraints")

    assert plan.action in control.ALLOWED_ACTIONS
    assert provider == "rule_engine"
