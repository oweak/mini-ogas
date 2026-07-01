"""Create or replace the local Mini-OGAS AI vault.

Inputs are read from environment variables so deploy/reset-ai-vault.ps1 can
collect secrets with SecureString and this script never echoes them.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ai_runtime import encrypt_vault_payload, valid_api_key


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def main() -> None:
    api_key = require_env("MINIOGAS_AI_API_KEY")
    password = require_env("MINIOGAS_VAULT_PASSWORD")
    if not valid_api_key(api_key):
        raise SystemExit("MINIOGAS_AI_API_KEY is empty or looks like a placeholder")

    payload = {
        "provider": os.getenv("MINIOGAS_AI_PROVIDER", "deepseek").strip() or "deepseek",
        "model": os.getenv("MINIOGAS_AI_MODEL", "deepseek-chat").strip() or "deepseek-chat",
        "base_url": os.getenv("MINIOGAS_AI_BASE_URL", "https://api.deepseek.com").strip()
        or "https://api.deepseek.com",
        "api_key": api_key,
    }
    vault_path = Path(os.getenv("MINIOGAS_AI_VAULT_PATH", "secrets/ai-vault.json"))
    vault_path.parent.mkdir(parents=True, exist_ok=True)
    vault_path.write_text(
        json.dumps(encrypt_vault_payload(payload, password), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "ok": True,
        "vault_path": str(vault_path),
        "provider": payload["provider"],
        "model": payload["model"],
        "base_url": payload["base_url"],
        "key_present": True,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
