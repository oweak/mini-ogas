# Phase 3 Gate Record

## Status

`PASS - 2026-07-14 - DIGITAL-TWIN/ENGINEERING GATE ONLY`

Current-state note: Phase 4 subsequently passed on 2026-07-14. Statements below
that inventory/genealogy were absent describe the Phase 3 gate boundary at closure,
not the current repository.

Phase 3 now has a durable production-order, work-order execution, and operation-task
vertical slice. This gate proves software behavior against PostgreSQL. It does not
authorize production use, connect a physical machine, or claim that validation
orders represent plant production.

## Baseline

`PHASE3_BASELINE_AUDIT.md` recorded all five gates as failed before implementation.
Legacy planner dispatch, `PartQueueItem`, heartbeat counters, SimPy completion, and
HTTP command acknowledgements were explicitly rejected as substitutes for governed
execution facts. The first `/execution/*` red test returned HTTP 405.

## Implemented Capability

- Production Orders bind a governed Phase 2 Product and exact planned quantity.
- Only released Phase 2 Work Orders can be attached; product and aggregate quantity
  must match before Production Order release.
- Dispatch materializes immutable Routing operations and their governed equipment
  and personnel assignments as durable Operation Tasks.
- Setup start/completion, start, pause, resume, hold/release, downtime start/end,
  completion, task close, Work Order close, and Production Order close are explicit
  transactions.
- Every accepted state change has append-only status history. Quantity reports are
  append-only and idempotent by `report_id`.
- Work Order replay is rebuilt from PostgreSQL tasks, assignments, setups, quantity
  reports, holds, downtime, and status history.
- Every accepted mutation writes the business fact, audit row, and NATS audit Outbox
  envelope in one transaction. Injected Outbox failure rolls the mutation back.

## Business Authority

PostgreSQL is the sole Phase 3 authority. `MemoryStore`, planner projections,
dashboard state, SimPy heartbeats, NATS shadow receipts, and AI text cannot create or
complete an execution object. NATS transports audit envelopes in shadow mode; it is
not the order or operation authority. The browser owns no Phase 3 business fact.

## State Machines

```text
Production Order:
draft -> released -> in_progress -> completed -> closed

Work Order execution:
dispatched -> in_progress -> completed -> closed

Operation Task:
dispatched -> setup -> ready -> running -> completed -> closed
                           running <-> paused
dispatched/setup/ready/running/paused -> held -> prior status
running -> paused (downtime start) -> running (downtime end)
```

The repository uses conditional writes and PostgreSQL row locks. A database trigger
also rejects direct illegal status changes. Starting setup additionally requires all
predecessor operations to be complete or closed.

## Quantity And Completion Semantics

- `good_quantity + scrap_quantity + rework_quantity` is the accepted accounted
  quantity for the current operation in this Phase 3 contract.
- A report may not make cumulative accounted quantity exceed planned quantity.
- Database triggers serialize PostgreSQL quantity inserts on the task row and reject
  over-plan writes even when the API is bypassed.
- Completion requires exact equality between accounted and planned quantity plus a
  non-empty durable evidence reference.
- HTTP 200 from setup, start, pause, AI, command, or heartbeat means only that the
  named transaction was accepted; only the guarded completion transition establishes
  completed state.

This accounting model is intentionally narrow. Material consumption, lot yield,
rework loops, inventory movements, and reconciliation belong to Phase 4.

## Data And Migrations

| Migration | Purpose | Live status |
|---|---|---|
| `2026.07.14-phase3-production-execution` | 11 scoped execution tables, indexes, forced RLS, append-only quantity/history guards | Applied once with checksum |
| `2026.07.14-phase3-execution-invariant-guards` | Database-enforced legal transitions, predecessor/setup/completion evidence, quantity conservation | Applied once with checksum |

Live PostgreSQL evidence:

- 11/11 Phase 3 tables have RLS enabled and forced.
- The runtime role is non-superuser and has no `BYPASSRLS`.
- Alternate-site probe sees `1` row in the active scope and `0` in another scope;
  the probe transaction was rolled back.
- Six operation trigger instances are present for append-only evidence, legal
  transitions, and quantity conservation.
- Direct `closed -> running` and direct over-plan quantity probes were rejected and
  rolled back.

## Interfaces And Error Contract

Generated OpenAPI v1 contains the `/execution/*` family for Production Orders,
Work Order dispatch/query/replay/close, Operation Task actions and history, quantity
reports, and downtime. Invalid business transitions return HTTP 409 with stable
`detail.code`; schema errors return 422; missing permission returns 403. Mutation
success responses report the accepted state and never imply later completion.

## Authorization And Audit

- Mutations require persisted JWT permission `execution:manage`.
- `system_admin` has the permission; `operator` receives it for the current local
  policy; a viewer token receives HTTP 403.
- Actors come from verified JWT claims, never request payloads.
- Phase 2 equipment/personnel bindings are materialized at dispatch; account role
  remains distinct from the Phase 2 personnel qualification used for release.
- Audit and Outbox use `run_id=execution`; an Outbox enqueue failure leaves no
  production order and no audit row.

## Test And Runtime Evidence

- `python -m pytest tests/test_phase3_execution.py -q`: 9 passed.
- Full `central-api` suite: 217 passed.
- Unified repository verification passed simulator, Go, AI dispatcher, CLI,
  Dashboard tests/build, correctness lint, secret/ACL, runtime, Phase 1 database,
  and Phase 3 live gates.
- Runtime: 9/9 supervisor processes healthy; 3/3 fresh SimPy nodes; PostgreSQL
  primary; NATS shadow live; DeepSeek `deepseek-v4-pro` source `api`, status `live`.
- Reusable `scripts/check_phase3_execution.py` authenticated against the running
  service, exercised four negative gates, closed a valid order, and replayed six
  ordered statuses plus two accepted quantity reports.

## Rollback And Recovery

Both migrations are additive. Application rollback may retain the tables and guards.
Execution evidence must not be deleted or rewritten during rollback. A destructive
rollback requires a verified PostgreSQL backup restore and reconciliation of audit
Outbox state. Backup/restore drills remain an open production gate.

## Non-Claims And Residual Scope

- No OPC UA, PLC, CNC, ERP, WMS, historian, or other physical/external connector is
  implemented.
- SimPy remains simulated telemetry and cannot issue accepted Phase 3 quantities.
- The validation workflow creates governed engineering test records, not real plant
  qualifications, production approvals, or product genealogy.
- No inventory, lot/serial, material issue/consume/produce, split/merge, transfer,
  genealogy, or reconciliation authority exists yet.
- No production-scale load, multi-host partition, HA, disaster recovery, or plant
  owner acceptance has been proven.

## Formal Gate

| Gate | Evidence | Result |
|---|---|---|
| Status cannot jump arbitrarily | API 409 test plus SQLite/PostgreSQL direct-write trigger rejection | PASS |
| Completion has evidence | Missing evidence returns `COMPLETION_EVIDENCE_REQUIRED`; DB guard enforces evidence | PASS |
| Quantity is conserved | Idempotency/over-plan/exact-total tests plus row-locking DB trigger | PASS |
| HTTP 200 is not completion | Setup/start/pause responses retain non-completed state; completion is separate guarded transaction | PASS |
| Frontend owns no business fact | PostgreSQL repository is sole authority; generated API is the read/write boundary; no browser mutation state | PASS |

At Phase 3 closure the first unmet stage was Phase 4. The current first unmet stage
is Phase 5 quality operations; see `PHASE4_GATE.md`.
