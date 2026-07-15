import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

API_URL = os.environ.get("MINIOGAS_API_URL", "http://127.0.0.1:8080").rstrip("/")
AUTH_ENV_PATH = Path(os.environ.get("MINIOGAS_AUTH_ENV_PATH", r"D:\MiniOGAS-VMs\auth.env"))
NODE_CODE = os.environ.get("MINIOGAS_WORKFLOW_NODE", f"workflow-check-node-{int(time.time())}")
ISSUE_TYPE = "SPINDLE_TEMP_HIGH"
ISSUE_ID = f"{NODE_CODE}-{ISSUE_TYPE}"
REQUEST_TIMEOUT_SEC = int(os.environ.get("MINIOGAS_WORKFLOW_TIMEOUT_SEC", "45"))


ACCESS_TOKEN = ""
NODE_TOKEN = ""
NODE_CREDENTIAL_ISSUED = False


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


def provision_workflow_node_credential() -> None:
    global NODE_CREDENTIAL_ISSUED, NODE_TOKEN
    issued = request(
        "POST",
        f"/api/security/node-credentials/{urllib.parse.quote(NODE_CODE, safe='')}/rotate",
        {},
        auth="bearer",
    )
    node_token = str(issued.get("token") or "") if isinstance(issued, dict) else ""
    require(
        bool(node_token) and issued.get("node_code") == NODE_CODE,
        "temporary workflow Principal did not return a bound node credential",
        issued,
    )
    NODE_TOKEN = node_token
    NODE_CREDENTIAL_ISSUED = True


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
        if not NODE_TOKEN:
            raise RuntimeError("temporary node credential is not initialized")
        headers["X-OGAS-Token"] = NODE_TOKEN
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
    provision_workflow_node_credential()
    now = datetime.now(UTC).isoformat()
    snapshot = request("GET", "/api/dashboard/snapshot", params={"mode": "normal"})
    active_run = snapshot.get("run", {}) if isinstance(snapshot, dict) else {}
    snapshot_nodes = snapshot.get("nodes", []) if isinstance(snapshot, dict) else []
    runtime_template = next(
        (
            node.get("runtime", {})
            for node in snapshot_nodes
            if isinstance(node, dict) and isinstance(node.get("runtime"), dict)
        ),
        {},
    )
    workflow_run_id = str(active_run.get("run_id") or f"RUN-{NODE_CODE}")
    workflow_scenario_id = str(
        active_run.get("scenario_id") or runtime_template.get("scenario_id") or "SCN-RUNTIME-WORKFLOW"
    )
    simulation_engine = str(
        active_run.get("simulation_engine") or runtime_template.get("simulation_engine") or "simple"
    )
    random_seed = int(runtime_template.get("random_seed") or 3001)
    simulation_mode = str(runtime_template.get("simulation_mode") or "workflow-check")
    heartbeat = {
        "node_code": NODE_CODE,
        "timestamp": now,
        "status": "fault",
        "agent_version": "3.0.0-gate",
        "uptime_sec": 60,
        "metrics": {
            "cpu_usage": 81,
            "memory_usage": 52,
            "disk_usage": 37,
            "db_latency_ms": 18,
            "network_latency_ms": 42,
        },
        "production": {
            "active_order": "WO-RUNTIME-WORKFLOW",
            "machine_code": "QA-MILL",
            "workshop_type": "milling",
            "finished_quantity": 17,
            "defect_quantity": 1,
            "target_rate": 1.0,
            "actual_rate": 0.72,
            "rate_unit": "parts_per_minute",
            "utilization": 0.81,
            "defect_rate": 1 / 18,
            "wip_input": 4,
            "wip_output": 2,
            "tool_wear_level": 42,
            "spindle_temp": 93,
        },
        "alarms": [{"type": ISSUE_TYPE, "severity": "critical", "status": "open"}],
        "sync": {"last_sync_id": 1, "pending_records": 0},
        "runtime": {
            "run_id": workflow_run_id,
            "scenario_id": workflow_scenario_id,
            "simulation_engine": simulation_engine,
            "simulation_mode": simulation_mode,
            "part_flow_mode": "workflow-check",
            "random_seed": random_seed,
            "simulation_time": now,
            "wall_clock_time": now,
            "deployment_mode": "process",
            "runtime_source": "simulated",
        },
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
        "timestamp": datetime.now(UTC).isoformat(),
        "status": "running",
        "production": {
            **heartbeat["production"],
            "spindle_temp": 62,
            "finished_quantity": 23,
            "actual_rate": 0.96,
            "defect_rate": 1 / 24,
            "wip_output": 3,
        },
        "alarms": [],
        "sync": {"last_sync_id": 2, "pending_records": 1},
    }
    recovery_heartbeat["runtime"] = {
        **heartbeat["runtime"],
        "simulation_time": recovery_heartbeat["timestamp"],
        "wall_clock_time": recovery_heartbeat["timestamp"],
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
                    "created_at": heartbeat["timestamp"],
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


def revoke_workflow_node_credential() -> None:
    global NODE_CREDENTIAL_ISSUED, NODE_TOKEN
    if not NODE_CREDENTIAL_ISSUED or not ACCESS_TOKEN:
        return
    try:
        revoked = request(
            "POST",
            f"/api/security/node-credentials/{urllib.parse.quote(NODE_CODE, safe='')}/revoke",
            {},
            auth="bearer",
        )
        require(
            int(revoked.get("revoked_credentials") or 0) >= 1,
            "temporary workflow Principal credential was not revoked",
            revoked,
        )
    except Exception as exc:
        print(f"warning: workflow node credential cleanup failed: {exc}", file=sys.stderr)
    finally:
        NODE_TOKEN = ""
        NODE_CREDENTIAL_ISSUED = False


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"runtime workflow check failed: {exc}", file=sys.stderr)
        raise
    finally:
        retire_workflow_node()
        revoke_workflow_node_credential()
