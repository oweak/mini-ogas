import os
import sqlite3
import tempfile
import unittest
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("OGAS_API_TOKEN", "node-agent-test-token")
os.environ.setdefault("LOCAL_DB_PATH", str(Path(tempfile.gettempdir()) / "miniogas-node-agent-test.db"))

import simulator
from event_publishers import EventPublisher, HTTPPublisher
from runtime_adapters import RuntimeAdapter, SimPyRuntimeAdapter, SimpleRuntimeAdapter


class FakeResponse:
    status = 202
    body = b'{"dispatch": {"active_order": "WO-1", "policy": "test"}}'

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


class NodeAgentTests(unittest.TestCase):
    def test_heartbeat_reports_actual_local_backlog_without_faking_latency(self) -> None:
        profile = simulator.PROFILES["milling"]

        payload = simulator.heartbeat_payload(profile, 1, pending_records_override=2400)

        self.assertEqual(payload["sync"]["pending_records"], 2400)
        self.assertLess(payload["metrics"]["network_latency_ms"], 500)

    def test_runtime_adapter_controls_heartbeat_state(self) -> None:
        class StubRuntime(RuntimeAdapter):
            name = "stub-runtime"

            def build_state(self, profile, tick, scenario_id):
                return {
                    "status": "running",
                    "finished_quantity": 9,
                    "defect_quantity": 1,
                    "tool_wear_level": 21.0,
                    "spindle_temp": 61.0,
                    "load": 0.5,
                    "defect_rate": 1 / 9,
                    "alarms": [],
                    "sync_pressure": False,
                }

        payload = simulator.heartbeat_payload(
            simulator.PROFILES["milling"],
            3,
            runtime_adapter=StubRuntime(),
        )

        self.assertEqual(payload["production"]["finished_quantity"], 9)
        self.assertEqual(payload["runtime"]["simulation_engine"], "stub-runtime")

    def test_runtime_adapter_factory_selects_simple_and_simpy(self) -> None:
        self.assertIsInstance(simulator.create_runtime_adapter("simple"), SimpleRuntimeAdapter)
        self.assertIsInstance(simulator.create_runtime_adapter("simpy"), SimPyRuntimeAdapter)

    def test_http_publisher_implements_event_publisher_contract(self) -> None:
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["token"] = request.headers["X-ogas-token"]
            captured["timeout"] = timeout
            return FakeResponse()

        publisher: EventPublisher = HTTPPublisher("http://central.test:8080", "node-token")
        with patch("urllib.request.urlopen", fake_urlopen):
            result = publisher.publish_heartbeat({"node_code": "turning-workshop-01"})

        self.assertTrue(result["synced"])
        self.assertEqual(result["http_status"], 202)
        self.assertEqual(
            captured,
            {
                "url": "http://central.test:8080/api/agents/turning-workshop-01/heartbeat",
                "token": "node-token",
                "timeout": 3,
            },
        )

    def test_parse_positive_int_rejects_invalid_values(self) -> None:
        with patch.dict(simulator.os.environ, {"BAD_INT": "abc", "ZERO_INT": "0"}):
            with self.assertRaises(ValueError):
                simulator.parse_positive_int("BAD_INT", "5")
            with self.assertRaises(ValueError):
                simulator.parse_positive_int("ZERO_INT", "5")

    def test_validate_startup_config_requires_token(self) -> None:
        original = simulator.OGAS_API_TOKEN
        simulator.OGAS_API_TOKEN = ""
        try:
            self.assertIn("OGAS_API_TOKEN is required", simulator.validate_startup_config())
        finally:
            simulator.OGAS_API_TOKEN = original

    def test_build_json_request_adds_auth_request_id_and_json_body(self) -> None:
        request, request_id = simulator.build_json_request("/api/node-heartbeats", {"node_code": "n1"})

        self.assertIn("/api/node-heartbeats", request.full_url)
        self.assertTrue(request_id)
        self.assertEqual(request.headers["X-request-id"], request_id)
        self.assertEqual(request.headers["X-ogas-token"], simulator.OGAS_API_TOKEN)
        self.assertEqual(request.headers["Content-type"], "application/json")
        self.assertIn(b'"node_code": "n1"', request.data)

    def test_send_heartbeat_adds_request_id_and_reports_status(self) -> None:
        captured: dict[str, urllib.request.Request] = {}

        def fake_urlopen(request: urllib.request.Request, timeout: int):
            captured["request"] = request
            self.assertEqual(timeout, 3)
            return FakeResponse()

        with patch.object(simulator.urllib.request, "urlopen", fake_urlopen):
            result = simulator.send_heartbeat({"node_code": "n1", "timestamp": "t1"})

        self.assertTrue(result["synced"])
        self.assertEqual(result["http_status"], 202)
        self.assertTrue(result["request_id"])
        self.assertEqual(captured["request"].headers["X-request-id"], result["request_id"])

    def test_send_heartbeat_records_http_error(self) -> None:
        def fake_urlopen(request: urllib.request.Request, timeout: int):
            raise urllib.error.HTTPError(request.full_url, 503, "down", {}, None)

        with patch.object(simulator.urllib.request, "urlopen", fake_urlopen):
            result = simulator.send_heartbeat({"node_code": "n1", "timestamp": "t1"})

        self.assertFalse(result["synced"])
        self.assertEqual(result["http_status"], 503)
        self.assertIn("503", result["error"])

    def test_store_heartbeat_persists_observability_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "node.db"
            original = simulator.LOCAL_DB_PATH
            simulator.LOCAL_DB_PATH = db_path
            try:
                conn = simulator.connect_db()
                result = {"synced": False, "request_id": "rid-1", "http_status": 503, "error": "central down"}
                simulator.store_heartbeat(conn, {"timestamp": "now", "node_code": "n1"}, result)

                row = conn.execute(
                    "SELECT synced, request_id, http_status, send_error FROM heartbeats"
                ).fetchone()
                self.assertEqual(row, (0, "rid-1", 503, "central down"))
                self.assertEqual(simulator.pending_record_count(conn), 1)
                conn.close()
            finally:
                simulator.LOCAL_DB_PATH = original

    def test_sync_pending_records_posts_archival_batch_and_marks_rows_synced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "node.db"
            original = simulator.LOCAL_DB_PATH
            simulator.LOCAL_DB_PATH = db_path
            try:
                conn = simulator.connect_db()
                simulator.store_heartbeat(
                    conn,
                    {"timestamp": "t1", "node_code": "n1", "status": "fault"},
                    {"synced": False, "request_id": "old-rid", "http_status": 0, "error": "central down"},
                )
                captured: dict[str, urllib.request.Request] = {}

                def fake_urlopen(request: urllib.request.Request, timeout: int):
                    captured["request"] = request
                    self.assertEqual(timeout, 5)
                    return FakeResponse()

                with patch.object(simulator.urllib.request, "urlopen", fake_urlopen):
                    result = simulator.sync_pending_records(conn)

                self.assertTrue(result["synced"])
                self.assertEqual(result["count"], 1)
                self.assertIn("/api/node-records/sync", captured["request"].full_url)
                self.assertEqual(simulator.pending_record_count(conn), 0)
                row = conn.execute("SELECT synced, http_status, send_error FROM heartbeats").fetchone()
                self.assertEqual(row, (1, 202, ""))
                conn.close()
            finally:
                simulator.LOCAL_DB_PATH = original

    def test_sync_pending_records_keeps_rows_unsynced_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "node.db"
            original = simulator.LOCAL_DB_PATH
            simulator.LOCAL_DB_PATH = db_path
            try:
                conn = simulator.connect_db()
                simulator.store_heartbeat(
                    conn,
                    {"timestamp": "t1", "node_code": "n1", "status": "warning"},
                    {"synced": False, "request_id": "old-rid", "http_status": 503, "error": "central down"},
                )

                def fake_urlopen(request: urllib.request.Request, timeout: int):
                    raise urllib.error.HTTPError(request.full_url, 503, "down", {}, None)

                with patch.object(simulator.urllib.request, "urlopen", fake_urlopen):
                    result = simulator.sync_pending_records(conn)

                self.assertFalse(result["synced"])
                self.assertEqual(result["http_status"], 503)
                self.assertEqual(simulator.pending_record_count(conn), 1)
                conn.close()
            finally:
                simulator.LOCAL_DB_PATH = original

    def test_fetch_dispatch_clears_stale_local_dispatch_when_central_returns_empty(self) -> None:
        simulator.ACTIVE_DISPATCH = {"active_order": "WO-stale", "policy": "old"}

        class EmptyDispatchResponse(FakeResponse):
            body = b'{"dispatch": {}}'

        def fake_urlopen(request: urllib.request.Request, timeout: int):
            self.assertIn("/api/node-dispatches/", request.full_url)
            return EmptyDispatchResponse()

        with patch.object(simulator.urllib.request, "urlopen", fake_urlopen):
            simulator.fetch_dispatch()

        self.assertEqual(simulator.ACTIVE_DISPATCH, {})

    def test_heartbeat_payload_uses_central_dispatch_when_present(self) -> None:
        original = simulator.ACTIVE_DISPATCH
        simulator.ACTIVE_DISPATCH = {"active_order": "WO-central", "policy": "human_approved_reschedule"}
        try:
            payload = simulator.heartbeat_payload(simulator.PROFILES["milling"], 1)
        finally:
            simulator.ACTIVE_DISPATCH = original

        self.assertEqual(payload["production"]["active_order"], "WO-central")
        self.assertEqual(payload["production"]["dispatch_policy"], "human_approved_reschedule")

    def test_apply_set_target_rate_command_updates_heartbeat_target_rate(self) -> None:
        original_target = simulator.COMMAND_TARGET_RATE
        original_applied = set(simulator.APPLIED_COMMAND_IDS)
        simulator.COMMAND_TARGET_RATE = None
        simulator.APPLIED_COMMAND_IDS.clear()
        try:
            status, message = simulator.apply_agent_command({
                "id": 1001,
                "command_type": "set_target_rate",
                "parameters": {"target_rate": 0.72},
            })
            payload = simulator.heartbeat_payload(simulator.PROFILES["milling"], 1)
            repeated_status, repeated_message = simulator.apply_agent_command({
                "id": 1001,
                "command_type": "set_target_rate",
                "parameters": {"target_rate": 0.5},
            })
        finally:
            simulator.COMMAND_TARGET_RATE = original_target
            simulator.APPLIED_COMMAND_IDS.clear()
            simulator.APPLIED_COMMAND_IDS.update(original_applied)

        self.assertEqual(status, "executed")
        self.assertIn("0.72", message)
        self.assertEqual(payload["production"]["target_rate"], 0.72)
        self.assertEqual(repeated_status, "executed")
        self.assertIn("already applied", repeated_message)

    def test_apply_agent_command_rejects_unsupported_or_unsafe_commands(self) -> None:
        unsupported = simulator.apply_agent_command({"id": 2001, "command_type": "emergency_stop"})
        unsafe = simulator.apply_agent_command({
            "id": 2002,
            "command_type": "set_target_rate",
            "parameters": {"target_rate": 9},
        })

        self.assertEqual(unsupported[0], "failed")
        self.assertIn("unsupported", unsupported[1])
        self.assertEqual(unsafe[0], "failed")
        self.assertIn("safe range", unsafe[1])

    def test_poll_agent_commands_claims_applies_and_reports_result(self) -> None:
        original_target = simulator.COMMAND_TARGET_RATE
        original_applied = set(simulator.APPLIED_COMMAND_IDS)
        simulator.COMMAND_TARGET_RATE = None
        simulator.APPLIED_COMMAND_IDS.clear()
        captured: list[urllib.request.Request] = []

        class CommandListResponse(FakeResponse):
            body = b'[{"id": 3001, "command_type": "set_target_rate", "parameters": {"target_rate": 0.66}}]'

        class CommandResultResponse(FakeResponse):
            body = b'{"accepted": true, "status": "executed"}'

        def fake_urlopen(request: urllib.request.Request, timeout: int):
            captured.append(request)
            if "/commands/pending" in request.full_url:
                return CommandListResponse()
            if "/commands/3001/result" in request.full_url:
                body = request.data.decode("utf-8")
                self.assertIn('"status": "executed"', body)
                self.assertIn("set_target_rate applied", body)
                return CommandResultResponse()
            raise AssertionError(f"unexpected url {request.full_url}")

        applied_target = None
        try:
            with patch.object(simulator.urllib.request, "urlopen", fake_urlopen):
                simulator.poll_agent_commands()
            applied_target = simulator.COMMAND_TARGET_RATE
        finally:
            simulator.COMMAND_TARGET_RATE = original_target
            simulator.APPLIED_COMMAND_IDS.clear()
            simulator.APPLIED_COMMAND_IDS.update(original_applied)

        self.assertEqual(len(captured), 2)
        self.assertEqual(applied_target, 0.66)

    def test_part_queue_claim_and_complete_http_helpers(self) -> None:
        captured: list[urllib.request.Request] = []

        class ClaimResponse(FakeResponse):
            body = (
                b'{"claimed": true, "part": {"part_id": "PART-00001", '
                b'"order_id": "WO-1", "claim_token": "tok-1"}}'
            )

        class CompleteResponse(FakeResponse):
            body = b'{"accepted": true, "part": {"part_id": "PART-00001", "status": "completed"}}'

        def fake_urlopen(request: urllib.request.Request, timeout: int):
            captured.append(request)
            if "/parts/claim-next" in request.full_url:
                return ClaimResponse()
            if "/parts/PART-00001/complete" in request.full_url:
                self.assertIn('"claim_token": "tok-1"', request.data.decode("utf-8"))
                return CompleteResponse()
            raise AssertionError(f"unexpected url {request.full_url}")

        original_active = simulator.ACTIVE_PART
        try:
            with patch.object(simulator.urllib.request, "urlopen", fake_urlopen):
                claim = simulator.claim_next_part(ttl_seconds=60)
                simulator.ACTIVE_PART = dict(claim["part"])
                complete = simulator.complete_active_part()
        finally:
            simulator.ACTIVE_PART = original_active

        self.assertEqual(len(captured), 2)
        self.assertTrue(claim["claimed"])
        self.assertEqual(claim["part"]["part_id"], "PART-00001")
        self.assertTrue(complete["accepted"])

    def test_poll_part_queue_claims_then_completes_milling_part(self) -> None:
        captured: list[urllib.request.Request] = []

        class ClaimResponse(FakeResponse):
            body = (
                b'{"claimed": true, "part": {"part_id": "PART-00002", '
                b'"order_id": "WO-2", "claim_token": "tok-2"}}'
            )

        class CompleteResponse(FakeResponse):
            body = b'{"accepted": true, "part": {"part_id": "PART-00002", "status": "completed"}}'

        def fake_urlopen(request: urllib.request.Request, timeout: int):
            captured.append(request)
            if "/parts/claim-next" in request.full_url:
                return ClaimResponse()
            if "/parts/PART-00002/complete" in request.full_url:
                return CompleteResponse()
            raise AssertionError(f"unexpected url {request.full_url}")

        original_type = simulator.WORKSHOP_TYPE
        original_active = simulator.ACTIVE_PART
        simulator.WORKSHOP_TYPE = "milling"
        simulator.ACTIVE_PART = {}
        try:
            with patch.object(simulator.urllib.request, "urlopen", fake_urlopen):
                simulator.poll_part_queue(1)
                self.assertEqual(simulator.ACTIVE_PART["part_id"], "PART-00002")
                simulator.poll_part_queue(4)
                self.assertEqual(simulator.ACTIVE_PART, {})
        finally:
            simulator.WORKSHOP_TYPE = original_type
            simulator.ACTIVE_PART = original_active

        self.assertEqual(len(captured), 2)

    def test_poll_part_queue_also_runs_for_grinding_node(self) -> None:
        captured: list[urllib.request.Request] = []

        class ClaimResponse(FakeResponse):
            body = (
                b'{"claimed": true, "part": {"part_id": "PART-00004", '
                b'"order_id": "WO-4", "claim_token": "tok-4", "current_step": "grinding"}}'
            )

        def fake_urlopen(request: urllib.request.Request, timeout: int):
            captured.append(request)
            self.assertIn("/parts/claim-next", request.full_url)
            return ClaimResponse()

        original_type = simulator.WORKSHOP_TYPE
        original_code = simulator.NODE_CODE
        original_active = simulator.ACTIVE_PART
        simulator.WORKSHOP_TYPE = "grinding"
        simulator.NODE_CODE = "grinding-workshop-01"
        simulator.ACTIVE_PART = {}
        try:
            with patch.object(simulator.urllib.request, "urlopen", fake_urlopen):
                simulator.poll_part_queue(1)
                self.assertEqual(simulator.ACTIVE_PART["part_id"], "PART-00004")
                self.assertEqual(simulator.ACTIVE_PART["current_step"], "grinding")
        finally:
            simulator.WORKSHOP_TYPE = original_type
            simulator.NODE_CODE = original_code
            simulator.ACTIVE_PART = original_active

        self.assertEqual(len(captured), 1)

    def test_heartbeat_payload_prefers_active_part_order(self) -> None:
        original_active = simulator.ACTIVE_PART
        simulator.ACTIVE_PART = {"part_id": "PART-00003", "order_id": "WO-PART-ACTIVE"}
        try:
            payload = simulator.heartbeat_payload(simulator.PROFILES["milling"], 1)
        finally:
            simulator.ACTIVE_PART = original_active

        self.assertEqual(payload["production"]["active_order"], "WO-PART-ACTIVE")
        self.assertEqual(payload["production"]["active_part_id"], "PART-00003")

    def test_heartbeat_payload_includes_v2_runtime_and_flow_fields(self) -> None:
        original_session = simulator.OGAS_SESSION_TOKEN
        simulator.OGAS_SESSION_TOKEN = "pytest-session-token"
        try:
            payload = simulator.heartbeat_payload(simulator.PROFILES["grinding"], 3)
        finally:
            simulator.OGAS_SESSION_TOKEN = original_session

        runtime = payload["runtime"]
        production = payload["production"]

        self.assertEqual(payload["session_token"], "pytest-session-token")
        self.assertEqual(runtime["run_id"], simulator.RUN_ID)
        self.assertTrue(runtime["scenario_id"].startswith("SCN-"))
        self.assertEqual(runtime["simulation_speed"], simulator.SIMULATION_SPEED)
        self.assertEqual(runtime["simulation_engine"], simulator.SIMULATION_ENGINE)
        self.assertEqual(runtime["runtime_source"], "node-agent")
        self.assertIsInstance(datetime.fromisoformat(runtime["simulation_time"]), datetime)

        for field in ("wip_input", "wip_output"):
            self.assertIsInstance(production[field], int)
            self.assertGreaterEqual(production[field], 0)
        for field in ("target_rate", "actual_rate", "utilization", "defect_rate"):
            self.assertIsInstance(production[field], float)
            self.assertGreaterEqual(production[field], 0.0)
        self.assertLessEqual(production["utilization"], 1.0)
        self.assertLessEqual(production["defect_rate"], 1.0)

    def test_simpy_machine_state_is_deterministic_for_same_seed_and_scenario(self) -> None:
        first = simulator.simpy_machine_state(
            simulator.PROFILES["milling"],
            12,
            random_seed=42,
            scenario_id="SCN-NORMAL-MIXED-001",
        )
        second = simulator.simpy_machine_state(
            simulator.PROFILES["milling"],
            12,
            random_seed=42,
            scenario_id="SCN-NORMAL-MIXED-001",
        )

        self.assertEqual(first, second)
        self.assertEqual(first["status"], "running")
        self.assertEqual(first["alarms"], [])

    def test_simpy_machine_state_uses_scenario_to_create_distinct_faults(self) -> None:
        normal = simulator.simpy_machine_state(
            simulator.PROFILES["grinding"],
            12,
            random_seed=42,
            scenario_id="SCN-NORMAL-MIXED-001",
        )
        vibration = simulator.simpy_machine_state(
            simulator.PROFILES["grinding"],
            12,
            random_seed=42,
            scenario_id="SCN-GRINDING-VIBRATION-HIGH-001",
        )

        self.assertEqual(normal["status"], "running")
        self.assertEqual(vibration["status"], "fault")
        self.assertEqual(vibration["alarms"][0]["type"], "VIBRATION_HIGH")

    def test_heartbeat_payload_can_use_simpy_engine_without_changing_v2_schema(self) -> None:
        original_engine = simulator.SIMULATION_ENGINE
        original_scenario = simulator.SCENARIO_ID
        original_seed = simulator.SIMULATION_RANDOM_SEED
        simulator.SIMULATION_ENGINE = "simpy"
        simulator.SCENARIO_ID = "SCN-MILLING-COOLANT-LOW-001"
        simulator.SIMULATION_RANDOM_SEED = 99
        try:
            payload = simulator.heartbeat_payload(simulator.PROFILES["milling"], 12)
        finally:
            simulator.SIMULATION_ENGINE = original_engine
            simulator.SCENARIO_ID = original_scenario
            simulator.SIMULATION_RANDOM_SEED = original_seed

        self.assertEqual(payload["runtime"]["simulation_engine"], "simpy")
        self.assertEqual(payload["runtime"]["scenario_id"], "SCN-MILLING-COOLANT-LOW-001")
        self.assertEqual(payload["runtime"]["random_seed"], 99)
        self.assertIn("run_id", payload["runtime"])
        self.assertIn("actual_rate", payload["production"])
        self.assertEqual(payload["alarms"][0]["type"], "COOLANT_FLOW_LOW")

    def test_all_workshop_profiles_emit_simpy_flow_metrics(self) -> None:
        original_engine = simulator.SIMULATION_ENGINE
        original_scenario = simulator.SCENARIO_ID
        simulator.SIMULATION_ENGINE = "simpy"
        simulator.SCENARIO_ID = "SCN-NORMAL-MIXED-001"
        try:
            payloads = {
                name: simulator.heartbeat_payload(profile, 18)
                for name, profile in simulator.PROFILES.items()
            }
        finally:
            simulator.SIMULATION_ENGINE = original_engine
            simulator.SCENARIO_ID = original_scenario

        self.assertEqual(payloads["turning"]["production"]["machine_code"], "LATHE-01")
        self.assertEqual(payloads["milling"]["production"]["machine_code"], "MILL-02")
        self.assertEqual(payloads["grinding"]["production"]["machine_code"], "GRIND-01")
        for payload in payloads.values():
            self.assertEqual(payload["runtime"]["simulation_engine"], "simpy")
            self.assertGreaterEqual(payload["production"]["wip_input"], 0)
            self.assertGreaterEqual(payload["production"]["wip_output"], 0)
            self.assertGreater(payload["production"]["target_rate"], 0)
            self.assertGreaterEqual(payload["production"]["actual_rate"], 0)
            self.assertGreaterEqual(payload["production"]["utilization"], 0)
            self.assertLessEqual(payload["production"]["utilization"], 1)


if __name__ == "__main__":
    unittest.main()
