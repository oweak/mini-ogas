#!/usr/bin/env python3
"""
Mini-OGAS Node Agent — standalone Python process that sends real host metrics
(CPU, memory, disk, network) as heartbeats + metric snapshots to central-api.

Usage:
  python agent.py --node-code turning-workshop-01
  python agent.py --node-code milling-workshop-01 --interval 3
  python agent.py --node-code cloud-db-01 --workshop-type database

Each agent maps to one workshop node.  Run one process per node to simulate
a real distributed factory where every workshop has its own edge agent.
"""

import argparse
import json
import os
import random
import signal
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None
    print("[agent] psutil not installed — using synthetic metrics (pip install psutil)", file=sys.stderr)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_API_URL = os.getenv("OGAS_CENTRAL_URL", "http://127.0.0.1:8080")
DEFAULT_TOKEN = os.getenv("OGAS_NODE_TOKEN", os.getenv("API_ACCESS_TOKEN", ""))

# Workshop-type → baseline ranges to simulate realistic per-workshop differences
BASELINES: dict[str, dict[str, tuple[float, float]]] = {
    "turning":   {"cpu": (30, 55), "mem": (35, 60), "disk": (45, 70)},
    "milling":   {"cpu": (40, 65), "mem": (45, 70), "disk": (50, 75)},
    "grinding":  {"cpu": (35, 58), "mem": (40, 65), "disk": (55, 80)},
    "cloud":     {"cpu": (40, 70), "mem": (50, 72), "disk": (40, 65)},
    "database":  {"cpu": (15, 40), "mem": (45, 68), "disk": (55, 82)},
}

