# Mini-OGAS Project Status

Verified: 2026-07-15 on branch `codex/current-stage-hardening`

## Current Position

Mini-OGAS has a verified local supervised runtime and broad functional coverage, but
the current A-H hardening objective is not complete. Historical v2.2/v2.5 functional
gates do not replace the current requirements for clean container builds, unified
identity/control, PostgreSQL fact ownership, deployment convergence and end-to-end
proof.

| Current stage | Status | Evidence boundary |
| --- | --- | --- |
| A - truthful baseline | Local and key-image paths verified; full Compose open | Tests, production frontend build, 12-process Supervisor runtime and clean Central/Node/Dashboard containers pass. Full Compose startup remains unproved. |
| B - P0 source fixes | Accepted | B1-B8 are tested; B4/B5 are proven by clean container build and live Node Agent heartbeat. |
| C - unified identity/control | Accepted | Human, service, node and AI Agent Principals are persisted; node credentials are unique, bound, rotatable and revocable; sensitive command writes use the canonical control service. |
| D - `MemoryStore` decomposition | Accepted | Command, Node, Production Execution, Quality, Simulation and Incident/Event ownership have repository/restart/transaction evidence; Outbox and Redis/NATS/MinIO adapters are isolated, and periodic work has one owner. |
| E - data/event convergence | In progress | PostgreSQL authority, Redis projection and NATS Shadow exist; one dedicated Outbox publisher and idempotent Shadow receipts are proved. Reconciliation/degrade/rollback gates remain open. |
| F - deployment convergence | Not accepted | Supervisor works locally, but Compose differs and Supervisor still serves Dashboard with Vite dev mode. |
| G - unified AI plane | Not accepted | AI Agent suggestions are provenance-bearing and cannot create commands, but AI Dispatcher is not yet the sole model-call owner. |
| H - final closed-loop proof | Not accepted | Existing workflow gates are useful evidence, but the entire market-to-audit chain has not yet been proven as one automated scenario. |

## Verified Runtime Truth

```text
Vue Dashboard :5173 (Supervisor currently uses Vite development server)
        |
        | JWT + REST
        v
FastAPI central-api :8080 ---- PostgreSQL authoritative facts
        |                         |-- scenarios / runs
        |                         |-- heartbeat history
        |                         |-- commands + audit transaction
        |                         |-- production / quality / maintenance facts
        |
        |---- background worker :8084 (simulation + Outbox + NATS consumer)
        |---- Redis rebuildable projection
        |---- NATS JetStream Shadow + PostgreSQL receipts
        |---- MinIO object/evidence storage
        |---- AI dispatcher :8081
        |---- market simulator :8082
        |---- production planner :8083
        |---- three SimPy workshop processes
        `---- Go supervisor :9099
```

The three workshop nodes are separate processes on one Windows host. This is real
process/API/PostgreSQL integration, but it is not an independently hosted distributed
deployment. HTTP/REST remains authoritative; NATS remains Shadow.

## Automated Evidence

| Suite or gate | Latest result |
| --- | ---: |
| Central API | 288 passed |
| Python node simulator | 39 passed |
| Dashboard | 16 files / 73 tests passed |
| Dashboard production build | passed |
| AI dispatcher | 4 passed |
| CLI/workflow | 36 passed + 9 subtests |
| Go node-agent | passed |
| Go supervisor | passed |
| API and generated contracts | passed |
| Secret scan and ACL check | passed |
| Ruff correctness | passed |
| Strict Supervisor runtime | passed, 12 healthy processes, dedicated worker ready and 3/3 fresh nodes |
| Runtime identity/control | passed, 3 distinct node credentials; rotation/revocation and AI suggestion isolation verified |
| Clean key-image build/start | passed: GitHub Container Gate `29410060670` on Stage D commit `3125430` |
| Full Compose-stack startup | not yet proved |

## Hard Boundaries

1. PostgreSQL is the central source of truth. SQLite is only node-local/test fallback.
2. Redis is a rebuildable projection and must never be described as authoritative.
3. NATS is a loopback Shadow path and must never be described as authoritative edge transport.
4. Live DeepSeek participation is proven only by an unlocked runtime verification result.
5. Dashboard production build passes, but the current Supervisor path still serves Vite dev mode.
6. Container Gate proves the three key images, but does not yet prove full Compose parity or persistence services.
7. Kali tooling remains laboratory-only; no registered, isolated Kali VM is currently claimed.

## Next Required Gate

Continue Stage E from the accepted Stage D boundaries. The unique Outbox publisher is
proved; reconciliation/degrade/rollback gates remain. Full Compose parity remains
tracked for Stage F.
