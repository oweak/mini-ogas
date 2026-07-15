# Mini-OGAS v3.0 Contracts

> Contract version: 3.0.0
> JSON Schema dialect: Draft 2020-12
> Compatibility rule: additive shadow transport; REST v2 remains authoritative during v3.0.1

## 1. General rules

1. UTF-8 JSON is the only application payload encoding.
2. Every NATS payload MUST validate before publication and after consumption.
3. Unknown top-level and contract-data fields are rejected. An additive field requires a new schema version.
4. All timestamps are RFC 3339 UTC with an explicit `Z` or offset.
5. Identifiers are immutable across retry and redelivery.
6. `event_time`/`occurred_at` is producer time; `published_at` is publisher time; PostgreSQL `ingest_time` is consumer time. They are not aliases.
7. A message acknowledged by NATS is transported, not proven effective.
8. Credentials, passwords, API keys, bearer tokens, private keys, and DSNs are forbidden in all payloads.
9. Payload size MUST be at most 256 KiB in v3.0.1.
10. Subject tokens and `node_code` use lower-case ASCII `[a-z0-9][a-z0-9_-]{0,63}`.

## 2. Subject contract

| Message type | Subject template | `node_code` meaning |
|---|---|---|
| event | `ogas.events.{event_type}.{node_code}` | fact origin |
| heartbeat | `ogas.heartbeats.{node_code}` | reporting edge |
| command | `ogas.commands.{node_code}` | command target |
| audit | `ogas.audit.{resource_type}` | use `central` when not node-specific |

`event_type` and `resource_type` MUST be normalized to the same token grammar. A publisher MUST reject a value containing `.`, `*`, `>`, whitespace, slash, or backslash.

## 3. NATS transport envelope schema