AGENT_VERSION = "0.2.0"
# Approximate db file size per workshop — simulates local SQLite storage
DB_SIZE_BASELINE_PER_NODE: dict[str, int] = {
    "turning": 38_000_000, "milling": 42_000_000, "grinding": 35_000_000,
    "cloud": 28_000_000, "database": 320_000_000,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _real_or_synthetic(rng: random.Random, ws_type: str) -> dict:
    """Return {cpu, mem, disk} — real if psutil is available, else synthetic."""
    if psutil:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory().percent
        disk_val = psutil.disk_usage("/").percent
        return {"cpu": round(cpu, 1), "mem": round(mem, 1), "disk": round(disk_val, 1)}

    # Synthetic random walk anchored to workshop baselines
    bl = BASELINES.get(ws_type, BASELINES["turning"])
    return {
        "cpu": round(rng.uniform(*bl["cpu"]), 1),
        "mem": round(rng.uniform(*bl["mem"]), 1),
        "disk": round(rng.uniform(*bl["disk"]), 1),
    }


def _api_request(url: str, data: dict | None = None, token: str = "", method: str = "GET") -> dict:
    """Minimal HTTP helper — no third-party deps."""
    headers = {
        "Content-Type": "application/json",
        "X-OGAS-Token": token,
        "X-OGAS-Session-Token": os.environ.get("OGAS_SESSION_TOKEN", ""),
    }
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {"error": exc.code, "detail": detail}
    except urllib.error.URLError as exc:
        return {"error": "connection", "detail": str(exc.reason)}


def _local_db_size(ws_type: str, rng: random.Random) -> tuple[int, str]:
    """Return local DB size plus source: local_file or estimated."""
    configured_path = os.getenv("LOCAL_DB_PATH", "").strip()
    candidates = [Path(configured_path)] if configured_path else [Path("node.db")]
    for path in candidates:
        try:
            if path.exists() and path.is_file():
                return path.stat().st_size, "local_file"
        except OSError:
            continue
    baseline = DB_SIZE_BASELINE_PER_NODE.get(ws_type, 30_000_000)
    return baseline + rng.randint(-500_000, 1_500_000), "estimated"


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def run_agent(node_code: str, api_url: str, token: str, interval: float,
              workshop_type: str | None = None) -> None:
    rng = random.Random(hash(node_code) & 0xFFFFFFFF)
    start_time = time.time()
    pid = os.getpid()
    ws_type = workshop_type or _infer_workshop_type(node_code)

    print(f"[agent:{node_code}] pid={pid}  ws={ws_type}  "
          f"api={api_url}  interval={interval}s  psutil={'yes' if psutil else 'no'}")
    running = True

    def _shutdown(signum, frame):
        nonlocal running
        print(f"\n[agent:{node_code}] signal={signum} — shutting down")
        running = False
        # Send final shutting_down heartbeat
        db_size, db_size_source = _local_db_size(ws_type, rng)
        _api_request(
            f"{api_url}/nodes/{node_code}/heartbeat",
            data={"node_code": node_code, "agent_version": AGENT_VERSION,
                  "uptime_seconds": int(time.time() - start_time),
                  "local_db_size_bytes": db_size,
                  "db_size_source": db_size_source,
                  "status": "shutting_down",
                  "session_token": os.environ.get("OGAS_SESSION_TOKEN", "")},
            token=token, method="PUT",
        )

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    tick = 0
    base_net = rng.randint(10_000_000, 20_000_000)

    while running:
        metrics_snapshot = _real_or_synthetic(rng, ws_type)
        uptime = int(time.time() - start_time)
        db_size, db_size_source = _local_db_size(ws_type, rng)

        # Network jitter — simulate varying traffic
        net_in = base_net + rng.randint(-2_000_000, 5_000_000)
        net_out = int(net_in * rng.uniform(0.5, 0.9))
        # Simulate some production output
        finished = rng.randint(0, 8)
        defect = 1 if finished and rng.random() < 0.06 else 0
        # Simulate latency
        db_lat = rng.randint(8, 60)
        api_lat = int(15 + metrics_snapshot["cpu"] * 0.4 + rng.randint(-5, 12))

        # ---- Heartbeat ----
        hb_resp = _api_request(
            f"{api_url}/nodes/{node_code}/heartbeat",
            data={
                "node_code": node_code,
                "agent_version": AGENT_VERSION,
                "uptime_seconds": uptime,
                "local_db_size_bytes": db_size,
                "db_size_source": db_size_source,
                "status": "online",
                "session_token": os.environ.get("OGAS_SESSION_TOKEN", ""),
            },
            token=token, method="PUT",
        )

        # ---- Metrics ----
        metric = {
            "node_code": node_code,
            "workshop_type": ws_type,
            "cpu_usage": metrics_snapshot["cpu"],
            "memory_usage": metrics_snapshot["mem"],
            "disk_usage": metrics_snapshot["disk"],
            "network_in": max(0, net_in),
            "network_out": max(0, net_out),
            "db_latency_ms": db_lat,
            "api_latency_ms": api_lat,
            "finished_quantity": finished,
            "defect_quantity": defect,
        }
        metric_resp = _api_request(f"{api_url}/metrics", data=metric, token=token, method="POST")

        tick += 1
        hb_ok = "error" not in hb_resp
        m_ok = "accepted" in metric_resp
        status_char = "OK" if (hb_ok and m_ok) else "ERR"
        if tick % 5 == 0 or not (hb_ok and m_ok):
            print(f"[agent:{node_code}] tick={tick} {status_char}  "
                  f"cpu={metrics_snapshot['cpu']:.1f}%  mem={metrics_snapshot['mem']:.1f}%  "
                  f"disk={metrics_snapshot['disk']:.1f}%  uptime={uptime}s  "
                  f"hb={'ok' if hb_ok else 'FAIL'}  metrics={'ok' if m_ok else 'FAIL'}")

        time.sleep(interval)


def _infer_workshop_type(node_code: str) -> str:
    for key in ("turning", "milling", "grinding"):
        if key in node_code:
            return key
    if "db" in node_code:
        return "database"
    if "cloud" in node_code:
        return "cloud"
    return "general"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Mini-OGAS Node Agent")
    parser.add_argument("--node-code", required=True,
                        help="Node code, e.g. turning-workshop-01")
    parser.add_argument("--api-url", default=DEFAULT_API_URL,
                        help=f"Central API base URL (default: {DEFAULT_API_URL})")
    parser.add_argument("--token", default=DEFAULT_TOKEN,
                        help="X-OGAS-Token for auth")
    parser.add_argument("--interval", type=float, default=3.0,
                        help="Seconds between heartbeat+metric pushes (default: 3)")
    parser.add_argument("--workshop-type",
                        help="Workshop type override (turning/milling/grinding/cloud/database)")
    args = parser.parse_args()

    run_agent(
        node_code=args.node_code,
        api_url=args.api_url.rstrip("/"),
        token=args.token,
        interval=args.interval,
        workshop_type=args.workshop_type,
    )


if __name__ == "__main__":
    main()
