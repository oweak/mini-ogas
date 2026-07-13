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

## Full-System Audit Baseline (2026-07-10)
- Repository history is small and recent: 17 commits from 2026-06-04 through 2026-07-06 on one branch. The highest code hotspot is `services/central-api/app/store.py`; it also appears in bug-fix commits, making it the primary architecture risk.
- Production-owned source totals roughly 25,000 lines: central-api 11,213 lines, dashboard 10,408, node-agent 2,243, supervisor 814, and three Python microservices about 508 combined. Central API state/orchestration and the dashboard dominate complexity.
- The worktree was clean at audit start. No supported service was listening during the first runtime probe, so older live-runtime claims are historical evidence rather than proof of current availability.
- Current documentation and configuration disagree in material ways: root `.env.example` sets `MICROSERVICES_ENABLED=false`, while supervisor config forces it true; README describes Redis and NATS as architecture components although no active implementation was found in the source inventory.
- Root reports contain stale and encoding-damaged sections. Status documents must be regenerated from code/runtime evidence after remediation, not treated as implementation truth.
- Supported runtime ports are 8080/8081/8082/8083/5173 and supervisor 9099 according to `config/supervisor.toml`; the initial legacy-port probe was therefore invalid and will be repeated against configured ports.
- Architecture boundary to verify: PostgreSQL is required as the central persistence backend, SQLite is permitted only for node-local/explicit fallback use, and in-memory state must not silently remain the authoritative read path for durable operational facts.

## Automated Verification Baseline (2026-07-10)
- Passed: central-api 102 tests, dashboard 60 tests, dashboard production build, Python simulator 22 tests, ai-dispatcher 4 tests, script suite 17 tests plus 9 subtests, and `mogas` CLI 13 tests.
- Passed after explicitly using the repository-local Go cache: Go node-agent packages and Go supervisor packages. Direct `go test ./...` fails on this machine because the default `C:\Users\hq362\go` cache is not writable.
- `scripts/verify-miniogas.ps1` does not source `scripts/env.ps1`, does not run the Go node-agent tests, and does not run supervisor tests. Its current "node-agent tests" step runs only `test_simulator.py`, so a green verification can miss failures in two supported Go runtime components.
- All pytest invocations pass but emit a cache warning because the root `.pytest_cache` ACL is unreadable. The cache is nonessential, but verification should disable or redirect it to avoid persistent warning noise.
- API contract check, dashboard login-gate check, secret scan, and `git diff --check` passed. Ruff did not run because it is not installed in the active Python environment; verification currently has no enforced Python lint/type-quality gate.
- `services/central-api/app/store.py` is 3,295 lines and owns state, simulation, alerts, commands, audit, persistence restore, replay, planning, dispatch, preflight, and reports. This is confirmed architecture concentration, not just a historical hotspot.
- Central API declares configurable `settings.cors_origins`, but `app/main.py` uses a separate hard-coded origin list. Configuration changes therefore do not actually control CORS behavior.

## Confirmed Diagnosis (2026-07-10)
1. **[HIGH] Pre-login self-check mutates operational state.** `MemoryStore.run_preflight()` calls `simulation_step()` when central simulation is stopped. This can refresh logical node facts without a child-node heartbeat and makes a connectivity check capable of manufacturing the evidence it is meant to verify.
2. **[HIGH] Production-node readiness is under-specified.** Preflight passes when any non-ephemeral node is fresh and even passes when no nodes are registered. It does not require every node in `EXPECTED_PRODUCTION_NODES`, so one logical/control node can mask missing workshop nodes.
3. **[HIGH] Pre-login self-check calls external AI.** Preflight invokes both `registry.chat()` and `registry.diagnose()` before administrator vault unlock, while the dashboard explicitly states that login-before-unlock uses only rule fallback. This is a contract and security-flow contradiction.
4. **[HIGH] AI provenance can be false.** AI routes set `used_ai` from `is_any_live_provider()` before the request. If every live provider fails and the registry serves `rule_fallback`, responses can still claim a live backend. Chat and shortcut responses also hard-code the DeepSeek model even when Ollama, LM Studio, or Groq actually served the request.
5. **[HIGH] Acceptance omits supported binaries.** `verify-miniogas.ps1` does not run the Go node-agent or Go supervisor tests and does not load the project-local Go environment. A green acceptance run therefore does not cover two supported runtime components.
6. **[MED] Startup result is not refreshed after authentication.** The login response returns `preflight: None`; after AI vault unlock and smoke testing, the dashboard retains the older pre-login checks instead of receiving a final authenticated readiness snapshot.
7. **[MED] Configuration drift is executable.** CORS settings are ignored by middleware, `.env.example` disables microservices while supported supervisor runtime enables them, and README lists Redis/NATS as current components despite no runtime implementation.
8. **[MED] Central orchestration concentration is excessive.** `MemoryStore` contains persistence, state, simulation, rules, command lifecycle, part flow, replay, reports, and preflight. The immediate architecture change will extract preflight into a side-effect-free service; larger primary-read migration remains a separately testable v2.5 boundary.

