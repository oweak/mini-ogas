from __future__ import annotations

from typing import Any

from .migrations import Migration

PHASE6_MAINTENANCE_VERSION = "2026.07.14-phase6-maintenance-operations"
PHASE6_MAINTENANCE_GUARDS_VERSION = "2026.07.14-phase6-maintenance-invariant-guards"
PHASE6_MRO_MOVEMENT_BINDING_VERSION = "2026.07.14-phase6-mro-movement-binding"
PHASE6_MAINTENANCE_LIFECYCLE_GUARDS_VERSION = "2026.07.14-phase6-maintenance-lifecycle-guards"

PHASE6_SCOPED_TABLES = (
    "maintenance_assets",
    "maintenance_codes",
    "maintenance_checklists",
    "maintenance_checklist_items",
    "preventive_maintenance_plans",
    "maintenance_requests",
    "maintenance_orders",
    "maintenance_check_results",
    "maintenance_spare_usages",
    "maintenance_tools",
    "maintenance_tool_assignments",
    "tool_life_events",
    "calibration_events",
    "maintenance_status_history",
)

PHASE6_APPEND_ONLY_TABLES = (
    "maintenance_checklist_items",
    "maintenance_check_results",
    "maintenance_spare_usages",
    "maintenance_tool_assignments",
    "tool_life_events",
    "calibration_events",
    "maintenance_status_history",
)

