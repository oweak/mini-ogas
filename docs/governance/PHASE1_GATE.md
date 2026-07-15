# Phase 1 Gate Record

## Status

`PASS - revalidated 2026-07-14`

Phase 1 code, complete regression, canonical supervisor runtime, PostgreSQL scope enforcement, migration ledger, Outbox publication and Audit retrieval were observed together. This was the prerequisite for Phase 2; Phase 2 subsequently passed on 2026-07-14 in `PHASE2_GATE.md`.

## Implementation Checklist

| Requirement | Implementation evidence | Current result |
|---|---|---|
| `APP_ENV` | Typed settings and production fail-fast validator | PASS (unit) |
| `DATA_SOURCE` | Runtime source classifier and ingestion rejection | PASS (unit) |
| `CONTROL_MODE` | Read-only blocks mutation; controlled write needs pilot/production plus connector and physical flags | PASS (unit) |
| tenant/site scope | Columns, connection scope, indexes and forced PostgreSQL RLS | PASS: 18/18 live tables |
| Migration management | Ledger, SHA-256 checksum, repeat/no-op and drift rejection | PASS (unit) |
| Module boundaries | Dependency direction test and frozen legacy router allowlist | PASS (unit) |
| OpenAPI/AsyncAPI | Deterministic generated contracts, manifest and drift check | PASS (unit) |
| Outbox foundation | Heartbeat and NATS intent share one DB transaction; claim/lease/retry/dead-letter | PASS: 1,395 live published rows at revalidation |
| Audit foundation | Existing durable audit log and API retained under scoped data layer | PASS: 8,080 scoped rows at revalidation |
| Unified ID | Request ID helper; deterministic transport ID; legacy IDs explicitly classified | PASS (foundation) |
| Unified time | UTC helper and problem/envelope timestamp policy | PASS (foundation) |
| Unified error model | RFC 7807-style envelope preserving legacy `detail` | PASS (unit) |
| Secret governance | Production fail-fast, scan, bootstrap password rule, login limiter, restricted Windows ACL | PASS (local) |
| Demo Seed isolation | Demo only with simulated source; production and non-simulated paths reject it | PASS (unit) |

## Formal Gate

| Gate | Acceptance evidence | Status |
|---|---|---|
| Production forbids Demo/Mock | Invalid production settings fail; demo endpoints disabled | PASS (unit) |
| Migration repeatable | Second application is a no-op; checksum drift fails closed | PASS (unit) |
| Audit available | Regression plus live PostgreSQL scoped query | PASS: 8,080 rows |
| tenant/site effective in data layer | Forced RLS under non-superuser/non-bypass application role; negative scope query | PASS: 18/18 policies, negative queries returned 0 |
| Legacy compatibility | Phase 0/1 compatibility partition after current fixes | PASS: 197 tests |

## Final Verification Evidence

- Compatibility command: `python -m pytest -q --ignore=tests/test_phase2_master_data.py` from `services/central-api`.
- Central API compatibility partition: 197 passed. The unfiltered suite remains red only on the four Phase 2 acceptance tests and is not claimed green.
- Python node simulator: 35 passed.
- AI dispatcher: 4 passed.
- CLI/workflow: 31 passed plus 9 subtests.
- Dashboard: 69 passed plus production build.
- Go node-agent and Go supervisor: all package tests passed.
- Ruff correctness class: passed.
- Runtime: 9/9 supervisor processes, 3/3 current SimPy nodes, live NATS shadow, PostgreSQL preflight `ok` and unlocked `deepseek-v4-pro` API with a successful live smoke call.
- PostgreSQL role: `mini_ogas`, not superuser, no `BYPASSRLS`.
- Migration: `2026.07.13-phase1-scope-outbox` with checksum ledger entry.
- Data scope: 18/18 scoped tables with forced RLS; alternate tenant/site read returned zero audit and Outbox rows.
- Secret ACL: 9/9 repository/runtime sensitive targets restricted to current user, SYSTEM and Administrators.
- Alarm workflow: all eleven stages passed through close, archive, notification acknowledgement, offline record archive and live-state preservation.

## Non-Claims

- No real PLC/CNC/SCADA connector exists.
- `CONTROL_MODE=controlled_write` is deliberately unusable without an implemented connector and explicit physical-write flag.
- NATS is a loopback shadow path; only heartbeat Outbox is transactionally wired.
- The modular monolith still contains legacy `store.py` authority and seven frozen router couplings.
- Tenant/site scope is deployment scope, not a completed multi-tenant control plane.
- This record does not approve a production network or physical command execution.
