"""``mogas ai`` — AI backend connectivity tester."""

from __future__ import annotations

from ..core.health import check, api_request


def run() -> None:
    print()
    if not check(8080, timeout=3):
        print("  ERROR: central-api offline.  Run 'mogas up' first.")
        print()
        return

    status = api_request("/ai/status")
    if not status:
        print("  ERROR: /ai/status endpoint unavailable.")
        print()
        return

    print(f"  Enabled       : {status.get('enabled')}")
    print(f"  Configured    : {status.get('configured')}")
    print(f"  Active        : {status.get('active_provider', 'none')}")
    print(f"  Mode          : {status.get('mode', 'unknown')}")
    print()
    print("  Providers:")
    for p in status.get("providers", []):
        name = p.get("name", "?")
        avail = p.get("available", False)
        fallback = p.get("fallback", False)

        if fallback:
            label = "FALLBACK"
        elif avail:
            label = "ONLINE"
        else:
            label = "OFFLINE"
        print(f"    {name:18s} {label}")

    tip = status.get("tip", "")
    if tip:
        print(f"\n  Tip: {tip}")
    print()