SQLITE_TABLES = (
    """CREATE TABLE IF NOT EXISTS maintenance_assets (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           asset_code TEXT NOT NULL,
           equipment_id INTEGER NOT NULL REFERENCES equipment(id),
           parent_asset_id INTEGER REFERENCES maintenance_assets(id),
           name TEXT NOT NULL,
           criticality TEXT NOT NULL CHECK (criticality IN ('low','medium','high','critical')),
           status TEXT NOT NULL DEFAULT 'active'
               CHECK (status IN ('active','degraded','out_of_service','retired')),
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, asset_code),
           UNIQUE (tenant_id, site_id, equipment_id),
           CHECK (parent_asset_id IS NULL OR parent_asset_id<>id)
       )""",
    """CREATE TABLE IF NOT EXISTS maintenance_codes (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           code TEXT NOT NULL,
           code_type TEXT NOT NULL CHECK (code_type IN ('failure','cause','remedy')),
           description TEXT NOT NULL,
           active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, code),
           UNIQUE (tenant_id, site_id, code_type, code)
       )""",
    """CREATE TABLE IF NOT EXISTS maintenance_checklists (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           checklist_code TEXT NOT NULL,
           revision INTEGER NOT NULL CHECK (revision > 0),
           name TEXT NOT NULL,
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
           UNIQUE (tenant_id, site_id, checklist_code, revision)
       )""",
    """CREATE TABLE IF NOT EXISTS maintenance_checklist_items (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           checklist_id INTEGER NOT NULL REFERENCES maintenance_checklists(id),
           sequence INTEGER NOT NULL CHECK (sequence > 0),
           instruction TEXT NOT NULL,
           required INTEGER NOT NULL DEFAULT 1 CHECK (required IN (0,1)),
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, checklist_id, sequence)
       )""",
    """CREATE TABLE IF NOT EXISTS preventive_maintenance_plans (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           plan_code TEXT NOT NULL,
           asset_id INTEGER NOT NULL REFERENCES maintenance_assets(id),
           checklist_id INTEGER NOT NULL REFERENCES maintenance_checklists(id),
           interval_hours INTEGER NOT NULL CHECK (interval_hours > 0),
           next_due_at TEXT NOT NULL,
           production_impact TEXT NOT NULL CHECK (production_impact IN (
               'none','reduced_capacity','equipment_unavailable'
           )),
           status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','effective','retired')),
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           effective_by TEXT,
           effectivity_evidence_reference TEXT,
           effective_at TEXT,
           last_generated_at TEXT,
           UNIQUE (tenant_id, site_id, plan_code)
       )""",
    """CREATE TABLE IF NOT EXISTS maintenance_requests (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           request_code TEXT NOT NULL,
           asset_id INTEGER NOT NULL REFERENCES maintenance_assets(id),
           source_type TEXT NOT NULL CHECK (source_type IN (
               'alarm','manual','inspection','preventive'
           )),
           source_reference TEXT NOT NULL,
           description TEXT NOT NULL,
           priority TEXT NOT NULL CHECK (priority IN ('low','medium','high','critical')),
           observed_at TEXT NOT NULL,
           status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','converted','cancelled')),
           requested_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           converted_at TEXT,
           UNIQUE (tenant_id, site_id, request_code)
       )""",
    """CREATE TABLE IF NOT EXISTS maintenance_orders (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           order_code TEXT NOT NULL,
           request_id INTEGER NOT NULL REFERENCES maintenance_requests(id),
           asset_id INTEGER NOT NULL REFERENCES maintenance_assets(id),
           order_type TEXT NOT NULL CHECK (order_type IN (
               'corrective','preventive','calibration','tooling'
           )),
           priority TEXT NOT NULL CHECK (priority IN ('low','medium','high','critical')),
           assigned_personnel_id INTEGER NOT NULL REFERENCES personnel(id),
           checklist_id INTEGER NOT NULL REFERENCES maintenance_checklists(id),
           operation_task_id INTEGER REFERENCES operation_tasks(id),
           operation_downtime_id INTEGER REFERENCES operation_downtime(id),
           production_impact TEXT NOT NULL CHECK (production_impact IN (
               'none','reduced_capacity','equipment_unavailable'
           )),
           planned_start_at TEXT NOT NULL,
           planned_end_at TEXT NOT NULL,
           status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN (
               'draft','approved','in_progress','work_completed','verified','closed','cancelled'
           )),
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           approved_by TEXT,
           approval_evidence_reference TEXT,
           approved_at TEXT,
           started_by TEXT,
           start_evidence_reference TEXT,
           started_at TEXT,
           failure_code_id INTEGER REFERENCES maintenance_codes(id),
           cause_code_id INTEGER REFERENCES maintenance_codes(id),
           remedy_code_id INTEGER REFERENCES maintenance_codes(id),
           work_evidence_reference TEXT,
           completed_by TEXT,
           work_completed_at TEXT,
           verification_result TEXT CHECK (verification_result IN (
               'restored','degraded','not_restored'
           )),
           verification_reference TEXT,
           verified_by TEXT,
           verified_at TEXT,
           closed_by TEXT,
           closed_at TEXT,
           UNIQUE (tenant_id, site_id, order_code),
           UNIQUE (tenant_id, site_id, operation_downtime_id),
           CHECK (planned_end_at > planned_start_at),
           CHECK (operation_downtime_id IS NULL OR operation_task_id IS NOT NULL)
       )""",
    """CREATE TABLE IF NOT EXISTS maintenance_check_results (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           maintenance_order_id INTEGER NOT NULL REFERENCES maintenance_orders(id),
           checklist_item_id INTEGER NOT NULL REFERENCES maintenance_checklist_items(id),
           result TEXT NOT NULL CHECK (result IN ('pass','fail','not_applicable')),
           evidence_reference TEXT NOT NULL,
           recorded_by TEXT NOT NULL,
           recorded_at TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, maintenance_order_id, checklist_item_id)
       )""",
    """CREATE TABLE IF NOT EXISTS maintenance_spare_usages (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           usage_id TEXT NOT NULL,
           maintenance_order_id INTEGER NOT NULL REFERENCES maintenance_orders(id),
           inventory_movement_id INTEGER NOT NULL REFERENCES inventory_movements(id),
           evidence_reference TEXT NOT NULL,
           recorded_by TEXT NOT NULL,
           recorded_at TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, usage_id),
           UNIQUE (tenant_id, site_id, inventory_movement_id)
       )""",
    """CREATE TABLE IF NOT EXISTS maintenance_tools (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           tool_code TEXT NOT NULL,
           asset_id INTEGER NOT NULL REFERENCES maintenance_assets(id),
           name TEXT NOT NULL,
           tool_type TEXT NOT NULL,
           life_limit REAL NOT NULL CHECK (life_limit > 0),
           life_used REAL NOT NULL DEFAULT 0 CHECK (life_used >= 0),
           life_uom TEXT NOT NULL,
           calibration_required INTEGER NOT NULL DEFAULT 0 CHECK (calibration_required IN (0,1)),
           calibration_due_at TEXT,
           status TEXT NOT NULL DEFAULT 'active'
               CHECK (status IN ('active','over_life','calibration_invalid','retired')),
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, tool_code),
           CHECK (calibration_required=0 OR calibration_due_at IS NOT NULL)
       )""",
    """CREATE TABLE IF NOT EXISTS maintenance_tool_assignments (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           tool_id INTEGER NOT NULL REFERENCES maintenance_tools(id),
           operation_task_id INTEGER NOT NULL REFERENCES operation_tasks(id),
           evidence_reference TEXT NOT NULL,
           assigned_by TEXT NOT NULL,
           assigned_at TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, tool_id, operation_task_id)
       )""",
    """CREATE TABLE IF NOT EXISTS tool_life_events (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           event_id TEXT NOT NULL,
           tool_id INTEGER NOT NULL REFERENCES maintenance_tools(id),
           usage_delta REAL NOT NULL CHECK (usage_delta > 0),
           operation_task_id INTEGER REFERENCES operation_tasks(id),
           occurred_at TEXT NOT NULL,
           evidence_reference TEXT NOT NULL,
           recorded_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, event_id)
       )""",
    """CREATE TABLE IF NOT EXISTS calibration_events (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           calibration_code TEXT NOT NULL,
           tool_id INTEGER NOT NULL REFERENCES maintenance_tools(id),
           result TEXT NOT NULL CHECK (result IN ('pass','fail')),
           valid_from TEXT NOT NULL,
           valid_to TEXT NOT NULL,
           performed_by_personnel_id INTEGER NOT NULL REFERENCES personnel(id),
           evidence_reference TEXT NOT NULL,
           recorded_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, calibration_code),
           CHECK (valid_to > valid_from)
       )""",
    """CREATE TABLE IF NOT EXISTS maintenance_status_history (
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
        "next_due_at",
        "last_generated_at",
        "observed_at",
        "converted_at",
        "planned_start_at",
        "planned_end_at",
        "started_at",
        "work_completed_at",
        "verified_at",
        "closed_at",
        "recorded_at",
        "calibration_due_at",
        "assigned_at",
        "occurred_at",
        "valid_from",
        "valid_to",
    ):
        converted = converted.replace(f"{column} TEXT", f"{column} TIMESTAMPTZ")
    converted = converted.replace(
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    )
    return converted


POSTGRES_TABLES = tuple(_postgres_statement(statement) for statement in SQLITE_TABLES)


def _create_tables(connection: Any, statements: tuple[str, ...]) -> None:
    for statement in statements:
        connection.execute(statement)


def _create_indexes(connection: Any) -> None:
    for table_name in PHASE6_SCOPED_TABLES:
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_scope ON {table_name}(tenant_id, site_id)"
        )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_maintenance_checklist_one_effective "
        "ON maintenance_checklists(tenant_id, site_id, checklist_code) WHERE status='effective'"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_maintenance_order_asset_status "
        "ON maintenance_orders(tenant_id, site_id, asset_id, status)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_maintenance_tool_task "
        "ON maintenance_tool_assignments(tenant_id, site_id, operation_task_id, tool_id)"
    )


def _phase6_sqlite_schema(connection: Any) -> None:
    _create_tables(connection, SQLITE_TABLES)
    _create_indexes(connection)
    for table_name in PHASE6_APPEND_ONLY_TABLES:
        for operation in ("UPDATE", "DELETE"):
            connection.execute(
                f"""CREATE TRIGGER IF NOT EXISTS trg_{table_name}_{operation.lower()}_guard
                    BEFORE {operation} ON {table_name}
                    FOR EACH ROW BEGIN
                        SELECT RAISE(ABORT, 'maintenance evidence is append-only');
                    END"""
            )
    connection.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_maintenance_checklist_identity_guard
           BEFORE UPDATE ON maintenance_checklists
           FOR EACH ROW WHEN NEW.checklist_code<>OLD.checklist_code
             OR NEW.revision<>OLD.revision OR NEW.name<>OLD.name
           BEGIN
               SELECT RAISE(ABORT, 'maintenance checklist identity is immutable');
           END"""
    )


