# ADR-0007: Phase 7 Data Platform Boundaries

- Status: Accepted for local engineering implementation
- Date: 2026-07-14
- Decision owners: Mini-OGAS platform and data governance
- Supersedes: no prior Phase 7 decision

## Context

Phase 7 must separate business transactions, high-frequency telemetry, current-state
projections, and document bytes. The audited host runs native PostgreSQL 16 and NATS
on Windows. It has no TimescaleDB extension, Redis runtime, Docker, WSL distribution,
or object store. The Central API currently stores mixed heartbeat JSON and host
metrics in public PostgreSQL tables and maintains current state in `MemoryStore`.

The phase gate requires real storage behavior. An in-memory dictionary, an unused
Compose declaration, or a page populated from fixtures cannot satisfy it.

## Decision

### Telemetry Authority And Historian PoC

PostgreSQL remains the only accepted business transaction authority. Phase 7 adds a
dedicated `telemetry` schema as a bounded Historian proof of concept:

- typed signal definitions and data-quality policy;
- idempotent ingest-batch and sample identity ledgers;
- time-partitioned raw measurements;
- quality events, hourly aggregates, retention runs, and projection checkpoints;
- no foreign-key path from a sample to an automatic business-state mutation.

The raw measurement source timestamp is the partition time. Central ingest and
processing timestamps are preserved separately. Raw telemetry is never inserted into
orders, WIP, inventory, quality, maintenance, audit, or legacy `metrics` by the new
ingest path.

This is a PostgreSQL-native Historian PoC, not a claim that plain PostgreSQL is the
final plant Historian. TimescaleDB remains the preferred next evaluation when any of
these thresholds is reached:

- sustained ingest above 1,000 samples/second per site;
- retained raw data above 100 million rows or 30 days at target rate;
- required compression below 40 percent of plain PostgreSQL storage;
- aggregate/query service-level objectives fail under measured concurrency;
- multi-site Historian isolation or continuous aggregates become operational needs.

The Phase 7 gate must record measured batch ingest and window-query results using the
same code path and schema as runtime ingestion. Synthetic/SimPy source remains labeled
`simulated`; benchmark load is engineering evidence, not physical-plant evidence.

### Redis Projection

Redis is a disposable current-state read model. On this Windows engineering host,
Memurai Developer 4.1.2 is selected as a Redis 7 API-compatible runtime because the
official old Windows Redis port is obsolete and neither Docker nor WSL is available.

The application uses the standard Redis protocol/client and must also run against
Redis/Valkey on Linux without code changes. Memurai's developer license is not a
production deployment approval. Production requires a supported Redis/Valkey service
or appropriately licensed Windows runtime.

PostgreSQL `telemetry.measurements` is the rebuild source. Rebuild writes a versioned
namespace, verifies key count and maximum source identity, atomically switches the
active pointer, records a checkpoint, and only then retires the old namespace. Redis
failure degrades the read projection; it never rolls back or fabricates telemetry.

### Object Storage And Document Integrity

MinIO Server is selected for the local S3-compatible object-storage implementation.
Object bytes use a content-addressed key derived from SHA-256. PostgreSQL stores the
manifest, storage version/ETag, media type, byte length, lifecycle state, and integrity
events. A controlled document revision stores its content SHA-256 whether content is
legacy inline text or an immutable object.

An object becomes `available` only after upload and read-back checksum verification.
Database failure after upload triggers best-effort object removal and an explicit
failure; no revision may reference a pending or checksum-mismatched object. Retrieval
recomputes SHA-256 before returning bytes.

MinIO is not a business fact source. The governed PostgreSQL manifest and document
revision decide which exact bytes are approved/effective.

### Data Quality

Every measurement carries:

- source and source identity;
- signal identity, unit, and mapping version;
- source sequence;
- source, edge-received, central-ingested, and processed timestamps;
- optional simulation time;
- quality code and machine-readable reasons;
- manual/correction flags and correction reason where applicable.

Definitions govern unit, numeric range, freshness threshold, source class, and mapping
version. Duplicate, sequence conflict, out-of-order, future-time, stale, range, unit,
and mapping checks are deterministic. Bad samples remain visible as evidence but do
not become accepted business facts. Missing status is derived from active definitions
and latest accepted observation.

### Compatibility Boundary

Legacy heartbeat ingestion remains for node health and v2.2 compatibility. Phase 7
node runtimes additionally send typed telemetry batches. Heartbeat-derived calls must
stop appending the same sample stream to legacy `metrics`; the existing table is
retained as historical compatibility evidence and may only serve the explicit legacy
`/metrics` interface.

Phase 7 does not add a physical connector. `live` source is rejected unless the later
industrial connector boundary is enabled and governed. No telemetry sample directly
reports accepted production quantity, material consumption, quality release,
maintenance completion, or equipment command success.

## Security And Scope

- All PostgreSQL Phase 7 rows carry tenant/site and use forced RLS.
- Node telemetry ingest uses the machine credential path; management, read, rebuild,
  retention, and object actions use distinct JWT permissions.
- Redis and MinIO listen only on loopback in the local runtime.
- Redis and MinIO credentials live outside the repository under the protected runtime
  root and are never returned by status APIs.
- Object keys, Redis keys, and query filters include tenant/site scope.

## Failure Semantics

- PostgreSQL ingest failure: reject the batch; do not update Redis.
- Redis update failure: persist the batch, report projection degraded, and rebuild
  from PostgreSQL.
- Duplicate batch/sample with identical payload: idempotent replay result.
- Reused identity with different payload: HTTP 409 and immutable evidence retained.
- MinIO unavailable/checksum mismatch: do not finalize object or revision.
- Retention failure: preserve raw data and record failed run; never delete without a
  completed aggregate/checkpoint precondition.

## Consequences

The architecture gains explicit source, freshness, quality, retention, projection,
and document-integrity semantics at the cost of three operational dependencies and a
larger migration/gate surface. The phase cannot claim production Historian, HA,
physical signal validity, disaster recovery, or plant acceptance until later pilots
and restore/load gates prove them.
