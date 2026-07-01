# central-api

Central HTTP API service.

Responsibilities:

- authentication and authorization
- node registry
- metrics query
- alert management
- incident management
- production plan APIs
- audit log APIs

Recommended implementation: Go or Python FastAPI.

## Minimal Demo API

This service now includes a small FastAPI runtime for the dashboard demo.

Run:

```bash
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8080 --reload
```

Endpoints:

- `GET /health`
- `GET /api/dashboard-state?mode=normal|emergency`
- `POST /api/issues/{issue_id}/actions`
- `POST /api/node-heartbeats`
