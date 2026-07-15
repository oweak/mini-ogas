from __future__ import annotations

from typing import Any

from .migrations import Migration

PHASE2_MASTER_DATA_MIGRATION_VERSION = "2026.07.14-phase2-master-data"
PHASE2_REVISION_DELETE_GUARD_VERSION = "2026.07.14-phase2-revision-delete-guard"

PHASE2_SCOPED_TABLES = (
    "organization_units",
    "uoms",
    "materials",
    "products",
    "equipment",
    "equipment_capabilities",
    "skills",
    "personnel",
    "personnel_qualifications",
    "calendars",
    "calendar_shifts",
    "controlled_documents",
    "document_revisions",
    "boms",
    "bom_revisions",
    "routings",
    "routing_revisions",
    "work_orders",
)


SQLITE_TABLES = (
    """CREATE TABLE IF NOT EXISTS organization_units (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           unit_code TEXT NOT NULL,
           name TEXT NOT NULL,
           unit_type TEXT NOT NULL CHECK (unit_type IN ('enterprise','site','area','line','cell')),
           parent_id INTEGER REFERENCES organization_units(id),
           active INTEGER NOT NULL DEFAULT 1,
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, unit_code)
       )""",
    """CREATE TABLE IF NOT EXISTS uoms (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           uom_code TEXT NOT NULL,
           name TEXT NOT NULL,
           dimension TEXT NOT NULL,
           scale REAL NOT NULL CHECK (scale > 0),
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, uom_code)
       )""",
    """CREATE TABLE IF NOT EXISTS materials (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           material_code TEXT NOT NULL,
           name TEXT NOT NULL,
           material_type TEXT NOT NULL,
           base_uom_id INTEGER NOT NULL REFERENCES uoms(id),
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, material_code)
       )""",
    """CREATE TABLE IF NOT EXISTS products (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           product_code TEXT NOT NULL,
           name TEXT NOT NULL,
           material_id INTEGER NOT NULL REFERENCES materials(id),
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, product_code)
       )""",
    """CREATE TABLE IF NOT EXISTS equipment (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           equipment_code TEXT NOT NULL,
           name TEXT NOT NULL,
           equipment_type TEXT NOT NULL,
           organization_unit_id INTEGER NOT NULL REFERENCES organization_units(id),
           active INTEGER NOT NULL DEFAULT 1,
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, equipment_code)
       )""",
    """CREATE TABLE IF NOT EXISTS equipment_capabilities (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           equipment_id INTEGER NOT NULL REFERENCES equipment(id),
           capability_code TEXT NOT NULL,
           name TEXT NOT NULL,
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, equipment_id, capability_code)
       )""",
    """CREATE TABLE IF NOT EXISTS skills (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           skill_code TEXT NOT NULL,
           name TEXT NOT NULL,
           level_min INTEGER NOT NULL CHECK (level_min >= 1),
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, skill_code)
       )""",
    """CREATE TABLE IF NOT EXISTS personnel (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           personnel_code TEXT NOT NULL,
           display_name TEXT NOT NULL,
           linked_username TEXT REFERENCES users(username),
           active INTEGER NOT NULL DEFAULT 1,
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, personnel_code),
           UNIQUE (tenant_id, site_id, linked_username)
       )""",
    """CREATE TABLE IF NOT EXISTS personnel_qualifications (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           personnel_id INTEGER NOT NULL REFERENCES personnel(id),
           skill_id INTEGER NOT NULL REFERENCES skills(id),
           level INTEGER NOT NULL CHECK (level >= 1),
           valid_from TEXT NOT NULL,
           valid_to TEXT NOT NULL,
           evidence_reference TEXT NOT NULL,
           issued_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, personnel_id, skill_id, valid_from)
       )""",
    """CREATE TABLE IF NOT EXISTS calendars (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           calendar_code TEXT NOT NULL,
           name TEXT NOT NULL,
           timezone TEXT NOT NULL,
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, calendar_code)
       )""",
    """CREATE TABLE IF NOT EXISTS calendar_shifts (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           calendar_id INTEGER NOT NULL REFERENCES calendars(id),
           shift_code TEXT NOT NULL,
           name TEXT NOT NULL,
           start_time TEXT NOT NULL,
           end_time TEXT NOT NULL,
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, calendar_id, shift_code)
       )""",
    """CREATE TABLE IF NOT EXISTS controlled_documents (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           document_code TEXT NOT NULL,
           title TEXT NOT NULL,
           document_type TEXT NOT NULL,
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, document_code)
       )""",
    """CREATE TABLE IF NOT EXISTS document_revisions (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           document_id INTEGER NOT NULL REFERENCES controlled_documents(id),
           revision TEXT NOT NULL,
           content_json TEXT NOT NULL,
           status TEXT NOT NULL DEFAULT 'draft'
               CHECK (status IN ('draft','approved','effective','superseded')),
           created_by TEXT NOT NULL,
           approved_by TEXT,
           approved_at TEXT,
           effective_by TEXT,
           effective_at TEXT,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, document_id, revision)
       )""",
    """CREATE TABLE IF NOT EXISTS boms (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           bom_code TEXT NOT NULL,
           product_id INTEGER NOT NULL REFERENCES products(id),
           name TEXT NOT NULL,
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, bom_code)
       )""",
    """CREATE TABLE IF NOT EXISTS bom_revisions (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           bom_id INTEGER NOT NULL REFERENCES boms(id),
           revision INTEGER NOT NULL CHECK (revision >= 1),
           content_json TEXT NOT NULL,
           status TEXT NOT NULL DEFAULT 'draft'
               CHECK (status IN ('draft','approved','effective','superseded')),
           created_by TEXT NOT NULL,
           approved_by TEXT,
           approved_at TEXT,
           effective_by TEXT,
           effective_at TEXT,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, bom_id, revision)
       )""",
    """CREATE TABLE IF NOT EXISTS routings (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           routing_code TEXT NOT NULL,
           product_id INTEGER NOT NULL REFERENCES products(id),
           name TEXT NOT NULL,
           created_by TEXT NOT NULL,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, routing_code)
       )""",
    """CREATE TABLE IF NOT EXISTS routing_revisions (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           routing_id INTEGER NOT NULL REFERENCES routings(id),
           revision INTEGER NOT NULL CHECK (revision >= 1),
           content_json TEXT NOT NULL,
           status TEXT NOT NULL DEFAULT 'draft'
               CHECK (status IN ('draft','approved','effective','superseded')),
           created_by TEXT NOT NULL,
           approved_by TEXT,
           approved_at TEXT,
           effective_by TEXT,
           effective_at TEXT,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, routing_id, revision)
       )""",
    """CREATE TABLE IF NOT EXISTS work_orders (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           tenant_id TEXT NOT NULL,
           site_id TEXT NOT NULL,
           work_order_code TEXT NOT NULL,
           product_id INTEGER NOT NULL REFERENCES products(id),
           quantity REAL NOT NULL CHECK (quantity > 0),
           bom_revision_id INTEGER NOT NULL REFERENCES bom_revisions(id),
           routing_revision_id INTEGER NOT NULL REFERENCES routing_revisions(id),
           document_revision_ids_json TEXT NOT NULL,
           calendar_id INTEGER NOT NULL REFERENCES calendars(id),
           shift_id INTEGER NOT NULL REFERENCES calendar_shifts(id),
           operation_assignments_json TEXT NOT NULL,
           status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','released','cancelled')),
           created_by TEXT NOT NULL,
           released_by TEXT,
           released_at TEXT,
           created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
           UNIQUE (tenant_id, site_id, work_order_code)
       )""",
)


