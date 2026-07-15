from __future__ import annotations

import json
import threading
from datetime import datetime

from ..core.database import get_db
from ..models import AiDiagnosis, Alert, AuditLog, IncidentEvent, Severity
from ..persistence_repository import central_fact_repository


def _database_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


class IncidentRepository:
    """Own rebuildable incident, audit, event, and AI evidence projections."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.alerts: list[Alert] = []
        self.audit_logs: list[AuditLog] = []
        self.events: list[IncidentEvent] = []
        self.ai_diagnoses: list[AiDiagnosis] = []
        self.incident_event_seq = 0
        self.node_event_sequences: dict[tuple[str, str], int] = {}
        self.shadow_event_count = 0

    def append_event(
        self,
        *,
        node_code: str,
        stage: str,
        severity: Severity,
        message: str,
        run_id: str,
        scenario_id: str,
        occurred_at: datetime,
    ) -> IncidentEvent:
        with self._lock:
            self.incident_event_seq += 1
            global_sequence = self.incident_event_seq
            sequence_key = (node_code, run_id)
            local_sequence = self.node_event_sequences.get(sequence_key, 0) + 1
            self.node_event_sequences[sequence_key] = local_sequence
            event = IncidentEvent(
                id=global_sequence,
                node_code=node_code,
                stage=stage,
                severity=severity,
                message=message,
                run_id=run_id,
                event_type=stage,
                source_node=node_code,
                event_time=occurred_at,
                ingest_time=occurred_at,
                local_sequence=local_sequence,
                global_sequence=global_sequence,
                correlation_id=f"{run_id or 'unbound'}:{node_code}:{global_sequence}",
                scenario_id=scenario_id,
                payload={
                    "stage": stage,
                    "severity": severity.value,
                    "message": message,
                },
                created_at=occurred_at,
            )
            self.events.append(event)
            self.events[:] = self.events[-160:]
            return event

    def note_persisted_event(self, event: IncidentEvent, *, inserted: bool) -> None:
        with self._lock:
            sequence_key = (event.source_node or event.node_code, event.run_id)
            self.node_event_sequences[sequence_key] = max(
                self.node_event_sequences.get(sequence_key, 0),
                event.local_sequence,
            )
            self.incident_event_seq = max(
                self.incident_event_seq,
                event.id,
                event.global_sequence,
            )
            if inserted:
                self.shadow_event_count += 1

    def note_persisted_audit(self) -> None:
        with self._lock:
            self.shadow_event_count += 1

    def persist_alert(self, alert: Alert, run_id: str) -> None:
        with get_db() as db:
            db.execute(
                """INSERT INTO alerts (
                       id, run_id, node_code, alert_type, severity, source,
                       description, handled_by, status, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                       run_id=excluded.run_id,
                       node_code=excluded.node_code,
                       alert_type=excluded.alert_type,
                       severity=excluded.severity,
                       source=excluded.source,
                       description=excluded.description,
                       handled_by=excluded.handled_by,
                       status=excluded.status,
                       created_at=excluded.created_at""",
                (
                    alert.id,
                    run_id,
                    alert.node_code,
                    alert.alert_type,
                    alert.severity.value,
                    alert.source,
                    alert.description,
                    alert.handled_by,
                    alert.status,
                    alert.created_at.isoformat(),
                ),
            )

    def update_alert_state(self, alert: Alert) -> None:
        with get_db() as db:
            cursor = db.execute(
                """UPDATE alerts
                   SET handled_by = ?, status = ?,
                       resolved_at = CASE
                           WHEN ? IN ('closed', 'resolved') THEN CURRENT_TIMESTAMP
                           ELSE resolved_at
                       END
                   WHERE id = ?""",
                (alert.handled_by, alert.status, alert.status, alert.id),
            )
            if int(getattr(cursor, "rowcount", 0) or 0) != 1:
                raise RuntimeError(f"alert state update matched no row: {alert.id}")

    def load_alerts(self) -> list[Alert]:
        with get_db() as db:
            rows = db.execute(
                """SELECT id, run_id, node_code, alert_type, severity, source,
                          description, handled_by, status, created_at
                   FROM alerts
                   ORDER BY created_at ASC, id ASC"""
            ).fetchall()
        loaded: list[Alert] = []
        for row in rows:
            data = dict(row)
            try:
                severity = Severity(str(data.get("severity") or Severity.medium.value))
            except ValueError:
                severity = Severity.medium
            loaded.append(
                Alert(
                    id=int(data["id"]),
                    run_id=str(data.get("run_id") or ""),
                    node_code=str(data["node_code"]),
                    alert_type=str(data["alert_type"]),
                    severity=severity,
                    description=str(data.get("description") or ""),
                    source=str(data.get("source") or "central-api"),
                    handled_by=data.get("handled_by"),
                    status=str(data.get("status") or "open"),
                    created_at=_database_datetime(data["created_at"]),
                )
            )
        return loaded

    def persist_audit(self, audit: AuditLog, run_id: str, detail: str) -> None:
        central_fact_repository.persist_audit(audit, run_id, detail)
        self.note_persisted_audit()

    def persist_event(self, event: IncidentEvent, run_id: str) -> bool:
        inserted = central_fact_repository.persist_event(event, run_id)
        self.note_persisted_event(event, inserted=inserted)
        return inserted

    def persist_ai_diagnosis(self, diagnosis: AiDiagnosis, run_id: str) -> None:
        with get_db() as db:
            db.execute(
                """INSERT INTO ai_diagnosis (
                       id, run_id, alert_id, severity, node_code, root_cause,
                       recommended_action, confidence, need_isolation, model_name,
                       raw_response, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                       run_id=excluded.run_id,
                       alert_id=excluded.alert_id,
                       severity=excluded.severity,
                       node_code=excluded.node_code,
                       root_cause=excluded.root_cause,
                       recommended_action=excluded.recommended_action,
                       confidence=excluded.confidence,
                       need_isolation=excluded.need_isolation,
                       model_name=excluded.model_name,
                       raw_response=excluded.raw_response,
                       created_at=excluded.created_at""",
                (
                    diagnosis.id,
                    run_id,
                    diagnosis.alert_id,
                    Severity.medium.value,
                    diagnosis.node_code,
                    diagnosis.root_cause,
                    diagnosis.recommended_action,
                    diagnosis.confidence,
                    bool(diagnosis.need_isolation),
                    diagnosis.model_name,
                    diagnosis.raw_response,
                    diagnosis.created_at.isoformat(),
                ),
            )

    def load_ai_diagnoses(self) -> list[AiDiagnosis]:
        with get_db() as db:
            rows = db.execute(
                """SELECT id, alert_id, node_code, root_cause, recommended_action,
                          confidence, need_isolation, model_name, raw_response, created_at
                   FROM ai_diagnosis
                   ORDER BY created_at ASC, id ASC"""
            ).fetchall()
        return [
            AiDiagnosis(
                id=int(data["id"]),
                alert_id=int(data.get("alert_id") or 0),
                node_code=str(data.get("node_code") or ""),
                model_name=str(data.get("model_name") or "deepseek"),
                root_cause=str(data.get("root_cause") or ""),
                recommended_action=str(data.get("recommended_action") or ""),
                confidence=float(data.get("confidence") or 0),
                need_isolation=bool(data.get("need_isolation")),
                raw_response=str(data.get("raw_response") or ""),
                created_at=_database_datetime(data["created_at"]),
            )
            for data in (dict(row) for row in rows)
        ]

    def load_audits_and_events(self) -> tuple[list[AuditLog], list[IncidentEvent]]:
        with get_db() as db:
            audit_rows = db.execute(
                """SELECT id, run_id, actor, action, resource_type, resource_id,
                          result, detail, created_at
                   FROM audit_logs
                   ORDER BY created_at ASC, id ASC"""
            ).fetchall()
            event_rows = db.execute(
                """SELECT event_id, event_type, schema_version, source_node, event_time,
                          ingest_time, local_sequence, global_sequence, correlation_id,
                          run_id, scenario_id, payload_json
                   FROM event_store
                   ORDER BY global_sequence ASC"""
            ).fetchall()

        audits: list[AuditLog] = []
        events: list[IncidentEvent] = []
        for row in audit_rows:
            data = dict(row)
            created_at = _database_datetime(data["created_at"])
            audits.append(
                AuditLog(
                    id=int(data["id"]),
                    actor=str(data.get("actor") or ""),
                    action=str(data.get("action") or ""),
                    resource_type=str(data.get("resource_type") or ""),
                    resource_id=str(data.get("resource_id") or ""),
                    result=str(data.get("result") or ""),
                    created_at=created_at,
                )
            )
            if not event_rows and str(data.get("resource_type") or "") == "incident_event":
                try:
                    severity = Severity(str(data.get("result") or Severity.info.value))
                except ValueError:
                    severity = Severity.info
                events.append(
                    IncidentEvent(
                        id=int(data["id"]),
                        node_code=str(data.get("actor") or ""),
                        stage=str(data.get("action") or ""),
                        severity=severity,
                        message=str(data.get("detail") or ""),
                        run_id=str(data.get("run_id") or ""),
                        created_at=created_at,
                    )
                )
        for row in event_rows:
            data = dict(row)
            try:
                payload = json.loads(str(data.get("payload_json") or "{}"))
            except json.JSONDecodeError:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            try:
                severity = Severity(str(payload.get("severity") or Severity.info.value))
            except ValueError:
                severity = Severity.info
            event_time = _database_datetime(data["event_time"])
            events.append(
                IncidentEvent(
                    id=int(data.get("global_sequence") or 0),
                    node_code=str(data.get("source_node") or ""),
                    stage=str(payload.get("stage") or data.get("event_type") or ""),
                    severity=severity,
                    message=str(payload.get("message") or ""),
                    run_id=str(data.get("run_id") or ""),
                    event_id=str(data.get("event_id") or ""),
                    event_type=str(data.get("event_type") or ""),
                    schema_version=str(data.get("schema_version") or "2.5"),
                    source_node=str(data.get("source_node") or ""),
                    event_time=event_time,
                    ingest_time=_database_datetime(data["ingest_time"]),
                    local_sequence=int(data.get("local_sequence") or 0),
                    global_sequence=int(data.get("global_sequence") or 0),
                    correlation_id=str(data.get("correlation_id") or ""),
                    scenario_id=str(data.get("scenario_id") or ""),
                    payload=payload,
                    created_at=event_time,
                )
            )
        return audits, events

    def replace_alerts(self, alerts: list[Alert]) -> None:
        with self._lock:
            self.alerts[:] = alerts[-120:]

    def replace_audits(self, audits: list[AuditLog]) -> None:
        with self._lock:
            self.audit_logs[:] = audits[-300:]

    def replace_events(self, events: list[IncidentEvent]) -> None:
        with self._lock:
            self.events[:] = events[-160:]

    def replace_ai_diagnoses(self, diagnoses: list[AiDiagnosis]) -> None:
        with self._lock:
            self.ai_diagnoses[:] = diagnoses[-80:]

    def set_incident_event_seq(self, value: int) -> None:
        with self._lock:
            self.incident_event_seq = value

    def replace_node_event_sequences(self, value: dict[tuple[str, str], int]) -> None:
        with self._lock:
            self.node_event_sequences = value

    def set_shadow_event_count(self, value: int) -> None:
        with self._lock:
            self.shadow_event_count = value

    def replace_audits_and_events(
        self,
        audits: list[AuditLog] | None,
        events: list[IncidentEvent] | None,
    ) -> None:
        with self._lock:
            if audits is not None:
                self.audit_logs[:] = audits[-300:]
                self.shadow_event_count = max(self.shadow_event_count, len(audits))
            if events is not None:
                self.events[:] = events[-160:]
            if events:
                self.incident_event_seq = max(
                    self.incident_event_seq,
                    max(event.id for event in events),
                )
                sequences = dict(self.node_event_sequences)
                for event in events:
                    key = (event.source_node or event.node_code, event.run_id)
                    sequences[key] = max(sequences.get(key, 0), event.local_sequence)
                self.node_event_sequences = sequences
