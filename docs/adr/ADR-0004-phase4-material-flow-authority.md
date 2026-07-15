# ADR-0004: PostgreSQL Authority For Phase 4 Material Flow

## Status

Accepted for the Phase 4 engineering gate on 2026-07-14.

## Context

The repository already depicted inventory cards, part queues, simulated WIP, and
operation output, but none established a material identity, location balance,
container, movement ledger, forward/reverse genealogy, or controlled reconciliation.
Treating those projections as inventory would make restart, duplicate delivery, and
external discrepancy behavior unsafe and unauditable.

## Decision

Implement Phase 4 inside the Central API modular monolith with PostgreSQL as the sole
material authority. Use immutable movement and genealogy evidence, transactionally
maintained balances, explicit Lot/Serial and Container identities, Phase 3 task
binding, request idempotency, forced RLS, audit Outbox, and database guards for
negative balance and global Serial quantity.

Treat external ERP/WMS input as a versioned observation. Persist the complete
simulated payload and hash, create discrepancy cases, and forbid observation import
from directly changing inventory. Apply a discrepancy only through a separately
authorized compensating movement after checking that the expected balance is still
current.

## Alternatives

- Promote `MemoryStore` inventory or `part_queue_shadow`: rejected because both are
  simulation/projection state and do not provide transaction or lineage authority.
- Derive inventory from Phase 3 good quantity: rejected because output accounting
  does not identify material, lot, location, container, or disposition.
- Let WMS snapshots overwrite stock: rejected because ownership conflict and data
  loss would be silent.
- Adopt event sourcing for every material aggregate immediately: deferred because
  append-only ledgers plus relational balances satisfy the current gate with fewer
  unproven replay and operations requirements.
- Split an inventory microservice: deferred until independent ownership, deployment,
  scale, and failure-boundary evidence justify it.

## Consequences

- Accepted material writes require PostgreSQL; SQLite remains a hermetic test/local
  fallback.
- Balance is a guarded current-state table derived in the same transaction as an
  immutable movement, not an independent fact source.
- Simulation and external snapshots remain labelled and cannot become physical truth.
- Validation writes durable records and therefore uses unique visible prefixes.
- Quality disposition and release remain a separate Phase 5 authority.

## Security Impact

Routes require JWT permission `inventory:manage`; identity comes from verified
claims. All 10 new tables are tenant/site scoped with forced RLS. The current broad
permission is acceptable only for this engineering gate; pilot deployment requires
segregated count, approve, and adjust responsibilities.

## Data And Migration Impact

Two additive checksum-ledger migrations create 10 tables, indexes, RLS policies,
append-only evidence guards, nonnegative balance checks, and a globally serialized
Serial quantity guard. No Phase 1-3 table is destructively changed.

## Rollback

Retain all accepted movement, genealogy, import, reconciliation, audit, and Outbox
evidence when rolling application code back. Destructive recovery requires a
verified database restore and business reconciliation.

## Evidence

- `docs/governance/PHASE4_GATE.md`
- `docs/validation/TEST_EVIDENCE/PHASE4_MATERIAL_FLOW_2026-07-14.md`
- `scripts/check_phase4_material_flow.py`

## Reviewers

Engineering gate only. Inventory control, production, quality, finance, OT/security,
ERP/WMS owners, and plant/business owners have not approved a pilot or production
release.
