# Go Supervisor Runtime

## Purpose

`services/supervisor` is the only local process-mode runtime owner. Stage F retired
the script-managed launcher so a second controller cannot compete for ports, restart
children, or serve a different frontend artifact. `scripts/start-system.ps1` remains
only as the `-CheckOnly` diagnostic used by the verification gate.

## Managed Processes

The Supervisor owns 12 processes:

1. `nats-server`
2. `redis-projection`
3. `minio-object-store`
4. `central-api`
5. `background-worker`
6. `ai-dispatcher`
7. `market-simulator`
8. `production-planner`
9. `dashboard`
10. `turning-simpy-node`
11. `milling-simpy-node`
12. `grinding-simpy-node`

PostgreSQL is a protected external Windows dependency in process mode. Compose owns
its PostgreSQL container. Both paths use PostgreSQL as the central fact authority.

## Startup Order

`scripts/start-supervisor.ps1` performs the following fail-closed sequence:

1. load protected service, node, PostgreSQL, NATS, Redis and MinIO credentials;
2. validate and protect local secret files;
3. run `python -m app.migrate` and require a PostgreSQL success report;
4. write the non-secret report to `.runtime/logs/migration-last.json`;
5. run the Dashboard production build;
6. build and start the Go Supervisor;
7. require all 12 processes healthy, authenticated Redis PING and MinIO liveness.

Central API, Background Worker, login and status queries never apply schema changes.

## Health Contract

HTTP services are healthy only when their health endpoint succeeds. Central and
Background Worker expose separate liveness and readiness. Node processes are accepted
by the runtime gate only when Central observes fresh authenticated heartbeats.
Dashboard is served from the built `dist` artifact through Vite preview and has an
HTTP status probe; `vite dev` is not a deployment path.

The Go management API is available at:

```text
GET  http://127.0.0.1:9099/supervisor/status
POST http://127.0.0.1:9099/supervisor/start/{process-name}
POST http://127.0.0.1:9099/supervisor/stop/{process-name}
POST http://127.0.0.1:9099/supervisor/restart/{process-name}
POST http://127.0.0.1:9099/supervisor/stopall
```

## Start And Verification

```powershell
.\scripts\start-miniogas.ps1
```

If the intended old runtime owns the ports and ownership transfer is deliberate:

```powershell
.\scripts\start-miniogas.ps1 -ReplaceRunning
```

Read-only verification, including optional live AI proof:

```powershell
.\scripts\start-miniogas.ps1 -CheckOnly -RequireAiApi
```

The complete repository gate is:

```powershell
.\scripts\verify-miniogas.ps1 -RequireAiUnlocked
```

The equivalent container contract and component mapping are documented in
`docs/deployment/component-truth-table.md`.
