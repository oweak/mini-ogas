# Mini-OGAS Intelligent Factory System

Mini-OGAS is a lightweight distributed factory operations and production
planning system for graduate interview demonstration. It simulates a general
machining factory with turning, milling, and grinding workshops.

## Goals

- Monitor workshop node health: CPU, memory, disk, network, database latency.
- Collect local production data from each workshop node.
- Handle common faults with scripts before calling AI APIs.
- Use DeepSeek API for complex diagnosis, report generation, and planning advice.
- Isolate dangerous child nodes to protect the whole system.
- Simulate market demand changes and adjust production plans.
- Demonstrate authentication, RBAC, resource permissions, and audit logs.

## Current Deployment

- Central host: one Windows workstation running the Go supervisor.
- Central facts: PostgreSQL primary database.
- Runtime projection: authenticated Redis, rebuildable from PostgreSQL authority.
- Object storage: local MinIO service for document and evidence objects.
- Workshop nodes: three supervised SimPy processes (`turning`, `milling`, `grinding`).
- Authoritative transport: authenticated HTTP heartbeat, command polling and REST management.
- Shadow transport: local NATS Server + JetStream with schema-valid v3 envelopes and a PostgreSQL receipt worker.
- Optional attack lab: prepared Kali disk/tooling, not a production availability dependency.

Separate edge hosts and a registered Kali lab remain later v3.0 work and are not
current runtime claims. NATS is currently a loopback-only shadow path; it is not yet
the authoritative edge transport. Redis is active only as a rebuildable projection,
not as a business fact source.

## Identity and Control Boundary

- Human users authenticate with password-verified JWTs and stable `user:<name>`
  Principal IDs.
- Each production node uses a distinct random credential bound to its own
  `node_code`; the protected runtime ledger supports rotation and revocation.
- Service and AI Agent credentials are separate opaque bearer credentials with
  restricted roles. AI Agents may submit auditable suggestions but cannot issue
  or approve production commands.
- Target-rate issue, command approval/rejection/cancel/retry, node control,
  dispatch approval and escalation approval pass through verified permissions,
  resource checks, Safety Governor conditions and audit recording.
- The implemented role/resource/action/condition matrix is documented in
  `docs/security/principal-control-matrix.md`.

## Architecture

```text
central-control
|-- dashboard
|-- central-api
|-- ai-dispatcher
|-- market-simulator
|-- production-planner
|-- postgres (primary facts)
|-- redis (rebuildable runtime projection)
|-- nats-server + JetStream (shadow messages)
|-- nats-event-worker (idempotent PostgreSQL receipts)
|-- minio (object/evidence storage)
`-- go-supervisor

workshop-node
|-- node-agent
|-- local sqlite database
|-- metrics collector
|-- production simulator
`-- script fix engine
```

## First Version Scope

1. Central dashboard.
2. Three simulated workshop nodes.
3. Local node databases.
4. Operations metrics collection.
5. Rule-based fault handling.
6. DeepSeek diagnosis gateway.
7. Node isolation workflow.
8. Virtual market simulator.
9. Production report generator.
10. Permission and audit demonstration.

## Repository Layout

```text
mini-ogas/
|-- services/
|   |-- central-api/
|   |-- ai-dispatcher/
|   |-- dashboard/
|   |-- market-simulator/
|   |-- node-agent/
|   `-- production-planner/
|-- scripts/
|-- database/
|-- deploy/
|-- docs/
`-- README.md
```

## Implemented Technology

- Dashboard: Vue 3 + TypeScript + Vite.
- Central API: Python FastAPI.
- Runtime supervisor: Go.
- Node runtime: Python SimPy, with a Go node-agent implementation and tests.
- AI dispatcher: Python FastAPI with provider-chain fallback.
- Central database: PostgreSQL.
- Node/local test database: SQLite.
- Authoritative event transport: existing HTTP/REST path.
- Shadow event transport: `NATSPublisher` using strict schema `3.0` envelopes, JetStream file persistence, explicit ACKs and deterministic message IDs.
- NATS failure policy: `/health.status` remains `ok` for liveness while `/health.overall_status` and `/health.nats.status` report `degraded`; REST remains authoritative.

## Current Verification

The current implementation is a Python FastAPI `central-api`, Vue 3 dashboard,
Python `node-agent`, SimPy process-mode workshop nodes, and optional isolated
Kali/VirtualBox red-team lab support. Install the pinned NATS Server runtime once,
then start the local system through the supervisor entrypoint. Redis and MinIO are
resolved by the runtime bootstrap path:

```powershell
.\scripts\install-nats.ps1
```

```powershell
.\scripts\start-miniogas.ps1
```

If a script-managed stack is already running and you intentionally want the Go
supervisor to take ownership, run:

```powershell
.\scripts\start-miniogas.ps1 -ReplaceRunning
```

To roll back only the NATS shadow publisher/worker while preserving the REST
fact path, start the supervisor with:

```powershell
.\scripts\start-miniogas.ps1 -ReplaceRunning -DisableNats
```

The NATS process may remain available in this rollback mode, but Central does
not publish or consume shadow messages. The authoritative HTTP/PostgreSQL path
is unchanged.

The legacy lightweight launcher remains available with:

```powershell
.\scripts\start-miniogas.ps1 -UseScriptLauncher
```

Use the verification script below as the current truth check:

```powershell
.\scripts\verify-miniogas.ps1
```

This runs API contract checks, central API tests, node-agent tests, dashboard
tests, dashboard build, and a runtime check that verifies protected API access,
live SimPy heartbeats, PostgreSQL persistence, AI runtime state, and dispatch
alignment. It also runs Ruff correctness rules when the project development
environment is installed. Optional Kali/VirtualBox state is not used as
production-node proof.

The latest local hardening verification on 2026-07-15 passed 288 Central API tests,
39 simulator tests, 73 Dashboard tests and production build, 4 AI Dispatcher
tests, 36 CLI/workflow tests plus 9 subtests, both Go module suites, secret/ACL
checks and Ruff correctness. The strict runtime reported 12/12 healthy processes,
a ready dedicated background worker, live NATS Shadow, three unique node credentials
and 3/3 authenticated SimPy nodes.

AI model calls are only proven when the runtime check is run with:

```powershell
.\scripts\verify-miniogas.ps1 -RequireAiUnlocked
```

If that fails with `AI vault is present but locked`, the system is using rule
fallback and must not be described as having live DeepSeek participation.

The current Windows host does not have Docker/Compose installed. Clean Linux image
build and startup are nevertheless verified by GitHub Container Gate run
`29406148599`: Central API health, a real Node Agent heartbeat, and the production
Nginx Dashboard all passed. Full Compose-stack startup is still a later deployment
gate and must not be inferred from this image-level proof.
