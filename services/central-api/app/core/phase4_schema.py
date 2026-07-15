from __future__ import annotations

from typing import Any

from .migrations import Migration

PHASE4_MATERIAL_FLOW_VERSION = "2026.07.14-phase4-material-flow"
PHASE4_BALANCE_GUARDS_VERSION = "2026.07.14-phase4-balance-invariant-guards"

PHASE4_SCOPED_TABLES = (
    "warehouses",
    "inventory_locations",
    "material_containers",
    "material_lots",
    "inventory_balances",
    "inventory_movements",
    "material_transformations",
    "genealogy_edges",
    "external_inventory_imports",
    "inventory_reconciliation_cases",
)

PHASE4_APPEND_ONLY_TABLES = (
    "inventory_movements",
    "material_transformations",
    "genealogy_edges",
    "external_inventory_imports",
)


SQLITE_TABLES = (
    """CREATE TABLE IF NOT EXISTS warehouses (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           warehouse_code TEXT NOT NULL,
           name TEXT NOT NULL,
           warehouse_type TEXT NOT NULL
               CHECK (warehouse_type IN ('raw','wip','finished','quarantine','scrap','shipping')),
           active INTEGER NOT NULL DEFAULT 1,
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, warehouse_code)
       )""",
    """CREATE TABLE IF NOT EXISTS inventory_locations (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           location_code TEXT NOT NULL,
           warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
           name TEXT NOT NULL,
           location_type TEXT NOT NULL
               CHECK (location_type IN ('storage','staging','wip','quarantine','scrap','shipping')),
           active INTEGER NOT NULL DEFAULT 1,
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, location_code)
       )""",
    """CREATE TABLE IF NOT EXISTS material_containers (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           container_code TEXT NOT NULL,
           container_type TEXT NOT NULL,
           location_id INTEGER NOT NULL REFERENCES inventory_locations(id),
           status TEXT NOT NULL DEFAULT 'active'
               CHECK (status IN ('active','closed','quarantined')),
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, container_code)
       )""",
    """CREATE TABLE IF NOT EXISTS material_lots (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           lot_code TEXT NOT NULL,
           material_id INTEGER NOT NULL REFERENCES materials(id),
           uom_id INTEGER NOT NULL REFERENCES uoms(id),
           tracking_kind TEXT NOT NULL CHECK (tracking_kind IN ('lot','serial')),
           status TEXT NOT NULL DEFAULT 'active'
               CHECK (status IN ('active','quarantined','closed')),
           evidence_reference TEXT NOT NULL,
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, lot_code)
       )""",
    """CREATE TABLE IF NOT EXISTS inventory_balances (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           material_id INTEGER NOT NULL REFERENCES materials(id),
           lot_id INTEGER NOT NULL REFERENCES material_lots(id),
           uom_id INTEGER NOT NULL REFERENCES uoms(id),
           location_id INTEGER NOT NULL REFERENCES inventory_locations(id),
           container_id INTEGER REFERENCES material_containers(id),
           container_key TEXT NOT NULL DEFAULT '',
           quantity REAL NOT NULL DEFAULT 0 CHECK (quantity >= 0),
           updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, lot_id, location_id, container_key)
       )""",
    """CREATE TABLE IF NOT EXISTS inventory_movements (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           movement_id TEXT NOT NULL,
           movement_type TEXT NOT NULL CHECK (movement_type IN (
               'receipt','issue','consume','produce','return','transfer',
               'scrap','rework','adjustment','split_input','split_output',
               'merge_input','merge_output','transform_input','transform_output'
           )),
           material_id INTEGER NOT NULL REFERENCES materials(id),
           lot_id INTEGER NOT NULL REFERENCES material_lots(id),
           uom_id INTEGER NOT NULL REFERENCES uoms(id),
           quantity REAL NOT NULL CHECK (quantity > 0),
           from_location_id INTEGER REFERENCES inventory_locations(id),
           to_location_id INTEGER REFERENCES inventory_locations(id),
           from_container_id INTEGER REFERENCES material_containers(id),
           to_container_id INTEGER REFERENCES material_containers(id),
           operation_task_id INTEGER REFERENCES operation_tasks(id),
           transformation_id TEXT,
           reconciliation_case_id INTEGER,
           source TEXT NOT NULL CHECK (source IN (
               'manual','execution','erp_simulated','wms_simulated','reconciliation'
           )),
           reason TEXT NOT NULL,
           evidence_reference TEXT NOT NULL,
           request_hash TEXT NOT NULL,
           occurred_at TEXT NOT NULL,
           recorded_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, movement_id)
       )""",
    """CREATE TABLE IF NOT EXISTS material_transformations (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           transformation_id TEXT NOT NULL,
           transformation_type TEXT NOT NULL
               CHECK (transformation_type IN ('split','merge','consume_produce','rework')),
           operation_task_id INTEGER REFERENCES operation_tasks(id),
           reason TEXT NOT NULL,
           evidence_reference TEXT NOT NULL,
           conversion_evidence_reference TEXT NOT NULL DEFAULT '',
           request_hash TEXT NOT NULL,
           occurred_at TEXT NOT NULL,
           recorded_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, transformation_id)
       )""",
    """CREATE TABLE IF NOT EXISTS genealogy_edges (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           transformation_id TEXT NOT NULL,
           parent_lot_id INTEGER NOT NULL REFERENCES material_lots(id),
           child_lot_id INTEGER NOT NULL REFERENCES material_lots(id),
           parent_quantity REAL NOT NULL CHECK (parent_quantity > 0),
           child_quantity REAL NOT NULL CHECK (child_quantity > 0),
           relation_type TEXT NOT NULL,
           evidence_reference TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, transformation_id, parent_lot_id, child_lot_id)
       )""",
    """CREATE TABLE IF NOT EXISTS external_inventory_imports (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           import_id TEXT NOT NULL,
           provider TEXT NOT NULL CHECK (provider IN ('erp_simulator','wms_simulator')),
           contract_version TEXT NOT NULL,
           source TEXT NOT NULL DEFAULT 'simulated' CHECK (source='simulated'),
           observed_at TEXT NOT NULL,
           evidence_reference TEXT NOT NULL,
           payload_json TEXT NOT NULL,
           payload_hash TEXT NOT NULL,
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, import_id)
       )""",
    """CREATE TABLE IF NOT EXISTS inventory_reconciliation_cases (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           case_code TEXT NOT NULL,
           external_import_id INTEGER NOT NULL REFERENCES external_inventory_imports(id),
           material_id INTEGER NOT NULL REFERENCES materials(id),
           lot_id INTEGER NOT NULL REFERENCES material_lots(id),
           uom_id INTEGER NOT NULL REFERENCES uoms(id),
           location_id INTEGER NOT NULL REFERENCES inventory_locations(id),
           container_id INTEGER REFERENCES material_containers(id),
           container_key TEXT NOT NULL DEFAULT '',
           expected_quantity REAL NOT NULL CHECK (expected_quantity >= 0),
           observed_quantity REAL NOT NULL CHECK (observed_quantity >= 0),
           variance REAL NOT NULL,
           status TEXT NOT NULL DEFAULT 'open'
               CHECK (status IN ('open','adjusted','closed')),
           evidence_reference TEXT NOT NULL,
           adjustment_movement_id TEXT,
           adjustment_reason TEXT,
           adjustment_evidence_reference TEXT,
           adjusted_by TEXT,
           adjusted_at TEXT,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, case_code)
       )""",
)


