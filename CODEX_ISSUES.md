# Mini-OGAS Issues Status

Last verified: 2026-07-13

## Acceptance Summary

| Scope | Status | Evidence |
| --- | --- | --- |
| v2.2 trusted loop | Complete | Contracts, Heartbeat v2, SimPy, rules, AI explanation, command polling, WIP flow and persistence tests pass. |
| v2.5 architecture cleanup | Complete for local multi-process scope | PostgreSQL primary projection, wrappers, Command Manager, Safety Governor, replay, formal run/scenario and adapter boundaries pass. |
| v3.0 true distributed deployment | Not started as a production claim | Separate edge hosts, NATS transport, registered Kali lab and HA remain roadmap work. |

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

## Current Supported Runtime Truth

- Runtime owner: Go supervisor, 8 managed processes.
- Production nodes: three process-hosted SimPy nodes, counted only from fresh heartbeats.
- Central fact source: PostgreSQL; memory is a cache/projection. SQLite is test/local fallback only.
- Dashboard fact source: `/api/dashboard/snapshot`; legacy state is a wrapper.
- AI: DeepSeek API is called only after administrator login; provider-chain fallback is explicit.
- Replay: PostgreSQL-backed, formal `run_id`, read-only and isolated from live state.
- Attack lab: script boundary is implemented; prepared Kali disk exists but the VM is not registered/running.

## Remaining Roadmap, Not Current Bugs

| Priority | Item | Target |
| --- | --- | --- |
| P1 | Freeze multi-host deployment and Agent Protocol contract. | v3.0.0 |
| P1 | Deploy each workshop agent to a separate host/VM with certificate auth and time sync. | v3.0.1-v3.0.3 |
| P1 | Implement `NATSPublisher` behind the existing interface. | v3.0.4 |
| P1 | Register and network-isolate the Kali VM before attack execution. | v3.0.6 |
| P2 | Split remaining Store projection into bounded repositories/services. | v3.0.x |
| P2 | Add HA, backup/restore SLOs and production observability. | v3.x |

## Verification

```powershell
.\scripts\verify-miniogas.ps1 -RequireAiUnlocked
& '.\services\central-api\.venv\Scripts\python.exe' '.\scripts\check_runtime_workflow.py'
.\scripts\check-runtime-status.ps1
```

Latest result: all required tests and live checks passed. Optional Ruff lint remains skipped when Ruff is not installed; it is not part of the current mandatory gate.
