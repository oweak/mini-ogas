from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime

from ..core.database import get_db
from ..models import IncidentEvent, NodeCommand
from ..persistence_repository import central_fact_repository


def _database_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


class CommandRepository:
    """Own the rebuildable command projection and its durable SQL boundary."""

    def __init__(self) -> None:
        self._projection: list[NodeCommand] = []

    @property
    def commands(self) -> list[NodeCommand]:
        return self._projection

    def replace_projection(self, commands: Iterable[NodeCommand]) -> None:
        self._projection[:] = list(commands)[-100:]

    def persist(self, command: NodeCommand, run_id: str, *, include_base: bool) -> None:
        central_fact_repository.persist_command(
            command,
            run_id,
            include_base=include_base,
        )

    def persist_with_event(
        self,
        commands: Iterable[NodeCommand],
        event: IncidentEvent,
        run_id: str,
        *,
        include_base: bool = False,
    ) -> bool:
        return central_fact_repository.persist_command_events(
            commands,
            event,
            run_id,
            include_base=include_base,
        )

    def load_projection(self) -> int:
        with get_db() as db:
            rows = db.execute(
                """
                SELECT command_id, node_code, command_type, risk_level, status, operator,
                       parameters_json, claimed_by, result_message, version, expires_at,
                       dispatched_at, received_at, applied_at, verified_at, attempt_count,
                       verification_status, verification_baseline_json,
                       verification_evidence_json, created_at, updated_at
                FROM command_shadow
                ORDER BY command_id ASC
                """
            ).fetchall()

        loaded: list[NodeCommand] = []
        for row in rows:
            data = dict(row)
            try:
                parameters = json.loads(data.get("parameters_json") or "{}")
            except json.JSONDecodeError:
                parameters = {}
            try:
                verification_baseline = json.loads(
                    data.get("verification_baseline_json") or "{}"
                )
                verification_evidence = json.loads(
                    data.get("verification_evidence_json") or "{}"
                )
            except json.JSONDecodeError:
                verification_baseline = {}
                verification_evidence = {}
            loaded.append(
                NodeCommand(
                    id=int(data["command_id"]),
                    node_code=data["node_code"],
                    command_type=data["command_type"],
                    risk_level=data["risk_level"],
                    status=data["status"],
                    operator=data["operator"],
                    parameters=parameters if isinstance(parameters, dict) else {},
                    claimed_by=data.get("claimed_by") or "",
                    result_message=data.get("result_message") or "",
                    version=int(data.get("version") or 1),
                    expires_at=(
                        _database_datetime(data["expires_at"])
                        if data.get("expires_at")
                        else None
                    ),
                    dispatched_at=(
                        _database_datetime(data["dispatched_at"])
                        if data.get("dispatched_at")
                        else None
                    ),
                    received_at=(
                        _database_datetime(data["received_at"])
                        if data.get("received_at")
                        else None
                    ),
                    applied_at=(
                        _database_datetime(data["applied_at"])
                        if data.get("applied_at")
                        else None
                    ),
                    verified_at=(
                        _database_datetime(data["verified_at"])
                        if data.get("verified_at")
                        else None
                    ),
                    attempt_count=int(data.get("attempt_count") or 0),
                    verification_status=str(
                        data.get("verification_status") or "not_started"
                    ),
                    verification_baseline=(
                        verification_baseline
                        if isinstance(verification_baseline, dict)
                        else {}
                    ),
                    verification_evidence=(
                        verification_evidence
                        if isinstance(verification_evidence, dict)
                        else {}
                    ),
                    created_at=_database_datetime(data["created_at"]),
                    updated_at=_database_datetime(
                        data.get("updated_at") or data["created_at"]
                    ),
                )
            )
        self.replace_projection(loaded)
        return len(loaded)
