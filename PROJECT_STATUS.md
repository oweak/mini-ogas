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
| A - truthful baseline | Local path verified; container path open | Tests, production frontend build and 11-process Supervisor runtime pass. Docker/Compose cannot be run on this host. |
| B - P0 source fixes | Seven closed; two image fixes await container proof | B1-B3 and B6-B8 are tested. B4/B5 are statically corrected but not clean-built. |
| C - unified identity/control | Audit pending | JWT/RBAC, node token paths and Safety Governor exist, but all sensitive writes still require route-by-route proof. |
| D - `MemoryStore` decomposition | Not accepted | Some repositories exist; a complete ownership map, duplicate-state removal and restart proof are still required. |
| E - data/event convergence | Not accepted | PostgreSQL authority, Redis projection and NATS Shadow exist; unique writer/outbox/idempotency/reconciliation gates remain to be proved. |
| F - deployment convergence | Not accepted | Supervisor works locally, but Compose differs and Supervisor still serves Dashboard with Vite dev mode. |
| G - unified AI plane | Not accepted | Live DeepSeek and fallback evidence exist; sole model-call ownership and high-risk approval integration remain to be proved. |
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
| Central API | 260 passed |
| Python node simulator | 39 passed |
| Dashboard | 16 files / 73 tests passed |
| Dashboard production build | passed |
| AI dispatcher | 4 passed |
| CLI/workflow | 31 passed + 9 subtests |
| Go node-agent | passed |
| Go supervisor | passed |
| API and generated contracts | passed |
| Secret scan and ACL check | passed |
| Ruff correctness | passed |
| Strict Supervisor runtime | passed, 11 healthy processes and 3/3 fresh nodes |
| Docker/Compose build and startup | not run: Docker/WSL unavailable |

## Hard Boundaries

1. PostgreSQL is the central source of truth. SQLite is only node-local/test fallback.
2. Redis is a rebuildable projection and must never be described as authoritative.
3. NATS is a loopback Shadow path and must never be described as authoritative edge transport.
4. Live DeepSeek participation is proven only by an unlocked runtime verification result.
5. Dashboard production build passes, but the current Supervisor path still serves Vite dev mode.
6. Dockerfiles and Compose manifests existing in the repository do not prove container deployability.
7. Kali tooling remains laboratory-only; no registered, isolated Kali VM is currently claimed.

## Next Required Gate

Provide a Docker-capable host, run clean image/Compose build and startup, and record the
evidence in `docs/audits/current-stage-baseline.md`. Only then can Stage B be accepted
and Stage C implementation proceed without violating the mandatory order.
