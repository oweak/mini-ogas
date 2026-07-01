import json

from fastapi.testclient import TestClient

from app.main import app
from app.rule_explanation import explain_rule_conclusions


AUTH_HEADERS = {"X-OGAS-Token": "mini-ogas-dev-token"}


def _snapshot(rule_conclusions: list[dict]) -> dict:
    return {
        "schema_version": "2.2",
        "generated_at": "2026-06-14T09:00:00+08:00",
        "data_source": "live",
        "run": {
            "run_id": "RUN-RULE-AI-TEST",
            "scenario_id": "SCN-MILLING-BOTTLENECK",
            "simulation_engine": "simpy",
        },
        "system": {"nodes_connected": 3, "nodes_expected": 3},
        "rule_conclusions": rule_conclusions,
    }


def test_rule_explanation_steady_state_does_not_call_live_ai() -> None:
    called = False

    def chat_fn(messages):
        nonlocal called
        called = True
        return "{}"

    explanation = explain_rule_conclusions(
        _snapshot([]),
        use_live_ai=True,
        chat_fn=chat_fn,
        provider="deepseek",
        model="deepseek-chat",
    )

    assert called is False
    assert explanation["status"] == "steady"
    assert explanation["used_live_ai"] is False
    assert explanation["rule_count"] == 0
    assert "未发现瓶颈" in explanation["summary"]


def test_rule_explanation_uses_live_ai_for_rule_conclusions() -> None:
    captured = {}
    conclusion = {
        "conclusion_id": "CONC-UNIT",
        "rule_id": "RULE-BOTTLENECK-LOW-OUTPUT",
        "type": "bottleneck_alert",
        "node_code": "milling-workshop-01",
        "machine_code": "MILL-02",
        "risk_level": "high",
        "severity": "high",
        "summary": "WIP accumulation with low output.",
        "evidence": [
            {
                "field": "production.wip_input - production.wip_output",
                "operator": ">=",
                "value": 14,
                "threshold": 12,
                "detail": "Input WIP is accumulating.",
            }
        ],
        "recommended_actions": ["Throttle upstream release.", "Check coolant flow."],
    }

    def chat_fn(messages):
        captured["messages"] = messages
        return json.dumps({
            "summary": "AI 已确认 MILL-02 存在流程瓶颈。",
            "reasoning": ["WIP 积压超过阈值。"],
            "recommended_actions": ["先限制上游放料，再复核冷却。"],
            "evidence": ["backlog=14 threshold=12"],
        }, ensure_ascii=False)

    explanation = explain_rule_conclusions(
        _snapshot([conclusion]),
        use_live_ai=True,
        chat_fn=chat_fn,
        provider="deepseek",
        model="deepseek-chat",
    )

    assert captured["messages"][0]["role"] == "system"
    assert "RULE-BOTTLENECK-LOW-OUTPUT" in captured["messages"][1]["content"]
    assert explanation["status"] == "explained"
    assert explanation["source"] == "api"
    assert explanation["used_live_ai"] is True
    assert explanation["provider"] == "deepseek"
    assert explanation["conclusion_ids"] == ["CONC-UNIT"]
    assert explanation["recommended_actions"] == ["先限制上游放料，再复核冷却。"]


def test_rule_explanation_endpoint_returns_contract() -> None:
    with TestClient(app) as client:
        response = client.get("/api/ai/rule-explanation?use_live=false", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "2.2"
    assert payload["status"] in {"steady", "fallback"}
    assert "summary" in payload
    assert "recommended_actions" in payload