POSTGRES_TABLES = tuple(
    statement
    .replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
    .replace(" INTEGER REFERENCES", " BIGINT REFERENCES")
    .replace(" INTEGER NOT NULL REFERENCES", " BIGINT NOT NULL REFERENCES")
    .replace("active INTEGER NOT NULL DEFAULT 1", "active BOOLEAN NOT NULL DEFAULT true")
    .replace("created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP", "created_at TIMESTAMPTZ NOT NULL DEFAULT now()")
    .replace("approved_at TEXT", "approved_at TIMESTAMPTZ")
    .replace("effective_at TEXT", "effective_at TIMESTAMPTZ")
    .replace("released_at TEXT", "released_at TIMESTAMPTZ")
    for statement in SQLITE_TABLES
)


def _create_tables(connection: Any, statements: tuple[str, ...]) -> None:
    for statement in statements:
        connection.execute(statement)


def _create_indexes(connection: Any) -> None:
    for table_name in PHASE2_SCOPED_TABLES:
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_scope "
            f"ON {table_name}(tenant_id, site_id)"
        )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_qualifications_validity "
        "ON personnel_qualifications(tenant_id, site_id, personnel_id, skill_id, valid_to)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_work_orders_status "
        "ON work_orders(tenant_id, site_id, status, created_at)"
    )
    for table_name, parent_column in (
        ("document_revisions", "document_id"),
        ("bom_revisions", "bom_id"),
        ("routing_revisions", "routing_id"),
    ):
        connection.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS uq_{table_name}_effective "
            f"ON {table_name}(tenant_id, site_id, {parent_column}) "
            "WHERE status='effective'"
        )


