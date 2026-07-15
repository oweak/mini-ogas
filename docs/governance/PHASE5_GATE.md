# Phase 5 Gate Record

## Status

`PASS - 2026-07-14 - DIGITAL-TWIN/ENGINEERING GATE ONLY`

Phase 5 now has a PostgreSQL-authoritative quality-operations vertical slice for
inspection definition, measurement, deterministic evaluation, quality hold,
nonconformance, disposition, authorized release, basic CAPA, and gauge reference.
This gate proves software behavior in the local digital-twin runtime. It does not
prove calibrated device integration, plant procedures, or production authorization.

## Baseline

`PHASE5_BASELINE_AUDIT.md` recorded all four Phase 5 gates as failed. The repository
had a simulated `defect_rate`, automatic legacy `quality_status='accepted'`, and
Scrap/Rework quantity labels, but no governed inspection or quality-release
authority. Authenticated quality endpoint probes returned HTTP 405.

## Implemented Capability

- Versioned Inspection Plans bind a governed Phase 2 Material to receiving,
  in-process, or final inspection and move through Draft, Approved, Effective,
  Superseded, and Retired states.
- Characteristics preserve typed specification, canonical UOM, target and limits,
  method, sample size, gauge type, required skill, and required qualification level.
- Gauge references include type, calibration status, validity period, evidence, and
  actor. They are governed records, not automatic readings from physical gauges.
- Opening an Inspection Lot binds an effective plan, Phase 4 Lot/Serial, exact
  location, quantity, optional Phase 3 task, and one automatically created open Hold.
- Measurement requires one typed value plus UOM, method, gauge, qualified person,
  occurrence time, and evidence. Numeric Pass/Fail is computed from the effective
  specification and independently guarded by PostgreSQL.
- Completing the sample deterministically sets Passed or Failed. A failed result
  creates exactly one durable Nonconformance and keeps the material held.
- Use-as-is, Rework, Scrap, and Return-to-supplier dispositions are proposals until
  separately approved. Rework remains held; Scrap/Return close the logical Lot and
  cannot restore normal flow.
- Release requires `quality:release`, an authorization reference, and either a
  passing inspection or an approved use-as-is disposition.
- CAPA basics preserve problem statement, root cause, action plan, due time,
  verification reference, and effectiveness result.
- Every accepted quality mutation writes business facts, status history, audit, and
  a NATS audit Outbox envelope in one transaction.

## Business Authority And Invariants

PostgreSQL is the sole Phase 5 authority. Simulated defect rate, heartbeat fields,
legacy `part_queue` quality text, Dashboard state, rule output, AI response, and HTTP
success cannot release material.

Application checks and database guards jointly enforce:

- one effective revision per Inspection Plan code;
- immutable plan identity and append-only characteristic, measurement, and status
  evidence;
- one open quality Hold per Lot/Serial;
- an open Hold blocks Phase 4 movement and transformation paths;
- measurement IDs are idempotent request keys and sample identity is unique;
- numeric measurement result cannot contradict the effective specification;
- method, UOM, gauge type/calibration period, person status, qualification level,
  and qualification validity are checked at measurement time;
- Failed material cannot release without an approved use-as-is disposition;
- release requires actor and authorization reference at both API and database level;
- the AI service credential has diagnosis permission only and receives HTTP 403 on
  quality release.

## Data And Migrations

| Migration | Purpose | Live status |
|---|---|---|
| `2026.07.14-phase5-quality-operations` | 10 scoped quality plan, gauge, inspection, hold, measurement, NC, disposition, CAPA and history tables | Applied once with checksum |
| `2026.07.14-phase5-quality-invariant-guards` | Hold/movement, deterministic result and authorized release database guards | Applied once with checksum |

Live PostgreSQL evidence:

- 10/10 Phase 5 tables have RLS enabled and forced.
- Alternate tenant/site scope returned zero Phase 5 rows.
- Direct measurement rewrite, held-lot movement, contradictory result insertion,
  and unauthorized release probes were rejected by PostgreSQL.
