"""``mogas demo`` — trigger demo scenarios via API."""

from __future__ import annotations

import json

from ..core.health import check, api_request


SCENARIOS = {
    "normal":         "Reset to normal state",
    "common_fault":   "Inject disk pressure → local script repair",
    "complex_fault":  "Inject CPU/latency spike → AI diagnosis + approval",
    "market_shift":   "Sudden demand surge → re-plan + re-dispatch",
    "hostile_attack": "Abnormal inbound traffic → auto-isolate node",
}


def run(scenario: str = "normal") -> None:
    if scenario not in SCENARIOS:
        print(f"\n  Invalid scenario: {scenario}")
        print("  Available: " + " | ".join(SCENARIOS))
        print()
        return

    if not check(8080, timeout=3):
        print("\n  ERROR: central-api offline.")
        print()
        return

    print(f"\n  Scenario: {scenario}  —  {SCENARIOS[scenario]}\n")

    result = api_request(
        "/demo/scenario",
        method="POST",
        body={"scenario": scenario},
        timeout=10,
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\n  Dashboard: http://127.0.0.1:5173")
    print()
