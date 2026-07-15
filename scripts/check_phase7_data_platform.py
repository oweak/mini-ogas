from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from check_phase1_database import read_env_value
from check_phase3_execution import ApiClient, GateFailure, _read_env_file

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GateFailure(message)


def _request_bytes(
    base_url: str,
    path: str,
    *,
    method: str,
    headers: dict[str, str],
    body: bytes | None = None,
    expected: tuple[int, ...] = (200,),
) -> tuple[bytes, dict[str, str]]:
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=90) as response:
            content = response.read()
            if response.status not in expected:
                raise GateFailure(
                    f"{method} {path} returned {response.status}, expected {expected}"
                )
            return content, {key.lower(): value for key, value in response.headers.items()}
    except HTTPError as exc:
        content = exc.read().decode("utf-8", errors="replace")
        raise GateFailure(f"{method} {path} returned {exc.code}: {content}") from exc


def _node_post(
    base_url: str,
    path: str,
    payload: dict[str, Any],
    node_token: str,
    *,
    expected: tuple[int, ...] = (200, 201),
) -> dict[str, Any]:
    content, _ = _request_bytes(
        base_url,
        path,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-OGAS-Token": node_token,
        },
        body=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        expected=expected,
    )
    return json.loads(content.decode("utf-8"))


def _set_scope(connection: Any, tenant_id: str, site_id: str) -> None:
    connection.execute(
        "SELECT set_config('app.tenant_id', %s, false), "
        "set_config('app.site_id', %s, false)",
        (tenant_id, site_id),
    )


def _database_snapshot(dsn: str, tenant_id: str, site_id: str) -> dict[str, Any]:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        _set_scope(connection, tenant_id, site_id)
        telemetry = connection.execute(
            """SELECT COUNT(*) AS row_count, COALESCE(MAX(id), 0) AS maximum_id,
                      MAX(source_timestamp) AS latest_at
               FROM telemetry.measurements
               WHERE tenant_id=%s AND site_id=%s""",
            (tenant_id, site_id),
        ).fetchone()
        legacy = connection.execute("SELECT COUNT(*) AS row_count FROM metrics").fetchone()
        return {
            "telemetry_rows": int(telemetry["row_count"]),
            "maximum_id": int(telemetry["maximum_id"]),
            "latest_at": str(telemetry["latest_at"] or ""),
            "legacy_metric_rows": int(legacy["row_count"]),
        }


def _verify_database_structure(
    dsn: str,
    tenant_id: str,
    site_id: str,
) -> dict[str, Any]:
    import psycopg
    from psycopg.rows import dict_row

    expected_migrations = {
        "2026.07.14-phase7-data-platform",
        "2026.07.14-phase7-document-integrity",
        "2026.07.14-phase7-invariant-guards",
        "2026.07.14-phase7-retention-partition-guard",
    }
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        _set_scope(connection, tenant_id, site_id)
        migrations = connection.execute(
            "SELECT version, checksum FROM schema_migrations WHERE version = ANY(%s)",
            (list(expected_migrations),),
        ).fetchall()
        versions = {str(row["version"]) for row in migrations if row["checksum"]}
        _require(versions == expected_migrations, "Phase 7 checksum migrations are incomplete")
        catalog = connection.execute(
            """SELECT
                   (SELECT COUNT(*) FROM equipment
                    WHERE tenant_id=%s AND site_id=%s
                      AND equipment_code IN ('LATHE-01','MILL-02','GRIND-01')) AS equipment,
                   (SELECT COUNT(*) FROM telemetry.signal_definitions
                    WHERE tenant_id=%s AND site_id=%s AND active) AS signals""",
            (tenant_id, site_id, tenant_id, site_id),
        ).fetchone()
        partitions = connection.execute(
            """SELECT DISTINCT tableoid::regclass::text AS partition_name
               FROM telemetry.measurements
               WHERE tenant_id=%s AND site_id=%s ORDER BY partition_name""",
            (tenant_id, site_id),
        ).fetchall()
    _require(int(catalog["equipment"]) == 3, "digital-twin equipment catalog is incomplete")
    _require(int(catalog["signals"]) >= 5, "typed signal catalog is incomplete")
    return {
        "migrations": sorted(versions),
        "equipment": int(catalog["equipment"]),
        "signals": int(catalog["signals"]),
        "partitions": [str(row["partition_name"]) for row in partitions],
    }