This schema is normative for all v3.0.1 NATS publications.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://mini-ogas.local/schemas/v3/transport-envelope.json",
  "title": "Mini-OGAS v3 Transport Envelope",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version",
    "message_id",
    "message_type",
    "source",
    "node_code",
    "occurred_at",
    "published_at",
    "correlation_id",
    "run_id",
    "sequence",
    "data"
  ],
  "properties": {
    "schema_version": {"const": "3.0"},
    "message_id": {
      "type": "string",
      "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    },
    "message_type": {
      "type": "string",
      "enum": ["event", "heartbeat", "command", "audit"]
    },
    "source": {
      "type": "string",
      "pattern": "^[a-z0-9][a-z0-9_-]{0,63}$"
    },
    "node_code": {"$ref": "#/$defs/nodeCode"},
    "occurred_at": {"type": "string", "format": "date-time"},
    "published_at": {"type": "string", "format": "date-time"},
    "correlation_id": {"type": "string", "minLength": 1, "maxLength": 128},
    "run_id": {"type": "string", "minLength": 1, "maxLength": 128},
    "sequence": {"type": "integer", "minimum": 0},
    "data": {"type": "object"}
  },
  "allOf": [
    {
      "if": {"properties": {"message_type": {"const": "heartbeat"}}},
      "then": {"properties": {"data": {"$ref": "#/$defs/heartbeatData"}}}
    },
    {
      "if": {"properties": {"message_type": {"const": "event"}}},
      "then": {"properties": {"data": {"$ref": "#/$defs/eventData"}}}
    },
    {
      "if": {"properties": {"message_type": {"const": "command"}}},
      "then": {"properties": {"data": {"$ref": "#/$defs/commandData"}}}
    },
    {
      "if": {"properties": {"message_type": {"const": "audit"}}},
      "then": {"properties": {"data": {"$ref": "#/$defs/auditData"}}}
    }
  ],
  "$defs": {
    "nodeCode": {
      "type": "string",
      "pattern": "^[a-z0-9][a-z0-9_-]{0,63}$"
    },
    "severity": {
      "type": "string",
      "enum": ["info", "low", "medium", "high", "critical"]
    },
    "alarm": {
      "type": "object",
      "additionalProperties": false,
      "required": ["type", "severity", "status"],
      "properties": {
        "type": {"type": "string", "pattern": "^[A-Z][A-Z0-9_]{0,63}$"},
        "severity": {"$ref": "#/$defs/severity"},
        "status": {"type": "string", "enum": ["open", "acknowledged", "resolved"]},
        "value": {"type": "number"},
        "threshold": {"type": "number"},
        "unit": {"type": "string", "maxLength": 32}
      }
    },
    "metrics": {
      "type": "object",
      "additionalProperties": false,
      "required": ["cpu_usage", "memory_usage", "disk_usage", "db_latency_ms", "network_latency_ms"],
      "properties": {
        "cpu_usage": {"type": "number", "minimum": 0, "maximum": 100},
        "memory_usage": {"type": "number", "minimum": 0, "maximum": 100},
        "disk_usage": {"type": "number", "minimum": 0, "maximum": 100},
        "db_latency_ms": {"type": "integer", "minimum": 0},
        "network_latency_ms": {"type": "integer", "minimum": 0}
      }
    },
    "production": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "workshop_type",
        "machine_code",
        "finished_quantity",
        "defect_quantity",
        "target_rate",
        "actual_rate",
        "rate_unit",
        "utilization",
        "defect_rate",
        "wip_input",
        "wip_output"
      ],
      "properties": {
        "workshop_type": {"type": "string", "enum": ["turning", "milling", "grinding"]},
        "machine_code": {"type": "string", "minLength": 1, "maxLength": 64},
        "machine_count": {"type": "integer", "minimum": 1},
        "active_order": {"type": "string", "maxLength": 128},
        "active_part_id": {"type": "string", "maxLength": 128},
        "finished_quantity": {"type": "integer", "minimum": 0},
        "raw_finished_quantity": {"type": "integer", "minimum": 0},
        "defect_quantity": {"type": "integer", "minimum": 0},
        "target_rate": {"type": "number", "minimum": 0},
        "actual_rate": {"type": "number", "minimum": 0},
        "target_rate_per_hour": {"type": "number", "minimum": 0},
        "actual_rate_per_hour": {"type": "number", "minimum": 0},
        "nominal_capacity_per_hour": {"type": "number", "minimum": 0},
        "rate_unit": {"type": "string", "enum": ["parts_per_minute", "parts_per_hour"]},
        "utilization": {"type": "number", "minimum": 0, "maximum": 1},
        "defect_rate": {"type": "number", "minimum": 0, "maximum": 1},
        "wip_input": {"type": "integer", "minimum": 0},
        "wip_output": {"type": "integer", "minimum": 0},
        "process_time_sec": {"type": "integer", "minimum": 0},
        "spindle_temp": {"type": "number"},
        "tool_wear_level": {"type": "number", "minimum": 0, "maximum": 100},
        "dispatch_policy": {"type": "string", "maxLength": 64}
      }
    },
    "sync": {
      "type": "object",
      "additionalProperties": false,
      "required": ["last_sync_id", "pending_records"],
      "properties": {
        "last_sync_id": {"type": "integer", "minimum": 0},
        "pending_records": {"type": "integer", "minimum": 0}
      }
    },
    "runtime": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "run_id",
        "scenario_id",
        "simulation_engine",
        "simulation_mode",
        "random_seed",
        "simulation_time",
        "wall_clock_time",
        "deployment_mode",
        "runtime_source",
        "clock_offset_ms",
        "clock_synchronized"
      ],
      "properties": {
        "run_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "scenario_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "simulation_engine": {"type": "string", "enum": ["simple", "simpy", "physical"]},
        "simulation_mode": {"type": "string", "maxLength": 64},
        "simulation_speed": {"type": "number", "exclusiveMinimum": 0},
        "random_seed": {"type": "integer", "minimum": 0},
        "simulation_started_at": {"type": "string", "format": "date-time"},
        "simulation_time": {"type": "string", "format": "date-time"},
        "wall_clock_time": {"type": "string", "format": "date-time"},
        "deployment_mode": {"type": "string", "enum": ["process", "vm", "physical"]},
        "runtime_source": {"type": "string", "enum": ["live", "replay", "fixture", "fallback"]},
        "part_flow_mode": {"type": "string", "maxLength": 64},
        "heartbeat_sec": {"type": "integer", "minimum": 1, "maximum": 60},
        "host": {"type": "string", "maxLength": 128},
        "pid": {"type": "integer", "minimum": 1},
        "clock_offset_ms": {"type": "number"},
        "clock_synchronized": {"type": "boolean"},
        "clock_source": {"type": "string", "maxLength": 128}
      }
    },
    "heartbeatData": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "node_code",
        "status",
        "timestamp",
        "agent_version",
        "uptime_sec",
        "metrics",
        "production",
        "alarms",
        "sync",
        "runtime"
      ],
      "properties": {
        "node_code": {"$ref": "#/$defs/nodeCode"},
        "status": {"type": "string", "enum": ["running", "warning", "fault", "degraded", "isolated", "shutting_down"]},
        "timestamp": {"type": "string", "format": "date-time"},
        "agent_version": {"type": "string", "minLength": 1, "maxLength": 32},
        "uptime_sec": {"type": "integer", "minimum": 0},
        "metrics": {"$ref": "#/$defs/metrics"},
        "production": {"$ref": "#/$defs/production"},
        "alarms": {"type": "array", "items": {"$ref": "#/$defs/alarm"}, "maxItems": 64},
        "sync": {"$ref": "#/$defs/sync"},
        "runtime": {"$ref": "#/$defs/runtime"}
      }
    },
    "eventData": {
      "type": "object",
      "additionalProperties": false,
      "required": ["event_type", "severity", "message", "payload"],
      "properties": {
        "event_type": {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,63}$"},
        "severity": {"$ref": "#/$defs/severity"},
        "message": {"type": "string", "minLength": 1, "maxLength": 1024},
        "scenario_id": {"type": "string", "maxLength": 128},
        "local_sequence": {"type": "integer", "minimum": 0},
        "payload": {"type": "object", "maxProperties": 64}
      }
    },
    "commandData": {
      "type": "object",
      "additionalProperties": false,
      "required": ["command_id", "version", "command_type", "risk_level", "status", "operator", "parameters", "expires_at"],
      "properties": {
        "command_id": {"type": "integer", "minimum": 1},
        "version": {"type": "integer", "minimum": 1},
        "command_type": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,63}$"},
        "risk_level": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        "status": {"type": "string", "enum": ["pending", "approved", "dispatched", "received", "applied", "verified", "rejected", "expired", "failed"]},
        "operator": {"type": "string", "minLength": 1, "maxLength": 128},
        "parameters": {"type": "object", "maxProperties": 32},
        "expires_at": {"type": "string", "format": "date-time"},
        "confirmation_required": {"type": "boolean"},
        "reason": {"type": "string", "maxLength": 1024}
      }
    },
    "auditData": {
      "type": "object",
      "additionalProperties": false,
      "required": ["actor", "action", "resource_type", "resource_id", "result"],
      "properties": {
        "actor": {"type": "string", "minLength": 1, "maxLength": 128},
        "action": {"type": "string", "minLength": 1, "maxLength": 128},
        "resource_type": {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,63}$"},
        "resource_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "result": {"type": "string", "minLength": 1, "maxLength": 64},
        "detail": {"type": "string", "maxLength": 4096}
      }
    }
  }
}
```

## 4. Command pull response schema

This is the target Agent Protocol response. The existing v2 list response remains compatible through an adapter until the command migration phase.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://mini-ogas.local/schemas/v3/command-pull-response.json",
  "title": "Mini-OGAS v3 Command Pull Response",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "node_code", "server_time", "lease_seconds", "commands"],
  "properties": {
    "schema_version": {"const": "3.0"},
    "node_code": {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,63}$"},
    "server_time": {"type": "string", "format": "date-time"},
    "lease_seconds": {"type": "integer", "minimum": 1, "maximum": 300},
    "commands": {
      "type": "array",
      "maxItems": 50,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["command_id", "version", "command_type", "risk_level", "status", "parameters", "expires_at"],
        "properties": {
          "command_id": {"type": "integer", "minimum": 1},
          "version": {"type": "integer", "minimum": 1},
          "command_type": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,63}$"},
          "risk_level": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
          "status": {"const": "dispatched"},
          "parameters": {"type": "object", "maxProperties": 32},
          "expires_at": {"type": "string", "format": "date-time"},
          "confirmation_required": {"type": "boolean"},
          "correlation_id": {"type": "string", "minLength": 1, "maxLength": 128}
        }
      }
    }
  }
}
```

