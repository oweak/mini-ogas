# Mini-OGAS Issues Status

Last verified: 2026-07-15 on branch `codex/current-stage-hardening`

## Acceptance Summary

| Scope | Status | Evidence |
| --- | --- | --- |
| Historical v2.2 trusted loop | Functionally accepted | Contracts, Heartbeat v2, SimPy, rules, AI explanation, command polling, WIP flow and persistence tests pass. |
| Historical v2.5 local cleanup | Functionally accepted, not the current hardening gate | PostgreSQL authority, wrappers, Command Manager, Safety Governor, replay, formal run/scenario and adapter boundaries pass locally. |
| Current A-H hardening objective | In progress | Stage A local runtime and key-image container gates pass. Stages B, C and D are accepted; Stage E has one Outbox publisher but reconciliation/degrade/rollback remains open. |
| True distributed deployment | Not claimed | Separate edge hosts, certificate-bound node identities, registered Kali lab and HA remain unproven. |

## Closed In This Audit

| ID | Defect | Resolution |
| --- | --- | --- |
| FIX-20260713-01 | Historical PostgreSQL alerts appeared as current popups while summary showed zero faults. | Added `Alert.run_id`, restored it from DB, and scoped all operational alert paths to the current node run. |
| FIX-20260713-02 | Result notifications from old runs could reappear after login. | Added `IncidentEvent.run_id`; live notifications include only unacknowledged events from the current run. |
| FIX-20260713-03 | Part queue SQL had `run_id`, but the domain object did not; target-node residue could assign WIP to the wrong run. | Added immutable `PartQueueItem.run_id`, source/system assignment, downstream inheritance and current-run claim filtering. |
| FIX-20260713-04 | Dashboard assigned the paginated audit response object to an array ref and displayed `undefined 条归档`. | Added audited response normalization and malformed-contract tests. |
| FIX-20260713-05 | Agent command creation emitted duplicate `command-created` events. | Removed route-level duplicate; Command Manager/Store transaction is the single event owner. |
| FIX-20260713-06 | Three supervised nodes shared a run but previously could carry different scenario IDs/seeds. | Unified scenario/seed configuration and reject mixed identities before mutation. |
| FIX-20260713-07 | AI provenance could report configured labels instead of the provider that actually answered. | Diagnosis/planning paths now return actual provider/model/source and test API vs fallback truth. |
| FIX-20260713-08 | High-risk actions had route-specific safety bypasses. | Node, control, ops, demo, dispatch, escalation and attack-lab paths now require Safety Governor decisions. |
| FIX-20260713-09 | Command and incident event persistence could diverge. | Repository transaction persists both or rolls both back; failure injection test proves rollback. |
| FIX-20260713-10 | Target-rate commands changed heartbeat labels but did not constrain physical SimPy output. | Added incremental physical rate control, raw/controlled counters and capacity checks; live command 54 proved divergence. |
| FIX-20260713-11 | Operator JWTs had no structured agent-command entry point. | Added `/ops/agents/{node}/commands`; machine claim/result routes remain node-token-only. |
| FIX-20260713-12 | Verifier compared only post-command observations and misclassified rate increases. | It now uses the creation baseline and direction-aware own-rate/downstream evidence; live command 55 verified effective. |
| FIX-20260713-13 | Old partial commands remained permanent live rule conclusions. | Rules evaluate the latest command per node/type; superseded failures remain only in audit/replay. |
| FIX-20260713-14 | Dashboard snapshot polling repeatedly called live AI as evidence values changed. | Semantic signature, single-flight/cooldown and server cache reduce calls; browser observed one call in 12 seconds. |
| FIX-20260713-15 | `mogas doctor` printed the first characters of sensitive environment values. | Secret values are fully redacted and covered by a regression test. |
| FIX-20260713-16 | Local steady-state rule text still named the configured DeepSeek provider despite no model call. | Local results now report `provider=rule_fallback`, `used_live_ai=false`; failed attempts use separate `attempted_provider`. |
| FIX-20260713-17 | Empty or unusable provider responses were marked as successful live AI explanations. | The provider chain and rule explanation contract now reject empty/unstructured output, fall back truthfully, and use a configurable 4096-token response budget for reasoning-capable models. |
| FIX-20260713-18 | A backlog-triggered bottleneck conclusion exposed an unmatched rate predicate, allowing AI to treat `0.94 <= 0.75` as evidence. | Rule conclusions now include only satisfied predicates and select summaries from the actual trigger path; a regression test covers backlog-only bottlenecks. |
| FIX-20260715-01 | Write routes trusted body-supplied `actor`/`operator` labels, allowing forged audit identity. | Audit and command paths now bind the verified Principal ID and ignore untrusted identity labels. |
| FIX-20260715-02 | Production nodes shared one ingest secret and legacy aliases exposed duplicate route surfaces. | Added three independently generated, node-bound credentials with rotation/revocation and removed duplicate `/api/api/...` aliases. |
| FIX-20260715-03 | Command lifecycle mutations were split across route-specific implementations. | Added `CommandControlService` for issue, approve, reject, cancel and retry with resource checks, Safety Governor, approval policy and audit. |
| FIX-20260715-04 | AI identity and advice had no persisted least-privilege boundary. | Added AI Agent Principals and auditable suggestions; high-risk suggestions enter `pending_human_review` and cannot create production commands. |
| FIX-20260715-05 | Phase 7 verification reused a shared node credential. | The gate now provisions a temporary node Principal, verifies bound telemetry and revokes the credential after the run. |
| FIX-20260715-06 | Command and node runtime projections were still owned directly by `MemoryStore`. | Added durable Command and Node repositories, compatibility projections, transaction/restart tests and a generated ownership map. |
| FIX-20260715-07 | Every API worker started simulation, Outbox and NATS consumer loops. | Moved periodic work to one `background-worker` process; API lifespan now owns request-serving dependencies only and architecture tests reject task creation there. |
| FIX-20260715-08 | Central liveness synchronously waited on Supervisor and worker readiness, creating a startup dependency cycle. | Bounded dependency probes to 250 ms, retained degraded readiness reporting and verified 195 ms Central health during a 12/12 supervised startup. |
| FIX-20260715-09 | Simulation control and progress remained eight independently mutable fields on `MemoryStore`. | Added one locked `RuntimeSimulationState`, made progress read-only through the compatibility facade, regenerated the ownership map and proved public API/worker tick consistency after restart. |
| FIX-20260715-10 | Stage D still listed Production Execution and Quality as unowned despite direct durable repositories already serving both route groups. | Added repository-recreation and architecture gates, confirmed transactional audit/Outbox behavior and accepted existing PostgreSQL Phase 3/5 owners without adding duplicate state. |
| FIX-20260715-11 | Heartbeat requests both enqueued a transactional Outbox row and published NATS directly; every API process opened a publisher connection. | Removed request-side NATS ownership. API workers commit fact plus Outbox only; the dedicated worker is the sole runtime publisher and owns retry/status transitions. |
| FIX-20260715-12 | Incident/Event state and mutation/restore SQL remained split across seven `MemoryStore` fields. | Added `IncidentRepository`, moved sequence/projection and Alert/AI/Event/Audit persistence boundaries, proved restart/cross-process PostgreSQL recovery and isolated transport/object adapters from the facade. |

