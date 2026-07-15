from __future__ import annotations

import hashlib
from typing import Any

from .migrations import Migration

PHASE7_DATA_PLATFORM_VERSION = "2026.07.14-phase7-data-platform"
PHASE7_DOCUMENT_INTEGRITY_VERSION = "2026.07.14-phase7-document-integrity"
PHASE7_INVARIANT_GUARDS_VERSION = "2026.07.14-phase7-invariant-guards"
PHASE7_RETENTION_PARTITION_GUARD_VERSION = (
    "2026.07.14-phase7-retention-partition-guard"
)

SQLITE_PHASE7_TABLES = (
    "telemetry_signal_definitions",
    "telemetry_ingest_batches",
    "telemetry_sample_receipts",
    "telemetry_measurements",
    "telemetry_quality_events",
    "telemetry_aggregates_hourly",
    "telemetry_projection_checkpoints",
        "telemetry_retention_runs",
        "telemetry_operation_context",
    "document_objects",
    "object_integrity_events",
)

POSTGRES_PHASE7_SCOPED_TABLES = (
    "telemetry.signal_definitions",
    "telemetry.ingest_batches",
    "telemetry.sample_receipts",
    "telemetry.measurements",
    "telemetry.measurements_2025",
    "telemetry.measurements_2026",
    "telemetry.measurements_2027",
    "telemetry.measurements_default",
    "telemetry.quality_events",
    "telemetry.aggregates_hourly",
    "telemetry.projection_checkpoints",
    "telemetry.retention_runs",
    "documents.objects",
    "documents.integrity_events",
)