- The Operator role has zero `quality:release` grants.
- At the Phase 5 gate, 67 authoritative tables were forced-RLS scoped.

## Interfaces, Authorization, And Audit

Generated OpenAPI v1 exposes `/quality/*` routes for Gauges, Inspection Plans,
Inspection Lots, Measurements, Dispositions, Release, and CAPA. Responsibilities are
split into `quality:manage`, `quality:measure`, and `quality:release`. The default
Operator receives measurement permission only. Dedicated Quality Engineer and
Quality Releaser roles separate definition/measurement from release; System Admin
retains all permissions for the current engineering runtime.

Business conflicts use HTTP 409 with stable `detail.code`; missing authority is HTTP
403. Actors are derived from verified JWT claims. There is no request field that can
substitute an actor or grant release authority.

## Test And Runtime Evidence

- Focused Phase 5 suite: 9 passed.
- Full Central API suite: 235 passed.
- Generated OpenAPI and manifest were refreshed and pass the contract-current test.
- Unified verification passed API/contract/secret/ACL gates, all Python and Go
  suites, Dashboard 69 tests and production build, correctness lint, strict runtime,
  and Phase 1/3/4/5 live PostgreSQL gates.
- Live validation prefix `P5G07132141342ED2` persisted two Inspection Lots, two
  Measurements, one Nonconformance, one approved disposition, one release, one
  completed CAPA, and 13 quality audit records in PostgreSQL.
- The live gate proved measurement retry idempotency, normal-flow blocking before
  release, AI release denial, required disposition approval, and movement only after
  authorized release.
- Unified revalidation used independent prefix `P5G071321471532DC`, movement row 50,
  measurement row 4, and repeated all database bypass probes successfully.
- Runtime restart succeeded with a fresh Central API session, 3/3 simulated nodes,
  PostgreSQL primary, and DeepSeek source `api`, status `live`.

## Rollback And Recovery

Both migrations are additive. Application rollback retains all Phase 5 tables,
guards, audit, history, measurement, and Outbox evidence. Accepted quality evidence
must not be rewritten or deleted. Destructive rollback requires a verified
PostgreSQL restore and material/quality reconciliation; that restore drill remains a
production blocker.

## Non-Claims And Residual Scope

- No physical gauge, CMM, LIMS/QMS, PLC, CNC, ERP, WMS, barcode, or RFID connector
  is implemented. Gauge calibration is a governed reference entered through the API.
- Scrap and Return-to-supplier approval close the logical Lot; no physical transfer,
  financial write-off, supplier RMA, or external inventory acknowledgement is proven.
- Rework remains held and requires a later controlled rework execution and new
  inspection; this gate does not claim an automated rework route.
- The engineering gate used System Admin for positive workflow actions. Pilot use
  still requires named separate users, resource scope, and any required
  proposer/approver separation policy.
- No quality Dashboard workbench, statistical process control, electronic signature,
  retention policy, load test, backup restore, HA, or plant validation is proven.
- AI may help explain evidence in later work, but it cannot set a quality result,
  approve a disposition, release material, or close CAPA.

## Formal Gate

| Gate | Evidence | Result |
|---|---|---|
| Nonconforming material cannot flow normally | Open Hold blocks API movement and PostgreSQL direct insertion; failed inspection remains held | PASS |
| Release is authorized | Separate release permission, authorization reference, failed-use-as-is approval and DB release trigger | PASS |
| Measurement identifies unit, method, device and person | Strict input, effective Characteristic, calibrated Gauge and current qualification checks | PASS |
| AI cannot release automatically | Diagnosis-only JWT receives HTTP 403; no AI quality-release permission | PASS |

The first unmet stage is now Phase 6: maintenance, equipment, and tooling.

Current-state note: Phase 6 subsequently passed. The preceding sentence preserves
the Phase 5 gate boundary at its validation time; `PHASE6_GATE.md` identifies Phase 7
as the first unmet stage.
