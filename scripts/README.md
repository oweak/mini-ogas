# Repair Scripts

This directory stores common repair scripts executed by the node agent before
requesting AI diagnosis.

Planned scripts:

- `check_process.ps1`
- `clean_temp_cache.ps1`
- `restart_simulator.ps1`
- `rotate_logs.ps1`
- `isolate_node.ps1`
- `kali_redteam_workflow.py`
- `check-postgres-replay-drill.ps1`

Scripts should always return structured JSON-like output to the node agent:

```json
{
  "success": true,
  "action": "clean_temp_cache",
  "message": "temporary cache cleaned"
}
```

## Authorized Kali red-team workflow

`kali_redteam_workflow.py` is intended for the Mini-OGAS lab network only. Run it
from a Kali VM or any isolated test host that can reach `central-api`. It uses
authenticated Mini-OGAS REST endpoints to inject a bounded production abnormality,
verify alert handling, request AI diagnosis, restore the node heartbeat when the
AI classifies the scenario as low risk, and archive the result.

It does not perform host exploitation, credential attacks, persistence, evasion,
or traffic against third-party systems.

The workflow has two separate credentials:

- `OGAS_API_TOKEN` or `--token-file`: node-ingest token used only for heartbeat
  injection and recovery.
- `--admin-password`, `MINIOGAS_ADMIN_PASSWORD`, or `--auth-env-file`: local
  administrator password used to obtain a bearer JWT for protected alert, AI,
  node, and audit operations.

Every run requires an explicit lab acknowledgement with
`--i-understand-this-is-a-lab` or `MINIOGAS_LAB_ACK=YES`. Public targets are
rejected by default; use `--allow-remote-lab` only for an authorized isolated
lab endpoint.

High-risk AI decisions do not auto-isolate or auto-repair by default. When AI
returns `need_isolation=true`, or the injected scenario is critical, the full
workflow stops at `waiting_human_approval` and writes structured evidence. Pass
`--auto-approve-high-risk` only when the lab operator deliberately wants the
script to execute isolation and recovery.

Example:

```powershell
$env:MINIOGAS_API_URL = "http://127.0.0.1:8080"
python scripts/kali_redteam_workflow.py `
  --token-file D:\MiniOGAS-VMs\miniogas-token.txt `
  --auth-env-file D:\MiniOGAS-VMs\auth.env `
  --scenario spindle_overheat `
  --i-understand-this-is-a-lab `
  --evidence-file .runtime\logs\kali-redteam-high-risk-hold.json `
  full
```

Supported scenarios:

- `spindle_overheat`: high-risk machine fault, expected to require confirmation,
  AI diagnosis, and human approval before any isolation or repair is executed.
- `vibration`: high-risk mechanical abnormality, expected to follow the same
  approval-gated path.
- `quality_drift`, `tool_wear`, `coolant_flow`: lower-risk production events
  that may be automatically handled by the rule or AI workflow and archived as
  operator notifications.

Latest evidence files from local verification are written under `.runtime/logs`,
including `kali-redteam-last.json`, `kali-redteam-high-risk-hold.json`, and
`kali-redteam-cleanup.json`.

## PostgreSQL replay drill

`check-postgres-replay-drill.ps1` verifies that the supervised local runtime can
survive a process restart without losing replayable PostgreSQL facts. It logs in
with the local administrator credentials from the runtime root, checks
`/api/persistence/status`, restarts Mini-OGAS through the Go supervisor, waits
for all processes to become healthy, then checks that replay readiness is still
`ok` and shadow-table counts did not decrease. The latest result is also written
to `.runtime/logs/postgres-replay-drill-last.json` for audit evidence.

Example:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check-postgres-replay-drill.ps1
```

Use `-SkipRestart` for a read-only check of the current replay status.
