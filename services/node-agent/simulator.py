import json
import os
import random
import sqlite3
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from socket import gethostname
from pathlib import Path

import simpy


@dataclass
class MachineProfile:
    code: str
    workshop_type: str
    cycle_time_sec: int
    base_yield_rate: float
    temp_warning: float
    temp_fault: float
    tool_wear_warning: float
    tool_wear_fault: float


PROFILES = {
    "milling": MachineProfile("MILL-02", "milling", 60, 0.965, 78.0, 82.0, 65.0, 80.0),
    "turning": MachineProfile("LATHE-01", "turning", 45, 0.975, 76.0, 84.0, 70.0, 86.0),
    "grinding": MachineProfile("GRIND-01", "grinding", 75, 0.982, 72.0, 80.0, 65.0, 82.0),
}


def load_env_file(path: str = "/etc/miniogas/node.env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip("\"'")


load_env_file(os.environ.get("OGAS_NODE_ENV_FILE", "/etc/miniogas/node.env"))


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def parse_positive_int(name: str, default: str, *, minimum: int = 1) -> int:
    raw = env(name, default)
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


NODE_CODE = env("NODE_CODE", "milling-workshop-01")
WORKSHOP_TYPE = env("WORKSHOP_TYPE", "milling")
CENTRAL_API_URL = env("CENTRAL_API_URL", "http://127.0.0.1:8080")
OGAS_API_TOKEN = env("OGAS_API_TOKEN", "")
OGAS_SESSION_TOKEN = env("OGAS_SESSION_TOKEN", "")
LOCAL_DB_PATH = Path(env("LOCAL_DB_PATH", "./node.db"))
HEARTBEAT_SEC = parse_positive_int("HEARTBEAT_SEC", "5")
EMERGENCY_AFTER_TICKS = parse_positive_int("EMERGENCY_AFTER_TICKS", "18")
SIMULATION_MODE = env("SIMULATION_MODE", "normal")
SIMULATION_ENGINE = env("SIMULATION_ENGINE", "simple").strip().lower()
NODE_DEPLOYMENT_MODE = env("NODE_DEPLOYMENT_MODE", "process")
RUN_ID = env("OGAS_RUN_ID", f"RUN-{datetime.now(timezone.utc).strftime('%Y%m%d')}-001")
SCENARIO_ID = env("OGAS_SCENARIO_ID", "")
SIMULATION_SPEED = parse_positive_int("SIMULATION_SPEED", "1")
SIMULATION_RANDOM_SEED = parse_positive_int("SIMULATION_RANDOM_SEED", "20260613", minimum=0)
ACTIVE_DISPATCH: dict = {}
ACTIVE_PART: dict = {}
APPLIED_COMMAND_IDS: set[int] = set()
COMMAND_TARGET_RATE: float | None = None


