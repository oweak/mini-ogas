from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from .config import settings
from .database import get_db
from .stage_e_schema import STAGE_E_OUTBOX_ORDERING_VERSION


def utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: object) -> datetime | None:
    if value in {None, ""}:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[rank], 3)


class NATSShadowReconciler:
    """Build a read-only, PostgreSQL-backed transport reconciliation report."""

    def report(self, *, now: datetime | None = None, enabled: bool | None = None) -> dict[str, Any]:
        transport_enabled = settings.nats_enabled if enabled is None else enabled
        if not transport_enabled:
            return self._inactive_report("disabled")
        if not settings.persist_enabled:
            return self._inactive_report("unavailable", ["persistence_disabled"])

        observed_at = (now or utc_now()).astimezone(UTC)
        with get_db() as db:
            baseline_row = db.execute(
                "SELECT applied_at FROM schema_migrations WHERE version = ?",
                (STAGE_E_OUTBOX_ORDERING_VERSION,),
            ).fetchone()
            if baseline_row is None:
                return self._inactive_report("unavailable", ["stage_e_migration_missing"])
            baseline = _as_utc(
                dict(baseline_row)["applied_at"]
                if hasattr(baseline_row, "keys")
                else baseline_row[0]
            )
            assert baseline is not None
            rows = db.execute(
                """SELECT o.message_id, o.status, o.created_at, o.published_at,
                          o.attempts, r.message_id AS receipt_message_id,
                          r.message_type, r.source_node, r.run_id, r.local_sequence,
                          r.ingested_at, r.delivery_count, r.duplicate_count
                   FROM outbox_messages o
                   LEFT JOIN nats_shadow_receipts r
                     ON r.message_id = o.message_id
                    AND r.tenant_id = o.tenant_id
                    AND r.site_id = o.site_id
                   WHERE o.tenant_id = ? AND o.site_id = ? AND o.created_at >= ?
                   ORDER BY o.created_at DESC
                   LIMIT ?""",
                (
                    settings.tenant_id,
                    settings.site_id,
                    baseline.isoformat(),
                    settings.nats_reconciliation_window_messages,
                ),
            ).fetchall()
            orphan_row = db.execute(
                """SELECT COUNT(*) AS count
                   FROM nats_shadow_receipts r
                   LEFT JOIN outbox_messages o
                     ON o.message_id = r.message_id
                    AND o.tenant_id = r.tenant_id
                    AND o.site_id = r.site_id
                   WHERE r.tenant_id = ? AND r.site_id = ? AND r.ingested_at >= ?
                     AND o.message_id IS NULL""",
                (settings.tenant_id, settings.site_id, baseline.isoformat()),
            ).fetchone()

        items = [dict(row) for row in rows]
        orphan_count = int(
            dict(orphan_row)["count"] if hasattr(orphan_row, "keys") else orphan_row[0]
        )
        grace_seconds = settings.nats_reconciliation_grace_seconds
        counts = {
            "sampled_outbox": len(items),
            "published": 0,
            "matched_receipts": 0,
            "fresh_unmatched": 0,
            "stale_unmatched": 0,
            "fresh_pending": 0,
            "stale_pending": 0,
            "dead_letter": 0,
            "orphan_receipts": orphan_count,
            "deliveries": 0,
            "duplicates": 0,
        }
        latencies: list[float] = []
        ordered_receipts: list[tuple[datetime, str, str, str, int]] = []

        for item in items:
            status = str(item.get("status") or "")
            created_at = _as_utc(item.get("created_at")) or observed_at
            age_seconds = max(0.0, (observed_at - created_at).total_seconds())
            has_receipt = bool(item.get("receipt_message_id"))
            if status == "dead_letter":
                counts["dead_letter"] += 1
            elif status in {"pending", "publishing"}:
                key = "stale_pending" if age_seconds > grace_seconds else "fresh_pending"
                counts[key] += 1
            elif status == "published":
                counts["published"] += 1
                if has_receipt:
                    counts["matched_receipts"] += 1
                else:
                    key = "stale_unmatched" if age_seconds > grace_seconds else "fresh_unmatched"
                    counts[key] += 1

            if not has_receipt:
                continue
            deliveries = max(1, int(item.get("delivery_count") or 1))
            duplicates = max(0, int(item.get("duplicate_count") or 0))
            counts["deliveries"] += deliveries
            counts["duplicates"] += duplicates
            ingested_at = _as_utc(item.get("ingested_at"))
            if ingested_at is not None:
                latency_ms = max(0.0, (ingested_at - created_at).total_seconds() * 1000)
                latencies.append(latency_ms)
                ordered_receipts.append(
                    (
                        ingested_at,
                        str(item.get("message_type") or ""),
                        str(item.get("source_node") or ""),
                        str(item.get("run_id") or ""),
                        int(item.get("local_sequence") or 0),
                    )
                )

        eligible = counts["matched_receipts"] + counts["stale_unmatched"]
        receive_rate = counts["matched_receipts"] / eligible if eligible else 1.0
        duplicate_rate = (
            counts["duplicates"] / counts["deliveries"] if counts["deliveries"] else 0.0
        )
        comparisons, divergences = self._order_differences(ordered_receipts)
        divergence_rate = divergences / comparisons if comparisons else 0.0
        p95_latency = _percentile(latencies, 0.95)

        violations: list[str] = []
        if counts["stale_pending"]:
            violations.append("stale_outbox_pending")
        if counts["stale_unmatched"]:
            violations.append("published_without_receipt")
        if counts["dead_letter"]:
            violations.append("dead_letter_present")
        if orphan_count:
            violations.append("receipt_without_outbox")
        enough_samples = eligible >= settings.nats_reconciliation_min_samples
        if enough_samples and receive_rate < settings.nats_min_receive_rate:
            violations.append("receive_rate_below_threshold")
        if enough_samples and duplicate_rate > settings.nats_max_duplicate_rate:
            violations.append("duplicate_rate_above_threshold")
        if enough_samples and p95_latency > settings.nats_max_p95_latency_ms:
            violations.append("latency_above_threshold")
        if divergences:
            violations.append("order_divergence_detected")

        catching_up = bool(counts["fresh_pending"] or counts["fresh_unmatched"])
        postgresql_reconciled = not counts["stale_unmatched"] and not orphan_count
        if violations:
            status = "degraded"
        elif catching_up:
            status = "catching_up"
        elif enough_samples:
            status = "ready"
        else:
            status = "observing"

        return {
            "status": status,
            "mode": "shadow",
            "authority": "rest-postgresql",
            "observed_at": observed_at.isoformat(),
            "baseline_at": baseline.isoformat(),
            "window_limit": settings.nats_reconciliation_window_messages,
            "minimum_samples": settings.nats_reconciliation_min_samples,
            "counts": counts,
            "rates": {
                "receive_rate": round(receive_rate, 6),
                "duplicate_rate": round(duplicate_rate, 6),
            },
            "latency_ms": {
                "sample_size": len(latencies),
                "p50": _percentile(latencies, 0.50),
                "p95": p95_latency,
                "max": round(max(latencies), 3) if latencies else 0.0,
            },
            "ordering": {
                "comparisons": comparisons,
                "divergences": divergences,
                "divergence_rate": round(divergence_rate, 6),
            },
            "postgresql_reconciliation": {
                "status": "matched" if postgresql_reconciled else "mismatch",
                "matched": counts["matched_receipts"],
                "missing_after_grace": counts["stale_unmatched"],
                "orphan_receipts": orphan_count,
            },
            "thresholds": {
                "grace_seconds": grace_seconds,
                "minimum_receive_rate": settings.nats_min_receive_rate,
                "maximum_duplicate_rate": settings.nats_max_duplicate_rate,
                "maximum_p95_latency_ms": settings.nats_max_p95_latency_ms,
                "maximum_order_divergences": 0,
            },
            "thresholds_met": enough_samples and not violations and not catching_up,
            "cutover_eligible": False,
            "promotion_gate": "manual-stage-gate-required",
            "violations": violations,
        }

    @staticmethod
    def _order_differences(
        receipts: list[tuple[datetime, str, str, str, int]],
    ) -> tuple[int, int]:
        previous: dict[tuple[str, str, str], int] = {}
        comparisons = 0
        divergences = 0
        for _, message_type, source_node, run_id, sequence in sorted(receipts):
            key = (message_type, source_node, run_id)
            if key in previous:
                comparisons += 1
                if sequence < previous[key]:
                    divergences += 1
            previous[key] = sequence
        return comparisons, divergences

    @staticmethod
    def _inactive_report(status: str, violations: list[str] | None = None) -> dict[str, Any]:
        return {
            "status": status,
            "mode": "shadow",
            "authority": "rest-postgresql",
            "thresholds_met": False,
            "cutover_eligible": False,
            "promotion_gate": "manual-stage-gate-required",
            "violations": violations or [],
        }


nats_shadow_reconciler = NATSShadowReconciler()
