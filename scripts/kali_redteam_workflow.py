from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_API_URL = "http://127.0.0.1:8080"
DEFAULT_OPERATOR = "\u8f66\u95f4\u4e3b\u7ba1"
REQUEST_TIMEOUT_SEC = 45
LOCAL_LAB_HOSTS = {"127.0.0.1", "localhost", "::1"}

SCENARIOS: dict[str, dict[str, Any]] = {
    "spindle_overheat": {
        "node_code": "milling-workshop-01",
        "machine_code": "MILL-02",
        "workshop_type": "milling",
        "status": "fault",
        "alarm_type": "SPINDLE_TEMP_HIGH",
        "severity": "critical",
        "production": {"spindle_temp": 93, "tool_wear_level": 44, "defect_quantity": 1},
    },
    "quality_drift": {
        "node_code": "turning-workshop-01",
        "machine_code": "LATHE-01",
        "workshop_type": "turning",
        "status": "warning",
        "alarm_type": "QUALITY_DRIFT",
        "severity": "warning",
        "production": {"spindle_temp": 66, "tool_wear_level": 48, "defect_quantity": 15},
    },
    "tool_wear": {
        "node_code": "grinding-workshop-01",
        "machine_code": "GRIND-01",
        "workshop_type": "grinding",
        "status": "warning",
        "alarm_type": "TOOL_WEAR_WARNING",
        "severity": "warning",
        "production": {"spindle_temp": 68, "tool_wear_level": 89, "defect_quantity": 2},
    },
    "vibration": {
        "node_code": "milling-workshop-01",
        "machine_code": "MILL-02",
        "workshop_type": "milling",
        "status": "fault",
        "alarm_type": "VIBRATION_HIGH",
        "severity": "critical",
        "production": {"spindle_temp": 79, "tool_wear_level": 54, "defect_quantity": 3},
    },
    "coolant_flow": {
        "node_code": "milling-workshop-01",
        "machine_code": "MILL-02",
        "workshop_type": "milling",
        "status": "warning",
        "alarm_type": "COOLANT_FLOW_LOW",
        "severity": "warning",
        "production": {"spindle_temp": 81, "tool_wear_level": 41, "defect_quantity": 1},
    },
}


def load_token(token: str = "", token_file: str = "") -> str:
    if token.strip():
        return token.strip()
    env_token = os.environ.get("OGAS_API_TOKEN", "").strip()
    if env_token:
        return env_token
    path_text = token_file.strip() or os.environ.get("MINIOGAS_TOKEN_PATH", "").strip()
    if path_text:
        path = Path(path_text)
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    raise RuntimeError("OGAS_API_TOKEN or --token-file is required")


def load_auth_env(path_text: str) -> dict[str, str]:
    if not path_text:
        return {}
    path = Path(path_text)
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def load_admin_password(args: argparse.Namespace) -> str:
    if args.admin_password:
        return args.admin_password
    if os.environ.get("MINIOGAS_ADMIN_PASSWORD"):
        return os.environ["MINIOGAS_ADMIN_PASSWORD"]
    env_values = load_auth_env(args.auth_env_file)
    return env_values.get("AUTH_BOOTSTRAP_PASSWORD", "")


def is_private_lab_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if hostname in LOCAL_LAB_HOSTS:
        return True
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return hostname.endswith(".local") or hostname.endswith(".lab")
    return address.is_private or address.is_loopback


def require_lab_boundary(args: argparse.Namespace) -> None:
    acknowledged = args.i_understand_this_is_a_lab or os.environ.get("MINIOGAS_LAB_ACK", "").upper() == "YES"
    if not acknowledged:
        raise RuntimeError(
            "Refusing to run red-team workflow without explicit lab acknowledgement. "
            "Pass --i-understand-this-is-a-lab or set MINIOGAS_LAB_ACK=YES."
        )
    if not args.allow_remote_lab and not is_private_lab_url(args.api_url):
        raise RuntimeError(
            f"Refusing to target non-private API URL {args.api_url!r}. "
            "Use a loopback/private lab address, or pass --allow-remote-lab only for an authorized isolated lab."
        )


