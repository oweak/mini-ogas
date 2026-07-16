from __future__ import annotations

import json
from typing import Any

from ..core.database import get_db


class AiSuggestionRepository:
    def create(
        self,
        *,
        suggestion_id: str,
        tenant_id: str,
        site_id: str,
        principal_id: str,
        node_code: str,
        risk_level: str,
        recommendation: str,
        evidence: dict[str, Any],
        status: str,
        command_id: int | None,
    ) -> None:
        with get_db() as db:
            db.execute(
                """INSERT INTO ai_suggestions (
                       suggestion_id, tenant_id, site_id, principal_id, node_code,
                       risk_level, recommendation, evidence_json, status, command_id
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    suggestion_id,
                    tenant_id,
                    site_id,
                    principal_id,
                    node_code,
                    risk_level,
                    recommendation,
                    json.dumps(evidence, ensure_ascii=False, sort_keys=True),
                    status,
                    command_id,
                ),
            )

    def set_status_for_command(self, command_id: int, status: str) -> str | None:
        if status not in {"accepted", "rejected"}:
            raise ValueError(f"unsupported AI suggestion status: {status}")
        with get_db() as db:
            row = db.execute(
                "SELECT suggestion_id FROM ai_suggestions WHERE command_id = ?",
                (command_id,),
            ).fetchone()
            if row is None:
                return None
            db.execute(
                """UPDATE ai_suggestions
                   SET status = ?, decided_at = CURRENT_TIMESTAMP
                   WHERE command_id = ?""",
                (status, command_id),
            )
            return str(row["suggestion_id"])

    def find_by_command(self, command_id: int) -> dict[str, Any] | None:
        with get_db() as db:
            row = db.execute(
                """SELECT suggestion_id, principal_id, node_code, risk_level,
                          recommendation, evidence_json, status, command_id,
                          created_at, decided_at
                   FROM ai_suggestions WHERE command_id = ?""",
                (command_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        try:
            evidence = json.loads(result.pop("evidence_json") or "{}")
        except json.JSONDecodeError:
            evidence = {}
        result["evidence"] = evidence if isinstance(evidence, dict) else {}
        return result


ai_suggestion_repository = AiSuggestionRepository()