Rules:

- A command already applied by `(command_id, version)` is acknowledged as duplicate and not executed again.
- The edge rejects an expired command before mutation.
- Empty `commands` is a valid successful response.
- The server does not return commands for another node even when a caller changes the URL path.

## 5. Offline replay request schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://mini-ogas.local/schemas/v3/offline-replay-request.json",
  "title": "Mini-OGAS v3 Offline Replay Request",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "node_code", "batch_id", "first_sequence", "last_sequence", "records"],
  "properties": {
    "schema_version": {"const": "3.0"},
    "node_code": {"type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,63}$"},
    "batch_id": {
      "type": "string",
      "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    },
    "first_sequence": {"type": "integer", "minimum": 1},
    "last_sequence": {"type": "integer", "minimum": 1},
    "records": {
      "type": "array",
      "minItems": 1,
      "maxItems": 100,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["local_id", "record_type", "created_at", "original_request_id", "payload"],
        "properties": {
          "local_id": {"type": "integer", "minimum": 1},
          "record_type": {"type": "string", "enum": ["heartbeat", "event", "command_result", "production_record"]},
          "created_at": {"type": "string", "format": "date-time"},
          "original_request_id": {"type": "string", "minLength": 1, "maxLength": 128},
          "original_http_status": {"type": "integer", "minimum": 0, "maximum": 599},
          "original_error": {"type": "string", "maxLength": 1024},
          "payload": {"type": "object", "maxProperties": 128}
        }
      }
    }
  }
}
```

Cross-field rules enforced outside JSON Schema:

- `first_sequence <= last_sequence`;
- record `local_id` values are strictly increasing;
- first/last values equal the first/last record IDs;
- `(node_code, local_id)` and `original_request_id` are idempotency keys;
- the server reports accepted, duplicate, and rejected IDs separately;
- one invalid record does not silently accept the whole batch.

## 6. Worker persistence mapping

The v3.0.1 `NATSEventWorker` writes each validated transport message to PostgreSQL table `nats_shadow_receipts`. It MUST NOT apply the same heartbeat, command, audit, or incident to an authoritative business table a second time. This is the meaning of shadow mode.

| Receipt column | Envelope source | Rule |
|---|---|---|
| `message_id` | `message_id` | primary idempotency key |
| `subject` | actual NATS subject | must match message type and validated data token |
| `message_type` | `message_type` | heartbeat, event, command, or audit |
| `source_node` | `node_code` | origin/target identity as defined by message type |
| `run_id` | `run_id` | immutable run binding |
| `local_sequence` | `sequence` | producer-local sequence; not a business global sequence |
| `correlation_id` | `correlation_id` | trace binding |
| `occurred_at` | `occurred_at` | producer timestamp |
| `ingested_at` | worker clock | PostgreSQL-consumer timestamp |
| `payload_json` | complete validated envelope | canonical UTF-8 JSON |

`message_id` is unique. Insert conflict is acknowledged as an idempotent duplicate and MUST NOT create another row. The existing `event_store.global_sequence` is deliberately not reused: it is an authoritative business ordering boundary, while per-node heartbeat sequences overlap. A later phase may promote selected NATS messages into business projections only behind a separate migration contract and dual-read verification.

## 7. v2 compatibility mapping

| v2 input | v3 envelope source |
|---|---|
| heartbeat `node_code` | envelope `node_code` and `source` |
| heartbeat `timestamp` | `occurred_at` |
| heartbeat `runtime.run_id` | `run_id` |
| v2 `runtime.runtime_source=node-agent` | v3 `runtime_source=live`; adapter records transport origin separately |
| heartbeat `sync.last_sync_id` | `sequence` |
| generated request/event ID | `message_id` and `correlation_id` |
| accepted Central time | `published_at`; consumer adds `ingest_time` |

The adapter may temporarily set missing v3 clock fields to measured Central values only in shadow mode, and must mark the conversion in payload metadata. Before direct edge publication, the edge must produce all required v3 fields itself.

## 8. Validation and failure behavior

- Invalid outbound payload: do not publish; return `degraded` with validation category and no secret or full sensitive payload.
- NATS unavailable: keep the accepted REST result, increment a failure counter, and expose `degraded`; never return false NATS success.
- Invalid inbound payload: send to a bounded dead-letter subject or terminate delivery after the configured maximum; do not write business tables.
- PostgreSQL unavailable: do not acknowledge the JetStream message; use bounded exponential backoff.
- Duplicate payload: commit/observe the existing row, acknowledge, and increment the duplicate metric.
- Poison payload: after five deliveries, preserve metadata and reason in a dead-letter stream; no infinite hot loop.

## 9. Versioning

- `3.0` permits no unannounced new required field.
- Compatible optional additions require `3.1` and dual-reader tests.
- Breaking changes require `4.0`, a new schema ID, and a migration window.
- Producers publish one version per message. Consumers reject unsupported versions explicitly.
- Schemas are frozen by documentation in v3.0.0 and must be represented by executable models/tests in v3.0.1.
