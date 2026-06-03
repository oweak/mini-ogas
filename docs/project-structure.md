# Mini-OGAS Project Structure

This document defines where new code should go as the system grows.

## Root

```text
mini-ogas/
  services/       Runtime services: API, dashboard, node agent, simulators
  scripts/        Development, startup, verification, and repair scripts
  database/       SQL schema and database initialization files
  deploy/         Docker Compose and deployment environment examples
  docs/           Architecture, operations, and interview explanation docs
  tools/          One-off local builders and data inspection utilities
  .runtime/       Local SDKs, caches, binaries, and generated runtime files
```

`.runtime/` is local-only and should not be committed.

## Central API

```text
services/central-api/
  app/
    main.py          FastAPI app factory and router registration only
    models.py        Pydantic request/response/domain models
    store.py         In-memory demo store and simulation engine
    core/            Settings and application lifecycle
    routers/         HTTP API groups by business domain
    tests/           Smoke tests and future API tests
```

Router ownership:

- `routers/health.py`: health and dashboard summary
- `routers/nodes.py`: nodes, metrics, topology, isolation and recovery
- `routers/production.py`: inventory and production plans
- `routers/market.py`: market signals and forecasts
- `routers/ai.py`: AI diagnosis records
- `routers/audit.py`: alerts, commands, incidents, audit logs
- `routers/simulation.py`: realtime simulation control
- `routers/demo.py`: stable interview/demo scenarios

## Dashboard

```text
services/dashboard/src/
  App.vue           Current management console shell and pages
  main.ts           Vue application bootstrap
  style.css         Current global UI style system
  api/              HTTP client and future API modules
  config/           Navigation and page configuration
  types/            Shared TypeScript domain types
```

When adding new frontend logic:

- Put reusable API request code in `src/api/`.
- Put stable data structures in `src/types/`.
- Put navigation/page metadata in `src/config/`.
- Keep `App.vue` for page composition until the next larger split into `pages/` and `components/`.

## Node Agent

```text
services/node-agent/
  cmd/node-agent/       Process entrypoint
  internal/config/      Environment and runtime config
  internal/metrics/     Metric collection and local repair decisions
  internal/centralapi/  Central API HTTP client
```

The node agent should stay lightweight because it is intended to run on low-end 2C4G cloud nodes.

## Verification

Run from project root:

```powershell
.\scripts\verify-dev.ps1
```

The verification script checks:

- Python service imports/compilation
- Vue + TypeScript dashboard build
- Go node-agent build
