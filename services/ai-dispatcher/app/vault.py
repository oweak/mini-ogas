from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any

PLACEHOLDER_KEYS = frozenset(
    {
        "",
        "replace-me",
        "replace_me",
        "replace-with-your-key",
        "your-key",
        "your_api_key",
        "changeme",
        "sk-your-key",
    }
)
VAULT_VERSION = "miniogas-vault-v1"


def valid_api_key(value: str) -> bool:
    lowered = value.strip().lower()
    return bool(lowered) and lowered not in PLACEHOLDER_KEYS and "your" not in lowered


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def _derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 240_000, dklen=32)


def _keystream(key: bytes, nonce: bytes, size: int) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < size:
        output.extend(hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
        counter += 1
    return bytes(output[:size])


def _xor(data: bytes, key: bytes, nonce: bytes) -> bytes:
    stream = _keystream(key, nonce, len(data))
    return bytes(left ^ right for left, right in zip(data, stream, strict=True))


def encrypt_vault_payload(payload: dict[str, Any], password: str) -> dict[str, str]:
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(16)
    key = _derive_key(password, salt)
    plaintext = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    ciphertext = _xor(plaintext, key, nonce)
    mac = hmac.new(
        key,
        VAULT_VERSION.encode("ascii") + salt + nonce + ciphertext,
        hashlib.sha256,
    ).digest()
    return {
        "version": VAULT_VERSION,
        "kdf": "pbkdf2-sha256-240000",
        "salt": _b64encode(salt),
        "nonce": _b64encode(nonce),
        "ciphertext": _b64encode(ciphertext),
        "mac": _b64encode(mac),
    }


def decrypt_vault_payload(vault: dict[str, Any], password: str) -> dict[str, Any]:
    if vault.get("version") != VAULT_VERSION:
        raise ValueError("unsupported_vault_version")
    salt = _b64decode(str(vault["salt"]))
    nonce = _b64decode(str(vault["nonce"]))
    ciphertext = _b64decode(str(vault["ciphertext"]))
    expected_mac = _b64decode(str(vault["mac"]))
    key = _derive_key(password, salt)
    actual_mac = hmac.new(
        key,
        VAULT_VERSION.encode("ascii") + salt + nonce + ciphertext,
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(actual_mac, expected_mac):
        raise ValueError("invalid_password_or_vault")
    return json.loads(_xor(ciphertext, key, nonce).decode("utf-8"))


def _project_root(module_path: Path) -> Path | None:
    for parent in module_path.resolve().parents:
        if (parent / ".git").exists() or (parent / "docker-compose.yml").exists():
            return parent
    return None


def vault_candidates(module_path: Path | None = None) -> list[Path]:
    explicit = os.getenv("AI_VAULT_PATH", "").strip()
    if explicit:
        return [Path(explicit).expanduser()]
    root = _project_root(module_path or Path(__file__))
    if root is None:
        return [Path("/run/secrets/ai-vault.json")]
    return [
        root / "services" / "ai-dispatcher" / "secrets" / "ai-vault.json",
        root / "services" / "central-api" / "secrets" / "ai-vault.json",
    ]


def vault_path(module_path: Path | None = None) -> Path:
    candidates = vault_candidates(module_path)
    return next((candidate for candidate in candidates if candidate.is_file()), candidates[0])


def vault_present() -> bool:
    return any(candidate.is_file() for candidate in vault_candidates())


def load_vault_payload(password: str) -> dict[str, str]:
    path = vault_path()
    if not path.is_file():
        raise ValueError("ai_vault_missing")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        payload = decrypt_vault_payload(raw, password)
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_ai_vault") from exc
    provider = str(payload.get("provider", "")).strip().lower()
    api_key = str(payload.get("api_key", "")).strip()
    if provider not in {"deepseek", "groq"}:
        raise ValueError("unsupported_ai_vault_provider")
    if not valid_api_key(api_key):
        raise ValueError("ai_vault_key_missing")
    return {
        "provider": provider,
        "model": str(payload.get("model") or "").strip(),
        "base_url": str(payload.get("base_url") or "").strip().rstrip("/"),
        "api_key": api_key,
    }
