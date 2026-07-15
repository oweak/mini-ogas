from __future__ import annotations

from typing import Any

from .migrations import Migration

PHASE5_QUALITY_VERSION = "2026.07.14-phase5-quality-operations"
PHASE5_QUALITY_GUARDS_VERSION = "2026.07.14-phase5-quality-invariant-guards"

PHASE5_SCOPED_TABLES = (
    "inspection_plans",
    "quality_characteristics",
    "gauges",
    "inspection_lots",
    "quality_holds",
    "quality_measurements",
    "nonconformances",
    "quality_dispositions",
    "capa_records",
    "quality_status_history",
)

PHASE5_APPEND_ONLY_TABLES = (
    "quality_characteristics",
    "quality_measurements",
    "quality_status_history",
)

SQLITE_TABLES = (
    """CREATE TABLE IF NOT EXISTS inspection_plans (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           plan_code TEXT NOT NULL,
           revision INTEGER NOT NULL CHECK (revision > 0),
           name TEXT NOT NULL,
           material_id INTEGER NOT NULL REFERENCES materials(id),
           stage TEXT NOT NULL CHECK (stage IN ('receiving','in_process','final')),
           operation_code TEXT,
           status TEXT NOT NULL DEFAULT 'draft'
               CHECK (status IN ('draft','approved','effective','superseded','retired')),
           created_by TEXT NOT NULL,
           approved_by TEXT,
           approval_evidence_reference TEXT,
           approved_at TEXT,
           effective_by TEXT,
           effectivity_evidence_reference TEXT,
           effective_at TEXT,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, plan_code, revision)
       )""",
    """CREATE TABLE IF NOT EXISTS quality_characteristics (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           inspection_plan_id INTEGER NOT NULL REFERENCES inspection_plans(id),
           characteristic_code TEXT NOT NULL,
           name TEXT NOT NULL,
           value_type TEXT NOT NULL CHECK (value_type IN ('numeric','boolean','text')),
           uom_id INTEGER REFERENCES uoms(id),
           target_value REAL,
           lower_spec_limit REAL,
           upper_spec_limit REAL,
           expected_boolean INTEGER,
           expected_text TEXT,
           method TEXT NOT NULL,
           sample_size INTEGER NOT NULL CHECK (sample_size > 0),
           gauge_type TEXT NOT NULL,
           required_skill_id INTEGER NOT NULL REFERENCES skills(id),
           required_skill_level INTEGER NOT NULL CHECK (required_skill_level BETWEEN 1 AND 10),
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, inspection_plan_id, characteristic_code)
       )""",
    """CREATE TABLE IF NOT EXISTS gauges (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           gauge_code TEXT NOT NULL,
           name TEXT NOT NULL,
           gauge_type TEXT NOT NULL,
           calibration_status TEXT NOT NULL
               CHECK (calibration_status IN ('valid','expired','out_of_calibration','retired')),
           valid_from TEXT NOT NULL,
           valid_to TEXT NOT NULL,
           evidence_reference TEXT NOT NULL,
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, gauge_code)
       )""",
    """CREATE TABLE IF NOT EXISTS inspection_lots (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           inspection_lot_code TEXT NOT NULL,
           inspection_plan_id INTEGER NOT NULL REFERENCES inspection_plans(id),
           lot_id INTEGER NOT NULL REFERENCES material_lots(id),
           location_id INTEGER NOT NULL REFERENCES inventory_locations(id),
           operation_task_id INTEGER REFERENCES operation_tasks(id),
           quantity REAL NOT NULL CHECK (quantity > 0),
           status TEXT NOT NULL DEFAULT 'open' CHECK (status IN (
               'open','passed','failed','released','dispositioned','rework_required','cancelled'
           )),
           evidence_reference TEXT NOT NULL,
           opened_by TEXT NOT NULL,
           opened_at TEXT NOT NULL,
           result_evaluated_at TEXT,
           released_by TEXT,
           release_authorization_reference TEXT,
           released_at TEXT,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, inspection_lot_code)
       )""",
    """CREATE TABLE IF NOT EXISTS quality_holds (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           hold_code TEXT NOT NULL,
           inspection_lot_id INTEGER NOT NULL REFERENCES inspection_lots(id),
           lot_id INTEGER NOT NULL REFERENCES material_lots(id),
           reason TEXT NOT NULL,
           status TEXT NOT NULL DEFAULT 'open'
               CHECK (status IN ('open','released','disposed','cancelled')),
           placed_by TEXT NOT NULL,
           placed_at TEXT NOT NULL,
           resolved_by TEXT,
           resolution_evidence_reference TEXT,
           resolved_at TEXT,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, hold_code)
       )""",
    """CREATE TABLE IF NOT EXISTS quality_measurements (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           measurement_id TEXT NOT NULL,
           inspection_lot_id INTEGER NOT NULL REFERENCES inspection_lots(id),
           characteristic_id INTEGER NOT NULL REFERENCES quality_characteristics(id),
           sample_index INTEGER NOT NULL CHECK (sample_index > 0),
           numeric_value REAL,
           boolean_value INTEGER,
           text_value TEXT,
           uom_id INTEGER REFERENCES uoms(id),
           method TEXT NOT NULL,
           gauge_id INTEGER NOT NULL REFERENCES gauges(id),
           personnel_id INTEGER NOT NULL REFERENCES personnel(id),
           occurred_at TEXT NOT NULL,
           evidence_reference TEXT NOT NULL,
           result TEXT NOT NULL CHECK (result IN ('pass','fail')),
           request_hash TEXT NOT NULL,
           recorded_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, measurement_id),
           UNIQUE (tenant_id, site_id, inspection_lot_id, characteristic_id, sample_index)
       )""",
    """CREATE TABLE IF NOT EXISTS nonconformances (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           nc_code TEXT NOT NULL,
           inspection_lot_id INTEGER NOT NULL REFERENCES inspection_lots(id),
           lot_id INTEGER NOT NULL REFERENCES material_lots(id),
           status TEXT NOT NULL DEFAULT 'open'
               CHECK (status IN ('open','dispositioned','closed')),
           severity TEXT NOT NULL CHECK (severity IN ('minor','major','critical')),
           description TEXT NOT NULL,
           affected_quantity REAL NOT NULL CHECK (affected_quantity > 0),
           opened_by TEXT NOT NULL,
           opened_at TEXT NOT NULL,
           closed_by TEXT,
           closed_at TEXT,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, nc_code),
           UNIQUE (tenant_id, site_id, inspection_lot_id)
       )""",
    """CREATE TABLE IF NOT EXISTS quality_dispositions (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           disposition_code TEXT NOT NULL,
           nonconformance_id INTEGER NOT NULL REFERENCES nonconformances(id),
           disposition_type TEXT NOT NULL CHECK (disposition_type IN (
               'use_as_is','rework','scrap','return_to_supplier'
           )),
           status TEXT NOT NULL DEFAULT 'proposed'
               CHECK (status IN ('proposed','approved','rejected')),
           reason TEXT NOT NULL,
           evidence_reference TEXT NOT NULL,
           proposed_by TEXT NOT NULL,
           proposed_at TEXT NOT NULL,
           approved_by TEXT,
           authorization_reference TEXT,
           approved_at TEXT,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, disposition_code)
       )""",
    """CREATE TABLE IF NOT EXISTS capa_records (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           capa_code TEXT NOT NULL,
           nonconformance_id INTEGER NOT NULL REFERENCES nonconformances(id),
           problem_statement TEXT NOT NULL,
           root_cause TEXT NOT NULL,
           action_plan TEXT NOT NULL,
           due_at TEXT NOT NULL,
           status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','completed','cancelled')),
           evidence_reference TEXT NOT NULL,
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL,
           verification_reference TEXT,
           effectiveness_result TEXT,
           completed_by TEXT,
           completed_at TEXT,
           UNIQUE (tenant_id, site_id, capa_code)
       )""",
    """CREATE TABLE IF NOT EXISTS quality_status_history (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           resource_type TEXT NOT NULL,
           resource_id TEXT NOT NULL,
           from_status TEXT,
           to_status TEXT NOT NULL,
           action TEXT NOT NULL,
           evidence_reference TEXT NOT NULL,
           actor TEXT NOT NULL,
           occurred_at TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
       )""",
)


