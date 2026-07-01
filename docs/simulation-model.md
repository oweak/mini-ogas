# Simulation Model

Mini-OGAS uses constraint-driven simulation for cloud workshop nodes. A node is
not a random data generator; it is a remote workshop edge node with local state,
local persistence, heartbeat synchronization, threshold alarms, and recovery
behavior.

## Public Data Basis

The milling simulation is based on the structure of public tool-wear datasets:

- NASA Open Data Portal, Milling Wear dataset.
- NASA Milling Wear resource `mill.zip`, updated May 29, 2025.
- The dataset records milling experiments under different speeds, feeds, and
  depths of cut, and includes milling insert wear measurements.

The dashboard does not bundle the external dataset. Instead, it uses the public
dataset structure to define realistic relationships among cycle time, tool wear,
temperature, production output, defect rate, and alarm thresholds.

## State Machine

```text
idle -> running -> warning -> fault -> maintenance -> running
                         `-> isolated -> maintenance -> running
```

High-risk transitions, such as `fault -> isolated`, must be approved by a
workshop manager and written to audit logs.

## Causal Rules

- Output grows by machine cycle time.
- Tool wear grows with cumulative output.
- Temperature rises with load and tool wear.
- Defect rate rises when tool wear crosses warning thresholds.
- Fault state stops or slows production and creates pending sync records.
- AI may diagnose and recommend, but cannot directly isolate nodes or dispatch
  orders without approval.

## Heartbeat Payload

Each cloud node sends a state snapshot rather than a bare online signal:

```json
{
  "node_code": "milling-workshop-01",
  "status": "fault",
  "metrics": {
    "cpu_usage": 72.5,
    "memory_usage": 61.2,
    "disk_usage": 64.2,
    "network_latency_ms": 53,
    "db_latency_ms": 38
  },
  "production": {
    "active_order": "WO-20260530-004",
    "machine_code": "MILL-02",
    "finished_quantity": 39,
    "defect_quantity": 4,
    "tool_wear_level": 76,
    "spindle_temp": 89
  },
  "alarms": [
    {
      "type": "SPINDLE_TEMP_HIGH",
      "severity": "high",
      "status": "open"
    }
  ]
}
```
