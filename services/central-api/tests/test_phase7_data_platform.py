from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.store import store
from fastapi.testclient import TestClient


class _ObjectResponse:
    def __init__(self, content: bytes):
        self.content = content

    def read(self, amount: int | None = None) -> bytes:
        if amount is None:
            return self.content
        return self.content[:amount]

    def close(self) -> None:
        return None

    def release_conn(self) -> None:
        return None


class _ObjectClient:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}

    def bucket_exists(self, bucket: str) -> bool:
        del bucket
        return True

    def make_bucket(self, bucket: str) -> None:
        del bucket

    def put_object(
        self,
        bucket: str,
        object_key: str,
        stream: object,
        *,
        length: int,
        content_type: str,
        metadata: dict[str, str],
    ) -> SimpleNamespace:
        del content_type, metadata
        content = stream.read(length)
        self.objects[(bucket, object_key)] = content
        return SimpleNamespace(etag="phase7-etag", version_id="phase7-version")

    def get_object(self, bucket: str, object_key: str) -> _ObjectResponse:
        return _ObjectResponse(self.objects[(bucket, object_key)])


def _post(
    context: dict,
    path: str,
    payload: dict | None = None,
    *,
    expected: int = 201,
    node: bool = False,
) -> dict:
    headers = (
        {"X-OGAS-Token": settings.node_ingest_token}
        if node
        else context["headers"]
    )
    response = context["client"].post(path, headers=headers, json=payload or {})
    assert response.status_code == expected, response.text
    return response.json()


def _signal(context: dict, code: str, **overrides: object) -> dict:
    payload = {
        "signal_code": code,
        "display_name": code.replace("-", " "),
        "value_type": "number",
        "unit": "Cel",
        "minimum": 0,
        "maximum": 120,
        "freshness_threshold_ms": 60_000,
        "allowed_sources": ["simulated"],
        "mapping_version": 1,
    }
    payload.update(overrides)
    return _post(context, "/telemetry/signals", payload)


def _batch(
    context: dict,
    *,
    batch_id: str,
    signal_code: str,
    sample_id: str,
    sequence_no: int,
    value: float = 61.5,
    unit: str = "Cel",
    mapping_version: int = 1,
    source_timestamp: datetime | None = None,
    source_id: str = "turning-workshop-01",
    equipment_code: str = "P7-LATHE-01",
    expected: int = 201,
) -> dict:
    occurred_at = source_timestamp or datetime.now(UTC)
    return _post(
        context,
        "/telemetry/batches",
        {
            "batch_id": batch_id,
            "source": "simulated",
            "source_id": source_id,
            "equipment_code": equipment_code,
            "edge_received_at": occurred_at.isoformat(),
            "samples": [
                {
                    "sample_id": sample_id,
                    "signal_code": signal_code,
                    "value": value,
                    "unit": unit,
                    "mapping_version": mapping_version,
                    "sequence_no": sequence_no,
                    "source_timestamp": occurred_at.isoformat(),
                    "simulation_time": occurred_at.isoformat(),
                }
            ],
        },
        expected=expected,
        node=True,
    )


@pytest.fixture(scope="module")
def phase7_context() -> dict:
    client = TestClient(app)
    client.__enter__()
    login = client.post(
        "/auth/login",
        json={"operator": "admin", "password": "mini-ogas-dev-token"},
    )
    assert login.status_code == 200
    context = {
        "client": client,
        "headers": {"Authorization": f"Bearer {login.json()['access_token']}"},
    }
    for code, name, unit_type, parent in (
        ("P7-ENT", "Phase 7 Enterprise", "enterprise", None),
        ("P7-SITE", "Phase 7 Site", "site", "P7-ENT"),
        ("P7-AREA", "Phase 7 Area", "area", "P7-SITE"),
        ("P7-LINE", "Phase 7 Line", "line", "P7-AREA"),
        ("P7-CELL", "Phase 7 Cell", "cell", "P7-LINE"),
    ):
        payload = {"unit_code": code, "name": name, "unit_type": unit_type}
        if parent:
            payload["parent_code"] = parent
        _post(context, "/master-data/organization-units", payload)
    _post(
        context,
        "/master-data/equipment",
        {
            "equipment_code": "P7-LATHE-01",
            "name": "Phase 7 Lathe",
            "equipment_type": "lathe",
            "organization_unit_code": "P7-CELL",
        },
    )
    yield context
    client.__exit__(None, None, None)


