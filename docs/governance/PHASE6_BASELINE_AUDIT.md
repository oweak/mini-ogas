# Phase 6 Maintenance, Equipment And Tooling Baseline Audit

## Audit Status

`FAIL - 2026-07-14 - 0/4 PHASE GATES SATISFIED`

This is the required pre-implementation record. It distinguishes existing equipment,
alarm, operation-downtime, and Gauge-reference data from an authoritative maintenance
workflow. No Phase 6 capability is credited from UI text, simulated wear, an alert,
or an HTTP acknowledgement.

## Repository Scope Examined

- `services/central-api/app/core/phase2_schema.py`
- `services/central-api/app/core/phase3_schema.py`
- `services/central-api/app/core/phase5_schema.py`
- Central API domains, repositories, routers, tests, and generated OpenAPI v1
- simulated node telemetry, rule/AI diagnosis, alarm and command paths
- live authenticated endpoint behavior at `http://127.0.0.1:8080`

## Existing Facts That Do Not Satisfy Phase 6

| Existing behavior | What it actually proves | Missing maintenance authority |
|---|---|---|
| Phase 2 `equipment` and `equipment_capabilities` | Flat governed equipment identity and capability | Asset parent/child hierarchy, criticality, lifecycle, maintenance state |
| Alert/rule/AI diagnosis | An observed or inferred issue and proposal text | Maintenance Request/Order, assignment, checklist, failure/cause/remedy and verification |
| Phase 3 `operation_downtime` | Durable pause interval bound to one Operation Task | Asset downtime cause/maintenance order, schedule/capacity impact and recovery verification |
| Simulated `tool_wear`/telemetry | Digital-twin observation | Governed Tool identity, life counter/limit, calibration, task eligibility and replacement |
| Phase 5 `gauges` | Quality Gauge reference with calibration status/period | General tool/calibration event history, out-of-service enforcement and calibration workflow |
| Command acknowledgement/effect verifier | Logical command lifecycle over simulated telemetry | Maintenance completion evidence or independent equipment restoration verification |

## Implementation Item Audit

| Required item | Baseline result | Evidence |
|---|---|---|
| Asset hierarchy | Absent | Equipment has organization unit only; no parent asset relation |
| Criticality | Absent | No governed criticality field/model |
| Maintenance Request/Order | Absent | No tables, domain state machine, repository or routes |
| Preventive Plan | Absent | No interval/meter plan or due-generation path |
| Checklist | Absent | No versioned task/check result/evidence model |
| Failure/Cause/Remedy | Absent | AI `root_cause` text is a proposal, not coded maintenance evidence |
| Spare Use | Absent | Phase 4 material movement has no maintenance-order consumption binding |
| Downtime | Partial only | Phase 3 task downtime exists but is not an asset maintenance lifecycle |
| Tool Life | Absent | Simulated wear is not a governed tool meter or task constraint |
| Calibration | Partial only | Phase 5 Gauge validity reference exists; no calibration event/workflow |
| Verification | Absent | No maintenance completion state requiring independent evidence |
| Production Impact | Absent | No maintenance Order to Operation Task/schedule/capacity impact relation |

## Authenticated API Probes

The running PostgreSQL-primary Central API was accessed with a valid administrator
JWT. Empty POST probes returned:

| Route | HTTP result |
|---|---|
| `/maintenance/requests` | 405 |
| `/maintenance/orders` | 405 |
| `/maintenance/preventive-plans` | 405 |
| `/maintenance/tools` | 405 |
| `/maintenance/calibrations` | 405 |

These probes establish the red baseline. They are not treated as implementation.

## Gate Assessment

| Phase 6 gate | Baseline | Reason |
|---|---|---|
| Alarm is not maintenance completion | FAIL | No maintenance aggregate exists; alarm state and maintenance evidence cannot be compared |
| Maintenance completion has verification | FAIL | No completion/verification transition exists |
| Tool life affects task | FAIL | No governed Tool/life authority is consulted during dispatch/start |
| Downtime is linked to scheduling | FAIL | Phase 3 downtime pauses one task but does not constrain or notify a governed schedule/capacity owner |

## First Implementable Vertical Slice

The smallest honest slice must create PostgreSQL-authoritative Asset, Maintenance
Request, Maintenance Order, checklist execution, failure/cause/remedy, verification,
Tool/life/calibration, spare usage, and production-impact records. It must bind to
existing governed Equipment, Phase 3 Operation Task/downtime, and Phase 4 material
movement instead of duplicating those authorities.

The first red tests must prove:

1. resolving an Alert cannot complete a Maintenance Order;
2. completion is impossible until required checklist, cause/remedy and verification
   evidence exist;
3. an expired/over-life Tool blocks task eligibility;
4. an active maintenance outage blocks or pauses the bound Operation Task and records
   explicit production impact;
5. all writes are scoped, authorized, audited, idempotent and transactionally paired
   with the Outbox.

## Non-Claims

No CMMS/EAM, sensor meter, tool setter, calibration laboratory, spare-parts store,
ERP, APS, PLC, CNC, or physical maintenance workflow is connected. Phase 6 remains
unimplemented until executable tests and a live PostgreSQL gate replace this failing
baseline.
