# Mini-OGAS Current Stage Baseline

Generated at: 2026-07-15T15:59:20+08:00

Branch: `codex/current-stage-hardening`

Commit under test: `a32652e88e474052a57495e9e4788dfe6f062bfd`

## Objective Scope

This baseline follows the current-stage objective file at
`C:\Users\hq362\.codex\attachments\ebef6c2b-fdcd-4622-9431-6423a50c1802\goal-objective.md`.

The stage objective is not to add new business modules. The current work is limited to
safety, reliability, data consistency, deployment closure, and integration of existing
production, quality, maintenance, telemetry, audit, and AI-assisted capabilities.

## Environment

| Item | Observed value |
| --- | --- |
| OS shell | Windows PowerShell |
| Python | `Python 3.13.6` |
| Node.js | `v24.13.0` |
| npm | `11.6.2` |
| Go | `go version go1.26.4 windows/amd64` |
| GitHub CLI | `gh version 2.93.0 (2026-05-27)` |
| Docker CLI | Not installed / not on PATH |
| Runtime root | `D:\MiniOGAS-VMs` |
| Project root | `D:\New project\mini-ogas` |

## Reproduction Commands

```powershell
cd "D:\New project\mini-ogas"

# Baseline tests and gates
.\scripts\verify-miniogas.ps1 -RequireAiUnlocked

# Runtime ownership path used for the successful run
.\scripts\start-supervisor.ps1 -ReplaceRunning
.\scripts\start-system.ps1 -CheckOnly
```

## Baseline Results

| Gate | Command / evidence | Result |
| --- | --- | --- |
| API contract | `scripts\check_api_contract.py` via `verify-miniogas.ps1` | PASS, 127 backend routes / 27 frontend calls |
| Generated contracts | `tools\export_contracts.py --check` via central-api venv | PASS |
| Dashboard login gate | `scripts\check_dashboard_gate.py` | PASS |
| Secret scan | `scripts\check_secrets.py` | PASS |
| Secret scan tests | `scripts\test_check_secrets.py` | PASS |
| Secret ACL | `scripts\protect-secrets.ps1 -CheckOnly` | PASS, 12 protected targets |
| Central API tests | central-api venv `pytest -q` | PASS, 260 passed |
| Python node simulator tests | `python -m pytest .\test_simulator.py -q` | PASS, 39 passed |
| Go node-agent tests | `go test ./...` | PASS |
| Go supervisor tests | `go test ./...` | PASS |
| AI dispatcher tests | ai-dispatcher venv `pytest .\tests -q` | PASS, 4 passed |
| CLI/workflow tests | `pytest tools\mogas\tests scripts\test_check_secrets.py scripts\test_kali_redteam_workflow.py -q` | PASS, 31 passed + 9 subtests |
| Dashboard tests | `npm run test -- --run` | PASS, 16 files / 73 tests |
| Dashboard production build | `npm run build` | PASS |
| Ruff correctness | central-api venv `ruff check .\services .\scripts .\tools --select F` | PASS |
| Strict runtime check | `.\scripts\start-system.ps1 -CheckOnly` after supervisor start | PASS |
| Phase 1 database gate | `scripts\check_phase1_database.py` | PASS |
| Phase 3 execution gate | `scripts\check_phase3_execution.py` | PASS |
| Phase 4 material flow gate | `scripts\check_phase4_material_flow.py` | PASS |
| Phase 5 quality gate | `scripts\check_phase5_quality.py` | PASS |
| Phase 6 maintenance gate | `scripts\check_phase6_maintenance.py` | PASS |
| Phase 7 data platform gate | `scripts\check_phase7_data_platform.py` | PASS |

## Runtime Evidence

The successful runtime path is `start-supervisor.ps1 -ReplaceRunning`, followed by
`start-system.ps1 -CheckOnly`.

Supervisor reported 11 healthy processes:

| Process | State |
| --- | --- |
| `nats-server` | healthy |
| `redis-projection` | healthy |
| `minio-object-store` | healthy |
| `central-api` | healthy |
| `ai-dispatcher` | healthy |
| `market-simulator` | healthy |
| `production-planner` | healthy |
| `dashboard` | healthy |
| `turning-simpy-node` | healthy |
| `milling-simpy-node` | healthy |
| `grinding-simpy-node` | healthy |

Strict runtime check confirmed:

- Redis authenticated `PING` and append-only persistence.
- MinIO health endpoint returned HTTP 200.
- Central API port 8080 was listening and matched the launch session.
- Telemetry projection provider was `redis`, authority was `postgresql-historian`,
  and an active generation was present.
