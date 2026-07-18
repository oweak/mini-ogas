# Mini-OGAS Project Status

Verified: 2026-07-18 on branch `codex/current-stage-hardening`

## Current Position

Mini-OGAS has completed the current A-H hardening objective. Acceptance is based on
the canonical full verifier, a live DeepSeek call, a real three-process SimPy control
loop, PostgreSQL fact/audit evidence and an independent clean Container Gate. This
does not convert the prototype into a mature MES/MOM or prove multi-host production
deployment.

| Current stage | Status | Evidence boundary |
| --- | --- | --- |
| A - truthful baseline | Accepted | Tests, production frontend build, 12-process Supervisor runtime and clean full-Compose deployment are independently verified. |
| B - P0 source fixes | Accepted | B1-B8 are tested; B4/B5 are proven by clean container build and live Node Agent heartbeat. |
| C - unified identity/control | Accepted | Human, service, node and AI Agent Principals are persisted; node credentials are unique, bound, rotatable and revocable; sensitive command writes use the canonical control service. |
| D - `MemoryStore` decomposition | Accepted | Command, Node, Production Execution, Quality, Simulation and Incident/Event ownership have repository/restart/transaction evidence; Outbox and Redis/NATS/MinIO adapters are isolated, and periodic work has one owner. |
| E - data/event convergence | Accepted | One Outbox publisher, durable idempotent receipts, per-stream retry order, 100-message reconciliation thresholds and controlled NATS degrade/recovery are proved. NATS remains Shadow. |
| F - deployment convergence | Accepted | Supervisor and Compose run the same core services, migration is one-shot, Dashboard is production-built, and clean full-stack restart persistence passed. |
| G - unified AI plane | Accepted | AI Dispatcher is the sole model-call owner; provider policy, provenance, timeout/retry/token budgets, fallback, cost, latency, redaction, egress and dedicated service authentication are unified. High-risk advice enters a human-only command approval chain. |
| H - final closed-loop proof | Accepted | Order `AO-006` changed the P3 plan and approved grinding target; command `60` was claimed, applied and verified from SimPy rate/output changes, then reconciled through PostgreSQL, Dashboard and audit/event history. |

## Verified Runtime Truth

```text
Vue Dashboard :5173 (Supervisor serves a production build with Vite preview)
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
| Central API | 330 passed |
| Python node simulator | 40 passed |
| Dashboard | 16 files / 74 tests passed |
| Dashboard production build | passed |
| AI dispatcher | 13 passed |
| Production planner | 2 passed |
| CLI/workflow | 41 passed + 9 subtests |
| Go node-agent | passed |
| Go supervisor | passed |
| API and generated contracts | passed |
| Secret scan and ACL check | passed |
| Ruff correctness | passed |
| Strict Supervisor runtime | passed, 12 healthy processes, dedicated worker ready and 3/3 fresh nodes |
| Runtime identity/control | passed, 3 distinct node credentials; rotation/revocation and AI suggestion isolation verified |
| Clean key-image build/start | passed |
| Stage H governed closed loop | passed: command `60`, `0.592 -> 0.750`, actual `0.432 -> 0.547`, finished `6 -> 7`, PostgreSQL/Dashboard effective |
| Full Compose-stack startup and restart persistence | passed: GitHub Container Gate `29632887914` on Stage H implementation commit `51eba35` |

## Hard Boundaries

1. PostgreSQL is the central source of truth. SQLite is only node-local/test fallback.
2. Redis is a rebuildable projection and must never be described as authoritative.
3. NATS is a loopback Shadow path and must never be described as authoritative edge transport.
4. Live DeepSeek participation is proven only by an unlocked runtime verification result.
5. Supervisor serves the Dashboard production build through Vite preview; Compose serves it through Nginx.
6. Container Gate proves clean full-Compose parity and PostgreSQL persistence across Central restart.
7. Kali tooling remains laboratory-only; no registered, isolated Kali VM is currently claimed.

## Current Objective Decision

Stages A-H are accepted. The complete evidence is recorded in
`docs/audits/current-objective-completion-audit.md` and
`docs/audits/stage-h-governed-closed-loop-evidence.md`. Future work may pursue real
independent edge hosts, registered isolated Kali infrastructure and industrial HA,
but those are outside this accepted hardening objective and remain unclaimed.
