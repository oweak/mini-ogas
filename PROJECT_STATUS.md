# Mini-OGAS Project Status

Verified: 2026-07-13

## Progress

| Stage | Completion | Acceptance boundary |
| --- | ---: | --- |
| v2.2 compatible trusted loop | 100% | Local deterministic three-node runtime, trusted control loop and persistence. |
| v2.5 architecture-debt cleanup | 100% | Local supervised multi-process architecture with PostgreSQL primary facts. |
| v3.0 true distributed system | 0% production deployment | Multi-host edge nodes, NATS, registered attack lab and HA are not claimed. |

## Current Architecture

```text
Vue Dashboard :5173
        |
        | JWT + REST
        v
FastAPI central-api :8080 ---- PostgreSQL primary facts
        |                         |-- scenarios / runs
        |                         |-- heartbeat history
        |                         |-- commands + audit transaction
        |                         |-- alerts / diagnoses / WIP
        |
        | HTTPPublisher / canonical heartbeat and command polling
        +---- turning SimPy process
        +---- milling SimPy process
        +---- grinding SimPy process
        |
        +---- AI dispatcher :8081
        +---- market simulator :8082
        +---- production planner :8083

Go supervisor :9099 owns all eight application processes.
```

The three workshop nodes are separate supervised processes on one Windows host. This is a real process/API/database integration, but it is not yet a multi-host deployment.

## Completed v2.5 Requirements

| Item | Result |
| --- | --- |
| v2.5.0 debt freeze | Every debt has status, owner and exit evidence in `docs/architecture-debt.md`. |
| v2.5.1 Snapshot migration | Core Dashboard runtime uses snapshot; legacy state is a wrapper. |
| v2.5.2 PostgreSQL primary facts | Repository/projection, schema migration, degraded state, rollback mode and restart recovery are implemented. |
| v2.5.3 API wrappers | Canonical agent heartbeat exists; legacy heartbeat/dashboard routes are deprecated wrappers. |
| v2.5.4 Command Manager | Complete lifecycle, idempotency, concurrency, retry, cancel, timeout and audit. |
| v2.5.5 Safety Governor | Role, risk, confirmation and RunMode policies gate all supported high-risk actions. |
| v2.5.6 Replay | Read-only database replay with formal run list and Dashboard timeline. |
| v2.5.7 Scenario/Run | Formal tables, deterministic seed, identity validation and attack/normal isolation. |
| v2.5.8 Adapters | `EventPublisher`/`HTTPPublisher` and `RuntimeAdapter`/SimPy implementations. |

## Runtime Verification

The latest strict check confirmed:

- 8/8 supervisor-owned processes healthy and session-matched.
- 3/3 fresh production node heartbeats.
- one shared `SCN-NORMAL-SIMPY-FLOW-001` scenario and deterministic seed per normal run.
- `data_source=live`, `simulation_engine=simpy`.
- PostgreSQL primary projection healthy with no unreported write failure.
- administrator login issued JWT and completed a real DeepSeek API smoke call.
- current snapshot contained no historical alerts or notifications.
- current WIP projection excluded historical runs.
- replay listed formal runs and showed `replay / 只读`.
- desktop and 390 px mobile browser checks had no horizontal overflow or clipped buttons.

## Automated Evidence

| Suite | Result |
| --- | ---: |
| central-api | 133 passed |
| Python node simulator | 26 passed |
| Dashboard | 63 passed |
| AI dispatcher | 4 passed |
| CLI/workflow | 30 passed + 9 subtests |
| Go node-agent | passed |
| Go supervisor | passed |
| Dashboard production build | passed |
| Real fault-to-archive workflow | passed |
| Secret scan | passed |

## Important Boundaries

1. PostgreSQL is the central source of truth; SQLite is not the normal central runtime.
2. Historical open rows remain available to audit/replay but never enter a new live run.
3. AI suggestions cannot directly bypass Command Manager or Safety Governor.
4. NATS and Redis are not active components. NATS is a v3 transport option; Redis has no current requirement.
5. Kali tooling is lab-only. The disk image being present does not mean the VM is registered or safe to run.

## Next Stage

Start v3.0 only after freezing the multi-host deployment contract: host roles, network zones, certificates, time synchronization, agent protocol, backup/restore and attack-lab isolation. Do not add NATS or extra VMs before that contract is accepted.
