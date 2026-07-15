# Phase 7 Baseline Audit

## Audit Status

`BASELINE COMPLETE - IMPLEMENTATION GATE NOT MET - 2026-07-14`

This audit evaluates the real repository and the running local digital-twin
environment before Phase 7 implementation. It does not treat a Compose service
declaration, a topology label, a legacy metrics endpoint, an in-process cache, or a
Dashboard source string as a data platform.

The current working tree is pre-existing and dirty. The verified Phase 6 baseline
passes the unified engineering gate, but Phase 7 has not passed any of its four
formal gates.

## Required Phase 7 Scope

The engineering master prompt requires:

- Historian ADR and proof of concept;
- a governed Telemetry Schema and ingest path;
- retention and aggregation;
- a Redis current-state projection and deterministic rebuild;
- object storage for controlled documents/evidence;
- visible data-quality state;
- source and freshness in the Dashboard.

Its formal gates are:

1. high-frequency telemetry does not pollute business tables;
2. Redis can be rebuilt;
3. documents have a checksum;
4. data quality is visible.

## Repository Evidence

### Runtime Dependencies

- `services/central-api/requirements.txt` contains FastAPI, Uvicorn, SimPy,
  Psycopg, and NATS only. It contains no Redis, TimescaleDB, InfluxDB, ClickHouse,
  MinIO, S3, or object-storage client.
- `deploy/docker-compose.central.yml` declares a plain `redis:7-alpine` service,
  but Central API has no Redis client or projection implementation. The same file
  uses plain `postgres:16-alpine`, not a TimescaleDB image.
- `store.py` exposes Redis only as a `planned` topology edge.
- No Historian, telemetry, Redis projection, projection checkpoint, object manifest,
  or object-storage module exists in the application.

### Existing Ingest Is A Compatibility Path

`NodeHeartbeatV2In` accepts untyped `dict[str, Any]` sections for `metrics`,
`production`, `sync`, and `runtime`. It does not define measurement identity, unit,
quality code, mapping version, source sequence, correction state, or typed value.

`MemoryStore.record_node_heartbeat_v2()` currently:

1. writes the complete mixed heartbeat to PostgreSQL `heartbeat_shadow`;
2. converts heartbeat host values and simulated production quantities into
   `MetricIn`;
3. writes those rows to the central `metrics` table;
4. mutates the in-process machine/current-state cache;
5. invokes the legacy heartbeat-driven part-flow adapter;
6. evaluates alarms and command effects on the same payload path.

This path is useful compatibility evidence, but it is not a governed high-frequency
telemetry pipeline. It mixes host metrics, simulation runtime, production context,
alarm input, and current-state projection in one envelope.

### Storage And Retention

- `metrics` is a public PostgreSQL table alongside business and audit tables. Its
  columns are only node, CPU, memory, disk, network, latency, creation time, and
  tenant/site. It has no measurement timestamp, unit, quality, source sequence, or
  mapping version.
- `heartbeat_shadow` stores each entire heartbeat as JSON. Retention is a per-node
  row cap (`HEARTBEAT_SHADOW_RETENTION_PER_NODE`, default 2,000), not a documented
  time-tier policy.
- The row-cap deletion runs inline with ingest. There is no aggregation table,
  continuous aggregate, compression policy, late-data policy, retention worker, or
  restore/replay gate for telemetry.
- `event_store` and NATS receipts are transport/domain compatibility records. They
  are not a Historian and do not provide measurement-window queries.

### Redis Projection And Rebuild

- There is no Redis connection setting in Central API configuration, no Redis
  package, no key schema, no checkpoint, no consumer, no rebuild command, and no
  projection comparison test.
- Dashboard snapshots are rebuilt ad hoc from `MemoryStore` plus PostgreSQL refresh
  code, not from Redis.
- Therefore the declared Compose Redis container is currently unused infrastructure,
  not an implemented read model.

### Controlled Documents And Objects

Phase 2 provides governed document identity and immutable inline revisions, but
`DocumentRevisionIn` contains only `revision` and an inline text `content` field.
`document_revisions` contains `content_json` and lifecycle evidence only. It has no:

- object key or immutable object version;
- SHA-256/content checksum;
- media type or byte length;
- storage provider/bucket;
- upload/finalization record;
- integrity verification result.

No MinIO/S3 service, filesystem object adapter, object manifest, or retrieval
integrity check exists. Phase 2 revision immutability does not satisfy the Phase 7
document-checksum gate.

### Data Quality And Presentation

The latest persisted production-node heartbeat contains `metrics`, `production`,
`runtime`, and `sync` sections, but no `quality_code` or `mapping_version`. The
current sample exposes a producer timestamp and central receive time only as fields
of the mixed heartbeat, not as governed measurement-time semantics.

The Dashboard exposes global/run `data_source`, snapshot `generated_at`, and node
`last_heartbeat`. It does not expose per-signal:

- quality code and reason;
- source timestamp versus ingest/processed time;
- freshness age and threshold;
- unit and mapping version;
- duplicate, missing, late, out-of-order, drift, or range status;
- projection source, checkpoint, or lag.

No telemetry/data-quality API exists in generated OpenAPI.