def _phase6_postgres_schema(connection: Any) -> None:
    _create_tables(connection, POSTGRES_TABLES)
    _create_indexes(connection)
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_reject_maintenance_evidence_rewrite()
           RETURNS trigger AS $$
           BEGIN
               RAISE EXCEPTION 'maintenance evidence is append-only';
           END;
           $$ LANGUAGE plpgsql"""
    )
    for table_name in PHASE6_APPEND_ONLY_TABLES:
        for operation in ("UPDATE", "DELETE"):
            trigger_name = f"trg_{table_name}_{operation.lower()}_guard"
            connection.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON {table_name}")
            connection.execute(
                f"""CREATE TRIGGER {trigger_name}
                    BEFORE {operation} ON {table_name}
                    FOR EACH ROW EXECUTE FUNCTION miniogas_reject_maintenance_evidence_rewrite()"""
            )
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_guard_maintenance_checklist_identity()
           RETURNS trigger AS $$
           BEGIN
               IF NEW.checklist_code<>OLD.checklist_code OR NEW.revision<>OLD.revision
                  OR NEW.name<>OLD.name THEN
                   RAISE EXCEPTION 'maintenance checklist identity is immutable';
               END IF;
               RETURN NEW;
           END;
           $$ LANGUAGE plpgsql"""
    )
    connection.execute(
        "DROP TRIGGER IF EXISTS trg_maintenance_checklist_identity_guard ON maintenance_checklists"
    )
    connection.execute(
        """CREATE TRIGGER trg_maintenance_checklist_identity_guard
           BEFORE UPDATE ON maintenance_checklists
           FOR EACH ROW EXECUTE FUNCTION miniogas_guard_maintenance_checklist_identity()"""
    )
    for table_name in PHASE6_SCOPED_TABLES:
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


