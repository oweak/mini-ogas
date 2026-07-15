# Phase 2 Gate Record

## Status

`PASS - 2026-07-14 - DIGITAL-TWIN/ENGINEERING GATE ONLY`

Phase 2 now has a durable vertical slice for governed organization, equipment,
personnel qualification, controlled revisions, and work-order release. This gate
does not authorize production use, physical equipment control, or Phase 3 operation
execution.

## Baseline

The pre-implementation record in `PHASE2_BASELINE_AUDIT.md` found all four gates
failed and all proposed `/master-data/*` routes returned HTTP 405. Existing seed,
heartbeat machine context, JWT roles, and free-form planner routes were explicitly
rejected as substitutes for governed master data.

## Implemented Capability

- Strict Enterprise -> Site -> Area -> Line -> Cell hierarchy.
- Governed UOM, Material, Product, Equipment, Equipment Capability, Skill,
  Personnel, Qualification, Calendar, and Shift records.
- Controlled Document, BOM, and Routing revisions with `draft -> approved ->
  effective -> superseded` transitions.
- Exact work-order binding to BOM, Routing, document, calendar, shift, equipment,
  and personnel assignment IDs.
- Release-time checks for product consistency, effective revisions, required
  documents, assignment coverage, equipment capability, active personnel, skill
  level, and qualification validity period.
- Dedicated `master-data:manage` permission; account role is never accepted as a
  personnel qualification.
- Business mutation, audit row, and NATS audit Outbox envelope commit in one
  transaction. Injected Outbox failure rolls all three back.

## Business Authority

PostgreSQL is authoritative for Phase 2 objects. All repository reads and writes
include the configured tenant/site scope, and PostgreSQL additionally enforces
forced row-level security. Legacy `MemoryStore`, dashboard seed, SimPy profile,
heartbeat machine strings, and planner route arrays are not Phase 2 authorities.

## State Machines

```text
Controlled revision:
draft -> approved -> effective -> superseded

Work order in Phase 2:
draft -> released
```

An effective transition supersedes the previous effective revision in the same
transaction. A partial unique index ensures that concurrent writers cannot leave
two effective revisions. Work-order release is idempotent; other illegal transitions
return HTTP 409 with a stable error code.

## Data And Migrations

| Migration | Purpose | Live status |
|---|---|---|
| `2026.07.14-phase2-master-data` | 18 scoped tables, indexes, forced RLS, immutable revision identity/content, one-effective-version constraint | Applied once with checksum |
| `2026.07.14-phase2-revision-delete-guard` | Database-level prevention of controlled revision deletion | Applied once with checksum |

Live PostgreSQL evidence:

- 18/18 Phase 2 tables exist with both RLS and forced RLS enabled.
- Alternate-site visibility probe: active scope `1`, other scope `0`.
- Three update guards rejected revision content overwrite.
- Three delete guards rejected history deletion.
- Three partial unique indexes enforce one effective revision per parent.
- Re-running `init_db()` preserved one ledger row per migration.

## Interfaces And Events

The versioned OpenAPI export contains the complete `/master-data/*` route family.
Create routes return HTTP 201; transitions, release, and revision query return HTTP
200. Every accepted mutation creates a schema-valid `audit` transport envelope in
the existing transactional Outbox with `run_id=master-data`. NATS remains shadow
transport and is not the master-data authority.

## Authorization And Audit

- `system_admin` receives `master-data:manage` through persisted RBAC.
- A signed viewer JWT without the permission receives HTTP 403.
- Mutations derive the actor from the verified JWT; payload actor fields do not exist.
- Qualification issue, revision creation/approval/effectivity, master creation, and
  work-order release are durably audited.
- Direct account linkage is informational only; qualification tables and validity
  evidence decide release eligibility.

## Test Evidence

- `python -m pytest tests/test_phase2_master_data.py -q`: 10 passed.
- `python -m pytest -q` from `services/central-api`: 208 passed.
- `python tools/export_contracts.py --check`: passed.
- Live HTTP authenticated negative probe: HTTP 409,
  `INVALID_ORGANIZATION_HIERARCHY`, no row persisted.
- Canonical runtime after migration: supervisor 9/9 healthy, three production
  simulator nodes fresh, PostgreSQL preflight OK, NATS shadow publisher/worker live,
  and live DeepSeek provider smoke successful.

## Rollback And Recovery

Both migrations are additive. An application rollback may leave the new tables and
triggers in place because older code does not reference them. Once controlled
revisions exist, destructive schema rollback is forbidden; restore must use a
verified PostgreSQL backup and preserve audit/history. A failed mutation is rolled
back automatically because business row, audit, and Outbox share one transaction.

## Residual Scope

- Phase 3 production order, operation task, dispatch, start/pause/resume/complete,
  quantity evidence, hold, close, downtime, and replay are not implemented here.
- Phase 2 master IDs are not yet reconciled to legacy simulator/dispatch strings.
- Base-master correction/retirement needs a governed future lifecycle; direct SQL is
  not an approved correction path.
- No real OT connector or physical write capability exists.

## Formal Gate

| Gate | Evidence | Result |
|---|---|---|
| Work order binds exact BOM, Routing, and document revisions | Persisted IDs survive release and are returned unchanged | PASS |
| Account is not operation qualification | Linked administrator without qualification is rejected with `QUALIFICATION_MISSING` | PASS |
| Master-data changes are auditable | Durable audit plus transactional audit Outbox; rollback fault test | PASS |
| Historical revision cannot be overwritten | Update and delete blocked by SQLite and live PostgreSQL triggers; prior content retained after supersession | PASS |

Phase 3 subsequently passed its separate gate in `PHASE3_GATE.md`. This Phase 2
record remains the authority for the earlier master-data acceptance decision.
