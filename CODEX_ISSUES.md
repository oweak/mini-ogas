# Mini-OGAS Issues Status

> Last updated: 2026-07-03

This file records the current verified state after the v2.2 first-phase remediation pass. It replaces older notes that still described the system as a three-node or VirtualBox-primary deployment.

## Current Runtime Truth

| Area | Current state |
| --- | --- |
| Central API | `/health` exposes `session_token`, `process_id`, and `process_started_at`; startup checks reject stale processes. |
| Production nodes | The live production runtime counts three SimPy workshop nodes: turning, milling, and grinding. Cloud workshop/DB entries remain management-side logical infrastructure facts, not production-node uptime counters. |
| Production simulation | The three production nodes run SimPy-compatible heartbeat v2 payloads through `services/node-agent/simulator.py`. |
| Snapshot API | `GET /api/dashboard/snapshot` is implemented and exposes runtime, production, part queue, dispatch, and rule facts. |
| AI runtime | central-api and ai-dispatcher both support provider-chain fallback; current supervised runtime verifies live DeepSeek through the unlocked vault and Ollama through model-level local availability checks. |
| Persistence | PostgreSQL is the central persistence backend when configured; SQLite remains an explicit local fallback for tests or edge use. |
| Supervisor | Go supervisor is the preferred v2.5 runtime owner. `scripts/start-miniogas.ps1` defaults to supervisor mode, owns dashboard plus backend/node processes, and the `-ReplaceRunning` handover has been verified. |
| Command lifecycle | v2.5 Command Manager owns command creation, approval, rejection, claim, result, timeout, supersede, and heartbeat verification transitions. |
| Safety governance | v2.5 Safety Governor centrally gates high-risk control commands and human approval actions, returning machine-readable `safety.reason_code` evidence to API clients. |

## Resolved Items

