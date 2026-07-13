# Mini-OGAS First-Stage Completion Plan

## Goal
Complete the v2.2 compatible trusted-loop stage to an evidence-based acceptance standard: every required contract, data path, runtime mode, command loop, dashboard state, persistence path, and test in the stage must work together without fixture-only substitutions.

## Acceptance Rule
A task is complete only when its implementation, configuration, automated tests, and a runnable integration check all pass. Code presence alone does not count.

## Phases
| Phase | Status | Deliverable |
|---|---|---|
| 1. Audit and evidence inventory | completed | Verified requirement matrix and gap list |
| 2. Runtime data path | completed | Simulator/agents -> heartbeat v2 -> central snapshot -> dashboard flow verified |
| 3. Control and AI closure | completed | Command polling, acknowledgement, diagnosis provenance, and human approval flow verified |
| 4. Durable persistence | completed | PostgreSQL-backed local/runtime path and restart evidence verified |
| 5. Stage acceptance | completed | Full tests, integration evidence, and updated completion report |
| 6. Post-acceptance remediation audit | completed | Removed dashboard VirtualBox residue, made production-node expectation explicit, activated microservices, migrated dashboard auth to JWT/RBAC, and cleaned stale logs |
| 7. Post-acceptance verification | completed | Full regression suites, production build, API contract check, PostgreSQL RBAC evidence, and strict runtime evidence passed |
| 8. Legacy runtime consolidation | completed | Removed the unused single-file central-api runtime, its tests, and generic production VirtualBox deployment path; all launchers now target `app.main` |
| 9. Runtime freshness and node-count evidence | completed | Added session-bound PID/start-time health proofs, made `mogas up` delegate to the strict launcher, and browser-verified the live 3/3 dashboard count |
| 10. Dispatcher AI provider chain | completed | Added ordered DeepSeek/Ollama/LM Studio/Groq fallback, provenance, failure records, tests, and live DeepSeek dispatcher evidence |
| 11. Full-system architecture and runtime audit | completed | Reconciled implementation, reports, configuration, persistence, AI, supervisor, nodes, dashboard, and baseline evidence |
| 12. P0/P1 remediation and architecture optimization | completed | Repaired cross-run alert/event/WIP leakage, audit contract drift, duplicate command events, unsafe action paths, persistence ownership, and run identity |
| 13. End-to-end acceptance and documentation sync | completed | Full tests, live PostgreSQL/AI/three-node workflow, browser checks, and current reports all pass |

## Non-Negotiable Constraints
- Preserve user work and existing dirty changes unless a correction is explicitly required.
- Do not claim PostgreSQL, AI, or distributed-node behaviour without a real runtime verification.
- Treat fixture/fallback display as degraded state, never as production truth.
- Keep credentials out of reports, logs, and test output.

## Errors Encountered
| Error | Attempt | Resolution |
|---|---:|---|
| Recursive project scan timed out on protected `.pytest_cache` | 1 | Use targeted directory scans and exclude cache paths |
| PostgreSQL RBAC seed used integer `1` for a boolean column | 1 | Bind a typed boolean value so SQLite and PostgreSQL share one schema path |
| Node restart script attempted to read the dashboard with a machine credential | 1 | Use the node-authenticated `/nodes` status endpoint; dashboard snapshots remain bearer-JWT protected |
| Global secret scanner traversed protected runtime/cache directories | 1 | Exclude `.pytest_cache` and `.runtime` from source scanning; retain them as runtime artifacts rather than code inputs |
| `rg.exe` was denied by Windows while inventorying the repository | 1 | Switched to targeted PowerShell-native enumeration and `Select-String` searches |
| Recursive Markdown inventory entered protected caches and runtime toolchains | 1 | Restrict report and source scans to repository-owned `docs`, `services`, `config`, `database`, `scripts`, and `tools` paths while excluding generated/runtime directories |
| Parallel central-api test runs contended for `.runtime/test-central.db` | 1 | Treat the shared integration database as a serial test resource; rerun the full verification without another central-api pytest process in parallel |
| `rg.exe` was denied again during the v2.5 call-path audit | 1 | Continued with targeted `Get-ChildItem` and `Select-String` queries |
| Targeted central-api tests were first launched from the repository root | 1 | Reran from `services/central-api` so the `app` package resolves correctly |
| Safety decision auditing increased the expected dispatch approval audit count | 1 | Updated the test to assert the denied and allowed safety records plus the execution record |
| A multi-file replay UI patch used a console-mojibake string as context | 1 | Re-read the UTF-8 file through .NET and applied the patch using real source text |
| A broad recursive report inventory entered generated/protected content and timed out | 1 | Restricted the report audit to repository-owned top-level status and docs files |
| The live workflow command first referenced a nonexistent root `.venv` | 1 | Used `services/central-api/.venv/Scripts/python.exe`, the repository's actual Python runtime |
| Current-run notification filtering hid an event from an ephemeral workflow node | 1 | Unbound central events now inherit the active system `run_id`; the complete workflow passed |

## Phase 12 Checkpoint (2026-07-13)
- Completed actual-provider provenance across compatibility diagnosis, metric-triggered diagnosis, control planning, and operations wrappers.
- Added command cancellation/retry routes and strengthened idempotency and concurrent claim tests.
- Added canonical agent heartbeat route plus explicit legacy deprecation wrappers.
- Added formal `scenarios`/`runs`, deterministic seed reporting, formal run replay preference, and run/scenario identity conflict rejection.
- Added `EventPublisher`/`HTTPPublisher` and `RuntimeAdapter`/SimPy adapter boundaries to the node runtime.
- Made PostgreSQL projection failures and unreconciled write failures visible as degraded state.
- Closed Safety Governor bypasses for node isolate/restore/retire, control execution, operations execution, demo scenarios, dispatch approval, and escalation approval; denials are now audited.
- Marked replay responses as `data_source=replay`, `read_only=true`, and proved replay queries do not mutate live state.
- Corrected the supervised three-node runtime to use one factory-level scenario and deterministic master seed per run; Kali attack-lab heartbeats now use isolated formal run/scenario identities.

## Final Acceptance (2026-07-13)

- Added domain-level `run_id` ownership for alerts, incident events and part queue; live projections and claims exclude historical runs while replay retains them.
- Corrected Dashboard audit pagination normalization and removed visible `undefined` archive metrics.
- Removed duplicate `command-created` emission and retained the transactional Store/repository owner.
- Canonical verification passed: central-api 133, simulator 26, dashboard 63, AI dispatcher 4, CLI/workflow 30 + 9 subtests, both Go projects, API/gate/secret checks, and frontend build.
- Strict runtime passed with 8/8 processes, 3/3 production nodes, PostgreSQL primary facts and live DeepSeek API.
- Real fault -> AI -> approval -> close -> audit -> notification acknowledgement workflow passed.
- Browser checks passed for clean login, zero stale popups, current-run WIP, read-only replay, desktop and 390 px mobile layouts.
- Current reports were synchronized and a complete audit report was added under `docs/`.
