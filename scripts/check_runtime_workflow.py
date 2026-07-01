import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


API_URL = os.environ.get("MINIOGAS_API_URL", "http://127.0.0.1:8080").rstrip("/")
TOKEN_PATH = Path(os.environ.get("MINIOGAS_TOKEN_PATH", r"D:\MiniOGAS-VMs\miniogas-token.txt"))
AUTH_ENV_PATH = Path(os.environ.get("MINIOGAS_AUTH_ENV_PATH", r"D:\MiniOGAS-VMs\auth.env"))
NODE_CODE = os.environ.get("MINIOGAS_WORKFLOW_NODE", f"workflow-check-node-{int(time.time())}")
ISSUE_TYPE = "SPINDLE_TEMP_HIGH"
ISSUE_ID = f"{NODE_CODE}-{ISSUE_TYPE}"
REQUEST_TIMEOUT_SEC = int(os.environ.get("MINIOGAS_WORKFLOW_TIMEOUT_SEC", "45"))


def load_token() -> str:
    if "OGAS_API_TOKEN" in os.environ and os.environ["OGAS_API_TOKEN"].strip():
        return os.environ["OGAS_API_TOKEN"].strip()
    if not TOKEN_PATH.exists():
        raise RuntimeError(f"token file not found: {TOKEN_PATH}")
    return TOKEN_PATH.read_text(encoding="utf-8").strip()


TOKEN = load_token()
ACCESS_TOKEN = ""


def load_auth_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if not AUTH_ENV_PATH.exists():
        return values
    for raw in AUTH_ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_admin_credentials() -> tuple[str, str]:
    auth_env = load_auth_env()
    username = (
        os.environ.get("MINIOGAS_ADMIN_USERNAME")
        or auth_env.get("AUTH_BOOTSTRAP_USERNAME")
        or "admin"
    ).strip()
    password = (
        os.environ.get("MINIOGAS_ADMIN_PASSWORD")
        or auth_env.get("AUTH_BOOTSTRAP_PASSWORD")
        or ""
    ).strip()
    if not password:
        raise RuntimeError(
            "admin password not configured; set MINIOGAS_ADMIN_PASSWORD or D:\\MiniOGAS-VMs\\auth.env"
        )
    return username, password


def login() -> None:
    global ACCESS_TOKEN
    username, password = load_admin_credentials()
    response = request(
        "POST",
        "/api/auth/login",
        {"operator": username, "password": password},
        auth="public",
    )
    token = response.get("access_token") if isinstance(response, dict) else ""
    if not token:
        raise RuntimeError("admin login did not return a bearer access token")
    ACCESS_TOKEN = str(token)


