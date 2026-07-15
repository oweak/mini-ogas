# Phase 0 Baseline Audit

## Audit Identity

| Field | Observed value |
|---|---|
| Audit date | 2026-07-14 (Asia/Shanghai) |
| Repository | `D:\New project\mini-ogas` |
| Branch | `master` |
| Audited HEAD | `f3d8d8836331eb0dd378c12e50c05fa11dbcabda` |
| HEAD subject | `feat: complete v2.5 trusted runtime architecture` |
| Worktree | Dirty before this audit; existing user/agent changes were preserved |
| Master prompt hash | `05D7A7D08D55057FE93BE7DEEA2AB1B03A03D169282D486EDAE431AC6E6301C5` |
| Audit method | Source inspection, executable tests, runtime API probes, process/port inspection, PostgreSQL queries, VM inventory and ACL inspection |

This document records observed repository and runtime facts. Historical progress percentages and architecture reports were not accepted as evidence.

## Executive Verdict

Mini-OGAS is a functioning single-host digital-twin prototype with a tested operator-assisted control workflow. It is not yet an industrial MOM, not truly distributed, and not connected to physical equipment. The strongest implemented areas are automated regression coverage, SimPy workshop flow, PostgreSQL persistence, ordered migrations, forced RLS on the Phase 1 scoped tables, command state transitions, durable audit records, a Safety Governor and an administrator-unlocked DeepSeek path. The largest structural gaps are fact ownership inside a 4,162-line `MemoryStore`, seeded/random context mixed with persisted facts, shared node identity, absent Phase 2 master-data authority, no industrial connector, no independent equipment-effect verification and an unmanaged host clock.

During Phase 0, one material truth defect was corrected: SimPy heartbeats and dashboard snapshots are now labeled `simulated`, not `live`; demo overlays are labeled `fixture`; the browser no longer fabricates OEE, yield, work-order progress or due times when the backend has no fact.

## Capability Classification

| Capability | Status | Evidence | Claim boundary |
|---|---|---|---|
| Three workshop runtimes | Implemented for simulation | `services/node-agent/simulator.py`; 35 tests | Local Python processes, not three active VMs or real workshops |
| SimPy material flow | Implemented, partial domain fidelity | SimPy runtime, part queue, WIP projection | Discrete-event model, not calibrated plant physics |
| Central REST API | Implemented for the compatibility baseline | 197 compatibility tests; 76-route/24-call contract check | Phase 2 master-data routes are deliberately red and are the next unmet gate |
| PostgreSQL persistence | Implemented as primary/shadow historical store | Runtime status and table counts | State transitions still originate largely in memory |
| NATS/JetStream | Implemented in shadow mode | Loopback listeners and receipt table | REST remains authoritative; no multi-host transport proof |
| Dashboard | Implemented | 69 tests and production build | Displays simulated/seeded projection; no real device facts |
| Rule engine | Implemented for selected conditions | Rule tests and snapshot conclusions | Narrow rule set, not validated process knowledge |
| DeepSeek AI | Live provider path available after unlock | Startup check reported provider/model | Proposal/explanation only; availability depends on external provider |
| Command lifecycle | Implemented for simulation control | Manager/verifier and edge SQLite outbox tests | Effect verification is SimPy telemetry, not device state |
| Safety Governor | Implemented, with documented automation exception | `safety_governor.py`, store guards | Logical actions only; shared node token is a trust weakness |
| JWT/RBAC | Implemented at global role level | PBKDF2 + JWT + PostgreSQL role tables | No tenant/site/equipment data scope |
| Industrial connector | Absent | No OPC UA/Modbus/MQTT connector implementation | No real read or write |
| Production HA/DR | Absent | Single Windows host, single PostgreSQL/NATS | Go supervisor is process supervision only |
| Security lab | Bounded workflow only | Kali VM saved; scripts inject telemetry | Not proof of a real attack or defense |