def _sqlite_data_platform(connection: Any) -> None:
    statements = (
        """CREATE TABLE IF NOT EXISTS telemetry_signal_definitions (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               signal_code TEXT NOT NULL,
               display_name TEXT NOT NULL,
               value_type TEXT NOT NULL CHECK (value_type IN ('number','integer','boolean','text')),
               unit TEXT NOT NULL DEFAULT '',
               minimum REAL,
               maximum REAL,
               freshness_threshold_ms INTEGER NOT NULL CHECK (freshness_threshold_ms > 0),
               allowed_sources_json TEXT NOT NULL,
               mapping_version INTEGER NOT NULL CHECK (mapping_version > 0),
               active INTEGER NOT NULL DEFAULT 1,
               created_by TEXT NOT NULL,
               created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
               UNIQUE (tenant_id, site_id, signal_code)
           )""",
        """CREATE TABLE IF NOT EXISTS telemetry_ingest_batches (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               batch_id TEXT NOT NULL,
               payload_hash TEXT NOT NULL,
               source TEXT NOT NULL,
               source_id TEXT NOT NULL,
               equipment_code TEXT NOT NULL,
               sample_count INTEGER NOT NULL,
               response_json TEXT NOT NULL DEFAULT '',
               ingested_by TEXT NOT NULL,
               central_ingested_at TEXT NOT NULL,
               UNIQUE (tenant_id, site_id, batch_id)
           )""",
        """CREATE TABLE IF NOT EXISTS telemetry_sample_receipts (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               sample_id TEXT NOT NULL,
               payload_hash TEXT NOT NULL,
               batch_id TEXT NOT NULL,
               source_id TEXT NOT NULL,
               signal_code TEXT NOT NULL,
               sequence_no INTEGER NOT NULL,
               source_timestamp TEXT NOT NULL,
               created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
               UNIQUE (tenant_id, site_id, sample_id),
               UNIQUE (tenant_id, site_id, source_id, signal_code, sequence_no)
           )""",
        """CREATE TABLE IF NOT EXISTS telemetry_measurements (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               sample_id TEXT NOT NULL,
               batch_id TEXT NOT NULL,
               source TEXT NOT NULL,
               source_id TEXT NOT NULL,
               equipment_code TEXT NOT NULL,
               signal_code TEXT NOT NULL,
               numeric_value REAL,
               text_value TEXT,
               unit TEXT NOT NULL,
               quality_code TEXT NOT NULL CHECK (quality_code IN ('good','uncertain','bad')),
               quality_reason TEXT NOT NULL DEFAULT '',
               mapping_version INTEGER NOT NULL,
               sequence_no INTEGER NOT NULL,
               source_timestamp TEXT NOT NULL,
               edge_received_at TEXT NOT NULL,
               central_ingested_at TEXT NOT NULL,
               processed_at TEXT NOT NULL,
               simulation_time TEXT,
               is_manual INTEGER NOT NULL DEFAULT 0,
               is_corrected INTEGER NOT NULL DEFAULT 0,
               correction_reason TEXT NOT NULL DEFAULT ''
           )""",
        """CREATE TABLE IF NOT EXISTS telemetry_quality_events (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               sample_id TEXT,
               source_id TEXT NOT NULL,
               signal_code TEXT NOT NULL,
               quality_code TEXT NOT NULL,
               reason_code TEXT NOT NULL,
               detail_json TEXT NOT NULL,
               occurred_at TEXT NOT NULL
           )""",
        """CREATE TABLE IF NOT EXISTS telemetry_aggregates_hourly (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               source_id TEXT NOT NULL,
               signal_code TEXT NOT NULL,
               window_start TEXT NOT NULL,
               window_end TEXT NOT NULL,
               sample_count INTEGER NOT NULL,
               good_count INTEGER NOT NULL,
               uncertain_count INTEGER NOT NULL,
               bad_count INTEGER NOT NULL,
               minimum REAL,
               maximum REAL,
               average REAL,
               generated_at TEXT NOT NULL,
               UNIQUE (tenant_id, site_id, source_id, signal_code, window_start)
           )""",
        """CREATE TABLE IF NOT EXISTS telemetry_projection_checkpoints (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               generation TEXT NOT NULL,
               provider TEXT NOT NULL,
               measurement_count INTEGER NOT NULL,
               projected_key_count INTEGER NOT NULL,
               max_measurement_id INTEGER NOT NULL,
               status TEXT NOT NULL,
               reason TEXT NOT NULL,
               created_by TEXT NOT NULL,
               created_at TEXT NOT NULL,
               UNIQUE (tenant_id, site_id, generation)
           )""",
        """CREATE TABLE IF NOT EXISTS telemetry_retention_runs (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               raw_cutoff TEXT NOT NULL,
               aggregate_cutoff TEXT NOT NULL,
               raw_deleted INTEGER NOT NULL DEFAULT 0,
               aggregate_deleted INTEGER NOT NULL DEFAULT 0,
               status TEXT NOT NULL,
               reason TEXT NOT NULL,
               created_by TEXT NOT NULL,
               started_at TEXT NOT NULL,
               completed_at TEXT
           )""",
        """CREATE TABLE IF NOT EXISTS telemetry_operation_context (
               singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
               retention_enabled INTEGER NOT NULL DEFAULT 0
                   CHECK (retention_enabled IN (0, 1))
           )""",
        """CREATE TABLE IF NOT EXISTS document_objects (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               object_key TEXT NOT NULL,
               bucket TEXT NOT NULL,
               provider TEXT NOT NULL,
               content_sha256 TEXT NOT NULL,
               byte_length INTEGER NOT NULL CHECK (byte_length >= 0),
               content_type TEXT NOT NULL,
               original_name TEXT NOT NULL,
               etag TEXT NOT NULL DEFAULT '',
               storage_version TEXT NOT NULL DEFAULT '',
               status TEXT NOT NULL CHECK (status IN ('pending','available','quarantined')),
               created_by TEXT NOT NULL,
               created_at TEXT NOT NULL,
               verified_at TEXT,
               UNIQUE (tenant_id, site_id, object_key)
           )""",
        """CREATE TABLE IF NOT EXISTS object_integrity_events (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               object_id INTEGER NOT NULL REFERENCES document_objects(id),
               event_type TEXT NOT NULL,
               expected_sha256 TEXT NOT NULL,
               observed_sha256 TEXT NOT NULL,
               byte_length INTEGER NOT NULL,
               actor TEXT NOT NULL,
               created_at TEXT NOT NULL
           )""",
    )
    for statement in statements:
        connection.execute(statement)
    connection.execute(
        """INSERT INTO telemetry_operation_context (singleton, retention_enabled)
           VALUES (1, 0) ON CONFLICT(singleton) DO NOTHING"""
    )
    indexes = (
        "CREATE INDEX IF NOT EXISTS idx_telemetry_measurements_window ON telemetry_measurements(tenant_id, site_id, source_id, signal_code, source_timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_telemetry_measurements_quality ON telemetry_measurements(tenant_id, site_id, quality_code, processed_at)",
        "CREATE INDEX IF NOT EXISTS idx_telemetry_quality_events_reason ON telemetry_quality_events(tenant_id, site_id, reason_code, occurred_at)",
    )
    for statement in indexes:
        connection.execute(statement)


