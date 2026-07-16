from __future__ import annotations

from typing import Any

from .migrations import Migration

STAGE_E_SHADOW_METRICS_VERSION = "2026.07.16-stage-e-shadow-metrics"
STAGE_E_OUTBOX_ORDERING_VERSION = "2026.07.16-stage-e-outbox-stream-ordering"


def _sqlite_shadow_metrics(connection: Any) -> None:
    columns = {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(nats_shadow_receipts)").fetchall()
    }
    additions = {
        "delivery_count": "INTEGER NOT NULL DEFAULT 1",
        "duplicate_count": "INTEGER NOT NULL DEFAULT 0",
        "last_ingested_at": "TEXT",
    }
    for name, definition in additions.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE nats_shadow_receipts ADD COLUMN {name} {definition}")
    connection.execute(
        """UPDATE nats_shadow_receipts
           SET last_ingested_at = ingested_at
           WHERE last_ingested_at IS NULL OR last_ingested_at = ''"""
    )
    connection.execute(
        """CREATE INDEX IF NOT EXISTS idx_nats_shadow_scope_ingested
           ON nats_shadow_receipts(tenant_id, site_id, ingested_at)"""
    )


def _postgres_shadow_metrics(connection: Any) -> None:
    connection.execute(
        """ALTER TABLE nats_shadow_receipts
           ADD COLUMN IF NOT EXISTS delivery_count BIGINT NOT NULL DEFAULT 1"""
    )
    connection.execute(
        """ALTER TABLE nats_shadow_receipts
           ADD COLUMN IF NOT EXISTS duplicate_count BIGINT NOT NULL DEFAULT 0"""
    )
    connection.execute(
        """ALTER TABLE nats_shadow_receipts
           ADD COLUMN IF NOT EXISTS last_ingested_at TIMESTAMPTZ"""
    )
    connection.execute(
        """UPDATE nats_shadow_receipts
           SET last_ingested_at = ingested_at
           WHERE last_ingested_at IS NULL"""
    )
    connection.execute(
        """CREATE INDEX IF NOT EXISTS idx_nats_shadow_scope_ingested
           ON nats_shadow_receipts(tenant_id, site_id, ingested_at)"""
    )


def _outbox_stream_ordering(connection: Any) -> None:
    connection.execute(
        """CREATE INDEX IF NOT EXISTS idx_outbox_stream_order
           ON outbox_messages(
               tenant_id, site_id, aggregate_type, aggregate_id,
               status, created_at, message_id
           )"""
    )


STAGE_E_MIGRATIONS = [
    Migration(
        version=STAGE_E_SHADOW_METRICS_VERSION,
        description="Durable NATS Shadow delivery and duplicate counters",
        checksum_material=(
            "nats-shadow-receipts-v2:delivery-count:duplicate-count:"
            "last-ingested-at:scope-ingested-index"
        ),
        sqlite_action=_sqlite_shadow_metrics,
        postgres_action=_postgres_shadow_metrics,
    ),
    Migration(
        version=STAGE_E_OUTBOX_ORDERING_VERSION,
        description="Preserve per-aggregate Outbox order across transport retries",
        checksum_material=(
            "outbox-stream-order-v1:tenant:site:aggregate-type:aggregate-id:"
            "status:created-at:message-id"
        ),
        sqlite_action=_outbox_stream_ordering,
        postgres_action=_outbox_stream_ordering,
    ),
]
