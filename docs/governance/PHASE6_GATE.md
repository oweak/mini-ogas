# Phase 6 Gate Record

## Status

`PASS - 2026-07-14 - DIGITAL-TWIN/ENGINEERING GATE ONLY`

Phase 6 now has a PostgreSQL-authoritative maintenance and tooling vertical slice.
It governs assets, criticality, maintenance requests and orders, preventive plans,
versioned checklists, failure/cause/remedy coding, spare consumption, downtime,
tool life, calibration evidence, independent verification, and production impact.
This is software evidence in the local digital-twin runtime. It is not CMMS, PLC,
CNC, sensor, calibration-laboratory, or plant maintenance acceptance evidence.

## Baseline

`PHASE6_BASELINE_AUDIT.md` recorded all four Phase 6 gates as failed. Existing
equipment was flat Phase 2 identity, Phase 3 downtime was only a task pause record,
Phase 5 Gauge calibration was a quality reference, and simulated `tool_wear` plus AI
root-cause text had no maintenance authority. Authenticated maintenance endpoint
probes returned HTTP 405.

## Implemented Capability

- Maintenance Assets bind one-to-one to governed Phase 2 Equipment, support a parent
  hierarchy, preserve criticality, and expose Active, Degraded, Out-of-service, and
  Retired software states.
- Failure, Cause, and Remedy codes are separate governed references. AI text and an
  alarm description cannot substitute for these accepted maintenance facts.
- Maintenance Checklists are versioned Draft, Approved, Effective, Superseded, or
  Retired definitions with immutable ordered items and one effective revision.
- A Maintenance Request records asset, source type/reference, observation time,
  priority, description, and actor. Alarm is one request source; it never creates a
  completion or verification fact.
- A Maintenance Order binds an open Request, Asset, assigned governed Personnel,
  effective Checklist, planned interval, production impact, and optional Phase 3
  Operation Task/Downtime.
- The order state path is Draft -> Approved -> In progress -> Work completed ->
  Verified, with optional later closure. Work completion requires all required
  checklist items to pass plus governed failure/cause/remedy and work evidence.
- Verification requires a separate `maintenance:verify` identity and records
  Restored, Degraded, or Not restored plus a verification reference. The work
  completer cannot verify the same order.
- Preventive Plans bind Asset, effective Checklist, interval, due time, and production
  impact. Due generation creates a durable Request and draft Order and advances the
  next due time without pretending the maintenance was performed.
- Phase 4 remains quantity authority for spare consumption. A Consume movement must
  bind exactly one Operation Task or Maintenance Order; Phase 6 records the immutable
  spare-use relation to that same accepted movement.
- Tool identity, life limit/usage unit, assignment, append-only life event, calibration
  requirement, due time, and calibration result are durable. Over-life or failed/
  expired calibration blocks Operation Task start/resume.
- Every accepted mutation writes business facts, status history where applicable,
  audit, and a NATS audit Outbox envelope in one transaction.

## Business Authority And Invariants

PostgreSQL is the sole Phase 6 authority. Alarm status, simulated temperature,
heartbeat `tool_wear`, dashboard cards, rules, AI diagnosis, HTTP success, and a
closed popup cannot complete maintenance.

Application checks and database guards jointly enforce:

- governed Equipment and Personnel references and tenant/site scope;
- immutable Checklist items and one effective Checklist revision;
- legal Maintenance Order transitions and immutable order identity, approval, work,
  and verification evidence;
- required passing Checklist evidence before Work completed;
- independent verification after Work completed;
- active equipment-unavailable maintenance blocks a Phase 3 task at both application
  and database levels;
- a running task must enter governed Phase 3 downtime before bound maintenance starts;
- a linked downtime belongs to the same Operation Task and may bind one order;
- tool-life events and calibration events are append-only and update tool readiness
  through database triggers;
- over-life and invalid/expired calibration block task start/resume;
- a Consume movement has exactly one production or maintenance authority;
- spare use references a real Phase 4 Consume movement authorized by the same order;
- the Operator role can execute maintenance but owns zero verification grants.

## Data And Migrations

| Migration | Purpose | Live status |
|---|---|---|
| `2026.07.14-phase6-maintenance-operations` | 14 scoped Asset, code, Checklist, request/order, PM, spare, tool, life, calibration and history tables | Applied once with checksum |
| `2026.07.14-phase6-maintenance-invariant-guards` | Work/checklist, independent verification, tool/calibration and task interlocks | Applied once with checksum |
| `2026.07.14-phase6-mro-movement-binding` | Add Maintenance Order authority to Phase 4 Consume movement | Applied once with checksum |
| `2026.07.14-phase6-maintenance-lifecycle-guards` | Lock legal order lifecycle and accepted approval/work/verification evidence | Applied once with checksum |

Live PostgreSQL evidence:

