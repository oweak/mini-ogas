from __future__ import annotations

import sqlite3

import pytest
from app.core.migrations import apply_migrations
from app.core.principal_schema import (
    STAGE_C_PRINCIPAL_MIGRATIONS,
    STAGE_G_AI_SUGGESTION_COMMAND_VERSION,
)


def test_ai_suggestion_command_migration_is_single_use_and_enforces_unique_link() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    try:
        applied = apply_migrations(
            connection,
            "sqlite",
            STAGE_C_PRINCIPAL_MIGRATIONS[:2],
        )
        assert len(applied) == 2
        connection.execute(
            """INSERT INTO principals (
                   principal_id, tenant_id, site_id, principal_type, display_name
               ) VALUES ('ai:test', 'tenant', 'site', 'ai_agent', 'Test AI')"""
        )
        connection.execute(
            """INSERT INTO ai_suggestions (
                   suggestion_id, tenant_id, site_id, principal_id, node_code,
                   risk_level, recommendation, evidence_json, status
               ) VALUES (
                   'ais-1', 'tenant', 'site', 'ai:test', 'node-1',
                   'high', 'First recommendation', '{}', 'pending_human_review'
               )"""
        )

        applied = apply_migrations(
            connection,
            "sqlite",
            STAGE_C_PRINCIPAL_MIGRATIONS,
        )

        assert applied == [STAGE_G_AI_SUGGESTION_COMMAND_VERSION]
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(ai_suggestions)")
        }
        assert {"command_id", "decided_at"}.issubset(columns)
        connection.execute(
            "UPDATE ai_suggestions SET command_id = 42 WHERE suggestion_id = 'ais-1'"
        )
        connection.execute(
            """INSERT INTO ai_suggestions (
                   suggestion_id, tenant_id, site_id, principal_id, node_code,
                   risk_level, recommendation, evidence_json, status
               ) VALUES (
                   'ais-2', 'tenant', 'site', 'ai:test', 'node-1',
                   'high', 'Second recommendation', '{}', 'pending_human_review'
               )"""
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE ai_suggestions SET command_id = 42 WHERE suggestion_id = 'ais-2'"
            )

        assert apply_migrations(
            connection,
            "sqlite",
            STAGE_C_PRINCIPAL_MIGRATIONS,
        ) == []
    finally:
        connection.close()
