# Phase 1 Module Boundaries

## Decision

Phase 1 keeps the current modular monolith and edge processes running. It does not perform a one-shot rewrite or claim that `store.py` is already a clean domain layer. New infrastructure is placed behind explicit modules, while legacy coupling is frozen by tests and recorded as debt.

## Current Runtime Boundaries

| Boundary | Current files/processes | Owns | Must not claim |
|---|---|---|---|
| HTTP interface | `app/main.py`, `app/routers/*` | Authentication context, validation, HTTP errors, route compatibility | Business fact ownership |
| Application/legacy domain | `store.py`, `command_manager.py`, `safety_governor.py`, `rules.py` | Existing state transitions, safety decisions, rule evaluation | A fully decomposed ISA-95 domain model |
| Persistence | `core/database.py`, `persistence_repository.py`, `core/migrations.py` | PostgreSQL/SQLite transactions, schema migration, scoped persistence | Exclusive authority for every legacy in-memory mutation |
| Messaging | `core/nats_contracts.py`, `core/nats_publisher.py`, `core/outbox.py` | Envelope validation, NATS shadow transport, durable heartbeat Outbox | Fully wired event/command/audit Outbox |
| Security | `core/auth.py`, `core/security.py`, `core/config.py` | JWT/RBAC, node credential boundary, environment fail-fast | Per-device identity, mTLS, production OT authorization |
| AI decision support | `core/ai/*`, `rule_explanation.py` | Provider selection, provenance, proposal/explanation | Autonomous physical control |
| Edge runtime | `services/node-agent/*` | SimPy/local edge state, heartbeat, command polling and result ledger | Real CNC/PLC connector |
| Presentation | `services/dashboard/*` | Operator projection and workflow controls | Fact generation or inferred production measurements |

## Dependency Direction

The allowed direction is `HTTP interface -> application -> infrastructure/contracts`. Core, model, store and persistence modules may not import HTTP routers. This is enforced by `test_architecture_boundaries.py`.

Seven legacy router-to-router imports remain and are frozen as an exact allowlist:

1. `ai -> demo`
2. `compat -> ai`
3. `compat -> audit`
4. `compat -> demo`
5. `demo -> compat`
6. `ops -> control`
7. `reports -> demo`

Any additional router coupling fails the architecture test. Removal of these seven links is tracked as architecture debt; their presence is not presented as the target architecture.

## Fact Ownership

- Runtime source classification is owned by `Settings.validate_runtime_source()` and the transport contract.
- Durable heartbeat and its NATS intent are committed in one persistence transaction.
- PostgreSQL scope is set per connection and enforced with forced RLS for scoped tables.
- The current `MemoryStore` remains authoritative for several operational transitions. That limitation is explicit in the source-of-truth matrix and prevents a false claim of complete PostgreSQL authority.
- Dashboard code consumes server facts and renders missing values as missing; it does not manufacture OEE, due times, yield or completion.

## Change Rule

New Phase 1 infrastructure must not add behavior to `store.py` unless it is a compatibility adapter. New business domains in later phases must enter application/domain modules with repositories and state-machine tests. Service extraction is permitted only after the modular boundary has a measured operational reason.
