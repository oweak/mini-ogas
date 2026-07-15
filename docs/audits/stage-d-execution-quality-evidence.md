# Stage D Production Execution And Quality Ownership Evidence

Verified: 2026-07-15

Branch: `codex/current-stage-hardening`

## Goal

Verify that Production Execution and Quality/Calibration facts have independent,
durable owners and do not rely on `MemoryStore` process state. This checkpoint audits
and proves the existing implementation; it does not create a duplicate repository.

## Repository Truth

- `ExecutionRepository` is the direct owner used by every `/execution/*` route. It
  reads and writes production orders, work-order execution, operation tasks, setup,
  quantity, downtime, history and replay through `get_db()`.
- `QualityRepository` is the direct owner used by every `/quality/*` route. It reads
  and writes gauges/calibration, inspection plans and lots, measurements,
  nonconformances, disposition, release and CAPA through `get_db()`.
- Neither repository instance holds process-local fact fields. New instances are
  empty facades over the active scoped database authority.
- Neither route or repository imports `MemoryStore`.
- Both repositories append audit evidence and call
  `outbox_repository.enqueue_in_transaction()` inside the same database transaction
  as the domain mutation. An Outbox failure rolls back the fact and audit write.
- PostgreSQL Phase 3 and Phase 5 migrations and invariant guards remain the production
  authority. SQLite remains an explicit test/local fallback.

## Added Gates

- Recreate `ExecutionRepository` after dispatch and read the same work-order
  execution and task from durable storage.
- Recreate `QualityRepository` after opening an inspection and read the same
  inspection and quality hold from durable storage.
- Reject future route or repository dependencies on `MemoryStore`.
- Reject addition of process-local fact fields to either repository.
- Require the transactional Outbox enqueue path in both repository implementations.

## Verification

```powershell
cd 'D:\New project\mini-ogas\services\central-api'
.\.venv\Scripts\python.exe -m ruff check `
  tests\test_phase3_execution.py tests\test_phase5_quality.py `
  tests\test_stage_d_repository_boundaries.py --select E9,F,I
.\.venv\Scripts\python.exe -m pytest `
  tests\test_phase3_execution.py tests\test_phase5_quality.py `
  tests\test_stage_d_repository_boundaries.py -q
```

Result: 22 passed; Ruff selected correctness/import checks passed.

The complete Central API suite passed 296 tests after these gates were added.

The official PostgreSQL gates in `scripts/verify-miniogas.ps1` also passed:

- Phase 3: production order and work order closed, one task, six history events, two
  quantity reports and live AI smoke evidence.
- Phase 5: inspection released, disposition approved, CAPA completed, post-release
  movement accepted, AI release forbidden, append-only and hold/release database
  guards active, zero operator release permissions and zero cross-scope rows.

## Architecture Impact

- Fact source: clarified, not changed. PostgreSQL is authoritative for both domains.
- API: no route or payload change.
- Migration: no new schema migration.
- Deployment: no new process, port or service.
- Event path: domain mutations already enqueue transactional Outbox rows. Stage E
  still owns proof of one formal publisher and all-consumer idempotency.

## Conclusion

Production Execution and Quality/Calibration satisfy the Stage D ownership gate.
They are removed from the remaining Stage D list. Event/Outbox and infrastructure
adapter extraction remain open.
