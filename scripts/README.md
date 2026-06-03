# Repair Scripts

This directory stores common repair scripts executed by the node agent before
requesting AI diagnosis.

Planned scripts:

- `check_process.ps1`
- `clean_temp_cache.ps1`
- `restart_simulator.ps1`
- `rotate_logs.ps1`
- `isolate_node.ps1`

Scripts should always return structured JSON-like output to the node agent:

```json
{
  "success": true,
  "action": "clean_temp_cache",
  "message": "temporary cache cleaned"
}
```