- 14/14 Phase 6 tables have RLS enabled and forced.
- Alternate tenant/site scope returned zero rows across all Phase 6 tables.
- Direct checklist-result rewrite, same-actor verification, verified-evidence rewrite,
  task-start bypass, and unbound Consume insertion were rejected by PostgreSQL.
- The Operator role has zero `maintenance:verify` grants.
- Together with earlier phases, 81 current authoritative tables are forced-RLS
  scoped.

## Interfaces, Authorization, And Audit

Generated OpenAPI v1 exposes `/maintenance/*` routes for Assets, codes, Checklists,
Requests, Orders, Checklist results, work completion, independent verification,
spares, Tools, life events, calibrations, and preventive plans. Responsibilities are
split into `maintenance:manage`, `maintenance:execute`, and `maintenance:verify`.
System Admin owns all three for the engineering runtime. Dedicated Planner,
Technician, and Verifier roles separate duties; the default Operator receives only
execution permission.

Business conflicts use HTTP 409 with stable `detail.code`; missing permission is
HTTP 403. Actor identity comes only from a verified JWT. No request field may name a
verifier or grant itself authority.

## Test And Runtime Evidence

- Focused Phase 6 suite: 9 passed.
- Phase 4/5/6 cross-domain suite: 27 passed.
- Full Central API suite: 244 passed.
- Unified `scripts/verify-miniogas.ps1 -RequireAiUnlocked` gate passed end to end:
  244 Central API, 35 simulator, 4 AI dispatcher, 31 CLI/workflow, 69 Dashboard,
  Go node-agent/supervisor, contract, secret, ACL, build, lint, strict-runtime,
  and live Phase 1/3/4/5/6 checks all passed.
- Generated OpenAPI/manifest and contract-current test pass.
- Phase 6 files and live gate pass Ruff; complete application correctness lint passes.
- Runtime restarted in a fresh session with PostgreSQL primary, 3/3 simulated nodes,
  and DeepSeek source `api`, status `live`.
- Latest unified live prefix `P6G07132222559859` persisted four Maintenance Orders and
  37 maintenance audit records. It closed a real Phase 3 downtime, linked a Phase 4
  spare Consume movement, blocked an over-life Tool task, and generated a due
  preventive Request/Order.
- All five direct PostgreSQL bypass probes passed, 14 RLS policies were forced, and
  cross-scope row count was zero.

## Gate Failure Evidence

The gate was not weakened when implementation defects appeared:

1. The first direct verification probe found that a trigger listening only to
   `UPDATE OF status` did not protect `verified_by` from a later single-column
   rewrite. The probe changed a validation-only `P6G...` row and the gate failed.
   A new migration now locks legal transitions and accepted approval/work/
   verification evidence on every update.
2. A later unbound-Consume probe was rejected by PostgreSQL, but the gate looked for
   a shortened error message that differed from the already applied migration. The
   database contained no probe row. Source and gate now retain the original stable
   migration text so fresh and existing databases agree.

Failed validation prefixes remain engineering evidence and are not release evidence.
Only the successful prefix above supports this gate.

## Rollback And Recovery

All four migrations are additive. Application rollback retains Phase 6 tables,
foreign keys, guards, audit, history, Checklist results, spare links, tool/calibration
events, and Outbox evidence. Accepted evidence must not be rewritten or deleted.
Destructive rollback requires a verified PostgreSQL restore plus maintenance,
production, and inventory reconciliation; no such restore drill is yet proven.

## Non-Claims And Residual Scope

- No CMMS/EAM, PLC, CNC, SCADA, vibration, temperature, oil-analysis, tool preset,
  calibration-laboratory, barcode, RFID, ERP, or WMS connector is implemented.
- Asset state is accepted software state, not independent physical readback.
- Calibration and tool-life inputs are governed manual/API facts, not authenticated
  device counters or laboratory certificates.
- Preventive Plan generation creates due work only; it does not perform, approve, or
  verify maintenance.
- Spare consumption is software inventory authority; physical issue confirmation,
  costing, procurement, and external stock acknowledgement are absent.
- No maintenance dashboard workbench, electronic signature, retention policy, load
  test, restore drill, HA, field procedure validation, or plant approval is proven.
- AI may explain evidence later, but cannot complete work, verify restoration, change
  Asset state, consume a spare, or release a production task.

## Formal Gate

| Gate | Evidence | Result |
|---|---|---|
| Alarm is not maintenance completion | Alarm creates Request; direct/premature verification rejected; work and Checklist required | PASS |
| Maintenance completion has verification | Work completed remains blocking until separate verifier records restoration evidence | PASS |
| Tool life affects task | Over-life and calibration-invalid Tool assignments return stable 409 and DB task interlock rejects bypass | PASS |
| Downtime is linked to schedule | Running Operation Task enters durable downtime; order binds the same task/downtime; resume occurs only after verification and downtime close | PASS |

The first unmet stage is now Phase 7: data platform, Historian, and projections.