def _postgres_statement(statement: str) -> str:
    converted = statement.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
    converted = converted.replace(" INTEGER NOT NULL REFERENCES", " BIGINT NOT NULL REFERENCES")
    converted = converted.replace(" INTEGER REFERENCES", " BIGINT REFERENCES")
    converted = converted.replace(" REAL ", " DOUBLE PRECISION ")
    for column in (
        "approved_at",
        "effective_at",
        "valid_from",
        "valid_to",
        "opened_at",
        "result_evaluated_at",
        "released_at",
        "placed_at",
        "resolved_at",
        "occurred_at",
        "closed_at",
        "proposed_at",
        "due_at",
        "completed_at",
    ):
        converted = converted.replace(f"{column} TEXT", f"{column} TIMESTAMPTZ")
    converted = converted.replace(
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    )
    converted = converted.replace("created_at TEXT NOT NULL,", "created_at TIMESTAMPTZ NOT NULL,")
    return converted


POSTGRES_TABLES = tuple(_postgres_statement(statement) for statement in SQLITE_TABLES)


def _create_tables(connection: Any, statements: tuple[str, ...]) -> None:
    for statement in statements:
        connection.execute(statement)


def _create_indexes(connection: Any) -> None:
    for table_name in PHASE5_SCOPED_TABLES:
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_scope ON {table_name}(tenant_id, site_id)"
        )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_quality_hold_one_open_lot "
        "ON quality_holds(tenant_id, site_id, lot_id) WHERE status='open'"
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_inspection_plan_one_effective "
        "ON inspection_plans(tenant_id, site_id, plan_code) WHERE status='effective'"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_quality_measurement_inspection "
        "ON quality_measurements(tenant_id, site_id, inspection_lot_id, characteristic_id)"
    )


