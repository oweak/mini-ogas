import unittest
from types import SimpleNamespace

import kali_redteam_workflow as workflow


class KaliRedteamWorkflowTests(unittest.TestCase):
    def test_builds_distinct_realistic_scenarios(self) -> None:
        expected = {
            "spindle_overheat": "SPINDLE_TEMP_HIGH",
            "quality_drift": "QUALITY_DRIFT",
            "tool_wear": "TOOL_WEAR_WARNING",
            "vibration": "VIBRATION_HIGH",
            "coolant_flow": "COOLANT_FLOW_LOW",
        }

        for scenario, alarm_type in expected.items():
            with self.subTest(scenario=scenario):
                heartbeat = workflow.build_attack_heartbeat(scenario=scenario, attack_id="KALI-UNIT")
                self.assertEqual(heartbeat["alarms"][0]["type"], alarm_type)
                self.assertEqual(heartbeat["runtime"]["source"], "kali-redteam")
                self.assertEqual(heartbeat["runtime"]["attack_id"], "KALI-UNIT")
                self.assertEqual(heartbeat["runtime"]["run_id"], "RUN-ATTACK-LAB-KALI-UNIT")
                self.assertTrue(heartbeat["runtime"]["scenario_id"].startswith("SCN-ATTACK-LAB-"))
                self.assertEqual(heartbeat["runtime"]["run_status"], "running")
                self.assertIsInstance(heartbeat["runtime"]["random_seed"], int)

    def test_recovery_heartbeat_removes_alarm_and_restores_running_state(self) -> None:
        attack = workflow.build_attack_heartbeat(scenario="tool_wear", attack_id="KALI-UNIT")

        recovery = workflow.build_recovery_heartbeat(attack)

        self.assertEqual(recovery["status"], "running")
        self.assertEqual(recovery["alarms"], [])
        self.assertLessEqual(recovery["production"]["tool_wear_level"], 58.0)
        self.assertEqual(recovery["runtime"]["recovery"], "script-restored-process-window")
        self.assertEqual(recovery["runtime"]["run_status"], "completed")
        self.assertEqual(recovery["runtime"]["run_id"], attack["runtime"]["run_id"])

    def test_select_alert_accepts_issue_id_or_id(self) -> None:
        alert = {"id": "node-a-QUALITY_DRIFT", "issue_id": "node-a-QUALITY_DRIFT"}

        self.assertIs(workflow.select_alert([alert], "node-a-QUALITY_DRIFT"), alert)
        self.assertIsNone(workflow.select_alert([alert], "node-a-SPINDLE_TEMP_HIGH"))

    def test_live_ai_runtime_rejects_rule_fallback_by_default(self) -> None:
        original_request = workflow.request
        workflow.request = lambda *args, **kwargs: {
            "runtime": {
                "status": "locked",
                "source": "rule_fallback",
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
            }
        }
        try:
            args = SimpleNamespace(api_url="http://127.0.0.1:8080", allow_rule_fallback=False)
            with self.assertRaisesRegex(RuntimeError, "not using a live API"):
                workflow.require_live_ai_runtime(args, "token")
        finally:
            workflow.request = original_request

    def test_live_ai_runtime_allows_explicit_rule_fallback_dry_run(self) -> None:
        original_request = workflow.request
        workflow.request = lambda *args, **kwargs: {
            "runtime": {"status": "locked", "source": "rule_fallback"}
        }
        try:
            args = SimpleNamespace(api_url="http://127.0.0.1:8080", allow_rule_fallback=True)
            runtime = workflow.require_live_ai_runtime(args, "token")
            self.assertEqual(runtime["source"], "rule_fallback")
        finally:
            workflow.request = original_request

    def test_extract_decision_source_prefers_nested_decision(self) -> None:
        self.assertEqual(workflow.extract_decision_source({"decision": {"source": "api"}}), "api")
        self.assertEqual(workflow.extract_decision_source({"source": "rule_fallback"}), "rule_fallback")

    def test_lab_boundary_requires_explicit_acknowledgement(self) -> None:
        args = SimpleNamespace(
            api_url="http://127.0.0.1:8080",
            i_understand_this_is_a_lab=False,
            allow_remote_lab=False,
        )

        with self.assertRaisesRegex(RuntimeError, "explicit lab acknowledgement"):
            workflow.require_lab_boundary(args)

    def test_lab_boundary_rejects_public_targets_by_default(self) -> None:
        args = SimpleNamespace(
            api_url="https://example.com",
            i_understand_this_is_a_lab=True,
            allow_remote_lab=False,
        )

        with self.assertRaisesRegex(RuntimeError, "non-private API URL"):
            workflow.require_lab_boundary(args)

    def test_lab_manifest_documents_non_destructive_scope(self) -> None:
        args = SimpleNamespace(
            api_url="http://127.0.0.1:8080",
            scenario="spindle_overheat",
            mode="full",
            operator="tester",
            i_understand_this_is_a_lab=True,
            allow_remote_lab=False,
        )

        manifest = workflow.build_lab_manifest(args)

        self.assertTrue(manifest["lab_only"])
        self.assertIn("Does not exploit hosts", " ".join(manifest["boundaries"]))
        self.assertIn("Kali/VirtualBox state", " ".join(manifest["boundaries"]))

    def test_login_bearer_uses_admin_password_without_node_token(self) -> None:
        calls = []
        original_request = workflow.request

        def fake_request(*args, **kwargs):
            calls.append((args, kwargs))
            return {"access_token": "bearer-test-token"}

        workflow.request = fake_request
        try:
            args = SimpleNamespace(
                api_url="http://127.0.0.1:8080",
                bearer_token="",
                admin_password="secret",
                auth_env_file="",
                operator="admin",
            )
            token = workflow.login_bearer(args)
        finally:
            workflow.request = original_request

        self.assertEqual(token, "bearer-test-token")
        self.assertEqual(calls[0][1]["auth_mode"], "none")
        self.assertEqual(calls[0][1]["body"]["password"], "secret")

    def test_full_workflow_skips_isolation_for_low_risk_api_diagnosis(self) -> None:
        calls = []
        original_request = workflow.request
        original_login = workflow.login_bearer

        def fake_login(args):
            return "bearer-test-token"

        def fake_request(method, path, **kwargs):
            calls.append((method, path, kwargs.get("auth_mode")))
            if path == "/api/auth/status":
                return {"runtime": {"status": "live", "source": "api", "provider": "deepseek"}}
            if path == "/api/node-heartbeats":
                return {"ok": True, "accepted": True}
            if path == "/api/alerts":
                return [{"issue_id": "milling-workshop-01-COOLANT_FLOW_LOW"}]
            if path.endswith("/confirm"):
                return {"ok": True}
            if path.startswith("/api/ai/diagnose/"):
                return {
                    "ok": True,
                    "source": "api",
                    "need_isolation": False,
                    "decision": {"risk_level": "low"},
                }
            if path.endswith("/actions"):
                return {"ok": True}
            if path == "/api/audit/events":
                return []
            if path == "/api/dashboard-state":
                return {"log_events": []}
            raise AssertionError(f"unexpected request: {method} {path}")

        workflow.login_bearer = fake_login
        workflow.request = fake_request
        try:
            args = SimpleNamespace(
                api_url="http://127.0.0.1:8080",
                scenario="coolant_flow",
                node_code="",
                machine_code="",
                attack_id="KALI-UNIT",
                issue_id="",
                operator="tester",
                allow_rule_fallback=False,
                i_understand_this_is_a_lab=True,
                allow_remote_lab=False,
                auto_approve_high_risk=False,
                mode="full",
            )
            result = workflow.full_workflow(args, "node-token")
        finally:
            workflow.request = original_request
            workflow.login_bearer = original_login

        self.assertTrue(result["steps"]["isolate"]["skipped"])
        self.assertFalse(any(path.endswith("/isolate") for _, path, _ in calls))

    def test_full_workflow_holds_high_risk_without_explicit_auto_approval(self) -> None:
        calls = []
        original_request = workflow.request
        original_login = workflow.login_bearer

        workflow.login_bearer = lambda args: "bearer-test-token"

        def fake_request(method, path, **kwargs):
            calls.append((method, path, kwargs.get("auth_mode")))
            if path == "/api/auth/status":
                return {"runtime": {"status": "live", "source": "api", "provider": "deepseek"}}
            if path == "/api/node-heartbeats":
                return {"ok": True, "accepted": True}
            if path == "/api/alerts":
                return [{"issue_id": "milling-workshop-01-SPINDLE_TEMP_HIGH"}]
            if path.endswith("/confirm"):
                return {"ok": True}
            if path.startswith("/api/ai/diagnose/"):
                return {
                    "ok": True,
                    "source": "api",
                    "need_isolation": True,
                    "decision": {"risk_level": "high"},
                }
            raise AssertionError(f"unexpected request: {method} {path}")

        workflow.request = fake_request
        try:
            args = SimpleNamespace(
                api_url="http://127.0.0.1:8080",
                scenario="spindle_overheat",
                node_code="",
                machine_code="",
                attack_id="KALI-UNIT",
                issue_id="",
                operator="tester",
                allow_rule_fallback=False,
                i_understand_this_is_a_lab=True,
                allow_remote_lab=False,
                auto_approve_high_risk=False,
                mode="full",
            )
            result = workflow.full_workflow(args, "node-token")
        finally:
            workflow.request = original_request
            workflow.login_bearer = original_login

        self.assertEqual(result["status"], "waiting_human_approval")
        self.assertTrue(result["steps"]["isolate"]["skipped"])
        self.assertFalse(any(path.endswith("/isolate") for _, path, _ in calls))


if __name__ == "__main__":
    unittest.main()
