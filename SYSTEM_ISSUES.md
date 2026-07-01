# Mini-OGAS System Issues

> Report time: 2026-07-01

## Executive Summary

The original first-phase blockers have been addressed. The system now has a working v2.2 trusted loop:

1. central-api validates fresh runtime processes.
2. Production nodes send heartbeat v2 payloads.
3. `/api/dashboard/snapshot` exposes backend runtime facts to the dashboard.
4. AI provider-chain fallback is implemented.
5. PostgreSQL is the configured central persistence target.
6. Runtime logs are written to `.runtime/logs`.
7. A structured production report endpoint and dashboard report viewer exist.
8. The v2.5 local runtime now starts through the Go supervisor by default.
9. PostgreSQL replay-readiness is exposed in persistence status and production reports.
10. A scripted PostgreSQL restart drill now proves replay readiness after supervisor restart.
11. Heartbeat shadow data now has a bounded per-node retention policy.
12. The Kali red-team workflow is now explicitly lab-only, authenticated, evidence-producing, and approval-gated for high-risk actions.
13. Production reports can be exported from protected backend endpoints and downloaded from the dashboard.
14. Command lifecycle transitions now live in a v2.5 Command Manager module with idempotent result handling, claim timeout, supersede, approval, rejection, and heartbeat verification.
15. High-risk commands and human approvals now pass through a v2.5 Safety Governor with shared confirmation-code and control-plane protection rules.

The remaining verified runtime gap is AI live-provider smoke: the supervised runtime is configured, but the 2026-07-01 login smoke returned `api_error` for provider `ollama`.

## Resolved Historical Issues

| Historical issue | Current state |
| --- | --- |
| No reliable launcher | Resolved for local operation by `scripts/start-miniogas.ps1`, which defaults to the Go supervisor and can fall back to the legacy script launcher when requested. |
| Preflight accepted stale processes | Resolved. Health includes session token, process ID, and process start time. |
| AI depended on one DeepSeek path only | Resolved. Provider-chain fallback exists in central-api and ai-dispatcher. |
| Dashboard showed `0/3 online` while API had 5 nodes | Resolved. Frontend counts actual host nodes. |
| VirtualBox confused production status | Resolved for production UI. Remaining VirtualBox references are optional Kali/red-team lab support or old design documents. |
| Missing dashboard-state rich fields | Resolved. Snapshot and dashboard-state expose production, metrics, alarms, sync, work orders, dispatch, and rule facts. |
| Root runtime logs | Resolved. Startup scripts now write to `.runtime/logs`, and existing root logs were moved. |
| Missing production report API | Resolved. `/api/reports/production` aggregates operational report data. |
| Missing production report viewer | Resolved. Dashboard `生产报告` renders live report data from the protected report API. |
| node-agent DB metric looked real while estimated | Resolved. Legacy node agent reports `db_size_source` as `local_file` or `estimated`. |
| Kali red-team path blurred production status | Resolved. The workflow no longer contributes production availability truth, requires explicit lab acknowledgement, rejects public targets by default, uses bearer auth for protected operations, and stops high-risk AI decisions at human approval unless explicitly overridden for a lab run. |
| Missing report export | Resolved. `/api/reports/production/export` supports JSON, Markdown, and CSV, and the dashboard report view exposes authenticated Markdown/CSV downloads. |
| Command lifecycle spread across Store | Resolved for initial v2.5. `CommandManager` now owns deterministic transitions; Store performs persistence and incident-event side effects. |
| High-risk action policy spread across routes | Resolved for initial v2.5. `SafetyGovernor` now owns confirmation-code enforcement and production-control-plane isolation denial for control commands, operations commands, dispatch approval, and escalation approval. |

## Current Issues

| Priority | Issue | Current evidence |
| --- | --- | --- |
| P1 | AI live-provider smoke failing | 2026-07-01 supervised login succeeds with PostgreSQL JWT auth, but `ai_smoke.status` returns `api_error` while runtime provider is `ollama`. |

## Verification Commands

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check-runtime-status.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1 -RequireAiUnlocked
python -m pytest services/central-api/tests
python -m pytest services/node-agent
cd services/dashboard; npm test; npm run build
```
