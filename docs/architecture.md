# Architecture Design

## System Overview

Mini-OGAS uses a central-control plus workshop-node architecture. The laptop
runs heavy coordination services. Low-end cloud servers run lightweight child
nodes that can collect data, make local decisions, and sync with the central
node.

```text
Dashboard
   |
Central API ---- PostgreSQL
   |       \---- Redis
   |       \---- AI Dispatcher ---- DeepSeek API
   |
NATS Message Bus
   |
Workshop Nodes: turning, milling, grinding
```

## Central Control Node

Responsibilities:

- Node registry and heartbeat supervision.
- Global metrics aggregation.
- Alert and incident management.
- AI diagnosis orchestration.
- Permission and audit management.
- Market simulation and production planning.
- Factory report generation.

Recommended services:

- `central-api`
- `dashboard`
- `ai-dispatcher`
- `market-simulator`
- `production-planner`
- `postgres`
- `redis`
- `nats`

## Workshop Nodes

Each workshop node has a dedicated local database and a lightweight agent.

Responsibilities:

- Collect local operations metrics.
- Store local production records.
- Execute common repair scripts.
- Receive central commands.
- Report alerts and hostile events.
- Enter isolation mode when required.

Workshops:

- `turning-workshop`: lathes and shaft products.
- `milling-workshop`: milling machines and flange products.
- `grinding-workshop`: grinding machines and precision sleeve products.

## Communication

Use NATS for event and command messaging:

- `metrics.node.*`
- `alerts.node.*`
- `commands.node.*`
- `incidents.node.*`
- `production.node.*`
- `market.events`

Use HTTP APIs for:

- Dashboard queries.
- Login and permission management.
- Manual command confirmation.
- Report download.

## Failure Handling Levels

```text
L0: script repair
L1: rule engine alert
L2: DeepSeek diagnosis
L3: node isolation or system stop
```

Common problems should be handled locally by scripts before using DeepSeek.
This reduces API pressure and makes the system more reliable under low-cost
hardware.

## AI Safety Boundary

DeepSeek is an assistant, not the final authority. High-risk actions must pass
through the policy engine and permission system before execution.

```text
event -> classifier -> AI diagnosis -> policy engine -> permission check -> action
```

