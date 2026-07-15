# Phase 2 Through Phase 6 Data Dictionary

Last verified: 2026-07-14. Every table below contains `id`, `tenant_id`, `site_id`,
creator/issuer identity where applicable, and a creation timestamp. PostgreSQL RLS is
enabled and forced for the application role.

| Table | Stable business key | Important references/fields | Authority and invariant |
|---|---|---|---|
| `organization_units` | `unit_code` | `unit_type`, `parent_id` | Enterprise/Site/Area/Line/Cell hierarchy; no skipped level |
| `uoms` | `uom_code` | `dimension`, positive `scale` | Canonical quantity unit definition |
| `materials` | `material_code` | `material_type`, `base_uom_id` | Governed raw/intermediate/finished/consumable material |
| `products` | `product_code` | finished `material_id` | Product identity mapped to a finished material |
| `equipment` | `equipment_code` | type, Cell `organization_unit_id`, active | Governed equipment identity, not heartbeat state |
| `equipment_capabilities` | equipment + `capability_code` | name | Release requires exact capability on assigned equipment |
| `skills` | `skill_code` | `level_min` 1..10 | Governed skill requirement |
| `personnel` | `personnel_code` | optional `linked_username`, active | Human/resource identity distinct from login account |
| `personnel_qualifications` | person + skill + valid-from | level, valid period, evidence | Release requires current period and sufficient level |
| `calendars` | `calendar_code` | IANA timezone | Governed working calendar |
| `calendar_shifts` | calendar + `shift_code` | start/end `HH:MM` | Shift belongs to exactly one calendar |
| `controlled_documents` | `document_code` | type, title | Parent identity for controlled instructions/documents |
| `document_revisions` | document + `revision` | content JSON, approval/effectivity | Identity/content update and delete blocked |
| `boms` | `bom_code` | `product_id` | Parent identity for product BOM |
| `bom_revisions` | BOM + integer revision | immutable item list | Positive quantities and compatible UOM dimensions |
| `routings` | `routing_code` | `product_id` | Parent identity for product Routing |
| `routing_revisions` | Routing + integer revision | immutable ordered operations | Unique sequence/code; capability, skill, document references |
| `work_orders` | `work_order_code` | exact revision IDs, quantity, schedule, assignments | `draft -> released`; release validates every bound fact |

Revision status values are `draft`, `approved`, `effective`, and `superseded`.
Work-order Phase 2 status values are `draft`, `released`, and reserved `cancelled`.
Only `draft -> released` is exposed by the Phase 2 route. Phase 3 execution references
the released row without rewriting its engineering binding.

## Phase 3 Execution Tables

All tables below are tenant/site scoped and have forced PostgreSQL RLS.

| Table | Stable business key | Important references/fields | Authority and invariant |
|---|---|---|---|
| `production_orders` | `production_order_code` | product, quantity, priority, due date, status | Exact attached Work Order quantity; guarded lifecycle |
| `production_order_work_orders` | Work Order | Production Order + Phase 2 Work Order | A Work Order belongs to at most one Production Order |
| `work_order_execution` | Phase 2 Work Order | Production Order, execution status/times | Aggregate derived from durable Operation Tasks |
| `operation_tasks` | Work Order + Routing sequence | exact Routing revision, operation, plan, state, evidence | Strict state machine; predecessor/setup/completion guards |
| `operation_task_assignments` | Operation Task | governed equipment and personnel IDs | Materialized released assignment, one per task |
| `operation_setups` | Operation Task | parameters JSON, evidence, actors/times | Setup must complete with evidence before ready |
| `operation_quantity_reports` | `report_id` | good/scrap/rework, evidence, occurrence time | Append-only; cumulative accounted quantity cannot exceed plan |
| `operation_downtime` | `downtime_code` | task, reason, start/end evidence, actors/times | At most one open downtime per task |
| `operation_holds` | generated ID | prior state, reason, hold/release actor/time | At most one open hold; release restores prior state |
| `operation_status_history` | Task + idempotency key | from/to state, action, reason, evidence, actor/time | Append-only deterministic transition history |
| `execution_idempotency` | resource/action/key | request hash, response JSON | Same request returns prior response; changed reuse is rejected |

Phase 3 accounted quantity is `good + scrap + rework` for one operation. It is not an
inventory balance or material genealogy model; those semantics are separately owned
by Phase 4.

## Phase 4 Material Flow Tables

All tables below are tenant/site scoped and have forced PostgreSQL RLS.

| Table | Stable business key | Important references/fields | Authority and invariant |
|---|---|---|---|
| `warehouses` | `warehouse_code` | type, active, creator | Governed storage/WIP/quarantine/scrap/shipping grouping |
| `inventory_locations` | `location_code` | warehouse, location type, active | Exact balance and movement endpoint |
| `material_containers` | `container_code` | type, current registered location, status | Governed tote/pallet/container identity |
| `material_lots` | `lot_code` | Material, UOM, tracking kind, evidence, status | Lot or Serial identity; Serial total cannot exceed one |
| `inventory_balances` | Lot + Location + Container key | material, UOM, nonnegative quantity | Guarded current balance changed only with accepted transaction |
| `inventory_movements` | `movement_id` | type, lot, quantity, endpoints, task/transformation/case, evidence, hash | Append-only, idempotent material fact |
| `material_transformations` | `transformation_id` | type, task, evidence, conversion evidence, hash | Append-only Split/Merge/Consume-Produce/Rework header |
| `genealogy_edges` | transformation + parent + child | parent/child quantities, relation, evidence | Append-only acyclic lineage edge |
| `external_inventory_imports` | `import_id` | provider, contract 1.0, simulated source, full payload/hash | Immutable external observation; never inventory authority |
| `inventory_reconciliation_cases` | `case_code` | expected/observed/variance, status, adjustment evidence | Difference workflow; adjustment is a separate movement |