def test_typed_telemetry_ingest_is_separate_from_legacy_metrics(
    phase7_context: dict,
) -> None:
    code = "P7-SPINDLE-TEMPERATURE"
    definition = _signal(phase7_context, code)
    assert definition["signal_code"] == code

    with get_db() as db:
        metrics_before = int(db.execute("SELECT COUNT(*) AS count FROM metrics").fetchone()["count"])

    accepted = _batch(
        phase7_context,
        batch_id="P7-BATCH-GOOD",
        signal_code=code,
        sample_id="P7-SAMPLE-GOOD",
        sequence_no=1,
    )
    assert accepted["counts"] == {"good": 1, "uncertain": 0, "bad": 0, "duplicate": 0}
    assert accepted["samples"][0]["quality_code"] == "good"
    assert accepted["historian"]["provider"] == "postgresql-native"

    with get_db() as db:
        metrics_after = int(db.execute("SELECT COUNT(*) AS count FROM metrics").fetchone()["count"])
        row = db.execute(
            "SELECT signal_code, unit, quality_code, source_timestamp, central_ingested_at "
            "FROM telemetry_measurements WHERE sample_id = ?",
            ("P7-SAMPLE-GOOD",),
        ).fetchone()
    assert metrics_after == metrics_before
    assert dict(row)["signal_code"] == code
    assert dict(row)["unit"] == "Cel"
    assert dict(row)["quality_code"] == "good"


def test_quality_classifies_unit_range_stale_and_out_of_order(phase7_context: dict) -> None:
    code = "P7-BEARING-TEMPERATURE"
    _signal(phase7_context, code, freshness_threshold_ms=1_000)
    now = datetime.now(UTC)
    _batch(
        phase7_context,
        batch_id="P7-Q-GOOD",
        signal_code=code,
        sample_id="P7-Q-GOOD",
        sequence_no=10,
        source_timestamp=now,
    )
    wrong_unit = _batch(
        phase7_context,
        batch_id="P7-Q-UNIT",
        signal_code=code,
        sample_id="P7-Q-UNIT",
        sequence_no=11,
        unit="degF",
        source_timestamp=now + timedelta(milliseconds=1),
    )
    out_of_range = _batch(
        phase7_context,
        batch_id="P7-Q-RANGE",
        signal_code=code,
        sample_id="P7-Q-RANGE",
        sequence_no=12,
        value=150,
        source_timestamp=now + timedelta(milliseconds=2),
    )
    stale = _batch(
        phase7_context,
        batch_id="P7-Q-STALE",
        signal_code=code,
        sample_id="P7-Q-STALE",
        sequence_no=13,
        source_timestamp=now - timedelta(minutes=2),
    )
    out_of_order = _batch(
        phase7_context,
        batch_id="P7-Q-ORDER",
        signal_code=code,
        sample_id="P7-Q-ORDER",
        sequence_no=9,
        source_timestamp=now + timedelta(milliseconds=3),
    )

    assert wrong_unit["samples"][0]["quality_reason"] == "unit_mismatch"
    assert out_of_range["samples"][0]["quality_reason"] == "range_violation"
    assert stale["samples"][0]["quality_reason"] == "stale"
    assert stale["samples"][0]["quality_code"] == "uncertain"
    assert out_of_order["samples"][0]["quality_reason"] == "out_of_order"


