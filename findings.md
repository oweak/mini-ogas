# Findings: v2.2 First-Stage Completion

## Evidence Baseline
- Previous implementation added a selectable persistence backend, but the local runtime has no reachable PostgreSQL service, no `psql`, and no Docker executable. Its current configuration remains memory mode with SQLite fallback disabled for normal persistence.
- The repository contains v2.2 contracts and a SimPy implementation, but code presence must be distinguished from a working end-to-end pipeline.
- The project worktree is intentionally dirty. Audit work must identify changes before editing and avoid reverting unrelated files.

## Audit Method
For each v2.2 requirement, record: source contract, implementation location, configuration path, automated test, and runtime evidence. A missing one means the requirement remains open.

## Scope and Contract Boundary
- The requested first stage is `v2.2.0` through `v2.2.10`: contracts, heartbeat v2, dashboard runtime display, snapshot adapter, deterministic SimPy, three-process WIP flow, read-only rules, LLM explanation, command polling, part queue, and PostgreSQL shadow write.
- PostgreSQL is explicitly a shadow-write target in v2.2.10. Promoting it to the primary source of truth belongs to v2.5, so v2.2 completion requires real shadow persistence and consistency checks, not an unsafe premature read-path switch.
- Core scope: `services/central-api/app`, `services/node-agent`, and `services/dashboard/src`; deployment/configuration files are integration dependencies.

## Diagnosis Report (2026-06-22)

### Verified working in isolation
- `central-api`: 55 tests passed.
- `node-agent`: 22 tests passed.
- `dashboard`: 56 tests passed and production build passed.
- `/api/*` is intentionally compatibility-normalized by security middleware to root routes, so `/api/node-heartbeats` and `/api/dashboard/snapshot` are not broken merely because the FastAPI route table shows root paths.

### Blocking findings
1. **[HIGH] Runtime absent.** No central API, dashboard, or node-agent process is listening on configured ports. Historical log output is not runtime evidence.
2. **[HIGH] Agent-to-host dispatch is incomplete.** `simulator.py` calls `/api/node-dispatches/{node}` but central-api has no matching handler. This violates SIM-003 because `active_order` falls back to a local default instead of a host-issued dispatch.
3. **[HIGH] Local-record recovery is incomplete.** `simulator.py` calls `/api/node-records/sync`, but central-api has no matching handler. Existing logs show repeated 405 responses, so queued local records are never acknowledged.
4. **[HIGH] PostgreSQL shadow-write stage is not complete.** No local PostgreSQL service, Docker executable, or `psql` client exists. The launch script currently forces `PERSIST_ENABLED=true` with a SQLite database path and no PostgreSQL DSN. No real PG-001 through PG-004 evidence exists.
5. **[HIGH] Heartbeat shadow data is insufficient for PG-004.** Current persistence stores derived metrics but not a raw heartbeat record containing `run_id`, `scenario_id`, and `simulation_time`; therefore a replay-ready shadow record cannot be proven.
6. **[MED] Stage tests have an integration gap.** Unit tests do not launch the actual central API plus three agents and assert dispatch, local-record acknowledgement, command verification, snapshot truth, and persistence consistency together.

### Root-cause confirmation
- Compatibility prefix behavior is confirmed in `security_middleware`, which strips `/api` before routing. It is not the source of the 405/404 log records.
- The missing node-records and node-dispatch routes are confirmed absent from central-api router declarations while the node agent calls them every polling cycle.
- Persistence is selected dynamically, but no PostgreSQL endpoint is configured or reachable; startup explicitly supplies only `CENTRAL_DB_PATH`, yielding SQLite.
## PostgreSQL Provisioning Attempts
| Attempt | Result | Next approach |
|---|---|---|
| Winget unattended installer | Timed out while installer remained active; binaries appeared but service/data were absent | Avoid waiting on the same installer state |
| Direct initdb from partial install | Failed because `$libdir/dict_snowball` was missing; initdb cleaned its incomplete data directory | Complete the package install with a component-minimal unattended invocation or use a verified complete distribution |

## Completion Evidence (2026-06-22)
- Native PostgreSQL 16 is running as Windows service `miniogas-postgresql-16`; application credentials are stored outside the repository in `D:\MiniOGAS-VMs\postgres.env` with user-only ACLs.
- The launcher now requires `POSTGRES_DSN` and launches central-api with `PERSIST_BACKEND=postgres`.
- Strict startup completed with: 3/3 live SimPy nodes, snapshot `data_source=live`, strict DeepSeek smoke `source=api`, and PostgreSQL persistence `status=ok`.
- An actual low-risk command completed `pending -> executed -> verified`, with the agent heartbeat reporting target rate `0.72`.
- PostgreSQL consistency report returned `ok` with zero heartbeat, command, and part-queue mismatches.
- The API contract checker now scans the actual modular router tree and passed for all current frontend API calls.

