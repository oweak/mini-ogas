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
- AI Dispatcher environment discovery no longer assumes a host-repository directory depth.
- The transport contract accepts the explicit `container` deployment mode used by Compose.
- The Background Worker publishes its documented `8084` health port on both deployment paths.

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
YAML and TOML source parsing passed. The complete local gate then passed 320 Central
tests, 40 simulator tests, both Go suites, 6 AI Dispatcher tests, 36 workflow tests plus
9 subtests, 73 Dashboard tests and production build, Ruff correctness, secret/ACL
checks, strict runtime, and PostgreSQL Phase 1/3/4/5/6/7 gates.

## Independent Linux Acceptance

GitHub Container Gate [29489184819](https://github.com/oweak/mini-ogas/actions/runs/29489184819)
passed on commit `829b295` in 1 minute 22 seconds. The clean Ubuntu runner proved:

- every image built from the checked-out source;
- the one-shot migration exited successfully and reported PostgreSQL;
- PostgreSQL, authenticated Redis, authenticated NATS JetStream and MinIO were healthy;
- Central, Background Worker, AI Dispatcher, market simulator, production planner and
  the production Nginx Dashboard were healthy;
- all three SimPy nodes produced accepted heartbeats and typed telemetry;
- at least three heartbeat facts existed in PostgreSQL before restart;
- stopping the nodes and restarting Central plus Background Worker preserved the nodes;
- the migration ledger count did not change during process restart;
- restarting the nodes increased the durable heartbeat count.

## Acceptance Decision

Stage F is accepted. Supervisor and Compose now declare and run the same core component
set, migration has one explicit owner, and both local process mode and clean Linux
Compose mode have executable evidence. This decision does not accept Stage G, Stage H,
multi-host deployment, NATS authority or autonomous AI control.