## Repository And Runtime Topology

Observed active services are all on one Windows 11 host:

| Component | Technology | Observed endpoint/mode |
|---|---|---|
| Central API | Python/FastAPI | `127.0.0.1:8080` |
| AI dispatcher | Python service | `127.0.0.1:8081` |
| Market simulator | Python service | `127.0.0.1:8082`; random simulated signals |
| Production planner | Python service | `127.0.0.1:8083`; deterministic rules |
| Dashboard | Vue/TypeScript/Vite | `127.0.0.1:5173` |
| Supervisor | Go | `127.0.0.1:9099`; reported 9/9 processes healthy |
| NATS/JetStream | NATS | `127.0.0.1:4222`, monitoring `127.0.0.1:8222`, shadow mode |
| PostgreSQL | PostgreSQL | Port `5432`; network listener is broad, host auth observed localhost-only SCRAM |
| Workshop nodes | Python + SimPy | Turning, milling, grinding host processes |

The three production-node heartbeats reported `deployment_mode=process`, `simulation_engine=simpy`, scenario `SCN-NORMAL-SIMPY-FLOW-001`. No workshop VM was running during the audit.

## Data Source And Fake-Data Audit

### Confirmed simulated or seeded sources

| Data set | Actual producer | Persistence/read path | Phase 0 label |
|---|---|---|---|
| Workshop quantities, rates, WIP, defects, wear | `services/node-agent/simulator.py` | REST heartbeat -> memory transition -> PostgreSQL shadow -> snapshot | `simulated` |
| Simulated time/run/scenario | Node simulator | Heartbeat runtime payload | `simulated` |
| Market signals | `market-simulator` random generator and seed logic | In-memory integration result | `demo-seed` / simulation |
| Inventory | `MemoryStore.seed_demo()` | In memory | `demo-seed` |
| Initial machines/topology/cloud roles | `MemoryStore.seed_demo()` | In memory, partly overlaid by heartbeat | `demo-seed` or `mixed` |
| Planner suggestions | Rule service over simulated market/node inputs | Planner response and PostgreSQL shadow | Derived simulation |
| Rule demo query modes | `mode` query overlay in `routers/demo.py` | Response-only projection | `fixture` |
| Emergency demo issue | Legacy demo state builder | Response-only fixture | `fixture` |

### Corrected misleading presentation

Before this audit:

- any non-empty runtime source was mapped to dashboard `data_source=live`;
- NATS compatibility mapped legacy `node-agent` to `live` even for SimPy;
- the dashboard derived OEE from `CPU + 22`;
- zero output defaulted to 100% yield;
- due times were selected from work-order ID suffixes;
- work-order completion was summed in the browser across node cumulative quantities.

Phase 0 changed those paths so that:

- SimPy/simple engines are `simulated`;
- only physical runtime is eligible for `live`;
- non-normal response overlays are `fixture`;
- absent OEE, yield, completion and due facts display `未上报`;
- snapshots expose data provenance and explicitly state `device_write_enabled=false`.

### Remaining seeded-data limitation

`MemoryStore.__init__()` invokes `seed_demo()` only when `DEMO_SEED_ENABLED=true`. The audited `digital_twin` profile intentionally enables it and reports `data_source=simulated`; Production configuration rejects demo seed and simulated source. Seeded machine, order, market and inventory context remains mixed with heartbeat projections in the digital twin and is therefore still architecture debt, not production master data.

## `store.py` Responsibility Audit

`services/central-api/app/store.py` is 4,162 lines at audit time and owns too many responsibilities:

1. node registry and heartbeat cache;
2. metrics and machine projections;
3. alerts, incident events and audit logs;
4. command creation, transition and verification orchestration;
5. market, inventory and allocation state;
6. production plans and dispatch tasks;
7. part queue, claims, completion and WIP projections;
8. PostgreSQL/SQLite shadow load and write behavior;
9. integration probing and runtime readiness;
10. replay and run history;
11. random-walk central simulation;
12. seeded demo data and scenario injection;
13. safety decision recording and logical isolation;
14. management snapshot assembly.

