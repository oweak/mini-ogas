"""Local AI vault helpers.

The vault format is intentionally dependency-free so the project can create
and unlock an API-key vault before optional packages are installed. It is an
authenticated password-derived stream cipher, suitable for the local lab
threat model where the goal is to keep keys out of source files and logs.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import urllib.error
import urllib.request
from typing import Any


PLACEHOLDER_KEYS = frozenset({"", "replace-me", "your-key", "your_api_key", "changeme", "sk-your-key"})
VAULT_VERSION = "miniogas-vault-v1"


class AiTransportError(RuntimeError):
    """AI provider call failed before a valid JSON response was returned."""


def env_value(name: str) -> str:
    return os.getenv(name, "").strip()


def valid_api_key(value: str) -> bool:
    lowered = value.strip().lower()
    return bool(lowered) and lowered not in PLACEHOLDER_KEYS and "your" not in lowered


def b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii")


def b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def derive_vault_key(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 240_000, dklen=32)


def vault_keystream(key: bytes, nonce: bytes, size: int) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < size:
        output.extend(hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
        counter += 1
    return bytes(output[:size])


def vault_xor(data: bytes, key: bytes, nonce: bytes) -> bytes:
    stream = vault_keystream(key, nonce, len(data))
    return bytes(left ^ right for left, right in zip(data, stream))


def encrypt_vault_payload(payload: dict[str, Any], password: str) -> dict[str, str]:
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(16)
    key = derive_vault_key(password, salt)
    plaintext = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    ciphertext = vault_xor(plaintext, key, nonce)
    mac = hmac.new(key, VAULT_VERSION.encode("ascii") + salt + nonce + ciphertext, hashlib.sha256).digest()
    return {
        "version": VAULT_VERSION,
        "kdf": "pbkdf2-sha256-240000",
        "salt": b64encode(salt),
        "nonce": b64encode(nonce),
        "ciphertext": b64encode(ciphertext),
        "mac": b64encode(mac),
    }


def decrypt_vault_payload(vault: dict[str, Any], password: str) -> dict[str, Any]:
    if vault.get("version") != VAULT_VERSION:
        raise ValueError("unsupported_vault_version")
    salt = b64decode(str(vault["salt"]))
    nonce = b64decode(str(vault["nonce"]))
    ciphertext = b64decode(str(vault["ciphertext"]))
    expected_mac = b64decode(str(vault["mac"]))
    key = derive_vault_key(password, salt)
    actual_mac = hmac.new(key, VAULT_VERSION.encode("ascii") + salt + nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(actual_mac, expected_mac):
        raise ValueError("invalid_password_or_vault")
    plaintext = vault_xor(ciphertext, key, nonce)
    return json.loads(plaintext.decode("utf-8"))


def normalize_confidence(value: object) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    text = str(value).strip().lower()
    if not text:
        return 0.5
    if text.endswith("%"):
        try:
            return max(0.0, min(1.0, float(text[:-1].strip()) / 100))
        except ValueError:
            return 0.5
    labels = {
        "high": 0.85,
        "medium-high": 0.75,
        "medium": 0.6,
        "low": 0.35,
    }
    if text in labels:
        return labels[text]
    try:
        return max(0.0, min(1.0, float(text)))
    except ValueError:
        return 0.5


def chat_completion_json(
    config: dict[str, Any],
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.2,
    timeout_sec: float | None = 20,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": config["model"],
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    request = urllib.request.Request(
        f"{config['base_url'].rstrip('/')}/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise AiTransportError("model_response_was_not_json_object")
        return parsed
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError, ValueError, TimeoutError) as error:
        raise AiTransportError(str(error)) from error
