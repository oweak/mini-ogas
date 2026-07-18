from __future__ import annotations

import argparse
import base64
import json
import math
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4


class GateFailure(RuntimeError):
    pass


def require(condition: bool, message: str, evidence: object | None = None) -> None:
    if condition:
        return
    detail = ""
    if evidence is not None:
        detail = f": {json.dumps(evidence, ensure_ascii=False, default=str)}"
    raise GateFailure(message + detail)


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        raise GateFailure(f"runtime configuration is missing: {path}")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = ""

    def call(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        params: dict[str, Any] | None = None,
        expected: tuple[int, ...] = (200, 201),
        authenticated: bool = True,
    ) -> dict[str, Any] | list[Any]:
        query = f"?{urlencode(params)}" if params else ""
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-Request-ID": f"stage-h-{uuid4()}",
        }
        if authenticated and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(
            f"{self.base_url}{path}{query}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                result = json.loads(raw) if raw else {}
                if response.status not in expected:
                    raise GateFailure(
                        f"{method} {path} returned {response.status}, expected {expected}"
                    )
                return result
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                result = {"body": raw}
            if exc.code in expected:
                return result
            raise GateFailure(f"{method} {path} returned {exc.code}: {result}") from exc
        except URLError as exc:
            raise GateFailure(f"{method} {path} could not reach {self.base_url}: {exc.reason}") from exc

    def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        return self.call("GET", path, params=params, expected=(200,))

    def post(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        params: dict[str, Any] | None = None,
        expected: tuple[int, ...] = (200, 201),
        authenticated: bool = True,
    ) -> dict[str, Any] | list[Any]:
        return self.call(
            "POST",
            path,
            payload or {},
            params=params,
            expected=expected,
            authenticated=authenticated,
        )


def jwt_permissions(token: str) -> set[str]:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except (IndexError, ValueError, json.JSONDecodeError) as exc:
        raise GateFailure("administrator access token is not a readable JWT") from exc
    return {str(item) for item in claims.get("permissions", [])}


def production_node(snapshot: dict[str, Any], node_code: str) -> dict[str, Any]:
    node = next(
        (
            item
            for item in snapshot.get("nodes", [])
            if isinstance(item, dict) and item.get("node_code") == node_code
        ),
        None,
    )
    require(node is not None, f"dashboard snapshot is missing {node_code}", snapshot.get("nodes"))
    return node


def heartbeat_age_seconds(
    node: dict[str, Any],
    *,
    now: datetime | None = None,
) -> float:
    raw_timestamp = node.get("received_at") or node.get("last_heartbeat")
    require(bool(raw_timestamp), "node snapshot is missing a heartbeat timestamp", node)
    try:
        timestamp = datetime.fromisoformat(str(raw_timestamp).replace("Z", "+00:00"))
    except ValueError as exc:
        raise GateFailure(f"node heartbeat timestamp is invalid: {raw_timestamp}") from exc
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return max(0.0, (current.astimezone(UTC) - timestamp.astimezone(UTC)).total_seconds())


def command_by_id(client: ApiClient, command_id: int) -> dict[str, Any]:
    commands = client.get("/api/commands")
    require(isinstance(commands, list), "commands endpoint did not return a list", commands)
    command = next(
        (item for item in commands if isinstance(item, dict) and int(item.get("id") or 0) == command_id),
        None,
    )
    require(command is not None, f"command {command_id} is missing from the command projection")
    return command


def changed_physical_metrics(
    baseline: dict[str, Any],
    current: dict[str, Any],
) -> list[str]:
    fields = ("finished_quantity", "wip_input", "wip_output", "defect_quantity")
    return [field for field in fields if current.get(field) != baseline.get(field)]


def event_mentions_command(event_type: str, payload: dict[str, Any], command_id: int) -> bool:
    required_types = {
        "command-created",
        "command-approved",
        "command-claimed",
        "command-result",
        "command-verification-effective",
    }
    if event_type not in required_types:
        return False
    message = str(payload.get("message") or "")
    return re.search(rf"(?<!\d){command_id}(?!\d)", message) is not None


def derive_observable_target(
    *,
    baseline_target: float,
    physical_rate: float,
    horizon_minutes: int,
) -> tuple[int, float, str]:
    preferred_rate = physical_rate * 0.7
    alternate_rate = physical_rate * 0.55
    desired_rate = (
        preferred_rate
        if abs(baseline_target - preferred_rate) >= 0.05
        else alternate_rate
    )
    quantity = max(1, math.floor(desired_rate * horizon_minutes))
    expected_rate = round(quantity / horizon_minutes, 3)
    direction = "increase" if expected_rate > baseline_target else "decrease"
    require(
        expected_rate <= physical_rate
        and abs(expected_rate - baseline_target) >= 0.05,
        "could not derive a safe, observable target-rate change",
        {
            "baseline_target": baseline_target,
            "physical_rate": physical_rate,
            "expected_rate": expected_rate,
        },
    )
    return quantity, expected_rate, direction


def wait_for_effect(
    client: ApiClient,
    *,
    command_id: int,
    node_code: str,
    expected_rate: float,
    baseline_production: dict[str, Any],
    timeout_seconds: int,
) -> tuple[dict[str, Any], dict[str, Any], list[str], list[str]]:
    deadline = time.monotonic() + timeout_seconds
    observed_statuses: list[str] = []
    latest_command: dict[str, Any] = {}
    latest_snapshot: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest_command = command_by_id(client, command_id)
        status = str(latest_command.get("status") or "")
        marker = f"{status}/{latest_command.get('verification_status', '')}"
        if not observed_statuses or observed_statuses[-1] != marker:
            observed_statuses.append(marker)
        latest_snapshot = client.get("/api/dashboard/snapshot", params={"mode": "normal"})
        require(isinstance(latest_snapshot, dict), "dashboard snapshot is not an object")
        node = production_node(latest_snapshot, node_code)
        production = node.get("production") if isinstance(node.get("production"), dict) else {}
        target_rate = float(production.get("target_rate") or 0)
        changed_metrics = changed_physical_metrics(baseline_production, production)
        if (
            status == "verified"
            and latest_command.get("verification_status") == "effective"
            and abs(target_rate - expected_rate) <= 0.001
            and changed_metrics
        ):
            return latest_command, latest_snapshot, observed_statuses, changed_metrics
        if status in {"failed", "rejected", "cancelled", "expired"}:
            raise GateFailure(
                f"command {command_id} reached terminal failure state {status}: "
                f"{latest_command.get('result_message', '')}"
            )
        time.sleep(2)
    raise GateFailure(
        f"command {command_id} did not prove an effective SimPy result within {timeout_seconds}s; "
        f"last={latest_command}; states={observed_statuses}"
    )


def postgres_evidence(
    *,
    dsn: str,
    tenant_id: str,
    site_id: str,
    order_id: str,
    command_id: int,
    node_code: str,
    expected_rate: float,
) -> dict[str, Any]:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(dsn, row_factory=dict_row, autocommit=True) as connection:
        connection.execute(
            "SELECT set_config('app.tenant_id', %s, false), set_config('app.site_id', %s, false)",
            (tenant_id, site_id),
        )
        order = connection.execute(
            "SELECT * FROM allocation_order_shadow WHERE order_id = %s",
            (order_id,),
        ).fetchone()
        require(order is not None, "allocation order was not persisted in PostgreSQL")
        require(order["status"] == "in_progress", "order did not reach in_progress", order)

        plan = connection.execute(
            """SELECT product_code, target_quantity, priority, reason, updated_at
               FROM production_plan_shadow WHERE product_code = %s""",
            (order["product_code"],),
        ).fetchone()
        require(plan is not None, "production plan was not persisted in PostgreSQL")
        require(
            int(plan["target_quantity"]) >= int(order["required_quantity"]),
            "persisted plan does not cover the accepted order",
            {"order": order, "plan": plan},
        )
        require(order_id in str(plan["reason"]), "persisted plan lost order causality", plan)

        dispatch = connection.execute(
            """SELECT task_id, assigned_node, status, quantity, updated_at
               FROM dispatch_task_shadow
               WHERE product_code = %s AND assigned_node = %s
               ORDER BY task_id DESC LIMIT 1""",
            (order["product_code"], node_code),
        ).fetchone()
        require(dispatch is not None, "dispatch task was not persisted for the target node")
        require(dispatch["status"] == "in_progress", "dispatch task did not reflect verified execution", dispatch)

        command = connection.execute(
            """SELECT command_id, node_code, status, risk_level, parameters_json, claimed_by,
                      attempt_count, verification_status, verification_evidence_json,
                      received_at, applied_at, verified_at
               FROM command_shadow WHERE command_id = %s""",
            (command_id,),
        ).fetchone()
        require(command is not None, "command was not persisted in PostgreSQL")
        parameters = json.loads(command["parameters_json"] or "{}")
        verification = json.loads(command["verification_evidence_json"] or "{}")
        require(command["node_code"] == node_code, "persisted command target changed", command)
        require(command["status"] == "verified", "persisted command is not verified", command)
        require(command["risk_level"] == "high", "dispatch command lost high-risk policy", command)
        require(command["claimed_by"] == node_code, "node claim identity was not persisted", command)
        require(int(command["attempt_count"]) >= 1, "node claim attempt was not persisted", command)
        require(command["verification_status"] == "effective", "Verifier result is not effective", command)
        require(parameters.get("source_order_id") == order_id, "command lost source order", parameters)
        require(
            abs(float(parameters.get("target_rate") or 0) - expected_rate) <= 0.001,
            "persisted command target differs from the approved target",
            parameters,
        )
        require(verification.get("target_applied") is True, "Verifier did not prove target application", verification)
        require(command["received_at"] and command["applied_at"] and command["verified_at"], "command lifecycle timestamps are incomplete", command)

        heartbeat = connection.execute(
            """SELECT payload_json, received_at FROM heartbeat_shadow
               WHERE node_code = %s ORDER BY id DESC LIMIT 1""",
            (node_code,),
        ).fetchone()
        require(heartbeat is not None, "post-command heartbeat is missing from PostgreSQL")
        heartbeat_payload = json.loads(heartbeat["payload_json"] or "{}")
        heartbeat_production = heartbeat_payload.get("production") or {}
        heartbeat_runtime = heartbeat_payload.get("runtime") or {}
        require(
            abs(float(heartbeat_production.get("target_rate") or 0) - expected_rate) <= 0.001,
            "PostgreSQL heartbeat does not contain the approved target",
            heartbeat_production,
        )
        require(
            heartbeat_runtime.get("simulation_engine") == "simpy",
            "post-command heartbeat is not from SimPy",
            heartbeat_runtime,
        )

        audit_rows = connection.execute(
            """SELECT action, resource_type, resource_id, result, detail, created_at
               FROM audit_logs
               WHERE (resource_id = %s AND resource_type = 'command')
                  OR (resource_id = %s AND resource_type = 'allocation_order')
               ORDER BY id ASC""",
            (str(command_id), order_id),
        ).fetchall()
        audit_actions = {str(row["action"]) for row in audit_rows}
        require(
            {
                "allocation-order:create",
                "dispatch:target-rate-proposed",
                "dispatch:propose",
                "command:approve",
            }.issubset(audit_actions),
            "PostgreSQL audit chain is incomplete",
            audit_rows,
        )

        event_rows = connection.execute(
            """SELECT event_type, payload_json, global_sequence
               FROM event_store
               WHERE source_node = %s
               ORDER BY global_sequence DESC LIMIT 200""",
            (node_code,),
        ).fetchall()
        matching_events: list[dict[str, Any]] = []
        for row in event_rows:
            payload = json.loads(row["payload_json"] or "{}")
            if event_mentions_command(str(row["event_type"]), payload, command_id):
                matching_events.append({**row, "payload": payload})
        stages = {str(item["payload"].get("stage") or item["event_type"]) for item in matching_events}
        require(
            {
                "command-created",
                "command-approved",
                "command-claimed",
                "command-result",
                "command-verification-effective",
            }.issubset(stages),
            "event-store command lifecycle is incomplete",
            {"stages": sorted(stages), "events": matching_events},
        )

    return {
        "allocation_order": {"order_id": order_id, "status": order["status"]},
        "production_plan": {
            "product_code": plan["product_code"],
            "target_quantity": int(plan["target_quantity"]),
        },
        "dispatch_task": {
            "task_id": int(dispatch["task_id"]),
            "status": dispatch["status"],
            "assigned_node": dispatch["assigned_node"],
        },
        "command": {
            "command_id": command_id,
            "status": command["status"],
            "verification_status": command["verification_status"],
            "claimed_by": command["claimed_by"],
            "attempt_count": int(command["attempt_count"]),
        },
        "heartbeat": {
            "target_rate": heartbeat_production.get("target_rate"),
            "actual_rate": heartbeat_production.get("actual_rate"),
            "finished_quantity": heartbeat_production.get("finished_quantity"),
            "simulation_engine": heartbeat_runtime.get("simulation_engine"),
            "received_at": heartbeat["received_at"],
        },
        "audit_actions": sorted(audit_actions),
        "event_stages": sorted(stages),
    }


def run_gate(
    *,
    api_url: str,
    runtime_root: Path,
    tenant_id: str,
    site_id: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    auth = read_env_file(runtime_root / "auth.env")
    postgres = read_env_file(runtime_root / "postgres.env")
    password = auth.get("AUTH_BOOTSTRAP_PASSWORD", "")
    dsn = postgres.get("POSTGRES_DSN", "")
    require(bool(password), "AUTH_BOOTSTRAP_PASSWORD is missing from auth.env")
    require(dsn.startswith("postgresql://"), "POSTGRES_DSN is missing or invalid")

    client = ApiClient(api_url)
    unauthenticated = client.post(
        "/api/dispatch/target-rate-proposals",
        {"order_id": "unauthorized-stage-h"},
        expected=(401,),
        authenticated=False,
    )
    require(isinstance(unauthenticated, dict), "authentication failure response is not an object")
    require(
        "missing or invalid bearer" in str(unauthenticated.get("detail", "")),
        "dispatch proposal endpoint did not enforce authentication",
        unauthenticated,
    )

    login = client.post(
        "/auth/login",
        {"operator": "admin", "password": password},
        authenticated=False,
    )
    require(isinstance(login, dict), "login response is not an object")
    client.token = str(login.get("access_token") or "")
    require(bool(client.token), "administrator login did not return an access token")
    permissions = jwt_permissions(client.token)
    require(
        {"execution:manage", "command:issue", "command:approve"}.issubset(permissions),
        "administrator JWT lacks Stage H permissions",
        sorted(permissions),
    )

    baseline = client.get("/api/dashboard/snapshot", params={"mode": "normal"})
    require(isinstance(baseline, dict), "baseline dashboard snapshot is not an object")
    system = baseline.get("system") or {}
    require(
        int(system.get("nodes_connected") or 0) == int(system.get("nodes_expected") or 0) == 3,
        "Stage H requires all three production nodes online",
        system,
    )
    node_code = "grinding-workshop-01"
    baseline_node = production_node(baseline, node_code)
    runtime = baseline_node.get("runtime") or {}
    production = baseline_node.get("production") or {}
    require(runtime.get("simulation_engine") == "simpy", "target node is not running SimPy", runtime)
    require(runtime.get("runtime_source") == "simulated", "target node runtime source is not simulated", runtime)
    heartbeat_age = heartbeat_age_seconds(baseline_node)
    require(
        heartbeat_age <= 15,
        "target node heartbeat is stale",
        {"age_seconds": round(heartbeat_age, 3), "node": baseline_node},
    )

    baseline_target = float(production.get("target_rate") or 0)
    baseline_actual = float(production.get("actual_rate") or 0)
    baseline_finished = int(production.get("finished_quantity") or 0)
    physical_rate = float(production.get("nominal_capacity_per_hour") or 0) / 60.0
    require(baseline_target > 0 and physical_rate > 0, "baseline rate/capacity is missing", production)
    deadline_hours = 2
    quantity, expected_rate, rate_direction = derive_observable_target(
        baseline_target=baseline_target,
        physical_rate=physical_rate,
        horizon_minutes=deadline_hours * 60,
    )

    order_result = client.post(
        "/api/allocation-orders",
        {
            "product_code": "P3",
            "required_quantity": quantity,
            "priority": 1,
            "deadline_hours": deadline_hours,
            "source_unit": "stage-h-verifier",
            "assigned_cloud_role": "governed-dispatch",
            "reason": f"Stage H closed-loop proof {datetime.now(UTC).isoformat()}",
        },
    )
    require(isinstance(order_result, dict), "allocation order response is not an object")
    order = order_result.get("order") or {}
    order_id = str(order.get("order_id") or "")
    require(bool(order_id), "allocation order was not created", order_result)
    plan = next(
        (
            item
            for item in order_result.get("plans", [])
            if isinstance(item, dict) and item.get("product_code") == "P3"
        ),
        None,
    )
    require(plan is not None, "order did not produce a P3 plan", order_result)
    require(int(plan.get("target_quantity") or 0) >= quantity, "plan does not cover order", plan)
    require(order_id in str(plan.get("reason") or ""), "plan reason does not identify source order", plan)

    tasks = client.get("/api/dispatch/tasks")
    require(isinstance(tasks, list), "dispatch tasks endpoint did not return a list", tasks)
    target_tasks = [
        item
        for item in tasks
        if isinstance(item, dict)
        and item.get("product_code") == "P3"
        and item.get("assigned_node") == node_code
    ]
    require(target_tasks, "plan did not create a dispatch task for the target node", tasks)

    proposal = client.post(
        "/api/dispatch/target-rate-proposals",
        {"order_id": order_id, "node_code": node_code},
    )
    require(isinstance(proposal, dict), "dispatch proposal response is not an object")
    require(proposal.get("requires_approval") is True, "dispatch proposal bypassed approval", proposal)
    require(abs(float(proposal.get("requested_rate") or 0) - expected_rate) <= 0.001, "proposal rate is not order-derived", proposal)
    commands = proposal.get("commands") or []
    require(len(commands) == 1, "Stage H expected exactly one target-node command", proposal)
    command = commands[0]
    command_id = int(command.get("id") or 0)
    require(command_id > 0, "dispatch proposal did not return a command id", command)
    require(command.get("status") == "waiting_approval", "command bypassed waiting_approval", command)
    require(command.get("risk_level") == "high", "dispatch command is not high risk", command)
    require(command.get("parameters", {}).get("source_order_id") == order_id, "command lost order causality", command)

    pending = client.get("/api/ops/pending-approvals")
    require(
        isinstance(pending, list)
        and any(int(item.get("command", {}).get("id") or 0) == command_id for item in pending),
        "command is not visible in the approval queue",
        pending,
    )
    denied = client.post(
        f"/api/ops/approve/{command_id}",
        params={"confirmation_code": "WRONG"},
    )
    require(isinstance(denied, dict), "denied approval response is not an object")
    require(denied.get("accepted") is False, "wrong confirmation code was accepted", denied)
    require(
        denied.get("safety", {}).get("reason_code") == "confirmation_code_required",
        "Safety Governor did not enforce CONFIRM",
        denied,
    )
    still_waiting = command_by_id(client, command_id)
    require(still_waiting.get("status") == "waiting_approval", "denied approval changed command state", still_waiting)

    approved = client.post(
        f"/api/ops/approve/{command_id}",
        params={"confirmation_code": "CONFIRM"},
    )
    require(isinstance(approved, dict), "approval response is not an object")
    require(approved.get("accepted") is True and approved.get("status") == "pending", "approved command did not enter pending", approved)

    final_command, final_snapshot, observed_statuses, changed_metrics = wait_for_effect(
        client,
        command_id=command_id,
        node_code=node_code,
        expected_rate=expected_rate,
        baseline_production=production,
        timeout_seconds=timeout_seconds,
    )
    final_node = production_node(final_snapshot, node_code)
    final_runtime = final_node.get("runtime") or {}
    final_production = final_node.get("production") or {}
    final_target = float(final_production.get("target_rate") or 0)
    final_actual = float(final_production.get("actual_rate") or 0)
    final_finished = int(final_production.get("finished_quantity") or 0)
    require(abs(final_target - expected_rate) <= 0.001, "Dashboard does not show approved target", final_node)
    actual_rate_moved = (
        final_actual >= baseline_actual + 0.02
        if rate_direction == "increase"
        else final_actual <= baseline_actual - 0.02
    )
    require(
        actual_rate_moved,
        f"SimPy actual rate did not {rate_direction} after the command",
        {"baseline": baseline_actual, "final": final_actual},
    )
    require(
        bool(changed_metrics),
        "SimPy did not change output, WIP, or quality metrics",
        {"baseline": production, "final": final_production},
    )
    require(final_runtime.get("simulation_time") != runtime.get("simulation_time"), "SimPy clock did not advance", {"baseline": runtime, "final": final_runtime})
    require(final_command.get("claimed_by") == node_code, "command was not claimed by its bound node", final_command)
    require(int(final_command.get("attempt_count") or 0) >= 1, "command claim attempt was not recorded", final_command)
    verification = final_command.get("verification_evidence") or {}
    require(verification.get("target_applied") is True, "Verifier did not observe target application", verification)
    require(verification.get("own_rate_moved") is True, "Verifier did not observe production-rate movement", verification)

    dashboard_command = next(
        (
            item
            for item in final_snapshot.get("commands", [])
            if isinstance(item, dict) and int(item.get("id") or 0) == command_id
        ),
        None,
    )
    require(dashboard_command is not None, "Dashboard snapshot does not expose the command", final_snapshot)
    dispatch_plan = final_snapshot.get("dispatch_plan") or {}
    require(int(dispatch_plan.get("command_id") or 0) == command_id, "Dashboard dispatch panel lost command identity", dispatch_plan)
    require(dispatch_plan.get("status") == "approved_executed", "Dashboard dispatch panel is not verified", dispatch_plan)
    require(dispatch_plan.get("verification_status") == "effective", "Dashboard does not expose effective verification", dispatch_plan)

    db_evidence = postgres_evidence(
        dsn=dsn,
        tenant_id=tenant_id,
        site_id=site_id,
        order_id=order_id,
        command_id=command_id,
        node_code=node_code,
        expected_rate=expected_rate,
    )

    return {
        "status": "PASS",
        "gate": "stage-h-closed-loop",
        "order_change": {
            "order_id": order_id,
            "product_code": "P3",
            "quantity": quantity,
            "deadline_hours": deadline_hours,
        },
        "plan_and_dispatch": {
            "plan_target_quantity": int(plan.get("target_quantity") or 0),
            "target_node": node_code,
            "target_rate_before": baseline_target,
            "target_rate_approved": expected_rate,
            "rate_direction": rate_direction,
        },
        "authorization_and_safety": {
            "unauthenticated_request_rejected": True,
            "required_permissions": ["execution:manage", "command:issue", "command:approve"],
            "wrong_confirmation_rejected": True,
            "risk_level": "high",
        },
        "node_and_simpy": {
            "claimed_by": final_command.get("claimed_by"),
            "attempt_count": int(final_command.get("attempt_count") or 0),
            "observed_statuses": observed_statuses,
            "simulation_engine": final_runtime.get("simulation_engine"),
            "simulation_time_before": runtime.get("simulation_time"),
            "simulation_time_after": final_runtime.get("simulation_time"),
            "actual_rate_before": baseline_actual,
            "actual_rate_after": final_actual,
            "finished_quantity_before": baseline_finished,
            "finished_quantity_after": final_finished,
            "changed_physical_metrics": changed_metrics,
        },
        "verifier": {
            "status": final_command.get("verification_status"),
            "observation_count": verification.get("observation_count"),
            "target_applied": verification.get("target_applied"),
            "own_rate_moved": verification.get("own_rate_moved"),
        },
        "dashboard": {
            "command_id": command_id,
            "dispatch_status": dispatch_plan.get("status"),
            "target_rate": final_target,
            "verification_status": dispatch_plan.get("verification_status"),
        },
        "postgresql": db_evidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the Stage H industrial control loop")
    parser.add_argument("--api-url", default="http://127.0.0.1:8080")
    parser.add_argument("--runtime-root", type=Path, default=Path(r"D:\MiniOGAS-VMs"))
    parser.add_argument("--tenant-id", default="tenant-local")
    parser.add_argument("--site-id", default="site-digital-twin")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args()
    try:
        result = run_gate(
            api_url=args.api_url,
            runtime_root=args.runtime_root,
            tenant_id=args.tenant_id,
            site_id=args.site_id,
            timeout_seconds=max(30, args.timeout_seconds),
        )
    except GateFailure as exc:
        print(json.dumps({"status": "FAIL", "gate": "stage-h-closed-loop", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
