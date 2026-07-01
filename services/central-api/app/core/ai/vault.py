"""Runtime AI vault integration for central-api."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_runtime import decrypt_vault_payload, valid_api_key

from ..config import PROJECT_ROOT, settings


def default_vault_path() -> Path:
    configured = Path(settings.central_db_path).parent / "ai-vault.json"
    legacy = PROJECT_ROOT / "services" / "central-api" / "secrets" / "ai-vault.json"
    if configured.exists():
        return configured
    return legacy


def vault_present() -> bool:
    return default_vault_path().exists()


def env_provider_configured() -> bool:
    return valid_api_key(settings.deepseek_api_key) or valid_api_key(settings.groq_api_key)


def load_vault_payload(password: str) -> dict[str, Any]:
    path = default_vault_path()
    if not path.exists():
        raise ValueError("ai_vault_missing")
    vault = json.loads(path.read_text(encoding="utf-8"))
    payload = decrypt_vault_payload(vault, password)
    if str(payload.get("provider", "")).strip().lower() != "deepseek":
        raise ValueError("unsupported_ai_vault_provider")
    if not valid_api_key(str(payload.get("api_key", ""))):
        raise ValueError("ai_vault_key_missing")
    return payload


def unlock_ai_runtime(password: str) -> dict[str, str]:
    payload = load_vault_payload(password)
    settings.deepseek_api_key = str(payload["api_key"])
    settings.deepseek_base_url = str(payload.get("base_url") or settings.deepseek_base_url).rstrip("/")
    settings.deepseek_model = str(payload.get("model") or settings.deepseek_model)
    from .registry import registry

    registry.reload()
    return {
        "provider": "deepseek",
        "model": settings.deepseek_model,
        "base_url": settings.deepseek_base_url,
    }


def runtime_status(*, verified_provider: str | None = None) -> dict[str, object]:
    from .registry import registry

    configured = registry.is_any_live_provider()
    active = registry.first_available()
    provider = verified_provider or (active.name if active else "rule_fallback")
    source = "api" if verified_provider else "configured" if configured else "rule_fallback"
    return {
        "status": "live" if verified_provider else "configured" if configured and settings.ai_enabled else "rule_fallback",
        "provider": provider,
        "model": settings.deepseek_model,
        "source": source,
        "vault_present": vault_present() or env_provider_configured(),
        "vault_unlocked": bool(verified_provider or env_provider_configured()),
    }