def _phase5_sqlite_schema(connection: Any) -> None:
    _create_tables(connection, SQLITE_TABLES)
    _create_indexes(connection)
    for table_name in PHASE5_APPEND_ONLY_TABLES:
        for operation in ("UPDATE", "DELETE"):
            connection.execute(
                f"""CREATE TRIGGER IF NOT EXISTS trg_{table_name}_{operation.lower()}_guard
                    BEFORE {operation} ON {table_name}
                    FOR EACH ROW BEGIN
                        SELECT RAISE(ABORT, 'quality evidence is append-only');
                    END"""
            )
    connection.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_inspection_plan_delete_guard
           BEFORE DELETE ON inspection_plans
           FOR EACH ROW BEGIN
               SELECT RAISE(ABORT, 'inspection plan history cannot be deleted');
           END"""
    )
    connection.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_inspection_plan_identity_guard
           BEFORE UPDATE ON inspection_plans
           FOR EACH ROW
           WHEN NEW.plan_code<>OLD.plan_code OR NEW.revision<>OLD.revision
             OR NEW.name<>OLD.name OR NEW.material_id<>OLD.material_id
             OR NEW.stage<>OLD.stage OR COALESCE(NEW.operation_code,'')<>COALESCE(OLD.operation_code,'')
           BEGIN
               SELECT RAISE(ABORT, 'inspection plan identity is immutable');
           END"""
    )


def _phase5_postgres_schema(connection: Any) -> None:
    _create_tables(connection, POSTGRES_TABLES)
    _create_indexes(connection)
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_reject_quality_evidence_rewrite()
           RETURNS trigger AS $$
           BEGIN
               RAISE EXCEPTION 'quality evidence is append-only';
           END;
           $$ LANGUAGE plpgsql"""
    )
    for table_name in PHASE5_APPEND_ONLY_TABLES:
        for operation in ("UPDATE", "DELETE"):
            trigger_name = f"trg_{table_name}_{operation.lower()}_guard"
            connection.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON {table_name}")
            connection.execute(
                f"""CREATE TRIGGER {trigger_name}
                    BEFORE {operation} ON {table_name}
                    FOR EACH ROW EXECUTE FUNCTION miniogas_reject_quality_evidence_rewrite()"""
            )
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_guard_inspection_plan_identity()
           RETURNS trigger AS $$
           BEGIN
               IF NEW.plan_code<>OLD.plan_code OR NEW.revision<>OLD.revision
                  OR NEW.name<>OLD.name OR NEW.material_id<>OLD.material_id
                  OR NEW.stage<>OLD.stage
                  OR COALESCE(NEW.operation_code,'')<>COALESCE(OLD.operation_code,'') THEN
                   RAISE EXCEPTION 'inspection plan identity is immutable';
               END IF;
               RETURN NEW;
           END;
           $$ LANGUAGE plpgsql"""
    )
    connection.execute(
        "DROP TRIGGER IF EXISTS trg_inspection_plan_identity_guard ON inspection_plans"
    )
    connection.execute(
        """CREATE TRIGGER trg_inspection_plan_identity_guard
           BEFORE UPDATE ON inspection_plans
           FOR EACH ROW EXECUTE FUNCTION miniogas_guard_inspection_plan_identity()"""
    )
    connection.execute(
        "DROP TRIGGER IF EXISTS trg_inspection_plan_delete_guard ON inspection_plans"
    )
    connection.execute(
        """CREATE TRIGGER trg_inspection_plan_delete_guard
           BEFORE DELETE ON inspection_plans
           FOR EACH ROW EXECUTE FUNCTION miniogas_reject_quality_evidence_rewrite()"""
    )
    for table_name in PHASE5_SCOPED_TABLES:
        connection.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        connection.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
        connection.execute(f"DROP POLICY IF EXISTS miniogas_scope ON {table_name}")
        connection.execute(
            f"""CREATE POLICY miniogas_scope ON {table_name}
                USING (
                    tenant_id=current_setting('app.tenant_id', true)
                    AND site_id=current_setting('app.site_id', true)
                )
                WITH CHECK (
                    tenant_id=current_setting('app.tenant_id', true)
                    AND site_id=current_setting('app.site_id', true)
                )"""
        )


