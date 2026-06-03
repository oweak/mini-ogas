# Fault Handling Design

## Processing Pipeline

```text
metric/log event
  -> local rule check
  -> common script repair
  -> central alert
  -> AI diagnosis if needed
  -> policy decision
  -> action execution
  -> audit log
```

## Severity Levels

| Level | Meaning | Example | Action |
|---|---|---|---|
| info | Normal event | heartbeat update | store only |
| low | Common fault | disk cache too large | run local script |
| medium | Complex fault | CPU high with API latency | call AI diagnosis |
| high | Node-level threat | abnormal traffic to one node | isolate node |
| critical | System threat | multiple nodes compromised | stop key services |

## Common Script Repairs

- Clean oversized temporary files.
- Restart a failed simulator service.
- Rotate local logs.
- Reconnect message bus.
- Rebuild local SQLite indexes.

## Hostile Behavior

Hostile behavior includes abnormal attacks and malicious or destructive data:

- brute force login
- abnormal API frequency
- simulated DDoS
- data tampering
- suspicious node command
- multi-node correlated anomaly

## Node Isolation

When a child node becomes dangerous, central control should:

1. Mark the node as `isolating`.
2. Stop accepting production updates from the node.
3. Stop sending new production plans to the node.
4. Keep heartbeat and emergency channel if available.
5. Write incident and audit logs.
6. Allow only administrators to restore the node.

