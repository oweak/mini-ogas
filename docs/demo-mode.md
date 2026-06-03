# Demo Mode

This mode is designed for graduate interview demonstration. It runs without
PostgreSQL, Redis, NATS, or cloud servers. The central API keeps data in memory
and exposes scenario injection endpoints.

## Start

Terminal 1:

```powershell
.\scripts\start-central-api.ps1
```

Terminal 2:

```powershell
.\scripts\start-dashboard.ps1
```

Open:

```text
http://127.0.0.1:5173
```

## Scenarios

```powershell
.\scripts\demo-scenarios.ps1 normal
.\scripts\demo-scenarios.ps1 common_fault
.\scripts\demo-scenarios.ps1 complex_fault
.\scripts\demo-scenarios.ps1 hostile_attack
.\scripts\demo-scenarios.ps1 market_shift
```

## What To Show

- `common_fault`: disk pressure is handled by script first.
- `complex_fault`: CPU and API latency trigger AI diagnosis recommendation.
- `hostile_attack`: hostile traffic isolates a child node to protect the system.
- `market_shift`: virtual market demand changes and production plan is regenerated.

