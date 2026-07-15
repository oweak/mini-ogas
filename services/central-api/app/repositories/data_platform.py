from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from ..core.config import settings
from ..core.database import get_db, persistence_backend, persistence_label
from ..domain.data_platform import (
    AggregateTelemetryIn,
    DataPlatformError,
    SignalDefinitionIn,
    TelemetryBatchIn,
)


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(_json_ready(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _row(value: Any) -> dict[str, Any]:
    return _json_ready(dict(value))


class DataPlatformRepository:
    """Durable Phase 7 authority for telemetry and object integrity metadata."""

    def _scope(self) -> tuple[str, str]:
        return settings.tenant_id, settings.site_id

    def _table(self, name: str) -> str:
        if persistence_backend() == "postgres":
            return f"telemetry.{name}"
        return f"telemetry_{name}"

    def _document_table(self, name: str) -> str:
        if persistence_backend() == "postgres":
            return f"documents.{name}"
        if name == "integrity_events":
            return "object_integrity_events"
        return f"document_{name}"

    def create_signal(self, payload: SignalDefinitionIn, actor: str) -> dict[str, Any]:
        table = self._table("signal_definitions")
        with get_db() as db:
            try:
                row = db.execute(
                    f"""INSERT INTO {table} (
                           tenant_id, site_id, signal_code, display_name, value_type,
                           unit, minimum, maximum, freshness_threshold_ms,
                           allowed_sources_json, mapping_version, active, created_by
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       RETURNING *""",
                    (
                        *self._scope(),
                        payload.signal_code,
                        payload.display_name,
                        payload.value_type,
                        payload.unit,
                        payload.minimum,
                        payload.maximum,
                        payload.freshness_threshold_ms,
                        _canonical_json(payload.allowed_sources),
                        payload.mapping_version,
                        True,
                        actor,
                    ),
                ).fetchone()
            except Exception as exc:
                if any(token in str(exc).lower() for token in ("unique", "duplicate")):
                    raise DataPlatformError(
                        409,
                        "TELEMETRY_SIGNAL_ALREADY_EXISTS",
                        "telemetry signal already exists in the active tenant/site",
                        signal_code=payload.signal_code,
                    ) from exc
                raise
        return self._format_signal(row)

    def provision_digital_twin_catalog(self, actor: str) -> dict[str, int]:
        if settings.data_source not in {"simulated", "replay"}:
            raise DataPlatformError(
                409,
                "DIGITAL_TWIN_CATALOG_SOURCE_MISMATCH",
                "digital-twin catalog provisioning is limited to simulated or replay data",
            )
        units = (
            ("OGAS-ENT", "Mini-OGAS Enterprise", "enterprise", None),
            ("OGAS-SITE", "Digital Twin Site", "site", "OGAS-ENT"),
            ("OGAS-AREA", "Machining Area", "area", "OGAS-SITE"),
            ("OGAS-LINE", "Machining Line", "line", "OGAS-AREA"),
            ("OGAS-CELL-TURN", "Turning Cell", "cell", "OGAS-LINE"),
            ("OGAS-CELL-MILL", "Milling Cell", "cell", "OGAS-LINE"),
            ("OGAS-CELL-GRIND", "Grinding Cell", "cell", "OGAS-LINE"),
        )
        equipment = (
            ("LATHE-01", "Digital Twin Lathe", "lathe", "OGAS-CELL-TURN"),
            ("MILL-02", "Digital Twin Mill", "mill", "OGAS-CELL-MILL"),
            ("GRIND-01", "Digital Twin Grinder", "grinder", "OGAS-CELL-GRIND"),
        )
        units_created = 0
        equipment_created = 0
        with get_db() as db:
            unit_ids: dict[str, int] = {}
            for code, name, unit_type, parent_code in units:
                existing = db.execute(
                    """SELECT id FROM organization_units
                       WHERE tenant_id=? AND site_id=? AND unit_code=?""",
                    (*self._scope(), code),
                ).fetchone()
                if existing is None:
                    parent_id = unit_ids.get(parent_code or "")
                    existing = db.execute(
                        """INSERT INTO organization_units (
                               tenant_id, site_id, unit_code, name, unit_type,
                               parent_id, active, created_by
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                           RETURNING id""",
                        (*self._scope(), code, name, unit_type, parent_id, True, actor),
                    ).fetchone()
                    units_created += 1
                unit_ids[code] = int(dict(existing)["id"])
            for code, name, equipment_type, unit_code in equipment:
                existing = db.execute(
                    """SELECT id FROM equipment
                       WHERE tenant_id=? AND site_id=? AND equipment_code=?""",
                    (*self._scope(), code),
                ).fetchone()
                if existing is not None:
                    continue
                db.execute(
                    """INSERT INTO equipment (
                           tenant_id, site_id, equipment_code, name, equipment_type,
                           organization_unit_id, active, created_by
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        *self._scope(),
                        code,
                        name,
                        equipment_type,
                        unit_ids[unit_code],
                        True,
                        actor,
                    ),
                )
                equipment_created += 1

        definitions = (
            ("SPINDLE-TEMPERATURE", "Spindle temperature", "Cel", 0.0, 120.0),
            ("TOOL-WEAR-LEVEL", "Tool wear level", "%", 0.0, 100.0),
            ("UTILIZATION", "Equipment utilization", "1", 0.0, 1.0),
            ("DEFECT-RATE", "Observed defect rate", "1", 0.0, 1.0),
            ("ACTUAL-RATE", "Observed throughput rate", "parts/min", 0.0, 10.0),
        )
        signals_created = 0
        existing_codes = {item["signal_code"] for item in self.list_signals()}
        for code, name, unit, minimum, maximum in definitions:
            if code in existing_codes:
                continue
            self.create_signal(
                SignalDefinitionIn(
                    signal_code=code,
                    display_name=name,
                    value_type="number",
                    unit=unit,
                    minimum=minimum,
                    maximum=maximum,
                    freshness_threshold_ms=20_000,
                    allowed_sources=["simulated", "replay"],
                    mapping_version=1,
                ),
                actor,
            )
            signals_created += 1
        return {
            "organization_units_created": units_created,
            "equipment_created": equipment_created,
            "signals_created": signals_created,
        }

    def list_signals(self) -> list[dict[str, Any]]:
        table = self._table("signal_definitions")
        with get_db() as db:
            rows = db.execute(
                f"""SELECT * FROM {table}
                    WHERE tenant_id=? AND site_id=?
                    ORDER BY signal_code""",
                self._scope(),
            ).fetchall()
        return [self._format_signal(item) for item in rows]

    def _format_signal(self, value: Any) -> dict[str, Any]:
        result = _row(value)
        result["allowed_sources"] = json.loads(result.pop("allowed_sources_json"))
        result["active"] = bool(result["active"])
        return result

    def _logical_batch_identity(self, payload: TelemetryBatchIn) -> dict[str, Any]:
        # The receipt clock may change on an at-least-once replay. Device sampling
        # clocks are measurement facts and remain part of the immutable identity.
        return {
            "batch_id": payload.batch_id,
            "source": payload.source,
            "source_id": payload.source_id,
            "equipment_code": payload.equipment_code,
            "samples": [
                {
                    "sample_id": item.sample_id,
                    "signal_code": item.signal_code,
                    "value": item.value,
                    "unit": item.unit,
                    "mapping_version": item.mapping_version,
                    "sequence_no": item.sequence_no,
                    "source_timestamp": item.source_timestamp,
                    "simulation_time": item.simulation_time,
                }
                for item in payload.samples
            ],
        }

    def ingest_batch(self, payload: TelemetryBatchIn, actor: str) -> tuple[dict[str, Any], bool]:
        batch_table = self._table("ingest_batches")
        receipt_table = self._table("sample_receipts")
        measurement_table = self._table("measurements")
        quality_table = self._table("quality_events")
        signal_table = self._table("signal_definitions")
        payload_hash = _hash(self._logical_batch_identity(payload))
        now = datetime.now(UTC)

        with get_db() as db:
            existing = db.execute(
                f"""SELECT payload_hash, response_json FROM {batch_table}
                    WHERE tenant_id=? AND site_id=? AND batch_id=?""",
                (*self._scope(), payload.batch_id),
            ).fetchone()
            if existing is not None:
                existing_data = dict(existing)
                if str(existing_data["payload_hash"]) != payload_hash:
                    raise DataPlatformError(
                        409,
                        "TELEMETRY_BATCH_IDENTITY_CONFLICT",
                        "batch_id was already committed with different measured values",
                        batch_id=payload.batch_id,
                    )
                response = json.loads(str(existing_data["response_json"]))
                response["idempotent_replay"] = True
                return response, True

            self._require_equipment(db, payload.equipment_code)
            db.execute(
                f"""INSERT INTO {batch_table} (
                       tenant_id, site_id, batch_id, payload_hash, source, source_id,
                       equipment_code, sample_count, response_json, ingested_by,
                       central_ingested_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?)""",
                (
                    *self._scope(),
                    payload.batch_id,
                    payload_hash,
                    payload.source,
                    payload.source_id,
                    payload.equipment_code,
                    len(payload.samples),
                    actor,
                    now.isoformat(),
                ),
            )

            counts = {"good": 0, "uncertain": 0, "bad": 0, "duplicate": 0}
            accepted: list[dict[str, Any]] = []
            for sample in payload.samples:
                definition_row = db.execute(
                    f"""SELECT * FROM {signal_table}
                        WHERE tenant_id=? AND site_id=? AND signal_code=? AND active=?""",
                    (*self._scope(), sample.signal_code, True),
                ).fetchone()
                if definition_row is None:
                    raise DataPlatformError(
                        409,
                        "TELEMETRY_SIGNAL_NOT_REGISTERED",
                        "sample references an unknown or inactive signal",
                        signal_code=sample.signal_code,
                    )
                definition = self._format_signal(definition_row)
                sample_identity = {
                    "sample_id": sample.sample_id,
                    "signal_code": sample.signal_code,
                    "value": sample.value,
                    "unit": sample.unit,
                    "mapping_version": sample.mapping_version,
                    "sequence_no": sample.sequence_no,
                }
                sample_hash = _hash(sample_identity)
                previous_receipt = db.execute(
                    f"""SELECT payload_hash FROM {receipt_table}
                        WHERE tenant_id=? AND site_id=? AND sample_id=?""",
                    (*self._scope(), sample.sample_id),
                ).fetchone()
                if previous_receipt is not None:
                    if str(dict(previous_receipt)["payload_hash"]) != sample_hash:
                        raise DataPlatformError(
                            409,
                            "TELEMETRY_SAMPLE_IDENTITY_CONFLICT",
                            "sample_id was already committed with different measured values",
                            sample_id=sample.sample_id,
                        )
                    counts["duplicate"] += 1
                    accepted.append(
                        {
                            "sample_id": sample.sample_id,
                            "signal_code": sample.signal_code,
                            "quality_code": "duplicate",
                            "quality_reason": "idempotent_replay",
                        }
                    )
                    continue

                sequence_owner = db.execute(
                    f"""SELECT sample_id FROM {receipt_table}
                        WHERE tenant_id=? AND site_id=? AND source_id=?
                          AND signal_code=? AND sequence_no=?""",
                    (
                        *self._scope(),
                        payload.source_id,
                        sample.signal_code,
                        sample.sequence_no,
                    ),
                ).fetchone()
                if sequence_owner is not None:
                    raise DataPlatformError(
                        409,
                        "TELEMETRY_SEQUENCE_IDENTITY_CONFLICT",
                        "sequence number is already owned by another sample",
                        signal_code=sample.signal_code,
                        sequence_no=sample.sequence_no,
                    )

                maximum_sequence = db.execute(
                    f"""SELECT MAX(sequence_no) AS maximum_sequence FROM {receipt_table}
                        WHERE tenant_id=? AND site_id=? AND source_id=? AND signal_code=?""",
                    (*self._scope(), payload.source_id, sample.signal_code),
                ).fetchone()
                maximum_value = dict(maximum_sequence)["maximum_sequence"]
                quality_code, quality_reason, detail = self._classify(
                    payload,
                    sample.model_dump(),
                    definition,
                    int(maximum_value) if maximum_value is not None else None,
                    now,
                )
                db.execute(
                    f"""INSERT INTO {receipt_table} (
                           tenant_id, site_id, sample_id, payload_hash, batch_id,
                           source_id, signal_code, sequence_no, source_timestamp
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        *self._scope(),
                        sample.sample_id,
                        sample_hash,
                        payload.batch_id,
                        payload.source_id,
                        sample.signal_code,
                        sample.sequence_no,
                        sample.source_timestamp.astimezone(UTC).isoformat(),
                    ),
                )
                numeric_value, text_value = self._split_value(
                    sample.value,
                    definition["value_type"],
                )
                measurement = db.execute(
                    f"""INSERT INTO {measurement_table} (
                           tenant_id, site_id, sample_id, batch_id, source, source_id,
                           equipment_code, signal_code, numeric_value, text_value, unit,
                           quality_code, quality_reason, mapping_version, sequence_no,
                           source_timestamp, edge_received_at, central_ingested_at,
                           processed_at, simulation_time, is_manual, is_corrected,
                           correction_reason
                       ) VALUES (
                           ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ''
                       )
                       RETURNING id""",
                    (
                        *self._scope(),
                        sample.sample_id,
                        payload.batch_id,
                        payload.source,
                        payload.source_id,
                        payload.equipment_code,
                        sample.signal_code,
                        numeric_value,
                        text_value,
                        sample.unit,
                        quality_code,
                        quality_reason,
                        sample.mapping_version,
                        sample.sequence_no,
                        sample.source_timestamp.astimezone(UTC).isoformat(),
                        payload.edge_received_at.astimezone(UTC).isoformat(),
                        now.isoformat(),
                        now.isoformat(),
                        sample.simulation_time.astimezone(UTC).isoformat()
                        if sample.simulation_time
                        else None,
                        False,
                        False,
                    ),
                ).fetchone()
                measurement_id = int(
                    dict(measurement)["id"]
                    if hasattr(measurement, "keys")
                    else measurement[0]
                )
                if quality_code != "good":
                    db.execute(
                        f"""INSERT INTO {quality_table} (
                               tenant_id, site_id, sample_id, source_id, signal_code,
                               quality_code, reason_code, detail_json, occurred_at
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            *self._scope(),
                            sample.sample_id,
                            payload.source_id,
                            sample.signal_code,
                            quality_code,
                            quality_reason,
                            _canonical_json(detail),
                            now.isoformat(),
                        ),
                    )
                counts[quality_code] += 1
                accepted.append(
                    {
                        "measurement_id": measurement_id,
                        "sample_id": sample.sample_id,
                        "signal_code": sample.signal_code,
                        "quality_code": quality_code,
                        "quality_reason": quality_reason,
                    }
                )

            response = {
                "batch_id": payload.batch_id,
                "idempotent_replay": False,
                "counts": counts,
                "samples": accepted,
                "central_ingested_at": now.isoformat(),
                "historian": {
                    "provider": "postgresql-native",
                    "runtime_backend": persistence_label(),
                    "schema": "telemetry",
                },
            }
            db.execute(
                f"""UPDATE {batch_table} SET response_json=?
                    WHERE tenant_id=? AND site_id=? AND batch_id=?""",
                (_canonical_json(response), *self._scope(), payload.batch_id),
            )
        return response, False

    def _require_equipment(self, db: Any, equipment_code: str) -> None:
        row = db.execute(
            """SELECT id FROM equipment
               WHERE tenant_id=? AND site_id=? AND equipment_code=?""",
            (*self._scope(), equipment_code),
        ).fetchone()
        if row is None:
            raise DataPlatformError(
                409,
                "TELEMETRY_EQUIPMENT_NOT_REGISTERED",
                "telemetry batch references equipment outside the active master data",
                equipment_code=equipment_code,
            )

    def _classify(
        self,
        batch: TelemetryBatchIn,
        sample: dict[str, Any],
        definition: dict[str, Any],
        maximum_sequence: int | None,
        now: datetime,
    ) -> tuple[str, str, dict[str, Any]]:
        detail = {
            "expected_unit": definition["unit"],
            "observed_unit": sample["unit"],
            "expected_mapping_version": definition["mapping_version"],
            "observed_mapping_version": sample["mapping_version"],
        }
        if maximum_sequence is not None and int(sample["sequence_no"]) < maximum_sequence:
            detail["maximum_sequence"] = maximum_sequence
            return "bad", "out_of_order", detail
        if batch.source not in definition["allowed_sources"]:
            return "bad", "source_not_allowed", detail
        if int(sample["mapping_version"]) != int(definition["mapping_version"]):
            return "bad", "mapping_version_mismatch", detail
        if str(sample["unit"]) != str(definition["unit"]):
            return "bad", "unit_mismatch", detail
        value = sample["value"]
        if not self._value_matches(value, str(definition["value_type"])):
            return "bad", "type_mismatch", detail
        if definition["value_type"] in {"number", "integer"}:
            numeric = float(value)
            if definition["minimum"] is not None and numeric < float(definition["minimum"]):
                detail["minimum"] = definition["minimum"]
                return "bad", "range_violation", detail
            if definition["maximum"] is not None and numeric > float(definition["maximum"]):
                detail["maximum"] = definition["maximum"]
                return "bad", "range_violation", detail
        source_timestamp = _as_datetime(sample["source_timestamp"])
        age_ms = int((now - source_timestamp).total_seconds() * 1_000)
        detail["freshness_age_ms"] = age_ms
        if age_ms > int(definition["freshness_threshold_ms"]):
            return "uncertain", "stale", detail
        if age_ms < -5_000:
            return "uncertain", "clock_skew", detail
        return "good", "", detail

    def _value_matches(self, value: Any, value_type: str) -> bool:
        if value_type == "boolean":
            return isinstance(value, bool)
        if value_type == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if value_type == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        return isinstance(value, str)

    def _split_value(self, value: Any, value_type: str) -> tuple[float | None, str | None]:
        if value_type in {"number", "integer"}:
            return float(value), None
        if value_type == "boolean":
            return (1.0 if bool(value) else 0.0), None
        return None, str(value)

    def latest_signals(self) -> dict[str, Any]:
        generated_at = datetime.now(UTC)
        definitions = [item for item in self.list_signals() if item["active"]]
        definitions_by_code = {item["signal_code"]: item for item in definitions}
        measurement_table = self._table("measurements")
        signals: list[dict[str, Any]] = []
        observed_codes: set[str] = set()
        with get_db() as db:
            latest_rows = db.execute(
                f"""SELECT * FROM (
                       SELECT m.*, ROW_NUMBER() OVER (
                           PARTITION BY source_id, signal_code
                           ORDER BY source_timestamp DESC, id DESC
                       ) AS row_number
                       FROM {measurement_table} m
                       WHERE tenant_id=? AND site_id=?
                   ) ranked WHERE row_number=1
                   ORDER BY source_id, signal_code""",
                self._scope(),
            ).fetchall()
            for latest in latest_rows:
                measurement = _row(latest)
                definition = definitions_by_code.get(str(measurement["signal_code"]))
                if definition is None:
                    continue
                observed_codes.add(definition["signal_code"])
                source_timestamp = _as_datetime(measurement["source_timestamp"])
                age_ms = max(0, int((generated_at - source_timestamp).total_seconds() * 1_000))
                quality_code = str(measurement["quality_code"])
                quality_reason = str(measurement["quality_reason"] or "")
                if quality_code == "good" and age_ms > int(definition["freshness_threshold_ms"]):
                    quality_code = "uncertain"
                    quality_reason = "stale"
                signals.append(
                    {
                        **definition,
                        "measurement_id": int(measurement["id"]),
                        "sample_id": measurement["sample_id"],
                        "equipment_code": measurement["equipment_code"],
                        "value": measurement["numeric_value"]
                        if measurement["numeric_value"] is not None
                        else measurement["text_value"],
                        "source": measurement["source"],
                        "source_id": measurement["source_id"],
                        "source_timestamp": source_timestamp.isoformat(),
                        "freshness_age_ms": age_ms,
                        "quality_code": quality_code,
                        "quality_reason": quality_reason,
                    }
                )
        for definition in definitions:
            if definition["signal_code"] in observed_codes:
                continue
            signals.append(
                {
                    **definition,
                    "value": None,
                    "source": None,
                    "source_id": None,
                    "source_timestamp": None,
                    "freshness_age_ms": None,
                    "quality_code": "bad",
                    "quality_reason": "missing",
                }
            )
        return {
            "generated_at": generated_at.isoformat(),
            "source_of_truth": "postgresql-historian",
            "runtime_backend": persistence_label(),
            "signals": signals,
        }

    def quality_summary(self) -> dict[str, Any]:
        latest = self.latest_signals()
        expected_sources = set(settings.expected_production_nodes)
        all_signals = latest["signals"]
        signals = [
            signal
            for signal in all_signals
            if signal.get("source_id") is None or signal.get("source_id") in expected_sources
        ]
        excluded_auxiliary_streams = len(all_signals) - len(signals)
        represented_codes = {str(signal["signal_code"]) for signal in signals}
        for definition in self.list_signals():
            if not definition["active"] or definition["signal_code"] in represented_codes:
                continue
            signals.append(
                {
                    **definition,
                    "value": None,
                    "source": None,
                    "source_id": None,
                    "source_timestamp": None,
                    "freshness_age_ms": None,
                    "quality_code": "bad",
                    "quality_reason": "missing",
                }
            )
        counts: defaultdict[str, int] = defaultdict(int)
        for signal in signals:
            counts[str(signal["quality_code"])] += 1
            reason = str(signal["quality_reason"] or "")
            if reason:
                counts[reason] += 1
        for key in ("good", "uncertain", "bad", "missing", "stale"):
            counts[key] += 0
        return {
            "generated_at": latest["generated_at"],
            "source_of_truth": latest["source_of_truth"],
            "scope": "configured-production-sources",
            "expected_sources": sorted(expected_sources),
            "excluded_auxiliary_streams": excluded_auxiliary_streams,
            "counts": dict(counts),
            "signals": signals,
        }

    def projection_source(self) -> dict[str, Any]:
        table = self._table("measurements")
        with get_db() as db:
            rows = db.execute(
                f"""SELECT * FROM (
                       SELECT m.*, ROW_NUMBER() OVER (
                           PARTITION BY source_id, signal_code
                           ORDER BY source_timestamp DESC, id DESC
                       ) AS row_number
                       FROM {table} m
                       WHERE tenant_id=? AND site_id=?
                   ) ranked WHERE row_number=1
                   ORDER BY source_id, signal_code""",
                self._scope(),
            ).fetchall()
            totals = db.execute(
                f"""SELECT COUNT(*) AS measurement_count, COALESCE(MAX(id), 0) AS maximum_id
                    FROM {table} WHERE tenant_id=? AND site_id=?""",
                self._scope(),
            ).fetchone()
        total_data = dict(totals)
        return {
            "rows": [_row(item) for item in rows],
            "measurement_count": int(total_data["measurement_count"]),
            "maximum_id": int(total_data["maximum_id"]),
        }

    def record_projection_checkpoint(
        self,
        generation: str,
        measurement_count: int,
        projected_key_count: int,
        maximum_id: int,
        status: str,
        reason: str,
        actor: str,
    ) -> dict[str, Any]:
        table = self._table("projection_checkpoints")
        created_at = datetime.now(UTC).isoformat()
        with get_db() as db:
            row = db.execute(
                f"""INSERT INTO {table} (
                       tenant_id, site_id, generation, provider, measurement_count,
                       projected_key_count, max_measurement_id, status, reason,
                       created_by, created_at
                   ) VALUES (?, ?, ?, 'redis', ?, ?, ?, ?, ?, ?, ?)
                   RETURNING *""",
                (
                    *self._scope(),
                    generation,
                    measurement_count,
                    projected_key_count,
                    maximum_id,
                    status,
                    reason,
                    actor,
                    created_at,
                ),
            ).fetchone()
        return _row(row)

    def aggregate_hourly(self, payload: AggregateTelemetryIn) -> dict[str, Any]:
        measurement_table = self._table("measurements")
        aggregate_table = self._table("aggregates_hourly")
        clauses = ["tenant_id=?", "site_id=?"]
        params: list[Any] = [*self._scope()]
        if payload.from_timestamp:
            clauses.append("source_timestamp>=?")
            params.append(payload.from_timestamp.astimezone(UTC).isoformat())
        if payload.to_timestamp:
            clauses.append("source_timestamp<?")
            params.append(payload.to_timestamp.astimezone(UTC).isoformat())
        with get_db() as db:
            rows = db.execute(
                f"SELECT * FROM {measurement_table} WHERE {' AND '.join(clauses)}",
                tuple(params),
            ).fetchall()
            groups: defaultdict[tuple[str, str, datetime], list[dict[str, Any]]] = defaultdict(list)
            for item in rows:
                data = _row(item)
                timestamp = _as_datetime(data["source_timestamp"])
                window = timestamp.replace(minute=0, second=0, microsecond=0)
                groups[(str(data["source_id"]), str(data["signal_code"]), window)].append(data)
            for (source_id, signal_code, window), items in groups.items():
                values = [
                    float(item["numeric_value"])
                    for item in items
                    if item["numeric_value"] is not None
                ]
                quality_counts = defaultdict(int)
                for item in items:
                    quality_counts[str(item["quality_code"])] += 1
                db.execute(
                    f"""INSERT INTO {aggregate_table} (
                           tenant_id, site_id, source_id, signal_code, window_start,
                           window_end, sample_count, good_count, uncertain_count,
                           bad_count, minimum, maximum, average, generated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT (tenant_id, site_id, source_id, signal_code, window_start)
                       DO UPDATE SET window_end=excluded.window_end,
                           sample_count=excluded.sample_count,
                           good_count=excluded.good_count,
                           uncertain_count=excluded.uncertain_count,
                           bad_count=excluded.bad_count,
                           minimum=excluded.minimum, maximum=excluded.maximum,
                           average=excluded.average, generated_at=excluded.generated_at""",
                    (
                        *self._scope(),
                        source_id,
                        signal_code,
                        window.isoformat(),
                        (window + timedelta(hours=1)).isoformat(),
                        len(items),
                        quality_counts["good"],
                        quality_counts["uncertain"],
                        quality_counts["bad"],
                        min(values) if values else None,
                        max(values) if values else None,
                        sum(values) / len(values) if values else None,
                        datetime.now(UTC).isoformat(),
                    ),
                )
        return {"windows_written": len(groups), "source_rows": len(rows)}

    def _retention_coverage(self, raw_cutoff: datetime) -> dict[str, int]:
        measurement_table = self._table("measurements")
        aggregate_table = self._table("aggregates_hourly")
        cutoff = raw_cutoff.astimezone(UTC).isoformat()
        with get_db() as db:
            raw_rows = db.execute(
                f"""SELECT source_id, signal_code, source_timestamp
                    FROM {measurement_table}
                    WHERE tenant_id=? AND site_id=? AND source_timestamp<?""",
                (*self._scope(), cutoff),
            ).fetchall()
            aggregate_rows = db.execute(
                f"""SELECT source_id, signal_code, window_start, sample_count
                    FROM {aggregate_table}
                    WHERE tenant_id=? AND site_id=? AND window_start<?""",
                (*self._scope(), cutoff),
            ).fetchall()

        expected: defaultdict[tuple[str, str, datetime], int] = defaultdict(int)
        for row in raw_rows:
            data = _row(row)
            window = _as_datetime(data["source_timestamp"]).replace(
                minute=0,
                second=0,
                microsecond=0,
            )
            expected[(str(data["source_id"]), str(data["signal_code"]), window)] += 1
        observed = {
            (
                str(data["source_id"]),
                str(data["signal_code"]),
                _as_datetime(data["window_start"]),
            ): int(data["sample_count"])
            for data in (_row(row) for row in aggregate_rows)
        }
        mismatches = [
            {
                "source_id": key[0],
                "signal_code": key[1],
                "window_start": key[2].isoformat(),
                "expected": sample_count,
                "observed": observed.get(key, 0),
            }
            for key, sample_count in expected.items()
            if observed.get(key) != sample_count
        ]
        if mismatches:
            raise DataPlatformError(
                409,
                "TELEMETRY_RETENTION_COVERAGE_INCOMPLETE",
                "raw telemetry was preserved because hourly aggregate coverage is incomplete",
                mismatches=mismatches[:20],
                mismatch_count=len(mismatches),
            )
        return {
            "raw_rows": len(raw_rows),
            "covered_windows": len(expected),
        }

    def _start_retention_run(
        self,
        *,
        raw_cutoff: datetime,
        aggregate_cutoff: datetime,
        reason: str,
        actor: str,
        started_at: datetime,
    ) -> int:
        table = self._table("retention_runs")
        with get_db() as db:
            row = db.execute(
                f"""INSERT INTO {table} (
                       tenant_id, site_id, raw_cutoff, aggregate_cutoff,
                       raw_deleted, aggregate_deleted, status, reason,
                       created_by, started_at
                   ) VALUES (?, ?, ?, ?, 0, 0, 'running', ?, ?, ?)
                   RETURNING id""",
                (
                    *self._scope(),
                    raw_cutoff.astimezone(UTC).isoformat(),
                    aggregate_cutoff.astimezone(UTC).isoformat(),
                    reason,
                    actor,
                    started_at.astimezone(UTC).isoformat(),
                ),
            ).fetchone()
        return int(dict(row)["id"])

    def _fail_retention_run(self, run_id: int) -> None:
        table = self._table("retention_runs")
        with get_db() as db:
            db.execute(
                f"""UPDATE {table}
                    SET status='failed', completed_at=?
                    WHERE tenant_id=? AND site_id=? AND id=?""",
                (datetime.now(UTC).isoformat(), *self._scope(), run_id),
            )

    def run_retention(self, *, reason: str, actor: str) -> dict[str, Any]:
        now = datetime.now(UTC)
        raw_cutoff = now - timedelta(days=settings.telemetry_raw_retention_days)
        aggregate_cutoff = now - timedelta(days=settings.telemetry_aggregate_retention_days)
        run_id = self._start_retention_run(
            raw_cutoff=raw_cutoff,
            aggregate_cutoff=aggregate_cutoff,
            reason=reason,
            actor=actor,
            started_at=now,
        )
        try:
            aggregation = self.aggregate_hourly(AggregateTelemetryIn(to_timestamp=raw_cutoff))
            coverage = self._retention_coverage(raw_cutoff)
            measurement_table = self._table("measurements")
            aggregate_table = self._table("aggregates_hourly")
            run_table = self._table("retention_runs")
            context_table = self._table("operation_context")
            with get_db() as db:
                if persistence_backend() == "postgres":
                    db.execute("SELECT set_config('app.retention_mode', 'on', true)")
                else:
                    db.execute(
                        f"UPDATE {context_table} SET retention_enabled=1 WHERE singleton=1"
                    )
                raw_result = db.execute(
                    f"""DELETE FROM {measurement_table}
                        WHERE tenant_id=? AND site_id=? AND source_timestamp<?""",
                    (*self._scope(), raw_cutoff.isoformat()),
                )
                aggregate_result = db.execute(
                    f"""DELETE FROM {aggregate_table}
                        WHERE tenant_id=? AND site_id=? AND window_end<=?""",
                    (*self._scope(), aggregate_cutoff.isoformat()),
                )
                raw_deleted = max(0, int(raw_result.rowcount))
                aggregate_deleted = max(0, int(aggregate_result.rowcount))
                if persistence_backend() != "postgres":
                    db.execute(
                        f"UPDATE {context_table} SET retention_enabled=0 WHERE singleton=1"
                    )
                completed_at = datetime.now(UTC).isoformat()
                row = db.execute(
                    f"""UPDATE {run_table}
                        SET raw_deleted=?, aggregate_deleted=?, status='completed',
                            completed_at=?
                        WHERE tenant_id=? AND site_id=? AND id=?
                        RETURNING *""",
                    (
                        raw_deleted,
                        aggregate_deleted,
                        completed_at,
                        *self._scope(),
                        run_id,
                    ),
                ).fetchone()
            result = _row(row)
            result["aggregation"] = aggregation
            result["coverage"] = coverage
            return result
        except DataPlatformError:
            self._fail_retention_run(run_id)
            raise
        except Exception as exc:
            self._fail_retention_run(run_id)
            raise DataPlatformError(
                503,
                "TELEMETRY_RETENTION_FAILED",
                "retention failed and raw telemetry was preserved",
                error_type=type(exc).__name__,
                run_id=run_id,
            ) from exc

    def create_object_manifest(
        self,
        *,
        object_key: str,
        content_sha256: str,
        byte_length: int,
        content_type: str,
        original_name: str,
        actor: str,
    ) -> dict[str, Any]:
        table = self._document_table("objects")
        with get_db() as db:
            existing = db.execute(
                f"""SELECT * FROM {table}
                    WHERE tenant_id=? AND site_id=? AND object_key=?""",
                (*self._scope(), object_key),
            ).fetchone()
            if existing is not None:
                return _row(existing)
            row = db.execute(
                f"""INSERT INTO {table} (
                       tenant_id, site_id, object_key, bucket, provider,
                       content_sha256, byte_length, content_type, original_name,
                       status, created_by, created_at
                   ) VALUES (?, ?, ?, ?, 'minio', ?, ?, ?, ?, 'pending', ?, ?)
                   RETURNING *""",
                (
                    *self._scope(),
                    object_key,
                    settings.object_storage_bucket,
                    content_sha256,
                    byte_length,
                    content_type,
                    original_name,
                    actor,
                    datetime.now(UTC).isoformat(),
                ),
            ).fetchone()
        return _row(row)

    def complete_object_manifest(
        self,
        object_id: int,
        *,
        status: str,
        expected_sha256: str,
        observed_sha256: str,
        byte_length: int,
        etag: str,
        storage_version: str,
        actor: str,
    ) -> dict[str, Any]:
        object_table = self._document_table("objects")
        event_table = self._document_table("integrity_events")
        now = datetime.now(UTC).isoformat()
        with get_db() as db:
            db.execute(
                f"""UPDATE {object_table}
                    SET status=?, etag=?, storage_version=?, verified_at=?
                    WHERE tenant_id=? AND site_id=? AND id=?""",
                (status, etag, storage_version, now, *self._scope(), object_id),
            )
            db.execute(
                f"""INSERT INTO {event_table} (
                       tenant_id, site_id, object_id, event_type, expected_sha256,
                       observed_sha256, byte_length, actor, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    object_id,
                    "verified" if status == "available" else "quarantined",
                    expected_sha256,
                    observed_sha256,
                    byte_length,
                    actor,
                    now,
                ),
            )
            row = db.execute(
                f"""SELECT * FROM {object_table}
                    WHERE tenant_id=? AND site_id=? AND id=?""",
                (*self._scope(), object_id),
            ).fetchone()
        return _row(row)

    def require_available_object(self, object_id: int) -> dict[str, Any]:
        table = self._document_table("objects")
        with get_db() as db:
            row = db.execute(
                f"""SELECT * FROM {table}
                    WHERE tenant_id=? AND site_id=? AND id=? AND status='available'""",
                (*self._scope(), object_id),
            ).fetchone()
        if row is None:
            raise DataPlatformError(
                409,
                "DOCUMENT_OBJECT_NOT_AVAILABLE",
                "document object is absent, unverified, or outside the active scope",
                object_id=object_id,
            )
        return _row(row)


data_platform_repository = DataPlatformRepository()