def _postgres_data_platform(connection: Any) -> None:
    connection.execute("CREATE SCHEMA IF NOT EXISTS telemetry")
    connection.execute("CREATE SCHEMA IF NOT EXISTS documents")
    statements = (
        """CREATE TABLE IF NOT EXISTS telemetry.signal_definitions (
               id BIGSERIAL PRIMARY KEY,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               signal_code TEXT NOT NULL,
               display_name TEXT NOT NULL,
               value_type TEXT NOT NULL CHECK (value_type IN ('number','integer','boolean','text')),
               unit TEXT NOT NULL DEFAULT '',
               minimum DOUBLE PRECISION,
               maximum DOUBLE PRECISION,
               freshness_threshold_ms BIGINT NOT NULL CHECK (freshness_threshold_ms > 0),
               allowed_sources_json TEXT NOT NULL,
               mapping_version INTEGER NOT NULL CHECK (mapping_version > 0),
               active BOOLEAN NOT NULL DEFAULT TRUE,
               created_by TEXT NOT NULL,
               created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
               UNIQUE (tenant_id, site_id, signal_code)
           )""",
        """CREATE TABLE IF NOT EXISTS telemetry.ingest_batches (
               id BIGSERIAL PRIMARY KEY,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               batch_id TEXT NOT NULL,
               payload_hash TEXT NOT NULL,
               source TEXT NOT NULL,
               source_id TEXT NOT NULL,
               equipment_code TEXT NOT NULL,
               sample_count INTEGER NOT NULL,
               response_json TEXT NOT NULL DEFAULT '',
               ingested_by TEXT NOT NULL,
               central_ingested_at TIMESTAMPTZ NOT NULL,
               UNIQUE (tenant_id, site_id, batch_id)
           )""",
        """CREATE TABLE IF NOT EXISTS telemetry.sample_receipts (
               id BIGSERIAL PRIMARY KEY,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               sample_id TEXT NOT NULL,
               payload_hash TEXT NOT NULL,
               batch_id TEXT NOT NULL,
               source_id TEXT NOT NULL,
               signal_code TEXT NOT NULL,
               sequence_no BIGINT NOT NULL,
               source_timestamp TIMESTAMPTZ NOT NULL,
               created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
               UNIQUE (tenant_id, site_id, sample_id),
               UNIQUE (tenant_id, site_id, source_id, signal_code, sequence_no)
           )""",
        """CREATE TABLE IF NOT EXISTS telemetry.measurements (
               id BIGINT GENERATED BY DEFAULT AS IDENTITY,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               sample_id TEXT NOT NULL,
               batch_id TEXT NOT NULL,
               source TEXT NOT NULL,
               source_id TEXT NOT NULL,
               equipment_code TEXT NOT NULL,
               signal_code TEXT NOT NULL,
               numeric_value DOUBLE PRECISION,
               text_value TEXT,
               unit TEXT NOT NULL,
               quality_code TEXT NOT NULL CHECK (quality_code IN ('good','uncertain','bad')),
               quality_reason TEXT NOT NULL DEFAULT '',
               mapping_version INTEGER NOT NULL,
               sequence_no BIGINT NOT NULL,
               source_timestamp TIMESTAMPTZ NOT NULL,
               edge_received_at TIMESTAMPTZ NOT NULL,
               central_ingested_at TIMESTAMPTZ NOT NULL,
               processed_at TIMESTAMPTZ NOT NULL,
               simulation_time TIMESTAMPTZ,
               is_manual BOOLEAN NOT NULL DEFAULT FALSE,
               is_corrected BOOLEAN NOT NULL DEFAULT FALSE,
               correction_reason TEXT NOT NULL DEFAULT '',
               PRIMARY KEY (id, source_timestamp)
           ) PARTITION BY RANGE (source_timestamp)""",
        """CREATE TABLE IF NOT EXISTS telemetry.measurements_2025
               PARTITION OF telemetry.measurements
               FOR VALUES FROM ('2025-01-01T00:00:00Z') TO ('2026-01-01T00:00:00Z')""",
        """CREATE TABLE IF NOT EXISTS telemetry.measurements_2026
               PARTITION OF telemetry.measurements
               FOR VALUES FROM ('2026-01-01T00:00:00Z') TO ('2027-01-01T00:00:00Z')""",
        """CREATE TABLE IF NOT EXISTS telemetry.measurements_2027
               PARTITION OF telemetry.measurements
               FOR VALUES FROM ('2027-01-01T00:00:00Z') TO ('2028-01-01T00:00:00Z')""",
        """CREATE TABLE IF NOT EXISTS telemetry.measurements_default
               PARTITION OF telemetry.measurements DEFAULT""",
        """CREATE TABLE IF NOT EXISTS telemetry.quality_events (
               id BIGSERIAL PRIMARY KEY,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               sample_id TEXT,
               source_id TEXT NOT NULL,
               signal_code TEXT NOT NULL,
               quality_code TEXT NOT NULL,
               reason_code TEXT NOT NULL,
               detail_json TEXT NOT NULL,
               occurred_at TIMESTAMPTZ NOT NULL
           )""",
        """CREATE TABLE IF NOT EXISTS telemetry.aggregates_hourly (
               id BIGSERIAL PRIMARY KEY,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               source_id TEXT NOT NULL,
               signal_code TEXT NOT NULL,
               window_start TIMESTAMPTZ NOT NULL,
               window_end TIMESTAMPTZ NOT NULL,
               sample_count BIGINT NOT NULL,
               good_count BIGINT NOT NULL,
               uncertain_count BIGINT NOT NULL,
               bad_count BIGINT NOT NULL,
               minimum DOUBLE PRECISION,
               maximum DOUBLE PRECISION,
               average DOUBLE PRECISION,
               generated_at TIMESTAMPTZ NOT NULL,
               UNIQUE (tenant_id, site_id, source_id, signal_code, window_start)
           )""",
        """CREATE TABLE IF NOT EXISTS telemetry.projection_checkpoints (
               id BIGSERIAL PRIMARY KEY,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               generation TEXT NOT NULL,
               provider TEXT NOT NULL,
               measurement_count BIGINT NOT NULL,
               projected_key_count BIGINT NOT NULL,
               max_measurement_id BIGINT NOT NULL,
               status TEXT NOT NULL,
               reason TEXT NOT NULL,
               created_by TEXT NOT NULL,
               created_at TIMESTAMPTZ NOT NULL,
               UNIQUE (tenant_id, site_id, generation)
           )""",
        """CREATE TABLE IF NOT EXISTS telemetry.retention_runs (
               id BIGSERIAL PRIMARY KEY,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               raw_cutoff TIMESTAMPTZ NOT NULL,
               aggregate_cutoff TIMESTAMPTZ NOT NULL,
               raw_deleted BIGINT NOT NULL DEFAULT 0,
               aggregate_deleted BIGINT NOT NULL DEFAULT 0,
               status TEXT NOT NULL,
               reason TEXT NOT NULL,
               created_by TEXT NOT NULL,
               started_at TIMESTAMPTZ NOT NULL,
               completed_at TIMESTAMPTZ
           )""",
        """CREATE TABLE IF NOT EXISTS documents.objects (
               id BIGSERIAL PRIMARY KEY,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               object_key TEXT NOT NULL,
               bucket TEXT NOT NULL,
               provider TEXT NOT NULL,
               content_sha256 TEXT NOT NULL,
               byte_length BIGINT NOT NULL CHECK (byte_length >= 0),
               content_type TEXT NOT NULL,
               original_name TEXT NOT NULL,
               etag TEXT NOT NULL DEFAULT '',
               storage_version TEXT NOT NULL DEFAULT '',
               status TEXT NOT NULL CHECK (status IN ('pending','available','quarantined')),
               created_by TEXT NOT NULL,
               created_at TIMESTAMPTZ NOT NULL,
               verified_at TIMESTAMPTZ,
               UNIQUE (tenant_id, site_id, object_key)
           )""",
        """CREATE TABLE IF NOT EXISTS documents.integrity_events (
               id BIGSERIAL PRIMARY KEY,
               tenant_id TEXT NOT NULL,
               site_id TEXT NOT NULL,
               object_id BIGINT NOT NULL REFERENCES documents.objects(id),
               event_type TEXT NOT NULL,
               expected_sha256 TEXT NOT NULL,
               observed_sha256 TEXT NOT NULL,
               byte_length BIGINT NOT NULL,
               actor TEXT NOT NULL,
               created_at TIMESTAMPTZ NOT NULL
           )""",
    )
    for statement in statements:
        connection.execute(statement)
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_telemetry_measurements_window "
        "ON telemetry.measurements(tenant_id, site_id, source_id, signal_code, source_timestamp)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_telemetry_measurements_quality "
        "ON telemetry.measurements(tenant_id, site_id, quality_code, processed_at)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_telemetry_quality_events_reason "
        "ON telemetry.quality_events(tenant_id, site_id, reason_code, occurred_at)"
    )
    for table_name in POSTGRES_PHASE7_SCOPED_TABLES:
        connection.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        connection.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
        policy_name = "miniogas_scope"
        connection.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table_name}")
        connection.execute(
            f"""CREATE POLICY {policy_name} ON {table_name}
                USING (
                    tenant_id = current_setting('app.tenant_id', true)
                    AND site_id = current_setting('app.site_id', true)
                )
                WITH CHECK (
                    tenant_id = current_setting('app.tenant_id', true)
                    AND site_id = current_setting('app.site_id', true)
                )"""
        )