- AI runtime was live through API source, provider `deepseek`, model `deepseek-v4-pro`.
- Dashboard process was listening on port 5173.
- 3/3 production SimPy nodes were connected.

## Reproduced Failures and Root Causes

### P0-B1 Node token command-creation authorization bypass

Problem:

- The legacy `/agents/{node_code}/commands` route was classified as a node-agent
  channel and could create a production command when called with the node ingest token.
- Because the route carried a path `node_code`, a compromised node token could target a
  different node.

Root cause:

- The route lacked a `command:issue` authorization dependency and relied on the
  broad node-ingest middleware classification for all `/agents/*` paths.

Impact:

- The system retained an ungoverned command creation path outside the operator
  `/ops/agents/{node_code}/commands` gateway.

Resolution evidence:

- `create_agent_command` now depends on `require_permission(PERM_COMMAND_ISSUE)`.
- Node-agent actors do not have `command:issue`, so node tokens receive 403.
- `tests/test_auth_rbac.py::test_node_ingest_token_cannot_create_cross_node_command`
  verifies no command is created or left pending.
- Smoke tests now issue commands through the `/ops` operator gateway and keep
  node-agent endpoints for claim/result only.
- `.\services\central-api\.venv\Scripts\python.exe -m pytest tests/test_auth_rbac.py tests/test_smoke.py -q`:
  57 passed.

### P0-B2 Dashboard data-quality encoding and build failure

Problem:

- `services/dashboard/src/dataQuality.ts` contained corrupted Chinese string literals
  and private-use Unicode characters.
- `npm run build` failed with TypeScript parse errors.

Root cause:

- The file was rewritten through a non-UTF-8-safe path, corrupting string delimiters
  and labels.

Impact:

- Dashboard production build could not complete.

Resolution evidence:

- `services/dashboard/src/dataQuality.ts` and `services/dashboard/src/dataQuality.test.ts`
  now have no BOM and no private-use or replacement characters.
- `npm test`: 16 files / 73 tests passed.
- `npm run build`: production build passed.

### P0-B7 Phase 5 gauge calibration time fixture failure

Problem:

- Central API tests had 8 failures in `tests/test_phase5_quality.py`.
- Valid gauges were rejected with `GAUGE_CALIBRATION_INVALID`.

Root cause:

- The fixture generated gauge validity from `datetime.now(UTC)` while measurement
  events were hardcoded at `2026-07-14T00:00:00+00:00`.
- On 2026-07-15, the measurement time fell before `valid_from`.

Impact:

- Failed inspections could not create measurements, nonconformances, dispositions,
  CAPA, evidence, or rollback coverage.

Resolution evidence:

- The test now uses a single controlled `P5_EVENT_TIME` / `P5_EVENT_AT` clock.
- `.\services\central-api\.venv\Scripts\python.exe -m pytest tests/test_phase5_quality.py -q`:
  9 passed.
- Full central-api test suite after the packaging dependency regression test was
  added: 260 passed.

### P0-B3 Central API runtime dependency declaration and interpreter path

Problem:

- `app/store.py` directly imports `psutil`, but the package was absent from
  `services/central-api/requirements.txt`.
- `start-system.ps1` also started central-api with global `python`; global Python did
  not have `redis` installed, causing central-api startup failure.

Root cause:

- The dependency manifest did not match the direct runtime import graph.
- The script did not use the service virtual environment even for dependencies that
  were declared in `services/central-api/requirements.txt`.

Impact:

- Port 8080 did not listen through the local start path.
- Strict runtime check failed before Supervisor ownership was used.

Resolution evidence:

- `requirements.txt` now pins `psutil==7.1.3`.
- `test_direct_runtime_dependencies_are_declared_for_clean_install` prevents the
  direct `psutil` dependency from being dropped from the production manifest.
- `start-system.ps1` now resolves service venv Python through `Get-ServicePython`.
- Central API and microservice uvicorn commands use their service `.venv` Python.
- After `start-supervisor.ps1 -ReplaceRunning`, `start-system.ps1 -CheckOnly` passed.
- Full `verify-miniogas.ps1 -RequireAiUnlocked` passed.

### P0-B4 Central API Dockerfile runtime module coverage

Problem:

- Central API Dockerfile copied `app/` and `requirements.txt`, but omitted
  service-level runtime helpers used for vault/bootstrap/portable service flows.

Root cause:

- The Dockerfile only modeled the direct uvicorn package entrypoint.

