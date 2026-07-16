# Stage F Component Truth Table

This table is the deployment contract for the current digital-twin system. PostgreSQL
is the central fact authority; Redis is a rebuildable projection; NATS remains Shadow;
MinIO owns controlled object bytes. A declared service is not accepted until its health
and persistence behavior pass the deployment gate.

| Component | Runtime entrypoint | Port | Required dependencies | Health/readiness proof | Durable data | Supervisor | Compose |
| --- | --- | ---: | --- | --- | --- | --- | --- |
| PostgreSQL | External Windows service / `postgres:16-alpine` | 5432 | protected credentials | migration succeeds; fact queries survive restart | PostgreSQL data directory / `postgres_data` | external dependency | `postgres` |
| Redis projection | Memurai / `redis:7-alpine` | 6379 | authenticated password | authenticated `PING`; projection can rebuild | append-only data / `redis_data` | `redis-projection` | `redis` |
| NATS Shadow | `nats-server -c ...` / `nats:2-alpine -js` | 4222, 8222 | auth token, JetStream store | monitoring health plus Central reconciliation | JetStream store / `nats_data` | `nats-server` | `nats` |
| MinIO | `minio server` | 9000, 9001 | root credential | `/minio/health/live` | object directory / `minio_data` | `minio-object-store` | `minio` |
| Schema migration | `python -m app.migrate` | none | PostgreSQL healthy | exit code 0 and safe JSON report | `schema_migrations` ledger | pre-start job | `migrate` one-shot service |
| Central API | `uvicorn app.main:app` | 8080 | migration, Redis, NATS, MinIO | `/health`: liveness `ok`, readiness `ready` | PostgreSQL facts | `central-api` | `central-api` |
| Background worker | `uvicorn app.worker:app` | 8084 | Central, PostgreSQL, Redis, NATS | `/health`: task owner and NATS live | Outbox/receipt facts in PostgreSQL | `background-worker` | `background-worker` |
| AI Dispatcher | `uvicorn app.main:app` | 8081 | dedicated Dispatcher token, provider policy/vault | `/health` plus authenticated `/runtime/status`; live provider proof is recorded in the Stage G gate | no business authority | `ai-dispatcher` | `ai-dispatcher` |
| Market simulator | `uvicorn app.main:app` | 8082 | Central | `/health` | Central persists accepted facts | `market-simulator` | `market-simulator` |
| Production planner | `uvicorn app.main:app` | 8083 | Central | `/health` | Central persists accepted facts | `production-planner` | `production-planner` |
| Dashboard | built `dist` via Vite preview / Nginx production image | 5173 | Central | HTTP 200 | none | `dashboard` | `dashboard` |
| Turning node | `simulator.py` | none | Central, unique node token | fresh authenticated heartbeat | node SQLite / `turning_node_data` | `turning-simpy-node` | `turning-simpy-node` |
| Milling node | `simulator.py` | none | Central, unique node token | fresh authenticated heartbeat | node SQLite / `milling_node_data` | `milling-simpy-node` | `milling-simpy-node` |
| Grinding node | `simulator.py` | none | Central, unique node token | fresh authenticated heartbeat | node SQLite / `grinding_node_data` | `grinding-simpy-node` | `grinding-simpy-node` |

## Migration Ownership

`app.migrate` is the only application caller of `init_db()`. Central API, Background
Worker, authentication, login and persistence-status queries never mutate schema.
Supervisor executes migration before the Go process starts and records the non-secret
result in `.runtime/logs/migration-last.json`. Compose blocks Central on a successful
one-shot `migrate` container.

## Dashboard Serving

Supervisor runs `npm run build` before process startup and serves the built artifact with
`npm run preview`. Compose uses the multi-stage Dashboard Dockerfile and Nginx; neither
deployment path uses `vite dev`.

## Required Secret Inputs

Compose fails configuration when service, dedicated AI Dispatcher, JWT, administrator, three node, PostgreSQL,
Redis, NATS or MinIO credentials are absent. Actual values belong in an ignored root
`.env` or an external secret provider. Supervisor continues to read protected files
under `D:\MiniOGAS-VMs`. Migration reports and health output must not contain credentials
or connection strings.

## Rollback Boundary

NATS can be disabled on the Supervisor path without changing REST/PostgreSQL authority.
Schema rollback is not automatic: restore a tested PostgreSQL backup and deploy the
compatible application version. Redis and NATS stores are rebuildable/shadow data and
must never be used as the only rollback source.
