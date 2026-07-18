import os

from fastapi.testclient import TestClient

os.environ["API_ACCESS_TOKEN"] = "planner-test-token"

from app.main import app


AUTH_HEADERS = {"X-OGAS-Token": "planner-test-token"}


def _healthy_nodes() -> list[dict[str, object]]:
    return [
        {
            "node_code": f"{workshop}-workshop-01",
            "workshop_type": workshop,
            "status": "online",
            "load_score": 45,
        }
        for workshop in ("turning", "milling", "grinding")
    ]


def test_accepted_order_sets_quantity_priority_and_causal_reason() -> None:
    payload = {
        "market_signals": [
            {"product_code": "P3", "demand_index": 30, "inventory_pressure": 30}
        ],
        "node_health": _healthy_nodes(),
        "allocation_orders": [
            {
                "order_id": "AO-STAGE-H",
                "product_code": "P3",
                "required_quantity": 72,
                "priority": 1,
                "deadline_hours": 2,
                "status": "received",
            }
        ],
    }

    with TestClient(app) as client:
        response = client.post("/plan", headers=AUTH_HEADERS, json=payload)

    assert response.status_code == 200
    plan = response.json()[0]
    assert plan["product_code"] == "P3"
    assert plan["target_quantity"] == 72
    assert plan["priority"] == 1
    assert "AO-STAGE-H" in plan["reason"]
    assert "committed_quantity=72" in plan["reason"]


def test_order_without_market_signal_is_still_planned() -> None:
    payload = {
        "market_signals": [],
        "node_health": _healthy_nodes(),
        "allocation_orders": [
            {
                "order_id": "AO-ORDER-ONLY",
                "product_code": "P2",
                "required_quantity": 40,
                "priority": 2,
                "deadline_hours": 4,
                "status": "received",
            }
        ],
    }

    with TestClient(app) as client:
        response = client.post("/plan", headers=AUTH_HEADERS, json=payload)

    assert response.status_code == 200
    assert response.json() == [
        {
            "product_code": "P2",
            "target_quantity": 40,
            "priority": 2,
            "route": ["turning", "milling"],
            "reason": (
                "Market demand and route capacity support the production plan; "
                "accepted_orders=AO-ORDER-ONLY; committed_quantity=40"
            ),
        }
    ]
