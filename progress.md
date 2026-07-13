# Progress Log

## 2026-06-22
- Created a completion plan for the v2.2 first stage.
- Began an evidence-first audit. Project root is `D:\New project\mini-ogas`.
- Initial recursive scan encountered protected `.pytest_cache`; subsequent scans will be targeted.
- Confirmed the v2.2 contracts and test matrix exist. Identified the stage boundary: PostgreSQL shadow write is required, while primary read/write migration is deferred to v2.5.
- Completed scope, dependency tracing, and diagnosis.
- Test baseline: central-api 55/55, node-agent 22/22, dashboard 56/56 plus production build.
- Confirmed P0 findings: runtime absent; missing host dispatch endpoint; missing local-record sync endpoint; PostgreSQL shadow-write path lacks an actual runtime and replay-ready heartbeat records.
- A broad scan of `services\central-api` included `.venv` and timed out; replaced it with a targeted `app` source scan.
- PostgreSQL 16 installation via winget timed out while its installer process remained active for more than four minutes; it had copied binaries but had not registered a service or initialized data.
- Direct `initdb` fallback failed because the interrupted installation did not yet contain the required `dict_snowball` library. `initdb` removed its incomplete data directory automatically.
- Added real node dispatch and local-record sync endpoints, replay-ready heartbeat shadow persistence, PostgreSQL timestamp reload support, shadow consistency reporting, strict AI provider smoke provenance, and corrected API contract checking.
- Installed and provisioned local PostgreSQL 16 in D:\MiniOGAS-VMs after the first installer invocation timed out; the final native service and application connection were verified.
- Final automated verification: central-api 60/60, node-agent 22/22, dashboard 56/56, dashboard production build, API contract checker passed.
- Final runtime verification: strict startup passed; PostgreSQL backend/status/consistency all `ok`; 3/3 live SimPy nodes; DeepSeek source=`api`; no 404/405/500 responses in current central log.
- Began post-acceptance remediation for five newly reported defects: frontend VirtualBox residue, configured/registered node-count mismatch, disabled microservices, token-only authentication, and root-level VirtualBox logs.
- Completed post-acceptance remediation: dashboard production code no longer includes VirtualBox state; expected production nodes are explicitly configured as the three workshop agents while five logical nodes remain visible as topology facts.
- Added PostgreSQL-backed RBAC associations and PBKDF2 password storage, then replaced dashboard shared-token authentication with time-limited HS256 bearer JWTs. Node and service credentials remain separate from human authentication.
- Enabled microservices by default and made the one-command launcher start, session-check, and verify ai-dispatcher, market-simulator, and production-planner before central-api.
- Fixed two runtime migration issues discovered by evidence: PostgreSQL boolean parameter binding during RBAC bootstrap and a node restart script that incorrectly used a machine token for a dashboard endpoint.
- Deleted all root-level VirtualBox logs. Final verification: central-api 210/210; dashboard 56/56 plus production build; API contract checker passed; strict launcher passed with PostgreSQL, three live SimPy nodes, live DeepSeek, three online microservices, and JWT dashboard access. A direct AI dispatcher probe returned `source=deepseek`.
- Consolidated the remaining old runtime path after review identified a second, unused root-level central-api implementation. Removed its VirtualBox configuration, hard-coded expected-node set, dependent helpers, and root-level tests; kept only the modular `app.main` runtime.
- Removed generic VirtualBox production deployment scripts while retaining the explicit optional Kali red-team VM path. Replaced `start-all.ps1` with a `start-system.ps1` wrapper and updated the portable entrypoint to import `app.main`.
- Final consolidation verification: central-api 64/64 current-runtime tests, dashboard 56/56 plus production build, API contract and dashboard-gate checks pass, strict startup reports 3/3 live SimPy nodes and live AI. Source scans find no legacy VirtualBox/node-count identifiers in production API, dashboard, or microservice code.
- Added process-freshness proof to all runtime health endpoints: session token, process PID, and UTC process start time. `mogas up` now delegates to the strict startup script using the same session token and validates the returned proof instead of trusting a listening port.
- P0 runtime verification completed: a real `mogas up --all` run produced a fresh central API PID/start time, and Playwright logged into the running dashboard and confirmed the live `3/3` node count in all three UI surfaces.
- Implemented a real multi-provider chain inside ai-dispatcher. It now tries `AI_PROVIDER_CHAIN` in order, exposes non-secret provider status, records each attempted provider and failure, and falls back to local rules only after exhaustion. Unit fallback tests and a live DeepSeek dispatcher diagnosis both passed.

