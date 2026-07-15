# Stage E Single Outbox Publisher Evidence

Verified: 2026-07-15

Branch: `codex/current-stage-hardening`

## Goal

Make PostgreSQL transactional Outbox the only application publishing path to NATS.
API request workers must commit authoritative facts and Outbox envelopes, then return;
one dedicated worker owns transport retries and terminal status transitions.

## Reproduced Defect

Heartbeat ingestion already wrote a deterministic envelope to `outbox_messages` in
the same transaction as the durable heartbeat. The API route then called
`nats_runtime.publish_heartbeat()` directly and marked that Outbox row published or
failed. Every API process also opened a publisher connection in its lifespan. This
created two publishing owners: request workers and the dedicated Outbox worker.

## Implemented Boundary

- API lifespan initializes authentication only. It does not import, start or stop a
  NATS publisher.
- Heartbeat ingestion commits the PostgreSQL fact and transactional Outbox envelope,
  then reports `queued / outbox / background-worker` to the node.
- The route contains no direct publish or Outbox status mutation.
- `background-worker` is the only application runtime that calls
  `nats_runtime.publish_envelope()`. It owns claim leases, retries, published status
  and dead-letter transitions.
- PostgreSQL remains authoritative. NATS remains Shadow and a transport outage cannot
  roll back an already committed heartbeat.

## Automated Gates

- Architecture test rejects `nats_runtime` in API lifecycle and node routes.
- Architecture test requires exactly one `publish_envelope` call in the dedicated
  worker.
- Route test rejects request-side publishing by contract and verifies queued transport
  metadata.
- Existing Outbox tests retain deterministic message IDs, claim leases, retries,
  dead-letter behavior and idempotent Shadow receipts.

```powershell
cd 'D:\New project\mini-ogas\services\central-api'
.\.venv\Scripts\python.exe -m pytest `
  tests\test_background_worker.py tests\test_nats_publisher.py `
  tests\test_architecture_boundaries.py tests\test_migrations_outbox.py `
  tests\test_store.py -q
.\.venv\Scripts\python.exe -m pytest tests -q
```

Results:

- Focused publisher/Outbox/runtime suite: 68 passed.
- Complete Central API suite: 297 passed.
- Ownership map generated and committed-map check passed.

## Runtime Evidence

After `scripts/start-supervisor.ps1 -ReplaceRunning`:

- Supervisor session match: true; 12/12 processes healthy.
- Worker tasks: `simulation=running`, `outbox=running`.
- NATS publisher: live, connected, published 9, failed 0.
- NATS Shadow consumer: persisted 9, duplicate 0, invalid 0, failure 0.
- Production nodes: 3/3 online with fresh heartbeats.
- Central health sourced NATS readiness from the dedicated worker and remained ready.
- A heartbeat authenticated with the bound turning-node credential returned
  `queued / background-worker`; after three seconds publisher and Shadow persistence
  counters both advanced from 142 to 145 with zero failures. The concurrent increment
  includes normal heartbeats from all three running nodes.

## Architecture Impact

- Fact source: unchanged; PostgreSQL is authoritative.
- API: heartbeat response transport metadata changes from synchronous publish status to
  durable queue acceptance. Heartbeat payload and route remain compatible.
- Migration: none.
- Deployment: no new service; removes API NATS publisher connections.
- Rollback: disable NATS/worker transport while REST/PostgreSQL ingestion continues.

## Remaining Stage E Work

- Prove reconciliation thresholds and degraded/rollback behavior under a controlled
  NATS outage in the current 12-process runtime.
- Confirm every current and future consumer has a durable idempotency receipt before
  NATS can advance beyond Shadow mode.
- Keep Redis explicitly rebuildable from PostgreSQL and prove no projection can become
  authoritative.