Impact:

- A clean container image would not contain every central-api service runtime helper.

Resolution evidence:

- `services/central-api/Dockerfile` now copies `ai_runtime.py`,
  `create_ai_vault.py`, and `run_portable.py`.
- Docker CLI is not present on this host, so image build remains unverified here.

### P0-B5 Node Agent Dockerfile direct-import module coverage

Problem:

- `services/node-agent/simulator.py` directly imports `event_publishers` and
  `runtime_adapters`, but the Dockerfile copied only `simulator.py`.

Root cause:

- The Dockerfile did not match the simulator's local import graph.

Impact:

- A clean Node Agent container would start with `ModuleNotFoundError`.

Resolution evidence:

- `services/node-agent/Dockerfile` now copies `event_publishers.py`,
  `runtime_adapters.py`, and `agent.py`.
- The image now installs `simpy==4.1.1` and `psutil==7.1.3`.
- Static import audit confirmed `simulator.py` local imports are covered.
- Docker CLI is not present on this host, so image build remains unverified here.

### P0-B6 illegal environment enum handling

Problem:

- The stage objective explicitly requires `APP_ENV=dev` and other illegal aliases
  not to be silently accepted.

Root cause:

- Existing `Settings` uses Literal validation, but there was no explicit regression
  test for the common invalid alias `dev`.

Impact:

- Future edits could reintroduce silent alias coercion.

Resolution evidence:

- `tests/test_environment_config.py::test_app_env_alias_dev_is_rejected_instead_of_silent_coercion`
  now asserts `Settings(app_env="dev")` raises `ValidationError`.
- `.\services\central-api\.venv\Scripts\python.exe -m pytest tests/test_environment_config.py -q`:
  11 passed, including the runtime dependency manifest regression.

### P0-B8 status-document alignment

Problem:

- `CODEX_ISSUES.md` and `PROJECT_STATUS.md` still reported the 2026-07-13 test
  counts and an eight-process runtime.
- `PROJECT_STATUS.md` stated that Redis and NATS were inactive even though the
  verified Supervisor runtime owned Redis, NATS, MinIO and 11 total processes.
- The README mixed the current NATS Shadow path with a future Redis claim.

Root cause:

- Status documents were not updated atomically with runtime, verifier and deployment
  changes.

Impact:

- A reader could mistake old process counts and transport boundaries for current
  deployment evidence.

Resolution evidence:

- `README.md`, `PROJECT_STATUS.md`, `CODEX_ISSUES.md` and this baseline now use the
  same 2026-07-15 test counts and runtime boundaries.
- All four documents explicitly state that PostgreSQL is authoritative, Redis is a
  rebuildable projection, NATS is Shadow, and Docker/Compose remains unverified.

## Known Remaining Gaps

### Docker / Compose clean build is not verified

Evidence:

- `docker --version` failed because Docker CLI is not installed or not on PATH.

Impact:

- Stage A clean Docker/Compose build and startup remains unproven in the current
  Windows environment.
- The system must not claim container deployment is available from this baseline.

Next action:

- Install or expose Docker CLI, then run explicit Central API, Node Agent, Dashboard,
  and Compose build/start checks.
- Alternatively, document this machine as a non-Docker runtime and run the Docker
  gate on another host.

### Deployment path consistency is not complete

Evidence:

- `start-supervisor.ps1 -ReplaceRunning` successfully starts the full 11-process
  runtime including NATS, Redis, MinIO, central-api, AI, dashboard, and nodes.
- `start-system.ps1` can start API/microservices with service venvs, but it does
  not itself own Redis/MinIO/NATS startup.
- `config/supervisor.toml` still runs the Dashboard through Vite dev server.

Impact:

- Supervisor is the proven one-click runtime path for the full system.
- Compose and Dashboard production-container runtime are not yet aligned with the
  same truth table.

Next action:

- Phase F must unify Supervisor, Compose, Dockerfiles, startup scripts, and README.
- Dashboard container/runtime must use production build before claiming container
  deployment readiness.

## Current Status

Stage A has a real baseline with code tests and local Supervisor runtime passing.
Stage B P0 items 1 through 8 have been reproduced and corrected in source, tests or
canonical status documents. P0-B4/B5 still require Docker CLI for real image-build
and startup proof, so the Stage B acceptance gate is not yet closed.

The full current-stage goal is not complete. Remaining work starts with Docker/Compose
clean-build verification on a Docker-capable host. After that gate passes, execution
continues with the identity/control plane and `MemoryStore` decomposition.
