# Permission Design

## Permission Model

Use authentication plus RBAC plus resource constraints.

Roles:

- `system_admin`
- `ops_engineer`
- `production_planner`
- `workshop_manager`
- `auditor`
- `demo_viewer`

## Example Permissions

| Permission | Description |
|---|---|
| `node:view` | View node status |
| `node:isolate` | Isolate a workshop node |
| `node:restore` | Restore an isolated node |
| `alert:handle` | Handle alerts |
| `plan:view` | View production plans |
| `plan:update` | Update production plans |
| `market:view` | View market simulation |
| `report:generate` | Generate factory reports |
| `audit:view` | View audit logs |
| `ai:diagnose` | Request AI diagnosis |

## High-Risk Actions

High-risk actions require administrator permission and must create audit logs:

- isolate node
- restore isolated node
- stop central services
- override AI policy result
- update production plan manually
- delete or archive incident logs

## Demonstration Focus

The permission system should be demonstrated together with real operations:

- An ops engineer can repair a service but cannot change production plans.
- A production planner can adjust plans but cannot isolate nodes.
- An auditor can view logs but cannot operate nodes.
- A system administrator can perform high-risk actions with audit records.