## Current Supported Runtime Truth

- Runtime owner: Go supervisor, 12 healthy managed processes in the latest verified session.
- Periodic task owner: one `background-worker` process on port 8084; API workers do not create simulation, Outbox or NATS consumer tasks.
- Production nodes: three process-hosted SimPy nodes, counted only from fresh heartbeats.
- Central fact source: PostgreSQL; memory is a cache/projection. SQLite is test/local fallback only.
- Dashboard fact source: `/api/dashboard/snapshot`; legacy state is a wrapper.
- Runtime projection: authenticated Redis; it is rebuildable and not authoritative.
- Object storage: local MinIO process.
- Event transport: authenticated HTTP/REST remains authoritative; NATS JetStream is loopback-only Shadow with PostgreSQL receipts.
- AI: the verified `-RequireAiUnlocked` run used DeepSeek after administrator unlock; locked/failed runs must be reported as fallback.
- Replay: PostgreSQL-backed, formal `run_id`, read-only and isolated from live state.
- Attack lab: script boundary is implemented; prepared Kali disk exists but the VM is not registered/running.

## Current Hardening Gate

| ID | Requirement | Current evidence | Gate status |
| --- | --- | --- | --- |
| B1 | Block node-token cross-node command creation | RBAC/smoke subset: 57 passed | Closed |
| B2 | Repair Dashboard data-quality encoding/build | Dashboard: 16 files / 73 tests; production build passed | Closed |
| B3 | Declare Central API runtime dependencies | `psutil==7.1.3` pinned; dependency regression test; current full suite 288 passed | Closed |
| B4 | Complete Central API image inputs | Clean Linux image started and passed `/health` in latest Container Gate `29410060670` | Closed |
| B5 | Complete Node Agent image inputs | Clean Linux image sent an observable authenticated SimPy heartbeat in the same gate | Closed |
| B6 | Reject illegal environment aliases | Environment suite: 11 passed | Closed |
| B7 | Use one controlled Phase 5 clock | Phase 5 suite: 9 passed | Closed |
| B8 | Align status documents to evidence | README, project status, issues and baseline updated together | Closed |

