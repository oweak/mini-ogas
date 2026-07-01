# Go Supervisor Runtime

## Purpose

`services/supervisor` is the long-running process supervisor for the local
Mini-OGAS runtime. In v2.5 it becomes the preferred runtime owner. The older
`scripts/start-system.ps1` path remains available as an explicit fallback, not
a second controller that should run beside it.

The supervisor owns these eight processes:

1. `central-api`
2. `ai-dispatcher`
3. `market-simulator`
4. `production-planner`
5. `dashboard`
6. `turning-simpy-node`
7. `milling-simpy-node`
8. `grinding-simpy-node`

The configuration in `config/supervisor.toml` uses the same three SimPy node
identities, random seeds, scenario IDs, PostgreSQL central-store settings, and
heartbeat token boundary as the current script-managed runtime.

## Health Contract

HTTP services are healthy only when `/health` returns all of the following:

- `status: "ok"`
- the supervisor launch session in `session_token`
- a positive `process_id`
- an RFC3339 `process_started_at`

This rejects stale listeners left behind by an earlier launch. Node simulators
and the Vite dashboard are configured with `type = "process"`: they do not
expose the Mini-OGAS session-aware `/health` proof, so the supervisor tracks
their child-process lifecycle instead of treating a generic HTTP page as a
trusted health source.

## Start And Ownership

Build and launch through the wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-miniogas.ps1
```

The wrapper reads the existing local runtime token, PostgreSQL DSN, and auth
configuration without printing them. It creates a new launch session and
builds `miniogas-supervisor.exe` into `.runtime\bin`.

For safety, the wrapper refuses to start while the regular Mini-OGAS service
ports are already owned by `start-system.ps1`. To transfer ownership to the
supervisor, first ensure that replacing the current processes is intended and
then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-miniogas.ps1 -ReplaceRunning
```

Use the legacy script-managed path only when you need the old lightweight
launcher or a check-only run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-miniogas.ps1 -UseScriptLauncher
powershell -ExecutionPolicy Bypass -File .\scripts\start-miniogas.ps1 -CheckOnly -RequireAiApi
```

The management API is available at:

```text
GET  http://127.0.0.1:9099/supervisor/status
POST http://127.0.0.1:9099/supervisor/restart/{process-name}
POST http://127.0.0.1:9099/supervisor/stopall
```

`restart/{process-name}` performs a real replacement. The retired child gets a
new generation number before cancellation, preventing its old monitor from
restarting it after the replacement is active.

## Verification

Run the Go test suite with project-local Go caches:

```powershell
$env:GOMODCACHE = "$PWD\.runtime\go\modcache"
$env:GOCACHE = "$PWD\.runtime\go\buildcache"
& "C:\Program Files\Go\bin\go.exe" test .\services\supervisor\...
```

The tests cover strict health-proof validation, configuration validation and
environment expansion, process-mode monitoring, and a real manual restart with
a changed child PID.
