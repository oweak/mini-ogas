# Mini-OGAS Current Stage Baseline

Generated at: 2026-07-15T17:51:24+08:00

Branch: `codex/current-stage-hardening`

Commit under test: `78b994d838fc595e97fa1e936c631ea3849133a4`

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
| API contract | `scripts\check_api_contract.py` via `verify-miniogas.ps1` | PASS, 134 backend routes / 27 frontend calls |
| Generated contracts | `tools\export_contracts.py --check` via central-api venv | PASS |
| Dashboard login gate | `scripts\check_dashboard_gate.py` | PASS |
| Secret scan | `scripts\check_secrets.py` | PASS |
| Secret scan tests | `scripts\test_check_secrets.py` | PASS |
| Secret ACL | `scripts\protect-secrets.ps1 -CheckOnly` | PASS, 12 protected targets |
| Central API tests | central-api venv `pytest -q` | PASS, 273 passed |
| Python node simulator tests | `python -m pytest .\test_simulator.py -q` | PASS, 39 passed |
| Go node-agent tests | `go test ./...` | PASS |
| Go supervisor tests | `go test ./...` | PASS |
| AI dispatcher tests | ai-dispatcher venv `pytest .\tests -q` | PASS, 4 passed |
| CLI/workflow tests | `pytest tools\mogas\tests scripts\test_check_secrets.py scripts\test_kali_redteam_workflow.py -q` | PASS, 32 passed + 9 subtests |
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
- Three distinct 64-character node credentials were loaded and bound to the expected
  `turning`, `milling`, and `grinding` node codes.
- PostgreSQL contained the Principal and AI-suggestion migrations; all active node
  credential hashes matched the protected runtime ledger.
- A live high-risk AI Agent suggestion persisted as `pending_human_review`, command
  count did not change, and the revoked test credential subsequently returned 401.

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
- Full central-api test suite after packaging, Principal, command-control, credential
  and node-inventory regressions were added: 273 passed.

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
- GitHub Container Gate `29406148599` built the clean image and started Central API;
  `/health` passed on an Ubuntu runner.

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
- GitHub Container Gate `29406148599` built the clean image, started Node Agent and
  observed its authenticated SimPy heartbeat through Central API.

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
  rebuildable projection, NATS is Shadow, key images are clean-build verified, and
  full Compose startup remains unverified.

## Stage C Identity and Control Acceptance

Implemented boundary:

- `Principal` covers human, service, node and AI Agent identities in PostgreSQL.
- Opaque credentials are hash-only at rest and support issue, rotate and revoke.
- Production startup rejects missing, duplicate, short or placeholder node credentials
  and disables legacy shared-node authentication by default.
- Node credentials are bound to `node_code`; node telemetry and command claim/result
  access cannot cross that resource boundary.
- `CommandControlService` owns target-rate issue and command approve/reject/cancel/retry
  operations. Each path evaluates authenticated Principal, permission, resource,
  Safety Governor, approval policy and audit.
- AI Agent suggestions are persisted separately from commands. High/critical advice is
  held for human review and cannot create or approve a production command.

Verification evidence:

- `docs/security/principal-control-matrix.md` maps every sensitive action to its
  Principal type, permission, resource rule, safety rule, approval and audit event.
- Central API full suite: 273 passed.
- Strict runtime: 3/3 independently authenticated nodes online.
- Live PostgreSQL query: both Stage C migrations present, three active expected node
  credentials, three unique hashes matching the protected runtime ledger.
- Live AI test: high-risk suggestion recorded as `pending_human_review`, no command
  created, credential revocation enforced with HTTP 401.
- Phase 7 created and revoked its own temporary node Principal while retaining
  idempotent ingest, Redis rebuild and PostgreSQL historian proof.

Stage C is accepted. This does not accept Stage G: AI Dispatcher still must become the
sole model provider-chain owner.

## Known Remaining Gaps

### Key container images are verified; full Compose startup is not

Evidence:

- `docker --version` still fails locally because Docker CLI is not installed or on PATH.
- GitHub Actions run `29406148599` on commit `6bf01f1` built Central API, Node Agent
  and Dashboard from clean contexts, started all three, verified Central API health,
  observed a real Node Agent heartbeat and served the Nginx production Dashboard.
- `docker compose ... config --quiet` passed in that run; full Compose services were
  not started together.

Impact:

- Stage A now has independent key-image build/start evidence.
- Full Compose parity, PostgreSQL/NATS/Redis/MinIO container integration and one-shot
  migration remain unproven.

Next action:

- Stage F must extend the gate to start the complete Compose component set and prove
  migration, readiness, persistence and shutdown behavior.

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
Stage B P0 items 1 through 8 have been reproduced, corrected and verified. B4/B5 are
proven by clean GitHub Container Gate run `29406148599`; the Stage B gate is closed.

Stage C is accepted with persisted Principal identities, independent node credentials,
canonical command governance, AI suggestion isolation and live rotation/revocation
proof.

The full current-stage goal is not complete. Execution now continues with Stage D
`MemoryStore` ownership mapping and incremental Command/Node extraction. Full Compose
parity remains explicitly assigned to Stage F.

## Stage D Checkpoint - 2026-07-15

This checkpoint supplements the immutable Stage A baseline above; it does not rewrite
the earlier commit-specific counts.

- The generated `memory-store-ownership-map.md` is current and guarded by a test.
- Command and Node repositories own their durable SQL/projections and have restart and
  transaction regressions.
- API lifespan creates no periodic tasks. A single `background-worker` owns simulation,
  Outbox publication and the NATS Shadow consumer/manager.
- Supervisor starts 12 processes and Compose registers the same worker image/entrypoint;
  complete Compose runtime parity remains unproved on this host.
- The startup dependency cycle caused by blocking readiness probes was reproduced and
  fixed. Central `/health` returned in 195 ms in the accepted runtime.
- Official verification passed: Central 288, simulator 39, AI Dispatcher 4,
  CLI/workflow 36 plus 9 subtests, Dashboard 73 plus production build, both Go suites,
  Ruff correctness and the Phase 1/3/4/5/6/7 PostgreSQL gates.
- Runtime evidence: 12/12 healthy processes, worker tasks `simulation=running` and
  `outbox=running`, NATS `live` in Shadow mode, PostgreSQL persistence pass and 3/3
  fresh SimPy production nodes.

Runtime Simulation State was subsequently extracted into one locked owner in the
dedicated worker. The ownership inventory is now 34 fields / 132 methods, Central API
passes 292 tests, authenticated public stepping produced `0 -> 1 -> 1`, and direct
unauthenticated worker access returned 401.

Stage D remains open for Production Execution, Quality/Calibration, Event/Outbox and
Redis/NATS/MinIO adapter extraction. Stage E remains open for the single formal
publisher and reconciliation thresholds.