def _sqlite_columns(connection: Any, table_name: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _backfill_document_integrity(connection: Any) -> None:
    rows = connection.execute("SELECT id, content_json FROM document_revisions").fetchall()
    for row in rows:
        if hasattr(row, "keys"):
            identifier = int(row["id"])
            content = str(row["content_json"])
        else:
            identifier = int(row[0])
            content = str(row[1])
        encoded = content.encode("utf-8")
        connection.execute(
            "UPDATE document_revisions SET content_sha256=?, content_length=? WHERE id=?",
            (hashlib.sha256(encoded).hexdigest(), len(encoded), identifier),
        )


def _sqlite_document_integrity(connection: Any) -> None:
    columns = _sqlite_columns(connection, "document_revisions")
    if "content_sha256" not in columns:
        connection.execute(
            "ALTER TABLE document_revisions ADD COLUMN content_sha256 TEXT NOT NULL DEFAULT ''"
        )
    if "content_length" not in columns:
        connection.execute(
            "ALTER TABLE document_revisions ADD COLUMN content_length INTEGER NOT NULL DEFAULT 0"
        )
    if "object_id" not in columns:
        connection.execute("ALTER TABLE document_revisions ADD COLUMN object_id INTEGER")
    _backfill_document_integrity(connection)


def _postgres_document_integrity(connection: Any) -> None:
    connection.execute(
        "ALTER TABLE document_revisions ADD COLUMN IF NOT EXISTS content_sha256 TEXT NOT NULL DEFAULT ''"
    )
    connection.execute(
        "ALTER TABLE document_revisions ADD COLUMN IF NOT EXISTS content_length BIGINT NOT NULL DEFAULT 0"
    )
    connection.execute("ALTER TABLE document_revisions ADD COLUMN IF NOT EXISTS object_id BIGINT")
    _backfill_document_integrity(connection)
    connection.execute(
        """DO $$ BEGIN
               IF NOT EXISTS (
                   SELECT 1 FROM pg_constraint WHERE conname='fk_document_revision_object'
               ) THEN
                   ALTER TABLE document_revisions
                   ADD CONSTRAINT fk_document_revision_object
                   FOREIGN KEY (object_id) REFERENCES documents.objects(id);
               END IF;
           END $$"""
    )
    connection.execute(
        """DO $$ BEGIN
               IF NOT EXISTS (
                   SELECT 1 FROM pg_constraint WHERE conname='ck_document_revision_sha256'
               ) THEN
                   ALTER TABLE document_revisions
                   ADD CONSTRAINT ck_document_revision_sha256
                   CHECK (content_sha256 ~ '^[0-9a-f]{64}$');
               END IF;
           END $$"""
    )


def _sqlite_guards(connection: Any) -> None:
    append_only = (
        "telemetry_sample_receipts",
        "telemetry_quality_events",
        "object_integrity_events",
    )
    for table_name in append_only:
        connection.execute(
            f"""CREATE TRIGGER IF NOT EXISTS trg_{table_name}_no_update
                BEFORE UPDATE ON {table_name}
                BEGIN SELECT RAISE(ABORT, '{table_name} is append-only'); END"""
        )
        connection.execute(
            f"""CREATE TRIGGER IF NOT EXISTS trg_{table_name}_no_delete
                BEFORE DELETE ON {table_name}
                BEGIN SELECT RAISE(ABORT, '{table_name} is append-only'); END"""
        )
    connection.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_telemetry_measurements_no_update
            BEFORE UPDATE ON telemetry_measurements
            BEGIN SELECT RAISE(ABORT, 'telemetry_measurements is append-only'); END"""
    )
    connection.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_telemetry_measurements_controlled_delete
            BEFORE DELETE ON telemetry_measurements
            WHEN (SELECT retention_enabled FROM telemetry_operation_context WHERE singleton=1) != 1
            BEGIN SELECT RAISE(ABORT, 'telemetry_measurements requires retention context'); END"""
    )
    connection.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_document_revision_integrity_immutable
            BEFORE UPDATE OF content_sha256, content_length, object_id ON document_revisions
            BEGIN SELECT RAISE(ABORT, 'document revision integrity evidence is immutable'); END"""
    )


def _postgres_guards(connection: Any) -> None:
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_reject_phase7_evidence_rewrite()
           RETURNS trigger LANGUAGE plpgsql AS $$
           BEGIN
               IF TG_OP = 'DELETE'
                  AND TG_TABLE_SCHEMA = 'telemetry'
                  AND TG_TABLE_NAME = 'measurements'
                  AND current_setting('app.retention_mode', true) = 'on' THEN
                   RETURN OLD;
               END IF;
               RAISE EXCEPTION '%% is append-only', TG_TABLE_NAME;
           END $$"""
    )
    for table_name in (
        "telemetry.sample_receipts",
        "telemetry.measurements",
        "telemetry.quality_events",
        "documents.integrity_events",
    ):
        trigger_name = "trg_" + table_name.replace(".", "_") + "_append_only"
        connection.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON {table_name}")
        connection.execute(
            f"""CREATE TRIGGER {trigger_name}
                BEFORE UPDATE OR DELETE ON {table_name}
                FOR EACH ROW EXECUTE FUNCTION miniogas_reject_phase7_evidence_rewrite()"""
        )
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_guard_document_integrity()
           RETURNS trigger LANGUAGE plpgsql AS $$
           BEGIN
               IF OLD.content_sha256 IS DISTINCT FROM NEW.content_sha256
                  OR OLD.content_length IS DISTINCT FROM NEW.content_length
                  OR OLD.object_id IS DISTINCT FROM NEW.object_id THEN
                   RAISE EXCEPTION 'document revision integrity evidence is immutable';
               END IF;
               RETURN NEW;
           END $$"""
    )
    connection.execute(
        "DROP TRIGGER IF EXISTS trg_document_revision_integrity_immutable ON document_revisions"
    )
    connection.execute(
        """CREATE TRIGGER trg_document_revision_integrity_immutable
            BEFORE UPDATE ON document_revisions
            FOR EACH ROW EXECUTE FUNCTION miniogas_guard_document_integrity()"""
    )


def _sqlite_retention_partition_guard(connection: Any) -> None:
    # SQLite uses a single measurements table, so the existing operation-context
    # trigger already covers retention deletes.
    connection.execute("SELECT 1")


def _postgres_retention_partition_guard(connection: Any) -> None:
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_reject_phase7_evidence_rewrite()
           RETURNS trigger LANGUAGE plpgsql AS $$
           BEGIN
               IF TG_OP = 'DELETE'
                  AND TG_TABLE_SCHEMA = 'telemetry'
                  AND (
                      TG_TABLE_NAME = 'measurements'
                      OR TG_TABLE_NAME LIKE 'measurements_%%'
                  )
                  AND current_setting('app.retention_mode', true) = 'on' THEN
                   RETURN OLD;
               END IF;
               RAISE EXCEPTION '%% is append-only', TG_TABLE_NAME;
           END $$"""
    )


