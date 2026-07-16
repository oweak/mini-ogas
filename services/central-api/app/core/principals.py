from __future__ import annotations

import hashlib
import json
import re
import secrets
from typing import Any

from .config import settings
from .database import get_db

PRINCIPAL_TYPES = {"human", "service", "node", "ai_agent"}
NODE_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _ensure_principal(
    principal_id: str,
    principal_type: str,
    display_name: str,
    *,
    node_code: str | None = None,
) -> None:
    if principal_type not in PRINCIPAL_TYPES:
        raise ValueError(f"unsupported principal_type: {principal_type}")
    with get_db() as db:
        db.execute(
            """INSERT INTO principals (
                   principal_id, tenant_id, site_id, principal_type,
                   display_name, node_code, active
               ) VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(principal_id) DO UPDATE SET
                   display_name = excluded.display_name,
                   node_code = excluded.node_code,
                   updated_at = CURRENT_TIMESTAMP""",
            (
                principal_id,
                settings.tenant_id,
                settings.site_id,
                principal_type,
                display_name,
                node_code,
                True,
            ),
        )


def _assign_role(principal_id: str, role_name: str) -> None:
    with get_db() as db:
        db.execute(
            """INSERT INTO principal_roles (principal_id, role_name)
               VALUES (?, ?) ON CONFLICT(principal_id, role_name) DO NOTHING""",
            (principal_id, role_name),
        )


def sync_human_principal(user: dict[str, Any]) -> None:
    principal_id = f"user:{user['username']}"
    _ensure_principal(
        principal_id,
        "human",
        str(user["display_name"]),
    )
    for role_name in user.get("roles", []):
        _assign_role(principal_id, str(role_name))


def ensure_ai_dispatcher_principal() -> None:
    _ensure_principal("ai:dispatcher", "ai_agent", "AI Dispatcher")
    _assign_role("ai:dispatcher", "ai_agent")


def rotate_node_credential(node_code: str) -> dict[str, str]:
    if not NODE_CODE_PATTERN.fullmatch(node_code):
        raise ValueError("node_code must use 2-64 letters, digits, '.', '_' or '-'")
    principal_id = f"node:{node_code}"
    _ensure_principal(principal_id, "node", node_code, node_code=node_code)
    _assign_role(principal_id, "node_agent")
    token = "mogas_node_" + secrets.token_urlsafe(32)
    credential_id = "cred_" + secrets.token_urlsafe(16)
    with get_db() as db:
        previous = db.execute(
            """SELECT credential_id FROM principal_credentials
               WHERE principal_id = ? AND revoked_at IS NULL
               ORDER BY created_at DESC LIMIT 1""",
            (principal_id,),
        ).fetchone()
        db.execute(
            """UPDATE principal_credentials SET revoked_at = CURRENT_TIMESTAMP
               WHERE principal_id = ? AND revoked_at IS NULL""",
            (principal_id,),
        )
        db.execute(
            """INSERT INTO principal_credentials (
                   credential_id, principal_id, token_hash, rotated_from
               ) VALUES (?, ?, ?, ?)""",
            (
                credential_id,
                principal_id,
                _token_hash(token),
                str(previous["credential_id"]) if previous else None,
            ),
        )
    return {
        "credential_id": credential_id,
        "principal_id": principal_id,
        "principal_type": "node",
        "node_code": node_code,
        "token": token,
    }


def _rotate_nonhuman_credential(
    subject: str,
    *,
    principal_type: str,
    role_name: str,
    token_prefix: str,
) -> dict[str, str]:
    if not NODE_CODE_PATTERN.fullmatch(subject):
        raise ValueError("principal name must use 2-64 letters, digits, '.', '_' or '-'")
    if principal_type not in {"service", "ai_agent"}:
        raise ValueError("nonhuman credential type must be service or ai_agent")
    principal_prefix = "ai" if principal_type == "ai_agent" else "service"
    principal_id = f"{principal_prefix}:{subject}"
    _ensure_principal(principal_id, principal_type, subject)
    _assign_role(principal_id, role_name)
    token = token_prefix + secrets.token_urlsafe(32)
    credential_id = "cred_" + secrets.token_urlsafe(16)
    with get_db() as db:
        previous = db.execute(
            """SELECT credential_id FROM principal_credentials
               WHERE principal_id = ? AND revoked_at IS NULL
               ORDER BY created_at DESC LIMIT 1""",
            (principal_id,),
        ).fetchone()
        db.execute(
            """UPDATE principal_credentials SET revoked_at = CURRENT_TIMESTAMP
               WHERE principal_id = ? AND revoked_at IS NULL""",
            (principal_id,),
        )
        db.execute(
            """INSERT INTO principal_credentials (
                   credential_id, principal_id, token_hash, rotated_from
               ) VALUES (?, ?, ?, ?)""",
            (
                credential_id,
                principal_id,
                _token_hash(token),
                str(previous["credential_id"]) if previous else None,
            ),
        )
    return {
        "credential_id": credential_id,
        "principal_id": principal_id,
        "principal_type": principal_type,
        "node_code": "",
        "token": token,
    }


