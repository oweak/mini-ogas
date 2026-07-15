# Phase 4 Material Flow Test Evidence - 2026-07-14

## Repository And Environment

- Validation applies to the current pre-existing dirty working tree, not a commit or
  tagged release.
- Host: Windows local digital twin.
- Authority: PostgreSQL; NATS is loopback shadow transport.
- Runtime: simulated telemetry, operator-assisted mode, no physical connector or
  physical write path.

## Commands And Results

| Command/probe | Result |
|---|---|
| `python -m pytest tests/test_phase4_material_flow.py -q` | 9 passed |
| `python -m pytest -q` in `services/central-api` | 226 passed |
| Ruff on Phase 4 Python files and gate script | passed |
| `python tools/export_contracts.py --check` | passed |
| `python scripts/check_phase4_material_flow.py` | PASS |
| `scripts/verify-miniogas.ps1 -RequireAiUnlocked` | complete pass |
| PostgreSQL migration query | both Phase 4 rows present |
| PostgreSQL RLS catalog | 10/10 Phase 4 tables enabled and forced |
| Cross-scope query | zero rows |
| Direct movement rewrite | rejected |
| Direct negative balance | rejected |
| Direct second balance for one serial | rejected |

## Automated Acceptance Coverage

- movement retry returns the original row and changed reuse is rejected;
- transfer cannot overdraw a source balance;
- Issue, Return, Scrap, and container transfer conserve total quantity;
- Consume and Produce require compatible Phase 3 task states;
- Split and Merge conserve quantity and create forward/reverse genealogy;
- one Serial movement and total balance are exactly one;
- external snapshot creates a discrepancy without changing authoritative balance;
- approved adjustment is a separate movement with reason and evidence;
- material movement and genealogy evidence cannot be updated or deleted;
- viewer mutation is forbidden;
- Outbox failure rolls back both movement and balance.

## Live Workflow Evidence

The unified live gate created prefix `P4G071321194200A8` through authenticated HTTP.
It created governed master data, a released Work Order and running Operation Task,
two warehouses, two locations, two containers, and five lots/serials. It then:

1. recorded an idempotent raw-material receipt;
2. issued, returned, reissued, and consumed material while the task was running;
3. rejected premature Produce with `EXECUTION_STATE_INCOMPATIBLE`;
4. accepted an evidenced quantity report and task completion;
5. produced finished quantity bound to the completed task;
6. split the product lot and returned exact forward/reverse genealogy;
7. rejected a two-unit Serial receipt and a negative transfer;
8. imported a versioned simulated WMS observation without changing stock;
9. created one open discrepancy and adjusted it from quantity 3 to 2 only after a
   separate approved request;
10. closed the task, Work Order execution, and Production Order.

The persisted live result used task ID 7, movement row ID 22, transformation row ID
3, and reconciliation status `adjusted`. These IDs are validation evidence only.

## Implementation Failure Evidence

- Baseline `/material-flow/warehouses` red test returned HTTP 405.
- Initial idempotency helper generated a new timestamp per retry and was corrected to
  replay the exact same request.
- The first live adjustment reached PostgreSQL but failed because an unrestricted
  `FOR UPDATE` cannot lock the nullable side of a left join. The repository now locks
  only the reconciliation authority row with `FOR UPDATE OF reconciliation`.
- The first unified run found a credential-pattern false positive in historical
  Phase 3 prose. The triggering literal was removed without weakening the scanner.

## Non-Claims

This proves a durable software material-flow and reconciliation model in the current
digital-twin environment. It does not prove physical inventory accuracy, calibrated
measurement, actual ERP/WMS interoperability, plant procedures, quality release,
load capacity, backup restoration, HA, or production authorization.
