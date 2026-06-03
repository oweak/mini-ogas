# Mini-OGAS Development Environment

This project keeps development dependencies inside the D drive project folder as much as possible.

## Installed local environments

- Python virtual environments:
  - `services/central-api/.venv`
  - `services/ai-dispatcher/.venv`
  - `services/market-simulator/.venv`
  - `services/production-planner/.venv`
- Frontend dependencies:
  - `services/dashboard/node_modules`
- Portable Go SDK:
  - `.runtime/tools/go`
- Local build/tool caches:
  - `.runtime/go`
  - `.runtime/npm-cache`
  - `.runtime/bin`

Node.js and npm are still provided by the host installation, while package dependencies are installed in this project.

## Common commands

Run from the project root:

```powershell
.\scripts\setup-dev.ps1
.\scripts\verify-dev.ps1
.\scripts\start-all.ps1
.\scripts\stop-all.ps1
.\scripts\open-vscode.ps1
```

Manual commands:

```powershell
.\services\central-api\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
cd services\dashboard
npm run dev
```

The normal demo URLs are:

- Central API: `http://127.0.0.1:8080`
- Dashboard: `http://127.0.0.1:5173`