def _postgres_statement(statement: str) -> str:
    converted = statement.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
    converted = converted.replace(" INTEGER NOT NULL REFERENCES", " BIGINT NOT NULL REFERENCES")
    converted = converted.replace(" INTEGER REFERENCES", " BIGINT REFERENCES")
    converted = converted.replace(" REAL ", " DOUBLE PRECISION ")
    converted = converted.replace(
        "active INTEGER NOT NULL DEFAULT 1", "active BOOLEAN NOT NULL DEFAULT true"
    )
    converted = converted.replace(
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    )
    converted = converted.replace(
        "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    )
    for column in ("occurred_at", "observed_at", "adjusted_at"):
        converted = converted.replace(f"{column} TEXT", f"{column} TIMESTAMPTZ")
    return converted


POSTGRES_TABLES = tuple(_postgres_statement(statement) for statement in SQLITE_TABLES)


def _create_tables(connection: Any, statements: tuple[str, ...]) -> None:
    for statement in statements:
        connection.execute(statement)


def _create_indexes(connection: Any) -> None:
    for table_name in PHASE4_SCOPED_TABLES:
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_scope "
            f"ON {table_name}(tenant_id, site_id)"
        )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventory_balance_lookup "
        "ON inventory_balances(tenant_id, site_id, lot_id, location_id, container_key)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventory_movement_lot_time "
        "ON inventory_movements(tenant_id, site_id, lot_id, occurred_at, id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_genealogy_parent "
        "ON genealogy_edges(tenant_id, site_id, parent_lot_id, child_lot_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_genealogy_child "
        "ON genealogy_edges(tenant_id, site_id, child_lot_id, parent_lot_id)"
    )


