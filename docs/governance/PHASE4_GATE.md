# Phase 4 Gate Record

## Status

`PASS - 2026-07-14 - DIGITAL-TWIN/ENGINEERING GATE ONLY`

Phase 4 now has an authoritative material-flow, inventory/WIP balance, lot/serial,
container, genealogy, and reconciliation vertical slice. This gate proves software
behavior against the live PostgreSQL runtime. It does not prove physical stock,
connect a plant WMS/ERP, or authorize production use.

## Baseline

`PHASE4_BASELINE_AUDIT.md` recorded all four gates as failed. Seeded inventory
cards, `part_queue_shadow`, SimPy part flow, operation quantity reports, and file
transfer APIs were explicitly rejected as material or inventory authority. The
first `/material-flow/*` red test returned HTTP 405.

## Implemented Capability

- Governed Warehouse, inventory/WIP Location, Container, Lot, and Serial identities
  bind to Phase 2 Material and canonical UOM records.
- Receipt, Issue, Consume, Produce, Return, Transfer, Scrap, Rework, and explicit
  Adjustment movements update location/container balances in one transaction.
- Execution-sourced Consume, Produce, and Rework require a compatible Phase 3
  Operation Task state. A task acknowledgement or heartbeat cannot move material.
- Split, Merge, Consume/Produce transformation, and Rework use immutable movement
  legs and parent/child genealogy edges with quantity and evidence.
- Forward descendants and reverse ancestors are reconstructed recursively from the
  PostgreSQL genealogy ledger.
- Versioned ERP/WMS simulation snapshots are stored in full with a payload hash and
  an explicit `simulated` source. A repeated import returns the original result.
- A difference creates an open reconciliation case without changing inventory.
  Adjustment requires a separate reason, evidence, actor, and compensating movement.
- Every accepted mutation writes its business facts, audit row, and NATS audit
  Outbox envelope in one transaction. Injected Outbox failure rolls everything back.

## Business Authority And Invariants

PostgreSQL is the sole Phase 4 authority. `MemoryStore` inventory cards,
`part_queue_shadow`, heartbeat WIP, SimPy output, browser state, NATS receipts, and AI
text cannot create a material fact. Balances are transactionally derived by accepted
movements; they are not independently editable through an API.

Application checks and database guards jointly enforce:

- no balance below zero;
- one serial identity represents at most one unit across all locations;
- movement, transformation, genealogy, and external-import evidence is append-only;
- movement/import/transformation identifiers are idempotent request keys;
- split, merge, and rework preserve material, UOM, and quantity;
- conversion changes require explicit conversion evidence;
- genealogy cannot contain self-reference or cycles;
- reconciliation refuses stale adjustment when inventory changed after observation.

PostgreSQL serial guards lock the parent Lot row before summing all location
balances, preventing concurrent writers from creating two units for one serial.

## Data And Migrations

| Migration | Purpose | Live status |
|---|---|---|
| `2026.07.14-phase4-material-flow` | 10 scoped material, location, movement, balance, genealogy, import and reconciliation tables | Applied once with checksum |
| `2026.07.14-phase4-balance-invariant-guards` | Global serial quantity database guard | Applied once with checksum |

Live PostgreSQL evidence:

- 10/10 Phase 4 tables have RLS enabled and forced.
- The runtime role is non-superuser and has no `BYPASSRLS`.
- Alternate tenant/site scope returned zero Phase 4 rows.
- Direct movement rewrite, negative balance, and duplicate serial-balance probes were
  rejected by PostgreSQL.
- Together with earlier phases, 57 current authoritative tables are forced-RLS
  scoped.

## Interfaces, Authorization, And Audit

Generated OpenAPI v1 now contains `/material-flow/*` routes for master identities,
movements, balances, transformations, genealogy, external snapshots, and approved
reconciliation adjustment. Mutations require persisted JWT permission
`inventory:manage`; a viewer receives HTTP 403. Actors come from verified JWT
claims. Business conflicts return HTTP 409 with a stable `detail.code`.

## Test And Runtime Evidence

- Focused Phase 4 suite: 9 passed.
- Full Central API suite: 226 passed.
- Unified verification passed contracts, secret/ACL checks, all Python and Go
  services, Dashboard 69 tests and production build, correctness lint, strict
  runtime, and Phase 1/3/4 live database gates.
- Runtime: Central API and Dashboard healthy; 3/3 simulated production nodes fresh;
  PostgreSQL primary; NATS shadow; DeepSeek `deepseek-v4-pro` source `api`, status
  `live`.
- Live validation prefix `P4G071321194200A8` accepted Issue/Return/Consume/Produce,
  idempotent movement and Split, recursive genealogy, simulated WMS discrepancy,
  approved adjustment, and closed its Phase 3 task/order chain.

## Rollback And Recovery

Both migrations are additive. Application rollback may retain all Phase 4 tables and
guards. Accepted movement, genealogy, import, audit, and Outbox evidence must not be
deleted or rewritten. Destructive rollback requires verified PostgreSQL restore and
business reconciliation; that restore drill remains an open production gate.

## Non-Claims And Residual Scope

- No physical barcode/RFID, scale, gauge, PLC, CNC, ERP, WMS, or OPC UA connector is
  implemented. External inventory imports are deliberately labelled simulated.
- No quality inspection plan, specification, sampling, measurement, nonconformance,
  disposition, CAPA, or authorized quality release exists yet.
- The Phase 4 adjustment permission is broad for the current engineering runtime;
  segregation of inventory observer, counter, approver, and adjuster duties remains
  required before pilot use.
- No production load, multi-host partition, backup restore, HA, plant validation, or
  business owner acceptance has been proven.

## Formal Gate

| Gate | Evidence | Result |
|---|---|---|
| Forward and reverse traceability | Split/Merge tests plus live recursive descendants/ancestors | PASS |
| No negative inventory/WIP | Atomic conditional balance writes plus SQLite/PostgreSQL database rejection | PASS |
| Retransmission does not double-count | Movement, transformation, and external-import retry returns original row | PASS |
| Discrepancy cannot be silently overwritten | Snapshot leaves balance unchanged; open case plus explicit adjustment movement | PASS |

The first unmet stage is now Phase 5: quality operations.

Current-state note: Phase 5 subsequently passed. The preceding line preserves the
Phase 4 boundary at its validation time; see `PHASE5_GATE.md` for current status.
