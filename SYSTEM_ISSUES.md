# Mini-OGAS System Issues

> Report time: 2026-06-28

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

The remaining work is roadmap selection for the next v2.5/v3.0 target, not an unresolved first-phase blocker.

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

## Current Issues

No active system issue is currently tracked in this file. Generated noise is ignored, `services/dashboard/tsconfig.tsbuildinfo` was removed from version content, and the implementation was committed as `4addc36`.

## Verification Commands

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check-runtime-status.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1 -RequireAiUnlocked
python -m pytest services/central-api/tests
python -m pytest services/node-agent
cd services/dashboard; npm test; npm run build
```
