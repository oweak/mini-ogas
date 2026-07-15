# Stage D Incident, Event And Adapter Ownership Evidence

Verified: 2026-07-15

Branch: `codex/current-stage-hardening`

## Goal

Remove incident/event fact state and mutation/restore SQL from `MemoryStore`, preserve
the compatibility API, and prove Redis/NATS/MinIO adapters are not owned by the facade.

## Reproduced Defect

`MemoryStore` directly held seven incident-domain fields: alerts, audit logs, incident
events, global sequence, per-node/run sequences, persisted-event count and AI
diagnoses. It also contained Alert and AI mutation SQL plus Event/Audit restore SQL.
This left one domain split between a monolithic process-local facade and PostgreSQL.

## Implemented Boundary

- `IncidentRepository` owns all seven rebuildable projections and sequences under one
  repository lock.
- Global event sequence and per-node/run local sequence are allocated atomically by
  the repository.
- Alert and AI diagnosis mutation/restore SQL moved to the repository.
- Event and Audit persistence now enter the formal Central fact repository from the
  incident repository; persisted sequence/count state is updated there.
- Audit/Event restore parsing and projection replacement moved to the repository.
- `MemoryStore` retains compatibility properties and run-ID/error-policy orchestration
  only. The seven old fields are absent from its instance dictionary.
- The generated ownership inventory fell from 41 fields before the simulation and
  incident extractions, through 34 after simulation, to 28 fields now; it records only
  `incident_repository` for this domain.
- `MemoryStore` imports no Redis projection, NATS publisher or object-storage adapter.
  `OutboxRepository` is stateless and PostgreSQL-backed.

## Automated Verification

```powershell
cd 'D:\New project\mini-ogas\services\central-api'
.\.venv\Scripts\python.exe -m ruff check `
  app\repositories\incidents.py app\store.py `
  tests\test_incident_repository.py tests\test_event_store.py `
  tests\test_memory_store_ownership_map.py --select E9,F,I
.\.venv\Scripts\python.exe -m pytest tests -q

cd 'D:\New project\mini-ogas'
.\services\central-api\.venv\Scripts\python.exe `
  tools\memory_store_ownership.py --check
```

Results:

- Focused incident/event/database regression: 76 passed before the final adapter gate.
- Final Stage D boundary tests: 7 passed.
- Complete Central API suite: 301 passed.
- Ruff correctness/import checks and generated ownership-map gate: passed.
- Existing event restart gate restores event ID, global/local sequence, run and payload
  from durable storage into a new `MemoryStore`/`IncidentRepository` pair.

## Runtime Evidence

The restarted supervised stack reported Central ready, 12/12 healthy processes,
session match true, background worker ready and NATS live. An authenticated simulation
step created `tick=1` in the worker. Central then refreshed from PostgreSQL and returned
the same event as:

```text
event_id=0159920e-a351-4318-ad12-2f6357554209
global_sequence=10143
run_id=RUN-LOCAL-20260715-200009
stage=tick
source=simulation-engine
```

This is a cross-process durable-fact proof, not shared-memory behavior.

## Architecture Impact

- Fact source: unchanged; PostgreSQL remains authoritative.
- API: no route or payload changes.
- Migration: none.
- Deployment: no new process or port.
- Event transport: one dedicated Outbox publisher remains the only NATS publishing
  path; NATS remains Shadow.

## Stage D Gate

Accepted. Command, Node, Production Execution, Quality, Runtime Simulation State,
Incident/Event, Outbox and infrastructure-adapter ownership now have repository,
restart/transaction and architecture evidence. Stage E remains responsible for
controlled NATS degradation, reconciliation thresholds and rollback proof.
