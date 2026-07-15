# Mini-OGAS Architecture Debt Register

Updated: 2026-07-13

Scope: v2.2 trusted loop and v2.5 architecture-debt cleanup. This register separates accepted v2.5 local multi-process architecture from future v3.0 multi-host work.

## Status Rules

| Status | Meaning |
| --- | --- |
| `resolved` | Exit tests pass and the debt no longer blocks v2.5. |
| `mitigated` | The v2.5 boundary is safe, but a named v3.0 extension remains. |
| `open` | Acceptance evidence is missing or a supported path is unsafe. |

The stricter long-cycle audit reopened P0/P1 debt that the earlier local-runtime
acceptance did not test. Deferred multi-host work does not count as locally
implemented.

## Debt Matrix

| ID | Priority | Current status | Owner module | Exit tests / evidence |
| --- | --- | --- | --- | --- |
| DEBT-001 Dashboard legacy aggregation | P1 | `resolved` | `services/dashboard/src/runtimeState.ts`, `app/routers/demo.py` | Dashboard reads `/api/dashboard/snapshot`; `/api/dashboard-state` wrapper parity test passes. |
| DEBT-002 Heartbeat schema drift | P1 | `resolved` | `app/routers/nodes.py`, `services/node-agent/simulator.py` | Three live nodes report schema/run/scenario/simulation fields; canonical and legacy route tests pass. |
| DEBT-003 Simulation truth vs display truth | P0 | `resolved` for v2.5 | node simulator, snapshot projection | Physical 3x135/2x144/2x111 second profiles, live 80/50/64.9 capacities, raw/controlled output divergence, PostgreSQL projection and UI parity pass. |
| DEBT-004 Alert lifecycle side effects | P1 | `resolved` | alert workflow, Store, compatibility routes | Fault workflow proves open -> confirm -> diagnose -> approve -> close -> archive -> notification acknowledgement. |
| DEBT-005 AI orchestration coupling | P1 | `mitigated` | AI registry, AI dispatcher, control/ops routers | Provider/model/source provenance tests pass; real login smoke reports DeepSeek API. Multi-agent model plane remains v3.0 work. |
| DEBT-006 Command queue lifecycle | P0 | `resolved` for v2.5 | command manager, verifier, node loop | Commands 54/55 prove pending -> claimed -> applied -> verified, physical throttle/restore and latest-result rule retirement; durable outbox tests pass. |
| DEBT-007 WIP/part flow too shallow | P1 | `resolved` for v2.5 | `part_queue_shadow`, Store flow projection, Dashboard WIP view | Identity, monotonic sequence, current-run filtering, live PostgreSQL queue and SimPy-delta flow pass. Multi-host part transport remains v3. |
| DEBT-008 Memory as primary fact source | P1 | `resolved` for v2.5 | `app/persistence_repository.py`, database projection | PostgreSQL primary mode, restart recovery, degraded status, schema migration, replay drill and transaction rollback tests pass. Memory is a cache/projection. |
| DEBT-009 VirtualBox and production status confusion | P2 | `resolved` for production, `mitigated` for lab | startup workflow, runtime presentation, Kali tooling | Production count depends only on heartbeats. VirtualBox is optional Kali lab evidence and never production availability. |
| DEBT-010 Attack-lab safety boundary | P1 | `mitigated` | `scripts/kali_redteam_workflow.py`, Safety Governor | Private-target guard, explicit lab acknowledgement, isolated attack run, evidence output and approval gate tests pass. Kali VM registration is v3.0 deployment work. |
| DEBT-011 Sound/popup lifecycle drift | P2 | `resolved` | Dashboard sound policy and issue workflow | Sounds trigger only for new issues; terminal issues leave with animation and enter audit; normal startup has zero stale popups. |
| DEBT-012 Missing formal replay | P2 | `resolved` | replay repository/API/UI | Replay is DB-backed, read-only, marked `data_source=replay`, and mutation-isolation tests pass. Browser displays formal run list and timeline. |
| DEBT-013 Run identity leakage across facts | P0 | `resolved` | models, Store, repository, snapshot | Alerts, events, commands, diagnoses and part queue carry `run_id`; current projection excludes historical open rows; mixed scenario/seed is rejected. |
| DEBT-014 Frontend audit contract mismatch | P1 | `resolved` | `runtimeState.ts`, `App.vue` | Paginated `{events: []}` response is normalized to archive rows; UI no longer renders `undefined`; tests cover malformed payloads. |
| DEBT-015 Central Store size/coupling | P2 | `mitigated` | Store, `persistence_repository.py`, preflight, command/safety modules | Key SQL writes and transitions have dedicated modules and transaction tests. Full bounded-context split is intentionally deferred to v3.0. |
| DEBT-016 Stable event envelope absent | P0 | `mitigated` | models, persistence, publisher | Full envelope, unique ordered persistence, restart restoration and replay tests pass; final resolution waits for distributed transport proof. |
| DEBT-017 Required rule coverage incomplete | P1 | `mitigated` | `app/rules.py` | Required deterministic conclusions and calculation summaries pass focused/full tests; final resolution waits for live scenario/UI evidence. |
| DEBT-018 Distributed transport/current cache absent | P2 | `open` | EventPublisher, future NATS/Redis adapters | Add NATS only after event contract stabilizes; add Redis only as rebuildable current projection. |
| DEBT-019 AI explanation request amplification | P1 | `resolved` | Dashboard refresh gate, central AI cache | Semantic signatures ignore per-second evidence values, requests are single-flight, failures back off, server cache deduplicates and manual refresh bypasses; browser observed one AI request in 12 seconds. |
| DEBT-020 Diagnostic command leaked secret prefixes | P1 | `resolved` | `tools/mogas/commands/doctor.py` | Sensitive values now render only `SET (redacted)`; regression test and Ruff correctness gate pass. |

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

- central-api: 162 tests passed.
- Python node simulator: 35 tests passed.
- Dashboard: 69 tests passed and production build passed.
- AI dispatcher: 4 tests passed.
- CLI/workflow: 31 tests and 9 subtests passed, including doctor redaction.
- Go node-agent and Go supervisor tests passed.
- Strict runtime check: 8/8 supervised processes, 3/3 production nodes, PostgreSQL primary facts, live DeepSeek API.
- Real workflow: heartbeat fault through archive and notification acknowledgement passed.
- Browser: current alerts 0, stale popups 0, live WIP current-run only, replay read-only, desktop/mobile layouts without horizontal overflow, and AI polling deduplicated.
- Ruff correctness lint (`F`) passes across repository-owned Python source.
