from __future__ import annotations

from ai_runtime import decrypt_vault_payload, encrypt_vault_payload
from app.core.ai import vault as ai_vault
from app.core.config import settings
from app.routers import ai
from app.routers import compat


def test_ai_vault_roundtrip_uses_current_format() -> None:
    payload = {
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "test-token-not-real",
    }

    vault = encrypt_vault_payload(payload, "miniogas")

    assert vault["version"] == "miniogas-vault-v1"
    assert vault["kdf"] == "pbkdf2-sha256-240000"
    assert decrypt_vault_payload(vault, "miniogas") == payload


def test_login_unlocks_vault_before_ai_smoke(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(compat, "vault_present", lambda: True)
    monkeypatch.setattr(compat, "unlock_ai_runtime", lambda password: calls.append(password) or {
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "base_url": "https://api.deepseek.com/v1",
    })
    monkeypatch.setattr(compat.registry, "is_any_live_provider", lambda: True)
    monkeypatch.setattr(compat.registry, "chat_with_provenance", lambda *_args, **_kwargs: ("OK", "deepseek", []))
    monkeypatch.setattr(compat.registry, "verified_provider", lambda: "deepseek")

    result = compat.login(compat._LoginBody(operator="admin", password=settings.api_access_token))

    assert calls == [settings.api_access_token]
    assert result["ai_smoke"]["ok"] is True
    assert result["ai_smoke"]["source"] == "api"


def test_runtime_status_marks_vault_present_without_unlock(monkeypatch, tmp_path) -> None:
    vault_path = tmp_path / "ai-vault.json"
    vault_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(ai_vault, "default_vault_path", lambda: vault_path)
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    monkeypatch.setattr(settings, "groq_api_key", "")

    status = ai_vault.runtime_status()

    assert status["vault_present"] is True
    assert status["vault_unlocked"] is False


def test_dispatcher_rule_fallback_does_not_mask_central_live_provider(monkeypatch) -> None:
    monkeypatch.setattr(settings, "microservices_enabled", True)
    monkeypatch.setattr(ai.registry, "is_any_live_provider", lambda: True)
    monkeypatch.setattr(ai, "post_json", lambda *_args, **_kwargs: (
        True,
        {
            "root_cause": "local fallback",
            "recommended_action": "observe",
            "need_isolation": False,
            "source": "local-fallback",
        },
    ))

    result = ai.diagnose_via_dispatcher(
        ai.AiDiagnoseRequest(node_code="milling-workshop-01"),
        "test alert",
        "medium",
        None,
    )

    assert result is None