Movement type is one of Receipt, Issue, Consume, Produce, Return, Transfer, Scrap,
Rework, Adjustment, or a transformation input/output leg. Execution-sourced material
facts reference a Phase 3 Operation Task. `expected_quantity` is the authoritative
balance observed at import time; `observed_quantity` is the external claim. The
external claim changes stock only after a still-current case is explicitly adjusted.

## Phase 5 Quality Tables

All tables below are tenant/site scoped and have forced PostgreSQL RLS.

| Table | Stable business key | Important references/fields | Authority and invariant |
|---|---|---|---|
| `inspection_plans` | `plan_code` + revision | Material, stage, optional operation, status and approval/effectivity evidence | Versioned inspection definition; one effective revision per code |
| `quality_characteristics` | Plan + `characteristic_code` | type, UOM, target/limits, method, sample size, Gauge type, skill/level | Append-only specification and sampling authority |
| `gauges` | `gauge_code` | type, calibration status/period, evidence | Governed reference checked at measurement time; not a physical reading |
| `inspection_lots` | `inspection_lot_code` | plan, Lot/Serial, location, optional task, quantity, status, release evidence | Exact inspected material and lifecycle authority |
| `quality_holds` | `hold_code` | Inspection Lot, material Lot, reason, resolution actor/evidence | One open Hold per Lot; normal material flow is blocked while open |
| `quality_measurements` | `measurement_id` | characteristic/sample, typed value, UOM, method, Gauge, person, result, hash | Append-only idempotent evidence; result must match specification |
| `nonconformances` | `nc_code` | Inspection Lot, Lot, severity, affected quantity, status | Exactly one NC for one failed Inspection Lot in current slice |
| `quality_dispositions` | `disposition_code` | NC, type, reason/evidence, proposer, approver, authorization | Proposal/approval authority for use-as-is, rework, scrap or return |
| `capa_records` | `capa_code` | NC, problem, root cause, action, due time, verification/effectiveness | Basic corrective/preventive action evidence |
| `quality_status_history` | generated ID | resource, from/to, action, evidence, actor/time | Append-only quality state path |

Numeric Pass/Fail is calculated from the effective characteristic limits. A Failed
inspection cannot release unless an approved use-as-is disposition exists. A Passed
inspection remains held until a separately authorized release records actor and
authorization reference.

## Phase 6 Maintenance Tables

All tables below are tenant/site scoped and have forced PostgreSQL RLS.

| Table | Stable business key | Important references/fields | Authority and invariant |
|---|---|---|---|
| `maintenance_assets` | `asset_code` | governed Equipment, optional parent, criticality, status | Maintenance identity and software availability state; one Asset per Equipment |
| `maintenance_codes` | `code` | failure/cause/remedy type, description, active | Governed coded maintenance conclusion; AI text is not a substitute |
| `maintenance_checklists` | code + revision | name, lifecycle, approval/effectivity evidence | Versioned work definition; one effective revision; identity immutable |
| `maintenance_checklist_items` | Checklist + sequence | instruction, required flag | Append-only ordered work requirement |
| `preventive_maintenance_plans` | `plan_code` | Asset, effective Checklist, interval, due time, impact | Due-work authority; generation advances schedule but never completes work |
| `maintenance_requests` | `request_code` | Asset, source/reference, observation, priority, status | Demand/observation fact; Alarm is a source, not completion |
| `maintenance_orders` | `order_code` | Request, Asset, person, Checklist, task/downtime, impact, coded work, verification | Strict Draft/Approved/In-progress/Work-completed/Verified lifecycle and immutable evidence |
| `maintenance_check_results` | Order + Checklist item | result, evidence, actor/time | Append-only pass/fail/not-applicable evidence; required items must pass |
| `maintenance_spare_usages` | `usage_id` | Order, Phase 4 Consume movement, evidence | Immutable purpose link; Phase 4 remains quantity authority |
| `maintenance_tools` | `tool_code` | Asset, type, life limit/used/unit, calibration due, status | Tool readiness authority for assigned Operation Tasks |
| `maintenance_tool_assignments` | Tool + Operation Task | evidence and actor/time | Append-only Tool-to-task binding |
| `tool_life_events` | `event_id` | Tool, usage delta, optional task, evidence/time | Append-only usage; database updates life and Over-life state |
| `calibration_events` | `calibration_code` | Tool, pass/fail, validity, person, evidence | Append-only calibration evidence; database updates readiness |
| `maintenance_status_history` | generated ID | resource, from/to, action, evidence, actor/time | Append-only maintenance state path |

`inventory_movements.maintenance_order_id` is an additive Phase 6 reference. A
Consume movement must bind exactly one `operation_task_id` or
`maintenance_order_id`; production and MRO consumption cannot be unowned or doubly
owned.
