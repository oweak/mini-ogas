# Mini-OGAS Verification Matrix

Updated: 2026-07-13

Status classes: A = runtime verified, B = implemented but not currently runtime
verified, C = shell/interface only, D = documentation only, E = incorrect or
broken against the current requirement.

| Capability | Requirement | Code/evidence | Verification command | Last actual result | Class | Remaining risk |
| --- | --- | --- | --- | --- | --- | --- |
| Local supervised startup | Stable baseline | `scripts/start-miniogas.ps1`, Go supervisor | `scripts/start-miniogas.ps1`; runtime status check | 9/9 processes, zero crashes on 2026-07-13 | A | Not a VM deployment |
| PostgreSQL central facts | Historical fact source | central repository/database modules | `scripts/verify-miniogas.ps1` | PostgreSQL primary, event envelope and projection passed 2026-07-13 | A | Single local instance; no HA claim |
| Phase 1 environment boundary | Production cannot silently run Demo/Mock or enable writes | `app/core/config.py`, environment tests | central pytest | Invalid source/control/production combinations fail closed | A | No real connector is installed |
| Tenant/site data scope | Scope must be effective below API layer | Phase 1 migration, forced RLS, scoped connections | `scripts/check_phase1_database.py` | 18/18 tables forced RLS; negative scope returned zero rows | A | Deployment-scoped, not a multi-tenant control plane |
| Transactional Outbox foundation | Durable intent with business write | `core/outbox.py`, heartbeat repository transaction | unit tests plus live DB gate | 112 published, zero cross-scope rows at final gate | A for heartbeat | Event/command/audit business mutations are not wired yet |
| OpenAPI/AsyncAPI contract | Contract follows real code and labels gaps | generated `contracts/`, manifest, exporter | `tools/export_contracts.py --check` | Deterministic drift check passed | A | Only heartbeat operations are declared wired |
| Unified API errors | Correlatable, UTC, non-leaking errors | `core/errors.py`, `core/identity.py` | central smoke tests | Request ID/problem contract and hidden internal detail passed | A | Distributed trace propagation is later work |
| Secret governance | No tracked secret and restricted local files | secret scan, ACL provision/check, config fail-fast | canonical verification | Scan passed; 9/9 sensitive paths restricted | A for local Windows | Managed vault and automatic rotation absent |
| Dashboard snapshot | Backend fact display | `/api/dashboard/snapshot`, `runtimeState.ts` | Dashboard tests + browser QA | 3/3 live, replay separated, raw/controlled output visible | A | HTTP polling remains local-runtime design |
| JWT/RBAC gate | Controlled operator access | `app/core/auth.py`, startup gate | central/dashboard tests | Passed 2026-07-13 | A | Production identity provider absent |
| AI provider degradation | AI failure must not stop core | AI registry/dispatcher/fallback | AI tests and live smoke | fallback tests and DeepSeek call passed | A | Remote availability external |
| Basic command polling | Command reaches Python edge | simulator command loop, SQLite result outbox, command manager | runtime workflow + simulator unit tests | Commands 54/55 claimed, applied, reported and verified live; 35 edge tests | A | HTTP command polling is not v3 message transport |
| Command effect verification | Observe later production facts | `app/command_verifier.py` | central pytest + live commands | Command 54 classified partial with evidence; command 55 restored nominal rate and became effective after 3 observations | A | Threshold calibration needs production data |
| SimPy physical consistency | 80/50/~65 per hour; physical time | `services/node-agent/simulator.py` | simulator tests + live snapshot | 35 tests; live nominal 80/50/64.9 per hour and physical throttle divergence proven | A | Simulation is not a digital twin certification |
| Deterministic rule coverage | Required fault/flow conditions | `app/rules.py` | central rule tests + snapshot | Latest-command supersession, fault, flow and evidence contracts pass in 173-test suite | A | More plant-specific thresholds need calibration |
| Stable event envelope | v2.5 event schema | `IncidentEvent`, `event_store`, persistence/replay | event, database and full central tests | Idempotent envelope, ordered restore, PostgreSQL replay and transaction rollback pass | A | HTTP ingress is not the final NATS transport |
| Three-operation part trace | Identity, causal flow and exactly-once claim | part queue/store, heartbeat delta flow | queue, run-switch, restart and live snapshot | Live current-run queue, PostgreSQL projection and raw/controlled production facts verified | A | Multi-host network transfer is v3 work |
| Offline buffer and resync | Disconnect/recover without loss | edge SQLite, `node_record_receipts`, heartbeat archive | process pause plus reconnect/reorder/dedupe tests | Node pause/recovery and durable replay preserve live facts without duplicate receipt | A | Independent-host failure remains unproven |
| Read-only replay | Historical facts do not mutate live | replay repository/API/UI | replay tests/browser | Passed 2026-07-13 | A | Must migrate to unified events |
| NATS shadow transport | Durable parallel event channel | `nats_publisher.py`, `nats_contracts.py`, JetStream, `nats_shadow_receipts` | canonical verification plus normal/unavailable live gates | 9/9 runtime, four message types persisted, unavailable NATS degrades without blocking REST | A | Loopback single node only; HTTP remains authoritative |
| Redis current cache | Current-state projection | topology/docs only | Redis integration required | Not implemented | D | Memory projection remains local cache |
| Independent workshop VMs | v3.0 failure boundaries | deployment target only | VM network acceptance required | VBoxManage not on PATH | D | No VM evidence |
| Authorized attack lab | Controlled test only | Kali workflow scripts/tests | Kali workflow test | Guard tests passed; no VM runtime | B | Lab VM absent/unverified |

## Core scenario state

| Scenario | Required proof | Current status | Next evidence |
| --- | --- | --- | --- |
| Normal production | Ordered parts, coherent rates/WIP/time, DB/UI parity | A | Live run, 3/3 SimPy, current-run part queue, PostgreSQL and Dashboard parity verified |
| Real bottleneck | 80 -> 50 capacity, WIP growth, rule and AI explanation | B | Physical and deterministic rule tests pass; causal live WIP run pending |
| Controlled speed change | Safety, physical apply, later observations, Verifier result | A | Commands 54 and 55 proved throttle, restore and effective/partial lifecycle |
| Starvation | Reduced supply causes Grinding starvation | B | Causal multi-node scenario test |
| Node disconnect | offline, local buffer, replay, no duplicates | A for local process | Controlled process pause/reconnect and durable receipt tests pass; independent host remains v3 |
| High-risk approval | No execution before approval, full audit | A | Retest after event migration |
| AI failure | Rule core works, UI degraded, no fabrication | A | Retest after verifier work |
| Central restart | Facts restore without seed overwrite | A | Retest after event migration |
| Attack experiment | Authorized anomaly, detect, contain, recover, evidence | B | Requires isolated lab runtime |
