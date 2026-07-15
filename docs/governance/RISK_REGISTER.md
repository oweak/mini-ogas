# Mini-OGAS Risk Register

## Control Rules

- P0: may affect personnel/equipment safety, produce seriously false facts or cause irrecoverable loss.
- P1: blocks core business or creates major inconsistency.
- P2: affects availability, performance or operations.
- P3: local behavior or user experience.
- An open P0 prevents Production. “Known issue” is not a treatment.
- P0 entries require an owner, test evidence, contingency/rollback and release disclosure.
- This register is reviewed at each phase gate and after any security, data-loss or command incident.

## Assessment Register

| risk_id | title | category | probability | impact | priority | owner | status | review_date |
|---|---|---|---|---|---|---|---|---|
| R-001 | Scope expansion leaves a permanent half-product | Governance | High | High | P1 | Product owner | Open | 2026-07-20 |
| R-002 | Incorrect domain model forces later rewrite | Architecture | Medium | High | P1 | Chief architect | Open | 2026-07-20 |
| R-003 | `store.py` continues to grow | Architecture | High | High | P1 | Central API owner | Open | 2026-07-20 |
| R-004 | Simulation is presented as production | Data truth | Medium | High | P0 | Data owner | Mitigated, not closed | 2026-07-20 |
| R-005 | SimPy time, rate, wear and quantity diverge | Simulation | High | High | P1 | Simulation owner | Partially mitigated | 2026-07-20 |
| R-006 | Duplicate messages double-count or re-execute | Data/control | High | High | P0 | Platform owner | Mitigated for Phase 3 execution; residual open | 2026-07-20 |
| R-007 | Device protocols and semantics are heterogeneous | Integration | High | High | P1 | Connector owner | Open before pilot | 2026-07-20 |
| R-008 | Unauthorized physical equipment write | Safety | Medium | Extreme | P0 | OT security owner | Contained by absence of connector | 2026-07-20 |
| R-009 | Edge SQLite backlog or corruption | Edge | Medium | High | P1 | Edge owner | Open | 2026-07-20 |
| R-010 | Broker failure interrupts the event chain | Messaging | Medium | High | P1 | Platform owner | Open | 2026-07-20 |
| R-011 | PostgreSQL single point of failure | Persistence | Medium | High | P1 | Operations owner | Open | 2026-07-20 |
| R-012 | Cache staleness causes a false display | Projection | Medium | Medium | P2 | Data owner | Open | 2026-08-13 |
| R-013 | Invalid units, clocks or quality flags | Data quality | High | High | P1 | Data owner | Partially mitigated | 2026-07-20 |
| R-014 | AI hallucination becomes an unsafe action | AI/safety | Medium | High | P0 | AI owner | Contained, not closed | 2026-07-20 |
| R-015 | DeepSeek or another provider is unavailable | AI availability | High | Medium | P2 | AI owner | Partially mitigated | 2026-08-13 |
| R-016 | Secret or API key disclosure | Security | High | High | P0 | Security owner | Rotation required | 2026-07-15 |
| R-017 | Cross-tenant/site data access | Authorization | Medium | Extreme | P0 | Security/data owners | Mitigated for 81 current tables, not closed | 2026-07-20 |
| R-018 | Test/demo state contaminates production | Environment | Medium | High | P0 | Release owner | Mitigated by fail-fast, not closed | 2026-07-20 |
| R-019 | Windows development differs from Linux runtime | Portability | High | Medium | P2 | Platform owner | Open | 2026-08-13 |
| R-020 | Small host capacity is exhausted | Capacity | High | Medium | P2 | Operations owner | Open | 2026-08-13 |
| R-021 | Missing OT/process knowledge creates unsafe assumptions | Safety/domain | High | High | P1 | OT owner | Open | 2026-07-20 |
| R-022 | Project never reaches a real read-only pilot | Delivery | High | High | P1 | Product owner | Open | 2026-07-20 |
| R-023 | Referenced standard versions change | Compliance | Medium | Medium | P2 | Architecture owner | Monitor | 2026-08-13 |
| R-024 | Security lab reaches production network | Cyber safety | Low | Extreme | P0 | Security owner | Contained, not closed | 2026-07-20 |
| R-025 | Telemetry volume overloads business storage | Data platform | Medium | High | P1 | Data owner | Open | 2026-07-20 |
| R-026 | Migration locks tables or causes downtime | Persistence | Medium | High | P1 | Database owner | Open | 2026-07-20 |
| R-027 | Schema/event incompatibility breaks consumers | Contracts | Medium | High | P1 | Platform owner | Open | 2026-07-20 |
| R-028 | Vendor/protocol lock-in | Integration | Medium | Medium | P2 | Architecture owner | Open | 2026-08-13 |
| R-029 | Backups cannot be restored | Resilience | Medium | Extreme | P0 | Operations owner | Open | 2026-07-20 |
| R-030 | Command executes but result receipt is lost | Control | Medium | High | P0 | Command owner | Partially mitigated | 2026-07-20 |
| R-031 | Clock drift corrupts event order | Time | High | Medium | P1 | Platform/OT owners | Open | 2026-07-20 |
| R-032 | Manual correction breaks quantity consistency | Business control | Medium | High | P1 | Operations owner | Phase 4 compensation controlled; duty separation open | 2026-07-20 |
| R-033 | Frontend KPI differs from backend definition | Data truth | High | Medium | P2 | Data/UI owners | Partially mitigated | 2026-08-13 |
| R-034 | Multi-AI complexity provides no value | AI architecture | High | Medium | P2 | AI owner | Deferred | 2026-08-13 |
| R-035 | Go supervisor is mistaken for production HA | Operations | Medium | Medium | P2 | Operations owner | Documented | 2026-08-13 |
| R-036 | Self-signed CA is poorly governed | PKI | Medium | High | P1 | Security owner | Open before mTLS | 2026-07-20 |
| R-037 | Premature microservices increase failure modes | Architecture | High | High | P1 | Chief architect | Open | 2026-07-20 |
| R-038 | Business tables and event store both claim authority | Data architecture | Medium | High | P1 | Data owner | Open | 2026-07-20 |
| R-039 | Logs contain sensitive production data | Privacy/security | Medium | High | P1 | Security owner | Open | 2026-07-20 |
| R-040 | Complex operator UI causes bypass behavior | Human factors | Medium | High | P1 | Product/UX owner | Open | 2026-07-20 |
| R-041 | Master-data correction bypasses governed lifecycle | Business control | Medium | High | P1 | Master-data owner | Open before pilot | 2026-07-20 |
| R-042 | Operation completion is mistaken for inventory or genealogy | Data truth | High | High | P0 | Inventory/data owners | Mitigated for Phase 4 authority; projection/pilot risk remains | 2026-07-20 |
| R-043 | Defect or measurement label is mistaken for an authorized quality disposition | Quality/data truth | High | Extreme | P0 | Quality/operations owners | Mitigated for Phase 5 software authority; physical/pilot risk remains | 2026-07-20 |
| R-044 | Alarm, AI text or software state is mistaken for completed physical maintenance | Maintenance/data truth | High | Extreme | P0 | Maintenance/OT owners | Mitigated for Phase 6 software authority; physical/pilot risk remains | 2026-07-20 |

