# Mini-OGAS Principal and Control Authorization Matrix

Status: Stage C control-plane baseline  
Authoritative code: `app/core/auth.py`, `app/core/security.py`,
`app/core/principals.py`, `app/command_control_service.py`, and
`app/safety_governor.py`.

## 1. Non-negotiable invariants

1. An audit actor is derived from a verified credential (`principal_id`), never
   from an `actor` or `operator` request field.
2. Every node credential is bound to exactly one `node_code`; path and body
   resources are checked against that binding.
3. A node token cannot be used as a human bearer token, and a human JWT cannot
   use the machine channel.
4. Production commands are created and changed only through
   `CommandControlService`, which applies resource validation, Safety Governor,
   approval rules, persistence, and audit.
5. AI Agents may read telemetry and submit suggestions. They cannot issue,
   approve, claim, or report production commands.
6. Plaintext opaque credentials are returned only at rotation time. The
   database stores SHA-256 token hashes and revocation metadata.
7. `ALLOW_LEGACY_NODE_TOKEN_AUTH` and `ALLOW_LEGACY_API_TOKEN_AUTH` are disabled
   by default and prohibited for production configuration.

## 2. Principal types

| Principal type | Credential | Stable identity | Resource relationship |
|---|---|---|---|
| Human | Password login, signed JWT | `user:<username>` | Permissions are the union of assigned roles; high-risk actions also require role and confirmation conditions. |
| Node | Independent opaque token | `node:<node_code>` | May access only the node matching the credential's `node_code`. |
| Service | Independent opaque bearer token | `service:<service_id>` | Read-only by default; no production-write permission. |
| AI Agent | Independent opaque bearer token | `ai:<agent_id>` | May submit an auditable suggestion; cannot modify production state. |

## 3. Role and permission matrix

| Role | Principal types | Main permissions | Explicitly excluded |
|---|---|---|---|
| `system_admin` | Human | All registered permissions, including credential management and high-risk approval | Node-only machine operations still require a node credential. |
| `operator` | Human | Node view, command issue, AI diagnosis, execution/inventory work, measurements, maintenance execution, telemetry read | Command approval/rejection, credential management, isolation/restore, simulation control. |
| `quality_engineer` | Human | Quality manage and measure | Quality release and production control. |
| `quality_releaser` | Human | Quality release | Quality measurement mutation and production control. |
| `maintenance_planner` | Human | Maintenance planning | Maintenance execution/verification and production control. |
| `maintenance_technician` | Human | Maintenance execution | Planning, verification, and production control. |
| `maintenance_verifier` | Human | Maintenance verification | Planning, execution, and production control. |
| `data_engineer` | Human | Telemetry lifecycle, projection rebuild, document-object management | Production command issue/approval. |
| `viewer` | Human | Node and telemetry read | All writes. |
| `node_agent` | Node | Own heartbeat/metrics/telemetry, own command receive/report, own part execution | Other nodes, human control endpoints, credential management. |
| `service_reader` | Service | Node and telemetry read | All writes. |
| `ai_agent` | AI Agent | Node/telemetry read and `ai:suggest` | Direct command issue/approval, simulation control, credential management. |

The exact permission tuples are seeded from `ROLE_PERMISSIONS`; database role
and permission rows are policy projections, not an independent policy source.

## 4. Sensitive action matrix

| Action/resource | Required permission | Relationship and conditions | Safety/approval | Audit result |
|---|---|---|---|---|
| Create target-rate command for node | `command:issue` | Human principal; node must exist; target must not exceed reported physical capacity; control mode must permit writes | Low-risk Safety decision; allowed result is the automatic approval rule | `safety:set_target_rate`, then `command:issue` |
| Approve pending command | `command:approve` | Command must exist and be in `waiting_approval` | Command risk is evaluated; high risk requires `CONFIRM` and `system_admin` | Safety decision, then `command:approve` |
| Reject pending command | `command:reject` | Command must exist and be in `waiting_approval` | Low-risk lifecycle Safety decision | Safety decision, then `command:reject` |
| Cancel command | `command:reject` | Command must exist and be cancellable | Low-risk lifecycle Safety decision | Safety decision, then `command:cancel` |
| Retry command | `command:issue` | Source command must exist, be retryable, and target a registered node | Source risk is re-evaluated; high risk requires confirmation | Safety decision, then `command:retry` |
| Claim/report command | `command:receive` / `command:report` | Node principal must match the command's `node_code` | Only claimable approved states are exposed | Command transition/event persistence |
| Isolate/restore/retire node | Specific node control permission | Human principal; target node must exist | High risk, `CONFIRM`, `system_admin`; control-plane isolation is denied | Safety decision and node action audit |
| Approve dispatch plan/escalation | `command:approve` | Verified human Principal; request-body actor is ignored | High risk, `CONFIRM`, `system_admin` | Safety decision and approval audit |
| Submit AI suggestion | `ai:suggest` | Principal type must be `ai_agent` | High/critical suggestions create one human-only `waiting_approval` command; the command is never node-claimable and high risk requires `CONFIRM` plus `system_admin` | Linked suggestion/command facts, Safety decision, terminal decision timestamp and audit |
| Rotate/revoke machine credential | `principal:manage` | Human administrator | Rotation revokes the previous active credential; revocation is irreversible without rotation | Credential lifecycle audit, no plaintext token stored |

## 5. Route-channel boundary

Machine-channel routes are limited to heartbeat, metric/telemetry ingestion,
pending-command receive, command-result reporting, and part execution. The
middleware authenticates an independent node token before route dependencies
run, then `assert_node_resource_access` verifies path or body ownership.

Human control routes use signed JWT bearer authentication. Opaque service and
AI credentials are accepted as bearer tokens only for their own restricted
roles. The compatibility `/api` prefix is stripped once; routers do not register
an additional `/api/...` alias, preventing `/api/api/...` authorization bypasses.

## 6. Verification evidence

The following tests are the minimum Stage C evidence and must remain in the
full Central API gate:

- `test_all_human_write_routes_declare_a_specific_permission`
- `test_node_machine_routes_do_not_register_nested_api_aliases`
- `test_operator_command_gateway_uses_jwt_and_keeps_agent_channel_machine_only`
- `test_high_risk_command_approval_requires_safety_confirmation`
- `test_high_risk_alert_human_approval_closes_active_queues`
- `test_legacy_dispatch_approval_cannot_bypass_safety_governor`
- `test_node_state_changes_cannot_bypass_safety_governor`
- all tests in `test_principal_credentials.py`

This matrix documents the implemented Stage C boundary. It does not claim that
the later PostgreSQL fact-source, event convergence, deployment, or AI-plane
stages are complete.
