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