def _verify_retained_sample(
    dsn: str,
    tenant_id: str,
    site_id: str,
    sample_id: str,
    source_id: str,
    window_start: datetime,
) -> dict[str, Any]:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        _set_scope(connection, tenant_id, site_id)
        raw = connection.execute(
            """SELECT id FROM telemetry.measurements
               WHERE tenant_id=%s AND site_id=%s AND sample_id=%s""",
            (tenant_id, site_id, sample_id),
        ).fetchone()
        aggregate = connection.execute(
            """SELECT sample_count, good_count, uncertain_count, bad_count
               FROM telemetry.aggregates_hourly
               WHERE tenant_id=%s AND site_id=%s AND source_id=%s
                 AND signal_code='SPINDLE-TEMPERATURE' AND window_start=%s""",
            (tenant_id, site_id, source_id, window_start),
        ).fetchone()
        run = connection.execute(
            """SELECT status, raw_deleted FROM telemetry.retention_runs
               WHERE tenant_id=%s AND site_id=%s
               ORDER BY id DESC LIMIT 1""",
            (tenant_id, site_id),
        ).fetchone()
    _require(raw is None, "eligible raw telemetry survived a completed retention run")
    _require(aggregate is not None, "hourly aggregate coverage is absent after retention")
    _require(run is not None and run["status"] == "completed", "retention run did not complete")
    return {
        "aggregate_sample_count": int(aggregate["sample_count"]),
        "retention_status": str(run["status"]),
        "raw_deleted": int(run["raw_deleted"]),
    }


