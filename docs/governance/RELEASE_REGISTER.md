# Release Register

## Phase 2 Validation Candidate - 2026-07-14

| Field | Value |
|---|---|
| release_id | `phase2-validation-2026-07-14` |
| git_commit | Not assigned; validation ran on a pre-existing dirty working tree |
| artifacts | Central API code, generated OpenAPI/manifest, Phase 2 governance and validation records |
| schema_version | Phase 1 scope migration plus two Phase 2 migrations |
| contract_version | OpenAPI v1; NATS schema 3.0 audit envelope |
| configuration | Digital twin, simulated data source, operator-assisted, PostgreSQL primary, NATS shadow, connector/write disabled |
| migrations | `2026.07.14-phase2-master-data`; `2026.07.14-phase2-revision-delete-guard` |
| known_risks | See R-004, R-017, R-026, R-041 and Phase 2 non-claims |
| test_evidence | `validation/TEST_EVIDENCE/PHASE2_MASTER_DATA_2026-07-14.md` |
| approver | Engineering gate only; no plant/business release approval recorded |
| rollback_version | Application rollback with additive schema retained; destructive rollback forbidden after revision data |
| deployment_time | Local supervisor restart and live migration on 2026-07-14 local date |

This is not a production release record. A commit, immutable artifacts, approver,
backup/restore evidence, and target deployment record are still required for release.

## Phase 3 Validation Candidate - 2026-07-14

| Field | Value |
|---|---|
| release_id | `phase3-validation-2026-07-14` |
| git_commit | Not assigned; validation ran on a pre-existing dirty working tree |
| artifacts | Central API execution domain/repository/router, generated OpenAPI/manifest, runtime gate, governance and evidence records |
| schema_version | Phase 1/2 plus two additive Phase 3 migrations |
| contract_version | OpenAPI v1 `/execution/*`; NATS schema 3.0 audit envelope |
| configuration | Digital twin, simulated telemetry, operator-assisted, PostgreSQL primary, NATS shadow, connector/write disabled |
| migrations | `2026.07.14-phase3-production-execution`; `2026.07.14-phase3-execution-invariant-guards` |
| known_risks | See R-004, R-006, R-017, R-026, R-032, R-042 and Phase 3 non-claims |
| test_evidence | `validation/TEST_EVIDENCE/PHASE3_EXECUTION_2026-07-14.md` |
| approver | Engineering gate only; no plant/business release approval recorded |
| rollback_version | Retain additive schema/evidence; destructive rollback forbidden without verified restore |
| deployment_time | Local Go supervisor restart and live PostgreSQL migration on 2026-07-14 local date |

This candidate proves only the Phase 3 digital-twin software gate. Phase 4 inventory,
genealogy, external connectors, production load, restore, HA, and business approval
remain absent.

Current-state note: Phase 4 subsequently passed. The preceding paragraph records
the Phase 3 candidate boundary at its validation time.

## Phase 4 Validation Candidate - 2026-07-14

| Field | Value |
|---|---|
| release_id | `phase4-validation-2026-07-14` |
| git_commit | Not assigned; validation ran on a pre-existing dirty working tree |
| artifacts | Central API material-flow domain/repository/router, generated OpenAPI/manifest, live gate, governance and evidence records |
| schema_version | Phase 1-3 plus two additive Phase 4 migrations |
| contract_version | OpenAPI v1 `/material-flow/*`; simulated external inventory contract 1.0; NATS schema 3.0 audit envelope |
| configuration | Digital twin, simulated telemetry, operator-assisted, PostgreSQL primary, NATS shadow, physical connector/write disabled |
| migrations | `2026.07.14-phase4-material-flow`; `2026.07.14-phase4-balance-invariant-guards` |
| known_risks | See R-004, R-006, R-017, R-026, R-032, R-042, R-043 and Phase 4 non-claims |
| test_evidence | `validation/TEST_EVIDENCE/PHASE4_MATERIAL_FLOW_2026-07-14.md` |
| approver | Engineering gate only; no inventory, quality, ERP/WMS, plant, or business approval recorded |
| rollback_version | Retain additive schema and immutable evidence; destructive rollback requires verified restore and reconciliation |
| deployment_time | Local service restart and live PostgreSQL migration on 2026-07-14 local date |

