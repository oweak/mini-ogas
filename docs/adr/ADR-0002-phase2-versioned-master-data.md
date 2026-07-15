# ADR-0002: Versioned Phase 2 Master Data In PostgreSQL

## Status

Accepted for the Phase 2 engineering gate on 2026-07-14.

## Context

The compatibility system used free-form product, machine, route, and user strings.
Those values could not prove equipment capability, personnel qualification, or the
exact engineering revision used by a released work order. Phase 2 requires governed
business objects without promoting SimPy, dashboard seed, or `MemoryStore` into an
industrial authority.

## Decision

Use PostgreSQL as the authoritative Phase 2 store behind a modular-monolith domain,
repository, and router boundary. Every object is tenant/site scoped. Engineering
content is represented by immutable Document, BOM, and Routing revision rows with
explicit approval and effectivity. A work order stores exact revision IDs and is
released only after resource capability and qualification validation.

Accepted state changes write an audit row and NATS audit Outbox envelope in the same
database transaction. NATS remains shadow transport; it does not become authority.

## Alternatives

- Extend `MemoryStore`: rejected because restart and concurrent writer semantics are
  unsuitable for governed master data.
- Reclassify simulator profiles and planner routes as masters: rejected because their
  provenance and revision control are inadequate.
- Split a new microservice: deferred because the current scale has no independent
  deployment or ownership need and would add distributed failure modes.
- Store revisions as mutable JSON on parent rows: rejected because it destroys exact
  historical binding.

## Consequences

- Phase 2 writes require PostgreSQL transactions and explicit references.
- Revision content and identity cannot be updated or deleted by the application role.
- One effective revision per parent is enforced in the database.
- Legacy runtime strings remain a separate compatibility projection until Phase 3
  mapping is implemented.
- Base-master correction/retirement requires a later controlled lifecycle.

## Security Impact

All routes require `master-data:manage`. Forced PostgreSQL RLS and explicit scope
predicates protect all 18 new tables. Account authorization and personnel operation
qualification remain distinct.

## Data Impact

Two checksum-ledger migrations add 18 tables, indexes, RLS policies, update/delete
guards, and no destructive change to existing tables.

## Migration

Apply `2026.07.14-phase2-master-data`, then
`2026.07.14-phase2-revision-delete-guard`. Both are repeatable through the migration
ledger and were applied to the local PostgreSQL runtime.

## Rollback

Roll back application code while retaining additive tables. Do not drop revision
tables after data exists. A destructive rollback requires verified backup restore and
explicit governance approval.

## Evidence

`docs/governance/PHASE2_GATE.md` and
`docs/validation/TEST_EVIDENCE/PHASE2_MASTER_DATA_2026-07-14.md`.

## Affected Contracts

Generated OpenAPI `/master-data/*` operations and NATS schema-version 3.0 audit
envelopes.

## Reviewers

Engineering gate review only; business, engineering-document-control, HR/training,
OT, and production owners are still required before pilot.
