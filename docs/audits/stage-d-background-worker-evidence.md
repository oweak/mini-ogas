# Stage D Dedicated Background Worker Evidence

Verified: 2026-07-15

Branch: `codex/current-stage-hardening`

## Goal

Prevent simulation and periodic transport work from being duplicated when Central API
uses multiple request workers. Preserve the public simulation API while assigning one
formal runtime process to periodic work.

## Reproduced Defects

1. `app/core/lifecycle.py` created simulation, heartbeat-monitor and Outbox tasks in
   every API process. `nats_runtime.start()` also created manager/consumer tasks there.
2. Supervisor and Compose had no dedicated worker, so moving functions alone would
   silently stop periodic behavior.
3. Restored heartbeat facts were marked online regardless of age after removing the
   in-process heartbeat monitor.
4. Central `/health` waited sequentially for Supervisor and the not-yet-started worker.
   The combined wait exceeded the Supervisor health timeout and caused a startup loop.

## Implemented Boundary

- `app/core/lifecycle.py` initializes auth and the request-side publisher connection;
  it never calls `asyncio.create_task`.
- `app/worker.py` is the dedicated process entrypoint. It owns simulation, Outbox,
  NATS manager and NATS consumer tasks and exposes process-bound health evidence.
- Public `/simulation/*` routes retain their URLs, permission checks and environment
  controls, then proxy to the internal worker using the configured service token.
- `DATABASE_AUTO_MIGRATE=false` is mandatory for the worker. Central remains the only
  migration owner in the current deployment until Stage F introduces the explicit
  one-shot migration service.
- Heartbeat projection restore evaluates persisted receipt time. Stale facts restore
  as offline and cannot produce a false-online machine state.
- Central liveness bounds each dependency probe to 250 ms. Readiness degradation is
  still visible through `overall_status`.

## Deployment Evidence

Supervisor TOML parses to 12 processes and contains exactly one `background-worker`.
The accepted runtime reported all 12 healthy in the same session:

```text
ai-dispatcher, background-worker, central-api, dashboard,
grinding-simpy-node, market-simulator, milling-simpy-node,
minio-object-store, nats-server, production-planner,
redis-projection, turning-simpy-node
```

Worker health reported:

```json
{
  "overall_status": "ready",
  "task_owner": "dedicated-process",
  "tasks": {"simulation": "running", "outbox": "running"},
  "nats": {"status": "live", "mode": "shadow"}
}
```

Central `/health` returned `status=ok`, `overall_status=ready` in 195 ms. PostgreSQL
preflight passed and all three production nodes were fresh.

Compose YAML parses with one `background-worker` service using
`uvicorn app.worker:app`; NATS is explicitly started with JetStream. Local Docker CLI
is absent, so clean Compose startup is not claimed by this checkpoint. GitHub
Container Gate `29410060670` passed its clean key-image build-and-smoke job on commit
`3125430`.

## Automated Verification

```powershell
cd 'D:\New project\mini-ogas\services\central-api'
.\.venv\Scripts\python.exe -m pytest tests -q

cd 'D:\New project\mini-ogas'
.\scripts\verify-miniogas.ps1
.\scripts\start-supervisor.ps1 -ReplaceRunning
```

Results:

- Central API: 288 passed.
- Python simulator: 39 passed.
- AI Dispatcher: 4 passed.
- CLI/workflow: 36 passed plus 9 subtests.
- Dashboard: 16 files / 73 tests and production build passed.
- Go Node Agent and Go Supervisor: passed.
- Ruff correctness: passed.
- PostgreSQL Phase 1/3/4/5/6/7 gates: passed.

## Architecture Impact

- Fact source: unchanged; PostgreSQL remains central durable authority and worker
  memory is a process-local execution cache.
- API compatibility: public simulation routes are unchanged.
- Migration: no schema migration was introduced.
- Deployment: one new required process and port (`background-worker`, `8084`).
- Event authority: NATS remains Shadow. This checkpoint does not claim Stage E's one
  formal publishing path because request-side direct publisher calls still exist.

## Remaining Stage D Work

- Extract Production Execution ownership.
- Extract Quality/Calibration ownership.
- Extract Event/Outbox repository/service ownership.
- Extract Runtime Simulation State ownership.
- Isolate Redis/NATS/MinIO adapters from `MemoryStore`.
- Complete duplicate-state deletion and restart proof for every extracted domain.
