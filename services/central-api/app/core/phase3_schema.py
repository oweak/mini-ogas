from __future__ import annotations

from typing import Any

from .migrations import Migration

PHASE3_EXECUTION_MIGRATION_VERSION = "2026.07.14-phase3-production-execution"
PHASE3_INVARIANT_GUARD_VERSION = "2026.07.14-phase3-execution-invariant-guards"

PHASE3_SCOPED_TABLES = (
    "production_orders",
    "production_order_work_orders",
    "work_order_execution",
    "operation_tasks",
    "operation_task_assignments",
    "operation_setups",
    "operation_quantity_reports",
    "operation_downtime",
    "operation_holds",
    "operation_status_history",
    "execution_idempotency",
)

PHASE3_APPEND_ONLY_TABLES = (
    "operation_quantity_reports",
    "operation_status_history",
)


SQLITE_TABLES = (
    """CREATE TABLE IF NOT EXISTS production_orders (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           production_order_code TEXT NOT NULL,
           product_id INTEGER NOT NULL REFERENCES products(id),
           quantity REAL NOT NULL CHECK (quantity > 0),
           priority INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 10),
           due_at TEXT NOT NULL,
           status TEXT NOT NULL DEFAULT 'draft'
               CHECK (status IN (
                   'draft','released','in_progress','completed','closed','cancelled'
               )),
           created_by TEXT NOT NULL,
           released_by TEXT,
           released_at TEXT,
           completed_at TEXT,
           closed_by TEXT,
           closed_at TEXT,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, production_order_code)
       )""",
    """CREATE TABLE IF NOT EXISTS production_order_work_orders (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           production_order_id INTEGER NOT NULL REFERENCES production_orders(id),
           work_order_id INTEGER NOT NULL REFERENCES work_orders(id),
           attached_by TEXT NOT NULL,
           attached_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, work_order_id),
           UNIQUE (tenant_id, site_id, production_order_id, work_order_id)
       )""",
    """CREATE TABLE IF NOT EXISTS work_order_execution (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           production_order_id INTEGER NOT NULL REFERENCES production_orders(id),
           work_order_id INTEGER NOT NULL REFERENCES work_orders(id),
           status TEXT NOT NULL DEFAULT 'released'
               CHECK (status IN ('released','dispatched','in_progress','completed','closed')),
           dispatched_by TEXT,
           dispatched_at TEXT,
           completed_at TEXT,
           closed_by TEXT,
           closed_at TEXT,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, work_order_id)
       )""",
    """CREATE TABLE IF NOT EXISTS operation_tasks (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           work_order_execution_id INTEGER NOT NULL REFERENCES work_order_execution(id),
           work_order_id INTEGER NOT NULL REFERENCES work_orders(id),
           routing_revision_id INTEGER NOT NULL REFERENCES routing_revisions(id),
           sequence INTEGER NOT NULL CHECK (sequence >= 1),
           operation_code TEXT NOT NULL,
           name TEXT NOT NULL,
           planned_quantity REAL NOT NULL CHECK (planned_quantity > 0),
           status TEXT NOT NULL
               CHECK (status IN (
                   'dispatched','setup','ready','running','paused','held','completed','closed'
               )),
           hold_return_status TEXT,
           completion_evidence_reference TEXT,
           started_at TEXT,
           completed_at TEXT,
           closed_at TEXT,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, work_order_id, sequence)
       )""",
    """CREATE TABLE IF NOT EXISTS operation_task_assignments (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           operation_task_id INTEGER NOT NULL REFERENCES operation_tasks(id),
           equipment_id INTEGER NOT NULL REFERENCES equipment(id),
           personnel_id INTEGER NOT NULL REFERENCES personnel(id),
           assigned_by TEXT NOT NULL,
           assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, operation_task_id)
       )""",
    """CREATE TABLE IF NOT EXISTS operation_setups (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           operation_task_id INTEGER NOT NULL REFERENCES operation_tasks(id),
           status TEXT NOT NULL CHECK (status IN ('in_progress','completed')),
           parameters_json TEXT NOT NULL DEFAULT '{}',
           evidence_reference TEXT,
           started_by TEXT NOT NULL,
           started_at TEXT NOT NULL,
           completed_by TEXT,
           completed_at TEXT,
           UNIQUE (tenant_id, site_id, operation_task_id)
       )""",
    """CREATE TABLE IF NOT EXISTS operation_quantity_reports (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           operation_task_id INTEGER NOT NULL REFERENCES operation_tasks(id),
           report_id TEXT NOT NULL,
           good_quantity REAL NOT NULL CHECK (good_quantity >= 0),
           scrap_quantity REAL NOT NULL CHECK (scrap_quantity >= 0),
           rework_quantity REAL NOT NULL CHECK (rework_quantity >= 0),
           evidence_reference TEXT NOT NULL,
           occurred_at TEXT NOT NULL,
           reported_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, report_id)
       )""",
    """CREATE TABLE IF NOT EXISTS operation_downtime (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           operation_task_id INTEGER NOT NULL REFERENCES operation_tasks(id),
           downtime_code TEXT NOT NULL,
           status TEXT NOT NULL CHECK (status IN ('open','closed')),
           reason TEXT NOT NULL,
           start_evidence_reference TEXT NOT NULL,
           end_evidence_reference TEXT,
           started_by TEXT NOT NULL,
           started_at TEXT NOT NULL,
           ended_by TEXT,
           ended_at TEXT,
           UNIQUE (tenant_id, site_id, downtime_code)
       )""",
    """CREATE TABLE IF NOT EXISTS operation_holds (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           operation_task_id INTEGER NOT NULL REFERENCES operation_tasks(id),
           prior_status TEXT NOT NULL,
           status TEXT NOT NULL CHECK (status IN ('open','released')),
           reason TEXT NOT NULL,
           held_by TEXT NOT NULL,
           held_at TEXT NOT NULL,
           released_by TEXT,
           released_at TEXT,
           release_reason TEXT
       )""",
    """CREATE TABLE IF NOT EXISTS operation_status_history (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           operation_task_id INTEGER NOT NULL REFERENCES operation_tasks(id),
           from_status TEXT,
           to_status TEXT NOT NULL,
           action TEXT NOT NULL,
           reason TEXT NOT NULL DEFAULT '',
           evidence_reference TEXT NOT NULL DEFAULT '',
           actor TEXT NOT NULL,
           occurred_at TEXT NOT NULL,
           idempotency_key TEXT NOT NULL,
           UNIQUE (tenant_id, site_id, operation_task_id, idempotency_key)
       )""",
    """CREATE TABLE IF NOT EXISTS execution_idempotency (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           resource_type TEXT NOT NULL,
           resource_id TEXT NOT NULL,
           action TEXT NOT NULL,
           idempotency_key TEXT NOT NULL,
           request_hash TEXT NOT NULL,
           response_json TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, resource_type, resource_id, action, idempotency_key)
       )""",
)


