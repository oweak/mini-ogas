# Stage E Shadow Reconciliation, Degrade And Recovery Evidence

Verified: 2026-07-16

Branch: `codex/current-stage-hardening`

## Decision

Stage E is accepted for the current loopback Shadow boundary. PostgreSQL and the
authenticated REST path remain authoritative. NATS is not promoted to authoritative
transport, and `cutover_eligible` is deliberately always false pending a separate
manual stage gate.

## Unique Fact Owners

| Fact | Write owner | Durable authority / idempotency |
| --- | --- | --- |
| Node heartbeat | `NodeRepository` -> `CentralFactRepository.persist_heartbeat` | PostgreSQL `heartbeat_shadow`; deterministic heartbeat envelope enters Outbox in the same transaction |
| Telemetry metric | `DataPlatformRepository` / `NodeRepository` | PostgreSQL Historian tables; Redis is a rebuildable projection |
| Production event | `ExecutionRepository` / `IncidentRepository` | PostgreSQL execution/event tables with transaction and replay gates |
| Quality event | `QualityRepository` | PostgreSQL Phase 5 tables and append-only guards |
| Control command | `CommandControlService` -> `CommandRepository` | PostgreSQL command/audit/event transaction; node ledger owns edge execution idempotency |
| Audit record | Owning domain repository; `IncidentRepository` for compatibility events | PostgreSQL `audit_logs` / `event_store`; transactionally enqueued audit envelope |
| AI suggestion | AI suggestion route under AI Principal policy | PostgreSQL `ai_suggestions`; AI cannot directly create a production command |
| Transport publication | Dedicated `background-worker` only | PostgreSQL `outbox_messages`; no request-side publisher |
| Shadow receipt | `NATSEventWorker` | PostgreSQL `nats_shadow_receipts` primary key plus durable delivery/duplicate counters |

## Implemented Controls

- Added explicit migrations `2026.07.16-stage-e-shadow-metrics` and
  `2026.07.16-stage-e-outbox-stream-ordering`.
- Persisted `delivery_count`, `duplicate_count` and `last_ingested_at` without
  replaying a duplicate business mutation.
- Added a per-aggregate predecessor fence to Outbox claims. A newer message cannot
  bypass an older message that is waiting for retry.
- Added a read-only reconciliation report with a 100-message observation window,
  15-second propagation grace and a 100-sample minimum gate.
- Reported received rate, duplicate rate, end-to-end P50/P95/max latency, order
  comparisons/divergences, stale queue items, missing receipts, orphan receipts,
  dead letters and PostgreSQL reconciliation.
- Worker liveness remains `status=ok`; transport or threshold failures change
  `overall_status` to `degraded`, preventing a Supervisor restart storm.
- Replaced a stale NATS consumer whenever the publisher establishes a new connection
  after bounded reconnect exhaustion.
- Added Supervisor single-component `stop`/`start` operations. `stop` now waits for
  actual child exit and exposes an intermediate `stopping` state, so a returned
  `stopped` state has PID zero and no port-release race.

## Defect Found By The Live Gate

The first controlled outage recovered all 272 sampled messages but found eight order
divergences. The cause was retry backoff: an older per-node heartbeat became
temporarily unavailable while a newer heartbeat was eligible, so the newer envelope
was published first. The evidence was retained. The claim-level predecessor fence
was then added, and a new migration timestamp established the observation baseline
for the corrected ordering policy.

## Automated Verification

```powershell
cd 'D:\New project\mini-ogas\services\central-api'
.\.venv\Scripts\python.exe -m pytest tests -q

cd 'D:\New project\mini-ogas\services\supervisor'
$env:GOCACHE="$PWD\.runtime\go-cache"
$env:GOMODCACHE="$PWD\.runtime\go-mod-cache"
$env:GOPATH="$PWD\.runtime\go-path"
& 'C:\Program Files\Go\bin\go.exe' test ./...

cd 'D:\New project\mini-ogas'
.\scripts\verify-miniogas.ps1
```

Results:

- Central API: 312 passed.
- Stage E focused reconciliation/Outbox/worker suite: 31 passed at the final focused
  checkpoint; all tests are included in the full Central result.
- Go Supervisor: all packages passed, including component control and immediate
  stop/start tests.
- Simulator: 39 passed.
- AI Dispatcher: 4 passed.
- CLI/workflow: 36 passed plus 9 subtests.
- Dashboard: 16 files / 73 tests and production build passed.
- Go Node Agent, contracts, secret scan, ACL, Ruff correctness, strict runtime and
  PostgreSQL Phase 1/3/4/5/6/7 gates passed.

## Controlled Outage And Recovery

Reproduction command:

```powershell
cd 'D:\New project\mini-ogas'
.\scripts\check-stage-e-nats-recovery.ps1
```

Final gate result:

| Observation | Result |
| --- | ---: |
| Outage duration | 18 seconds |
| Stale Outbox rows observed during outage | 2 |
| Central liveness during outage | `ok` |
| Central readiness during outage | `degraded` |
| Recovered observation sample | 100 |
| Receive rate | 1.000000 |
| Duplicate rate | 0.000000 |
| P95 end-to-end latency | 4007.568 ms |
| Order divergences | 0 |
| PostgreSQL reconciliation | `matched` |
| Central readiness after recovery | `ready` |

The gate does not stop when NATS merely reconnects. It first requires zero pending
or missing receipts, then waits for a complete 100-message steady-state window to
meet every threshold. A subsequent immediate Supervisor stop/start test returned a
true stopped state with PID zero in 355 ms, restored NATS and the consumer, and the
steady-state report naturally returned to `ready`: receive rate 1.0, duplicate rate
0.0, P95 752.122 ms, zero order divergences and PostgreSQL `matched`.

## Rollback Boundary

The controlled stop proves the rollback boundary without deleting data: NATS can be
stopped while REST ingestion, PostgreSQL facts, the API and node processes remain
running. Outbox rows accumulate durably and replay after restart. The existing
`start-supervisor.ps1 -ReplaceRunning -DisableNats` path remains the configuration
rollback; disabled NATS is labeled `disabled`, never `live`.

## Architecture Impact

- Fact source: unchanged; PostgreSQL remains authoritative.
- API compatibility: unchanged; heartbeat responses still report durable queue
  acceptance.
- Database: two explicit, ledgered, repeatable Stage E migrations.
- Deployment: Supervisor management API gains loopback-only component start/stop;
  the component set is unchanged.
- Transport authority: unchanged; NATS remains Shadow.

## Next Gate

Stage F must align Supervisor, Compose, Dockerfiles, migration entrypoints, health,
readiness, volumes, environment variables and Dashboard production serving. Stage E
evidence does not prove full Compose deployment or multi-host transport.
