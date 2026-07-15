# Interface Catalog

Last verified: 2026-07-14. Generated schema authority remains
`contracts/openapi/mini-ogas-openapi-v1.json` and the contract manifest.

## Phase 2 Master Data API

| Name | Version | Producer | Consumer | Authority | Security | Idempotency/compatibility |
|---|---|---|---|---|---|---|
| Organization Unit create | OpenAPI v1 | Central API | Admin client | PostgreSQL `organization_units` | JWT `master-data:manage` plus RLS | Duplicate scoped code -> 409; additive route |
| UOM/Material/Product create | OpenAPI v1 | Central API | Admin client | PostgreSQL corresponding tables | JWT permission plus RLS | Duplicate scoped code -> 409 |
| Equipment/Capability create | OpenAPI v1 | Central API | Admin client | PostgreSQL equipment tables | JWT permission plus RLS | Duplicate equipment/capability -> 409 |
| Skill/Personnel/Qualification create | OpenAPI v1 | Central API | Admin client | PostgreSQL personnel tables | JWT permission plus RLS | Duplicate evidence identity -> 409; account is not qualification |
| Calendar/Shift create | OpenAPI v1 | Central API | Admin client | PostgreSQL calendar tables | JWT permission plus RLS | Duplicate scoped code -> 409 |
| Document/BOM/Routing create | OpenAPI v1 | Central API | Admin client | PostgreSQL parent tables | JWT permission plus RLS | Duplicate scoped code -> 409 |
| Revision create | OpenAPI v1 | Central API | Document/process engineering | PostgreSQL revision tables | JWT permission plus RLS | Duplicate parent/revision -> 409; content immutable |
| Revision approve/effective | OpenAPI v1 | Central API | Authorized engineering admin | PostgreSQL revision status | JWT permission plus RLS | Same accepted state is idempotent; illegal transition -> 409 |
| BOM revision query | OpenAPI v1 | Central API | Admin/Phase 3 service | PostgreSQL `bom_revisions` | JWT permission plus RLS | Ordered immutable history |
| Work-order draft/release | OpenAPI v1 | Central API | MOM admin/Phase 3 service | PostgreSQL `work_orders` | JWT permission plus RLS | Duplicate code -> 409; repeated release returns same binding |
| Master-data audit envelope | NATS 3.0 | Transactional Outbox | Shadow NATS worker | Audit row remains authority | Broker token; scoped DB writer | Deterministic message ID; at-least-once shadow receipt |

## Phase 3 Execution API

| Name | Version | Producer | Consumer | Authority | Security | Idempotency/compatibility |
|---|---|---|---|---|---|---|
| Production Order create/attach/release/close | OpenAPI v1 | Central API | Operations client | PostgreSQL Production Order aggregate | JWT `execution:manage` plus RLS | Scoped code uniqueness; action idempotency key; illegal transition -> 409 |
| Work Order dispatch/query/close | OpenAPI v1 | Central API | Operations client | PostgreSQL work-order execution | JWT permission plus RLS | Dispatch materializes exact Routing operations once |
| Work Order replay | OpenAPI v1 | Central API | Investigation/UI | PostgreSQL execution ledgers | JWT permission plus RLS | Ordered immutable facts; read only |
| Task setup/start/pause/resume/complete/close | OpenAPI v1 | Central API | Operations client | PostgreSQL Operation Task | JWT permission plus RLS | Per-resource/action idempotency key; strict transition errors |
| Task hold/release | OpenAPI v1 | Central API | Operations client | PostgreSQL hold and task state | JWT permission plus RLS | Restores durable prior state; one open hold |
| Quantity report | OpenAPI v1 | Central API | Authorized execution reporter | PostgreSQL append-only quantity ledger | JWT permission plus RLS | `report_id` is idempotency key; changed retry/over-plan -> 409 |
| Downtime start/end | OpenAPI v1 | Central API | Operations/maintenance client | PostgreSQL downtime and task state | JWT permission plus RLS | One open downtime; end requires evidence |
| Execution audit envelope | NATS 3.0 | Transactional Outbox | Shadow NATS worker | PostgreSQL business/audit rows remain authority | Broker token; scoped DB writer | Deterministic audit message; at-least-once shadow receipt |

## Phase 4 Material Flow API

| Name | Version | Producer | Consumer | Authority | Security | Idempotency/compatibility |
|---|---|---|---|---|---|---|
| Warehouse/Location/Container/Lot create | OpenAPI v1 | Central API | Inventory administration client | PostgreSQL Phase 4 identity tables | JWT `inventory:manage` plus RLS | Scoped code uniqueness; duplicate -> 409 |
| Material movement | OpenAPI v1 | Central API | Inventory/execution client | PostgreSQL movement ledger and balance transaction | JWT permission plus RLS | `movement_id` + request hash; changed retry -> 409 |
| Lot balance query | OpenAPI v1 | Central API | Operations/inventory query | PostgreSQL `inventory_balances` | JWT permission plus RLS | Read only; no browser calculation |
| Split/Merge/transform/rework | OpenAPI v1 | Central API | Inventory/execution client | PostgreSQL transformation, movement and genealogy ledgers | JWT permission plus RLS | `transformation_id` + request hash; conservation/cycle checks |
| Genealogy query | OpenAPI v1 | Central API | Quality/investigation client | PostgreSQL recursive genealogy graph | JWT permission plus RLS | Read-only forward descendants and reverse ancestors |
| External inventory snapshot | OpenAPI v1 contract 1.0 | Simulated ERP/WMS adapter | Central API reconciliation | Immutable PostgreSQL import plus discrepancy cases | JWT permission plus RLS | `import_id` + full payload hash; source always `simulated` |
| Reconciliation adjustment | OpenAPI v1 | Authorized inventory client | Central API | PostgreSQL case plus compensating movement | JWT permission plus RLS | Open/still-current case required; movement ID idempotent |
| Material audit envelope | NATS 3.0 | Transactional Outbox | Shadow NATS worker | PostgreSQL business/audit rows remain authority | Broker token; scoped DB writer | Deterministic audit message; at-least-once shadow receipt |

