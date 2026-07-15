# Mini-OGAS Project Charter

## Document Control

| Field | Value |
|---|---|
| Status | Active engineering charter |
| Effective date | 2026-07-13 |
| Last verified | 2026-07-14 |
| Baseline repository | `D:\New project\mini-ogas` |
| Governing prompt | `MINI_OGAS_CODEX_ENGINEERING_MASTER_PROMPT.md` |
| Governing prompt SHA-256 | `05D7A7D08D55057FE93BE7DEEA2AB1B03A03D169282D486EDAE431AC6E6301C5` |
| Current product class | Trusted simulation prototype evolving toward a discrete-manufacturing MOM |
| Current operating class | Development / digital-twin laboratory only |
| Production authorization | Not granted |
| Current gate | Phase 0 and Phase 1 pass; Phase 2 is the first unmet gate |

## Mission

Mini-OGAS is intended to become an industrial operations management platform for discrete manufacturing. It shall coordinate production orders, operations, equipment context, material flow, alarms, human approvals, auditable commands and AI-assisted diagnosis without hiding the origin or confidence of any fact.

The current repository is not a production MES/MOM and shall not be represented as one. Its present value is a verifiable simulation and engineering laboratory in which the team can prove contracts, state machines, persistence, safety policy, idempotency, auditability and operator workflows before connecting a real asset.

## Current Truth

As of this charter:

- Three local Python processes run deterministic/simple or SimPy workshop simulations.
- `central-api`, dashboard, AI dispatcher, market simulator, production planner, NATS, PostgreSQL and a Go supervisor run on one Windows host.
- PostgreSQL is the configured central historical store, but many state transitions still originate in `MemoryStore` and are shadow-written.
- NATS is a loopback shadow transport, not yet the authoritative distributed command/event path.
- Dashboard telemetry is simulated. Machines, market, inventory, topology and some work-order context include central demo seed data.
- DeepSeek can provide diagnosis/explanation after administrator unlock; the LLM is not a fact authority and is not authorized to execute equipment commands.
- There is no OPC UA, Modbus, MQTT device connector, PLC integration, historian integration or physical equipment write path.
- Five VirtualBox workshop/central/Kali machines are registered in the default profile and powered off; the active runtime uses host processes, and the startup VirtualBox profile is not yet reconciled with the default inventory.
- Phase 2 organization, asset, personnel, qualification, BOM, Routing, document revision and governed work-order release authorities are not implemented.

## In Scope

1. A canonical ISA-95-inspired domain model for tenant, site, area, work center, equipment, material, work order, operation, alarm, command and audit evidence.
2. Explicit environment, data-source and control modes.
3. PostgreSQL-backed authoritative business facts with repeatable migrations and reconciliation.
4. Edge buffering, idempotent ingestion, durable command lifecycle and effect verification.
5. Read-only-first industrial connector onboarding, followed by shadow and tightly governed controlled write.
6. Operator, supervisor, administrator and auditor workflows with data-level authorization.
7. AI proposals that cite input facts, express uncertainty and remain subject to policy and human approval.
8. Observable, testable and recoverable deployments with evidence-backed phase gates.
9. A physically isolated security laboratory for bounded testing that has no production credentials.

## Explicit Non-Goals For The Current Baseline

- Claiming production readiness, high availability, safety certification or deterministic real-time control.
- Treating SimPy output, random market signals, seeded machine records or browser calculations as production facts.
- Allowing an LLM to directly control equipment.
- Connecting a real device or enabling a real write before the read-only, shadow, safety and rollback gates are complete.
- Treating the Go process supervisor as production orchestration or HA.
- Treating a single-host NATS/PostgreSQL deployment as distributed fault tolerance.
- Treating the Kali workflow as proof of industrial cyber-resilience.

## Non-Negotiable Engineering Principles

1. **Truth before appearance.** Every displayed value must identify whether it is live, simulated, replayed, fixture, fallback, seeded or unknown.
2. **One authority per fact.** Every domain object must have one declared authority and a reconciliation rule.
3. **No browser facts.** The dashboard may format or filter facts but may not invent KPI, progress, due dates, machine status or resolution effects.
4. **Proposal is not execution.** Rules and AI may propose. Safety policy, authorization, approval and the command state machine govern execution.
5. **Read-only first.** A connector progresses through offline, read-only, shadow and controlled-write stages; it cannot skip stages.
6. **PostgreSQL central, SQLite edge/test.** SQLite is not a production central authority.
7. **At-least-once implies idempotency.** Events, commands, results and projections require stable identifiers, deduplication and replay behavior.
8. **Audit is a business requirement.** Actor, role, scope, request, decision, result, timestamps and evidence must survive restart.
9. **Failure must be visible.** Fallback, stale, degraded and unverified states are explicit; silent substitution is prohibited.
10. **Phase gates are binding.** A later phase cannot be claimed complete while an earlier gate is open.

## Authority And Roles

| Role | Authority |
|---|---|
| Product owner | Defines pilot scope, business acceptance and non-goals |
| Chief architect | Owns architecture boundaries, ADRs and phase gate recommendation |
| OT/equipment owner | Owns device capability, tag semantics, safe operating envelope and write authorization |
| Security owner | Owns zones, conduits, identity, secrets and security-lab separation |
| Data owner | Owns fact authority, retention, quality, reconciliation and KPI definitions |
| Operations owner | Owns deployment, backup, restore, incident and edge recovery evidence |
| Test owner | Owns independent acceptance evidence and regression gates |
| AI owner | Owns model/provider policy, evaluation, provenance and cost controls |

No software agent may self-authorize production access, equipment write, risk acceptance or a phase gate.

## Success Criteria

The project succeeds only when all of the following are evidenced, not merely implemented in UI:

- A real pilot scope and named equipment owner exist.
- Read-only connector data has been mapped, quality-checked and reconciled against the external owner.
- Business and telemetry fact authorities are unambiguous and durable.
- Duplicate, delayed, out-of-order and replayed messages do not corrupt counts or execute commands twice.
- High-risk changes require scoped authorization and approval.
- Command execution is verified from independent equipment state, not only from an API acknowledgement.
- Backup restore, edge reconnect, broker outage and central restart have been exercised.
- Production and laboratory networks, identities, credentials and data are separated.
- AI output is traceable to input facts, never silently substituted for a rule or equipment fact, and cannot bypass safety policy.
- The final production gate has written approval from product, OT, security, operations and test owners.

## Claims Policy

Allowed current wording:

- “SimPy-based digital-twin prototype”
- “PostgreSQL-backed shadow persistence”
- “Loopback NATS shadow transport”
- “AI-assisted proposal and explanation workflow”
- “Logical node isolation in a laboratory runtime”

Prohibited current wording:

- “Live factory connection”
- “Industrial production deployment”
- “AI autonomous factory control”
- “Physical device isolation”
- “Cyberattack defense proven”
- “High availability”

## Change And Gate Governance

Each phase must produce:

- an updated baseline and test record;
- an explicit list of completed, partial and absent capabilities;
- risks and architecture debt with owner and exit condition;
- migration, rollback and compatibility evidence;
- a gate decision with dated evidence.

Any contradiction between documentation and executable evidence is resolved in favor of executable evidence. A failing or skipped mandatory test keeps the gate open.