def run_gate(
    api_url: str,
    runtime_root: Path,
    tenant_id: str,
    site_id: str,
    raw_retention_days: int,
) -> dict[str, Any]:
    auth = _read_env_file(runtime_root / "auth.env")
    redis_env = _read_env_file(runtime_root / "data-platform" / "redis" / "redis.env")
    minio_env = _read_env_file(runtime_root / "data-platform" / "minio" / "minio.env")
    password = auth.get("AUTH_BOOTSTRAP_PASSWORD", "")
    dsn = read_env_value(runtime_root / "postgres.env", "POSTGRES_DSN")
    _require(bool(password and dsn), "runtime administrator credential or PostgreSQL DSN missing")

    client = ApiClient(api_url)
    login = client.post(
        "/auth/login",
        {"operator": "admin", "password": password},
        expected=(200,),
    )
    client.token = str(login.get("access_token") or "")
    _require(bool(client.token), "administrator login returned no bearer token")
    prefix = f"P7G{datetime.now(UTC):%m%d%H%M%S}{uuid4().hex[:6].upper()}"
    validation_source = f"{prefix.lower()}-validation-node"
    issued = client.post(
        f"/security/node-credentials/{validation_source}/rotate",
        {},
        expected=(200,),
    )
    node_token = str(issued.get("token") or "")
    _require(
        bool(node_token) and issued.get("node_code") == validation_source,
        "temporary telemetry Principal did not return a bound node credential",
    )

    structure = _verify_database_structure(dsn, tenant_id, site_id)
    quality = client.get("/telemetry/quality/summary")
    _require(
        quality.get("source_of_truth") == "postgresql-historian",
        "quality API does not identify the PostgreSQL historian authority",
    )
    _require(bool(quality.get("generated_at")), "quality API has no generation timestamp")
    _require(
        all(item.get("source") in {None, "simulated"} for item in quality.get("signals", [])),
        "digital-twin quality view contains an unlabelled or non-simulated source",
    )
    expected_sources = {
        "turning-workshop-01",
        "milling-workshop-01",
        "grinding-workshop-01",
    }
    expected_signals = {
        "SPINDLE-TEMPERATURE",
        "TOOL-WEAR-LEVEL",
        "UTILIZATION",
        "DEFECT-RATE",
        "ACTUAL-RATE",
    }
    observed_streams = {
        (str(item.get("source_id")), str(item.get("signal_code")))
        for item in quality.get("signals", [])
        if item.get("source_id") in expected_sources
    }
    expected_streams = {
        (source_id, signal_code)
        for source_id in expected_sources
        for signal_code in expected_signals
    }
    _require(
        expected_streams.issubset(observed_streams),
        "quality API collapsed or omitted one or more production node signal streams",
    )

    before = _database_snapshot(dsn, tenant_id, site_id)
    time.sleep(12)
    after = _database_snapshot(dsn, tenant_id, site_id)
    telemetry_delta = after["telemetry_rows"] - before["telemetry_rows"]
    legacy_delta = after["legacy_metric_rows"] - before["legacy_metric_rows"]
    _require(telemetry_delta > 0, "typed telemetry did not grow while node agents were running")
    _require(legacy_delta == 0, "heartbeat telemetry polluted the legacy business metrics table")

    benchmark_at = datetime.now(UTC) - timedelta(days=raw_retention_days + 1)
    benchmark_source = validation_source
    benchmark_samples = [
        {
            "sample_id": f"{prefix}-LOAD-{index:04d}",
            "signal_code": "SPINDLE-TEMPERATURE",
            "value": 55.0 + (index % 20) / 10,
            "unit": "Cel",
            "mapping_version": 1,
            "sequence_no": 10_000 + index,
            "source_timestamp": (benchmark_at + timedelta(milliseconds=index)).isoformat(),
            "simulation_time": (benchmark_at + timedelta(milliseconds=index)).isoformat(),
        }
        for index in range(200)
    ]
    benchmark_payload = {
        "batch_id": f"{prefix}-LOAD-BATCH",
        "source": "simulated",
        "source_id": benchmark_source,
        "equipment_code": "LATHE-01",
        "edge_received_at": datetime.now(UTC).isoformat(),
        "samples": benchmark_samples,
    }
    started = time.perf_counter()
    benchmark = _node_post(api_url, "/telemetry/batches", benchmark_payload, node_token)
    ingest_ms = round((time.perf_counter() - started) * 1_000, 2)
    accepted = sum(int(value) for value in benchmark.get("counts", {}).values())
    _require(accepted == 200, "200-sample telemetry benchmark was not fully classified")
    replay = _node_post(
        api_url,
        "/telemetry/batches",
        benchmark_payload,
        node_token,
        expected=(200,),
    )
    _require(bool(replay.get("idempotent_replay")), "telemetry retry was not idempotent")

    redis_password = redis_env.get("REDIS_PASSWORD", "")
    _require(bool(redis_password), "Redis runtime credential is missing")
    from redis import Redis

    redis = Redis.from_url(
        f"redis://:{redis_password}@127.0.0.1:6379/0",
        decode_responses=True,
        socket_timeout=5,
    )
    _require(bool(redis.ping()), "Redis projection runtime did not answer PING")
    first_rebuild = client.post(
        "/telemetry/projection/rebuild",
        {"reason": f"{prefix} rebuildability gate"},
        expected=(200,),
    )
    root = f"miniogas:{tenant_id}:{site_id}:telemetry"
    first_generation = str(first_rebuild["generation"])
    first_keys = list(redis.scan_iter(match=f"{root}:{first_generation}:latest:*"))
    _require(
        len(first_keys) == int(first_rebuild["projected_key_count"]),
        "Redis key count differs from the durable projection checkpoint",
    )
    if first_keys:
        redis.delete(*first_keys)
    _require(
        not list(redis.scan_iter(match=f"{root}:{first_generation}:latest:*")),
        "Redis projection destruction test did not remove the active generation",
    )
    second_rebuild = client.post(
        "/telemetry/projection/rebuild",
        {"reason": f"{prefix} rebuild after projection loss"},
        expected=(200,),
    )
    second_generation = str(second_rebuild["generation"])
    second_keys = list(redis.scan_iter(match=f"{root}:{second_generation}:latest:*"))
    _require(first_generation != second_generation, "Redis rebuild reused an old generation")
    _require(
        len(second_keys) == int(second_rebuild["projected_key_count"]),
        "Redis projection was not rebuilt completely from PostgreSQL",
    )
    _require(
        redis.get(f"{root}:active-generation") == second_generation,
        "Redis active-generation pointer was not switched atomically",
    )

    object_body = f"{prefix} controlled document object".encode("utf-8")
    object_sha = hashlib.sha256(object_body).hexdigest()
    uploaded_raw, _ = _request_bytes(
        api_url,
        f"/document-objects/{prefix.lower()}-manual.txt",
        method="PUT",
        headers={
            "Authorization": f"Bearer {client.token}",
            "Content-Type": "text/plain; charset=utf-8",
            "X-Content-SHA256": object_sha,
        },
        body=object_body,
        expected=(201,),
    )
    manifest = json.loads(uploaded_raw.decode("utf-8"))
    retrieved, headers = _request_bytes(
        api_url,
        f"/document-objects/{manifest['id']}",
        method="GET",
        headers={"Authorization": f"Bearer {client.token}"},
    )
    _require(retrieved == object_body, "object API did not return the verified bytes")
    _require(headers.get("x-content-sha256") == object_sha, "object API checksum is absent")

    from minio import Minio

    minio_user = minio_env.get("MINIO_ROOT_USER", "")
    minio_password = minio_env.get("MINIO_ROOT_PASSWORD", "")
    _require(bool(minio_user and minio_password), "MinIO runtime credential is missing")
    minio = Minio(
        "127.0.0.1:9000",
        access_key=minio_user,
        secret_key=minio_password,
        secure=False,
    )
    response = minio.get_object(str(manifest["bucket"]), str(manifest["object_key"]))
    try:
        direct_bytes = response.read()
    finally:
        response.close()
        response.release_conn()
    _require(hashlib.sha256(direct_bytes).hexdigest() == object_sha, "MinIO bytes failed SHA-256")
    document_code = f"{prefix}-DOC"
    client.post(
        "/master-data/documents",
        {"document_code": document_code, "title": prefix, "document_type": "manual"},
        expected=(201,),
    )
    revision = client.post(
        f"/master-data/documents/{document_code}/revisions",
        {"revision": "A", "object_id": int(manifest["id"])},
        expected=(201,),
    )
    _require(revision.get("content_sha256") == object_sha, "document revision lost checksum")
    _require(int(revision.get("content_length") or -1) == len(object_body), "length mismatch")

    old_at = datetime.now(UTC) - timedelta(days=raw_retention_days + 1)
    retention_source = validation_source
    retention_sample = f"{prefix}-RETENTION-SAMPLE"
    _node_post(
        api_url,
        "/telemetry/batches",
        {
            "batch_id": f"{prefix}-RETENTION-BATCH",
            "source": "simulated",
            "source_id": retention_source,
            "equipment_code": "LATHE-01",
            "edge_received_at": datetime.now(UTC).isoformat(),
            "samples": [
                {
                    "sample_id": retention_sample,
                    "signal_code": "SPINDLE-TEMPERATURE",
                    "value": 61.25,
                    "unit": "Cel",
                    "mapping_version": 1,
                    "sequence_no": 1,
                    "source_timestamp": old_at.isoformat(),
                    "simulation_time": old_at.isoformat(),
                }
            ],
        },
        node_token,
    )
    retention = client.post(
        "/telemetry/retention/run",
        {"reason": f"{prefix} aggregate-before-delete gate"},
        expected=(200,),
    )
    _require(retention.get("status") == "completed", "retention endpoint did not complete")
    retention_db = _verify_retained_sample(
        dsn,
        tenant_id,
        site_id,
        retention_sample,
        retention_source,
        old_at.replace(minute=0, second=0, microsecond=0),
    )
    post_retention_rebuild = client.post(
        "/telemetry/projection/rebuild",
        {"reason": f"{prefix} post-retention consistency rebuild"},
        expected=(200,),
    )
    final_generation = str(post_retention_rebuild["generation"])
    final_keys = list(redis.scan_iter(match=f"{root}:{final_generation}:latest:*"))
    _require(
        redis.get(f"{root}:active-generation") == final_generation,
        "post-retention Redis generation was not activated",
    )
    _require(
        len(final_keys) == int(post_retention_rebuild["projected_key_count"]),
        "post-retention Redis projection key count does not match its checkpoint",
    )
    _require(
        not any(source_id in key for source_id in (benchmark_source, retention_source) for key in final_keys),
        "post-retention Redis projection retained a deleted validation stream",
    )
    latest_after_retention = client.get("/telemetry/latest")
    _require(
        not any(
            item.get("source_id") in {benchmark_source, retention_source}
            for item in latest_after_retention.get("signals", [])
        ),
        "validation telemetry survived the aggregate-before-delete retention cycle",
    )
    revoked = client.post(
        f"/security/node-credentials/{validation_source}/revoke",
        {},
        expected=(200,),
    )
    _require(
        int(revoked.get("revoked_credentials") or 0) >= 1,
        "temporary telemetry Principal credential was not revoked",
    )

    return {
        "status": "PASS",
        "validation_prefix": prefix,
        "catalog": structure,
        "telemetry_separation": {
            "measurement_delta": telemetry_delta,
            "legacy_metric_delta": legacy_delta,
            "source_of_truth": quality["source_of_truth"],
            "quality_counts": quality.get("counts", {}),
            "production_streams": len(expected_streams),
        },
        "benchmark": {
            "samples": 200,
            "ingest_ms": ingest_ms,
            "idempotent_replay": True,
        },
        "redis_rebuild": {
            "destroyed_generation": first_generation,
            "recovery_generation": second_generation,
            "post_retention_generation": final_generation,
            "projected_keys": len(final_keys),
            "authority": post_retention_rebuild["authority"],
        },
        "object_integrity": {
            "object_id": int(manifest["id"]),
            "sha256": object_sha,
            "bytes": len(object_body),
            "document_revision_id": int(revision["id"]),
        },
        "retention": retention_db,
        "temporary_principal": {
            "principal_id": issued.get("principal_id"),
            "credential_revoked": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the live Phase 7 data-platform gate")
    parser.add_argument("--api-url", default="http://127.0.0.1:8080")
    parser.add_argument("--runtime-root", type=Path, default=Path(r"D:\MiniOGAS-VMs"))
    parser.add_argument("--tenant-id", default="tenant-local")
    parser.add_argument("--site-id", default="site-digital-twin")
    parser.add_argument("--raw-retention-days", type=int, default=7)
    args = parser.parse_args()
    try:
        result = run_gate(
            args.api_url,
            args.runtime_root,
            args.tenant_id,
            args.site_id,
            args.raw_retention_days,
        )
    except (GateFailure, OSError, ValueError, KeyError) as exc:
        print(
            json.dumps(
                {"status": "FAIL", "error": str(exc), "error_type": type(exc).__name__},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