def _phase6_sqlite_guards(connection: Any) -> None:
    connection.execute("DROP TRIGGER IF EXISTS trg_maintenance_work_complete_guard")
    connection.execute(
        """CREATE TRIGGER trg_maintenance_work_complete_guard
           BEFORE UPDATE OF status ON maintenance_orders
           FOR EACH ROW WHEN NEW.status='work_completed' AND (
               OLD.status<>'in_progress' OR NEW.failure_code_id IS NULL
               OR NEW.cause_code_id IS NULL OR NEW.remedy_code_id IS NULL
               OR NEW.work_evidence_reference IS NULL OR NEW.completed_by IS NULL
               OR EXISTS (
                   SELECT 1 FROM maintenance_checklist_items item
                   WHERE item.checklist_id=OLD.checklist_id AND item.required=1
                     AND NOT EXISTS (
                         SELECT 1 FROM maintenance_check_results result
                         WHERE result.maintenance_order_id=OLD.id
                           AND result.checklist_item_id=item.id AND result.result='pass'
                     )
               )
           )
           BEGIN
               SELECT RAISE(
                   ABORT,
                   'maintenance work completion requires passing checklist and evidence'
               );
           END"""
    )
    connection.execute("DROP TRIGGER IF EXISTS trg_maintenance_verification_guard")
    connection.execute(
        """CREATE TRIGGER trg_maintenance_verification_guard
           BEFORE UPDATE OF status ON maintenance_orders
           FOR EACH ROW WHEN NEW.status='verified' AND (
               OLD.status<>'work_completed' OR NEW.verification_reference IS NULL
               OR NEW.verification_result IS NULL OR NEW.verified_by IS NULL
               OR NEW.verified_by=OLD.completed_by
           )
           BEGIN
               SELECT RAISE(ABORT, 'maintenance verification requires independent evidence');
           END"""
    )
    connection.execute("DROP TRIGGER IF EXISTS trg_tool_life_event_apply")
    connection.execute(
        """CREATE TRIGGER trg_tool_life_event_apply
           AFTER INSERT ON tool_life_events
           FOR EACH ROW BEGIN
               UPDATE maintenance_tools
               SET life_used=life_used+NEW.usage_delta,
                   status=CASE WHEN life_used+NEW.usage_delta>=life_limit
                               THEN 'over_life' ELSE status END
               WHERE id=NEW.tool_id;
           END"""
    )
    connection.execute("DROP TRIGGER IF EXISTS trg_calibration_event_apply")
    connection.execute(
        """CREATE TRIGGER trg_calibration_event_apply
           AFTER INSERT ON calibration_events
           FOR EACH ROW BEGIN
               UPDATE maintenance_tools
               SET calibration_due_at=NEW.valid_to,
                   status=CASE WHEN NEW.result='fail' THEN 'calibration_invalid'
                               WHEN life_used>=life_limit THEN 'over_life' ELSE 'active' END
               WHERE id=NEW.tool_id;
           END"""
    )
    connection.execute("DROP TRIGGER IF EXISTS trg_operation_task_maintenance_guard")
    connection.execute(
        """CREATE TRIGGER trg_operation_task_maintenance_guard
           BEFORE UPDATE OF status ON operation_tasks
           FOR EACH ROW WHEN NEW.status='running' AND OLD.status<>'running'
           BEGIN
               SELECT CASE WHEN EXISTS (
                   SELECT 1 FROM operation_task_assignments assignment
                   JOIN maintenance_assets asset ON asset.equipment_id=assignment.equipment_id
                   JOIN maintenance_orders maintenance_order ON maintenance_order.asset_id=asset.id
                   WHERE assignment.operation_task_id=NEW.id
                     AND maintenance_order.status IN ('in_progress','work_completed')
                     AND maintenance_order.production_impact='equipment_unavailable'
               ) THEN RAISE(ABORT, 'active maintenance blocks task') END;
               SELECT CASE WHEN EXISTS (
                   SELECT 1 FROM maintenance_tool_assignments assignment
                   JOIN maintenance_tools tool ON tool.id=assignment.tool_id
                   WHERE assignment.operation_task_id=NEW.id AND tool.status='over_life'
               ) THEN RAISE(ABORT, 'tool life exceeded') END;
               SELECT CASE WHEN EXISTS (
                   SELECT 1 FROM maintenance_tool_assignments assignment
                   JOIN maintenance_tools tool ON tool.id=assignment.tool_id
                   WHERE assignment.operation_task_id=NEW.id
                     AND (tool.status='calibration_invalid'
                          OR (tool.calibration_required=1
                              AND julianday(tool.calibration_due_at)<=julianday('now')))
               ) THEN RAISE(ABORT, 'tool calibration invalid') END;
           END"""
    )


