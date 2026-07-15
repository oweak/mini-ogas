# Phase 5 Quality Test Evidence - 2026-07-14

## Repository And Environment

- Validation applies to the current pre-existing dirty working tree, not a commit or
  tagged release.
- Host: Windows local digital twin.
- Business authority: PostgreSQL; NATS remains loopback shadow transport.
- Runtime: simulated production telemetry, operator-assisted control, no physical
  quality or device connector.

## Commands And Results

| Command/probe | Result |
|---|---|
| `python -m pytest tests/test_phase5_quality.py -q` | 9 passed |
| `python -m pytest -q` in `services/central-api` | 235 passed |
| Ruff format plus correctness lint on Phase 5 files and gate script | passed |
| `python tools/export_contracts.py --check` | passed after export refresh |
| `scripts/start-system.ps1` | fresh Central API session; 3/3 nodes; AI API live |
| `python scripts/check_phase5_quality.py` | PASS |
| `scripts/verify-miniogas.ps1 -RequireAiUnlocked` | complete pass |
| PostgreSQL migration query | both Phase 5 rows present |
| PostgreSQL RLS catalog | 10/10 Phase 5 tables enabled and forced |
| Cross-scope query | zero rows across all Phase 5 tables |
| Direct quality evidence rewrite | rejected |
| Direct held-lot movement | rejected |
| Direct contradictory result insertion | rejected |
| Direct unauthorized release | rejected |

## Automated Acceptance Coverage

- governed plan revision, characteristic, specification, sample size, method, Gauge,
  UOM, skill, and qualification binding;
- automatic quality Hold on inspection opening;
- held material cannot move through the Phase 4 movement API;
- measurement retry returns the original row and changed reuse is rejected;
- method, UOM, Gauge calibration, and person qualification mismatches fail closed;
- complete sample deterministically sets Passed/Failed and creates one NC on failure;
- AI credential cannot release;
- Failed inspection requires proposed and approved use-as-is before release;
- passing inspection remains held until explicit release;
- Scrap closes the logical Lot and Rework remains held;
- CAPA preserves root cause, action, verification, and effectiveness;
- measurement and status history are append-only;
- injected Outbox failure rolls back measurement and audit facts.

## Live Workflow Evidence

The live gate created prefix `P5G07132141342ED2` through authenticated HTTP. It
created governed master data, two warehouses and locations, two product Lots, a
calibrated Gauge reference, one effective final Inspection Plan, and two Inspection
Lots. It then:

1. rejected a normal material transfer while the quality Hold was open;
2. recorded one conforming and one out-of-specification measurement;
3. returned the original row for an exact measurement retry;
4. evaluated the inspection as Failed and created one Nonconformance;
5. rejected release without disposition;
6. returned HTTP 403 for an AI-service release attempt;
7. recorded a use-as-is proposal, rejected release while it was unapproved, then
   accepted separate disposition approval;
8. released the inspection with an authorization reference;
9. accepted material transfer only after release;
10. created and completed a basic CAPA with effectiveness evidence;
11. kept the second Inspection Lot held for direct database bypass probes.

Persisted evidence includes movement row ID 35, measurement row ID 1, 13 quality
audit rows, disposition status `approved`, inspection status `released`, CAPA status
`completed`, and zero Operator release grants. Numeric IDs are validation evidence
only; the validation prefix is the durable business correlation key.

The later unified run repeated the entire workflow with independent prefix
`P5G071321471532DC`, movement row ID 50, measurement row ID 4, 10/10 forced-RLS
tables, and every direct bypass guard still true.

## Implementation Failure Evidence

- The baseline quality API probes returned HTTP 405.
- The first router implementation forwarded action `approve` to a state machine that
  accepts target state `approved`; the route now performs an explicit action-to-state
  mapping without weakening the state machine.
- The first PostgreSQL startup failed transactionally because psycopg interpreted
  PL/pgSQL `%ROWTYPE` as a placeholder. Escaping it as `%%ROWTYPE` allowed the same
  database guard to migrate successfully; no fallback database was used.
- The first full regression after adding routes failed only because generated
  OpenAPI/manifest artifacts were stale. Export refresh produced 235 passing tests.

## Non-Claims

This proves a durable quality workflow in the current digital-twin environment. It
does not prove physical measurement accuracy, actual calibration, external QMS/LIMS
interoperability, shop-floor procedures, electronic signatures, statistical process
control, physical scrap/rework execution, production load, backup restoration, HA,
or production authorization.
