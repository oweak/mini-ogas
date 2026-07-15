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

from event_publishers import EventPublisher, HTTPPublisher
from runtime_adapters import RuntimeAdapter, SimPyRuntimeAdapter, SimpleRuntimeAdapter


@dataclass
class MachineProfile:
    code: str
    workshop_type: str
    machine_count: int
    cycle_time_sec: int
    base_yield_rate: float
    temp_warning: float
    temp_fault: float
    tool_wear_warning: float
    tool_wear_fault: float

    @property
    def nominal_capacity_per_hour(self) -> float:
        return self.machine_count * 3600.0 / self.cycle_time_sec


PROFILES = {
    "turning": MachineProfile("LATHE-01", "turning", 3, 135, 0.975, 76.0, 84.0, 70.0, 86.0),
    "milling": MachineProfile("MILL-02", "milling", 2, 144, 0.965, 78.0, 82.0, 65.0, 80.0),
    "grinding": MachineProfile("GRIND-01", "grinding", 2, 111, 0.982, 72.0, 80.0, 65.0, 82.0),
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
PART_FLOW_MODE = env("PART_FLOW_MODE", "heartbeat").strip().lower()
_simulation_start_raw = env("OGAS_SIMULATION_START_TIME", "")
try:
    SIMULATION_STARTED_AT = (
        datetime.fromisoformat(_simulation_start_raw.replace("Z", "+00:00"))
        if _simulation_start_raw
        else datetime.now(timezone.utc)
    )
except ValueError as error:
    raise ValueError("OGAS_SIMULATION_START_TIME must be an ISO-8601 timestamp") from error
if SIMULATION_STARTED_AT.tzinfo is None:
    SIMULATION_STARTED_AT = SIMULATION_STARTED_AT.replace(tzinfo=timezone.utc)
ACTIVE_DISPATCH: dict = {}
ACTIVE_PART: dict = {}
APPLIED_COMMAND_IDS: set[int] = set()
COMMAND_TARGET_RATE: float | None = None
RATE_CONTROL_STATE: dict[str, dict[str, float]] = {}
TELEMETRY_SIGNAL_MAPPINGS = {
    "SPINDLE-TEMPERATURE": ("spindle_temp", "Cel"),
    "TOOL-WEAR-LEVEL": ("tool_wear_level", "%"),
    "UTILIZATION": ("utilization", "1"),
    "DEFECT-RATE": ("defect_rate", "1"),
    "ACTUAL-RATE": ("actual_rate", "parts/min"),
}


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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS local_commands (
            command_id INTEGER PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            version INTEGER NOT NULL,
            command_type TEXT NOT NULL,
            parameters_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL,
            result_message TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            result_reported INTEGER NOT NULL DEFAULT 0,
            report_attempts INTEGER NOT NULL DEFAULT 0,
            last_report_error TEXT NOT NULL DEFAULT '',
            reported_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS telemetry_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL UNIQUE,
            payload TEXT NOT NULL,
            synced INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            request_id TEXT NOT NULL DEFAULT '',
            send_error TEXT NOT NULL DEFAULT '',
            http_status INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS telemetry_sequence_state (
            source_id TEXT PRIMARY KEY,
            last_sequence INTEGER NOT NULL CHECK (last_sequence >= 0)
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
    command_columns = {row[1] for row in conn.execute("PRAGMA table_info(local_commands)").fetchall()}
    command_migrations = {
        "parameters_json": "TEXT NOT NULL DEFAULT '{}'",
        "result_reported": "INTEGER NOT NULL DEFAULT 0",
        "report_attempts": "INTEGER NOT NULL DEFAULT 0",
        "last_report_error": "TEXT NOT NULL DEFAULT ''",
        "reported_at": "TEXT",
    }
    for name, definition in command_migrations.items():
        if name not in command_columns:
            conn.execute(f"ALTER TABLE local_commands ADD COLUMN {name} {definition}")
    initialize_telemetry_sequence_state(conn)
    conn.commit()
    return conn


def _payload_sequence(payload: dict) -> int:
    samples = list(payload.get("samples") or [])
    return max((int(sample.get("sequence_no") or 0) for sample in samples), default=0)


def _stored_telemetry_sequence(conn: sqlite3.Connection) -> int:
    maximum = 0
    rows = conn.execute("SELECT payload FROM telemetry_batches").fetchall()
    for row in rows:
        try:
            payload = json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            continue
        if str(payload.get("source_id") or "") != NODE_CODE:
            continue
        maximum = max(maximum, _payload_sequence(payload))
    return maximum


def initialize_telemetry_sequence_state(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT last_sequence FROM telemetry_sequence_state WHERE source_id=?",
        (NODE_CODE,),
    ).fetchone()
    if row is not None:
        return int(row[0])
    maximum = _stored_telemetry_sequence(conn)
    conn.execute(
        "INSERT INTO telemetry_sequence_state (source_id, last_sequence) VALUES (?, ?)",
        (NODE_CODE, maximum),
    )
    return maximum


def reserve_telemetry_sequence(conn: sqlite3.Connection) -> int:
    initialize_telemetry_sequence_state(conn)
    conn.execute(
        """UPDATE telemetry_sequence_state
           SET last_sequence=last_sequence+1 WHERE source_id=?""",
        (NODE_CODE,),
    )
    row = conn.execute(
        "SELECT last_sequence FROM telemetry_sequence_state WHERE source_id=?",
        (NODE_CODE,),
    ).fetchone()
    conn.commit()
    return int(row[0])


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
    elapsed_simulation_sec = tick * HEARTBEAT_SEC * SIMULATION_SPEED
    finished = max(0, elapsed_simulation_sec * profile.machine_count // profile.cycle_time_sec)
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

    def machine_process(initial_delay_sec: float):
        yield env.timeout(initial_delay_sec)
        while True:
            state["finished"] += 1
            if rng.random() > profile.base_yield_rate:
                state["defects"] += 1
            yield env.timeout(profile.cycle_time_sec)

    for machine_index in range(profile.machine_count):
        steady_state_phase = profile.cycle_time_sec * (machine_index + 1) / profile.machine_count
        env.process(machine_process(steady_state_phase))
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
    return (SIMULATION_STARTED_AT + elapsed).isoformat()


def create_runtime_adapter(engine: str | None = None) -> RuntimeAdapter:
    selected = (engine or SIMULATION_ENGINE).strip().lower()
    if selected == "simpy":
        return SimPyRuntimeAdapter(simpy_machine_state, SIMULATION_RANDOM_SEED)
    if selected == "simple":
        return SimpleRuntimeAdapter(machine_state)
    raise ValueError(f"unsupported SIMULATION_ENGINE={selected}")


def production_flow_metrics(profile: MachineProfile, state: dict, tick: int) -> dict:
    nominal_capacity_per_hour = profile.nominal_capacity_per_hour
    target_rate = COMMAND_TARGET_RATE if COMMAND_TARGET_RATE is not None else nominal_capacity_per_hour / 60.0
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
        "rate_unit": "parts_per_minute",
        "machine_count": profile.machine_count,
        "process_time_sec": profile.cycle_time_sec,
        "nominal_capacity_per_hour": round(nominal_capacity_per_hour, 1),
        "target_rate_per_hour": round(target_rate * 60.0, 1),
        "actual_rate_per_hour": round(actual_rate * 60.0, 1),
        "utilization": round(utilization, 3),
        "defect_rate": round(defect_rate if finished else 0.0, 4),
    }


def apply_rate_control_to_state(profile: MachineProfile, state: dict) -> dict:
    """Apply the command target to incremental physical output, not only telemetry."""
    raw_finished = int(state.get("finished_quantity") or 0)
    control = RATE_CONTROL_STATE.get(profile.workshop_type)
    if control is None or raw_finished < int(control["last_raw_finished"]):
        control = {
            "last_raw_finished": float(raw_finished),
            "controlled_finished": float(raw_finished),
        }
        RATE_CONTROL_STATE[profile.workshop_type] = control

    raw_delta = max(0.0, raw_finished - control["last_raw_finished"])
    if COMMAND_TARGET_RATE is None:
        controlled_delta = raw_delta
    else:
        nominal_per_minute = profile.nominal_capacity_per_hour / 60.0
        utilization = min(1.0, max(0.0, float(state.get("load") or 0.0)))
        defect_rate = min(1.0, max(0.0, float(state.get("defect_rate") or 0.0)))
        effective_target = COMMAND_TARGET_RATE * utilization * (1.0 - defect_rate)
        controlled_delta = raw_delta * min(1.0, effective_target / nominal_per_minute)

    control["last_raw_finished"] = float(raw_finished)
    control["controlled_finished"] += controlled_delta
    controlled_finished = int(control["controlled_finished"])
    adjusted = dict(state)
    adjusted["raw_finished_quantity"] = raw_finished
    adjusted["finished_quantity"] = controlled_finished
    adjusted["defect_quantity"] = min(
        controlled_finished,
        int(round(controlled_finished * float(state.get("defect_rate") or 0.0))),
    )
    return adjusted


def heartbeat_payload(
    profile: MachineProfile,
    tick: int,
    *,
    pending_records_override: int | None = None,
    runtime_adapter: RuntimeAdapter | None = None,
) -> dict:
    scenario_id = scenario_id_for(profile)
    runtime = runtime_adapter or create_runtime_adapter()
    state = apply_rate_control_to_state(profile, runtime.build_state(profile, tick, scenario_id))
    now = datetime.now(timezone.utc).isoformat()
    db_latency = 8 + int(state["load"] * 12) + (18 if state["status"] == "fault" else 0)
    simulated_pending_records = 0
    if state["sync_pressure"]:
        simulated_pending_records = 3 + (tick % 5)
    elif state["status"] == "fault":
        simulated_pending_records = min(12, 6 + (tick % 7))
    reported_pending_records = (
        max(0, int(pending_records_override))
        if pending_records_override is not None
        else simulated_pending_records
    )
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
            "simulation_engine": runtime.name,
            "host": gethostname(),
            "pid": os.getpid(),
            "heartbeat_sec": HEARTBEAT_SEC,
            "run_id": RUN_ID,
            "scenario_id": scenario_id,
            "simulation_time": simulation_time_for_tick(tick),
            "wall_clock_time": now,
            "simulation_started_at": SIMULATION_STARTED_AT.isoformat(),
            "simulation_speed": SIMULATION_SPEED,
            "random_seed": SIMULATION_RANDOM_SEED,
            "runtime_source": "simulated",
            "part_flow_mode": PART_FLOW_MODE,
        },
        "metrics": {
            "cpu_usage": round(24 + state["load"] * 42 + random.uniform(-2, 2), 2),
            "memory_usage": round(48 + state["load"] * 20 + random.uniform(-1, 1), 2),
            "disk_usage": 64.2,
            "network_latency_ms": 35 + simulated_pending_records * 3,
            "db_latency_ms": db_latency,
        },
        "production": {
            "active_order": active_order,
            "active_part_id": ACTIVE_PART.get("part_id", ""),
            "dispatch_policy": ACTIVE_DISPATCH.get("policy", "local_fallback"),
            "machine_code": profile.code,
            "workshop_type": profile.workshop_type,
            "finished_quantity": state["finished_quantity"],
            "raw_finished_quantity": state.get("raw_finished_quantity", state["finished_quantity"]),
            "defect_quantity": state["defect_quantity"],
            "tool_wear_level": state["tool_wear_level"],
            "spindle_temp": state["spindle_temp"],
            **production_flow_metrics(profile, state, tick),
        },
        "alarms": state["alarms"],
        "sync": {
            "last_sync_id": tick,
            "pending_records": reported_pending_records,
        },
    }


def telemetry_batch_payload(heartbeat: dict, tick: int) -> dict:
    production = dict(heartbeat.get("production") or {})
    runtime = dict(heartbeat.get("runtime") or {})
    timestamp = str(heartbeat["timestamp"])
    samples = []
    for signal_code, (field, unit) in TELEMETRY_SIGNAL_MAPPINGS.items():
        samples.append(
            {
                "sample_id": f"{RUN_ID}:{NODE_CODE}:{signal_code}:{tick}",
                "signal_code": signal_code,
                "value": float(production[field]),
                "unit": unit,
                "mapping_version": 1,
                "sequence_no": tick,
                "source_timestamp": timestamp,
                "simulation_time": runtime.get("simulation_time"),
            }
        )
    return {
        "batch_id": f"{RUN_ID}:{NODE_CODE}:telemetry:{tick}",
        "source": str(runtime.get("runtime_source") or "simulated"),
        "source_id": NODE_CODE,
        "equipment_code": str(production["machine_code"]),
        "edge_received_at": timestamp,
        "samples": samples,
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


def send_heartbeat(payload: dict, publisher: EventPublisher | None = None) -> dict:
    active_publisher = publisher or HTTPPublisher(CENTRAL_API_URL, OGAS_API_TOKEN)
    return active_publisher.publish_heartbeat(payload)


def send_telemetry_batch(payload: dict) -> dict:
    request, request_id = build_json_request("/api/telemetry/batches", payload)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return {
                "synced": 200 <= response.status < 300,
                "request_id": request_id,
                "http_status": response.status,
                "error": "",
            }
    except urllib.error.HTTPError as error:
        try:
            detail = error.read().decode("utf-8")
        except OSError:
            detail = str(error)
        return {
            "synced": False,
            "request_id": request_id,
            "http_status": error.code,
            "error": detail or str(error),
        }
    except (urllib.error.URLError, TimeoutError) as error:
        return {
            "synced": False,
            "request_id": request_id,
            "http_status": 0,
            "error": str(error),
        }


TERMINAL_TELEMETRY_CONFLICTS = {
    "TELEMETRY_BATCH_IDENTITY_CONFLICT",
    "TELEMETRY_SAMPLE_IDENTITY_CONFLICT",
    "TELEMETRY_SEQUENCE_IDENTITY_CONFLICT",
}


def telemetry_result_is_terminal(result: dict) -> bool:
    if int(result.get("http_status") or 0) != 409:
        return False
    try:
        problem = json.loads(str(result.get("error") or "{}"))
    except json.JSONDecodeError:
        return False
    code = str(problem.get("code") or (problem.get("detail") or {}).get("code") or "")
    return code in TERMINAL_TELEMETRY_CONFLICTS


def store_telemetry_batch(conn: sqlite3.Connection, payload: dict, result: dict) -> None:
    sequence = _payload_sequence(payload)
    conn.execute(
        """INSERT INTO telemetry_sequence_state (source_id, last_sequence)
           VALUES (?, ?)
           ON CONFLICT(source_id) DO UPDATE SET
               last_sequence=MAX(last_sequence, excluded.last_sequence)""",
        (str(payload.get("source_id") or NODE_CODE), sequence),
    )
    sync_state = 1 if result.get("synced") else (-1 if telemetry_result_is_terminal(result) else 0)
    conn.execute(
        """INSERT INTO telemetry_batches (
               batch_id, payload, synced, created_at, request_id, send_error, http_status
           ) VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(batch_id) DO UPDATE SET
               synced=excluded.synced,
               request_id=excluded.request_id,
               send_error=excluded.send_error,
               http_status=excluded.http_status""",
        (
            payload["batch_id"],
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            sync_state,
            payload["edge_received_at"],
            str(result.get("request_id") or ""),
            str(result.get("error") or ""),
            int(result.get("http_status") or 0),
        ),
    )
    conn.execute(
        """DELETE FROM telemetry_batches
           WHERE synced!=0 AND id NOT IN (
               SELECT id FROM telemetry_batches WHERE synced!=0 ORDER BY id DESC LIMIT 2000
           )"""
    )
    conn.commit()


def pending_telemetry_batches(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        """SELECT id, payload FROM telemetry_batches
           WHERE synced=0 ORDER BY id ASC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [{"id": int(row[0]), "payload": json.loads(row[1])} for row in rows]


def sync_pending_telemetry_batches(conn: sqlite3.Connection, limit: int = 20) -> dict:
    attempted = 0
    synced = 0
    rejected = 0
    for item in pending_telemetry_batches(conn, limit):
        attempted += 1
        result = send_telemetry_batch(item["payload"])
        if not result.get("synced"):
            terminal = telemetry_result_is_terminal(result)
            conn.execute(
                """UPDATE telemetry_batches
                   SET synced=?, request_id=?, send_error=?, http_status=? WHERE id=?""",
                (
                    -1 if terminal else 0,
                    str(result.get("request_id") or ""),
                    str(result.get("error") or ""),
                    int(result.get("http_status") or 0),
                    item["id"],
                ),
            )
            conn.commit()
            if terminal:
                rejected += 1
                continue
            break
        conn.execute(
            """UPDATE telemetry_batches
               SET synced=1, request_id=?, send_error='', http_status=? WHERE id=?""",
            (
                str(result.get("request_id") or ""),
                int(result.get("http_status") or 0),
                item["id"],
            ),
        )
        conn.commit()
        synced += 1
    pending_row = conn.execute(
        "SELECT COUNT(*) FROM telemetry_batches WHERE synced=0"
    ).fetchone()
    return {
        "attempted": attempted,
        "synced": synced,
        "rejected": rejected,
        "pending": int(pending_row[0]),
    }


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


def applied_command_record(conn: sqlite3.Connection, command_id: int, idempotency_key: str) -> dict | None:
    row = conn.execute(
        """SELECT command_id, idempotency_key, version, command_type, parameters_json,
                  status, result_message, applied_at, result_reported, report_attempts,
                  last_report_error, reported_at
           FROM local_commands WHERE command_id = ? OR idempotency_key = ?""",
        (command_id, idempotency_key),
    ).fetchone()
    if row is None:
        return None
    return {
        "command_id": int(row[0]),
        "idempotency_key": str(row[1]),
        "version": int(row[2]),
        "command_type": str(row[3]),
        "parameters": json.loads(str(row[4]) or "{}"),
        "status": str(row[5]),
        "result_message": str(row[6]),
        "applied_at": str(row[7]),
        "result_reported": bool(row[8]),
        "report_attempts": int(row[9]),
        "last_report_error": str(row[10]),
        "reported_at": str(row[11] or ""),
    }


def persist_applied_command(
    conn: sqlite3.Connection,
    command: dict,
    idempotency_key: str,
    status: str,
    message: str,
) -> None:
    conn.execute(
        """INSERT INTO local_commands (
               command_id, idempotency_key, version, command_type, parameters_json,
               status, result_message, applied_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(command_id) DO NOTHING""",
        (
            int(command.get("id") or command.get("command_id") or 0),
            idempotency_key,
            int(command.get("version") or 1),
            str(command.get("command_type") or ""),
            json.dumps(command.get("parameters") or {}, ensure_ascii=False, sort_keys=True),
            status,
            message,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def pending_command_results(conn: sqlite3.Connection, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        """SELECT command_id, status, result_message, report_attempts
           FROM local_commands
           WHERE result_reported = 0
           ORDER BY applied_at ASC, command_id ASC
           LIMIT ?""",
        (max(1, min(int(limit), 1000)),),
    ).fetchall()
    return [
        {
            "command_id": int(row[0]),
            "status": str(row[1]),
            "message": str(row[2]),
            "report_attempts": int(row[3]),
        }
        for row in rows
    ]


def mark_command_result_reported(conn: sqlite3.Connection, command_id: int) -> None:
    conn.execute(
        """UPDATE local_commands
           SET result_reported = 1,
               report_attempts = report_attempts + 1,
               last_report_error = '',
               reported_at = ?
           WHERE command_id = ?""",
        (datetime.now(timezone.utc).isoformat(), command_id),
    )
    conn.commit()


def mark_command_result_failed(conn: sqlite3.Connection, command_id: int, error: str) -> None:
    conn.execute(
        """UPDATE local_commands
           SET report_attempts = report_attempts + 1,
               last_report_error = ?
           WHERE command_id = ?""",
        (error[:1000], command_id),
    )
    conn.commit()


def flush_pending_command_results(conn: sqlite3.Connection) -> dict[str, int]:
    attempted = 0
    reported = 0
    for item in pending_command_results(conn):
        attempted += 1
        result = report_agent_command_result(item["command_id"], item["status"], item["message"])
        if result.get("accepted"):
            mark_command_result_reported(conn, item["command_id"])
            reported += 1
            log_event(
                "info",
                "command_result_reported",
                command_id=item["command_id"],
                request_id=result.get("request_id", ""),
                report_attempt=item["report_attempts"] + 1,
            )
        else:
            error = str(result.get("error") or f"HTTP {result.get('http_status', 0)}")
            mark_command_result_failed(conn, item["command_id"], error)
            log_event(
                "warning",
                "command_result_retry_pending",
                command_id=item["command_id"],
                request_id=result.get("request_id", ""),
                error=error,
            )
    return {"attempted": attempted, "reported": reported, "pending": len(pending_command_results(conn))}


def restore_local_command_state(conn: sqlite3.Connection) -> None:
    global COMMAND_TARGET_RATE
    row = conn.execute(
        """SELECT parameters_json
           FROM local_commands
           WHERE command_type = 'set_target_rate' AND status = 'executed'
           ORDER BY applied_at DESC, command_id DESC
           LIMIT 1"""
    ).fetchone()
    if row is None:
        return
    try:
        parameters = json.loads(str(row[0]) or "{}")
        target_rate = float(parameters["target_rate"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        log_event("warning", "command_state_restore_failed", reason="invalid persisted parameters")
        return
    physical_limit = PROFILES.get(WORKSHOP_TYPE, PROFILES["milling"]).nominal_capacity_per_hour / 60.0
    if 0 < target_rate <= physical_limit:
        COMMAND_TARGET_RATE = round(target_rate, 3)
    else:
        log_event(
            "warning",
            "command_state_restore_skipped",
            target_rate=target_rate,
            physical_limit=round(physical_limit, 3),
        )


def apply_agent_command(
    command: dict,
    conn: sqlite3.Connection | None = None,
    *,
    now: datetime | None = None,
) -> tuple[str, str]:
    global COMMAND_TARGET_RATE
    command_id = int(command.get("id") or command.get("command_id") or 0)
    command_type = str(command.get("command_type") or "")
    if not command_id:
        return "failed", "missing command id"
    version = int(command.get("version") or 1)
    if version != 1:
        return "failed", f"unsupported command version={version}"
    parameters = command.get("parameters") if isinstance(command.get("parameters"), dict) else {}
    idempotency_key = str(parameters.get("idempotency_key") or f"command-{command_id}")
    existing = applied_command_record(conn, command_id, idempotency_key) if conn else None
    if command_id in APPLIED_COMMAND_IDS or existing:
        if existing:
            return str(existing["status"]), f"command already applied locally: {existing['result_message']}"
        return "executed", "command already applied locally"
    expires_at = str(command.get("expires_at") or "")
    if expires_at:
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
        except ValueError:
            return "failed", "invalid command expires_at"
        if (now or datetime.now(timezone.utc)) >= expiry:
            return "failed", "command expired before execution"
    if command_type != "set_target_rate":
        return "failed", f"unsupported command_type={command_type}"
    try:
        target_rate = float(parameters.get("target_rate"))
    except (TypeError, ValueError):
        return "failed", "set_target_rate requires numeric target_rate"
    physical_limit = PROFILES.get(WORKSHOP_TYPE, PROFILES["milling"]).nominal_capacity_per_hour / 60.0
    if target_rate <= 0 or target_rate > physical_limit:
        return "failed", f"target_rate out of safe range: {target_rate}"
    COMMAND_TARGET_RATE = round(target_rate, 3)
    APPLIED_COMMAND_IDS.add(command_id)
    message = f"set_target_rate applied: {COMMAND_TARGET_RATE}"
    if conn:
        persist_applied_command(conn, command, idempotency_key, "executed", message)
    return "executed", message


def poll_agent_commands(conn: sqlite3.Connection | None = None) -> None:
    if conn:
        flush_pending_command_results(conn)
    commands = fetch_agent_commands()
    for command in commands:
        command_id = int(command.get("id") or command.get("command_id") or 0)
        parameters = command.get("parameters") if isinstance(command.get("parameters"), dict) else {}
        idempotency_key = str(parameters.get("idempotency_key") or f"command-{command_id}")
        existing = applied_command_record(conn, command_id, idempotency_key) if conn and command_id else None
        if existing:
            log_event(
                "info",
                "command_duplicate_ignored",
                command_id=command_id,
                result_reported=existing["result_reported"],
            )
            continue
        status, message = apply_agent_command(command, conn)
        if command_id:
            if conn:
                if applied_command_record(conn, command_id, idempotency_key) is None:
                    persist_applied_command(conn, command, idempotency_key, status, message)
                log_event(
                    "info",
                    "command_result_queued",
                    command_id=command_id,
                    status=status,
                    message=message,
                )
            else:
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
    if conn:
        flush_pending_command_results(conn)


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
    runtime_adapter = create_runtime_adapter()
    event_publisher: EventPublisher = HTTPPublisher(CENTRAL_API_URL, OGAS_API_TOKEN)
    conn = connect_db()
    restore_local_command_state(conn)
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
            poll_agent_commands(conn)
            if PART_FLOW_MODE == "agent_claim":
                poll_part_queue(tick)
        payload = heartbeat_payload(
            profile,
            tick,
            pending_records_override=pending_record_count(conn),
            runtime_adapter=runtime_adapter,
        )
        result = send_heartbeat(payload, event_publisher)
        store_heartbeat(conn, payload, result)
        telemetry = telemetry_batch_payload(payload, reserve_telemetry_sequence(conn))
        telemetry_result = send_telemetry_batch(telemetry)
        store_telemetry_batch(conn, telemetry, telemetry_result)
        telemetry_sync = sync_pending_telemetry_batches(conn) if telemetry_result.get("synced") else {
            "attempted": 0,
            "synced": 0,
            "pending": len(pending_telemetry_batches(conn)),
        }
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
        log_event(
            "info" if telemetry_result.get("synced") else "warning",
            "telemetry_batch_sent",
            batch_id=telemetry["batch_id"],
            sample_count=len(telemetry["samples"]),
            request_id=telemetry_result.get("request_id", ""),
            synced=telemetry_result.get("synced", False),
            http_status=telemetry_result.get("http_status", 0),
            send_error=telemetry_result.get("error", ""),
            retry=telemetry_sync,
        )
        time.sleep(HEARTBEAT_SEC)


if __name__ == "__main__":
    main()
