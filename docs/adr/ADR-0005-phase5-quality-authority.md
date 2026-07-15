# ADR-0005: PostgreSQL Authority For Phase 5 Quality Operations

## Status

Accepted for the Phase 5 engineering gate on 2026-07-14.

## Context

The repository previously exposed simulated defect rates, legacy queue quality text,
and Scrap/Rework quantity labels. None defined an Inspection Plan, specification,
sample, traceable measurement, calibrated Gauge reference, qualified inspector,
quality Hold, Nonconformance, Disposition, CAPA, or authorized release. Promoting
those projections would allow nonconforming material to flow without a defensible
quality record.

## Decision

Implement Phase 5 inside the Central API modular monolith with PostgreSQL as the sole
quality authority. Bind quality records to existing Phase 2 Material/UOM/Skill/
Personnel, optional Phase 3 Operation Task, and Phase 4 Lot/Serial/Location. Create
an open Hold transactionally with every Inspection Lot. Compute Pass/Fail from a
versioned effective Characteristic, then require explicit human authorization for
release.

Use three permissions: `quality:manage`, `quality:measure`, and `quality:release`.
The Operator may measure but cannot release. AI remains proposal-only and receives no
quality mutation or release authority. Preserve measurement and status evidence as
append-only rows and enqueue audit through the existing transactional Outbox.

## Alternatives

- Promote simulated `defect_rate` or queue `quality_status`: rejected because neither
  has specification, sample, device, person, evidence, or release authority.
- Let AI assign Pass/Fail or auto-release: rejected because model output is a
  proposal, not deterministic quality evidence or an accountable authorization.
- Treat Phase 3 Scrap/Rework quantity as disposition: rejected because operation
  accounting does not identify an NC review, Hold, approval, or Lot release.
- Split a quality microservice immediately: deferred because the current ownership,
  scale, deployment, and failure boundary do not justify distributed transactions.
- Store only final inspection status: rejected because it destroys the measurement,
  actor, device, method, specification, and status path needed for audit.

## Consequences

- Accepted quality writes require PostgreSQL; SQLite remains a hermetic test/local
  fallback.
- An Inspection Lot immediately prevents normal Phase 4 flow until a valid release or
  terminal disposition resolves the Hold.
- Measurement validity depends on governed Gauge and qualification references; this
  does not claim direct physical acquisition or calibration-system integration.
- Scrap/Return are logical terminal dispositions in this phase. Rework remains held
  for controlled execution and reinspection.
- Validation creates durable quality records with unique, visible prefixes.

## Security Impact

All quality routes require verified JWT claims. Definition/measurement/release are
separate permissions; the default Operator has no release permission. The System
Admin retains all permissions in the engineering environment. All 10 tables are
tenant/site scoped with forced RLS. Pilot deployment still needs named accounts,
resource scope, and any required two-person approval policy.

## Data And Migration Impact

Two additive checksum-ledger migrations create 10 tables, indexes, RLS policies,
append-only evidence guards, one-open-Hold enforcement, deterministic numeric-result
validation, held-movement rejection, and an authorized-release database guard. No
Phase 1-4 business table is destructively changed.

## Rollback

Retain all accepted plans, characteristics, Gauges, inspections, Holds,
measurements, NCs, dispositions, CAPA, status history, audit, and Outbox evidence
when rolling application code back. Destructive recovery requires a verified
database restore and quality/material reconciliation.

## Evidence

- `docs/governance/PHASE5_GATE.md`
- `docs/validation/TEST_EVIDENCE/PHASE5_QUALITY_2026-07-14.md`
- `scripts/check_phase5_quality.py`

## Reviewers

Engineering gate only. Quality management, metrology, production, inventory,
compliance, OT/security, external-system owners, and plant/business owners have not
approved a pilot or production release.
