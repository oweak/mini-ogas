# Stage F Deployment Convergence Evidence

Date: 2026-07-16

## Gate Scope

Stage F aligns Supervisor, Compose, Dockerfiles, migration ownership, health checks,
volumes, environment variables and Dashboard production serving. It does not promote
NATS to authority, prove multi-host edge deployment, or accept the unified AI plane.

## Implemented Controls

- Added the sole deployment migration entrypoint: `python -m app.migrate`.
- Removed schema mutation from API import, lifespan, authentication and status queries.
- Made `DATABASE_AUTO_MIGRATE=true` fail configuration instead of silently migrating.
- Added a migration ownership architecture test and explicit test schema setup.
- Supervisor now migrates PostgreSQL before process startup and writes a safe evidence file.
- Supervisor builds Dashboard `dist` and serves it with Vite preview, not Vite dev.
- Compose now includes PostgreSQL, authenticated Redis, authenticated NATS JetStream,
  MinIO, one-shot migration, Central, Worker, three microservices, production Nginx
  Dashboard and three consistently identified SimPy nodes.
- Compose has durable volumes, dependency conditions and service health checks.
- Required Compose credentials fail closed; placeholder defaults were removed.
- GitHub Container Gate now starts the full stack and tests migration, infrastructure,
  three heartbeats, restart persistence and production Dashboard serving.

## Local Acceptance

The Windows Supervisor was restarted through `scripts/start-supervisor.ps1 -ReplaceRunning`.
Observed evidence:

- migration status `migrated`, backend `postgresql`, 23 ledger rows;
- Supervisor 12/12 processes healthy;
- Central liveness `ok` and readiness `ready`;
- Background Worker `ok`; NATS `live`;
- Dashboard HTTP 200 with `services/dashboard/dist/index.html` present;
- preflight 3/3 production nodes online with fresh authenticated heartbeats;
- PostgreSQL persistence healthy;
- authenticated login and a live DeepSeek provider smoke call succeeded.

## Automated Source Tests

The focused migration, architecture, authentication and persistence set passed 49 tests.
YAML and TOML source parsing passed. The complete local gate then passed 317 Central
tests, 39 simulator tests, both Go suites, 4 AI Dispatcher tests, 36 workflow tests plus
9 subtests, 73 Dashboard tests and production build, Ruff correctness, secret/ACL
checks, strict runtime, and PostgreSQL Phase 1/3/4/5/6/7 gates.

## Pending Acceptance Evidence

- GitHub full Compose Container Gate conclusion and run URL;
- status/document synchronization after the remote gate.