def test_batch_identity_is_idempotent_and_conflicting_reuse_fails(phase7_context: dict) -> None:
    code = "P7-SPINDLE-SPEED"
    _signal(
        phase7_context,
        code,
        unit="r/min",
        minimum=0,
        maximum=10_000,
    )
    observed_at = datetime.now(UTC)
    first = _batch(
        phase7_context,
        batch_id="P7-IDEMPOTENT-BATCH",
        signal_code=code,
        sample_id="P7-IDEMPOTENT-SAMPLE",
        sequence_no=1,
        value=1_800,
        unit="r/min",
        source_timestamp=observed_at,
    )
    replay = _batch(
        phase7_context,
        batch_id="P7-IDEMPOTENT-BATCH",
        signal_code=code,
        sample_id="P7-IDEMPOTENT-SAMPLE",
        sequence_no=1,
        value=1_800,
        unit="r/min",
        source_timestamp=observed_at,
        expected=200,
    )
    conflict = _batch(
        phase7_context,
        batch_id="P7-IDEMPOTENT-BATCH",
        signal_code=code,
        sample_id="P7-IDEMPOTENT-SAMPLE",
        sequence_no=1,
        value=1_800,
        unit="r/min",
        source_timestamp=observed_at + timedelta(seconds=1),
        expected=409,
    )

    assert first["idempotent_replay"] is False
    assert replay["idempotent_replay"] is True
    assert replay["batch_id"] == first["batch_id"]
    assert conflict["code"] == "TELEMETRY_BATCH_IDENTITY_CONFLICT"


def test_latest_and_quality_summary_expose_missing_source_and_freshness(
    phase7_context: dict,
) -> None:
    missing_code = "P7-VIBRATION-MISSING"
    _signal(
        phase7_context,
        missing_code,
        unit="mm/s",
        minimum=0,
        maximum=50,
        freshness_threshold_ms=5_000,
    )
    latest = phase7_context["client"].get(
        "/telemetry/latest", headers=phase7_context["headers"]
    )
    assert latest.status_code == 200, latest.text
    missing = next(item for item in latest.json()["signals"] if item["signal_code"] == missing_code)
    assert missing["quality_code"] == "bad"
    assert missing["quality_reason"] == "missing"
    assert missing["source"] is None
    assert missing["freshness_age_ms"] is None

    summary = phase7_context["client"].get(
        "/telemetry/quality/summary", headers=phase7_context["headers"]
    )
    assert summary.status_code == 200, summary.text
    assert summary.json()["counts"]["missing"] >= 1
    assert summary.json()["generated_at"]


def test_latest_and_quality_summary_preserve_each_observed_source_stream(
    phase7_context: dict,
) -> None:
    code = f"P7-MULTI-SOURCE-{uuid4().hex[:8].upper()}"
    _signal(phase7_context, code)
    observed_at = datetime.now(UTC)
    _batch(
        phase7_context,
        batch_id=f"batch-{uuid4()}",
        signal_code=code,
        sample_id=f"sample-{uuid4()}",
        sequence_no=1,
        source_id="turning-workshop-01",
        value=51.0,
        source_timestamp=observed_at,
    )
    _batch(
        phase7_context,
        batch_id=f"batch-{uuid4()}",
        signal_code=code,
        sample_id=f"sample-{uuid4()}",
        sequence_no=1,
        source_id="milling-workshop-01",
        value=62.0,
        source_timestamp=observed_at + timedelta(milliseconds=1),
    )
    _batch(
        phase7_context,
        batch_id=f"batch-{uuid4()}",
        signal_code=code,
        sample_id=f"sample-{uuid4()}",
        sequence_no=1,
        source_id="phase7-validation-source",
        value=73.0,
        source_timestamp=observed_at + timedelta(milliseconds=2),
    )

    latest = phase7_context["client"].get(
        "/telemetry/latest", headers=phase7_context["headers"]
    )
    assert latest.status_code == 200, latest.text
    streams = [item for item in latest.json()["signals"] if item["signal_code"] == code]
    assert {(item["source_id"], item["value"]) for item in streams} == {
        ("turning-workshop-01", 51.0),
        ("milling-workshop-01", 62.0),
        ("phase7-validation-source", 73.0),
    }

    summary = phase7_context["client"].get(
        "/telemetry/quality/summary", headers=phase7_context["headers"]
    )
    assert summary.status_code == 200, summary.text
    quality_streams = [
        item for item in summary.json()["signals"] if item["signal_code"] == code
    ]
    assert len(quality_streams) == 2
    assert summary.json()["scope"] == "configured-production-sources"
    assert summary.json()["excluded_auxiliary_streams"] >= 1


