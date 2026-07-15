# Phase 3 Production Execution Test Evidence - 2026-07-14

## Repository And Environment

- Validation applies to the current pre-existing dirty working tree, not a commit or
  tagged release.
- Host: Windows local digital twin.
- Authority: PostgreSQL; NATS is loopback shadow transport.
- Runtime: simulated source, operator-assisted mode, physical connector disabled,
  physical write disabled.

## Commands And Results

| Command/probe | Result |
|---|---|
| `python -m pytest tests/test_phase3_execution.py -q` | 9 passed |
| `python -m pytest -q` in `services/central-api` | 217 passed |
| Ruff on all new Phase 3 Python files | passed |
| `python tools/export_contracts.py --check` | passed |
| `scripts/verify-miniogas.ps1 -RequireAiUnlocked` | complete pass |
| PostgreSQL migration query | both Phase 3 rows present with checksum |
| PostgreSQL RLS catalog query | 11/11 Phase 3 tables enabled and forced |
| Cross-site transaction probe | active scope 1; alternate scope 0; rolled back |
| PostgreSQL trigger catalog | 6 operation guard trigger instances |
| Direct status jump probe | rejected and rolled back |
| Direct over-plan quantity probe | rejected and rolled back |
| `python scripts/check_phase3_execution.py` | PASS; legal order closed and replayed |

## Automated Acceptance Coverage

- setup cannot be skipped;
- exact quantity and completion evidence are required;
- report retry returns the original row;
- over-plan report is rejected;
- hold and release restore the prior state;
- pause/resume and downtime produce durable ordered history;
- aggregate completion and explicit close are distinct;
- status history cannot be updated or deleted;
- database rejects direct illegal transition and over-report;
- viewer mutation is forbidden;
- Outbox failure rolls back business and audit facts.

## Live Workflow Evidence

The unified live gate created validation order prefix `V3G07132054352FF5` through
authenticated HTTP. It intentionally received:

- `INVALID_OPERATION_TRANSITION` when start skipped setup;
- `QUANTITY_NOT_CONSERVED` on premature completion;
- `QUANTITY_EXCEEDS_PLAN` on an over-plan report;
- `COMPLETION_EVIDENCE_REQUIRED` after quantity conservation but without evidence.

It then accepted setup evidence, two quantity reports, completion evidence, task
close, Work Order close, and Production Order close. PostgreSQL replay returned one
task, six ordered status events, and exactly two accepted reports. Repeating the
first `report_id` returned its original row rather than double-counting.

## Failure Evidence During Implementation

- Baseline route test failed with HTTP 405.
- The first full suite was contaminated by two concurrently running pytest processes
  sharing the same SQLite test path; a clean single-process run passed.
- Generated OpenAPI was stale after routes were added and was regenerated.
- Secret scan initially treated a non-secret test identifier as a credential-like
  prefix; the identifier was renamed and the unchanged strict scanner passed.
- Application-only invariants were judged insufficient, so a second additive
  migration added database transition/evidence/quantity guards before gate closure.

## Non-Claims

This evidence proves a software execution state machine in the current digital-twin
environment. It does not prove physical execution, calibrated measurements, actual
material consumption, inventory, genealogy, ERP/WMS integration, production load,
backup restoration, high availability, or business/plant approval.
