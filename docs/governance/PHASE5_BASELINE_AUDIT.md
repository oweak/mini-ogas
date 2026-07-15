# Phase 5 Baseline Audit

## Decision

`FAIL - 0/4 GATES SATISFIED BEFORE IMPLEMENTATION`

Audit date: 2026-07-14. Phase 4 has passed. This record evaluates quality operations
without promoting defect-rate telemetry, report labels, recommendations, or legacy
queue strings into inspection or disposition authority.

## Required Capability Versus Repository Fact

| Requirement | Repository fact before Phase 5 | Baseline |
|---|---|---|
| Inspection Plan | No governed inspection plan, revision, operation/stage binding, characteristic list, or effectivity exists | ABSENT |
| Characteristic and Specification | No characteristic identity, nominal/limits, datatype, UOM, method, or acceptance rule exists | ABSENT |
| Sampling | Dashboard `sampling` describes replay-row truncation only; no sample size, frequency, selection, or lot rule exists | ABSENT |
| Measurement | No measured value, result identity, instrument/gauge reference, method, operator, occurrence time, or raw evidence record exists | ABSENT |
| Pass/Fail and Quality Gate | `defect_rate` threshold rules emit recommendations; they do not evaluate governed specifications or block a Lot/Serial | ABSENT |
| Hold/Release | Phase 3 Operation Task hold is an execution control, not a quality hold on product/material; Phase 4 has no governed lot hold/release route | WRONG DOMAIN ONLY |
| Nonconformance | No NC identity, affected quantity/lot, defect code, containment, owner, severity, or lifecycle exists | ABSENT |
| Disposition | No use-as-is, rework, repair, return, or scrap authorization workflow exists | ABSENT |
| Rework/Scrap | Phase 3 quantity categories and Phase 4 movement types account quantity/material only; they have no quality decision or authorization evidence | FOUNDATION LABEL ONLY |
| CAPA | No corrective/preventive action, cause, action, verification, effectiveness, or closure exists | ABSENT |
| Gauge Reference | Equipment master has production capability only; no gauge identity, calibration state, traceability, or measurement-device binding exists | ABSENT |

## Existing Objects That Must Not Be Reclassified

- Simulated heartbeat `defect_rate` is a model output. It is neither a sample nor a
  measured characteristic.
- `RULE-QUALITY-DEFECT-RISE` is a deterministic alert over telemetry and returns
  recommended text. It does not place or release a governed quality hold.
- Legacy `PartQueueItem.quality_status` is an unvalidated string. Completing a claim
  sets it directly to `accepted` without plan, measurement, gauge, person, method,
  authorization, or audit-grade disposition.
- Phase 3 `scrap_quantity` and `rework_quantity` are operation accounting categories,
  not Nonconformance or Disposition records.
- Phase 4 Scrap/Rework movements prove where material moved. They do not prove why it
  was nonconforming or who authorized the disposition.
- An AI diagnosis, alert acknowledgement, HTTP 200, or normal heartbeat cannot release
  suspect material.

## Repository And Live Evidence

- Generated OpenAPI contains no path with quality, inspection, measurement,
  nonconformance, disposition, gauge, or quality-release semantics.
- Central API schema migrations contain no quality-domain table.
- Source search found only telemetry `defect_rate`, rule recommendations, Phase 3
  accounting labels, Phase 4 movement labels, and legacy queue `quality_status`.
- Authenticated runtime probes returned HTTP 405 for:
  - `POST /quality/inspection-plans`;
  - `POST /quality/measurements`;
  - `POST /quality/nonconformances`;
  - `POST /quality/dispositions`;
  - `POST /quality/releases`.

## First Authoritative Vertical Slice

1. Create a versioned Inspection Plan bound to a governed Phase 2 Material/Product,
   operation code or receiving/final stage, and effective Characteristic definitions.
2. Define each Characteristic with datatype, UOM/dimension, method, lower/upper
   specification limits, sample size, required gauge type, and deterministic result
   rule.
3. Register a governed Gauge with calibration status, validity interval, evidence,
   and capability for the measured characteristic.
4. Create an Inspection Lot bound to a Phase 4 Lot/Serial, location, quantity, and
   optionally a Phase 3 Operation Task. Creation places a durable quality hold on the
   affected material without rewriting its genealogy.
5. Record append-only Measurements with result ID, sample identity, value/UOM,
   method, gauge, personnel, timestamp, and evidence. Reject expired/unqualified
   gauge or incompatible UOM.
6. Evaluate Pass/Fail deterministically from the effective specification. AI may
   explain evidence but cannot set the result, disposition, or release state.
7. A failed characteristic creates a Nonconformance and keeps the hold. Authorized
   Disposition records use-as-is, rework, return, or scrap with reason/evidence and
   links any Phase 4 material movement.
8. Release requires all required samples, deterministic pass result or authorized
   disposition, a distinct permission, and an immutable decision record.
9. Write quality fact, audit row, and audit Outbox in one PostgreSQL transaction under
   forced RLS. Retries must be idempotent and changed reuse must fail.

## Phase 5 Gate At Baseline

| Gate | Result | Reason |
|---|---|---|
| Nonconforming material cannot flow normally | FAIL | No quality hold, NC, or material gate exists |
| Release is authorized | FAIL | No quality-release transaction or permission exists |
| Measurement has unit, method, device, and person | FAIL | No Measurement/Gauge domain exists |
| AI cannot automatically release | FAIL | No quality release boundary exists to enforce |

The first red implementation test must target a PostgreSQL-backed quality hold and
measurement workflow bound to Phase 2-4 identities. Legacy quality strings and
defect-rate alerts remain simulation/projection artifacts.