PHASE7_MIGRATIONS = [
    Migration(
        version=PHASE7_DATA_PLATFORM_VERSION,
        description="Phase 7 isolated telemetry Historian PoC and object manifest schemas",
        checksum_material=(
            "phase7-data-platform-v2|postgres-telemetry-schema-v1|"
            "partitioned-measurements-2025-2027-v1|redis-checkpoint-v1|"
            "controlled-retention-context-v1|object-manifest-v1"
        ),
        sqlite_action=_sqlite_data_platform,
        postgres_action=_postgres_data_platform,
    ),
    Migration(
        version=PHASE7_DOCUMENT_INTEGRITY_VERSION,
        description="Phase 7 controlled-document SHA-256 and object binding",
        checksum_material="phase7-document-integrity-v1|canonical-json-sha256-backfill-v1",
        sqlite_action=_sqlite_document_integrity,
        postgres_action=_postgres_document_integrity,
    ),
    Migration(
        version=PHASE7_INVARIANT_GUARDS_VERSION,
        description="Phase 7 append-only telemetry and document integrity guards",
        checksum_material=(
            "phase7-invariant-guards-v2|append-only-evidence-v1|"
            "controlled-retention-delete-v1|document-integrity-lock-v1"
        ),
        sqlite_action=_sqlite_guards,
        postgres_action=_postgres_guards,
    ),
    Migration(
        version=PHASE7_RETENTION_PARTITION_GUARD_VERSION,
        description="Phase 7 controlled retention guard for PostgreSQL partitions",
        checksum_material=(
            "phase7-retention-partition-guard-v1|"
            "parent-and-child-measurement-delete-context-v1"
        ),
        sqlite_action=_sqlite_retention_partition_guard,
        postgres_action=_postgres_retention_partition_guard,
    ),
]
