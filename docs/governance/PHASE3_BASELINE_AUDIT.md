# Phase 3 Baseline Audit

## Decision

`FAIL - 0/5 GATES SATISFIED BEFORE IMPLEMENTATION`

Audit date: 2026-07-14. Phase 2 has passed. This record evaluates the next stage
without reclassifying compatibility, simulator, or dashboard structures.

## Required Capability Versus Repository Fact

| Requirement | Repository fact before Phase 3 | Baseline |
|---|---|---|
| Production Order | `AllocationOrder` and `ProductionPlanIn` are free-form compatibility/simulation records without governed revision binding or execution state | ABSENT |
| Work Order execution | Phase 2 `work_orders` authoritatively binds revisions and can be released, but has no operation execution aggregate | PARTIAL FOUNDATION ONLY |
| Operation Task and Assignment | `DispatchTask` is a planner projection; Phase 2 assignment JSON is a release-time binding, not an execution task/assignment ledger | ABSENT |
| Setup and Start/Pause/Resume/Complete | No durable legal-transition state machine exists | ABSENT |
| Quantity Report and conservation | Heartbeat counters and `PartQueueItem` transitions are simulated observations/projections; no accepted execution quantity transaction exists | ABSENT |
| Hold/Close | Alarm/command closure does not close a work operation | ABSENT |
| Downtime | No operation-linked downtime ledger exists | ABSENT |
| Status History and Replay | General event/audit history cannot deterministically rebuild a production-order/work-order/operation aggregate | ABSENT |

## Existing Data That Must Not Be Reclassified

- `ProductionPlanIn.route: list[str]` is not an effective Routing revision.
- `DispatchTask.status` is not an operation execution state machine.
- SimPy heartbeat `finished_quantity` is simulated telemetry, not an accepted
  quantity report or completion proof.
- `PartQueueItem.status=completed` is a digital-twin flow projection, not a governed
  work-operation completion.
- HTTP 200 from a node command, AI response, or simulator heartbeat is not production
  completion evidence.

## First Vertical Slice

1. Create a durable Production Order for a governed Product.
2. Attach one Phase 2 released Work Order with exact revisions and resources.
3. Release the Production Order and dispatch immutable Operation Tasks from the bound
   Routing revision.
4. Execute legal setup/start/pause/resume/hold/downtime transitions only.
5. Accept idempotent good/scrap/rework quantity reports without exceeding planned
   quantity.
6. Reject completion until quantity conservation and a non-empty evidence reference
   are both present.
7. Complete and close operations, derive Work Order/Production Order aggregate state,
   and replay all status/quantity/downtime history from PostgreSQL.
8. Write every accepted transition to durable status history, audit, and transactional
   audit Outbox.

## Phase 3 Gate At Baseline

| Gate | Result | Reason |
|---|---|---|
| Status cannot jump arbitrarily | FAIL | No operation state machine |
| Completion has evidence | FAIL | No completion transaction/evidence field |
| Quantity is conserved | FAIL | No governed quantity report ledger |
| HTTP 200 is not completion | FAIL | No separate execution completion authority |
| Frontend owns no business fact | FAIL/UNPROVEN | No Phase 3 backend contract exists for the frontend to consume |
