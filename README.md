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
- Workshop nodes: three supervised SimPy processes (`turning`, `milling`, `grinding`).
- Transport: authenticated HTTP heartbeat, command polling and REST management.
- Optional attack lab: prepared Kali disk/tooling, not a production availability dependency.

Separate edge hosts, NATS transport and a registered Kali lab belong to the v3.0 roadmap and are not current runtime claims.

## Architecture

```text
central-control
|-- dashboard
|-- central-api
|-- ai-dispatcher
|-- market-simulator
|-- production-planner
|-- postgres (primary facts)
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
- Current event transport: HTTP via `EventPublisher` / `HTTPPublisher`.
- Future transport option: NATS behind the publisher interface; not deployed.

## Current Verification

The current implementation is a Python FastAPI `central-api`, Vue 3 dashboard,
Python `node-agent`, SimPy process-mode workshop nodes, and optional isolated
Kali/VirtualBox red-team lab support. Start the local system through the v2.5
supervisor entrypoint:

```powershell
.\scripts\start-miniogas.ps1
```

If a script-managed stack is already running and you intentionally want the Go
supervisor to take ownership, run:

```powershell
.\scripts\start-miniogas.ps1 -ReplaceRunning
```

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
alignment. Optional Kali/VirtualBox state is not used as production-node proof.

AI model calls are only proven when the runtime check is run with:

```powershell
.\scripts\verify-miniogas.ps1 -RequireAiUnlocked
```

If that fails with `AI vault is present but locked`, the system is using rule
fallback and must not be described as having live DeepSeek participation.