## Remediation Evidence Before Live Runtime (2026-07-10)
- Extracted startup validation into `app/preflight_service.py`. It reads runtime evidence without advancing simulation, creating alerts, or calling an AI provider before login.
- `MemoryStore.production_node_readiness()` now requires every configured production node to be registered, fresh within the heartbeat timeout, and in an available state. Logical cloud/control nodes cannot satisfy this check.
- Login now returns a refreshed authenticated preflight payload after vault unlock and AI smoke testing; dashboard startup state can therefore reflect post-login reality.
- `ProviderRegistry.diagnose_with_provenance()` records the provider that actually served each diagnosis. AI chat, shortcut, and diagnosis routes now distinguish live API from rule fallback and report the serving provider/model instead of assuming DeepSeek.
- CORS middleware now consumes `settings.cors_origins`; `.env.example` defaults to microservices plus PostgreSQL and documents SQLite as edge/test fallback.
- The canonical verification script now loads the local tool environment and covers central-api, Python simulator, Go node-agent, Go supervisor, AI dispatcher, CLI/workflow scripts, dashboard tests, and dashboard production build.
- Serial full verification passed: central-api 107, Python simulator 22, AI dispatcher 4, CLI/workflow 30 plus 9 subtests, dashboard 60, both Go modules, API contract, login gate, secret scan, and production build.

## v2.5 Contract Re-Audit (2026-07-13)
- The Safety Governor existed but node-management routes could call Store mutations without carrying an approved decision. Store now rejects direct high-risk mutations unless the decision matches action, target, and actor; emergency automatic isolation is restricted to `safety_automation` in `emergency_containment` mode.
- Safety denials were returned to clients but not consistently audited. Every route-level safety review now records allowed/denied decisions and machine-readable reason codes before execution.
- PostgreSQL projection refresh previously swallowed individual loader failures and durable write failures only produced warning logs. Projection loads now fail closed into `stale_cache`, and write failures keep persistence/snapshot status degraded instead of claiming healthy primary facts.
- Replay was database-backed and read-only in implementation, but its API/UI did not explicitly identify replay data. Responses now expose `data_source=replay` and `read_only=true`; an integration test snapshots live heartbeats, commands, parts, and alerts and proves replay leaves them unchanged.
- Formal `runs` and `scenarios` tables had been added, but replay still discovered runs only by grouping heartbeat rows. Replay now prefers formal run entities and keeps an explicit heartbeat fallback for legacy rows.
- The supervisor gave all three nodes one `run_id` while assigning three different scenario IDs and random seeds. Because `runs.run_id` is unique, successive heartbeats overwrote run identity. The runtime now uses one factory-level scenario and master seed, and central-api rejects conflicting run/scenario/seed identities before state mutation.
- Kali attack-lab heartbeats had no `run_id`, `scenario_id`, or seed, so their alerts, AI decisions, and commands could not be isolated from normal runs. The workflow now emits a unique attack run, stable scenario seed, scripted engine provenance, and completed lifecycle state on recovery.
- Remaining architectural concern: primary persistence SQL is still concentrated in `MemoryStore`; v2.5.2 is not complete until the repository/transaction boundary and migration rollback evidence are finalized.
# Final full-system findings - 2026-07-13

- PostgreSQL already stored `run_id` for alerts and part queue, but the domain models dropped it. This allowed historical open alerts to enter new live snapshots and allowed target-node residue to misclassify WIP. Domain ownership, restoration and operational filters now agree.
- Incident events also needed run identity. Events without a node heartbeat inherit the current system run so central/manual workflow facts remain replayable without weakening live filters.
- The Dashboard audit client consumed the paginated unified event response as an array. A contract normalizer now supports both pagination and legacy arrays and prevents `undefined` archive metrics.
- Command creation had two event writers. Store/Command Manager is now the single event owner and transaction boundary.
- Live browser truth after fixes: 3/3 nodes, 0 active faults, 0 warnings, 0 stale popups, current-run WIP only, DeepSeek API verified, formal replay read-only.
- The accepted v2.5 architecture is local multi-process, PostgreSQL-primary and HTTP-connected. NATS, Redis, separate edge hosts and a registered Kali VM are not current implementation claims.