def rotate_service_credential(service_id: str) -> dict[str, str]:
    return _rotate_nonhuman_credential(
        service_id,
        principal_type="service",
        role_name="service_reader",
        token_prefix="mogas_service_",
    )


def rotate_ai_agent_credential(agent_id: str) -> dict[str, str]:
    return _rotate_nonhuman_credential(
        agent_id,
        principal_type="ai_agent",
        role_name="ai_agent",
        token_prefix="mogas_ai_",
    )


def provision_node_credential(node_code: str, token: str) -> bool:
    if len(token) < 32:
        raise ValueError(f"configured credential for {node_code} must be at least 32 characters")
    if not NODE_CODE_PATTERN.fullmatch(node_code):
        raise ValueError(f"invalid configured node_code: {node_code}")
    principal_id = f"node:{node_code}"
    _ensure_principal(principal_id, "node", node_code, node_code=node_code)
    _assign_role(principal_id, "node_agent")
    with get_db() as db:
        existing = db.execute(
            "SELECT 1 FROM principal_credentials WHERE principal_id = ? LIMIT 1",
            (principal_id,),
        ).fetchone()
        if existing is not None:
            return False
        db.execute(
            """INSERT INTO principal_credentials (
                   credential_id, principal_id, token_hash
               ) VALUES (?, ?, ?)""",
            (
                "cred_" + secrets.token_urlsafe(16),
                principal_id,
                _token_hash(token),
            ),
        )
    return True


def initialize_configured_node_principals() -> list[str]:
    if not settings.node_credentials_json:
        return []
    try:
        configured = json.loads(settings.node_credentials_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError("NODE_CREDENTIALS_JSON is not valid JSON") from exc
    if not isinstance(configured, dict):
        raise RuntimeError("NODE_CREDENTIALS_JSON must contain a JSON object")
    provisioned: list[str] = []
    for node_code, token in configured.items():
        if provision_node_credential(str(node_code), str(token)):
            provisioned.append(str(node_code))
    return provisioned


def revoke_node_credentials(node_code: str) -> int:
    return revoke_principal_credentials(f"node:{node_code}")


def revoke_principal_credentials(principal_id: str) -> int:
    with get_db() as db:
        cursor = db.execute(
            """UPDATE principal_credentials SET revoked_at = CURRENT_TIMESTAMP
               WHERE principal_id = ? AND revoked_at IS NULL""",
            (principal_id,),
        )
        return max(0, int(cursor.rowcount or 0))


def _authenticate_credential(
    token: str,
    allowed_types: set[str],
) -> dict[str, Any] | None:
    if not token:
        return None
    with get_db() as db:
        principal = db.execute(
            """SELECT p.principal_id, p.principal_type, p.display_name, p.node_code,
                      c.credential_id
               FROM principal_credentials c
               JOIN principals p ON p.principal_id = c.principal_id
               WHERE c.token_hash = ?
                 AND c.revoked_at IS NULL
                 AND (c.expires_at IS NULL OR c.expires_at > CURRENT_TIMESTAMP)
                 AND p.active = ?
                 AND p.tenant_id = ? AND p.site_id = ?
               LIMIT 1""",
            (_token_hash(token), True, settings.tenant_id, settings.site_id),
        ).fetchone()
        if principal is None:
            return None
        if str(principal["principal_type"]) not in allowed_types:
            return None
        roles = db.execute(
            "SELECT role_name FROM principal_roles WHERE principal_id = ? ORDER BY role_name",
            (principal["principal_id"],),
        ).fetchall()
        permissions = db.execute(
            """SELECT DISTINCT rp.permission_name
               FROM role_permissions rp
               JOIN principal_roles pr ON pr.role_name = rp.role_name
               WHERE pr.principal_id = ? ORDER BY rp.permission_name""",
            (principal["principal_id"],),
        ).fetchall()
    role_names = [str(row["role_name"]) for row in roles]
    return {
        "principal_id": str(principal["principal_id"]),
        "principal_type": str(principal["principal_type"]),
        "username": str(principal["principal_id"]),
        "display_name": str(principal["display_name"]),
        "role": role_names[0] if role_names else "node_agent",
        "roles": role_names,
        "permissions": {str(row["permission_name"]) for row in permissions},
        "node_code": str(principal["node_code"] or ""),
        "credential_id": str(principal["credential_id"]),
    }


def authenticate_node_credential(token: str) -> dict[str, Any] | None:
    return _authenticate_credential(token, {"node"})


def authenticate_bearer_credential(token: str) -> dict[str, Any] | None:
    return _authenticate_credential(token, {"service", "ai_agent"})