## Phase 5 Quality API

| Name | Version | Producer | Consumer | Authority | Security | Idempotency/compatibility |
|---|---|---|---|---|---|---|
| Gauge reference create | OpenAPI v1 | Quality administration client | Inspection service | PostgreSQL `gauges` | JWT `quality:manage` plus RLS | Scoped code uniqueness; calibration metadata required |
| Inspection Plan create/approve/effective | OpenAPI v1 | Quality engineering client | Inspection execution | PostgreSQL plan and immutable characteristics | JWT `quality:manage` plus RLS | Revision identity; legal transitions; one effective plan |
| Inspection Lot open/query | OpenAPI v1 | Inspection client | Quality/operations query | PostgreSQL Inspection Lot plus automatic Hold | JWT `quality:measure` plus RLS | Scoped code uniqueness; one open Hold per Lot |
| Measurement record | OpenAPI v1 | Qualified inspection client | Quality evaluation | PostgreSQL append-only measurement ledger | JWT `quality:measure` plus RLS | `measurement_id` + request hash; unique sample; deterministic result |
| Disposition propose | OpenAPI v1 | Quality engineering client | Quality release | PostgreSQL NC and disposition | JWT `quality:manage` plus RLS | Proposal remains non-authoritative until approval |
| Disposition approve and inspection release | OpenAPI v1 | Quality releaser | Material-flow gate | PostgreSQL disposition, release and Hold state | JWT `quality:release` plus RLS | Authorization reference; pass or approved use-as-is required |
| CAPA create/complete | OpenAPI v1 | Quality engineering/releaser | Quality investigation | PostgreSQL CAPA record | Split manage/release permissions plus RLS | Root cause/action and later effectiveness evidence retained |
| Quality audit envelope | NATS 3.0 | Transactional Outbox | Shadow NATS worker | PostgreSQL business/audit rows remain authority | Broker token; scoped DB writer | Deterministic audit message; at-least-once shadow receipt |

## Phase 6 Maintenance API

| Name | Version | Producer | Consumer | Authority | Security | Idempotency/compatibility |
|---|---|---|---|---|---|---|
| Asset and code create | OpenAPI v1 | Maintenance administration | Maintenance planning/execution | PostgreSQL Asset and failure/cause/remedy tables | JWT `maintenance:manage` plus RLS | Scoped code/equipment uniqueness; additive route |
| Checklist create/approve/effective | OpenAPI v1 | Maintenance planner | Technician/Order creation | PostgreSQL Checklist revision and immutable items | JWT `maintenance:manage` plus RLS | Legal transitions; one effective revision |
| Request create/query | OpenAPI v1 | Operator/alarm adapter | Maintenance planner | PostgreSQL Maintenance Request | JWT `maintenance:execute` plus RLS | Alarm is source only; scoped request code |
| Order create/approve/start | OpenAPI v1 | Planner/authorized execution | Technician/production interlock | PostgreSQL Maintenance Order | Split manage/execute permissions plus RLS | Strict durable lifecycle and immutable bindings |
| Checklist result/work complete | OpenAPI v1 | Technician | Independent verifier | PostgreSQL append-only result and coded work evidence | JWT `maintenance:execute` plus RLS | Required passes and effective Checklist required |
| Order verify | OpenAPI v1 | Independent verifier | Asset/task readiness | PostgreSQL verification fact and Asset state | JWT `maintenance:verify` plus RLS | Work completer denied; accepted evidence immutable |
| Preventive Plan create/effective/generate | OpenAPI v1 | Maintenance planner | Maintenance Request/Order queue | PostgreSQL preventive Plan | JWT `maintenance:manage` plus RLS | Due-only generation; creates work, never completion |
| Tool create/assign/life/calibrate | OpenAPI v1 | Tool administration/technician | Operation Task interlock | PostgreSQL Tool and append-only event ledgers | Split manage/execute permissions plus RLS | Event code uniqueness; life/calibration DB trigger |
| Spare-use relation | OpenAPI v1 | Technician/inventory workflow | Maintenance Order | Phase 4 movement plus Phase 6 immutable relation | JWT execute/inventory permissions plus RLS | Consume must reference same Order authority |
| Maintenance audit envelope | NATS 3.0 | Transactional Outbox | Shadow NATS worker | PostgreSQL business/audit rows remain authority | Broker token; scoped DB writer | Deterministic audit message; at-least-once shadow receipt |

## Error Contract

Validation uses HTTP 422. Missing or inconsistent references, invalid state, missing
capability/qualification/evidence, quantity conflicts, and duplicate resources use
HTTP 409 with a stable `detail.code`.
Missing permission uses HTTP 403. Unexpected transaction failure uses the existing
RFC 7807-style `INTERNAL_ERROR` response and rolls back all writes.

## Retention And Deprecation

Controlled revision, execution status/quantity, movement, transformation, genealogy,
external-import, quality measurement/status, maintenance Checklist/result/status,
spare, Tool-life, and Calibration evidence have no application delete path. The
current API is additive and does not deprecate compatibility routes. Retention and
archival must be approved before any destructive policy is introduced.