def _postgres_statement(statement: str) -> str:
    converted = statement.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
    converted = converted.replace(" INTEGER NOT NULL REFERENCES", " BIGINT NOT NULL REFERENCES")
    converted = converted.replace(" INTEGER REFERENCES", " BIGINT REFERENCES")
    converted = converted.replace(" REAL ", " DOUBLE PRECISION ")
    converted = converted.replace(
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    )
    converted = converted.replace(
        "attached_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "attached_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    )
    for column in (
        "due_at",
        "released_at",
        "completed_at",
        "closed_at",
        "dispatched_at",
        "started_at",
        "ended_at",
        "held_at",
        "occurred_at",
    ):
        converted = converted.replace(f"{column} TEXT", f"{column} TIMESTAMPTZ")
    return converted


POSTGRES_TABLES = tuple(_postgres_statement(statement) for statement in SQLITE_TABLES)


def _create_tables(connection: Any, statements: tuple[str, ...]) -> None:
    for statement in statements:
        connection.execute(statement)


def _create_indexes(connection: Any) -> None:
    for table_name in PHASE3_SCOPED_TABLES:
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_scope "
            f"ON {table_name}(tenant_id, site_id)"
        )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_operation_tasks_work_order "
        "ON operation_tasks(tenant_id, site_id, work_order_id, sequence)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_operation_status_replay "
        "ON operation_status_history(tenant_id, site_id, operation_task_id, occurred_at, id)"
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_operation_downtime_open "
        "ON operation_downtime(tenant_id, site_id, operation_task_id) WHERE status='open'"
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_operation_hold_open "
        "ON operation_holds(tenant_id, site_id, operation_task_id) WHERE status='open'"
    )


