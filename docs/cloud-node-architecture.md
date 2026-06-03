# Cloud Node Architecture

Tencent Cloud server `82.156.217.166` is configured as a Mini-OGAS cloud workshop child node.

## Role

- Node code: `cloud-workshop-01`
- Workshop type: `milling`
- System role: cloud milling workshop child node
- Runtime mode: lightweight node agent + local SQLite + SSH reverse tunnel

## Installed tools on Ubuntu

- Python 3 / pip / venv
- Go SDK
- Git
- SQLite3
- jq
- curl / wget
- build-essential
- htop
- net-tools
- unzip / tar

## Cloud directory layout

```text
/opt/mini-ogas/
  node-agent/
    node-agent
  scripts/
  tools/
  logs/

/etc/mini-ogas/
  node-agent.env

/var/lib/mini-ogas/
  node.db
```

## System service

```text
mini-ogas-node-agent.service
```

Responsibilities:

- Collect CPU, memory, disk, network and latency metrics.
- Write metrics to local SQLite database.
- Detect local repair candidates.
- Report metrics to the laptop central API through the reverse tunnel.
- Support center-side isolation and recovery workflow.

## Connection to laptop central node

The laptop runs:

```text
central-api: http://127.0.0.1:8080
```

The cloud node uses:

```text
CENTRAL_API_URL=http://127.0.0.1:18080
```

This is connected by SSH reverse tunnel:

```text
cloud 127.0.0.1:18080 -> laptop 127.0.0.1:8080
```

## Cloud verification commands

```bash
sudo systemctl status mini-ogas-node-agent --no-pager -l
curl http://127.0.0.1:18080/health
sudo sqlite3 /var/lib/mini-ogas/node.db '.tables'
sudo sqlite3 /var/lib/mini-ogas/node.db 'select count(*), max(collected_at) from node_metrics;'
```

## Security note

Only SSH port `22` is required from the public internet. The node agent talks to `127.0.0.1:18080` on the cloud host, so the central API is not exposed publicly.
