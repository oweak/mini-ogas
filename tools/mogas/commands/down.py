"""``mogas down`` — stop all services."""

from __future__ import annotations

from ..core.health import check


def run() -> None:
    """Gracefully stop the running system."""
    ended = 0

    # Use REST to shut down agents cleanly
    from ..core.health import api_request

    if check(8080, timeout=2):
        # Notify agents to shut down
        nodes = api_request("/nodes")
        if isinstance(nodes, list):
            for node in nodes:
                code = node.get("node_code", "")
                if isinstance(code, str):
                    try:
                        from ..core.health import api_request as ar
                        ar(
                            f"/nodes/{code}/heartbeat",
                            method="PUT",
                            body={
                                "node_code": code,
                                "agent_version": "0.1.0",
                                "uptime_seconds": 0,
                                "local_db_size_bytes": 0,
                                "status": "shutting_down",
                            },
                            timeout=2,
                        )
                        ended += 1
                    except Exception:
                        pass

    # Force-kill ports
    from ..core.process import kill_port
    ports = [8080, 8081, 8082, 8083, 5173]
    for p in ports:
        kill_port(p)

    print(f"\n  Stopped.  ({ended} agent(s) notified)")