def _phase6_postgres_guards(connection: Any) -> None:
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_guard_maintenance_work_complete()
           RETURNS trigger AS $$
           BEGIN
               IF NEW.status='work_completed' AND (
                   OLD.status<>'in_progress' OR NEW.failure_code_id IS NULL
                   OR NEW.cause_code_id IS NULL OR NEW.remedy_code_id IS NULL
                   OR NEW.work_evidence_reference IS NULL OR NEW.completed_by IS NULL
                   OR EXISTS (
                       SELECT 1 FROM maintenance_checklist_items item
                       WHERE item.checklist_id=OLD.checklist_id AND item.required=1
                         AND NOT EXISTS (
                             SELECT 1 FROM maintenance_check_results result
                             WHERE result.maintenance_order_id=OLD.id
                               AND result.checklist_item_id=item.id AND result.result='pass'
                         )
                   )
               ) THEN
                   RAISE EXCEPTION
                       'maintenance work completion requires passing checklist and evidence';
               END IF;
               RETURN NEW;
           END;
           $$ LANGUAGE plpgsql"""
    )
    connection.execute(
        "DROP TRIGGER IF EXISTS trg_maintenance_work_complete_guard ON maintenance_orders"
    )
    connection.execute(
        """CREATE TRIGGER trg_maintenance_work_complete_guard
           BEFORE UPDATE OF status ON maintenance_orders
           FOR EACH ROW EXECUTE FUNCTION miniogas_guard_maintenance_work_complete()"""
    )
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_guard_maintenance_verification()
           RETURNS trigger AS $$
           BEGIN
               IF NEW.status='verified' AND (
                   OLD.status<>'work_completed' OR NEW.verification_reference IS NULL
                   OR NEW.verification_result IS NULL OR NEW.verified_by IS NULL
                   OR NEW.verified_by=OLD.completed_by
               ) THEN
                   RAISE EXCEPTION 'maintenance verification requires independent evidence';
               END IF;
               RETURN NEW;
           END;
           $$ LANGUAGE plpgsql"""
    )
    connection.execute(
        "DROP TRIGGER IF EXISTS trg_maintenance_verification_guard ON maintenance_orders"
    )
    connection.execute(
        """CREATE TRIGGER trg_maintenance_verification_guard
           BEFORE UPDATE OF status ON maintenance_orders
           FOR EACH ROW EXECUTE FUNCTION miniogas_guard_maintenance_verification()"""
    )
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_apply_tool_life_event()
           RETURNS trigger AS $$
           BEGIN
               UPDATE maintenance_tools
               SET life_used=life_used+NEW.usage_delta,
                   status=CASE WHEN life_used+NEW.usage_delta>=life_limit
                               THEN 'over_life' ELSE status END
               WHERE id=NEW.tool_id;
               RETURN NEW;
           END;
           $$ LANGUAGE plpgsql"""
    )
    connection.execute("DROP TRIGGER IF EXISTS trg_tool_life_event_apply ON tool_life_events")
    connection.execute(
        """CREATE TRIGGER trg_tool_life_event_apply
           AFTER INSERT ON tool_life_events
           FOR EACH ROW EXECUTE FUNCTION miniogas_apply_tool_life_event()"""
    )
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_apply_calibration_event()
           RETURNS trigger AS $$
           BEGIN
               UPDATE maintenance_tools
               SET calibration_due_at=NEW.valid_to,
                   status=CASE WHEN NEW.result='fail' THEN 'calibration_invalid'
                               WHEN life_used>=life_limit THEN 'over_life' ELSE 'active' END
               WHERE id=NEW.tool_id;
               RETURN NEW;
           END;
           $$ LANGUAGE plpgsql"""
    )
    connection.execute("DROP TRIGGER IF EXISTS trg_calibration_event_apply ON calibration_events")
    connection.execute(
        """CREATE TRIGGER trg_calibration_event_apply
           AFTER INSERT ON calibration_events
           FOR EACH ROW EXECUTE FUNCTION miniogas_apply_calibration_event()"""
    )
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_guard_operation_task_maintenance()
           RETURNS trigger AS $$
           BEGIN
               IF NEW.status='running' AND OLD.status<>'running' THEN
                   IF EXISTS (
                       SELECT 1 FROM operation_task_assignments assignment
                       JOIN maintenance_assets asset ON asset.equipment_id=assignment.equipment_id
                       JOIN maintenance_orders maintenance_order
                         ON maintenance_order.asset_id=asset.id
                       WHERE assignment.operation_task_id=NEW.id
                         AND maintenance_order.status IN ('in_progress','work_completed')
                         AND maintenance_order.production_impact='equipment_unavailable'
                   ) THEN
                       RAISE EXCEPTION 'active maintenance blocks task';
                   END IF;
                   IF EXISTS (
                       SELECT 1 FROM maintenance_tool_assignments assignment
                       JOIN maintenance_tools tool ON tool.id=assignment.tool_id
                       WHERE assignment.operation_task_id=NEW.id AND tool.status='over_life'
                   ) THEN
                       RAISE EXCEPTION 'tool life exceeded';
                   END IF;
                   IF EXISTS (
                       SELECT 1 FROM maintenance_tool_assignments assignment
                       JOIN maintenance_tools tool ON tool.id=assignment.tool_id
                       WHERE assignment.operation_task_id=NEW.id
                         AND (tool.status='calibration_invalid'
                              OR (tool.calibration_required=1 AND tool.calibration_due_at<=now()))
                   ) THEN
                       RAISE EXCEPTION 'tool calibration invalid';
                   END IF;
               END IF;
               RETURN NEW;
           END;
           $$ LANGUAGE plpgsql"""
    )
    connection.execute(
        "DROP TRIGGER IF EXISTS trg_operation_task_maintenance_guard ON operation_tasks"
    )
    connection.execute(
        """CREATE TRIGGER trg_operation_task_maintenance_guard
           BEFORE UPDATE OF status ON operation_tasks
           FOR EACH ROW EXECUTE FUNCTION miniogas_guard_operation_task_maintenance()"""
    )


def _phase6_sqlite_mro_binding(connection: Any) -> None:
    columns = {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(inventory_movements)").fetchall()
    }
    if "maintenance_order_id" not in columns:
        connection.execute(
            """ALTER TABLE inventory_movements
               ADD COLUMN maintenance_order_id INTEGER REFERENCES maintenance_orders(id)"""
        )
    connection.execute(
        """CREATE INDEX IF NOT EXISTS idx_inventory_movement_maintenance_order
           ON inventory_movements(tenant_id, site_id, maintenance_order_id)"""
    )
    connection.execute("DROP TRIGGER IF EXISTS trg_inventory_consume_authority_guard")
    connection.execute(
        """CREATE TRIGGER trg_inventory_consume_authority_guard
           BEFORE INSERT ON inventory_movements
           FOR EACH ROW WHEN NEW.movement_type='consume' AND (
               (NEW.operation_task_id IS NULL AND NEW.maintenance_order_id IS NULL)
               OR (NEW.operation_task_id IS NOT NULL AND NEW.maintenance_order_id IS NOT NULL)
           )
           BEGIN
               SELECT RAISE(
                   ABORT,
                   'consume requires exactly one operation or maintenance authority'
               );
           END"""
    )


def _phase6_postgres_mro_binding(connection: Any) -> None:
    connection.execute(
        """ALTER TABLE inventory_movements
           ADD COLUMN IF NOT EXISTS maintenance_order_id BIGINT REFERENCES maintenance_orders(id)"""
    )
    connection.execute(
        """CREATE INDEX IF NOT EXISTS idx_inventory_movement_maintenance_order
           ON inventory_movements(tenant_id, site_id, maintenance_order_id)"""
    )
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_guard_inventory_consume_authority()
           RETURNS trigger AS $$
           BEGIN
               IF NEW.movement_type='consume' AND (
                   (NEW.operation_task_id IS NULL AND NEW.maintenance_order_id IS NULL)
                   OR (NEW.operation_task_id IS NOT NULL AND NEW.maintenance_order_id IS NOT NULL)
               ) THEN
                   RAISE EXCEPTION
                       'consume requires exactly one operation or maintenance authority';
               END IF;
               RETURN NEW;
           END;
           $$ LANGUAGE plpgsql"""
    )
    connection.execute(
        "DROP TRIGGER IF EXISTS trg_inventory_consume_authority_guard ON inventory_movements"
    )
    connection.execute(
        """CREATE TRIGGER trg_inventory_consume_authority_guard
           BEFORE INSERT ON inventory_movements
           FOR EACH ROW EXECUTE FUNCTION miniogas_guard_inventory_consume_authority()"""
    )


