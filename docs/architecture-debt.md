# Mini-OGAS Architecture Debt Register

Updated: 2026-07-13

Scope: v2.2 trusted loop and v2.5 architecture-debt cleanup. This register separates accepted v2.5 local multi-process architecture from future v3.0 multi-host work.

## Status Rules

| Status | Meaning |
| --- | --- |
| `resolved` | Exit tests pass and the debt no longer blocks v2.5. |
| `mitigated` | The v2.5 boundary is safe, but a named v3.0 extension remains. |
| `open` | Acceptance evidence is missing or a supported path is unsafe. |

No P0/P1 debt remains open for the v2.5 acceptance scope. Deferred multi-host work does not count as locally implemented.

## Debt Matrix

| ID | Priority | Current status | Owner module | Exit tests / evidence |
| --- | --- | --- | --- | --- |
| DEBT-001 Dashboard legacy aggregation | P1 | `resolved` | `services/dashboard/src/runtimeState.ts`, `app/routers/demo.py` | Dashboard reads `/api/dashboard/snapshot`; `/api/dashboard-state` wrapper parity test passes. |
| DEBT-002 Heartbeat schema drift | P1 | `resolved` | `app/routers/nodes.py`, `services/node-agent/simulator.py` | Three live nodes report schema/run/scenario/simulation fields; canonical and legacy route tests pass. |
| DEBT-003 Simulation truth vs display truth | P0 | `resolved` | snapshot projection, Dashboard runtime presentation | Live browser shows `data_source=live`, SimPy, one shared scenario/run and 3/3 nodes; fallback is visibly labelled. |
| DEBT-004 Alert lifecycle side effects | P1 | `resolved` | alert workflow, Store, compatibility routes | Fault workflow proves open -> confirm -> diagnose -> approve -> close -> archive -> notification acknowledgement. |
| DEBT-005 AI orchestration coupling | P1 | `mitigated` | AI registry, AI dispatcher, control/ops routers | Provider/model/source provenance tests pass; real login smoke reports DeepSeek API. Multi-agent model plane remains v3.0 work. |
| DEBT-006 Command queue lifecycle | P1 | `resolved` | `app/command_manager.py`, node command loop | Timeout/retry/supersede/cancel/idempotency/concurrent claim/result/heartbeat verification tests pass. |
| DEBT-007 WIP/part flow too shallow | P1 | `resolved` | `part_queue_shadow`, Store part queue, Dashboard WIP view | Turning -> milling -> grinding transfer and claim/complete tests pass; live current-run WIP is visible. |
| DEBT-008 Memory as primary fact source | P1 | `resolved` for v2.5 | `app/persistence_repository.py`, database projection | PostgreSQL primary mode, restart recovery, degraded status, schema migration, replay drill and transaction rollback tests pass. Memory is a cache/projection. |
| DEBT-009 VirtualBox and production status confusion | P2 | `resolved` for production, `mitigated` for lab | startup workflow, runtime presentation, Kali tooling | Production count depends only on heartbeats. VirtualBox is optional Kali lab evidence and never production availability. |
| DEBT-010 Attack-lab safety boundary | P1 | `mitigated` | `scripts/kali_redteam_workflow.py`, Safety Governor | Private-target guard, explicit lab acknowledgement, isolated attack run, evidence output and approval gate tests pass. Kali VM registration is v3.0 deployment work. |
| DEBT-011 Sound/popup lifecycle drift | P2 | `resolved` | Dashboard sound policy and issue workflow | Sounds trigger only for new issues; terminal issues leave with animation and enter audit; normal startup has zero stale popups. |
| DEBT-012 Missing formal replay | P2 | `resolved` | replay repository/API/UI | Replay is DB-backed, read-only, marked `data_source=replay`, and mutation-isolation tests pass. Browser displays formal run list and timeline. |
| DEBT-013 Run identity leakage across facts | P0 | `resolved` | models, Store, repository, snapshot | Alerts, events, commands, diagnoses and part queue carry `run_id`; current projection excludes historical open rows; mixed scenario/seed is rejected. |
| DEBT-014 Frontend audit contract mismatch | P1 | `resolved` | `runtimeState.ts`, `App.vue` | Paginated `{events: []}` response is normalized to archive rows; UI no longer renders `undefined`; tests cover malformed payloads. |
| DEBT-015 Central Store size/coupling | P2 | `mitigated` | Store, `persistence_repository.py`, preflight, command/safety modules | Key SQL writes and transitions have dedicated modules and transaction tests. Full bounded-context split is intentionally deferred to v3.0. |

## Detailed Exit State

### Snapshot and Compatibility

- Canonical node ingestion is `POST /api/agents/{node_code}/heartbeat`.
- `POST /api/node-heartbeats` remains a deprecated compatibility wrapper and emits deprecation metadata/logging.
- `GET /api/dashboard/snapshot` is the Dashboard fact contract.
- `GET /api/dashboard-state` is generated from snapshot and does not own business logic.

### PostgreSQL Primary Facts

- `CENTRAL_FACT_SOURCE=postgresql` is the default supervised runtime.
- `-FactSource memory` is an explicit operational rollback, not the normal production claim.
- Heartbeats, scenarios, runs, commands, audit events, alerts, diagnoses and part queue are persisted with run identity.
- Command state plus its incident event use one repository transaction.
- Projection/write failures are exposed as degraded persistence instead of being hidden.
- SQLite remains limited to automated tests and explicit local/edge fallback.

### Run Isolation

The 2026-07-13 audit found two cross-run defects and closed both:

1. Historical open alerts were restored from PostgreSQL and displayed in a new run. `Alert.run_id` is now restored and operational queries use only the current node run.
2. `PartQueueItem.run_id` existed in SQL but not in the domain model. Parts now own an immutable run identity, downstream parts inherit it, and agents cannot claim prior-run WIP.

Audit/replay retains historical data; live snapshot intentionally does not.

### Safety and AI

- High-risk node, control, dispatch, escalation and attack-lab actions pass through Safety Governor.
- Denials carry machine-readable reason codes and are audited.
- AI output records actual provider, model and source; rule fallback is never labelled as a live API result.
- The accepted local runtime proves a DeepSeek API call after administrator login. Availability of the remote provider is still an external dependency.

## Remaining v3.0 Work

The following are roadmap items, not hidden v2.5 claims:

1. Deploy workshop agents on separate hosts/VMs with certificates and time synchronization.
2. Add a NATS publisher implementation behind `EventPublisher`; HTTP remains the current implementation.
3. Add Redis only if a measured coordination/cache requirement justifies it.
4. Register and isolate the prepared Kali VM before executing red-team scenarios.
5. Split the remaining Store projection into bounded repositories/services after distributed contracts are frozen.
6. Add service-level HA, backup/restore objectives and production observability.

## Acceptance Evidence

On 2026-07-13:

- central-api: 133 tests passed.
- Python node simulator: 26 tests passed.
- Dashboard: 63 tests passed and production build passed.
- AI dispatcher: 4 tests passed.
- CLI/workflow: 30 tests and 9 subtests passed.
- Go node-agent and Go supervisor tests passed.
- Strict runtime check: 8/8 supervised processes, 3/3 production nodes, PostgreSQL primary facts, live DeepSeek API.
- Real workflow: heartbeat fault through archive and notification acknowledgement passed.
- Browser: current alerts 0, stale popups 0, live WIP current-run only, replay read-only, desktop/mobile layouts without horizontal overflow.