## 2026-07-10
- Started a full-system architecture, runtime, implementation, test, and documentation audit at the user's request.
- Confirmed a clean worktree and completed the initial history/hotspot inventory. `central-api/app/store.py` is both the largest change hotspot and a bug magnet.
- Inventoried all repository-owned services and source files while excluding generated runtime, virtual environments, caches, and node modules.
- Found initial report/config drift: no current runtime was active, `.env.example` disagrees with supervisor microservice policy, README lists unimplemented Redis/NATS components, and some status documents contain corrupted text.
- Logged tool errors and switched from denied `rg.exe`/broad recursion to targeted PowerShell-native scans.
- Completed the automated baseline: 218 Python/TypeScript tests passed, the dashboard production build passed, and both Go modules passed when run with the project-local cache.
- Confirmed the current verification script omits Go node-agent and supervisor tests and does not load the repository-local Go environment; logged this as a P0 acceptance gap.
- Confirmed contract, login-gate, secret, and whitespace checks pass. Ruff is unavailable and not currently part of the enforced project verification path.
- Completed dependency tracing for startup, supervisor, preflight, authentication, AI provider registry, persistence, nodes, and dashboard startup workflow.
- Confirmed four high-impact truth defects: preflight mutates simulation state, preflight does not require all expected production nodes, preflight calls AI before login, and AI responses can report configured-provider availability instead of the provider that actually served the request.
- Moved Phase 11 to complete and started P0/P1 remediation with an explicit architecture extraction for side-effect-free preflight.
- Extracted preflight from `MemoryStore`, made it side-effect-free, deferred all model calls until authenticated login, and made production-node readiness require all configured workshop nodes.
- Corrected AI request provenance across login smoke, diagnosis, chat, and shortcut paths; responses now identify the actual serving provider/model and rule fallback cannot be labeled as live AI.
- Unified CORS configuration, changed the example runtime to PostgreSQL/microservices by default, disabled unusable pytest cache writes, and expanded the canonical verification script to all supported Python/Go/TypeScript components.
- Full serial verification passed with 223 Python/TypeScript test cases plus Go package tests and 9 workflow subtests; production dashboard build passed.

## 2026-07-13
- Resumed the full-system audit against the original v2.5.0-v2.5.8 acceptance text rather than existing completion claims.
- Removed remaining false AI provenance from compatibility diagnosis, metric-triggered diagnosis, and both command gateways.
- Added command retry/cancel lifecycle operations, permanent idempotency-key deduplication, and concurrent claim verification.
- Added the canonical agent heartbeat route and deprecation headers/logging for old heartbeat and dashboard-state APIs.
- Added node-runtime publisher/adapter abstractions, formal scenario/run persistence, and deterministic seed reporting.
- Enforced Safety Governor decisions at Store boundaries and all high-risk HTTP entry points; added denial auditing and emergency-containment-only automatic isolation.
- Made PostgreSQL loader/write faults visible as degraded projection state and changed primary heartbeat writes to occur before cache publication.
- Made replay explicitly read-only and added a non-mutation integration proof plus formal run-entity discovery.
- Found and fixed conflicting scenario/seed identities across the three supervised nodes; added central rejection tests and isolated Kali attack-lab runs.
- Current focused evidence: central-api 130/130, Kali workflow 12 tests plus 5 subtests, dashboard 60/60, and production build passed. Full canonical and live/browser acceptance remain pending.
# 2026-07-13 Final acceptance

- Completed cross-run fact isolation for alerts, events, notifications and part queue.
- Added audit-response normalization and frontend tests; Dashboard now has 63 passing tests.
- Full verification passed with central-api 133, simulator 26, AI dispatcher 4, CLI/workflow 30 plus 9 subtests, Go tests and production build.
- Strict live verification passed: 8/8 supervised processes, 3/3 SimPy nodes, PostgreSQL primary projection and real DeepSeek API.
- Fault-to-archive runtime workflow passed end to end.
- Desktop/mobile browser QA and read-only replay checks passed.
- Updated README, issue/status/debt/compatibility reports and added the full-system audit report.
