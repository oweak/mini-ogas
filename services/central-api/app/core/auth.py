"""Persistent local RBAC and minimal HS256 JWT support.

The dashboard uses bearer tokens issued after a password is verified against
the persistence backend. Machine-to-machine ingestion remains separately
authenticated with NODE_INGEST_TOKEN.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from .config import settings
from .database import get_db, init_db

ALL_PERMISSIONS = (
    "node:view",
    "node:isolate",
    "node:restore",
    "command:approve",
    "command:reject",
    "command:issue",
    "ai:diagnose",
    "metric:ingest",
    "simulation:control",
    "master-data:manage",
    "execution:manage",
    "inventory:manage",
    "quality:manage",
    "quality:measure",
    "quality:release",
    "maintenance:manage",
    "maintenance:execute",
    "maintenance:verify",
    "telemetry:manage",
    "telemetry:ingest",
    "telemetry:read",
    "telemetry:retention",
    "projection:rebuild",
    "document-object:manage",
)

ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "system_admin": ALL_PERMISSIONS,
    "operator": (
        "node:view",
        "command:issue",
        "ai:diagnose",
        "execution:manage",
        "inventory:manage",
        "quality:measure",
        "maintenance:execute",
        "telemetry:read",
    ),
    "quality_engineer": (
        "node:view",
        "quality:manage",
        "quality:measure",
    ),
    "quality_releaser": (
        "node:view",
        "quality:release",
    ),
    "maintenance_planner": (
        "node:view",
        "maintenance:manage",
    ),
    "maintenance_technician": (
        "node:view",
        "maintenance:execute",
    ),
    "maintenance_verifier": (
        "node:view",
        "maintenance:verify",
    ),
    "data_engineer": (
        "node:view",
        "telemetry:manage",
        "telemetry:ingest",
        "telemetry:read",
        "telemetry:retention",
        "projection:rebuild",
        "document-object:manage",
    ),
    "viewer": ("node:view", "telemetry:read"),
}


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    raw_salt = _b64decode(salt) if salt else secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), raw_salt, 310_000)
    return _b64encode(derived), _b64encode(raw_salt)


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    candidate, _ = hash_password(password, salt)
    return secrets.compare_digest(candidate, password_hash)


def initialize_auth_store() -> None:
    """Seed fixed RBAC policy and a first administrator exactly once."""
    init_db()
    with get_db() as db:
        for permission in ALL_PERMISSIONS:
            db.execute(
                "INSERT INTO permissions (name, description) VALUES (?, ?) ON CONFLICT (name) DO NOTHING",
                (permission, permission),
            )
        for role, permissions in ROLE_PERMISSIONS.items():
            db.execute(
                "INSERT INTO roles (name, description) VALUES (?, ?) ON CONFLICT (name) DO NOTHING",
                (role, role.replace("_", " ")),
            )
            for permission in permissions:
                db.execute(
                    """INSERT INTO role_permissions (role_name, permission_name)
                       VALUES (?, ?) ON CONFLICT (role_name, permission_name) DO NOTHING""",
                    (role, permission),
                )

        existing = db.execute(
            "SELECT id FROM users WHERE username = ?", (settings.auth_bootstrap_username,)
        ).fetchone()
        if existing is None:
            bootstrap_password = settings.auth_bootstrap_password
            if not bootstrap_password and settings.app_env != "production":
                bootstrap_password = settings.api_access_token
            if not bootstrap_password:
                raise RuntimeError(
                    "AUTH_BOOTSTRAP_PASSWORD is required to create the first administrator"
                )
            if settings.app_env == "production" and len(bootstrap_password) < 16:
                raise RuntimeError(
                    "AUTH_BOOTSTRAP_PASSWORD must contain at least 16 characters in production"
                )
            password_hash, password_salt = hash_password(bootstrap_password)
            db.execute(
                """INSERT INTO users (username, display_name, password_hash, password_salt, active)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    settings.auth_bootstrap_username,
                    settings.auth_bootstrap_display_name,
                    password_hash,
                    password_salt,
                    True,
                ),
            )
            db.execute(
                """INSERT INTO user_roles (username, role_name)
                   VALUES (?, ?) ON CONFLICT (username, role_name) DO NOTHING""",
                (settings.auth_bootstrap_username, "system_admin"),
            )


def authenticate_user(login_name: str, password: str) -> dict[str, Any] | None:
    if not login_name or not password:
        return None
    # Route-level unit tests and command-line diagnostics can invoke login
    # without FastAPI lifespan. Ensure the auth schema exists in that path too.
    initialize_auth_store()
    with get_db() as db:
        user = db.execute(
            """SELECT username, display_name, password_hash, password_salt, active
               FROM users WHERE username = ? OR display_name = ? LIMIT 1""",
            (login_name, login_name),
        ).fetchone()
        if user is None or not bool(user["active"]):
            return None
        if not verify_password(password, str(user["password_hash"]), str(user["password_salt"])):
            return None
        roles = db.execute(
            "SELECT role_name FROM user_roles WHERE username = ? ORDER BY role_name",
            (user["username"],),
        ).fetchall()
        role_names = [str(row["role_name"]) for row in roles]
        permissions = db.execute(
            """SELECT DISTINCT rp.permission_name
               FROM role_permissions rp
               JOIN user_roles ur ON ur.role_name = rp.role_name
               WHERE ur.username = ? ORDER BY rp.permission_name""",
            (user["username"],),
        ).fetchall()
    return {
        "username": str(user["username"]),
        "display_name": str(user["display_name"]),
        "roles": role_names,
        "permissions": [str(row["permission_name"]) for row in permissions],
    }


def issue_access_token(user: dict[str, Any]) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "iss": "mini-ogas-central-api",
        "sub": user["username"],
        "name": user["display_name"],
        "roles": user["roles"],
        "permissions": user["permissions"],
        "iat": now,
        "exp": now + settings.auth_jwt_ttl_seconds,
        "jti": secrets.token_urlsafe(12),
    }
    signing_input = f"{_b64encode(_json_bytes(header))}.{_b64encode(_json_bytes(payload))}".encode(
        "ascii"
    )
    signature = hmac.new(
        settings.auth_jwt_secret.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    return f"{signing_input.decode('ascii')}.{_b64encode(signature)}"


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        header_raw, payload_raw, signature_raw = token.split(".")
        signing_input = f"{header_raw}.{payload_raw}".encode("ascii")
        expected = hmac.new(
            settings.auth_jwt_secret.encode("utf-8"), signing_input, hashlib.sha256
        ).digest()
        if not secrets.compare_digest(expected, _b64decode(signature_raw)):
            return None
        header = json.loads(_b64decode(header_raw))
        payload = json.loads(_b64decode(payload_raw))
        if header.get("alg") != "HS256" or payload.get("iss") != "mini-ogas-central-api":
            return None
        if int(payload.get("exp", 0)) <= int(time.time()):
            return None
        if not isinstance(payload.get("permissions"), list) or not isinstance(
            payload.get("roles"), list
        ):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return None
