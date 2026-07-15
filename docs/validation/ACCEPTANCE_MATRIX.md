# Acceptance Matrix

## Phase 2

| Requirement | Automated evidence | Live evidence | Result |
|---|---|---|---|
| Exact revision binding | Valid release retains exact BOM/Routing/document IDs | PostgreSQL schema and runtime migration | PASS |
| Account differs from qualification | Linked admin without qualification returns `QUALIFICATION_MISSING` | Permission and RLS active | PASS |
| Equipment capability required | Equipment without capability returns `EQUIPMENT_CAPABILITY_MISSING` | Capability relation exists under forced RLS | PASS |
| Qualification must be current | Expired evidence is rejected | TIMESTAMPTZ storage and UTC comparison | PASS |
| Controlled revision workflow | Premature effectivity returns 409; supersession preserved | One-effective unique indexes | PASS |
| History cannot be overwritten/deleted | SQLite update/delete failure | PostgreSQL update/delete trigger probes | PASS |
| Tenant/site isolation | Explicit scope predicates in repository | Alternate-site query returns zero | PASS |
| Mutation is authorized | Viewer token returns 403 | Admin login authenticated | PASS |
| Audit and Outbox are atomic | Fault injection rolls back master and audit | Outbox/NATS worker healthy | PASS |
| Contracts remain compatible | Full central regression and export check | Live invalid request returns stable code | PASS |

## Phase 3

| Requirement | Automated evidence | Live evidence | Result |
|---|---|---|---|
| Legal operation transitions | API negative tests and direct SQLite trigger probe | PostgreSQL direct `closed -> running` rejected | PASS |
| Completion evidence | Empty evidence returns stable 409; DB completion guard | Authenticated live negative/positive completion | PASS |
| Quantity conservation | Idempotent report, over-plan, exact-total tests | PostgreSQL direct over-report rejected | PASS |
| HTTP 200 is not completion | Setup/start/pause retain explicit nonterminal status | Live workflow requires separate completion transaction | PASS |
| Assignment and setup are durable | Task materializes exact released assignment; setup evidence stored | Replay contains task/assignment/setup | PASS |
| Hold and downtime are durable | Hold restore and downtime pause/resume history test | Schema, RLS, and trigger catalog live | PASS |
| Status history is immutable | SQLite update/delete rejection | PostgreSQL update/delete guards present | PASS |
| Replay is deterministic | Exact ordered history and report-count assertions | Live replay: 6 statuses, 2 reports | PASS |
| Mutation is authorized | Viewer JWT returns 403 | Admin JWT used by runtime gate | PASS |
| Audit and Outbox are atomic | Injected enqueue failure rolls back business/audit rows | NATS Outbox publisher/worker live | PASS |
| Tenant/site isolation | Explicit repository scope | 11/11 forced RLS; alternate scope returns zero | PASS |
| Full system remains healthy | 217 central tests plus all component suites | 9/9 processes, 3/3 nodes, API AI source live | PASS |

## Phase 4

| Requirement | Automated evidence | Live evidence | Result |
|---|---|---|---|
| Forward and reverse genealogy | Split/Merge recursive lineage assertions | Product lot returns two descendants; child returns parent | PASS |
| No negative inventory/WIP | Conditional balance writes and SQLite constraint probes | PostgreSQL direct negative update and overdraw rejected | PASS |
| Retransmission does not double-count | Movement/transformation/import retry returns original ID | Live retry preserved movement 22 and transformation 3 | PASS |
| Serial identity is globally singular | Per-leg and aggregate Serial tests | PostgreSQL rejected second location balance | PASS |
| Execution state owns Consume/Produce timing | Running Consume, completed Produce, invalid-state 409 | Live task-bound consume/produce and premature rejection | PASS |
| Split/Merge quantity is conserved | Material/UOM/total conservation tests | Live 4 -> 1 + 3 Split | PASS |
| Discrepancy does not overwrite balance | Snapshot leaves balance unchanged | Live expected 3 remained until approved adjustment to 2 | PASS |
| Evidence is immutable | Movement/genealogy update/delete rejection | PostgreSQL direct movement rewrite rejected | PASS |
| Mutation is authorized | Viewer JWT returns 403 | Admin JWT used by runtime gate | PASS |
| Audit and Outbox are atomic | Fault injection rolls back movement/balance | Unified Outbox and NATS shadow gates pass | PASS |
| Tenant/site isolation | Explicit repository scope | 10/10 forced RLS; alternate scope returns zero | PASS |
| Full system remains healthy | 226 central tests and all component suites | 3/3 nodes, API AI source live, Dashboard build | PASS |