This is not a module boundary suitable for production. It creates dual authority between memory and PostgreSQL and makes transactions, locking, authorization and testing difficult to reason about. It is registered as architecture debt, not silently accepted.

## Database Fact Audit

### Observed configuration

- Persistence backend: PostgreSQL.
- Reported central fact source: PostgreSQL.
- Read model: database projection.
- A historical overlapping-writer failure was observed on `(source_node, run_id, local_sequence)`. Phase 0 added PostgreSQL transaction-level sequence serialization, stale-writer rebasing, fail-closed behavior for primary PostgreSQL writes and a two-store regression test.
- After restart and the authoritative alarm workflow, `/api/persistence/status` and startup preflight reported `ok` with no current write failure.
- Ordered migrations are recorded in `schema_migrations`; the Phase 1 live gate observed three migration records and migration `2026.07.13-phase1-scope-outbox`.
- The application role is non-superuser, has no `BYPASSRLS`, and all 18 scoped tables use forced RLS in the live gate.
- SQLite remains in code for tests/local edge use and is not the intended central production backend.

### Observed PostgreSQL public tables

`ai_diagnosis`, `alerts`, `allocation_order_shadow`, `audit_logs`, `command_shadow`, `commands`, `dispatch_task_shadow`, `event_store`, `heartbeat_shadow`, `metrics`, `nats_shadow_receipts`, `node_record_receipts`, `part_queue_shadow`, `permissions`, `production_plan_shadow`, `role_permissions`, `roles`, `runs`, `scenarios`, `schema_migrations`, `user_roles`, `users`.

### Observed row counts during audit

| Table | Rows |
|---|---:|
| `schema_migrations` | 3 |
| `heartbeat_shadow` | 6,038 |
| `part_queue_shadow` | 2,587 |
| `command_shadow` | 55 |
| `commands` | 55 |
| `alerts` | 85 |
| `ai_diagnosis` | 62 |
| `audit_logs` | 8,080 |
| `event_store` | 1,391 |
| `outbox_messages` | 1,404 |
| `production_plan_shadow` | 5 |
| `dispatch_task_shadow` | 11 |
| `allocation_order_shadow` | 1 |
| `runs` | 10 |
| `scenarios` | 1 |
| `schema_migrations` | 2 |

The two recorded migration markers were `2026.07.13-v2.5-primary-facts` and `2026.07.13-v3.0.1-nats-shadow`. They are markers created by runtime initialization; there is no ordered migration directory with independently repeatable up/down or compatibility testing. All domain objects share the `public` schema.

### Authority conclusion

PostgreSQL is durable history for many objects, but it is not yet the sole transactional authority. `MemoryStore` mutates in-process objects and then writes or reloads shadow tables. Machines, inventory, topology, cloud roles, authority matrix and shortcuts retain seeded in-memory ownership. The runtime label “PostgreSQL fact source” must therefore be read as a target/current historical boundary, not proof that all displayed state is database-authoritative.

## Time, Rate And Simulation Audit

- Node simulation has a run ID, scenario ID, random seed, simulation start, simulation clock, wall clock and speed.
- SimPy capacity profiles encode machine count and process time; tests assert one-hour nominal capacity.
- `simulation_speed` accelerates simulated elapsed time and cumulative output; nominal hourly capacity remains unchanged.
- `target_rate` is a simulated control constraint measured in parts/minute; edge validation caps it to profile capacity.
- The command verifier observes later heartbeats and compares rates over multiple observations.
- Host Windows Time service was observed stopped/manual, and VMs were not running; cross-host clock synchronization has not been proven.
- Current `clock_offset_ms` is central-arrival skew, not a substitute for NTP/PTP evidence.
- The older central `simulation_step()` remains a random walk and must not be treated as SimPy or plant physics.

