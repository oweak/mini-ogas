# Database Design

## Central Database

Recommended database: PostgreSQL.

Core tables:

- `users`
- `roles`
- `permissions`
- `user_roles`
- `role_permissions`
- `nodes`
- `node_status`
- `metrics`
- `alerts`
- `incident_logs`
- `ai_diagnosis`
- `workshops`
- `machines`
- `production_orders`
- `production_records`
- `inventory`
- `market_products`
- `market_demand`
- `market_events`
- `production_plans`
- `audit_logs`
- `hostile_events`

## Child Node Database

Recommended database: SQLite.

Core tables:

- `local_metrics`
- `local_production_records`
- `local_alerts`
- `local_commands`
- `local_operation_logs`
- `sync_status`

## Data Ownership

Child nodes own local raw data. The central node owns global summaries,
permissions, audit logs, final production plans, and reports.

## Synchronization

Each child node stores a local sync cursor. When network recovery occurs, the
node uploads unsynced local records to the central API or message bus.

