# Phase 4 Baseline Audit

## Decision

`FAIL - 0/4 GATES SATISFIED BEFORE IMPLEMENTATION`

Audit date: 2026-07-14. Phase 3 has passed. This record evaluates WIP, inventory,
and genealogy without promoting simulation, seed cards, or a mutable shadow queue
into material authority.

## Required Capability Versus Repository Fact

| Requirement | Repository fact before Phase 4 | Baseline |
|---|---|---|
| Warehouse and WIP Location | No governed warehouse/location master or location balance exists | ABSENT |
| Lot/Serial | `PartQueueItem.part_id`, `batch_id`, and `parent_part_id` are generated simulation strings without material/UOM/location/execution binding | ABSENT |
| Container | No container identity, type, capacity, content, seal, or lifecycle exists | ABSENT |
| Issue/Consume/Produce/Return | Phase 3 accepts operation quantities but records no material movement; no movement API exists | ABSENT |
| Split/Merge | Downstream `PartQueueItem` creation is a one-parent simulation chain, not governed quantity split/merge | ABSENT |
| Transfer | Existing transfer routes test data/file delivery to a node; they do not move material or update a balance | ABSENT |
| Scrap/Rework | Phase 3 quantity categories account operation output only; they create no disposition, material movement, or rework route | FOUNDATION LABEL ONLY |
| Genealogy | General replay and `parent_part_id` cannot query complete forward/reverse material lineage | ABSENT |
| Reconciliation | No expected/observed balance, discrepancy case, reason, approval, or compensation exists | ABSENT |
| ERP/WMS simulated contract | `market-simulator` and seeded stock are random what-if inputs, not a versioned external inventory contract | ABSENT |

## Existing Objects That Must Not Be Reclassified

- `InventoryItem.current_stock` is generated in `MemoryStore.seed_demo()` and is
  neither persisted nor derived from movements.
- `InventoryItem.pressure_score` and `expected_days` are dashboard/planning
  projections, not inventory facts.
- `part_queue_shadow` is a mutable compatibility/shadow table. Its producer mutates
  memory first, upserts the latest row, caps the cache at 500, and may derive flow
  directly from simulated heartbeat output.
- `PartQueueItem.status=completed` proves only completion of that simulated queue
  step. It does not establish material production, availability, lot disposition,
  or inventory ownership.
- Phase 3 `operation_quantity_reports` prove accepted operation accounting. They do
  not identify consumed lots, produced lots/serials, containers, or locations.
- `/transfer/*` data/file tests prove bytes and checksums, not material transfer.
- Replay of heartbeat/part queue/audit data is not forward or reverse product
  genealogy.

## Live Route Evidence

Authenticated runtime probes before implementation returned:

| Probe | Result |
|---|---|
| `GET /inventory` | HTTP 200; five seeded cards with stock/safety/pressure fields only |
| `GET /part-queue` | HTTP 200; nine current simulation items, eight completed and one ready |
| `POST /inventory/movements` | HTTP 405 |
| `GET /genealogy/BASELINE` | HTTP 404 |
| `POST /inventory/reconcile` | HTTP 405 |

## First Authoritative Vertical Slice

1. Create governed Warehouse and Location masters with explicit inventory/WIP types.
2. Create a Lot or Serial identity bound to a Phase 2 Material/Product and canonical
   UOM; optionally place it in a governed Container.
3. Record every Issue, Consume, Produce, Return, Transfer, Split, Merge, Scrap, and
   Rework action as an append-only movement with a globally unique idempotency key.
4. Bind execution-related movements to an existing Phase 3 Work Order/Operation Task.
5. Maintain balances transactionally from movements and reject any write that would
   make a non-virtual location/lot balance negative.
6. Store parent/child genealogy edges with quantity and movement evidence; query both
   downstream descendants and upstream ancestors.
7. Record reconciliation observations and discrepancies. A difference creates an
   open case; it never overwrites expected balance. Adjustment requires a separate
   reasoned/authorized compensating movement.
8. Define a strict versioned ERP/WMS simulation import contract whose records remain
   explicitly simulated and idempotent.
9. Write business movement, balance, genealogy, audit, and audit Outbox in one
   PostgreSQL transaction under forced RLS.

## Phase 4 Gate At Baseline

| Gate | Result | Reason |
|---|---|---|
| Forward and reverse traceability | FAIL | No authoritative lineage graph or query |
| No negative inventory/WIP | FAIL | No governed movement-derived balance exists |
| Retransmission does not double-count | FAIL | No material movement idempotency contract |
| Discrepancy cannot be silently overwritten | FAIL | No reconciliation case or compensating-adjustment workflow |

The first red implementation test must target this new PostgreSQL authority. Legacy
inventory cards and `part_queue_shadow` remain compatibility/simulation projections.