## Post-Acceptance Scope (2026-06-22)
- Frontend VirtualBox residue spans `App.vue`, `types.ts`, `useStartupWorkflow.ts`, `FactoryRuntimeView.vue`, runtime presentation helpers, and associated tests.
- The store registers five logical nodes, while runtime acceptance expects only three production heartbeat agents. The correct repair must make expected-agent counting explicit rather than remove cloud coordination/data nodes.
- Microservice clients exist but `MICROSERVICES_ENABLED` defaults to false. Startup, health checks, and fallback semantics must be inspected before enabling them.
- Authentication uses shared static tokens and in-memory role maps. Any JWT/RBAC repair crosses configuration, middleware, login endpoints, persistence schema, and dashboard token handling.
- Three root-level `VirtualBoxVM` log files are stale artifacts and can be removed after code references are eliminated.

## Post-Acceptance Remediation Evidence (2026-06-22)
- **VirtualBox residue:** Removed VirtualBox state, VM fields, and startup handling from the dashboard source and tests. A targeted source scan returns zero remaining `VirtualBox`, `virtualbox`, `vm_name`, or `vm_running` references. Kali remains an isolated optional red-team asset in the launcher, not a production dashboard dependency.
- **Production-node contract:** `EXPECTED_PRODUCTION_NODES` now explicitly declares the three heartbeat-producing workshops. The snapshot reports `nodes_expected=3`, while separately reporting five registered logical topology nodes, so cloud coordination/data nodes are retained without corrupting production availability.
- **Microservice activation:** `MICROSERVICES_ENABLED` defaults to true. The one-command launcher starts `ai-dispatcher`, `market-simulator`, and `production-planner` before central-api, waits for their session-bound health endpoints, and central-api reports all three online. Docker Compose now declares all three with internal URLs.
- **JWT/RBAC:** PostgreSQL now contains persistent `users`, `roles`, `permissions`, `user_roles`, and `role_permissions` tables. Passwords use salted PBKDF2-SHA256 hashes; successful administrator login issues a time-limited HS256 bearer JWT. Browser requests no longer use `X-OGAS-Token`; that header is reserved for node/service credentials. Runtime proof: one user, three roles, one user-role relation, and thirteen role-permission relations persisted; old browser machine-token snapshot requests return HTTP 401.
- **AI dispatcher proof:** A real, controlled dispatcher diagnosis returned `source=deepseek` with root-cause and recommended-action fields. This is in addition to the live AI runtime proof used by central-api.
- **Artifact cleanup:** All three root-level `VirtualBoxVM` log files were deleted; a root scan returns zero matches.

## Legacy Consolidation Evidence (2026-06-22)
- The unused root-level `services/central-api/main.py`, `config.py`, helper modules, and their root-level tests were removed. Docker, portable startup, and all supported launch scripts now resolve the modular `app.main` application.
- The obsolete generic VirtualBox production-node deployment scripts were removed. The only retained VirtualBox integration is the optional Kali red-team VM path in `scripts/start-system.ps1 -StartKali`; it is deliberately outside the production node/dashboard boundary.
- `scripts/start-all.ps1` now delegates to `start-system.ps1`, preventing a second launcher from starting five old node agents with legacy authentication assumptions.
- Final targeted scans report no legacy VirtualBox/node-count identifiers in production API, dashboard, or microservice source. The legacy central files and generic VM deployment entrypoints do not exist.

## Runtime Freshness and Dashboard Evidence (2026-06-22)
- Central API and all three microservices now publish `session_token`, `process_id`, and `process_started_at` from `/health`.
- `mogas up --all` delegates to the strict launcher with its generated session token, then rejects a health response unless the returned session, PID, and start-time proof are valid. A real run printed the new central API PID and UTC start time.
- A Playwright browser login against the live dashboard verified `3/3` in the operating summary, heartbeat service row, and parent-child evidence panel. The same page showed `data_source=live` and `simulation_engine=simpy`.

## Dispatcher Provider Chain Evidence (2026-06-23)
- `ai-dispatcher` now reads `AI_PROVIDER_CHAIN` and attempts DeepSeek, Ollama, LM Studio, and Groq in configured order before returning an explicit `local-fallback` result.
- Diagnosis output records `source`, `attempted_providers`, and bounded `provider_errors`; central-api continues to persist the serving source without any route-contract change.
- Unit tests prove next-provider fallback after a simulated DeepSeek outage and local-rule fallback only after all providers fail.
- A real runtime probe reported the configured chain and returned a DeepSeek diagnosis with non-empty root cause and recommended action.