def test_projection_failure_is_explicit_when_redis_is_unavailable(
    phase7_context: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "redis_enabled", False)
    response = phase7_context["client"].post(
        "/telemetry/projection/rebuild",
        headers=phase7_context["headers"],
        json={"reason": "phase7 unit gate"},
    )
    assert response.status_code == 503, response.text
    assert response.json()["code"] == "REDIS_PROJECTION_UNAVAILABLE"


def test_document_revision_has_immutable_sha256_and_length(phase7_context: dict) -> None:
    code = f"P7-DOC-{uuid4().hex[:8].upper()}"
    content = "Phase 7 controlled object integrity"
    _post(
        phase7_context,
        "/master-data/documents",
        {"document_code": code, "title": "Phase 7 Manual", "document_type": "manual"},
    )
    revision = _post(
        phase7_context,
        f"/master-data/documents/{code}/revisions",
        {"revision": "A", "content": content},
    )
    canonical = json.dumps(
        {"content": content}, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert revision["content_sha256"] == hashlib.sha256(canonical).hexdigest()
    assert revision["content_length"] == len(canonical)

    with get_db() as db:
        row = db.execute(
            "SELECT content_sha256, content_length FROM document_revisions WHERE id = ?",
            (revision["id"],),
        ).fetchone()
        with pytest.raises(Exception):
            db.execute(
                "UPDATE document_revisions SET content_sha256 = ? WHERE id = ?",
                ("0" * 64, revision["id"]),
            )
    assert dict(row)["content_sha256"] == revision["content_sha256"]


def test_object_checksum_mismatch_is_rejected_before_storage(phase7_context: dict) -> None:
    body = b"phase7-object-payload"
    response = phase7_context["client"].put(
        "/document-objects/manual.pdf",
        headers={
            **phase7_context["headers"],
            "Content-Type": "application/pdf",
            "X-Content-SHA256": "0" * 64,
        },
        content=body,
    )
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "OBJECT_CHECKSUM_MISMATCH"


def test_document_object_is_verified_again_on_every_read(
    phase7_context: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.object_storage import document_object_storage

    client = _ObjectClient()
    monkeypatch.setattr(settings, "object_storage_enabled", True)
    monkeypatch.setattr(settings, "object_storage_access_key", "phase7-test-access")
    monkeypatch.setattr(settings, "object_storage_secret_key", "phase7-test-secret")
    monkeypatch.setattr(document_object_storage, "_client", lambda: client)
    body = b"phase7-retrieval-integrity-payload"
    checksum = hashlib.sha256(body).hexdigest()

    stored = phase7_context["client"].put(
        "/document-objects/integrity-manual.pdf",
        headers={
            **phase7_context["headers"],
            "Content-Type": "application/pdf",
            "X-Content-SHA256": checksum,
        },
        content=body,
    )
    assert stored.status_code == 201, stored.text
    manifest = stored.json()
    retrieved = phase7_context["client"].get(
        f"/document-objects/{manifest['id']}",
        headers=phase7_context["headers"],
    )
    assert retrieved.status_code == 200, retrieved.text
    assert retrieved.content == body
    assert retrieved.headers["x-content-sha256"] == checksum
    assert retrieved.headers["x-object-integrity"] == "verified"

    client.objects[(manifest["bucket"], manifest["object_key"])] = body + b"-tampered"
    rejected = phase7_context["client"].get(
        f"/document-objects/{manifest['id']}",
        headers=phase7_context["headers"],
    )
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["code"] == "OBJECT_READBACK_CHECKSUM_MISMATCH"
    with get_db() as db:
        row = db.execute(
            "SELECT status FROM document_objects WHERE id = ?",
            (manifest["id"],),
        ).fetchone()
    assert dict(row)["status"] == "quarantined"


def test_retention_aggregates_before_controlled_raw_deletion(phase7_context: dict) -> None:
    code = f"P7-RETENTION-{uuid4().hex[:8].upper()}"
    sample_id = f"P7-RETENTION-SAMPLE-{uuid4().hex}"
    _signal(phase7_context, code)
    occurred_at = datetime.now(UTC) - timedelta(days=settings.telemetry_raw_retention_days + 1)
    _batch(
        phase7_context,
        batch_id=f"P7-RETENTION-BATCH-{uuid4().hex}",
        signal_code=code,
        sample_id=sample_id,
        sequence_no=1,
        source_timestamp=occurred_at,
    )

    completed = _post(
        phase7_context,
        "/telemetry/retention/run",
        {"reason": "phase7 test retention coverage"},
        expected=200,
    )
    assert completed["status"] == "completed"
    assert completed["raw_deleted"] >= 1
    assert completed["coverage"]["covered_windows"] >= 1
    with get_db() as db:
        raw = db.execute(
            "SELECT id FROM telemetry_measurements WHERE sample_id = ?",
            (sample_id,),
        ).fetchone()
        aggregate = db.execute(
            "SELECT sample_count FROM telemetry_aggregates_hourly "
            "WHERE signal_code = ? AND window_start = ?",
            (code, occurred_at.replace(minute=0, second=0, microsecond=0).isoformat()),
        ).fetchone()
    assert raw is None
    assert int(dict(aggregate)["sample_count"]) == 1


def test_retention_failure_preserves_raw_data_and_records_failure(
    phase7_context: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.domain.data_platform import DataPlatformError
    from app.repositories.data_platform import data_platform_repository

    code = f"P7-RETENTION-FAIL-{uuid4().hex[:8].upper()}"
    sample_id = f"P7-RETENTION-FAIL-SAMPLE-{uuid4().hex}"
    _signal(phase7_context, code)
    occurred_at = datetime.now(UTC) - timedelta(days=settings.telemetry_raw_retention_days + 1)
    _batch(
        phase7_context,
        batch_id=f"P7-RETENTION-FAIL-BATCH-{uuid4().hex}",
        signal_code=code,
        sample_id=sample_id,
        sequence_no=1,
        source_timestamp=occurred_at,
    )

    def fail_aggregation(payload: object) -> dict:
        del payload
        raise DataPlatformError(
            503,
            "TELEMETRY_AGGREGATION_FAILED",
            "injected aggregation failure",
        )

    monkeypatch.setattr(data_platform_repository, "aggregate_hourly", fail_aggregation)
    response = phase7_context["client"].post(
        "/telemetry/retention/run",
        headers=phase7_context["headers"],
        json={"reason": "phase7 preservation test"},
    )
    assert response.status_code == 503, response.text
    with get_db() as db:
        raw = db.execute(
            "SELECT id FROM telemetry_measurements WHERE sample_id = ?",
            (sample_id,),
        ).fetchone()
        run = db.execute(
            "SELECT status FROM telemetry_retention_runs "
            "WHERE reason = ? ORDER BY id DESC LIMIT 1",
            ("phase7 preservation test",),
        ).fetchone()
    assert raw is not None
    assert dict(run)["status"] == "failed"


def test_heartbeat_no_longer_appends_the_high_frequency_legacy_metric_stream(
    phase7_context: dict,
) -> None:
    before = len(store.metrics)
    response = phase7_context["client"].post(
        "/agents/turning-workshop-01/heartbeat",
        headers={"X-OGAS-Token": settings.node_ingest_token},
        json={
            "node_code": "turning-workshop-01",
            "status": "running",
            "metrics": {"cpu_usage": 20, "memory_usage": 30, "disk_usage": 40},
            "production": {
                "machine_code": "P7-LATHE-01",
                "workshop_type": "turning",
                "spindle_temp": 61.5,
            },
            "runtime": {
                "simulation_engine": "simpy",
                "runtime_source": "simulated",
                "run_id": "P7-HEARTBEAT-SEPARATION",
                "scenario_id": "P7-TELEMETRY-SEPARATION",
            },
        },
    )
    assert response.status_code == 200, response.text
    assert len(store.metrics) == before


def test_digital_twin_catalog_provisioning_is_idempotent() -> None:
    from app.repositories.data_platform import data_platform_repository

    first = data_platform_repository.provision_digital_twin_catalog("phase7-test")
    second = data_platform_repository.provision_digital_twin_catalog("phase7-test")

    assert first["equipment_created"] == 3
    assert first["signals_created"] == 5
    assert second == {
        "organization_units_created": 0,
        "equipment_created": 0,
        "signals_created": 0,
    }