def _phase5_sqlite_guards(connection: Any) -> None:
    connection.execute("DROP TRIGGER IF EXISTS trg_quality_hold_blocks_movement")
    connection.execute(
        """CREATE TRIGGER trg_quality_hold_blocks_movement
           BEFORE INSERT ON inventory_movements
           FOR EACH ROW
           WHEN EXISTS (
               SELECT 1 FROM quality_holds hold
               WHERE hold.tenant_id=NEW.tenant_id AND hold.site_id=NEW.site_id
                 AND hold.lot_id=NEW.lot_id AND hold.status='open'
           )
           BEGIN
               SELECT RAISE(ABORT, 'open quality hold blocks material movement');
           END"""
    )
    connection.execute("DROP TRIGGER IF EXISTS trg_quality_measurement_result_guard")
    connection.execute(
        """CREATE TRIGGER trg_quality_measurement_result_guard
           BEFORE INSERT ON quality_measurements
           FOR EACH ROW
           WHEN EXISTS (
               SELECT 1 FROM quality_characteristics characteristic
               WHERE characteristic.id=NEW.characteristic_id
                 AND characteristic.value_type='numeric'
                 AND (
                     NEW.numeric_value IS NULL OR
                     NEW.result<>CASE WHEN
                         (characteristic.lower_spec_limit IS NULL
                          OR NEW.numeric_value>=characteristic.lower_spec_limit)
                         AND (characteristic.upper_spec_limit IS NULL
                          OR NEW.numeric_value<=characteristic.upper_spec_limit)
                         THEN 'pass' ELSE 'fail' END
                 )
           )
           BEGIN
               SELECT RAISE(ABORT, 'measurement result contradicts specification');
           END"""
    )
    connection.execute("DROP TRIGGER IF EXISTS trg_inspection_release_guard")
    connection.execute(
        """CREATE TRIGGER trg_inspection_release_guard
           BEFORE UPDATE OF status ON inspection_lots
           FOR EACH ROW WHEN NEW.status='released' AND (
               NEW.released_by IS NULL OR NEW.release_authorization_reference IS NULL OR
               NOT (
                   OLD.status='passed' OR (
                       OLD.status='failed' AND EXISTS (
                           SELECT 1 FROM nonconformances nc
                           JOIN quality_dispositions disposition
                             ON disposition.nonconformance_id=nc.id
                           WHERE nc.inspection_lot_id=OLD.id
                             AND disposition.disposition_type='use_as_is'
                             AND disposition.status='approved'
                       )
                   )
               )
           )
           BEGIN
               SELECT RAISE(ABORT, 'quality release requires pass or approved use-as-is');
           END"""
    )