## Safety And Command Audit

### Implemented controls

- High-risk actions require `CONFIRM` and `system_admin` through the Safety Governor.
- Logical isolate/restore/retire operations require a matching allowed safety decision.
- Commands carry version, expiration, risk, status and parameters.
- The Python edge stores applied commands and result outbox data in SQLite, rejects unsupported versions/expired commands and avoids re-execution after restart.
- `set_target_rate` is verified by subsequent simulated heartbeat observations.

### Material limitations

- Isolation changes logical node/topology state; it does not cut a network switch, PLC or machine.
- `emergency_containment` permits a `safety_automation` logical isolation exception.
- A network metric threshold can trigger that exception automatically.
- All nodes share one ingest token; the credential is not cryptographically bound to node identity.
- A holder of that token can address another node's heartbeat/command endpoints.
- `restart_workshop_scheduler` currently acknowledges rather than performing a scheduler restart.
- `clean_temp_cache` has a bounded local host side effect; it is not an equipment command.
- Verification proves a SimPy response to a software command, not a physical effect observed independently.

No real device write path was found.

## Authentication And Secret Audit

Implemented:

- PBKDF2-HMAC-SHA256 password hashing with random salt and 310,000 iterations;
- HS256 JWT and PostgreSQL-backed roles/permissions;
- global `system_admin`, `operator` and `viewer` roles;
- legacy API token authentication disabled by default;
- AI key vault encrypted at rest and unlocked by administrator workflow;
- repository secret scan included in the authoritative verification script.

Open weaknesses:

- local development may use a generated/default secret, while Production fail-fast prevents accepting the development default;
- login has an in-process rate-limit bucket but no durable account lockout or MFA;
- forced PostgreSQL RLS covers 18 Phase 1 tables, while roles remain global and area/equipment-level policy is not implemented;
- node identity uses one shared bearer token rather than per-node mTLS/certificates;
- NATS uses one token and no TLS, although it is loopback-only today;
- the ACL conformance script passed for all nine configured runtime secret targets; rotation/revocation remains unexercised;
- the provider credential was previously disclosed in an operator conversation and must be rotated even though repository scans pass;
- production secret rotation and revocation have not been exercised.

## Phase 0 Gate Assessment

| Gate | Assessment | Evidence |
|---|---|---|
| Completed and incomplete work is unambiguous | Pass | This audit, source-of-truth matrix, debt and risk registers |
| No unmarked fake data | Pass for audited runtime/UI paths | SimPy=`simulated`; demo overlay=`fixture`; provenance metadata; absent frontend KPI=`未上报` |
| Current chain remains runnable | Pass | 9/9 supervisor processes, 3/3 fresh SimPy nodes, PostgreSQL preflight, live AI smoke and the full alarm-to-archive workflow passed |
| No real equipment write | Pass | No industrial connector; snapshot explicitly reports no connection/write |

**Final Phase 0 status: PASS (2026-07-14).** The Phase 0/Phase 1 compatibility partition completed with 197 central API tests, 35 simulator tests, all Go suites, 4 AI dispatcher tests, 31 CLI/workflow tests plus 9 subtests, 69 dashboard tests, a production frontend build, contract, Secret/ACL and strict runtime acceptance. The live runtime reported 3/3 SimPy nodes with `data_source=simulated`, 9/9 fresh supervisor-owned processes, PostgreSQL preflight `ok`, and a real DeepSeek provider smoke call. The authoritative alarm workflow passed all eleven stages through notification acknowledgement, offline-record archive and live-state preservation.

The unfiltered Central API invocation is intentionally **not green**: it reports `197 passed, 4 errors` because `tests/test_phase2_master_data.py` calls master-data routes that do not yet exist and receives HTTP 405. Those four tests are the executable Phase 2 entry gate, not a hidden Phase 0 regression. No report may claim the whole repository is green until that vertical slice is implemented.