## Treatment And Evidence Register

| risk_id | description | trigger | mitigation | contingency | evidence |
|---|---|---|---|---|---|
| R-001 | Many planned components could outrun verified vertical slices. | A phase starts while an earlier gate is open. | Binding gates, explicit non-goals, one authority per deliverable. | Freeze additions; return to first failed gate. | `PROJECT_CHARTER.md`; phase plan |
| R-002 | Seeded manufacturing concepts do not yet form a complete MOM model. | New logic encodes incompatible work-order/equipment states. | ISA-95 mapping, state-machine tests and ADR before schema expansion. | Compatibility adapter and controlled migration. | `SOURCE_OF_TRUTH_MATRIX.md`; `store.py` audit |
| R-003 | One 4,162-line object owns unrelated domains and persistence. | Another domain/state transition is added to `MemoryStore`. | Strangler extraction behind repository/application interfaces. | Stop feature growth; extract the touched responsibility first. | `services/central-api/app/store.py` |
| R-004 | SimPy, seed and fixture values can look like live plant data. | Any simulated/simple engine or demo overlay returns `live`, or UI invents a KPI. | Phase 0 source classifier, provenance, `未上报`, Phase 1 environment modes. | Disable affected view/API and disclose incorrect historical label. | `routers/demo.py`; `useRuntimePresentation.ts`; tests |
| R-005 | Acceleration can be confused with physical capacity and wear may lack calibration. | Quantity/rate invariant fails or scenario cannot replay from seed. | Fixed seed/time model, capacity profile tests, calibration registry later. | Revert to read-only replay and mark model invalid. | `test_simulator.py` capacity/time tests |
| R-006 | At-least-once delivery or overlapping writers can duplicate quantities, commands or event sequences. | Duplicate ID changes total, repeats a side effect or degrades persistence. | Edge command ledger, idempotency key, event/message IDs, unique constraints, PostgreSQL sequence serialization, Phase 3 task-row locking/report IDs, and Phase 4 movement/transformation/import hashes. | Quarantine consumer, reconcile from durable ledger, compensate explicitly. | edge SQLite tests; NATS contracts; Phase 3/4 live idempotency gates |
| R-007 | A canonical tag may not match vendor units/capabilities. | Connector reports an unmapped/ambiguous tag or command. | Capability discovery, mapping version, unit normalization, read-only shadow. | Reject mapping and continue offline/read-only. | No connector yet; gate remains open |
| R-008 | A user/service might reach a physical actuator without permission. | Any physical connector exposes write outside controlled-write policy. | No connector today; later whitelist, mTLS identity, approval, interlock and rate limit. | Disable connector credential/network route; invoke OT incident process. | Snapshot `device_write_enabled=false`; code search |
| R-009 | Local records or result outbox can fill/corrupt. | Backlog threshold, SQLite integrity error or disk pressure. | WAL/transactions, capacity thresholds, integrity checks and tested recovery. | Stop claims/commands; preserve DB; restore/reconcile. | simulator local DB/outbox tests; soak missing |
| R-010 | NATS loss can interrupt future authoritative events. | Publish/consume/ack latency or stream unavailable. | Durable outbox/inbox, retries, degraded mode, observability. | Keep REST/read-only path for current phase; replay from outbox. | Current NATS is shadow; `nats_shadow_receipts` |
| R-011 | One database host can lose availability/history. | PostgreSQL health or storage failure. | Backup/PITR design, restore drills, later replication. | Stop mutation, preserve edge queues, restore to validated point. | Single local PostgreSQL; no restore evidence |
| R-012 | In-memory/browser projection can be stale. | Freshness exceeds SLA or source version lags. | Source timestamp/version/freshness badges and rebuildable projections. | Mark stale and block decisions based on it. | Snapshot timestamps; remaining memory cache |
| R-013 | Wrong units/time/quality can produce false decisions. | Unit absent, clock skew high or implausible value. | Canonical units, quality flags, sequence and drift policy; Phase 2 validates UOM dimension, timezone and qualification validity. | Quarantine record and use last-known-good only with stale label. | strict NATS contract; Phase 2 UOM/time tests; host time still not proven |
| R-014 | LLM text may suggest an unsafe or unsupported action. | AI proposal is treated as fact/command or lacks cited evidence. | Proposal-only boundary, rule/safety review, approval, schema validation. | Disable AI provider; retain deterministic rules/manual review. | `rule_explanation.py`; Safety Governor; no direct AI write |
| R-015 | External AI outage can block explanation. | Timeout, quota, DNS or provider error. | Transparent provider status and deterministic rule fallback. | Continue without AI; never forge a provider response. | Provider chain config; independent chain validation incomplete |
| R-016 | A provider key was disclosed in an operator conversation even though repository scans pass. | Any credential appears in chat, logs, source, backup or an over-broad file. | Encrypted vault, owner-only ACL on nine targets, redacted scanner and Production secret validation. | Rotate the provider key, inspect use, invalidate affected sessions and preserve an incident record without the value. | secret scan and ACL gate pass; provider rotation is still required |
| R-017 | Global application roles can still overreach area/equipment scope. | A user reads or mutates another allowed site/resource by changing an ID. | Forced PostgreSQL RLS on all 81 current Phase 1/2/3/4/5/6 tables plus explicit-scope repository queries; add resource policies before shared-site use. | Disable multi-tenant use; isolate deployments. | live role is non-superuser/no BYPASSRLS; 81/81 forced RLS; alternate-site probes returned zero; area/equipment policy remains absent |
| R-018 | Demo seed or test credentials can enter production. | Production starts with demo seed, simulated source or a development secret. | `APP_ENV`, `DATA_SOURCE`, `CONTROL_MODE` and Production fail-fast validation. | Abort startup and purge/rebuild contaminated environment. | seed is conditional; Production rejection tests and environment status |
| R-019 | Windows scripts/path/locking behavior differs from target Linux. | CI/staging differs from local result. | Cross-platform CI and Linux staging before pilot. | Hold release; reproduce in target OS. | Current audit host Windows only |
| R-020 | Single small host cannot meet throughput. | CPU/memory/DB/broker saturation or latency SLA breach. | Load test, bounded retention, modular monolith and capacity budget. | Degrade noncritical services; add resources based on measurements. | No production load baseline |
| R-021 | Software assumptions lack equipment/process owner validation. | Tag, threshold or safe rate has no signed owner. | Named OT owner, tag review, read-only pilot, conservative envelope. | Reject write/decision and escalate to human. | No real OT integration or calibration |
| R-022 | Simulation polish substitutes for a real pilot. | Later phase claims progress without read-only external facts. | Phase 12/production hard gate and pilot evidence checklist. | Stop UI feature work; acquire/define pilot. | Charter non-goals and simulation boundary |
| R-023 | Standards and profiles evolve. | Referenced version changes or certification scope shifts. | Version register and annual review. | Pin current version; assess delta. | Master prompt standards section |
| R-024 | Kali tools or lab credentials reach OT/production. | Route, shared credential or copied dataset crosses boundary. | VM isolation, no production credential, explicit target allowlist/acknowledgement. | Power off lab, revoke credentials, investigate traffic. | default VirtualBox inventory is powered off; startup profile does not currently register Kali; host-only network remains unvalidated |
| R-025 | Raw telemetry growth can overload PostgreSQL. | Retention/storage/latency threshold exceeded. | Retention, aggregation and later historian/time-series store. | Throttle low-priority telemetry; preserve business events. | 6,038 retained heartbeat rows at audit; no capacity test |
| R-026 | A migration can lock tables or create incompatible state. | Upgrade/rollback fails or blocks. | Ordered checksum ledger, additive migrations, repeatability tests, expand/contract and compatibility gates. | Roll back application while retaining additive tables; restore snapshot for destructive failure. | Phase 2-5 additive migrations applied live; production load/restore evidence remains absent |
| R-027 | Producers/consumers disagree on contract version. | Strict model rejects or consumer misreads event. | Generated OpenAPI/AsyncAPI, strict transport models, compatibility tests and version policy. | Quarantine incompatible message and keep prior consumer. | REST and generated contract checks pass; multi-version broker compatibility remains absent |
| R-028 | Direct vendor assumptions block replacement. | Domain code imports a vendor SDK/tag layout. | Connector interface and canonical model. | Isolate adapter; retain read-only export. | No connector framework yet |
| R-029 | A backup exists but cannot recreate service. | Restore drill misses RPO/RTO or integrity checks. | Scheduled restore into isolated environment with evidence. | Stop writes and recover from last verified backup plus edge queues. | No restore drill found |
| R-030 | Device/software applies command but result POST is lost. | Command remains uncertain after edge side effect. | Durable edge result outbox, idempotent command query, independent verification. | Mark `inconclusive`, block retry side effect, reconcile manually. | edge outbox/restart tests; physical verification absent |
| R-031 | Different clocks reorder facts. | Drift threshold or sequence regression detected. | NTP/PTP plan, monotonic sequence, arrival and occurrence timestamps. | Use sequence/ingest order; quarantine ambiguous interval. | Windows Time stopped; clock fields exist but unproven |
| R-032 | Manual edits bypass material/quantity invariants. | Adjustment lacks reason/evidence or creates negative stock. | Phase 4 uses a still-current reconciliation case, separate compensating movement, actor, reason, evidence, audit Outbox, and nonnegative DB guard. | Freeze affected lot and require a new observation/case. | Focused and live reconciliation gates pass; separate approver role remains open |
| R-033 | Browser computes KPI differently from backend. | UI formula is not in KPI registry/backend response. | Phase 0 removed fabricated OEE/yield/progress/due; create KPI registry later. | Display `未上报` and disable decision use. | `App.vue`; `useRuntimePresentation.ts` |
| R-034 | Multiple provider adapters add cost/failure without measured benefit. | Provider added without evaluation target. | Defer multi-agent/provider expansion until evaluation gate. | Use deterministic rules or one approved provider. | chain config exists; value evaluation absent |
| R-035 | Process restart is described as availability. | Supervisor health is used as HA evidence. | Explicit classification and later production orchestration ADR. | Manual service restart; no HA claim. | 9/9 host processes; charter claim policy |
| R-036 | Self-signed PKI may lack revocation/rotation. | Certificate cannot be attributed/revoked. | PKI runbook, inventory, short lifetime and revocation drill. | Revoke CA/certs and isolate connector zone. | mTLS not implemented |
| R-037 | Premature service split creates distributed failure modes. | New service has no independent scale/security/ownership need. | Modular monolith default and split ADR. | Merge boundary back behind interface. | Current microservices are local helper services |
| R-038 | Event and CRUD/shadow tables disagree. | Same object has conflicting latest state. | Declare authority, projection checkpoints and reconciliation jobs. | Freeze mutation and rebuild projection from authority. | matrix shows ambiguous memory/PG ownership |
| R-039 | Logs may include credentials, operator or production-sensitive payload. | Scanner/audit finds secret or excessive payload. | Structured redaction, retention/access policy and tests. | Restrict/delete compromised logs and rotate secret. | secret scan exists; production log policy absent |
| R-040 | Dense workflows can encourage out-of-band work. | Operators cannot complete/understand alarm and command state. | Role-based workflow tests, accessibility/E2E and pilot observation. | Simplify/disable confusing action and use supervised manual procedure. | component tests only; field validation absent |
| R-041 | Phase 2 base records have governed creation but no correction/retirement state machine. | An operator requests a typo fix, deactivation or replacement and attempts direct SQL. | Keep direct SQL unsupported; add effective-dated correction/retirement with permission, reason, approval and audit before pilot. | Freeze the affected master and create a reviewed replacement record; preserve old identifiers and audit. | No update/delete API; revision content/update/delete is database-blocked; lifecycle acceptance remains future work |
| R-042 | A completed operation is treated as available inventory or full traceability. | UI/planner/export derives stock, location, lot or genealogy from Phase 3 quantity totals. | Phase 3 quantity remains operation-scoped; Phase 4 PostgreSQL movement, balance, Lot/Serial/Container, lineage and reconciliation are separate authorities. | Block projection that lacks Phase 4 IDs and provenance. | Phase 4 focused/live gates; legacy inventory and part queue remain explicitly simulated |
| R-043 | A defect counter or AI suggestion is treated as a quality release. | Nonconforming Lot/Serial continues movement without governed inspection, hold, disposition and authorized release. | Phase 5 PostgreSQL plans/specifications/measurements, deterministic evaluation, Hold, NC/disposition and explicit release role are authoritative; AI stays proposal-only. | Freeze the affected Lot and use approved plant quality procedure if the software authority or connector is unavailable. | Phase 5 focused/live gates pass; physical Gauge/QMS/pilot evidence remains absent |
| R-044 | An alarm close, AI explanation, simulated wear value or verified software Order is treated as proof of physical restoration. | Production resumes while the machine/tool remains unsafe, failed, uncalibrated or physically unrepaired. | Phase 6 separates Request, approved Order, Checklist work, coded evidence and independent verification; active maintenance and invalid Tool state block tasks in application and PostgreSQL. Physical claims remain forbidden without authenticated readback and plant procedure. | Keep the affected Asset out of service, stop dependent tasks and use the approved plant maintenance/safety procedure. | Phase 6 focused/live gates pass; no CMMS/EAM, condition source, calibration laboratory, safety PLC or physical readback exists |

## P0 Release Rule

R-004, R-006, R-008, R-014, R-016, R-017, R-018, R-024, R-029, R-030,
R-042, R-043 and R-044 remain release-visible. None is considered closed for
Production. R-016 requires provider-key rotation because disclosure outside the
repository invalidates a clean static scan. Current containment by `no real
connector` is valid only for the development/digital-twin environment.
