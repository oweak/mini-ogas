from __future__ import annotations

from typing import Any

from .migrations import Migration

STAGE_C_PRINCIPAL_VERSION = "2026.07.15-stage-c-principals"
STAGE_C_AI_SUGGESTION_VERSION = "2026.07.15-stage-c-ai-suggestions-v2"
STAGE_G_AI_SUGGESTION_COMMAND_VERSION = "2026.07.16-stage-g-ai-suggestion-command-v1"


def _sqlite_principals(connection: Any) -> None:
    statements = (
        """CREATE TABLE IF NOT EXISTS principals (
               principal_id TEXT PRIMARY KEY,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               principal_type TEXT NOT NULL
                   CHECK (principal_type IN ('human','service','node','ai_agent')),
               display_name TEXT NOT NULL,
               node_code TEXT,
               active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
               created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
               updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
               UNIQUE (tenant_id, site_id, node_code)
           )""",
        """CREATE TABLE IF NOT EXISTS principal_roles (
               principal_id TEXT NOT NULL REFERENCES principals(principal_id) ON DELETE CASCADE,
               role_name TEXT NOT NULL REFERENCES roles(name) ON DELETE CASCADE,
               PRIMARY KEY (principal_id, role_name)
           )""",
        """CREATE TABLE IF NOT EXISTS principal_credentials (
               credential_id TEXT PRIMARY KEY,
               principal_id TEXT NOT NULL REFERENCES principals(principal_id) ON DELETE CASCADE,
               token_hash TEXT NOT NULL UNIQUE,
               created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
               expires_at TEXT,
               revoked_at TEXT,
               rotated_from TEXT REFERENCES principal_credentials(credential_id)
           )""",
        (
            "CREATE INDEX IF NOT EXISTS idx_principal_credentials_active "
            "ON principal_credentials(token_hash, revoked_at)"
        ),
    )
    for statement in statements:
        connection.execute(statement)


def _postgres_principals(connection: Any) -> None:
    statements = (
        """CREATE TABLE IF NOT EXISTS principals (
               principal_id TEXT PRIMARY KEY,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               principal_type TEXT NOT NULL
                   CHECK (principal_type IN ('human','service','node','ai_agent')),
               display_name TEXT NOT NULL,
               node_code TEXT,
               active BOOLEAN NOT NULL DEFAULT TRUE,
               created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
               updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
               UNIQUE (tenant_id, site_id, node_code)
           )""",
        """CREATE TABLE IF NOT EXISTS principal_roles (
               principal_id TEXT NOT NULL REFERENCES principals(principal_id) ON DELETE CASCADE,
               role_name TEXT NOT NULL REFERENCES roles(name) ON DELETE CASCADE,
               PRIMARY KEY (principal_id, role_name)
           )""",
        """CREATE TABLE IF NOT EXISTS principal_credentials (
               credential_id TEXT PRIMARY KEY,
               principal_id TEXT NOT NULL REFERENCES principals(principal_id) ON DELETE CASCADE,
               token_hash TEXT NOT NULL UNIQUE,
               created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
               expires_at TIMESTAMPTZ,
               revoked_at TIMESTAMPTZ,
               rotated_from TEXT REFERENCES principal_credentials(credential_id)
           )""",
        (
            "CREATE INDEX IF NOT EXISTS idx_principal_credentials_active "
            "ON principal_credentials(token_hash, revoked_at)"
        ),
    )
    for statement in statements:
        connection.execute(statement)


def _sqlite_ai_suggestions(connection: Any) -> None:
    connection.execute(
        """CREATE TABLE IF NOT EXISTS ai_suggestions (
               suggestion_id TEXT PRIMARY KEY,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               principal_id TEXT NOT NULL REFERENCES principals(principal_id),
               node_code TEXT NOT NULL,
               risk_level TEXT NOT NULL CHECK (risk_level IN ('low','medium','high','critical')),
               recommendation TEXT NOT NULL,
               evidence_json TEXT NOT NULL,
               status TEXT NOT NULL CHECK (
                   status IN ('submitted','pending_human_review','accepted','rejected')
               ),
               created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
           )"""
    )


def _postgres_ai_suggestions(connection: Any) -> None:
    connection.execute(
        """CREATE TABLE IF NOT EXISTS ai_suggestions (
               suggestion_id TEXT PRIMARY KEY,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               principal_id TEXT NOT NULL REFERENCES principals(principal_id),
               node_code TEXT NOT NULL,
               risk_level TEXT NOT NULL CHECK (risk_level IN ('low','medium','high','critical')),
               recommendation TEXT NOT NULL,
               evidence_json TEXT NOT NULL,
               status TEXT NOT NULL CHECK (
                   status IN ('submitted','pending_human_review','accepted','rejected')
               ),
               created_at TIMESTAMPTZ NOT NULL DEFAULT now()
           )"""
    )


def _sqlite_ai_suggestion_command(connection: Any) -> None:
    connection.execute("ALTER TABLE ai_suggestions ADD COLUMN command_id INTEGER")
    connection.execute("ALTER TABLE ai_suggestions ADD COLUMN decided_at TEXT")
    connection.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_suggestions_command_id
           ON ai_suggestions(command_id) WHERE command_id IS NOT NULL"""
    )


def _postgres_ai_suggestion_command(connection: Any) -> None:
    connection.execute(
        "ALTER TABLE ai_suggestions ADD COLUMN IF NOT EXISTS command_id BIGINT"
    )
    connection.execute(
        "ALTER TABLE ai_suggestions ADD COLUMN IF NOT EXISTS decided_at TIMESTAMPTZ"
    )
    connection.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_suggestions_command_id
           ON ai_suggestions(command_id) WHERE command_id IS NOT NULL"""
    )


STAGE_C_PRINCIPAL_MIGRATIONS = [
    Migration(
        version=STAGE_C_PRINCIPAL_VERSION,
        description="Unified principals and revocable credential ledger",
        checksum_material="principals-v1:human-service-node-ai-agent:sha256-opaque-credentials",
        sqlite_action=_sqlite_principals,
        postgres_action=_postgres_principals,
    ),
    Migration(
        version=STAGE_C_AI_SUGGESTION_VERSION,
        description="Persist AI Agent suggestions without direct control authority",
        checksum_material="ai-suggestions-v1:principal-node:risk:evidence:human-review",
        sqlite_action=_sqlite_ai_suggestions,
        postgres_action=_postgres_ai_suggestions,
    ),
    Migration(
        version=STAGE_G_AI_SUGGESTION_COMMAND_VERSION,
        description="Link high-risk AI suggestions to canonical approval commands",
        checksum_material="ai-suggestions-v3:command-id:decision-timestamp:unique-link",
        sqlite_action=_sqlite_ai_suggestion_command,
        postgres_action=_postgres_ai_suggestion_command,
    ),
]