def _phase4_sqlite_schema(connection: Any) -> None:
    _create_tables(connection, SQLITE_TABLES)
    _create_indexes(connection)
    for table_name in PHASE4_APPEND_ONLY_TABLES:
        for operation in ("UPDATE", "DELETE"):
            connection.execute(
                f"""CREATE TRIGGER IF NOT EXISTS trg_{table_name}_{operation.lower()}_guard
                    BEFORE {operation} ON {table_name}
                    FOR EACH ROW BEGIN
                        SELECT RAISE(ABORT, 'material evidence is append-only');
                    END"""
            )


def _phase4_postgres_schema(connection: Any) -> None:
    _create_tables(connection, POSTGRES_TABLES)
    _create_indexes(connection)
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_reject_material_evidence_rewrite()
           RETURNS trigger AS $$
           BEGIN
               RAISE EXCEPTION 'material evidence is append-only';
           END;
           $$ LANGUAGE plpgsql"""
    )
    for table_name in PHASE4_APPEND_ONLY_TABLES:
        for operation in ("UPDATE", "DELETE"):
            trigger_name = f"trg_{table_name}_{operation.lower()}_guard"
            connection.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON {table_name}")
            connection.execute(
                f"""CREATE TRIGGER {trigger_name}
                    BEFORE {operation} ON {table_name}
                    FOR EACH ROW EXECUTE FUNCTION miniogas_reject_material_evidence_rewrite()"""
            )
    for table_name in PHASE4_SCOPED_TABLES:
        connection.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        connection.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
        connection.execute(f"DROP POLICY IF EXISTS miniogas_scope ON {table_name}")
        connection.execute(
            f"""CREATE POLICY miniogas_scope ON {table_name}
                USING (
                    tenant_id = current_setting('app.tenant_id', true)
                    AND site_id = current_setting('app.site_id', true)
                )
                WITH CHECK (
                    tenant_id = current_setting('app.tenant_id', true)
                    AND site_id = current_setting('app.site_id', true)
                )"""
        )


def _phase4_sqlite_balance_guards(connection: Any) -> None:
    connection.execute("DROP TRIGGER IF EXISTS trg_serial_balance_insert_guard")
    connection.execute("DROP TRIGGER IF EXISTS trg_serial_balance_update_guard")
    connection.execute(
        """CREATE TRIGGER trg_serial_balance_insert_guard
           BEFORE INSERT ON inventory_balances
           FOR EACH ROW
           WHEN (
               SELECT tracking_kind FROM material_lots WHERE id=NEW.lot_id
           )='serial' AND NEW.quantity + COALESCE((
               SELECT SUM(quantity) FROM inventory_balances
               WHERE tenant_id=NEW.tenant_id AND site_id=NEW.site_id
                 AND lot_id=NEW.lot_id
           ), 0) > 1.000000001
           BEGIN
               SELECT RAISE(ABORT, 'serial total balance cannot exceed one');
           END"""
    )
    connection.execute(
        """CREATE TRIGGER trg_serial_balance_update_guard
           BEFORE UPDATE OF quantity ON inventory_balances
           FOR EACH ROW
           WHEN (
               SELECT tracking_kind FROM material_lots WHERE id=NEW.lot_id
           )='serial' AND NEW.quantity + COALESCE((
               SELECT SUM(quantity) FROM inventory_balances
               WHERE tenant_id=NEW.tenant_id AND site_id=NEW.site_id
                 AND lot_id=NEW.lot_id AND id<>OLD.id
           ), 0) > 1.000000001
           BEGIN
               SELECT RAISE(ABORT, 'serial total balance cannot exceed one');
           END"""
    )


def _phase4_postgres_balance_guards(connection: Any) -> None:
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_guard_serial_balance()
           RETURNS trigger AS $$
           DECLARE
               other_quantity DOUBLE PRECISION;
           BEGIN
               IF EXISTS (
                   SELECT 1 FROM material_lots
                   WHERE id=NEW.lot_id AND tenant_id=NEW.tenant_id
                     AND site_id=NEW.site_id AND tracking_kind='serial'
               ) THEN
                   PERFORM 1 FROM material_lots
                   WHERE id=NEW.lot_id AND tenant_id=NEW.tenant_id
                     AND site_id=NEW.site_id
                   FOR UPDATE;
                   SELECT COALESCE(SUM(quantity), 0) INTO other_quantity
                   FROM inventory_balances
                   WHERE tenant_id=NEW.tenant_id AND site_id=NEW.site_id
                     AND lot_id=NEW.lot_id AND id<>COALESCE(NEW.id, -1);
                   IF other_quantity + NEW.quantity > 1.000000001 THEN
                       RAISE EXCEPTION 'serial total balance cannot exceed one';
                   END IF;
               END IF;
               RETURN NEW;
           END;
           $$ LANGUAGE plpgsql"""
    )
    connection.execute(
        "DROP TRIGGER IF EXISTS trg_serial_balance_guard ON inventory_balances"
    )
    connection.execute(
        """CREATE TRIGGER trg_serial_balance_guard
           BEFORE INSERT OR UPDATE OF quantity ON inventory_balances
           FOR EACH ROW EXECUTE FUNCTION miniogas_guard_serial_balance()"""
    )


PHASE4_MIGRATIONS = [
    Migration(
        version=PHASE4_MATERIAL_FLOW_VERSION,
        description=(
            "Phase 4 warehouse, location, lot/serial, container, movement, balance, "
            "genealogy, external snapshot and reconciliation authority"
        ),
        checksum_material=(
            "phase4-material-flow-v2|complete-external-payload-v1|"
            "separate-adjustment-evidence-v1|append-only-evidence-v1|"
            "postgres-force-rls-v1|"
            + "|".join(PHASE4_SCOPED_TABLES)
        ),
        sqlite_action=_phase4_sqlite_schema,
        postgres_action=_phase4_postgres_schema,
    ),
    Migration(
        version=PHASE4_BALANCE_GUARDS_VERSION,
        description="Phase 4 database serial balance invariant guards",
        checksum_material=(
            "phase4-balance-guards-v2|nonnegative-check-v1|"
            "serial-global-max-one-v1|parent-row-lock-v1"
        ),
        sqlite_action=_phase4_sqlite_balance_guards,
        postgres_action=_phase4_postgres_balance_guards,
    ),
]