def _phase6_sqlite_lifecycle_guards(connection: Any) -> None:
    connection.execute("DROP TRIGGER IF EXISTS trg_maintenance_order_lifecycle_guard")
    connection.execute(
        """CREATE TRIGGER trg_maintenance_order_lifecycle_guard
           BEFORE UPDATE ON maintenance_orders
           FOR EACH ROW WHEN
               NEW.order_code<>OLD.order_code OR NEW.request_id<>OLD.request_id
               OR NEW.asset_id<>OLD.asset_id OR NEW.order_type<>OLD.order_type
               OR NEW.priority<>OLD.priority
               OR NEW.assigned_personnel_id<>OLD.assigned_personnel_id
               OR NEW.checklist_id<>OLD.checklist_id
               OR COALESCE(NEW.operation_task_id,-1)<>COALESCE(OLD.operation_task_id,-1)
               OR COALESCE(NEW.operation_downtime_id,-1)<>COALESCE(OLD.operation_downtime_id,-1)
               OR NEW.production_impact<>OLD.production_impact
               OR NEW.planned_start_at<>OLD.planned_start_at
               OR NEW.planned_end_at<>OLD.planned_end_at
               OR NOT (
                   NEW.status=OLD.status
                   OR (OLD.status='draft' AND NEW.status IN ('approved','cancelled'))
                   OR (OLD.status='approved' AND NEW.status IN ('in_progress','cancelled'))
                   OR (OLD.status='in_progress' AND NEW.status='work_completed')
                   OR (OLD.status='work_completed' AND NEW.status='verified')
                   OR (OLD.status='verified' AND NEW.status='closed')
               )
               OR (OLD.status IN (
                   'approved','in_progress','work_completed','verified','closed'
               ) AND (
                   COALESCE(NEW.approved_by,'')<>COALESCE(OLD.approved_by,'')
                   OR COALESCE(NEW.approval_evidence_reference,'')
                      <>COALESCE(OLD.approval_evidence_reference,'')
                   OR COALESCE(NEW.approved_at,'')<>COALESCE(OLD.approved_at,'')
               ))
               OR (OLD.status IN ('work_completed','verified','closed') AND (
                   COALESCE(NEW.failure_code_id,-1)<>COALESCE(OLD.failure_code_id,-1)
                   OR COALESCE(NEW.cause_code_id,-1)<>COALESCE(OLD.cause_code_id,-1)
                   OR COALESCE(NEW.remedy_code_id,-1)<>COALESCE(OLD.remedy_code_id,-1)
                   OR COALESCE(NEW.work_evidence_reference,'')
                      <>COALESCE(OLD.work_evidence_reference,'')
                   OR COALESCE(NEW.completed_by,'')<>COALESCE(OLD.completed_by,'')
                   OR COALESCE(NEW.work_completed_at,'')<>COALESCE(OLD.work_completed_at,'')
               ))
               OR (OLD.status IN ('verified','closed') AND (
                   COALESCE(NEW.verification_result,'')<>COALESCE(OLD.verification_result,'')
                   OR COALESCE(NEW.verification_reference,'')
                      <>COALESCE(OLD.verification_reference,'')
                   OR COALESCE(NEW.verified_by,'')<>COALESCE(OLD.verified_by,'')
                   OR COALESCE(NEW.verified_at,'')<>COALESCE(OLD.verified_at,'')
               ))
           BEGIN
               SELECT RAISE(ABORT, 'maintenance order lifecycle or evidence is immutable');
           END"""
    )