def _phase2_sqlite_master_data(connection: Any) -> None:
    _create_tables(connection, SQLITE_TABLES)
    _create_indexes(connection)
    immutable = (
        ("document_revisions", "document_id"),
        ("bom_revisions", "bom_id"),
        ("routing_revisions", "routing_id"),
    )
    for table_name, parent_column in immutable:
        connection.execute(
            f"""CREATE TRIGGER IF NOT EXISTS trg_{table_name}_immutable
                BEFORE UPDATE OF {parent_column}, revision, content_json ON {table_name}
                FOR EACH ROW
                WHEN OLD.{parent_column} != NEW.{parent_column}
                  OR OLD.revision != NEW.revision
                  OR OLD.content_json != NEW.content_json
                BEGIN
                    SELECT RAISE(ABORT, 'published revision identity and content are immutable');
                END"""
        )


def _phase2_postgres_master_data(connection: Any) -> None:
    _create_tables(connection, POSTGRES_TABLES)
    _create_indexes(connection)
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_reject_revision_rewrite()
           RETURNS trigger AS $$
           BEGIN
               IF TG_TABLE_NAME = 'document_revisions' THEN
                   IF OLD.document_id IS DISTINCT FROM NEW.document_id
                      OR OLD.revision IS DISTINCT FROM NEW.revision
                      OR OLD.content_json IS DISTINCT FROM NEW.content_json THEN
                       RAISE EXCEPTION 'published revision identity and content are immutable';
                   END IF;
               ELSIF TG_TABLE_NAME = 'bom_revisions' THEN
                   IF OLD.bom_id IS DISTINCT FROM NEW.bom_id
                      OR OLD.revision IS DISTINCT FROM NEW.revision
                      OR OLD.content_json IS DISTINCT FROM NEW.content_json THEN
                       RAISE EXCEPTION 'published revision identity and content are immutable';
                   END IF;
               ELSIF TG_TABLE_NAME = 'routing_revisions' THEN
                   IF OLD.routing_id IS DISTINCT FROM NEW.routing_id
                      OR OLD.revision IS DISTINCT FROM NEW.revision
                      OR OLD.content_json IS DISTINCT FROM NEW.content_json THEN
                       RAISE EXCEPTION 'published revision identity and content are immutable';
                   END IF;
               END IF;
               RETURN NEW;
           END;
           $$ LANGUAGE plpgsql"""
    )
    for table_name in ("document_revisions", "bom_revisions", "routing_revisions"):
        connection.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_immutable ON {table_name}")
        connection.execute(
            f"""CREATE TRIGGER trg_{table_name}_immutable
                BEFORE UPDATE ON {table_name}
                FOR EACH ROW EXECUTE FUNCTION miniogas_reject_revision_rewrite()"""
        )
    for table_name in PHASE2_SCOPED_TABLES:
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


def _phase2_sqlite_revision_delete_guard(connection: Any) -> None:
    for table_name in ("document_revisions", "bom_revisions", "routing_revisions"):
        connection.execute(
            f"""CREATE TRIGGER IF NOT EXISTS trg_{table_name}_delete_guard
                BEFORE DELETE ON {table_name}
                FOR EACH ROW
                BEGIN
                    SELECT RAISE(ABORT, 'controlled revision history cannot be deleted');
                END"""
        )


def _phase2_postgres_revision_delete_guard(connection: Any) -> None:
    connection.execute(
        """CREATE OR REPLACE FUNCTION miniogas_reject_revision_delete()
           RETURNS trigger AS $$
           BEGIN
               RAISE EXCEPTION 'controlled revision history cannot be deleted';
           END;
           $$ LANGUAGE plpgsql"""
    )
    for table_name in ("document_revisions", "bom_revisions", "routing_revisions"):
        connection.execute(
            f"DROP TRIGGER IF EXISTS trg_{table_name}_delete_guard ON {table_name}"
        )
        connection.execute(
            f"""CREATE TRIGGER trg_{table_name}_delete_guard
                BEFORE DELETE ON {table_name}
                FOR EACH ROW EXECUTE FUNCTION miniogas_reject_revision_delete()"""
        )


PHASE2_MIGRATIONS = [
    Migration(
        version=PHASE2_MASTER_DATA_MIGRATION_VERSION,
        description=(
            "Phase 2 scoped organization, resource qualification, versioned master data, "
            "and bound work-order release"
        ),
        checksum_material=(
            "phase2-master-data-v1|immutable-revisions-v1|single-effective-revision-v1|"
            "postgres-force-rls-v1|"
            + "|".join(PHASE2_SCOPED_TABLES)
        ),
        sqlite_action=_phase2_sqlite_master_data,
        postgres_action=_phase2_postgres_master_data,
    ),
    Migration(
        version=PHASE2_REVISION_DELETE_GUARD_VERSION,
        description="Phase 2 controlled revision deletion guard",
        checksum_material=(
            "phase2-revision-delete-guard-v1|document_revisions|bom_revisions|"
            "routing_revisions"
        ),
        sqlite_action=_phase2_sqlite_revision_delete_guard,
        postgres_action=_phase2_postgres_revision_delete_guard,
    ),
]