Stage B is accepted. Docker Desktop/CLI and WSL remain absent on this Windows host,
but B4/B5 were independently proven on a clean GitHub Ubuntu runner. Full Compose
startup is still a Stage F gap.

## Stage C Acceptance

- Human, service, node and AI Agent identities share one persisted Principal schema.
- Opaque service/node/AI credentials are stored as hashes and support rotation and
  revocation; production startup rejects missing, duplicate or placeholder node secrets.
- Three runtime production nodes use distinct credentials bound to their own
  `node_code`; cross-node resource access is rejected.
- Sensitive command lifecycle actions use `CommandControlService`, verified
  permissions, resource ownership, Safety Governor, approval policy and audit.
- AI Agents can submit provenance-bearing suggestions only. A live high-risk
  suggestion persisted as `pending_human_review` without changing command count.
- The complete matrix and route evidence are recorded in
  `docs/security/principal-control-matrix.md`.

## Remaining Work

| Priority | Item | Target |
| --- | --- | --- |
| P1 | Complete NATS Shadow reconciliation/degrade/rollback gates; one Outbox publisher and the current idempotent Shadow consumer are proved. | Stage E |
| P1 | Align Supervisor/Compose/Docker/startup components; run Dashboard production build in deployment. | Stage F |
| P1 | Make AI Dispatcher the sole provider-chain owner and route high-risk advice through approval. | Stage G |
| P1 | Prove the full market-to-audit production-control loop, including state change and persistence. | Stage H |

## Verification

```powershell
.\scripts\verify-miniogas.ps1 -RequireAiUnlocked
& '.\services\central-api\.venv\Scripts\python.exe' '.\scripts\check_runtime_workflow.py'
.\scripts\check-runtime-status.ps1
```

Latest local verifier gates passed. Canonical counts are Central API 288, node
simulator 39, Dashboard 73 across 16 files plus production build, AI dispatcher 4,
CLI/workflow 36 plus 9 subtests, and both Go modules. Ruff correctness passes. The
strict runtime reports 12/12 healthy processes, a ready dedicated worker, live NATS
Shadow and 3/3 fresh SimPy nodes. GitHub
Container Gate `29410060670` on Stage D commit `3125430` also passed. Full Compose
parity and Stages D-H remain
open, so the current A-H objective is not complete.
