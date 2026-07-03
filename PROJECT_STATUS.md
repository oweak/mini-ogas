# Mini-OGAS Project Status

> Report time: 2026-07-03

## Project Position

Mini-OGAS is now a local trusted-loop industrial management prototype. The v2.2 phase is verified complete for deterministic runtime facts, heartbeat v2, SimPy-backed production flow, AI-assisted diagnosis, PostgreSQL central persistence, and a dashboard that reflects backend state. v2.5 has started with architecture-debt cleanup and runtime ownership consolidation under the Go supervisor.

The system is not yet a true multi-host v3.0 deployment. It is a local multi-process runtime with five logical nodes and a PostgreSQL-backed central API, suitable for first-phase verification and demonstrations.

## Service Architecture

| Service | Port | Current role |
| --- | --- | --- |
| central-api | 8080 | Main API, auth, rules, persistence, dispatch, reports |
| ai-dispatcher | 8081 | AI diagnosis gateway with provider-chain fallback |
| market-simulator | 8082 | Market signal service |
| production-planner | 8083 | Production planning service |
| dashboard | 5173 | Vue management console |
| node simulators | process | turning, milling, grinding SimPy heartbeat v2 nodes |
| cloud logical nodes | central state | cloud-workshop-01 and cloud-db-01 logical runtime nodes |
| Go supervisor | 9099 | Preferred v2.5 process manager via `scripts/start-miniogas.ps1` |

## Completed v2.2 Work

| Area | Status |
| --- | --- |
| v2.2 contracts | Complete. Contract, compatibility, simulation, test matrix, and architecture debt docs exist. |
| Heartbeat v2 | Complete. `/api/node-heartbeats` accepts runtime, production, metrics, alarms, sync, run, and scenario facts. |
| Dashboard snapshot | Complete. `/api/dashboard/snapshot` exposes live runtime state. |
| SimPy runtime | Complete for first phase. Three production nodes emit SimPy-compatible facts. |
| Rule engine | Complete for first phase. Bottleneck and starvation rules run from snapshot facts. |
| AI chain | Complete for first phase. central-api and ai-dispatcher both support provider fallback. |
| Command loop | Implemented. Node simulator can claim and report command results. |
| Part queue MVP | Implemented. Part queue is persisted and visible in snapshots. |
| PostgreSQL central persistence | Implemented. Runtime preflight reports PostgreSQL when configured; SQLite is only a local/test fallback. |
| Process freshness | Implemented. Session and process identity are checked. |
| Production report API | Implemented. `/api/reports/production` returns structured operational report JSON. |
| Production report viewer | Implemented. Dashboard `生产报告` renders live report data from the protected report API. |
| Runtime log cleanup | Implemented. Launcher logs now target `.runtime/logs`. |
| v2.5 supervisor handover | Implemented for initial rollout. `scripts/start-miniogas.ps1` defaults to the Go supervisor, `-ReplaceRunning` handover was verified, and supervisor owns dashboard plus backend/node processes. |
| v2.5 replay-readiness evidence | Implemented. Persistence status and production reports now expose replay readiness for heartbeat, command, part queue, and audit shadow facts; tests verify a new store instance can restore persisted runtime facts. |
| v2.5 run replay API | Implemented. `/api/replay/runs` lists persisted heartbeat `run_id` batches, and `/api/replay/runs/{run_id}` reconstructs heartbeat, command, part queue, audit, alert, and AI diagnosis timelines from persisted database facts. |
| v2.5 run replay console | Implemented. Dashboard `运行回放` lists persisted run batches, loads replay details through the protected API client, and renders database-backed heartbeat, command, part queue, audit, alert, and AI diagnosis timelines. |
| v2.5 restart replay drill | Implemented. `scripts/check-postgres-replay-drill.ps1` restarts the supervised stack and verifies PostgreSQL replay readiness after restart. Latest evidence is written to `.runtime/logs/postgres-replay-drill-last.json`. |
| v2.5 heartbeat-shadow retention | Implemented. `HEARTBEAT_SHADOW_RETENTION_PER_NODE` keeps recent heartbeat shadow rows bounded per node, and persistence status exposes the active policy. |
| v2.5 Kali red-team boundary | Implemented. `scripts/kali_redteam_workflow.py` is lab-acknowledged, private-target guarded, bearer-authenticated for protected operations, evidence-producing, and high-risk AI actions are held for human approval unless explicitly auto-approved for a lab run. |
| v2.5 production report export | Implemented. Protected report export endpoints provide JSON, Markdown, and node CSV downloads; the dashboard report page exposes Markdown and CSV export actions. |
| v2.5 Command Manager lifecycle | Implemented initial module. `CommandManager` now owns create, approve, reject, claim, result, timeout, supersede, and heartbeat verification transitions; Store keeps persistence and event side effects. |
| v2.5 Safety Governor | Implemented initial module. `SafetyGovernor` now gates high-risk natural-language control commands, operations gateway commands, dispatch approval, and escalation approval with shared confirmation-code and control-plane protection decisions. |
| v2.5 AI live-provider verification | Implemented. The supervised login smoke now unlocks the DeepSeek vault with the administrator password, reports `source=api`, and shows Ollama as a verified local fallback only when the selected local model exists. |