## Live Runtime Evidence

The running environment was queried on 2026-07-14 after the Phase 6 unified gate:

| Check | Observed result |
|---|---|
| PostgreSQL `5432` | Listening |
| NATS `4222` | Listening |
| Central API `8080` | Listening |
| Dashboard `5173` | Listening |
| Redis `6379` | Not listening |
| Redis server/client command | Not installed on host PATH |
| Docker command | Not installed on host PATH |
| PostgreSQL extensions | `plpgsql` only; no TimescaleDB |
| Phase 7-named PostgreSQL relations | None |
| Scoped `metrics` rows | 52,179 |
| Scoped `heartbeat_shadow` rows | 6,051 |
| Scoped `event_store` rows | 2,062 |
| Scoped controlled document revisions | 18 |
| Production-node heartbeat retention | 2,000 rows per turning/milling/grinding node |
| Oldest retained metric | 2026-06-22 09:04:29 +08:00 |
| Latest metric during audit | 2026-07-14 06:27:27 +08:00 |

Forced RLS initially returned zero rows until the audited tenant/site session scope
was set. The scoped counts above were obtained through the non-superuser runtime role;
no BYPASSRLS or superuser shortcut was used.

The generated OpenAPI contains legacy `/metrics`, `/metrics/history`,
`/metrics/latest`, heartbeat endpoints, and Phase 2 document routes. It contains no
telemetry, Historian, data-quality, object, projection, or rebuild route.

## Gate Matrix

| Formal gate | Current evidence | Result |
|---|---|---|
| High-frequency telemetry does not pollute business tables | Mixed heartbeats and 52,179 metrics rows are stored in the central public business database; there is no separate telemetry schema/store or typed measurement contract | FAIL |
| Redis can be rebuilt | Redis is not running and application code has no Redis projection, checkpoint, source manifest, or rebuild/compare operation | FAIL |
| Documents have checksum | 18 governed revisions exist, but schema and API have no checksum or object metadata and no object store exists | FAIL |
| Data quality is visible | Persisted samples lack quality/mapping fields; API/UI have no quality summary or per-value freshness/quality semantics | FAIL |

## Implementation Item Matrix

| Required item | Baseline | Assessment |
|---|---|---|
| Historian ADR and PoC | No ADR, extension, service, load evidence, or query contract | NOT STARTED |
| Telemetry Schema | Mixed untyped heartbeat dictionaries only | NOT STARTED |
| Telemetry Ingest | Legacy metrics/heartbeat compatibility endpoints | NOT ACCEPTABLE AS PHASE 7 |
| Retention/Aggregation | Heartbeat latest-2,000 row deletion only | PARTIAL LEGACY MECHANISM |
| Redis Projection | Compose declaration only | NOT STARTED |
| Rebuild | PostgreSQL-to-MemoryStore refresh, not Redis deterministic rebuild | NOT STARTED |
| Object Storage | No service or adapter | NOT STARTED |
| Data Quality | No governed signal-quality model or rules | NOT STARTED |
| Dashboard Source/Freshness | Global source and node timestamps only | PARTIAL PRESENTATION |

## Risks Found During Baseline

1. **Telemetry/business coupling:** a future higher sample rate would expand the
   central `metrics` table without a time retention contract and can increase load on
   the same PostgreSQL instance that owns orders, material, quality, and maintenance.
2. **Semantic coupling:** heartbeat values can mutate legacy current state and part
   flow. A sensor sample must not become an accepted business fact without an
   interpreter and governed production context.
3. **Quality blindness:** range-valid JSON can still be stale, duplicated,
   out-of-order, incorrectly mapped, uncalibrated, or expressed in the wrong unit.
4. **Projection ambiguity:** MemoryStore is a mutable read cache without a durable
   checkpoint; restart reconstruction is not equivalent to a deterministic projection
   rebuild and comparison.
5. **Document integrity gap:** revision immutability protects database text from
   update but cannot prove that a retrieved external file is the approved bytes.
6. **Deployment overstatement:** Redis in Compose can be mistaken for implemented
   capability even though no running process or application connection exists.

## Required Decisions Before Implementation

Phase 7 must record ADRs before adding runtime dependencies:

- Historian PoC choice and isolation boundary. TimescaleDB must be evaluated against
  current native PostgreSQL/Windows constraints and real measured write/query load;
  plain PostgreSQL may only be accepted as a bounded PoC with an explicit upgrade
  threshold and separate telemetry schema/database boundary.
- Redis-compatible runtime choice on Windows, key/TTL schema, source authority,
  checkpoint semantics, atomic rebuild/swap, and PostgreSQL-only fallback.
- Object-storage provider and content-addressed checksum lifecycle, including failed
  upload/finalization and retrieval-integrity behavior.
- Telemetry identity, units, quality codes, all required timestamps, duplicate and
  out-of-order policy, correction policy, and retention tiers.

## Phase Boundary

Phase 7 implementation may now begin from this failed baseline. No Phase 8 connector
claim is permitted: all initial telemetry must remain explicitly simulated or
engineering-generated until a governed read-only industrial connector passes the
later Phase 8 gate.