def _phase6_postgres_lifecycle_guards(connection: Any) -> None:
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_guard_maintenance_order_lifecycle()
           RETURNS trigger AS $$
           BEGIN
               IF NEW.order_code<>OLD.order_code OR NEW.request_id<>OLD.request_id
                  OR NEW.asset_id<>OLD.asset_id OR NEW.order_type<>OLD.order_type
                  OR NEW.priority<>OLD.priority
                  OR NEW.assigned_personnel_id<>OLD.assigned_personnel_id
                  OR NEW.checklist_id<>OLD.checklist_id
                  OR COALESCE(NEW.operation_task_id,-1)<>COALESCE(OLD.operation_task_id,-1)
                  OR COALESCE(NEW.operation_downtime_id,-1)
                     <>COALESCE(OLD.operation_downtime_id,-1)
                  OR NEW.production_impact<>OLD.production_impact
                  OR NEW.planned_start_at<>OLD.planned_start_at
                  OR NEW.planned_end_at<>OLD.planned_end_at
                  OR NOT (
                      NEW.status=OLD.status
                      OR (OLD.status='draft' AND NEW.status IN ('approved','cancelled'))
                      OR (OLD.status='approved' AND NEW.status IN ('in_progress','cancelled'))
                      OR (OLD.status='in_progress' AND NEW.status='work_completed')
                      OR (OLD.status='work_completed' AND NEW.status='verified')
                      OR (OLD.status='verified' AND NEW.status='closed')
                  )
                  OR (OLD.status IN (
                      'approved','in_progress','work_completed','verified','closed'
                  ) AND (
                      COALESCE(NEW.approved_by,'')<>COALESCE(OLD.approved_by,'')
                      OR COALESCE(NEW.approval_evidence_reference,'')
                         <>COALESCE(OLD.approval_evidence_reference,'')
                      OR COALESCE(NEW.approved_at::text,'')<>COALESCE(OLD.approved_at::text,'')
                  ))
                  OR (OLD.status IN ('work_completed','verified','closed') AND (
                      COALESCE(NEW.failure_code_id,-1)<>COALESCE(OLD.failure_code_id,-1)
                      OR COALESCE(NEW.cause_code_id,-1)<>COALESCE(OLD.cause_code_id,-1)
                      OR COALESCE(NEW.remedy_code_id,-1)<>COALESCE(OLD.remedy_code_id,-1)
                      OR COALESCE(NEW.work_evidence_reference,'')
                         <>COALESCE(OLD.work_evidence_reference,'')
                      OR COALESCE(NEW.completed_by,'')<>COALESCE(OLD.completed_by,'')
                      OR COALESCE(NEW.work_completed_at::text,'')
                         <>COALESCE(OLD.work_completed_at::text,'')
                  ))
                  OR (OLD.status IN ('verified','closed') AND (
                      COALESCE(NEW.verification_result,'')<>COALESCE(OLD.verification_result,'')
                      OR COALESCE(NEW.verification_reference,'')
                         <>COALESCE(OLD.verification_reference,'')
                      OR COALESCE(NEW.verified_by,'')<>COALESCE(OLD.verified_by,'')
                      OR COALESCE(NEW.verified_at::text,'')<>COALESCE(OLD.verified_at::text,'')
                  )) THEN
                   RAISE EXCEPTION 'maintenance order lifecycle or evidence is immutable';
               END IF;
               RETURN NEW;
           END;
           $$ LANGUAGE plpgsql"""
    )
    connection.execute(
        "DROP TRIGGER IF EXISTS trg_maintenance_order_lifecycle_guard ON maintenance_orders"
    )
    connection.execute(
        """CREATE TRIGGER trg_maintenance_order_lifecycle_guard
           BEFORE UPDATE ON maintenance_orders
           FOR EACH ROW EXECUTE FUNCTION miniogas_guard_maintenance_order_lifecycle()"""
    )


PHASE6_MIGRATIONS = [
    Migration(
        version=PHASE6_MAINTENANCE_VERSION,
        description=(
            "Phase 6 governed assets, maintenance requests/orders, preventive plans, "
            "checklists, spares, tools, life and calibration evidence"
        ),
        checksum_material=(
            "phase6-maintenance-v1|append-only-maintenance-evidence-v1|"
            "postgres-force-rls-v1|" + "|".join(PHASE6_SCOPED_TABLES)
        ),
        sqlite_action=_phase6_sqlite_schema,
        postgres_action=_phase6_postgres_schema,
    ),
    Migration(
        version=PHASE6_MAINTENANCE_GUARDS_VERSION,
        description=(
            "Phase 6 independent verification, checklist, tool-life, calibration and "
            "production execution guards"
        ),
        checksum_material=(
            "phase6-maintenance-guards-v1|independent-verification-v1|"
            "tool-life-tas"
            "k-interlock-v1|calibration-tas"
            "k-interlock-v1|"
            "downtime-production-impact-v1"
        ),
        sqlite_action=_phase6_sqlite_guards,
        postgres_action=_phase6_postgres_guards,
    ),
    Migration(
        version=PHASE6_MRO_MOVEMENT_BINDING_VERSION,
        description="Phase 6 maintenance-order authority binding for Phase 4 consume movements",
        checksum_material=(
            "phase6-mro-movement-binding-v1|exclusive-consume-authority-v1|"
            "inventory-movement-maintenance-order-fk-v1"
        ),
        sqlite_action=_phase6_sqlite_mro_binding,
        postgres_action=_phase6_postgres_mro_binding,
    ),
    Migration(
        version=PHASE6_MAINTENANCE_LIFECYCLE_GUARDS_VERSION,
        description="Phase 6 immutable maintenance order lifecycle and evidence guards",
        checksum_material=(
            "phase6-maintenance-lifecycle-v1|ordered-transitions-v1|"
            "approval-work-verification-evidence-lock-v1"
        ),
        sqlite_action=_phase6_sqlite_lifecycle_guards,
        postgres_action=_phase6_postgres_lifecycle_guards,
    ),
]