def login_bearer(args: argparse.Namespace) -> str:
    if args.bearer_token:
        return args.bearer_token.strip()
    password = load_admin_password(args)
    if not password:
        raise RuntimeError(
            "Administrator password is required for protected workflow steps. "
            "Use --admin-password, MINIOGAS_ADMIN_PASSWORD, or --auth-env-file."
        )
    payload = request(
        "POST",
        "/api/auth/login",
        base_url=args.api_url,
        token="",
        bearer_token="",
        body={"operator": args.operator, "password": password},
        auth_mode="none",
    )
    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise RuntimeError("admin login did not return a bearer access token")
    return str(payload["access_token"])


def request(
    method: str,
    path: str,
    *,
    base_url: str,
    token: str,
    bearer_token: str = "",
    auth_mode: str = "node",
    body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {
        "Content-Type": "application/json",
        "X-Request-ID": f"kali-redteam-{int(time.time() * 1000)}",
    }
    if auth_mode == "node":
        headers["X-OGAS-Token"] = token
    elif auth_mode == "bearer":
        headers["Authorization"] = f"Bearer {bearer_token}"
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}{query}",
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


def scenario_config(name: str) -> dict[str, Any]:
    if name not in SCENARIOS:
        raise ValueError(f"unknown scenario: {name}")
    return dict(SCENARIOS[name])


def issue_id_for(node_code: str, alarm_type: str) -> str:
    return f"{node_code}-{alarm_type}"


