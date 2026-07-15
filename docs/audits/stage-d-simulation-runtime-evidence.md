# Stage D Runtime Simulation State Evidence

Verified: 2026-07-15

Branch: `codex/current-stage-hardening`

## Goal

Give volatile simulation control and progress one explicit, independently testable
owner inside the dedicated background worker. Prevent `MemoryStore` from retaining
eight parallel state fields that could drift or be modified outside the runtime lock.

## Reproduced Defect

`MemoryStore` directly owned the deterministic random source plus running, tick,
speed, anomaly rate, last-tick time and generated-item counters. The fields were
mutated independently and the ownership audit classified each one separately. Moving
the loop to a dedicated process removed duplicate execution, but did not yet create a
single simulation-state boundary.

## Implemented Boundary

- `RuntimeSimulationState` owns the lock, deterministic random source, operator
  configuration and volatile progress counters.
- A whole simulation step runs under one reentrant operation lock. Configuration,
  snapshots and generated-item counters use the same owner.
- `MemoryStore` retains compatibility read properties only. The three configuration
  setters delegate to validated `configure()`; progress fields cannot be written
  through the facade.
- `seed_demo()` resets volatile progress without silently persisting or restoring a
  running simulation. PostgreSQL remains the authority for durable production facts;
  worker restart intentionally returns the simulation clock to a stopped zero state.
- The generated ownership map now inventories 34 instance fields and records only
  `simulation_runtime` as the simulation field owned by `MemoryStore`.

## Automated Verification

```powershell
cd 'D:\New project\mini-ogas\services\central-api'
.\.venv\Scripts\python.exe -m ruff check `
  app\domain\simulation.py app\store.py `
  tests\test_simulation_runtime_state.py `
  tests\test_memory_store_ownership_map.py --select E9,F,I
.\.venv\Scripts\python.exe -m pytest tests -q

cd 'D:\New project\mini-ogas'
.\services\central-api\.venv\Scripts\python.exe `
  tools\memory_store_ownership.py --check
.\scripts\start-supervisor.ps1 -ReplaceRunning
.\scripts\check-runtime-status.ps1
```

Results:

- Ruff selected correctness/import checks: passed.
- Central API: 292 passed.
- Ownership map generation and committed-map check: passed.
- Supervisor runtime: 12/12 processes healthy in one session.
- Worker health: `simulation=running`, `outbox=running`, task owner
  `dedicated-process`, NATS `live` in Shadow mode.
- Production nodes: 3/3 online with fresh heartbeats.
- PostgreSQL preflight and live DeepSeek provider smoke: passed.
- Authenticated public simulation step: tick observed as `0 -> 1 -> 1` across
  before/step/after requests.
- Direct worker simulation request without the internal token: HTTP 401.

## Architecture Impact

- Fact source: unchanged. PostgreSQL remains central durable authority; runtime
  simulation progress is explicitly volatile and rebuildable.
- API compatibility: public `/simulation/state`, `/simulation/control` and
  `/simulation/step` routes are unchanged.
- Migration: no database migration was introduced.
- Deployment: no new process or port beyond the already accepted dedicated worker.
- Event authority: unchanged. NATS remains Shadow and Stage E's unique publisher gate
  is not claimed here.

## Remaining Stage D Work

- Production Execution and Quality/Calibration ownership is closed by
  `docs/audits/stage-d-execution-quality-evidence.md`.
- Extract Event/Outbox service ownership and isolate Redis/NATS/MinIO adapters from
  the compatibility facade.
- Prove restart behavior for every remaining extracted domain.