## Phase 5

| Requirement | Automated evidence | Live evidence | Result |
|---|---|---|---|
| Effective plan owns inspection | Draft/approve/effective and immutable characteristic tests | Live effective final plan bound to governed Material | PASS |
| Nonconforming material cannot flow | Open Hold returns `QUALITY_HOLD_ACTIVE` | API and PostgreSQL direct movement both rejected | PASS |
| Measurement metadata is complete | Method/UOM/Gauge/person mismatch tests | Two persisted measurements carry all required references | PASS |
| Pass/Fail is deterministic | Limit evaluation and forged-result trigger test | PostgreSQL direct contradictory result rejected | PASS |
| Failed sample creates NC | Complete sample produces one failed inspection and one NC | Live NC `P5G07132141342ED2-RELEASE-INSP-NC` | PASS |
| Release is explicit and authorized | Passing still held; missing/unapproved disposition rejected | Approved use-as-is plus authorization released the Lot | PASS |
| AI cannot release | Diagnosis-only JWT receives HTTP 403 | Live API AI credential release attempt forbidden | PASS |
| Disposition preserves control | Scrap closes logical Lot; Rework remains held | Approved use-as-is required before live release | PASS |
| CAPA evidence is durable | Root-cause/action/effectiveness test | Live CAPA status `completed` | PASS |
| Evidence is immutable | SQLite measurement/history update/delete rejection | PostgreSQL direct measurement rewrite rejected | PASS |
| Audit and Outbox are atomic | Injected enqueue failure rolls back measurement | 13 live quality audit rows; unified Outbox path | PASS |
| Tenant/site isolation | Explicit repository scope | 10/10 forced RLS; alternate scope returns zero | PASS |
| Full system remains healthy | 235 Central API tests and generated contract check | Fresh runtime, 3/3 nodes, AI API source live | PASS |

## Phase 6

| Requirement | Automated evidence | Live evidence | Result |
|---|---|---|---|
| Alarm is not completion | Premature verification returns `MAINTENANCE_NOT_READY_FOR_VERIFICATION` | Alarm Request required separate Order, work, Checklist and verifier | PASS |
| Governed asset and criticality | Equipment binding, hierarchy and code tests | Live critical Asset and failure/cause/remedy references | PASS |
| Work requires Checklist evidence | Missing required item returns `CHECKLIST_INCOMPLETE` | Two immutable passes required before Work completed | PASS |
| Completion has independent verification | Same actor returns `INDEPENDENT_VERIFIER_REQUIRED` | Separate verifier restored Asset and unblocked task | PASS |
| Tool life affects execution | Over-life and failed-calibration tests block task start | Live over-life Tool returned `TOOL_LIFE_EXCEEDED` | PASS |
| Downtime links maintenance to schedule | Task/Downtime/Order ID consistency tests | Live downtime closed and task resumed only after verification | PASS |
| Spare use has inventory authority | Movement/order mismatch and Consume binding tests | Phase 4 Consume linked to same Phase 6 Order | PASS |
| Preventive due work is durable | Due Plan creates Request/Order and advances due time | Live generated draft Order without false completion | PASS |
| Evidence is immutable | SQLite Checklist/history/order rewrite rejection | PostgreSQL direct Checklist and verified-evidence rewrites rejected | PASS |
| Database interlocks resist bypass | SQLite/PostgreSQL task and Consume triggers | Direct task start and unbound Consume rejected | PASS |
| Audit and Outbox are atomic | Injected enqueue failure rolls back Request | 37 live maintenance audit rows; unified Outbox path | PASS |
| Tenant/site isolation | Explicit repository scope | 14/14 forced RLS; alternate scope returns zero | PASS |
| Full system remains healthy | 244 Central API tests and contract check | Fresh runtime, 3/3 nodes, AI API source live | PASS |

Phase 7 data platform, Historian and projection work remains outside this accepted
matrix.
