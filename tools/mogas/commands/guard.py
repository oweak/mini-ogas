"""``mogas guard`` — process guardian with health monitoring."""

from __future__ import annotations

import signal
import time

from ..core.health import check, api_request


def run() -> None:
    print()
    print("  Guardian running.  Ctrl+C to stop.")
    print()

    def _handle(sig: int, frame: object) -> None:
        print("\n  Guardian stopped.")
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _handle)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _handle)

    while True:
        if not check(8080, timeout=3):
            print(f"  {_ts()} WARN  central-api OFFLINE")
            time.sleep(5)
            continue

        nodes = api_request("/nodes")
        if not isinstance(nodes, list):
            time.sleep(5)
            continue

        for node in nodes:
            status = str(node.get("status", "?"))
            if status != "online":
                name = node.get("node_code", "?")
                print(f"  {_ts()} WARN  {name} = {status}")

        time.sleep(5)


def _ts() -> str:
    return time.strftime("%H:%M:%S")
