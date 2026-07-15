# Phase 2 Baseline Audit

## Decision

`FAIL - 0/4 GATES SATISFIED BEFORE IMPLEMENTATION`

Audit date: 2026-07-13. Repository baseline: the same dirty working tree accepted by Phase 1; no unrelated user change was reverted.

## Required Capability Versus Repository Fact

| Requirement | Repository fact before Phase 2 | Baseline status |
|---|---|---|
| Enterprise/Site/Area/Line/Cell | Only deployment `tenant_id/site_id` and free-form workshop/node labels exist | ABSENT |
| Equipment and capability | `Machine` is an in-memory/dashboard operational model; no governed equipment master or capability relation exists | ABSENT |
| Product/Material/UOM | Product codes/names occur in inventory and plans without referential master data | ABSENT |
| BOM | No BOM model, table, revision, approval or effective state exists | ABSENT |
| Routing/Operation | Plans carry a free-form `list[str]` route; no operation revision or capability/skill requirement exists | ABSENT |
| Personnel/Skill/Qualification | JWT users/roles exist, but there is no separate personnel identity or qualification evidence | ABSENT |
| Calendar/Shift | No governed calendar or shift table exists | ABSENT |
| Document Revision | No controlled document/revision/effective record exists | ABSENT |
| Approval/Effective | Safety approvals exist for operational actions, not master-data revision approval/effectivity | ABSENT |
| Work-order revision binding | `DispatchTask` and production plan are not work orders and do not bind BOM/routing/document revisions | ABSENT |

## Existing Data That Must Not Be Reclassified

- `ProductionPlanIn.route` is a compatibility list, not an approved routing revision.
- `Machine` and heartbeat `machine_code` are runtime projections, not an equipment register.
- JWT role permission is account authorization, not proof that a named person is qualified for an operation.
- SimPy process-time/capacity values are simulation configuration, not approved equipment capability master data.
- Product strings in demo seeds, inventory and market signals are not governed Product/Material master records.

## First Vertical Slice

The first real slice will release a work order only when all of the following durable, scoped facts exist:

1. Product and BOM revision are approved/effective and match.
2. Routing revision is approved/effective and matches the product.
3. Every routing operation has an equipment assignment with the required capability.
4. Every routing operation has a personnel assignment with a currently valid required-skill qualification.
5. Every operation-required controlled document has an effective revision explicitly bound to the work order.
6. The work order stores immutable revision IDs rather than latest-version lookups.
7. Creation, approval, effectivity, qualification and release are written to the durable audit log.

This slice introduces no connector, PLC command, generated measurement, AI authority or simulated master fact.

## Phase 2 Gate At Baseline

| Gate | Result | Reason |
|---|---|---|
| Work order binds exact BOM/Routing/document revisions | FAIL | No such entities |
| Account is distinct from operation qualification | FAIL | Personnel/qualification domain absent |
| Master-data changes are auditable | FAIL | No master-data mutations |
| Historical revision cannot be overwritten | FAIL | No revision persistence or immutability control |