def _phase5_postgres_guards(connection: Any) -> None:
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_quality_hold_blocks_movement()
           RETURNS trigger AS $$
           BEGIN
               IF EXISTS (
                   SELECT 1 FROM quality_holds hold
                   WHERE hold.tenant_id=NEW.tenant_id AND hold.site_id=NEW.site_id
                     AND hold.lot_id=NEW.lot_id AND hold.status='open'
               ) THEN
                   RAISE EXCEPTION 'open quality hold blocks material movement';
               END IF;
               RETURN NEW;
           END;
           $$ LANGUAGE plpgsql"""
    )
    connection.execute(
        "DROP TRIGGER IF EXISTS trg_quality_hold_blocks_movement ON inventory_movements"
    )
    connection.execute(
        """CREATE TRIGGER trg_quality_hold_blocks_movement
           BEFORE INSERT ON inventory_movements
           FOR EACH ROW EXECUTE FUNCTION miniogas_quality_hold_blocks_movement()"""
    )
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_quality_measurement_result_guard()
           RETURNS trigger AS $$
           DECLARE
               characteristic quality_characteristics%%ROWTYPE;
               expected_result TEXT;
           BEGIN
               SELECT * INTO characteristic FROM quality_characteristics
               WHERE id=NEW.characteristic_id;
               IF characteristic.value_type='numeric' THEN
                   IF NEW.numeric_value IS NULL THEN
                       RAISE EXCEPTION 'numeric measurement requires numeric value';
                   END IF;
                   expected_result := CASE WHEN
                       (characteristic.lower_spec_limit IS NULL
                        OR NEW.numeric_value>=characteristic.lower_spec_limit)
                       AND (characteristic.upper_spec_limit IS NULL
                        OR NEW.numeric_value<=characteristic.upper_spec_limit)
                       THEN 'pass' ELSE 'fail' END;
                   IF NEW.result<>expected_result THEN
                       RAISE EXCEPTION 'measurement result contradicts specification';
                   END IF;
               END IF;
               RETURN NEW;
           END;
           $$ LANGUAGE plpgsql"""
    )
    connection.execute(
        "DROP TRIGGER IF EXISTS trg_quality_measurement_result_guard ON quality_measurements"
    )
    connection.execute(
        """CREATE TRIGGER trg_quality_measurement_result_guard
           BEFORE INSERT ON quality_measurements
           FOR EACH ROW EXECUTE FUNCTION miniogas_quality_measurement_result_guard()"""
    )
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_inspection_release_guard()
           RETURNS trigger AS $$
           BEGIN
               IF NEW.status='released' AND (
                   NEW.released_by IS NULL OR NEW.release_authorization_reference IS NULL OR
                   NOT (
                       OLD.status='passed' OR (
                           OLD.status='failed' AND EXISTS (
                               SELECT 1 FROM nonconformances nc
                               JOIN quality_dispositions disposition
                                 ON disposition.nonconformance_id=nc.id
                               WHERE nc.inspection_lot_id=OLD.id
                                 AND disposition.disposition_type='use_as_is'
                                 AND disposition.status='approved'
                           )
                       )
                   )
               ) THEN
                   RAISE EXCEPTION 'quality release requires pass or approved use-as-is';
               END IF;
               RETURN NEW;
           END;
           $$ LANGUAGE plpgsql"""
    )
    connection.execute("DROP TRIGGER IF EXISTS trg_inspection_release_guard ON inspection_lots")
    connection.execute(
        """CREATE TRIGGER trg_inspection_release_guard
           BEFORE UPDATE OF status ON inspection_lots
           FOR EACH ROW EXECUTE FUNCTION miniogas_inspection_release_guard()"""
    )


PHASE5_MIGRATIONS = [
    Migration(
        version=PHASE5_QUALITY_VERSION,
        description=(
            "Phase 5 inspection plans, specifications, gauges, measurements, quality "
            "holds, nonconformance, disposition and CAPA"
        ),
        checksum_material=(
            "phase5-quality-v1|append-only-measurement-history-v1|"
            "postgres-force-rls-v1|" + "|".join(PHASE5_SCOPED_TABLES)
        ),
        sqlite_action=_phase5_sqlite_schema,
        postgres_action=_phase5_postgres_schema,
    ),
    Migration(
        version=PHASE5_QUALITY_GUARDS_VERSION,
        description="Phase 5 material hold, deterministic result and release guards",
        checksum_material=(
            "phase5-quality-guards-v1|hold-blocks-movement-v1|"
            "deterministic-result-v1|authorized-release-fact-v1"
        ),
        sqlite_action=_phase5_sqlite_guards,
        postgres_action=_phase5_postgres_guards,
    ),
]