def _phase3_sqlite_execution(connection: Any) -> None:
    _create_tables(connection, SQLITE_TABLES)
    _create_indexes(connection)
    for table_name in PHASE3_APPEND_ONLY_TABLES:
        connection.execute(
            f"""CREATE TRIGGER IF NOT EXISTS trg_{table_name}_update_guard
                BEFORE UPDATE ON {table_name}
                FOR EACH ROW BEGIN
                    SELECT RAISE(ABORT, 'execution evidence is append-only');
                END"""
        )
        connection.execute(
            f"""CREATE TRIGGER IF NOT EXISTS trg_{table_name}_delete_guard
                BEFORE DELETE ON {table_name}
                FOR EACH ROW BEGIN
                    SELECT RAISE(ABORT, 'execution evidence is append-only');
                END"""
        )


def _phase3_postgres_execution(connection: Any) -> None:
    _create_tables(connection, POSTGRES_TABLES)
    _create_indexes(connection)
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_reject_execution_evidence_rewrite()
           RETURNS trigger AS $$
           BEGIN
               RAISE EXCEPTION 'execution evidence is append-only';
           END;
           $$ LANGUAGE plpgsql"""
    )
    for table_name in PHASE3_APPEND_ONLY_TABLES:
        for operation in ("UPDATE", "DELETE"):
            trigger_name = f"trg_{table_name}_{operation.lower()}_guard"
            connection.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON {table_name}")
            connection.execute(
                f"""CREATE TRIGGER {trigger_name}
                    BEFORE {operation} ON {table_name}
                    FOR EACH ROW EXECUTE FUNCTION miniogas_reject_execution_evidence_rewrite()"""
            )
    for table_name in PHASE3_SCOPED_TABLES:
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


def _phase3_sqlite_invariant_guards(connection: Any) -> None:
    connection.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_operation_quantity_conservation
           BEFORE INSERT ON operation_quantity_reports
           FOR EACH ROW
           WHEN (
               COALESCE((
                   SELECT SUM(good_quantity + scrap_quantity + rework_quantity)
                   FROM operation_quantity_reports
                   WHERE tenant_id=NEW.tenant_id AND site_id=NEW.site_id
                     AND operation_task_id=NEW.operation_task_id
               ), 0) + NEW.good_quantity + NEW.scrap_quantity + NEW.rework_quantity
           ) > (
               SELECT planned_quantity FROM operation_tasks
               WHERE tenant_id=NEW.tenant_id AND site_id=NEW.site_id
                 AND id=NEW.operation_task_id
           ) + 0.000000001
           BEGIN
               SELECT RAISE(ABORT, 'quantity reports exceed operation plan');
           END"""
    )
    connection.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_operation_task_transition_guard
           BEFORE UPDATE OF status ON operation_tasks
           FOR EACH ROW
           WHEN OLD.status != NEW.status AND NOT (
               (OLD.status='dispatched' AND NEW.status IN ('setup','held')) OR
               (OLD.status='setup' AND NEW.status IN ('ready','held')) OR
               (OLD.status='ready' AND NEW.status IN ('running','held')) OR
               (OLD.status='running' AND NEW.status IN ('paused','held','completed')) OR
               (OLD.status='paused' AND NEW.status IN ('running','held')) OR
               (OLD.status='held' AND NEW.status IN (
                   'dispatched','setup','ready','running','paused'
               )) OR
               (OLD.status='completed' AND NEW.status='closed')
           )
           BEGIN
               SELECT RAISE(ABORT, 'invalid operation task state transition');
           END"""
    )
    connection.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_operation_task_predecessor_guard
           BEFORE UPDATE OF status ON operation_tasks
           FOR EACH ROW
           WHEN NEW.status='setup' AND EXISTS (
               SELECT 1 FROM operation_tasks predecessor
               WHERE predecessor.tenant_id=NEW.tenant_id
                 AND predecessor.site_id=NEW.site_id
                 AND predecessor.work_order_execution_id=NEW.work_order_execution_id
                 AND predecessor.sequence<NEW.sequence
                 AND predecessor.status NOT IN ('completed','closed')
           )
           BEGIN
               SELECT RAISE(ABORT, 'predecessor operation is incomplete');
           END"""
    )
    connection.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_operation_task_ready_evidence_guard
           BEFORE UPDATE OF status ON operation_tasks
           FOR EACH ROW
           WHEN NEW.status='ready' AND NOT EXISTS (
               SELECT 1 FROM operation_setups setup
               WHERE setup.tenant_id=NEW.tenant_id AND setup.site_id=NEW.site_id
                 AND setup.operation_task_id=NEW.id AND setup.status='completed'
                 AND LENGTH(TRIM(COALESCE(setup.evidence_reference, '')))>0
           )
           BEGIN
               SELECT RAISE(ABORT, 'completed setup evidence is required');
           END"""
    )
    connection.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_operation_task_completion_guard
           BEFORE UPDATE OF status ON operation_tasks
           FOR EACH ROW
           WHEN NEW.status='completed' AND (
               LENGTH(TRIM(COALESCE(NEW.completion_evidence_reference, '')))=0 OR
               ABS(COALESCE((
                   SELECT SUM(good_quantity + scrap_quantity + rework_quantity)
                   FROM operation_quantity_reports
                   WHERE tenant_id=NEW.tenant_id AND site_id=NEW.site_id
                     AND operation_task_id=NEW.id
               ), 0) - NEW.planned_quantity) > 0.000000001
           )
           BEGIN
               SELECT RAISE(ABORT, 'completion evidence and exact quantity are required');
           END"""
    )


