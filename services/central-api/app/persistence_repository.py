from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from typing import Iterable

from .core.database import get_db, persistence_backend
from .core.config import settings
from .core.nats_contracts import build_heartbeat_envelope
from .core.outbox import outbox_repository
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
                parameters_json, claimed_by, result_message, version, expires_at, dispatched_at,
                received_at, applied_at, verified_at, attempt_count, verification_status,
                verification_baseline_json, verification_evidence_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                version=excluded.version,
                expires_at=excluded.expires_at,
                dispatched_at=excluded.dispatched_at,
                received_at=excluded.received_at,
                applied_at=excluded.applied_at,
                verified_at=excluded.verified_at,
                attempt_count=excluded.attempt_count,
                verification_status=excluded.verification_status,
                verification_baseline_json=excluded.verification_baseline_json,
                verification_evidence_json=excluded.verification_evidence_json,
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
                command.version,
                command.expires_at.isoformat() if command.expires_at else None,
                command.dispatched_at.isoformat() if command.dispatched_at else None,
                command.received_at.isoformat() if command.received_at else None,
                command.applied_at.isoformat() if command.applied_at else None,
                command.verified_at.isoformat() if command.verified_at else None,
                command.attempt_count,
                command.verification_status,
                json.dumps(command.verification_baseline, ensure_ascii=False, sort_keys=True),
                json.dumps(command.verification_evidence, ensure_ascii=False, sort_keys=True),
                command.created_at.isoformat(),
                command.updated_at.isoformat(),
            ),
        )

    @staticmethod
    def _insert_event(db: object, event: IncidentEvent, run_id: str) -> bool:
        durable_run_id = event.run_id or run_id
        source_node = event.source_node or event.node_code
        if persistence_backend() == "postgres":
            db.execute(
                "SELECT pg_advisory_xact_lock(hashtext(?), 0)",
                ("mini-ogas:event-store",),
            )

        existing = db.execute(
            "SELECT local_sequence, global_sequence FROM event_store WHERE event_id = ?",
            (event.event_id,),
        ).fetchone()
        if existing is not None:
            existing_values = dict(existing)
            event.local_sequence = int(existing_values["local_sequence"])
            event.global_sequence = int(existing_values["global_sequence"])
            event.id = event.global_sequence
            return False

        sequence_row = db.execute(
            """SELECT
                   COALESCE(MAX(CASE WHEN source_node = ? AND run_id = ? THEN local_sequence END), 0)
                       AS max_local_sequence,
                   COALESCE(MAX(global_sequence), 0) AS max_global_sequence
               FROM event_store""",
            (source_node, durable_run_id),
        ).fetchone()
        sequences = dict(sequence_row)
        requested_local = int(event.local_sequence or event.id)
        requested_global = int(event.global_sequence or event.id)
        next_local = max(requested_local, int(sequences["max_local_sequence"]) + 1)
        next_global = max(requested_global, int(sequences["max_global_sequence"]) + 1)
        old_event_id = event.id
        old_global_sequence = event.global_sequence or old_event_id
        auto_correlations = {
            "",
            f"{durable_run_id or 'unbound'}:{event.node_code}:{old_event_id}",
            f"{durable_run_id or 'unbound'}:{event.node_code}:{old_global_sequence}",
        }
        event.local_sequence = next_local
        event.global_sequence = next_global
        event.id = next_global
        if event.correlation_id in auto_correlations:
            event.correlation_id = f"{durable_run_id or 'unbound'}:{event.node_code}:{next_global}"

        payload = dict(event.payload)
        payload.setdefault("stage", event.stage)
        payload.setdefault("severity", event.severity.value)
        payload.setdefault("message", event.message)
        db.execute(
            """INSERT INTO event_store (
                   event_id, event_type, schema_version, source_node, event_time, ingest_time,
                   local_sequence, global_sequence, correlation_id, run_id, scenario_id, payload_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(event_id) DO NOTHING""",
            (
                event.event_id,
                event.event_type or event.stage,
                event.schema_version,
                source_node,
                event.event_time.isoformat(),
                event.ingest_time.isoformat(),
                event.local_sequence or event.id,
                event.global_sequence or event.id,
                event.correlation_id or f"{durable_run_id or 'unbound'}:{event.node_code}:{event.id}",
                durable_run_id,
                event.scenario_id,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
            ),
        )
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
        return True

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
    ) -> bool:
        """Commit command state and its audit event in one transaction."""
        with get_db() as db:
            for command in commands:
                if include_base:
                    self._insert_command_base(db, command, run_id)
                self._upsert_command_shadow(db, command, run_id)
            return self._insert_event(db, event, run_id)

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

    def persist_nats_receipt(self, envelope: dict[str, object], subject: str) -> bool:
        """Persist one schema-validated transport receipt without replaying business state."""
        ingested_at = datetime.now(timezone.utc).isoformat()
        with get_db() as db:
            cursor = db.execute(
                """INSERT INTO nats_shadow_receipts (
                       message_id, subject, message_type, source_node, run_id, local_sequence,
                       correlation_id, occurred_at, ingested_at, payload_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(message_id) DO NOTHING""",
                (
                    str(envelope.get("message_id") or ""),
                    subject,
                    str(envelope.get("message_type") or ""),
                    str(envelope.get("node_code") or ""),
                    str(envelope.get("run_id") or ""),
                    int(envelope.get("sequence") or 0),
                    str(envelope.get("correlation_id") or ""),
                    str(envelope.get("occurred_at") or ""),
                    ingested_at,
                    json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                ),
            )
            return int(cursor.rowcount or 0) == 1

    def persist_event(self, event: IncidentEvent, run_id: str) -> bool:
        with get_db() as db:
            return self._insert_event(db, event, run_id)

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
            if settings.nats_enabled:
                outbox_repository.enqueue_in_transaction(
                    db,
                    build_heartbeat_envelope(payload),
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

    def persist_synced_node_records(
        self,
        node_code: str,
        records: list[dict[str, object]],
        *,
        retention_per_node: int,
    ) -> dict[str, int]:
        """Archive offline heartbeats idempotently without changing live projection."""
        accepted = 0
        duplicates = 0
        ingested_at = datetime.now(timezone.utc).isoformat()
        with get_db() as db:
            for record in sorted(records, key=lambda item: int(item.get("local_id") or 0)):
                local_id = int(record.get("local_id") or 0)
                raw_payload = record.get("payload")
                if isinstance(raw_payload, str):
                    try:
                        payload = json.loads(raw_payload)
                    except json.JSONDecodeError as exc:
                        raise ValueError(f"node record {local_id} contains invalid JSON") from exc
                elif isinstance(raw_payload, dict):
                    payload = dict(raw_payload)
                else:
                    raise ValueError(f"node record {local_id} payload must be an object")
                payload_node = str(payload.get("node_code") or node_code)
                if payload_node != node_code:
                    raise ValueError(f"node record {local_id} node_code mismatch")
                runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
                run_id = str(runtime.get("run_id") or "")
                scenario_id = str(runtime.get("scenario_id") or "")
                created_at = str(record.get("created_at") or payload.get("timestamp") or ingested_at)
                canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
                payload_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                existing = db.execute(
                    """SELECT payload_hash FROM node_record_receipts
                       WHERE node_code = ? AND run_id = ? AND local_id = ?""",
                    (node_code, run_id, local_id),
                ).fetchone()
                if existing is not None:
                    if str(dict(existing).get("payload_hash") or "") != payload_hash:
                        raise ValueError(
                            f"node record identity conflict: {node_code}/{run_id or 'unbound'}/{local_id}"
                        )
                    duplicates += 1
                    continue
                db.execute(
                    """INSERT INTO node_record_receipts (
                           node_code, run_id, local_id, payload_hash, payload_created_at, ingested_at
                       ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (node_code, run_id, local_id, payload_hash, created_at, ingested_at),
                )
                archived = {
                    **payload,
                    "node_code": node_code,
                    "_received_at": created_at,
                    "_ingested_at": ingested_at,
                    "_ingest_type": "offline_replay",
                    "_local_id": local_id,
                }
                db.execute(
                    """INSERT INTO heartbeat_shadow (
                           node_code, run_id, scenario_id, simulation_time, payload_json, received_at
                       ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        node_code,
                        run_id,
                        scenario_id,
                        runtime.get("simulation_time"),
                        json.dumps(archived, ensure_ascii=False, sort_keys=True, default=str),
                        created_at,
                    ),
                )
                accepted += 1

            if retention_per_node > 0:
                db.execute(
                    """DELETE FROM heartbeat_shadow
                       WHERE node_code = ? AND id NOT IN (
                           SELECT id FROM heartbeat_shadow
                           WHERE node_code = ? ORDER BY received_at DESC, id DESC LIMIT ?
                       )""",
                    (node_code, node_code, retention_per_node),
                )
        return {"accepted": accepted, "duplicates": duplicates}


central_fact_repository = CentralFactRepository()
