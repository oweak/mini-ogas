from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from .config import settings
from .database import get_db
from .nats_contracts import TransportEnvelope, subject_for_envelope


def utc_now() -> datetime:
    return datetime.now(UTC)


class OutboxRepository:
    """Durable at-least-once transport queue scoped to one tenant/site."""

    def enqueue_in_transaction(self, db: Any, envelope: TransportEnvelope) -> bool:
        subject = subject_for_envelope(envelope)
        payload = json.dumps(
            envelope.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        cursor = db.execute(
            """INSERT INTO outbox_messages (
                   message_id, tenant_id, site_id, aggregate_type, aggregate_id,
                   message_type, subject, schema_version, payload_json, status,
                   available_at, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
               ON CONFLICT(message_id) DO NOTHING""",
            (
                envelope.message_id,
                settings.tenant_id,
                settings.site_id,
                envelope.message_type,
                envelope.node_code,
                envelope.message_type,
                subject,
                envelope.schema_version,
                payload,
                utc_now().isoformat(),
                utc_now().isoformat(),
            ),
        )
        return int(getattr(cursor, "rowcount", 0) or 0) == 1

    def claim_pending(self, *, limit: int = 50, lease_seconds: int = 30) -> list[dict[str, Any]]:
        now = utc_now()
        stale_before = (now - timedelta(seconds=max(1, lease_seconds))).isoformat()
        claim_token = str(uuid.uuid4())
        claimed: list[dict[str, Any]] = []
        with get_db() as db:
            db.execute(
                """UPDATE outbox_messages
                   SET status='pending', claim_token='', claimed_at=NULL
                   WHERE tenant_id=? AND site_id=? AND status='publishing'
                     AND claimed_at IS NOT NULL AND claimed_at < ?""",
                (settings.tenant_id, settings.site_id, stale_before),
            )
            rows = db.execute(
                """SELECT candidate.message_id, candidate.payload_json, candidate.attempts
                   FROM outbox_messages candidate
                   WHERE candidate.tenant_id=? AND candidate.site_id=?
                     AND candidate.status='pending' AND candidate.available_at <= ?
                     AND NOT EXISTS (
                         SELECT 1
                         FROM outbox_messages predecessor
                         WHERE predecessor.tenant_id = candidate.tenant_id
                           AND predecessor.site_id = candidate.site_id
                           AND predecessor.aggregate_type = candidate.aggregate_type
                           AND predecessor.aggregate_id = candidate.aggregate_id
                           AND predecessor.status IN ('pending', 'publishing')
                           AND (
                               predecessor.created_at < candidate.created_at
                               OR (
                                   predecessor.created_at = candidate.created_at
                                   AND predecessor.message_id < candidate.message_id
                               )
                           )
                     )
                   ORDER BY candidate.created_at ASC, candidate.message_id ASC
                   LIMIT ?""",
                (settings.tenant_id, settings.site_id, now.isoformat(), max(1, limit)),
            ).fetchall()
            for row in rows:
                data = dict(row)
                cursor = db.execute(
                    """UPDATE outbox_messages
                       SET status='publishing', attempts=attempts+1, claimed_at=?, claim_token=?
                       WHERE message_id=? AND tenant_id=? AND site_id=? AND status='pending'""",
                    (
                        now.isoformat(),
                        claim_token,
                        str(data["message_id"]),
                        settings.tenant_id,
                        settings.site_id,
                    ),
                )
                if int(getattr(cursor, "rowcount", 0) or 0) != 1:
                    continue
                claimed.append(
                    {
                        "message_id": str(data["message_id"]),
                        "payload": json.loads(str(data["payload_json"])),
                        "attempts": int(data.get("attempts") or 0) + 1,
                        "claim_token": claim_token,
                    }
                )
        return claimed

    def mark_published(self, message_id: str) -> bool:
        with get_db() as db:
            cursor = db.execute(
                """UPDATE outbox_messages
                   SET status='published', published_at=?, claim_token='', last_error=''
                   WHERE message_id=? AND tenant_id=? AND site_id=? AND status!='published'""",
                (utc_now().isoformat(), message_id, settings.tenant_id, settings.site_id),
            )
            return int(getattr(cursor, "rowcount", 0) or 0) == 1

    def mark_failed(self, message_id: str, error: str, attempts: int = 1) -> bool:
        retry_seconds = min(60, max(1, 2 ** min(max(attempts, 1), 6)))
        available_at = utc_now() + timedelta(seconds=retry_seconds)
        with get_db() as db:
            cursor = db.execute(
                """UPDATE outbox_messages
                   SET status='pending', available_at=?, claim_token='', claimed_at=NULL,
                       last_error=?
                   WHERE message_id=? AND tenant_id=? AND site_id=? AND status!='published'""",
                (
                    available_at.isoformat(),
                    error[:1024],
                    message_id,
                    settings.tenant_id,
                    settings.site_id,
                ),
            )
            return int(getattr(cursor, "rowcount", 0) or 0) == 1

    def mark_dead_letter(self, message_id: str, error: str) -> bool:
        with get_db() as db:
            cursor = db.execute(
                """UPDATE outbox_messages
                   SET status='dead_letter', claim_token='', claimed_at=NULL, last_error=?
                   WHERE message_id=? AND tenant_id=? AND site_id=? AND status!='published'""",
                (error[:1024], message_id, settings.tenant_id, settings.site_id),
            )
            return int(getattr(cursor, "rowcount", 0) or 0) == 1

    def status(self) -> dict[str, object]:
        with get_db() as db:
            rows = db.execute(
                """SELECT status, COUNT(*) AS count
                   FROM outbox_messages
                   WHERE tenant_id=? AND site_id=?
                   GROUP BY status""",
                (settings.tenant_id, settings.site_id),
            ).fetchall()
        counts = {str(dict(row)["status"]): int(dict(row)["count"]) for row in rows}
        return {
            "tenant_id": settings.tenant_id,
            "site_id": settings.site_id,
            "counts": counts,
            "pending": counts.get("pending", 0) + counts.get("publishing", 0),
        }


outbox_repository = OutboxRepository()
