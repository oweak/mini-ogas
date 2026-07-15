# Phase 0 Test Baseline

## Scope

This document records commands executed against `D:\New project\mini-ogas` on 2026-07-14. Counts are command results, not inherited progress claims. It separates the green compatibility baseline from the deliberately red Phase 2 acceptance tests.

## Environment

| Tool | Observed version/context |
|---|---|
| Host OS | Windows 11 Home, build family `10.0.26200` |
| Python | 3.13.6 on the authoritative `PATH` |
| Go | 1.26.4; repository cache paths require `scripts/env.ps1` |
| Node.js | 24.13.0 |
| npm | 11.6.2 |
| Database | Local PostgreSQL 5432; application role is non-superuser and cannot bypass RLS |
| Broker | NATS/JetStream on loopback, shadow mode |
| Browser build | Vue 3 + TypeScript + Vite |

The repository-local Central API virtual environment contains Ruff but does not contain the current NATS Python dependency. Runtime and pytest commands therefore use the authoritative `PATH` Python; Ruff uses `services/central-api/.venv/Scripts/ruff.exe`. This interpreter drift remains architecture debt.

## Result Summary

| Gate | Command/result |
|---|---|
| API contract | Pass: 76 backend routes, 24 frontend calls |
| Generated OpenAPI/AsyncAPI | Pass: checked artifacts match generators |
| Dashboard login gate | Pass |
| Secret scan | Pass |
| Secret scanner self-tests | Pass: 5 tests; negative fixtures were detected and redacted |
| Runtime secret ACL | Pass: 9 targets, no ACL failures |
| Central API compatibility partition | Pass: 197 tests |
| Central API unfiltered suite | Expected red: 197 passed, 4 Phase 2 setup errors |
| Python simulator | Pass: 35 tests |
| Go node-agent | Pass: all packages |
| Go supervisor | Pass: all packages |
| AI dispatcher | Pass: 4 tests |
| CLI/workflow | Pass: 31 tests and 9 subtests |
| Dashboard | Pass: 15 files, 69 tests |
| Dashboard production build | Pass: `vue-tsc -b` and Vite |
| Python correctness lint | Pass: Ruff `--select F` |
| Runtime workflow | Pass: 11 stages from fault heartbeat through archive and live-state preservation |
| Strict runtime/preflight | Pass: 9/9 processes, 3/3 nodes, PostgreSQL, NATS and AI |
| Phase 1 PostgreSQL gate | Pass: 18/18 forced-RLS tables and negative-scope queries |

## Compatibility Commands

```powershell
cd services\central-api
python -m pytest -q --ignore=tests/test_phase2_master_data.py
# 197 passed

cd ..\node-agent
python -m pytest .\test_simulator.py -q
# 35 passed

. ..\..\scripts\env.ps1
go test ./...

cd ..\supervisor
. ..\..\scripts\env.ps1
go test ./...

cd ..\ai-dispatcher
python -m pytest .\tests -q
# 4 passed

cd ..\..
python -m pytest .\tools\mogas\tests .\scripts\test_check_secrets.py .\scripts\test_kali_redteam_workflow.py -q
# 31 passed, 9 subtests passed

cd services\dashboard
npm.cmd run test -- --run
# 15 files, 69 tests
npm.cmd run build
```

## Runtime Acceptance

Executed commands:

```powershell
.\scripts\start-miniogas.ps1 -ReplaceRunning
.\scripts\start-system.ps1 -CheckOnly -RequireAiApi
python .\scripts\check_runtime_workflow.py
.\scripts\check-runtime-status.ps1
python .\scripts\check_phase1_database.py
```

Observed evidence:

- Go supervisor owns a fresh session with 9/9 healthy definitions.
- Central API is `ok/ready`; preflight is `ok`.
- Three expected workshop nodes are online with fresh SimPy heartbeats and `data_source=simulated`.
- PostgreSQL is the configured central fact source; persistence consistency and replay readiness are `ok`.
- NATS publisher and worker are live in explicitly non-authoritative shadow mode.
- Administrator login unlocked the AI vault and a real DeepSeek call returned `live provider call completed` using the configured model.
- The runtime workflow passed `heartbeat_fault`, `alert_open`, `confirmed`, `diagnosed`, `approval_required`, `human_approved`, `closed`, `audit_archived`, `notification_acknowledged`, `offline_records_archived` and `live_state_preserved`.
- The event writer survived the new overlapping-store regression without a duplicate `(source_node, run_id, local_sequence)` failure.
- The database role is non-superuser, has no `BYPASSRLS`, and negative tenant/site queries returned zero rows.

These results prove one-host integration. They do not prove multi-host availability, calibrated production physics or physical equipment control.

## Phase 2 Red Gate

The unfiltered command is intentionally retained as evidence:

```powershell
cd services\central-api
python -m pytest -q
# 197 passed, 4 errors
```

All four errors originate in `tests/test_phase2_master_data.py` setup. `POST /master-data/organization-units` returns HTTP 405 because the Phase 2 master-data domain/router has not been implemented. The tests cover:

1. a work order bound to effective BOM, Routing and document revisions plus qualified resources;
2. rejection when an administrator account lacks personnel qualification;
3. immutable historical revision content and superseding revision behavior;
4. durable audit of master-data mutations and release.

This is the first unmet phase gate. It must not be deleted, skipped in a final repository gate, changed to expect 405, or represented as a Phase 0 regression.

## Risk Coverage

| Risk area | Current evidence | Missing evidence |
|---|---|---|
| Source labeling | Classifier, snapshot and frontend null tests | Governed external connector |
| SimPy determinism/capacity | Seed, clock, capacity and flow tests | Calibration against plant history |
| Alarm/human workflow | Live eleven-stage acceptance | Long soak and concurrent operator conflict |
| Event persistence | Transaction, restart, overlap and replay tests | Multi-host writer/partition chaos |
| Command idempotency | Edge SQLite ledger/outbox tests | Independent physical readback |
| Safety | RBAC, confirmation and decision-binding tests | Per-equipment policy and real interlock |
| PostgreSQL | Migrations, forced RLS and runtime checks | Backup restore/PITR drill and HA |
| NATS | Contract, outbox and receipt checks | Authoritative transport and multi-host partition |
| AI | Live smoke plus provider/rule tests | Evaluation corpus, injection and cost/quality gate |
| Auth/secrets | JWT/RBAC, rate limit, scan and ACL gate | MFA, durable lockout, rotation/revocation and per-node identity |
| Dashboard | Component tests, contract gate and build | Canonical Playwright visual/accessibility gate |
| Master data | Four red acceptance tests | Phase 2 implementation |

## Acceptance Rule

Phase 0 is green only while its compatibility partition and runtime workflow remain green and the four Phase 0 gate statements remain true. The repository as a whole is not green while the Phase 2 red tests remain. Future work must convert those tests to green through a durable domain implementation; it may not hide them behind mocks, frontend state or an empty API shell.
