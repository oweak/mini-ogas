# Phase 6 Maintenance Test Evidence - 2026-07-14

## Repository And Environment

- Validation applies to the current pre-existing dirty working tree, not a commit or
  tagged release.
- Host: Windows local digital twin.
- Business authority: PostgreSQL; NATS remains loopback shadow transport.
- Runtime: simulated production telemetry, operator-assisted control, no physical
  maintenance or device connector.

## Commands And Results

| Command/probe | Result |
|---|---|
| `python -m pytest tests/test_phase6_maintenance.py -q` | 9 passed |
| Phase 4/5/6 focused regression | 27 passed |
| `python -m pytest -q` in `services/central-api` | 244 passed |
| Ruff Phase 6/default checks and application `--select F` | passed |
| `python tools/export_contracts.py --check` | passed after export refresh |
| `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1 -RequireAiUnlocked` | complete unified gate passed: contracts, secrets/ACL, all service suites, Dashboard test/build, lint, strict runtime, and live Phase 1/3/4/5/6 |
| `scripts/start-system.ps1 -RequireAiApi` | fresh Central API/microservices; 3/3 nodes; AI API live |
| `python scripts/check_phase6_maintenance.py` | PASS |
| PostgreSQL migration query | all four Phase 6 rows present |
| PostgreSQL RLS catalog | 14/14 Phase 6 tables enabled and forced |
| Cross-scope query | zero rows across all Phase 6 tables |
| Direct Checklist result rewrite | rejected |
| Direct same-actor verification | rejected |
| Direct verified-evidence rewrite | rejected |
| Direct task start during active maintenance | rejected |
| Direct Consume without production/maintenance authority | rejected |

## Automated Acceptance Coverage

- governed Asset hierarchy, Equipment binding, criticality, and code taxonomy;
- versioned Checklist Draft/Approved/Effective path and immutable items;
- alarm-sourced Request remains distinct from Order work and verification;
- required Checklist pass evidence and failure/cause/remedy before work completion;
- work completer cannot verify the same order;
- equipment-unavailable maintenance blocks task start until verification;
- Tool life event reaches Over-life and blocks its assigned task;
- failed Calibration reaches Calibration-invalid and blocks its assigned task;
- Phase 3 running task/downtime and Phase 6 order use the same durable IDs;
- due preventive Plan creates Request/Order and advances next due time;
- spare usage references a Phase 4 Consume movement authorized by the same order;
- Checklist, status, spare, life, calibration, and assignment evidence is append-only;
- injected Outbox failure rolls back Request, audit, and Outbox transaction.

## Live Workflow Evidence

Authenticated unified-gate prefix `P6G07132222559859` created governed Phase 2 master data,
one maintenance Asset, code taxonomy, one effective Checklist, MRO inventory, four
Maintenance Orders, production tasks, one Tool, and one preventive Plan. It then:

1. started corrective maintenance and rejected Operation Task start;
2. rejected work completion before required Checklist evidence;
3. accepted work completion only with two passes and coded work evidence;
4. accepted restoration only from an independent verifier;
5. started the task only after verification;
6. opened Phase 3 downtime, bound a second order to it, consumed and linked one spare,
   verified restoration, closed downtime, and resumed the task;
7. accumulated Tool life above its limit and rejected the assigned task start;
8. generated a due preventive Request and draft Order without claiming completion;
9. left a fourth order at Work completed while database bypass probes ran, then
   accepted only independent API verification;
10. queried PostgreSQL catalogs and alternate scope directly.

PostgreSQL persisted four matching Maintenance Orders and 37 matching maintenance
audit records. All four migration rows, 14 forced-RLS tables, zero Operator verify
grants, zero cross-scope rows, and five database guard booleans were confirmed.

## Implementation Failure Evidence

- Baseline authenticated routes returned HTTP 405.
- Initial red suite produced 9 errors at `/maintenance/assets`, proving the missing
  domain rather than passing against a placeholder.
- The first gate detected that `verified_by` could be changed without updating
  `status`; the failed probe changed validation-only data. A fourth migration added
  full lifecycle/evidence immutability and the direct rewrite now fails.
- The second gate run saw PostgreSQL reject an unbound Consume, but classified the
  result as failure because source and deployed migration error text differed. No
  unbound row was committed. Source and gate now use the applied migration's stable
  message.
- The first full regression after adding routes failed only on stale generated
  OpenAPI/manifest files. Export refresh produced 244 passing tests.

## Non-Claims

This proves a durable maintenance workflow in the current digital-twin environment.
It does not prove physical equipment state, real condition monitoring, actual
calibration/tool counters, CMMS/EAM interoperability, external inventory costing,
electronic signatures, plant procedures, production load, backup restoration, HA,
or production authorization.
