# ADR-0006: PostgreSQL Authority For Phase 6 Maintenance And Tooling

## Status

Accepted for the Phase 6 engineering gate on 2026-07-14.

## Context

The repository previously had governed Equipment identity, task downtime, Gauge
references, simulated tool-wear values, alarms, and AI explanations. None represented
a maintenance Request/Order, controlled Checklist, coded work, spare use, independent
verification, preventive Plan, Tool life ledger, calibration event, or production
interlock. Treating an alarm close or AI answer as maintenance completion would create
an unsupported equipment-restoration fact.

## Decision

Implement Phase 6 inside the Central API modular monolith with PostgreSQL as sole
maintenance authority. Bind Assets to Phase 2 Equipment, Orders to governed Personnel
and Checklists, downtime to Phase 3 Operation Tasks, and spare quantity to Phase 4
Consume movements. Use append-only Tool life and Calibration events to determine task
readiness.

Separate Request, approval, work completion, and independent verification. Use
`maintenance:manage`, `maintenance:execute`, and `maintenance:verify`; the Operator
may execute but cannot verify. Keep AI proposal-only with no maintenance mutation or
restoration authority. Write audit and NATS Outbox in the same transaction as every
accepted business mutation.

## Alternatives

- Close maintenance when an alarm clears: rejected because alarm state has no work,
  Checklist, cause/remedy, person, verification, or physical readback evidence.
- Treat simulated `tool_wear` as Tool life authority: rejected because it has no
  governed Tool identity, unit, source counter, assignment, calibration, or immutable
  event.
- Let AI select and execute a remedy: rejected because model text is not controlled
  work evidence, authorization, safety interlock, or independent verification.
- Keep spare usage only in a maintenance note: rejected because quantity must remain
  in the Phase 4 inventory ledger and refer to an accepted Consume movement.
- Create a separate maintenance microservice now: deferred because current scale,
  ownership, deployment, and transaction boundaries do not justify distributed
  transactions across Equipment, Task, Downtime, and Inventory.

## Consequences

- Accepted maintenance writes require PostgreSQL; SQLite remains hermetic local/test
  fallback.
- Equipment-unavailable work blocks production execution until independently
  verified. This is a software interlock, not a safety PLC claim.
- MRO Consume extends the Phase 4 movement contract with explicit Maintenance Order
  authority while preserving movement/balance ownership in Phase 4.
- Validation creates durable, prefixed maintenance records. Failed gate probes remain
  visible engineering evidence.
- Physical state, counters, certificates, and external acknowledgements remain absent
  until later connector and pilot phases.

## Security Impact

All routes require verified JWT claims. Planning, execution, and verification are
separate permissions and roles. Actor fields are never accepted from payloads. All
14 new tables are tenant/site scoped with forced RLS. PostgreSQL also rejects direct
same-actor verification, accepted-evidence rewrites, active-maintenance task starts,
and unbound Consume inserts.

## Data And Migration Impact

Four additive checksum-ledger migrations create 14 tables, indexes, foreign keys,
RLS policies, append-only guards, order state/evidence guards, Tool/Calibration
triggers, task interlocks, and one nullable Maintenance Order reference on the Phase 4
movement ledger. Existing production-task Consume remains compatible and must bind an
Operation Task; MRO Consume binds a Maintenance Order instead.

## Rollback

Retain accepted Assets, plans, requests, orders, Checklist results, spares, Tool life,
Calibration, history, audit, and Outbox evidence when application code rolls back.
Do not remove guards or rewrite evidence. Destructive recovery requires a verified
database restore and cross-domain reconciliation.

## Evidence

- `docs/governance/PHASE6_GATE.md`
- `docs/validation/TEST_EVIDENCE/PHASE6_MAINTENANCE_2026-07-14.md`
- `scripts/check_phase6_maintenance.py`

## Reviewers

Engineering gate only. Maintenance, production, inventory, quality, metrology,
OT/security, equipment vendors, external-system owners, and plant/business owners
have not approved a pilot or production release.
