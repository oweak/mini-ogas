from __future__ import annotations

import json
from typing import Iterable

from .core.database import get_db
from .models import AuditLog, IncidentEvent, NodeCommand


class CentralFactRepository:
    """SQL boundary for durable central facts used by the v2.5 projection."""

    @staticmethod
    def _insert_command_base(db: object, command: NodeCommand, run_id: str) -> None:
        db.execute(
            """INSERT INTO commands (run_id, node_code, command_type, risk_level, status, operator, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                command.node_code,
                command.command_type,
                command.risk_level,
                command.status,
                command.operator,
                command.created_at.isoformat(),
            ),
        )

    @staticmethod
    def _upsert_command_shadow(db: object, command: NodeCommand, run_id: str) -> None:
        db.execute(
            """
            INSERT INTO command_shadow (
                command_id, run_id, node_code, command_type, risk_level, status, operator,
                parameters_json, claimed_by, result_message, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(command_id) DO UPDATE SET
                run_id=excluded.run_id,
                node_code=excluded.node_code,
                command_type=excluded.command_type,
                risk_level=excluded.risk_level,
                status=excluded.status,
                operator=excluded.operator,
                parameters_json=excluded.parameters_json,
                claimed_by=excluded.claimed_by,
                result_message=excluded.result_message,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at
            """,
            (
                command.id,
                run_id,
                command.node_code,
                command.command_type,
                command.risk_level,
                command.status,
                command.operator,
                json.dumps(command.parameters, ensure_ascii=False, sort_keys=True),
                command.claimed_by,
                command.result_message,
                command.created_at.isoformat(),
                command.updated_at.isoformat(),
            ),
        )

    @staticmethod
    def _insert_event(db: object, event: IncidentEvent, run_id: str) -> None:
        durable_run_id = event.run_id or run_id
        db.execute(
            """INSERT INTO audit_logs (
                   run_id, actor, action, resource_type, resource_id, result, detail, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                durable_run_id,
                event.node_code,
                event.stage,
                "incident_event",
                str(event.id),
                event.severity.value,
                event.message,
                event.created_at.isoformat(),
            ),
        )

    def persist_command(self, command: NodeCommand, run_id: str, *, include_base: bool) -> None:
        with get_db() as db:
            if include_base:
                self._insert_command_base(db, command, run_id)
            self._upsert_command_shadow(db, command, run_id)

    def persist_command_events(
        self,
        commands: Iterable[NodeCommand],
        event: IncidentEvent,
        run_id: str,
        *,
        include_base: bool = False,
    ) -> None:
        """Commit command state and its audit event in one transaction."""
        with get_db() as db:
            for command in commands:
                if include_base:
                    self._insert_command_base(db, command, run_id)
                self._upsert_command_shadow(db, command, run_id)
            self._insert_event(db, event, run_id)

    def persist_audit(self, audit: AuditLog, run_id: str, detail: str) -> None:
        with get_db() as db:
            db.execute(
                """INSERT INTO audit_logs (
                       run_id, actor, action, resource_type, resource_id, result, detail, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    audit.actor,
                    audit.action,
                    audit.resource_type,
                    audit.resource_id,
                    audit.result,
                    detail,
                    audit.created_at.isoformat(),
                ),
            )

    def persist_event(self, event: IncidentEvent, run_id: str) -> None:
        with get_db() as db:
            self._insert_event(db, event, run_id)

    def persist_heartbeat(self, payload: dict[str, object], *, retention_per_node: int) -> int:
        runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
        received_at = str(payload.get("_received_at") or "")
        run_id = str(runtime.get("run_id") or "")
        scenario_id = str(runtime.get("scenario_id") or "")
        random_seed = int(runtime.get("random_seed") or 0)
        requested_run_status = str(runtime.get("run_status") or "").lower()
        if requested_run_status and requested_run_status not in {"created", "running", "paused", "completed", "failed"}:
            raise ValueError(f"unsupported run status: {requested_run_status}")
        run_status = requested_run_status or (
            "completed" if str(payload.get("status") or "") == "shutting_down" else "running"
        )

        with get_db() as db:
            existing_run = db.execute(
                "SELECT scenario_id, random_seed FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone() if run_id else None
            if existing_run:
                existing = dict(existing_run)
                if str(existing.get("scenario_id") or "") != scenario_id:
                    raise ValueError(f"run {run_id} already belongs to scenario {existing.get('scenario_id')}")
                if int(existing.get("random_seed") or 0) != random_seed:
                    raise ValueError(f"run {run_id} already uses random_seed {existing.get('random_seed')}")

            existing_scenario = db.execute(
                "SELECT random_seed, simulation_engine FROM scenarios WHERE scenario_id = ?",
                (scenario_id,),
            ).fetchone() if scenario_id else None
            if existing_scenario:
                existing = dict(existing_scenario)
                if int(existing.get("random_seed") or 0) != random_seed:
                    raise ValueError(f"scenario {scenario_id} already uses random_seed {existing.get('random_seed')}")
                existing_engine = str(existing.get("simulation_engine") or "")
                incoming_engine = str(runtime.get("simulation_engine") or "")
                if existing_engine and incoming_engine and existing_engine != incoming_engine:
                    raise ValueError(f"scenario {scenario_id} already uses simulation_engine {existing_engine}")

            db.execute(
                """INSERT INTO heartbeat_shadow (
                       node_code, run_id, scenario_id, simulation_time, payload_json, received_at
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    str(payload.get("node_code") or ""),
                    run_id,
                    scenario_id,
                    runtime.get("simulation_time"),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
                    received_at,
                ),
            )
            if scenario_id:
                db.execute(
                    """INSERT INTO scenarios (
                           scenario_id, simulation_engine, random_seed, mode, created_at, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(scenario_id) DO UPDATE SET mode=excluded.mode, updated_at=excluded.updated_at""",
                    (
                        scenario_id,
                        str(runtime.get("simulation_engine") or ""),
                        random_seed,
                        str(runtime.get("simulation_mode") or "normal"),
                        received_at,
                        received_at,
                    ),
                )
            if run_id:
                db.execute(
                    """INSERT INTO runs (
                           run_id, scenario_id, status, random_seed, started_at, last_event_at, ended_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(run_id) DO UPDATE SET
                           status=excluded.status,
                           last_event_at=excluded.last_event_at,
                           ended_at=excluded.ended_at""",
                    (
                        run_id,
                        scenario_id,
                        run_status,
                        random_seed,
                        received_at,
                        received_at,
                        received_at if run_status in {"completed", "failed"} else None,
                    ),
                )

            if retention_per_node <= 0:
                return 0
            cursor = db.execute(
                """DELETE FROM heartbeat_shadow
                   WHERE node_code = ? AND id NOT IN (
                       SELECT id FROM heartbeat_shadow
                       WHERE node_code = ? ORDER BY id DESC LIMIT ?
                   )""",
                (
                    str(payload.get("node_code") or ""),
                    str(payload.get("node_code") or ""),
                    retention_per_node,
                ),
            )
            return max(0, int(getattr(cursor, "rowcount", 0) or 0))


central_fact_repository = CentralFactRepository()
