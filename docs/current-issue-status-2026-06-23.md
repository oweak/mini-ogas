# Mini-OGAS Current Issue Status

Checked on 2026-06-25 against the active D: project runtime and source tree.
Historical root-level status files remain as older snapshots. This document is
the current technical status for the seven tracked maintenance issues.

| ID | Issue | Current status | Evidence |
| --- | --- | --- | --- |
| 1 | Remove generic VirtualBox runtime UI | Complete | Dashboard runtime path no longer imports or renders generic VirtualBox state. The optional Kali lab path is separate from production-node presentation. |
| 2 | Verify process freshness | Complete | Central API and three microservices expose session token, PID, and start time. `start-system.ps1 -CheckOnly` validates the active launch session. |
| 3 | AI multi-provider fallback | Complete | `ai-dispatcher` attempts `deepseek -> ollama -> lm_studio -> groq -> local-fallback`, records attempts and errors, and has regression tests. Central API also unlocks the encrypted AI vault after administrator login and bypasses dispatcher rule fallback when a live central provider is available. |
| 4 | Go process supervisor | Complete, optional runtime path | Source is in `services/supervisor`, builds to `.runtime/bin/miniogas-supervisor.exe`, validates strict health proofs, monitors process-mode nodes, and supports real restart. It does not run beside the existing script-managed stack. |
| 5 | Dashboard node-count mismatch | Complete | Startup self-check and live snapshot report `3/3` expected production nodes. |
| 6 | Root generated-artifact cleanup | Complete | Root `node_modules` is a valid document-generation dependency; `.runtime` is active state. Old `.playwright-mcp` artifacts were removed and generated folders/logs are ignored. |
| 7 | CRLF/LF policy | Complete | `.gitattributes` now declares LF for source/config/docs files, Dockerfile, `.dockerignore`, `.example`, `.txt`, and CRLF for PowerShell. Modified text files were normalized and `git diff --check` passes. |

## Verification Evidence

- Go supervisor: `go test ./...` passes.
- Go supervisor: production `config/supervisor.toml` parses as seven managed processes.
- AI vault: `services/central-api/ai_runtime.py` and `create_ai_vault.py`
  recreate the encrypted vault format; administrator login unlocks the runtime
  provider chain without keeping the API key in `.env`.
- Main runtime self-check passes with `3/3` production SimPy nodes online.
- Snapshot reports `data_source=live`, `schema_version=2.2`, and
  `simulation_engine=simpy`.
- Strict AI verification passes with `source=api`, `provider=deepseek`,
  and `vault_unlocked=true` when `scripts/start-system.ps1 -CheckOnly
  -RequireAiApi` is run. The script can use `D:\MiniOGAS-VMs\auth.env` without
  printing the password.
- `scripts/check-runtime-status.ps1` performs the login probe from
  `auth.env`, redacts the bearer token, and reports `login_probe.ok=true`.
- `scripts/check_runtime_workflow.py` proves the full runtime loop: fault
  heartbeat, visible alert, confirmation, AI diagnosis, human approval,
  closure, audit archive, notification acknowledgement, offline-record sync,
  live-state preservation, and temporary-node retirement.
- `git diff --check` passes for the active worktree.

## v2.2 First Phase Completion

The v2.2 compatibility/trusted-loop phase is complete as of 2026-06-25. See
`docs/v2.2-first-phase-completion.md` for the acceptance checklist and command
evidence.

## Operating Boundary

Use one process owner at a time:

- Normal current runtime: `scripts/start-system.ps1`.
- Go-managed runtime: `scripts/start-supervisor.ps1 -ReplaceRunning`.

The supervisor wrapper refuses to start if the regular runtime owns service
ports, preventing two controllers from launching duplicate API or node
processes.
