# Phase 2 Master Data Test Evidence - 2026-07-14

## Repository State

- Working tree: dirty before and during this batch; unrelated user changes preserved.
- Validation is evidence for the current working tree, not a tagged release or commit.
- Environment: Windows digital twin, PostgreSQL primary, NATS loopback shadow,
  physical connector disabled, physical write disabled.

## Commands And Results

| Command/probe | Result |
|---|---|
| `python -m pytest tests/test_phase2_master_data.py -q` | 10 passed |
| `python -m pytest -q` in `services/central-api` | 208 passed |
| `python tools/export_contracts.py --check` | passed |
| `scripts/start-miniogas.ps1 -ReplaceRunning` | supervisor became ready |
| `scripts/check-runtime-status.ps1` | central ready; 9/9 processes; 3/3 fresh nodes; PostgreSQL/NATS/AI checks OK |
| PostgreSQL migration query | one row for each Phase 2 migration, checksum present |
| PostgreSQL RLS catalog query | 18/18 Phase 2 tables enabled and forced |
| Cross-site transaction probe | active scope 1; alternate scope 0; rolled back |
| Revision update probe | blocked by immutable trigger; transaction rolled back |
| Revision delete probe | blocked by delete guard; transaction rolled back |
| Authenticated live invalid hierarchy probe | HTTP 409, `INVALID_ORGANIZATION_HIERARCHY`, no row persisted |

## Acceptance IDs

- Migration IDs: `2026.07.14-phase2-master-data`,
  `2026.07.14-phase2-revision-delete-guard`.
- Contract: generated OpenAPI v1 plus NATS audit envelope schema 3.0.
- Runtime session observed after final migration restart; exact session ID is runtime
  evidence only and not a stable business identifier.
- Test work-order/equipment IDs are isolated SQLite acceptance data and are deleted
  when the hermetic test database is recreated. No simulated qualification was
  inserted into the live PostgreSQL master tables.

## Failure Evidence

- Before implementation, four Phase 2 tests failed during setup because the first
  master-data route returned HTTP 405.
- After implementation, the first full suite had only a stale generated OpenAPI
  contract failure. Re-exporting the deterministic contract resolved it.
- Transactional Outbox fault injection returns HTTP 500 and leaves zero master rows
  and zero audit rows for the failed business key.

## Non-Claims

This evidence proves the Phase 2 software gate in the current digital-twin runtime.
It does not prove real equipment connectivity, real employee qualification, business
approval by a plant owner, production load, disaster recovery, or Phase 3 execution.
