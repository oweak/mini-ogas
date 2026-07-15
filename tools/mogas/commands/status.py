"""``mogas status`` — show live system state."""

from __future__ import annotations

from ..core.health import check, api_request


def run() -> None:
    print()
    _print_api_status()
    print()


def _print_api_status() -> None:
    if check(8080, timeout=2):
        _show_nodes()
        _show_integrations()
    else:
        print("  central-api  : OFFLINE")

    worker = "ONLINE" if check(8084, timeout=1) else "OFFLINE"
    print(f"  worker       : {worker}")
    dash = "ONLINE" if check(5173, timeout=1) else "OFFLINE"
    print(f"  dashboard    : {dash}")


def _show_nodes() -> None:
    nodes = api_request("/nodes")
    if not isinstance(nodes, list):
        return
    online = sum(1 for n in nodes if n.get("status") == "online")
    print(f"  Nodes        : {online}/{len(nodes)} online")
    for n in nodes:
        status = str(n.get("status", "?"))
        code = str(n.get("node_code", "?"))
        print(f"    {code:30s} {status}")


def _show_integrations() -> None:
    snap = api_request("/management/snapshot")
    if not isinstance(snap, dict):
        return
    for item in snap.get("integrations", []):
        svc = item.get("service", "?")
        st = item.get("status", "?")
        print(f"  {str(svc):25s} {st}")
