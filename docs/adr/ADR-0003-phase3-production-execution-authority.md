# ADR-0003: PostgreSQL Authority For Phase 3 Production Execution

## Status

Accepted for the Phase 3 engineering gate on 2026-07-14.

## Context

The existing planner, SimPy runtime, heartbeat counters, part queue, and dashboard
could depict work moving, but none formed a governed execution transaction. Phase 3
requires legal state transitions, accepted quantities, evidence, assignment, holds,
downtime, close, and deterministic replay without treating HTTP acknowledgement or
simulation output as production completion.

## Decision

Implement Phase 3 as a modular-monolith domain/repository/router boundary in the
Central API, with PostgreSQL as sole authority. Bind each execution aggregate to a
released Phase 2 Work Order and materialize the exact effective Routing operations
and released equipment/personnel assignments at dispatch.

Use an explicit Operation Task state machine, append-only quantity/status evidence,
transactional audit Outbox, request idempotency, conditional updates, row locking,
forced RLS, and database triggers for critical invariants. Keep NATS as shadow audit
transport and keep the frontend, AI, simulator, and compatibility planner outside
the business-fact boundary.

## Alternatives

- Extend `MemoryStore`: rejected because restart and concurrent writer behavior
  cannot provide accepted execution authority.
- Treat SimPy or heartbeat completion as execution: rejected because those facts are
  simulated observations without operator/equipment evidence or governed quantity.
- Reuse legacy `DispatchTask`: rejected because its schema and lifecycle are planner
  projection semantics, not exact Routing operation execution.
- Make NATS events the authority immediately: deferred because current NATS is
  loopback shadow and authoritative inbox/replay/multi-host evidence is absent.
- Split an execution microservice: deferred because independent deployment,
  ownership, and scaling evidence does not yet justify another failure boundary.

## Consequences

- PostgreSQL remains required for accepted runtime execution; SQLite is an explicit
  hermetic/local fallback used by tests.
- HTTP success reports only the accepted transaction state.
- Quantity reporting in Phase 3 accounts good, scrap, and rework against one
  operation plan; material/inventory conservation is deferred to Phase 4.
- Validation creates durable records and audit history, so test prefixes are explicit.
- Legacy planner/SimPy projections remain separate and require mapping if displayed
  beside Phase 3 objects.

## Security Impact

All routes require `execution:manage`. Identity comes from signed JWT claims. All 11
new tables are tenant/site scoped with forced PostgreSQL RLS. The application role is
non-superuser and has no RLS bypass. No physical command path is introduced.

## Data And Migration Impact

Two additive checksum-ledger migrations create 11 tables, indexes, RLS policies,
append-only guards, strict state/quantity/evidence triggers, and no destructive
change to Phase 2 tables.

## Rollback

Retain additive tables and immutable evidence when rolling application code back.
Do not drop execution history. Destructive recovery requires verified backup restore
and audit/Outbox reconciliation.

## Evidence

- `docs/governance/PHASE3_GATE.md`
- `docs/validation/TEST_EVIDENCE/PHASE3_EXECUTION_2026-07-14.md`
- `scripts/check_phase3_execution.py`

## Reviewers

Engineering gate only. Operations, production control, process engineering,
quality, inventory, OT/security, and plant/business owners have not approved a pilot
or production release.
