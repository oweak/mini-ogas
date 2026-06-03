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
├─ dashboard
├─ central-api
├─ ai-dispatcher
├─ market-simulator
├─ production-planner
├─ postgres
├─ redis
└─ nats

workshop-node
├─ node-agent
├─ local sqlite database
├─ metrics collector
├─ production simulator
└─ script fix engine
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

## Current Code Skeleton

The repository now contains minimal runnable service skeletons:

- `services/central-api`: FastAPI central control API.
- `services/ai-dispatcher`: FastAPI DeepSeek diagnosis gateway with local fallback.
- `services/market-simulator`: FastAPI virtual market signal generator.
- `services/production-planner`: FastAPI rule-based production planner.
- `services/node-agent`: Go workshop node agent.
- `services/dashboard`: Vue 3 dashboard.

## Local Development

Recommended one-command workflow from the project root:

```powershell
.\scripts\setup-dev.ps1
.\scripts\verify-dev.ps1
.\scripts\start-all.ps1
```

See `docs/development-environment.md` for the local D-drive tool layout.
See `docs/project-structure.md` for file ownership and future coding rules.
Open the prepared VS Code workspace:

```powershell
.\scripts\open-vscode.ps1
```

Central API:

```powershell
cd services/central-api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

Dashboard:

```powershell
cd services/dashboard
npm install
npm run dev
```

Node agent:

```powershell
cd services/node-agent
$env:NODE_CODE="turning-workshop-01"
$env:CENTRAL_API_URL="http://localhost:8080"
go run ./cmd/node-agent
```

Docker Compose central stack:

```powershell
docker compose -f deploy/docker-compose.central.yml up --build
```

## Demo Mode

For a quick interview demo without databases or cloud servers:

```powershell
.\scripts\start-central-api.ps1
```

Open another terminal:

```powershell
.\scripts\start-dashboard.ps1
```

Then visit:

```text
http://127.0.0.1:5173
```

The dashboard includes buttons for normal state, common fault, complex AI
diagnosis, hostile attack isolation, and market demand shift.

## Repository Layout

```text
mini-ogas/
├─ services/
│  ├─ central-api/
│  ├─ ai-dispatcher/
│  ├─ dashboard/
│  ├─ market-simulator/
│  ├─ node-agent/
│  └─ production-planner/
├─ scripts/
├─ database/
├─ deploy/
├─ docs/
└─ README.md
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