def request(
    method: str,
    path: str,
    body: dict | None = None,
    params: dict | None = None,
    auth: str = "bearer",
) -> dict | list:
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {
        "Content-Type": "application/json",
        "X-Request-ID": f"runtime-workflow-{int(time.time() * 1000)}",
    }
    if auth == "node":
        headers["X-OGAS-Token"] = TOKEN
    elif auth == "bearer":
        if not ACCESS_TOKEN:
            raise RuntimeError("bearer access token is not initialized")
        headers["Authorization"] = f"Bearer {ACCESS_TOKEN}"
    req = urllib.request.Request(
        f"{API_URL}{path}{query}",
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed with {exc.code}: {raw}") from exc


def require(condition: bool, message: str, payload=None) -> None:
    if condition:
        return
    detail = f"\n{json.dumps(payload, ensure_ascii=False, indent=2)}" if payload is not None else ""
    raise AssertionError(f"{message}{detail}")


def find_alert(issue_id: str) -> dict | None:
    alerts = request("GET", "/api/alerts")
    require(isinstance(alerts, list), "alerts endpoint did not return a list", alerts)
    return next((item for item in alerts if item.get("issue_id") == issue_id), None)


def main() -> None:
    login()
    heartbeat = {
        "node_code": NODE_CODE,
        "status": "fault",
        "metrics": {"cpu_usage": 81, "memory_usage": 52, "network_latency_ms": 42},
        "production": {
            "active_order": "WO-RUNTIME-WORKFLOW",
            "machine_code": "QA-MILL",
            "workshop_type": "milling",
            "finished_quantity": 17,
            "defect_quantity": 1,
            "tool_wear_level": 42,
            "spindle_temp": 93,
        },
        "alarms": [{"type": ISSUE_TYPE, "severity": "critical", "status": "open"}],
        "sync": {"pending_records": 0},
        "runtime": {"deployment_mode": "runtime-workflow", "simulation_mode": "workflow-check"},
    }
    hb = request("POST", "/api/node-heartbeats", heartbeat, auth="node")
    require(bool(hb.get("ok")), "fault heartbeat was not accepted", hb)

    alert = find_alert(ISSUE_ID)
    require(alert is not None, "fault heartbeat did not create a visible alert", {"issue_id": ISSUE_ID})
    require(alert["status"] == "open", "new alert should start open", alert)

    confirmed = request(
        "POST",
        f"/api/alerts/{urllib.parse.quote(ISSUE_ID, safe='')}/confirm",
        {"action": "确认真实报警", "operator": "车间主管"},
    )
    require(bool(confirmed.get("ok")), "alert confirmation failed", confirmed)
    require(confirmed["lifecycle"]["status"] == "confirmed", "alert did not move to confirmed", confirmed)

    diagnosed = request("POST", f"/api/ai/diagnose/{urllib.parse.quote(ISSUE_ID, safe='')}")
    require(bool(diagnosed.get("ok")), "AI diagnosis endpoint failed", diagnosed)
    require(diagnosed["decision"]["requires_human"], "high-risk diagnosis did not require human approval", diagnosed)
    escalation = diagnosed.get("escalation")
    require(escalation and escalation.get("issue_id") == ISSUE_ID, "diagnosis did not create approval item", diagnosed)

    diagnosed_alert = find_alert(ISSUE_ID)
    require(diagnosed_alert and diagnosed_alert["status"] == "diagnosed", "alert did not move to diagnosed", diagnosed_alert)

    queue = request("GET", "/api/ops/escalations")
    queue_item = next((item for item in queue if item.get("issue_id") == ISSUE_ID), None)
    require(queue_item is not None, "approval item not visible in escalation queue", queue)

    denied = request(
        "POST",
        f"/api/ops/escalations/{queue_item['id']}/decision",
        {"actor": "车间主管", "decision": "approve", "confirmation_code": ""},
    )
    require(not denied.get("ok") and denied.get("error") == "confirmation_code_required", "high-risk approval did not require CONFIRM", denied)

    notices_before_approval = request("GET", "/api/dashboard-state", params={"mode": "normal"}).get("notifications", [])
    notice_ids_before_approval = {item.get("id") for item in notices_before_approval}
    approved = request(
        "POST",
        f"/api/ops/escalations/{queue_item['id']}/decision",
        {"actor": "车间主管", "decision": "approve", "confirmation_code": "CONFIRM"},
    )
    require(bool(approved.get("ok")), "human approval failed", approved)
    verification = approved.get("effect", {}).get("verification", {})
    require(verification.get("issue_closed"), "approved issue was not marked closed", approved)
    require(verification.get("alarm_removed"), "approved issue alarm was not removed", approved)

    remaining_alert = find_alert(ISSUE_ID)
    require(remaining_alert is None, "closed issue is still visible in alerts", remaining_alert)
    remaining_queue = request("GET", "/api/ops/escalations")
    require(
        not any(item.get("issue_id") == ISSUE_ID for item in remaining_queue),
        "closed issue is still visible in escalation queue",
        remaining_queue,
    )

    audit = request("GET", "/api/audit/events")
    audit_events = audit.get("events", []) if isinstance(audit, dict) else audit
    matching_audit = [
        event for event in audit_events
        if event.get("node_code") == NODE_CODE
        and (
            event.get("issue_id") == ISSUE_ID
            or event.get("detail", {}).get("stage") == "human-escalation"
            or ISSUE_ID in str(event.get("message", ""))
        )
    ]
    require(matching_audit, "closed issue was not archived to audit events", audit_events[:5])
    require(
        any(event.get("detail", {}).get("stage") == "human-escalation" for event in matching_audit),
        "human approval audit event missing",
        matching_audit,
    )

    dashboard = request("GET", "/api/dashboard-state", params={"mode": "normal"})
    notices = dashboard.get("notifications", [])
    notice = next(
        (
            item
            for item in notices
            if str(item.get("id", "")).startswith("HUMAN-")
            and item.get("source_node") == NODE_CODE
            and item.get("id") not in notice_ids_before_approval
        ),
        None,
    )
    require(notice is not None, "result notification was not created for operator awareness", notices)

    acknowledged = request(
        "POST",
        f"/api/issues/{urllib.parse.quote(str(notice['id']), safe='')}/actions",
        {"action": "关闭人工处置结果通知", "operator": "车间主管"},
    )
    require(bool(acknowledged.get("ok")), "result notification acknowledgement failed", acknowledged)
    dashboard_after_ack = request("GET", "/api/dashboard-state", params={"mode": "normal"})
    require(
        not any(item.get("id") == notice["id"] for item in dashboard_after_ack.get("notifications", [])),
        "acknowledged result notification is still visible",
        dashboard_after_ack.get("notifications", []),
    )

    recovery_heartbeat = {
        **heartbeat,
        "status": "running",
        "production": {**heartbeat["production"], "spindle_temp": 62, "finished_quantity": 23},
        "alarms": [],
        "sync": {"pending_records": 1},
    }
    recovered = request("POST", "/api/node-heartbeats", recovery_heartbeat, auth="node")
    require(bool(recovered.get("ok")), "recovery heartbeat was not accepted", recovered)

    archived = request(
        "POST",
        "/api/node-records/sync",
        {
            "node_code": NODE_CODE,
            "records": [
                {
                    "local_id": 1,
                    "payload": heartbeat,
                    "created_at": heartbeat["timestamp"] if "timestamp" in heartbeat else "runtime-workflow",
                    "original_request_id": "offline-heartbeat",
                    "original_http_status": 0,
                    "original_error": "central-api unavailable during offline window",
                }
            ],
        },
        auth="node",
    )
    accepted_count = archived.get("accepted", archived.get("records_accepted"))
    require(bool(archived.get("ok", archived.get("accepted"))) and accepted_count == 1, "offline record sync was not accepted", archived)
    dashboard_after_sync = request("GET", "/api/dashboard-state", params={"mode": "normal"})
    workflow_node = next((node for node in dashboard_after_sync.get("nodes", []) if node.get("node_code") == NODE_CODE), None)
    if workflow_node is not None:
        require(workflow_node.get("status") in {"running", "online"}, "offline record sync polluted live node status", workflow_node)
        require(
            workflow_node.get("production", {}).get("spindle_temp") == 62,
            "offline record sync replaced current production telemetry",
            workflow_node,
        )
    else:
        snapshot = dashboard_after_sync.get("snapshot", {})
        system = snapshot.get("system", {}) if isinstance(snapshot, dict) else {}
        nodes = dashboard_after_sync.get("nodes", [])
        expected = int(system.get("nodes_expected") or 0)
        require(
            NODE_CODE.startswith("workflow-check-node-"),
            "non-temporary workflow node missing after recovery heartbeat",
            nodes,
        )
        require(
            len(nodes) == expected and expected >= 3,
            "production snapshot node count changed after offline record sync",
            {"expected": expected, "nodes": nodes},
        )
        require(
            all(node.get("status") in {"running", "online"} for node in nodes),
            "offline record sync polluted production node status",
            nodes,
        )

    print(
        json.dumps(
            {
                "ok": True,
                "api_url": API_URL,
                "node_code": NODE_CODE,
                "issue_id": ISSUE_ID,
                "workflow": [
                    "heartbeat_fault",
                    "alert_open",
                    "confirmed",
                    "diagnosed",
                    "approval_required",
                    "human_approved",
                    "closed",
                    "audit_archived",
                    "notification_acknowledged",
                    "offline_records_archived",
                    "live_state_preserved",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def retire_workflow_node() -> None:
    if not NODE_CODE.startswith("workflow-check-node-"):
        return
    try:
        request(
            "POST",
            f"/api/nodes/{urllib.parse.quote(NODE_CODE, safe='')}/retire",
            {"actor": "车间主管", "decision": "approve", "confirmation_code": "CONFIRM"},
            auth="bearer",
        )
    except Exception as exc:
        print(f"warning: workflow node cleanup failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"runtime workflow check failed: {exc}", file=sys.stderr)
        raise
    finally:
        retire_workflow_node()