| # | Item | Resolution |
| --- | --- | --- |
| 1 | Remove production-node VirtualBox UI coupling | Resolved. Production node status is driven by live heartbeats. VirtualBox references that remain are limited to optional Kali/red-team lab handling and older docs. |
| 2 | Process freshness verification | Resolved. `/health` and startup scripts verify launch session and process identity. |
| 3 | AI multi-provider chain | Resolved. central-api uses provider registry; ai-dispatcher uses `diagnose_with_chain()`. |
| 4 | Supervisor availability | Resolved as an operational path. Source is in `services/supervisor`; `scripts/start-supervisor.ps1` builds and runs it. Normal `start-system.ps1` remains a lightweight launcher. |
| 5 | Frontend node count bug | Resolved. Runtime presentation counts the actual host node list instead of a fixed 3-node assumption. |
| 6 | Root generated-artifact cleanup | Resolved. Runtime logs now go to `.runtime/logs`; old root logs were moved. Root `node_modules` was moved to `tools/node_modules` with the document-reporting package files. |
| 7 | CRLF/LF line endings | Resolved. `.gitattributes` is present and `git diff --check` passes. |
| 8 | Production report generator | Resolved. `GET /api/reports/production` and `/reports/production` aggregate management snapshot, dashboard snapshot, rules, AI runtime, persistence, nodes, alerts, and dispatch state. |
| 9 | node-agent DB size provenance | Resolved. Legacy `agent.py` now sends `db_size_source`; real local DB files are reported as `local_file`, otherwise values are explicitly marked `estimated`. |
| 10 | Documentation sync | Resolved in this pass. `SYSTEM_ISSUES.md` and `PROJECT_STATUS.md` now reflect the current runtime state. |
| 11 | Frontend production report viewer | Resolved. The dashboard now has a `鐢熶骇鎶ュ憡` page backed by the protected production report API; it renders live node counts, production metrics, PostgreSQL state, AI runtime, market signals, and rule conclusions. |
| 12 | Protected API CORS/rate-limit failures | Resolved. 401/429 early responses preserve dashboard CORS visibility, stale JWTs force the UI back to login, and the local default rate limit now fits the multi-process simulator. |
| 13 | v2.5 supervisor runtime transfer | Resolved for the initial rollout. `scripts/start-miniogas.ps1 -ReplaceRunning` successfully moved the local stack under the Go supervisor, verified all 8 managed processes healthy, and removed stale non-supervised simulator processes. |
| 14 | PostgreSQL replay-readiness evidence | Resolved for the v2.5 local runtime. `MemoryStore.replay_readiness_report()` now checks heartbeat, command, part queue, and audit shadow facts; `/api/persistence/status` and `/api/reports/production` expose the result; the live PostgreSQL runtime reports `replay_status=ok`. |
| 14a | Run-level replay API | Resolved for v2.5. `/api/replay/runs` lists persisted `run_id` batches, and `/api/replay/runs/{run_id}` returns database-backed heartbeat, command, part queue, audit, alert, and AI diagnosis timelines. Tests verify route registration and 404 behavior for missing runs. |
| 14b | Run-level replay console | Resolved for v2.5. Dashboard `运行回放` consumes the protected replay API, lists persisted runs, handles loading/empty/error states, and renders a database-backed operational timeline for administrators. |
| 14c | Replay sampling boundary drift | Resolved. `replay_runs()` and `replay_run()` now derive run start/end and heartbeat totals from full database aggregates, while detail payloads expose sampling metadata when only recent heartbeat rows are returned. |
| 15 | PostgreSQL restart drill | Resolved for the v2.5 local runtime. `scripts/check-postgres-replay-drill.ps1` performs a supervisor restart, waits for all 8 processes, verifies PostgreSQL replay readiness remains ok, and writes `.runtime/logs/postgres-replay-drill-last.json`. |
| 16 | PostgreSQL heartbeat-shadow retention | Resolved for v2.5. `HEARTBEAT_SHADOW_RETENTION_PER_NODE` now controls per-node heartbeat shadow retention, `/api/persistence/status` exposes the policy, and the live runtime reports `keep_latest_per_node` with replay readiness still ok. |
| 17 | Kali red-team workflow boundary | Resolved for v2.5. `scripts/kali_redteam_workflow.py` now requires explicit lab acknowledgement, rejects public targets by default, separates node-ingest token from administrator bearer auth, records structured evidence, and holds high-risk AI decisions at `waiting_human_approval` unless `--auto-approve-high-risk` is explicitly passed. |
| 18 | Production report export | Resolved for v2.5. `/api/reports/production/export` now exports the live production report as JSON, Markdown, or node CSV; the dashboard report page can download Markdown and CSV using the authenticated API client. |
| 19 | Commit hygiene | Resolved. Generated noise is ignored, `services/dashboard/tsconfig.tsbuildinfo` was removed from version content, secret scan and staged whitespace checks passed, and the implementation was committed as `4addc36`. |
| 20 | Command Manager lifecycle | Resolved for initial v2.5. Command transitions are centralized in `app/command_manager.py`; duplicate results are idempotent, stale claimed commands expire, older pending same-node commands are superseded, and heartbeat verification drives `verified`. |
| 21 | Safety Governor for high-risk actions | Resolved for initial v2.5. `app/safety_governor.py` now applies shared confirmation-code and control-plane isolation rules to `/control/command`, `/ops/issue-command`, dispatch-plan approval, and escalation approval. Runtime verification blocks missing confirmation as `confirmation_code_required` and blocks cloud isolation as `control_plane_isolation_blocked`. |
| 22 | AI live-provider verification | Resolved for v2.5. The AI vault was re-encrypted to the current administrator password, login smoke now reports `provider=deepseek`, `source=api`, `model=deepseek-v4-pro`, and Ollama/LM Studio availability checks now verify the selected local model/server rather than reporting generic configured status. |

## Remaining Work After v2.2

No open v2.5 blocker is currently tracked here. The latest supervised runtime verifies DeepSeek live smoke, Ollama local fallback availability, PostgreSQL persistence, and Safety Governor enforcement.

## Verification Targets

Use these checks after changes:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check-runtime-status.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1 -RequireAiUnlocked
python -m pytest services/central-api/tests
python -m pytest services/node-agent
cd services/dashboard; npm test; npm run build
```