This candidate proves only the Phase 4 digital-twin software gate. Physical
inventory, real ERP/WMS integration, Phase 5 quality authority, production load,
restore, HA, and business approval remain absent.

Current-state note: Phase 5 subsequently passed. The preceding paragraph preserves
the Phase 4 candidate boundary at its validation time.

## Phase 5 Validation Candidate - 2026-07-14

| Field | Value |
|---|---|
| release_id | `phase5-validation-2026-07-14` |
| git_commit | Not assigned; validation ran on a pre-existing dirty working tree |
| artifacts | Central API quality domain/repository/router, generated OpenAPI/manifest, live gate, governance and evidence records |
| schema_version | Phase 1-4 plus two additive Phase 5 migrations |
| contract_version | OpenAPI v1 `/quality/*`; NATS schema 3.0 audit envelope |
| configuration | Digital twin, simulated production telemetry, operator-assisted, PostgreSQL primary, NATS shadow, physical quality/device connector disabled |
| migrations | `2026.07.14-phase5-quality-operations`; `2026.07.14-phase5-quality-invariant-guards` |
| known_risks | See R-004, R-014, R-017, R-026, R-043, DEBT-027, DEBT-028 and Phase 5 non-claims |
| test_evidence | `validation/TEST_EVIDENCE/PHASE5_QUALITY_2026-07-14.md` |
| approver | Engineering gate only; no quality, metrology, plant, compliance, or business approval recorded |
| rollback_version | Retain additive schema and immutable evidence; destructive rollback requires verified restore and quality/material reconciliation |
| deployment_time | Fresh local service session and live PostgreSQL migration on 2026-07-14 local date |

This candidate proves only the Phase 5 digital-twin software gate. Physical Gauge or
QMS/LIMS integration, actual scrap/rework execution, electronic signatures,
production load, restore, HA, and business approval remain absent.

Current-state note: Phase 6 subsequently passed. The preceding paragraph preserves
the Phase 5 candidate boundary at its validation time.

## Phase 6 Validation Candidate - 2026-07-14

| Field | Value |
|---|---|
| release_id | `phase6-validation-2026-07-14` |
| git_commit | Not assigned; validation ran on a pre-existing dirty working tree |
| artifacts | Central API maintenance domain/repository/router, generated OpenAPI/manifest, live gate, governance and evidence records |
| schema_version | Phase 1-5 plus four additive Phase 6 migrations |
| contract_version | OpenAPI v1 `/maintenance/*` and maintenance-authorized Phase 4 Consume; NATS schema 3.0 audit envelope |
| configuration | Digital twin, simulated telemetry, operator-assisted, PostgreSQL primary, NATS shadow, physical maintenance/device connector disabled |
| migrations | `2026.07.14-phase6-maintenance-operations`; `2026.07.14-phase6-maintenance-invariant-guards`; `2026.07.14-phase6-mro-movement-binding`; `2026.07.14-phase6-maintenance-lifecycle-guards` |
| known_risks | See R-004, R-008, R-014, R-017, R-026, R-044, DEBT-028, DEBT-029 and Phase 6 non-claims |
| test_evidence | `validation/TEST_EVIDENCE/PHASE6_MAINTENANCE_2026-07-14.md` |
| approver | Engineering gate only; no maintenance, tooling, metrology, OT, plant, compliance, or business approval recorded |
| rollback_version | Retain additive schema and immutable evidence; destructive rollback requires verified restore and maintenance/production/inventory reconciliation |
| deployment_time | Fresh local service session and live PostgreSQL migration on 2026-07-14 local date |

This candidate proves only the Phase 6 digital-twin software gate. Physical Asset
state, condition monitoring, Tool counters, calibration certificates, CMMS/EAM,
electronic signatures, production load, restore, HA, and business approval remain
absent.