def log_event(level: str, event: str, **fields) -> None:
    print(
        json.dumps(
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "level": level,
                "event": event,
                "node_code": NODE_CODE,
                **fields,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def validate_startup_config() -> list[str]:
    errors: list[str] = []
    if not OGAS_API_TOKEN:
        errors.append("OGAS_API_TOKEN is required")
    if not str(LOCAL_DB_PATH).strip():
        errors.append("LOCAL_DB_PATH is required")
    if HEARTBEAT_SEC < 1:
        errors.append("HEARTBEAT_SEC must be >= 1")
    return errors


def build_json_request(path: str, payload: dict | None, *, method: str = "POST") -> tuple[urllib.request.Request, str]:
    request_id = str(uuid.uuid4())
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "X-OGAS-Token": OGAS_API_TOKEN,
        "X-Request-ID": request_id,
    }
    if payload is not None:
        headers["Content-Type"] = "application/json"
    return (
        urllib.request.Request(
            CENTRAL_API_URL.rstrip("/") + path,
            data=data,
            headers=headers,
            method=method,
        ),
        request_id,
    )


def connect_db() -> sqlite3.Connection:
    LOCAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(LOCAL_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS heartbeats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payload TEXT NOT NULL,
            synced INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(heartbeats)").fetchall()}
    if "request_id" not in existing_columns:
        conn.execute("ALTER TABLE heartbeats ADD COLUMN request_id TEXT NOT NULL DEFAULT ''")
    if "send_error" not in existing_columns:
        conn.execute("ALTER TABLE heartbeats ADD COLUMN send_error TEXT NOT NULL DEFAULT ''")
    if "http_status" not in existing_columns:
        conn.execute("ALTER TABLE heartbeats ADD COLUMN http_status INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    return conn


def machine_state(profile: MachineProfile, tick: int) -> dict:
    stress_mode = SIMULATION_MODE == "demo_stress"
    profile_offset = {"turning": 10, "milling": 6, "grinding": 52}.get(profile.workshop_type, 0) if stress_mode else 0
    phase = (tick + profile_offset) % 72
    temp_fault_window = (
        profile.workshop_type == "turning"
        and ((stress_mode and 34 <= phase < 46) or (not stress_mode and 620 <= tick < 644))
    )
    sync_pressure_window = (
        profile.workshop_type == "milling"
        and ((stress_mode and 18 <= phase < 34) or (not stress_mode and 180 <= tick < 210))
    )
    wear_warning_window = (
        profile.workshop_type == "grinding"
        and ((stress_mode and 24 <= phase < 46) or (not stress_mode and tick >= 900))
    )
    coolant_window = (
        profile.workshop_type == "milling"
        and ((stress_mode and 8 <= phase < 16) or (not stress_mode and 260 <= tick < 276))
    )
    quality_window = (
        profile.workshop_type == "turning"
        and ((stress_mode and 12 <= phase < 20) or (not stress_mode and 340 <= tick < 356))
    )
    vibration_window = (
        profile.workshop_type == "grinding"
        and ((stress_mode and 54 <= phase < 62) or (not stress_mode and 720 <= tick < 732))
    )
    emergency = temp_fault_window
    finished = max(0, tick * HEARTBEAT_SEC // profile.cycle_time_sec)
    wear_start = {"milling": 18.0, "turning": 16.0, "grinding": 14.0}.get(profile.workshop_type, 18.0)
    wear_rate = 0.22 if stress_mode else 0.035
    tool_wear = min(95.0, wear_start + finished * wear_rate + (28.0 if wear_warning_window and stress_mode else 0.0))
    load = 0.72 + min(0.18, finished * 0.004)
    spindle_temp = 54.0 + load * 18.0 + tool_wear * 0.18 + random.uniform(-1.2, 1.2)
    if emergency:
        spindle_temp += 12.0
    if sync_pressure_window or coolant_window:
        spindle_temp += 3.0
    if vibration_window:
        spindle_temp += 5.0

    defect_rate = max(0.01, 1.0 - profile.base_yield_rate)
    if tool_wear > profile.tool_wear_warning:
        defect_rate += (tool_wear - profile.tool_wear_warning) * 0.004
    if sync_pressure_window:
        defect_rate += 0.018
    if quality_window:
        defect_rate += 0.035
    defect_quantity = int(finished * defect_rate)

    status = "running"
    alarms = []
    if sync_pressure_window:
        status = "warning"
    if coolant_window:
        status = "warning"
        alarms.append({"type": "COOLANT_FLOW_LOW", "severity": "medium", "status": "open"})
    if quality_window:
        status = "warning"
        alarms.append({"type": "QUALITY_DRIFT", "severity": "medium", "status": "open"})
    if tool_wear >= profile.tool_wear_warning:
        status = "warning"
        alarms.append({"type": "TOOL_WEAR_WARNING", "severity": "medium", "status": "open"})
    if vibration_window:
        status = "fault"
        alarms.append({"type": "VIBRATION_HIGH", "severity": "high", "status": "open"})
    if temp_fault_window and spindle_temp >= profile.temp_fault:
        status = "fault"
        alarms.append({"type": "SPINDLE_TEMP_HIGH", "severity": "high", "status": "open"})

    return {
        "status": status,
        "finished_quantity": finished,
        "defect_quantity": defect_quantity,
        "tool_wear_level": round(tool_wear, 2),
        "spindle_temp": round(spindle_temp, 2),
        "load": round(load, 2),
        "defect_rate": round(defect_rate, 4),
        "alarms": alarms,
        "sync_pressure": sync_pressure_window,
    }


def simpy_machine_state(
    profile: MachineProfile,
    tick: int,
    *,
    random_seed: int,
    scenario_id: str,
) -> dict:
    rng = random.Random(f"{random_seed}:{profile.workshop_type}:{scenario_id}")
    env = simpy.Environment()
    state = {"finished": 0, "defects": 0}

    def machine_process():
        while True:
            yield env.timeout(profile.cycle_time_sec)
            state["finished"] += 1
            if rng.random() > profile.base_yield_rate:
                state["defects"] += 1

    env.process(machine_process())
    until_sec = max(0.0, float(tick * HEARTBEAT_SEC * SIMULATION_SPEED))
    if until_sec:
        env.run(until=until_sec + 0.0001)

    finished = int(state["finished"])
    defects = int(state["defects"])
    scenario = scenario_id.upper()
    load = min(0.94, 0.62 + finished * 0.006)
    tool_wear = min(95.0, 14.0 + finished * 0.045)
    spindle_temp = 52.0 + load * 18.0 + tool_wear * 0.12
    alarms: list[dict] = []
    status = "running"
    sync_pressure = False

    if "COOLANT" in scenario:
        status = "warning"
        spindle_temp += 4.0
        alarms.append({"type": "COOLANT_FLOW_LOW", "severity": "medium", "status": "open"})
    if "QUALITY" in scenario:
        status = "warning"
        defects = max(defects, max(1, finished // 12))
        alarms.append({"type": "QUALITY_DRIFT", "severity": "medium", "status": "open"})
    if "WEAR" in scenario:
        status = "warning"
        tool_wear = max(tool_wear, profile.tool_wear_warning + 2.0)
        alarms.append({"type": "TOOL_WEAR_WARNING", "severity": "medium", "status": "open"})
    if "VIBRATION" in scenario:
        status = "fault"
        spindle_temp += 5.0
        alarms.append({"type": "VIBRATION_HIGH", "severity": "high", "status": "open"})
    if "SPINDLE" in scenario or "TEMP" in scenario:
        status = "fault"
        spindle_temp = max(spindle_temp, profile.temp_fault + 6.0)
        alarms.append({"type": "SPINDLE_TEMP_HIGH", "severity": "high", "status": "open"})
    if "SYNC" in scenario:
        status = "warning" if status == "running" else status
        sync_pressure = True

    defect_rate = defects / finished if finished else 0.0
    return {
        "status": status,
        "finished_quantity": finished,
        "defect_quantity": defects,
        "tool_wear_level": round(tool_wear, 2),
        "spindle_temp": round(spindle_temp, 2),
        "load": round(load, 2),
        "defect_rate": round(defect_rate, 4),
        "alarms": alarms,
        "sync_pressure": sync_pressure,
    }


def scenario_id_for(profile: MachineProfile) -> str:
    if SCENARIO_ID:
        return SCENARIO_ID
    if SIMULATION_MODE == "demo_stress":
        return f"SCN-{profile.workshop_type.upper()}-DEMO-STRESS-001"
    return "SCN-NORMAL-MIXED-001"


def simulation_time_for_tick(tick: int) -> str:
    elapsed = timedelta(seconds=tick * HEARTBEAT_SEC * SIMULATION_SPEED)
    return (datetime.now(timezone.utc) + elapsed).isoformat()


def production_flow_metrics(profile: MachineProfile, state: dict, tick: int) -> dict:
    target_rate = COMMAND_TARGET_RATE if COMMAND_TARGET_RATE is not None else 60.0 / profile.cycle_time_sec
    utilization = min(0.98, max(0.0, float(state["load"])))
    defect_rate = min(1.0, max(0.0, float(state["defect_rate"])))
    actual_rate = target_rate * utilization * max(0.0, 1.0 - defect_rate)
    finished = int(state["finished_quantity"])
    queue_pressure = 4 if state["sync_pressure"] else 0
    wip_input = max(0, 6 + (tick % 9) + queue_pressure)
    wip_output = max(0, min(wip_input, int(round(actual_rate * 4))))
    return {
        "wip_input": wip_input,
        "wip_output": wip_output,
        "target_rate": round(target_rate, 3),
        "actual_rate": round(actual_rate, 3),
        "utilization": round(utilization, 3),
        "defect_rate": round(defect_rate if finished else 0.0, 4),
    }


def heartbeat_payload(profile: MachineProfile, tick: int) -> dict:
    scenario_id = scenario_id_for(profile)
    if SIMULATION_ENGINE == "simpy":
        state = simpy_machine_state(
            profile,
            tick,
            random_seed=SIMULATION_RANDOM_SEED,
            scenario_id=scenario_id,
        )
    else:
        state = machine_state(profile, tick)
    now = datetime.now(timezone.utc).isoformat()
    db_latency = 8 + int(state["load"] * 12) + (18 if state["status"] == "fault" else 0)
    pending_records = 0
    if state["sync_pressure"]:
        pending_records = 3 + (tick % 5)
    elif state["status"] == "fault":
        pending_records = min(12, 6 + (tick % 7))
    active_order = ACTIVE_PART.get("order_id") or ACTIVE_DISPATCH.get("active_order", "WO-20260530-004")

    return {
        "node_code": NODE_CODE,
        "timestamp": now,
        "status": state["status"],
        "agent_version": "0.1.0",
        "session_token": OGAS_SESSION_TOKEN,
        "uptime_sec": tick * HEARTBEAT_SEC,
        "runtime": {
            "deployment_mode": NODE_DEPLOYMENT_MODE,
            "simulation_mode": SIMULATION_MODE,
            "simulation_engine": SIMULATION_ENGINE,
            "host": gethostname(),
            "pid": os.getpid(),
            "heartbeat_sec": HEARTBEAT_SEC,
            "run_id": RUN_ID,
            "scenario_id": scenario_id,
            "simulation_time": simulation_time_for_tick(tick),
            "simulation_speed": SIMULATION_SPEED,
            "runtime_source": "node-agent",
        },
        "metrics": {
            "cpu_usage": round(24 + state["load"] * 42 + random.uniform(-2, 2), 2),
            "memory_usage": round(48 + state["load"] * 20 + random.uniform(-1, 1), 2),
            "disk_usage": 64.2,
            "network_latency_ms": 35 + pending_records * 3,
            "db_latency_ms": db_latency,
        },
        "production": {
            "active_order": active_order,
            "active_part_id": ACTIVE_PART.get("part_id", ""),
            "dispatch_policy": ACTIVE_DISPATCH.get("policy", "local_fallback"),
            "machine_code": profile.code,
            "workshop_type": profile.workshop_type,
            "finished_quantity": state["finished_quantity"],
            "defect_quantity": state["defect_quantity"],
            "tool_wear_level": state["tool_wear_level"],
            "spindle_temp": state["spindle_temp"],
            **production_flow_metrics(profile, state, tick),
        },
        "alarms": state["alarms"],
        "sync": {
            "last_sync_id": tick,
            "pending_records": pending_records,
        },
    }


def store_heartbeat(conn: sqlite3.Connection, payload: dict, result: dict) -> None:
    conn.execute(
        """
        INSERT INTO heartbeats (payload, synced, created_at, request_id, send_error, http_status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            json.dumps(payload, ensure_ascii=False),
            1 if result.get("synced") else 0,
            payload["timestamp"],
            str(result.get("request_id", "")),
            str(result.get("error", "")),
            int(result.get("http_status", 0) or 0),
        ),
    )
    conn.commit()


def pending_record_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM heartbeats WHERE synced = 0").fetchone()
    return int(row[0] if row else 0)


def pending_records(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, payload, created_at, request_id, send_error, http_status
        FROM heartbeats
        WHERE synced = 0
        ORDER BY id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    records: list[dict] = []
    for row in rows:
        payload = json.loads(row[1])
        records.append(
            {
                "id": int(row[0]),
                "payload": payload,
                "created_at": row[2],
                "request_id": row[3],
                "send_error": row[4],
                "http_status": int(row[5] or 0),
            }
        )
    return records


def mark_records_synced(conn: sqlite3.Connection, record_ids: list[int], request_id: str, http_status: int) -> None:
    if not record_ids:
        return
    placeholders = ",".join("?" for _ in record_ids)
    conn.execute(
        f"""
        UPDATE heartbeats
        SET synced = 1, request_id = ?, http_status = ?, send_error = ''
        WHERE id IN ({placeholders})
        """,
        (request_id, http_status, *record_ids),
    )
    conn.commit()


def send_heartbeat(payload: dict) -> dict:
    request, request_id = build_json_request("/api/node-heartbeats", payload)
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            ok = 200 <= response.status < 300
            return {"synced": ok, "request_id": request_id, "http_status": response.status, "error": ""}
    except urllib.error.HTTPError as error:
        return {"synced": False, "request_id": request_id, "http_status": error.code, "error": str(error)}
    except (urllib.error.URLError, TimeoutError) as error:
        return {"synced": False, "request_id": request_id, "http_status": 0, "error": str(error)}


def sync_pending_records(conn: sqlite3.Connection, limit: int = 20) -> dict:
    records = pending_records(conn, limit=limit)
    if not records:
        return {"synced": True, "request_id": "", "http_status": 204, "error": "", "count": 0}

    payload = {
        "node_code": NODE_CODE,
        "records": [
            {
                "local_id": record["id"],
                "payload": record["payload"],
                "created_at": record["created_at"],
                "original_request_id": record["request_id"],
                "original_http_status": record["http_status"],
                "original_error": record["send_error"],
            }
            for record in records
        ],
    }
    request, request_id = build_json_request("/api/node-records/sync", payload)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            ok = 200 <= response.status < 300
            if ok:
                mark_records_synced(conn, [record["id"] for record in records], request_id, response.status)
            return {"synced": ok, "request_id": request_id, "http_status": response.status, "error": "", "count": len(records)}
    except urllib.error.HTTPError as error:
        return {"synced": False, "request_id": request_id, "http_status": error.code, "error": str(error), "count": len(records)}
    except (urllib.error.URLError, TimeoutError) as error:
        return {"synced": False, "request_id": request_id, "http_status": 0, "error": str(error), "count": len(records)}


def fetch_dispatch() -> None:
    global ACTIVE_DISPATCH
    request, request_id = build_json_request(f"/api/node-dispatches/{NODE_CODE}", None, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            dispatch = data.get("dispatch") or {}
            previous_order = ACTIVE_DISPATCH.get("active_order", "")
            ACTIVE_DISPATCH = dispatch
            if dispatch:
                log_event("info", "dispatch_updated", request_id=request_id, active_order=dispatch.get("active_order", ""))
            elif previous_order:
                log_event("info", "dispatch_cleared", request_id=request_id, previous_order=previous_order)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        log_event("warning", "dispatch_fetch_failed", request_id=request_id, error=str(error))
        return


def fetch_agent_commands() -> list[dict]:
    request, request_id = build_json_request(f"/api/agents/{NODE_CODE}/commands/pending", None, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
            log_event("warning", "command_fetch_unexpected", request_id=request_id, response_type=type(data).__name__)
            return []
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        log_event("warning", "command_fetch_failed", request_id=request_id, error=str(error))
        return []


def report_agent_command_result(command_id: int, status: str, message: str) -> dict:
    request, request_id = build_json_request(
        f"/api/commands/{command_id}/result",
        {"status": status, "message": message},
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            data["request_id"] = request_id
            return data
    except urllib.error.HTTPError as error:
        return {"accepted": False, "request_id": request_id, "http_status": error.code, "error": str(error)}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return {"accepted": False, "request_id": request_id, "http_status": 0, "error": str(error)}


def apply_agent_command(command: dict) -> tuple[str, str]:
    global COMMAND_TARGET_RATE
    command_id = int(command.get("id") or command.get("command_id") or 0)
    command_type = str(command.get("command_type") or "")
    if not command_id:
        return "failed", "missing command id"
    if command_id in APPLIED_COMMAND_IDS:
        return "executed", "command already applied locally"
    if command_type != "set_target_rate":
        return "failed", f"unsupported command_type={command_type}"
    parameters = command.get("parameters") if isinstance(command.get("parameters"), dict) else {}
    try:
        target_rate = float(parameters.get("target_rate"))
    except (TypeError, ValueError):
        return "failed", "set_target_rate requires numeric target_rate"
    if target_rate <= 0 or target_rate > 5:
        return "failed", f"target_rate out of safe range: {target_rate}"
    COMMAND_TARGET_RATE = round(target_rate, 3)
    APPLIED_COMMAND_IDS.add(command_id)
    return "executed", f"set_target_rate applied: {COMMAND_TARGET_RATE}"


def poll_agent_commands() -> None:
    commands = fetch_agent_commands()
    for command in commands:
        command_id = int(command.get("id") or command.get("command_id") or 0)
        status, message = apply_agent_command(command)
        if command_id:
            result = report_agent_command_result(command_id, status, message)
            log_event(
                "info" if result.get("accepted") else "warning",
                "command_result_reported",
                command_id=command_id,
                status=status,
                message=message,
                request_id=result.get("request_id", ""),
                report_accepted=result.get("accepted", False),
            )


def claim_next_part(ttl_seconds: int = 30) -> dict:
    request, request_id = build_json_request(
        f"/api/agents/{NODE_CODE}/parts/claim-next?ttl_seconds={ttl_seconds}",
        {},
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            data["request_id"] = request_id
            return data
    except urllib.error.HTTPError as error:
        return {"claimed": False, "request_id": request_id, "http_status": error.code, "error": str(error)}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return {"claimed": False, "request_id": request_id, "http_status": 0, "error": str(error)}


def complete_active_part() -> dict:
    if not ACTIVE_PART:
        return {"accepted": False, "message": "no active part"}
    part_id = str(ACTIVE_PART.get("part_id") or "")
    claim_token = str(ACTIVE_PART.get("claim_token") or "")
    request, request_id = build_json_request(
        f"/api/agents/{NODE_CODE}/parts/{part_id}/complete",
        {"claim_token": claim_token},
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
            data["request_id"] = request_id
            return data
    except urllib.error.HTTPError as error:
        return {"accepted": False, "request_id": request_id, "http_status": error.code, "error": str(error)}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return {"accepted": False, "request_id": request_id, "http_status": 0, "error": str(error)}


def poll_part_queue(tick: int) -> None:
    global ACTIVE_PART
    if WORKSHOP_TYPE not in {"milling", "grinding"}:
        return
    if not ACTIVE_PART:
        result = claim_next_part(ttl_seconds=max(30, HEARTBEAT_SEC * 8))
        if result.get("claimed") and isinstance(result.get("part"), dict):
            ACTIVE_PART = dict(result["part"])
            ACTIVE_PART["claimed_tick"] = tick
            log_event(
                "info",
                "part_claimed",
                request_id=result.get("request_id", ""),
                part_id=ACTIVE_PART.get("part_id", ""),
                order_id=ACTIVE_PART.get("order_id", ""),
            )
        return

    claimed_tick = int(ACTIVE_PART.get("claimed_tick") or tick)
    if tick - claimed_tick < 3:
        return
    part_id = str(ACTIVE_PART.get("part_id") or "")
    result = complete_active_part()
    log_event(
        "info" if result.get("accepted") else "warning",
        "part_completion_reported",
        request_id=result.get("request_id", ""),
        part_id=part_id,
        accepted=result.get("accepted", False),
        message=result.get("message", ""),
    )
    if result.get("accepted"):
        ACTIVE_PART = {}


def main() -> None:
    startup_errors = validate_startup_config()
    if startup_errors:
        log_event("error", "startup_failed", errors=startup_errors)
        raise SystemExit(2)
    profile = PROFILES.get(WORKSHOP_TYPE, PROFILES["milling"])
    conn = connect_db()
    tick = 0
    log_event(
        "info",
        "agent_started",
        central_api_url=CENTRAL_API_URL,
        deployment_mode=NODE_DEPLOYMENT_MODE,
        simulation_mode=SIMULATION_MODE,
        local_db_path=str(LOCAL_DB_PATH),
        heartbeat_sec=HEARTBEAT_SEC,
    )
    while True:
        tick += 1
        if tick == 1 or tick % 6 == 0:
            fetch_dispatch()
            poll_agent_commands()
            poll_part_queue(tick)
        payload = heartbeat_payload(profile, tick)
        result = send_heartbeat(payload)
        store_heartbeat(conn, payload, result)
        sync_result = {"count": 0}
        if result.get("synced"):
            sync_result = sync_pending_records(conn)
            if sync_result.get("count"):
                log_event(
                    "info" if sync_result.get("synced") else "warning",
                    "pending_records_sync",
                    request_id=sync_result.get("request_id", ""),
                    synced=sync_result.get("synced", False),
                    count=sync_result.get("count", 0),
                    http_status=sync_result.get("http_status", 0),
                    send_error=sync_result.get("error", ""),
                    local_pending_records=pending_record_count(conn),
                )
        log_event(
            "info" if result.get("synced") else "warning",
            "heartbeat_sent",
            request_id=result.get("request_id", ""),
            synced=result.get("synced", False),
            http_status=result.get("http_status", 0),
            send_error=result.get("error", ""),
            local_pending_records=pending_record_count(conn),
            heartbeat=payload,
        )
        time.sleep(HEARTBEAT_SEC)


if __name__ == "__main__":
    main()
