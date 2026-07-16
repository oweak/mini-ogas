from __future__ import annotations

from pathlib import Path

from app.core.ai.dispatcher import DispatcherClient, DispatcherError


def test_central_api_contains_no_model_provider_transport_stack() -> None:
    app_root = Path(__file__).resolve().parents[1] / "app"
    forbidden = (
        "chat/completions",
        "api.deepseek.com",
        "api.groq.com",
        "DEEPSEEK_API_KEY",
        "GROQ_API_KEY",
        "AI_PROVIDER_CHAIN",
        "ProviderRegistry",
    )
    matches: list[str] = []
    for path in app_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                matches.append(f"{path.relative_to(app_root)}:{token}")

    assert matches == []


def test_unreachable_dispatcher_is_explicit_rule_fallback(monkeypatch) -> None:
    client = DispatcherClient()
    monkeypatch.setattr(
        client,
        "_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            DispatcherError("dispatcher_unreachable")
        ),
    )

    status = client.status()

    assert status["reachable"] is False
    assert status["source"] == "rule_fallback"
    assert status["owner"] == "ai-dispatcher"