## Current Open Work

| Priority | Item | Reason |
| --- | --- | --- |
| Planning | Select next v2.5/v3.0 target | The trusted loop, supervisor runtime, command lifecycle, safety governor, PostgreSQL persistence, and live AI smoke are verified. The next item should be selected from the roadmap. |

## Current Verification Status

Recent runtime check showed:

- central-api health: ok
- preflight: ok
- active nodes: 5
- admin login: `admin` / `admin` verified against PostgreSQL-backed JWT auth
- AI runtime: live. Latest 2026-07-03 login smoke returned `source=api`, provider `deepseek`, model `deepseek-v4-pro`; Ollama fallback is available with `deepseek-r1:7b-local`, and LM Studio correctly reports unavailable when its server is not running
- persistence: PostgreSQL active in the supervised runtime
- Go supervisor: owns central-api, ai-dispatcher, market-simulator, production-planner, dashboard, and the three SimPy nodes
- replay readiness: live PostgreSQL status reports heartbeat, command, and part queue shadow facts as replayable
- run replay API: central-api tests verify `/api/replay/runs` and `/api/replay/runs/{run_id}` rebuild persisted operational timelines from database rows
- run replay console: Playwright login verified the `运行回放` page renders PostgreSQL run batches and a reconstructed event timeline from the live supervised system
- retention: live PostgreSQL status reports `keep_latest_per_node` for heartbeat shadow rows
- Kali red-team boundary: low-risk `coolant_flow` completed attack-detect-AI-repair archival; high-risk `spindle_overheat` stopped at `waiting_human_approval` without isolation or repair until cleanup was run
- report export: backend smoke tests verify Markdown/CSV attachments, and dashboard production build passes with export buttons
- command lifecycle: live runtime issued `set_target_rate`, node agent claimed it, reported execution, and heartbeat verified it as `verified`
- safety governor: live runtime blocks `isolate milling` without confirmation as `confirmation_code_required`, and blocks `isolate cloud` even with confirmation as `control_plane_isolation_blocked`
- working tree hygiene: generated caches/build outputs/local databases are ignored; `services/dashboard/tsconfig.tsbuildinfo` was removed from version content and verified by a fresh dashboard build
- commit: implementation committed as `4addc36 feat: complete mini-ogas trusted-loop hardening`
- `git diff --check`: passes

## Important Boundaries

- PostgreSQL is the intended central store.
- SQLite is acceptable only for tests, local fallback, or edge-node local queues.
- Production node truth comes from heartbeat v2 and dashboard snapshot, not VirtualBox status.
- Optional Kali/VirtualBox logic is a red-team lab path, not the production-node availability source.
- High-risk Kali workflow actions require human approval by default; script auto-approval is an explicit lab-only override.
