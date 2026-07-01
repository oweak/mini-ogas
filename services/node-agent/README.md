# node-agent

Lightweight workshop node agent.

Current implementation: Python simulator (`simulator.py`). Earlier prototypes
considered a Go agent, but this workspace now runs the Python simulator in
process, Docker, or VirtualBox-backed lab nodes.

Responsibilities:

- collect metrics
- write local SQLite records
- run simple repair scripts
- publish alerts
- receive central commands
- enter isolation mode
- sync local records to central control

## Simulator

`simulator.py` is a configuration-driven edge-node simulator for a cloud server.
It writes local SQLite heartbeat records, generates constrained production data,
and posts heartbeat snapshots to the central API when available.

Run on the cloud server:

```bash
python simulator.py
```

Or run with Docker Compose from the project `deploy` directory:

```bash
docker compose -f docker-compose.edge.yml up -d --build
```

Configure with environment variables:

- `NODE_CODE`
- `WORKSHOP_TYPE`
- `CENTRAL_API_URL`
- `LOCAL_DB_PATH`
- `HEARTBEAT_SEC`
- `EMERGENCY_AFTER_TICKS`
- `OGAS_API_TOKEN` is required. The agent fails closed on startup when it is
  missing.

The simulation uses device parameters, a state machine, and threshold alarms
instead of independent random values. If the central API is unavailable, records
remain in the local SQLite database for later synchronization.

All outbound requests include `X-Request-ID` and `X-OGAS-Token`, and logs are
emitted as JSON lines for central collection.
