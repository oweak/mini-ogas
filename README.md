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

## Suggested Deployment

- Central node: Lenovo Legion Y7000P 2023 laptop.
- Child nodes: low-end cloud servers, 2 cores and 4 GB RAM each.
- Workshop nodes:
  - `turning-workshop`
  - `milling-workshop`
  - `grinding-workshop`

## Architecture

```text
central-control
|-- dashboard
|-- central-api
|-- ai-dispatcher
|-- market-simulator
|-- production-planner
|-- postgres
|-- redis
`-- nats

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

## Recommended Technology

- Dashboard: Vue 3 + TypeScript + ECharts.
- Central API: Go or Python FastAPI.
- Node agent: Go.
- AI dispatcher: Python FastAPI.
- Message bus: NATS.
- Central database: PostgreSQL.
- Node database: SQLite.
- Cache and short-lived state: Redis.
- Deployment: Docker Compose.

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