def _phase3_postgres_invariant_guards(connection: Any) -> None:
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_guard_operation_quantity()
           RETURNS trigger AS $$
           DECLARE
               planned DOUBLE PRECISION;
               accounted DOUBLE PRECISION;
           BEGIN
               SELECT planned_quantity INTO planned
               FROM operation_tasks
               WHERE tenant_id=NEW.tenant_id AND site_id=NEW.site_id
                 AND id=NEW.operation_task_id
               FOR UPDATE;
               SELECT COALESCE(SUM(good_quantity + scrap_quantity + rework_quantity), 0)
               INTO accounted
               FROM operation_quantity_reports
               WHERE tenant_id=NEW.tenant_id AND site_id=NEW.site_id
                 AND operation_task_id=NEW.operation_task_id;
               IF accounted + NEW.good_quantity + NEW.scrap_quantity
                    + NEW.rework_quantity > planned + 0.000000001 THEN
                   RAISE EXCEPTION 'quantity reports exceed operation plan';
               END IF;
               RETURN NEW;
           END;
           $$ LANGUAGE plpgsql"""
    )
    connection.execute(
        "DROP TRIGGER IF EXISTS trg_operation_quantity_conservation "
        "ON operation_quantity_reports"
    )
    connection.execute(
        """CREATE TRIGGER trg_operation_quantity_conservation
           BEFORE INSERT ON operation_quantity_reports
           FOR EACH ROW EXECUTE FUNCTION miniogas_guard_operation_quantity()"""
    )
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_guard_operation_transition()
           RETURNS trigger AS $$
           DECLARE
               accounted DOUBLE PRECISION;
           BEGIN
               IF OLD.status IS DISTINCT FROM NEW.status AND NOT (
                   (OLD.status='dispatched' AND NEW.status IN ('setup','held')) OR
                   (OLD.status='setup' AND NEW.status IN ('ready','held')) OR
                   (OLD.status='ready' AND NEW.status IN ('running','held')) OR
                   (OLD.status='running' AND NEW.status IN ('paused','held','completed')) OR
                   (OLD.status='paused' AND NEW.status IN ('running','held')) OR
                   (OLD.status='held' AND NEW.status IN (
                       'dispatched','setup','ready','running','paused'
                   )) OR
                   (OLD.status='completed' AND NEW.status='closed')
               ) THEN
                   RAISE EXCEPTION 'invalid operation task state transition';
               END IF;
               IF NEW.status='setup' AND EXISTS (
                   SELECT 1 FROM operation_tasks predecessor
                   WHERE predecessor.tenant_id=NEW.tenant_id
                     AND predecessor.site_id=NEW.site_id
                     AND predecessor.work_order_execution_id=NEW.work_order_execution_id
                     AND predecessor.sequence<NEW.sequence
                     AND predecessor.status NOT IN ('completed','closed')
               ) THEN
                   RAISE EXCEPTION 'predecessor operation is incomplete';
               END IF;
               IF NEW.status='ready' AND NOT EXISTS (
                   SELECT 1 FROM operation_setups setup
                   WHERE setup.tenant_id=NEW.tenant_id AND setup.site_id=NEW.site_id
                     AND setup.operation_task_id=NEW.id AND setup.status='completed'
                     AND LENGTH(TRIM(COALESCE(setup.evidence_reference, '')))>0
               ) THEN
                   RAISE EXCEPTION 'completed setup evidence is required';
               END IF;
               IF NEW.status='completed' THEN
                   SELECT COALESCE(SUM(
                       good_quantity + scrap_quantity + rework_quantity
                   ), 0) INTO accounted
                   FROM operation_quantity_reports
                   WHERE tenant_id=NEW.tenant_id AND site_id=NEW.site_id
                     AND operation_task_id=NEW.id;
                   IF LENGTH(TRIM(COALESCE(NEW.completion_evidence_reference, '')))=0
                      OR ABS(accounted - NEW.planned_quantity) > 0.000000001 THEN
                       RAISE EXCEPTION 'completion evidence and exact quantity are required';
                   END IF;
               END IF;
               RETURN NEW;
           END;
           $$ LANGUAGE plpgsql"""
    )
    connection.execute(
        "DROP TRIGGER IF EXISTS trg_operation_task_invariant_guard ON operation_tasks"
    )
    connection.execute(
        """CREATE TRIGGER trg_operation_task_invariant_guard
           BEFORE UPDATE OF status ON operation_tasks
           FOR EACH ROW EXECUTE FUNCTION miniogas_guard_operation_transition()"""
    )


PHASE3_MIGRATIONS = [
    Migration(
        version=PHASE3_EXECUTION_MIGRATION_VERSION,
        description=(
            "Phase 3 production-order execution, operation state machine, quantity "
            "conservation, evidence, downtime, history and replay authority"
        ),
        checksum_material=(
            "phase3-execution-v1|strict-state-machine-v1|quantity-conservation-v1|"
            "append-only-evidence-v1|postgres-force-rls-v1|"
            + "|".join(PHASE3_SCOPED_TABLES)
        ),
        sqlite_action=_phase3_sqlite_execution,
        postgres_action=_phase3_postgres_execution,
    ),
    Migration(
        version=PHASE3_INVARIANT_GUARD_VERSION,
        description=(
            "Phase 3 database-enforced operation transitions, setup/completion evidence "
            "and quantity conservation"
        ),
        checksum_material=(
            "phase3-invariant-guards-v1|operation-transition-v1|predecessor-v1|"
            "setup-evidence-v1|completion-evidence-v1|quantity-conservation-v1"
        ),
        sqlite_action=_phase3_sqlite_invariant_guards,
        postgres_action=_phase3_postgres_invariant_guards,
    ),
]