def build_attack_heartbeat(
    *,
    scenario: str,
    node_code: str = "",
    machine_code: str = "",
    attack_id: str = "",
) -> dict[str, Any]:
    config = scenario_config(scenario)
    selected_node = node_code or str(config["node_code"])
    selected_machine = machine_code or str(config["machine_code"])
    selected_attack_id = attack_id or f"KALI-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    production = {
        "active_order": f"WO-KALI-{selected_attack_id[-6:]}",
        "machine_code": selected_machine,
        "workshop_type": config["workshop_type"],
        "finished_quantity": 84,
        **config["production"],
    }
    return {
        "node_code": selected_node,
        "status": config["status"],
        "metrics": {"cpu_usage": 72, "memory_usage": 58, "network_latency_ms": 115},
        "production": production,
        "alarms": [{"type": config["alarm_type"], "severity": config["severity"], "status": "open"}],
        "sync": {"pending_records": 0},
        "runtime": {
            "source": "kali-redteam",
            "deployment_mode": "kali-adversary-lab",
            "simulation_mode": "authorized-process-test",
            "attack_id": selected_attack_id,
            "scenario": scenario,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


def build_recovery_heartbeat(attack_heartbeat: dict[str, Any]) -> dict[str, Any]:
    production = dict(attack_heartbeat.get("production") or {})
    production.update({"spindle_temp": min(float(production.get("spindle_temp") or 68), 72.0), "defect_quantity": 0})
    if "tool_wear_level" in production:
        production["tool_wear_level"] = min(float(production["tool_wear_level"]), 58.0)
    runtime = dict(attack_heartbeat.get("runtime") or {})
    runtime["recovery"] = "script-restored-process-window"
    return {
        **attack_heartbeat,
        "status": "running",
        "production": production,
        "alarms": [],
        "sync": {"pending_records": 1},
        "runtime": runtime,
    }


def select_alert(alerts: list[dict[str, Any]], issue_id: str) -> dict[str, Any] | None:
    return next((item for item in alerts if item.get("issue_id") == issue_id or item.get("id") == issue_id), None)


def require_ok(payload: dict[str, Any] | list[dict[str, Any]], step: str) -> None:
    if isinstance(payload, dict) and payload.get("ok") is False:
        raise RuntimeError(f"{step} failed: {json.dumps(payload, ensure_ascii=False)}")


def extract_ai_runtime(payload: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    runtime = payload.get("runtime")
    return runtime if isinstance(runtime, dict) else {}


def extract_decision_source(payload: dict[str, Any] | list[dict[str, Any]]) -> str:
    if not isinstance(payload, dict):
        return ""
    decision = payload.get("decision")
    if isinstance(decision, dict) and decision.get("source"):
        return str(decision["source"])
    if payload.get("source"):
        return str(payload["source"])
    return ""


def build_lab_manifest(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "tool": "mini-ogas-kali-redteam-workflow",
        "lab_only": True,
        "api_url": args.api_url,
        "scenario": args.scenario,
        "mode": args.mode,
        "operator": args.operator,
        "acknowledged": bool(args.i_understand_this_is_a_lab or os.environ.get("MINIOGAS_LAB_ACK", "").upper() == "YES"),
        "allow_remote_lab": bool(args.allow_remote_lab),
        "boundaries": [
            "Uses authenticated Mini-OGAS lab APIs only.",
            "Does not exploit hosts, scan networks, brute force credentials, persist access, or evade detection.",
            "Injects bounded production telemetry abnormalities and verifies detect-repair audit flow.",
            "Kali/VirtualBox state must not be used as production-node availability proof.",
        ],
    }


def write_evidence(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    if not args.evidence_file:
        return
    path = Path(args.evidence_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def require_live_ai_runtime(args: argparse.Namespace, bearer_token: str) -> dict[str, Any]:
    status = request("GET", "/api/auth/status", base_url=args.api_url, token="", bearer_token=bearer_token, auth_mode="none")
    runtime = extract_ai_runtime(status)
    source = str(runtime.get("source") or "")
    if source != "api" and not args.allow_rule_fallback:
        state = str(runtime.get("status") or "unknown")
        provider = str(runtime.get("provider") or "unknown")
        model = str(runtime.get("model") or "unknown")
        raise RuntimeError(
            "AI runtime is not using a live API. "
            f"status={state}, source={source or 'unknown'}, provider={provider}, model={model}. "
            "Unlock the dashboard AI vault or configure DEEPSEEK_API_KEY before running the full red-team workflow; "
            "pass --allow-rule-fallback only when you intentionally want a non-AI dry run."
        )
    return runtime


def post_attack(args: argparse.Namespace, token: str) -> dict[str, Any]:
    heartbeat = build_attack_heartbeat(
        scenario=args.scenario,
        node_code=args.node_code,
        machine_code=args.machine_code,
        attack_id=args.attack_id,
    )
    result = request("POST", "/api/node-heartbeats", base_url=args.api_url, token=token, body=heartbeat)
    require_ok(result, "attack heartbeat")
    alarm_type = heartbeat["alarms"][0]["type"]
    issue_id = issue_id_for(heartbeat["node_code"], alarm_type)
    return {"heartbeat": heartbeat, "issue_id": issue_id, "result": result}


def repair_issue(args: argparse.Namespace, token: str, heartbeat: dict[str, Any] | None = None) -> dict[str, Any]:
    bearer_token = login_bearer(args)
    if heartbeat is None:
        heartbeat = build_attack_heartbeat(
            scenario=args.scenario,
            node_code=args.node_code,
            machine_code=args.machine_code,
            attack_id=args.attack_id,
        )
    issue_id = args.issue_id or issue_id_for(heartbeat["node_code"], heartbeat["alarms"][0]["type"])
    recovery = build_recovery_heartbeat(heartbeat)
    recovery_result = request("POST", "/api/node-heartbeats", base_url=args.api_url, token=token, body=recovery)
    close_result = request(
        "POST",
        f"/api/issues/{urllib.parse.quote(issue_id, safe='')}/actions",
        base_url=args.api_url,
        token=token,
        bearer_token=bearer_token,
        auth_mode="bearer",
        body={
            "operator": args.operator,
            "action": "Kali repair script restored node telemetry, removed injected alarm, and validated recovery heartbeat.",
        },
    )
    require_ok(close_result, "issue close")
    return {"issue_id": issue_id, "recovery_result": recovery_result, "close_result": close_result}


def full_workflow(args: argparse.Namespace, token: str) -> dict[str, Any]:
    bearer_token = login_bearer(args)
    ai_runtime = require_live_ai_runtime(args, bearer_token)
    attack = post_attack(args, token)
    issue_id = attack["issue_id"]
    alerts = request("GET", "/api/alerts", base_url=args.api_url, token=token, bearer_token=bearer_token, auth_mode="bearer")
    if not isinstance(alerts, list):
        raise RuntimeError("alerts endpoint did not return a list")
    if not select_alert(alerts, issue_id):
        dashboard = request("GET", "/api/dashboard-state", base_url=args.api_url, token=token, bearer_token=bearer_token, auth_mode="bearer", params={"mode": "normal"})
        notifications = dashboard.get("notifications", []) if isinstance(dashboard, dict) else []
        matching_notice = next((item for item in notifications if item.get("source_node") == attack["heartbeat"]["node_code"]), None)
        if not matching_notice:
            raise RuntimeError(f"alert not visible after attack heartbeat: {issue_id}")
        return {
            "ok": True,
            "scenario": args.scenario,
            "issue_id": issue_id,
            "attack_id": attack["heartbeat"]["runtime"]["attack_id"],
            "status": "auto_resolved",
            "ai_runtime": ai_runtime,
            "lab_manifest": build_lab_manifest(args),
            "steps": {"attack": attack["result"], "auto_resolution": matching_notice},
            "kali_log_sample": [
                item
                for item in (dashboard.get("log_events", []) if isinstance(dashboard, dict) else [])
                if item.get("source") == "kali-redteam"
            ][:5],
        }
    confirm = request(
        "POST",
        f"/api/alerts/{urllib.parse.quote(issue_id, safe='')}/confirm",
        base_url=args.api_url,
        token=token,
        bearer_token=bearer_token,
        auth_mode="bearer",
        body={"operator": args.operator, "action": "Authorized Kali red-team scenario confirmed."},
    )
    require_ok(confirm, "confirm alert")
    diagnosis = request("POST", f"/api/ai/diagnose/{urllib.parse.quote(issue_id, safe='')}", base_url=args.api_url, token=token, bearer_token=bearer_token, auth_mode="bearer")
    require_ok(diagnosis, "AI diagnosis")
    diagnosis_source = extract_decision_source(diagnosis)
    if diagnosis_source != "api" and not args.allow_rule_fallback:
        raise RuntimeError(
            "AI diagnosis did not come from a live API. "
            f"source={diagnosis_source or 'unknown'}. "
            "The attack was injected, but isolation/repair was stopped so the run cannot be mistaken for a real AI-assisted test."
        )
    severity = str(attack["heartbeat"]["alarms"][0].get("severity") or "").lower()
    needs_isolation = bool(
        diagnosis.get("need_isolation")
        or diagnosis.get("decision", {}).get("risk_level") == "high"
        or severity in {"critical", "high"}
    )
    isolate: dict[str, Any] = {
        "skipped": True,
        "reason": "AI diagnosis did not require isolation for this bounded scenario.",
    }
    if needs_isolation:
        if not args.auto_approve_high_risk:
            return {
                "ok": True,
                "scenario": args.scenario,
                "issue_id": issue_id,
                "attack_id": attack["heartbeat"]["runtime"]["attack_id"],
                "status": "waiting_human_approval",
                "ai_runtime": ai_runtime,
                "lab_manifest": build_lab_manifest(args),
                "steps": {
                    "attack": attack["result"],
                    "confirm": confirm,
                    "diagnosis": diagnosis,
                    "isolate": {
                        "skipped": True,
                        "reason": "High-risk isolation requires explicit --auto-approve-high-risk in this lab workflow.",
                    },
                    "repair": {
                        "skipped": True,
                        "reason": "Repair is held until a human approves the high-risk isolation/recovery path.",
                    },
                },
            }
        isolate = request(
            "POST",
            f"/api/nodes/{urllib.parse.quote(attack['heartbeat']['node_code'], safe='')}/isolate",
            base_url=args.api_url,
            token=token,
            bearer_token=bearer_token,
            auth_mode="bearer",
            body={"actor": args.operator, "decision": "approve", "confirmation_code": "CONFIRM"},
        )
        require_ok(isolate, "node isolation")
    repair = repair_issue(args, token, attack["heartbeat"])
    audit = request("GET", "/api/audit/events", base_url=args.api_url, token=token, bearer_token=bearer_token, auth_mode="bearer")
    logs = request("GET", "/api/dashboard-state", base_url=args.api_url, token=token, bearer_token=bearer_token, auth_mode="bearer", params={"mode": "normal"})
    return {
        "ok": True,
        "scenario": args.scenario,
        "issue_id": issue_id,
        "attack_id": attack["heartbeat"]["runtime"]["attack_id"],
        "ai_runtime": ai_runtime,
        "lab_manifest": build_lab_manifest(args),
        "steps": {
            "attack": attack["result"],
            "confirm": confirm,
            "diagnosis": diagnosis,
            "isolate": isolate,
            "repair": repair,
        },
        "audit_sample": [item for item in audit if item.get("issue_id") == issue_id][:5] if isinstance(audit, list) else [],
        "kali_log_sample": [
            item for item in (logs.get("log_events", []) if isinstance(logs, dict) else []) if item.get("source") == "kali-redteam"
        ][:5],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Authorized Kali red-team workflow for Mini-OGAS lab nodes.")
    parser.add_argument("--api-url", default=os.environ.get("MINIOGAS_API_URL", DEFAULT_API_URL).rstrip("/"))
    parser.add_argument("--token", default="")
    parser.add_argument("--token-file", default="")
    parser.add_argument("--bearer-token", default=os.environ.get("MINIOGAS_BEARER_TOKEN", ""))
    parser.add_argument("--admin-password", default="")
    parser.add_argument("--auth-env-file", default=os.environ.get("MINIOGAS_AUTH_ENV", r"D:\MiniOGAS-VMs\auth.env"))
    parser.add_argument("--operator", default=os.environ.get("MINIOGAS_OPERATOR", DEFAULT_OPERATOR))
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="spindle_overheat")
    parser.add_argument("--node-code", default="")
    parser.add_argument("--machine-code", default="")
    parser.add_argument("--attack-id", default="")
    parser.add_argument("--issue-id", default="")
    parser.add_argument(
        "--allow-rule-fallback",
        action="store_true",
        help="Allow full workflow to continue when central-api reports rule_fallback instead of a live AI API.",
    )
    parser.add_argument(
        "--allow-remote-lab",
        action="store_true",
        help="Allow targeting a non-private URL. Use only for an isolated authorized Mini-OGAS lab.",
    )
    parser.add_argument(
        "--i-understand-this-is-a-lab",
        action="store_true",
        help="Required acknowledgement that this workflow is only for an authorized Mini-OGAS lab.",
    )
    parser.add_argument(
        "--evidence-file",
        default=os.environ.get("MINIOGAS_REDTEAM_EVIDENCE", ".runtime/logs/kali-redteam-last.json"),
        help="Write the structured workflow result to this JSON file.",
    )
    parser.add_argument(
        "--auto-approve-high-risk",
        action="store_true",
        help="Allow the lab workflow to isolate and repair when AI marks the scenario high risk.",
    )
    parser.add_argument("mode", choices=["attack", "repair", "full"], nargs="?", default="full")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    require_lab_boundary(args)
    token = load_token(args.token, args.token_file)
    if args.mode == "attack":
        output = post_attack(args, token)
        output["lab_manifest"] = build_lab_manifest(args)
    elif args.mode == "repair":
        output = repair_issue(args, token)
        output["lab_manifest"] = build_lab_manifest(args)
    else:
        output = full_workflow(args, token)
    write_evidence(args, output)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"kali red-team workflow failed: {exc}", file=sys.stderr)
        raise
