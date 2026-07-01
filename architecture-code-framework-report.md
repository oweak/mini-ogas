# Mini-OGAS Architecture and Code Framework Report

Date: 2026-05-11

## Inspection Scope

This report is based on the current project files under `mini-ogas`, including:

- Root project README.
- Architecture, database, fault-handling, market-production, permission, and demo docs.
- PostgreSQL and SQLite schema drafts.
- Docker Compose and environment examples.
- Service-level README files for the planned services.

The repository is currently a design and scaffolding project. It contains
documentation, database schema drafts, deployment examples, and service folders,
but it does not yet contain application source code, Dockerfiles, package
manifests, API handlers, UI code, tests, or executable repair scripts.

## Current Architecture

Mini-OGAS is designed as a central-control plus workshop-node system for a
simulated machining factory. The central control plane coordinates monitoring,
diagnosis, permissions, production planning, market simulation, reporting, and
audit. Workshop nodes collect local metrics and production records, execute
common repairs, publish alerts, receive central commands, and can enter
isolation mode.

Planned central services:

- `dashboard`: Vue 3 dashboard for operations, alerts, plans, market simulation,
  reports, users, roles, and audit logs.
- `central-api`: HTTP API for authentication, authorization, node registry,
  metrics, alerts, incidents, plans, and audit APIs.
- `ai-dispatcher`: DeepSeek gateway responsible for event classification,
  deduplication, caching, API calls, and normalized diagnosis output.
- `market-simulator`: source of product demand, competitor price, seasonal, and
  inventory pressure signals.
- `production-planner`: combines demand, inventory, node health, machine
  availability, defect rate, and tool wear into production plan suggestions.
- `postgres`, `redis`, and `nats`: persistence, cache or short-lived state, and
  event bus.

Planned workshop-node services:

- `node-agent`: local collection, SQLite persistence, simple repair script
  execution, alert publishing, command receiving, isolation, and sync.
- Local SQLite database for offline-tolerant node data.
- Metrics collector, production simulator, and script repair engine.

## Data and Control Flow

Primary event topics are documented around NATS:

- `metrics.node.*`
- `alerts.node.*`
- `commands.node.*`
- `incidents.node.*`
- `production.node.*`
- `market.events`

HTTP APIs are planned for dashboard queries, login and permission management,
manual command confirmation, and report download. Fault handling follows this
progression:

```text
metric/log event
  -> local rule check
  -> common script repair
  -> central alert
  -> AI diagnosis if needed
  -> policy decision
  -> action execution
  -> audit log
```

The AI boundary is documented correctly for a safety-sensitive demo: DeepSeek
can diagnose and recommend, but high-risk actions must pass through policy and
permission checks before execution.

## Persistence Model

The central PostgreSQL schema draft covers core operational tables:

- Users, roles, permissions.
- Nodes and metrics.
- Alerts and AI diagnosis.
- Production orders and production records.
- Market demand.
- Hostile events and audit logs.

The local SQLite schema draft covers:

- Local metrics.
- Local production records.
- Local alerts.
- Local commands.
- Sync cursor state.

The data-ownership model is clear: child nodes own raw local data, while the
central node owns global summaries, permissions, audit logs, final plans, and
reports.

## Deployment Shape

`deploy/docker-compose.central.yml` defines containers for PostgreSQL, Redis,
NATS, `central-api`, `ai-dispatcher`, and `dashboard`. `deploy/docker-compose.node.yml`
defines `node-agent` with a persistent data volume and read-only repair script
mount.

These compose files are useful as topology documentation, but they are not yet
directly runnable because the referenced service directories do not contain
Dockerfiles or implementation code.

## Concrete Optimization Opportunities

1. Add explicit schema indexes for high-volume query paths.
   Metrics, alerts, production records, market demand, hostile events, and audit
   logs will be time-series-like tables. Index candidates include
   `(node_code, created_at)`, `(status, created_at)`, `(severity, created_at)`,
   and `(actor, created_at)` depending on API query patterns.

2. Reconcile documented tables with schema drafts.
   `docs/database-design.md` lists `user_roles`, `role_permissions`,
   `node_status`, `incident_logs`, `workshops`, `machines`, `inventory`,
   `market_products`, `market_events`, and `production_plans`, but
   `database/central-schema.sql` does not define them yet. This is likely the
   next safest schema planning task before API implementation starts.

3. Define durable event payload contracts.
   NATS subjects are documented, but message schemas are not. Adding JSON schema
   examples for metrics, alerts, commands, incidents, and production events
   would reduce coupling between `node-agent`, `central-api`, and the dashboard.

4. Separate development examples from production configuration.
   The example environment files use placeholder secrets and development
   database credentials. Before real deployment, keep `.example` files safe and
   document required real environment variables separately.

5. Add service manifests before implementation grows.
   Each planned service should get a minimal manifest early, such as
   `go.mod`, `pyproject.toml`, or `package.json`, plus a Dockerfile matching the
   documented compose topology. This will make the deployment skeleton
   verifiable.

6. Implement repair scripts as deterministic local actions first.
   The scripts README names planned PowerShell repair scripts, but none exist.
   Implementing read-only checks and JSON result contracts first would create a
   low-risk foundation for later mutation-capable repairs.

7. Add a demo seed-data plan.
   The demo script depends on three online workshop nodes, fault injection,
   market events, user roles, and audit records. Seed data and deterministic
   scenario fixtures will make the interview demo repeatable.

8. Define health-check and isolation state transitions.
   The docs describe `offline`, `isolating`, and restore behavior, but not a
   state machine. A small state transition table would prevent inconsistent
   command handling once implementation begins.

## Low-Risk Improvement Applied

The root README architecture and repository-layout diagrams contained corrupted
box-drawing characters. They were replaced with ASCII tree diagrams. This does
not change system behavior or design intent and improves readability across
terminals and encodings.

## Deferred Changes

No database schema, compose, or service implementation changes were made in this
pass. Those changes would affect future runtime behavior and should be handled
after choosing concrete API query patterns, service languages, and demo data
contracts.

## Recommended Next Implementation Order

1. Reconcile the central schema with the documented permission, incident,
   workshop, inventory, market, and plan tables.
2. Add minimal service manifests and Dockerfiles so compose can build.
3. Define NATS event payload examples and central HTTP API route contracts.
4. Implement `node-agent` local SQLite writes and heartbeat publishing.
5. Implement `central-api` node registry, heartbeat ingestion, metrics query,
   RBAC, and audit foundation.
6. Add deterministic seed data and demo fault-injection scripts.
