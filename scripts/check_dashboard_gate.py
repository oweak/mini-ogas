from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "services" / "dashboard" / "src"
APP_VUE = SRC_DIR / "App.vue"
STARTUP_GATE = SRC_DIR / "StartupGate.vue"
ALARM_MANAGEMENT_VIEW = SRC_DIR / "AlarmManagementView.vue"
LOG_MANAGEMENT_VIEW = SRC_DIR / "LogManagementView.vue"
ORDER_DISPATCH_VIEW = SRC_DIR / "OrderDispatchView.vue"
FACTORY_RUNTIME_VIEW = SRC_DIR / "FactoryRuntimeView.vue"
OPERATIONS_API = SRC_DIR / "operationsApi.ts"
PROTECTED_POLLING = SRC_DIR / "protectedPolling.ts"
ALARM_WORKFLOW = SRC_DIR / "useAlarmWorkflow.ts"
STARTUP_WORKFLOW = SRC_DIR / "useStartupWorkflow.ts"
RUNTIME_PRESENTATION = SRC_DIR / "useRuntimePresentation.ts"
STYLES = SRC_DIR / "styles.css"

PROTECTED_FETCHERS = ("loadDashboardState(", "fetchAlarmData(", "fetchAuditEvents(")


def block_between(text: str, start: str, end: str) -> str:
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    return text[start_index:end_index]


def assert_presentational(path: Path, name: str) -> str:
    text = path.read_text(encoding="utf-8")
    if "apiFetch" in text or "/api/" in text:
        raise SystemExit(f"frontend boundary violation: {name} must stay presentational and must not call APIs directly")
    return text


def main() -> None:
    text = APP_VUE.read_text(encoding="utf-8")
    if 'v-else-if="false"' in text or 'v-if="false"' in text:
        raise SystemExit("dead template violation: App.vue must not keep unreachable legacy template branches")

    template = text[text.index("<template>") :]
    if ':class="{ locked: loginRequired }"' not in template:
        raise SystemExit("startup gate violation: shell must expose locked state while login is required")
    startup_index = template.index("<StartupGate")
    locked_content_index = template.index('<template v-if="!loginRequired">')
    if 'v-if="loginRequired"' not in template[startup_index:locked_content_index]:
        raise SystemExit("startup gate violation: StartupGate must be controlled by loginRequired")
    if startup_index > locked_content_index:
        raise SystemExit("startup gate violation: StartupGate must appear before the protected console content")
    protected_content = template[locked_content_index:]
    protected_markers = ("<header class=\"topbar\">", "<FactoryRuntimeView", "<OrderDispatchView", "<LogManagementView", "<AlarmManagementView")
    missing_protected_markers = [marker for marker in protected_markers if marker not in protected_content]
    if missing_protected_markers:
        raise SystemExit(f"startup gate violation: protected console content must stay inside !loginRequired block: {missing_protected_markers}")

    styles = STYLES.read_text(encoding="utf-8")
    locked_sidebar_block = block_between(styles, ".shell.locked .sidebar", "}\n")
    if "display: none" not in locked_sidebar_block:
        raise SystemExit("startup gate violation: locked shell must hide the sidebar before login")

    mounted = block_between(text, "onMounted(() => {", "})\n\nwatch(systemUnlocked")
    violations = [name for name in PROTECTED_FETCHERS if name in mounted]
    if violations:
        raise SystemExit(f"login gate violation: onMounted calls protected fetchers before login: {violations}")

    watcher = block_between(text, "watch(systemUnlocked", "watch(activeIssuePopups")
    if "startRuntimePolling()" not in watcher or "refreshProtectedData()" not in watcher:
        raise SystemExit("login gate violation: systemUnlocked watcher does not start protected data flow")
    if "stopRuntimePolling()" not in watcher:
        raise SystemExit("login gate violation: systemUnlocked watcher does not stop protected polling when locked")

    issue_popup_block = block_between(text, "const activeIssuePopups = computed", "function uniqueIssues")
    if "fallbackIssues" in issue_popup_block or "demoMode.value === 'emergency'" in issue_popup_block:
        raise SystemExit("live data violation: real issue popups must not be generated from demo emergency fallback data")
    if "ISSUE-SPINDLE-TEMP" in text:
        raise SystemExit("live data violation: management logic must not depend on the old static ISSUE-SPINDLE-TEMP id")

    heartbeat_log_block = block_between(text, "function appendBackendHeartbeatLog", "const { refreshProtectedData")
    if "liveOutput" in heartbeat_log_block or "liveTemp" in heartbeat_log_block or "pendingRecords" in heartbeat_log_block:
        raise SystemExit("live data violation: heartbeat logs must use backend node heartbeats, not synthetic demo metrics")

    audit_fetch_block = block_between(text, "async function fetchAuditEvents", "async function fetchAlarmData")
    forbidden_clears = ("hostNodes.value = []", "hostWorkOrders.value = []", "apiIssues.value = []")
    found_clears = [marker for marker in forbidden_clears if marker in audit_fetch_block]
    if found_clears:
        raise SystemExit(f"module isolation violation: audit log failure must not clear live runtime state: {found_clears}")
    audit_catch_block = block_between(audit_fetch_block, "} catch", "}\n")
    if "apiAvailable.value = false" in audit_catch_block:
        raise SystemExit("module isolation violation: audit log failure must not mark the whole central-api connection offline")

    alarm_fetch_block = block_between(text, "async function fetchAlarmData", "async function loadDashboardState")
    if "responseToFetchSlot" not in alarm_fetch_block:
        raise SystemExit("partial fetch violation: alarm refresh must preserve successful endpoint data via responseToFetchSlot")

    if "useAlarmWorkflow({" not in text:
        raise SystemExit("alarm lifecycle violation: App.vue must delegate alarm actions to useAlarmWorkflow")
    if "useStartupWorkflow({" not in text:
        raise SystemExit("startup gate violation: App.vue must delegate startup/login actions to useStartupWorkflow")
    if "useRuntimePresentation({" not in text:
        raise SystemExit("runtime presentation violation: App.vue must delegate backend runtime presentation to useRuntimePresentation")

    alarm_workflow_text = ALARM_WORKFLOW.read_text(encoding="utf-8")
    required_lifecycle_markers = (
        "const diagnose = status === 'confirmed'",
        "const close = status === 'contained' || status === 'observing'",
        "const escalate = status === 'confirmed' || status === 'diagnosed' || status === 'observing'",
    )
    missing_lifecycle_markers = [marker for marker in required_lifecycle_markers if marker not in alarm_workflow_text]
    if missing_lifecycle_markers:
        raise SystemExit(f"alarm lifecycle violation: frontend actions must enforce confirm -> diagnose -> decide/execute -> close: {missing_lifecycle_markers}")

    alarm_view_text = assert_presentational(ALARM_MANAGEMENT_VIEW, "AlarmManagementView")
    required_ai_markers = ("真实模型 API", "规则回退", "latestDiagnosisForSelected.evidence", "latestDiagnosisForSelected.options")
    missing_ai_markers = [marker for marker in required_ai_markers if marker not in alarm_view_text]
    if missing_ai_markers:
        raise SystemExit(f"AI truth violation: alarm detail must expose AI source, evidence, and options: {missing_ai_markers}")

    startup_workflow_text = STARTUP_WORKFLOW.read_text(encoding="utf-8")
    startup_markers = (
        "/api/system/preflight",
        "/api/auth/login",
        "AI 接口已验证",
        "真实 API 已验证",
        "未确认真实模型调用",
        "systemUnlocked.value = true",
        "soundArmed.value = true",
    )
    missing_startup_markers = [marker for marker in startup_markers if marker not in startup_workflow_text]
    if missing_startup_markers:
        raise SystemExit(f"startup gate violation: startup workflow must keep preflight, login, unlock, and AI smoke proof: {missing_startup_markers}")

    runtime_presentation_text = RUNTIME_PRESENTATION.read_text(encoding="utf-8")
    runtime_markers = (
        "options.hostNodes.value",
        "options.hostWorkOrders.value",
        "options.aiSmokeTruth.value",
        "deployment_mode",
        "解决后的问题必须从队列消失并进入日志",
    )
    missing_runtime_markers = [marker for marker in runtime_markers if marker not in runtime_presentation_text]
    if missing_runtime_markers:
        raise SystemExit(f"runtime presentation violation: backend/VM/AI runtime presentation markers missing: {missing_runtime_markers}")

    deprecated_virtualbox_markers = (
        "Virtual" + "BoxState",
        "virtual" + "BoxState",
        "virtual" + "box",
        "vm" + "_name",
        "vm" + "_running",
    )
    found_virtualbox_markers = [marker for marker in deprecated_virtualbox_markers if marker in text or marker in runtime_presentation_text]
    if found_virtualbox_markers:
        raise SystemExit(f"VirtualBox residue violation: {found_virtualbox_markers}")

    smoke_markers = ("aiSmokeTruth",)
    factory_smoke_markers = ("AI 调用证明", "真实模型", "未证明真实模型调用")
    factory_text = assert_presentational(FACTORY_RUNTIME_VIEW, "FactoryRuntimeView")
    missing_smoke_markers = [marker for marker in smoke_markers if marker not in text] + [
        marker for marker in factory_smoke_markers if marker not in factory_text
    ]
    if missing_smoke_markers:
        raise SystemExit(f"AI truth violation: dashboard must keep visible AI smoke/runtime proof: {missing_smoke_markers}")
    assert_presentational(STARTUP_GATE, "StartupGate")
    assert_presentational(LOG_MANAGEMENT_VIEW, "LogManagementView")
    assert_presentational(ORDER_DISPATCH_VIEW, "OrderDispatchView")
    factory_forbidden_demo_markers = ("liveOutput", "liveTemp", "pendingRecords", "demoMode", "demoScenario")
    found_factory_demo_markers = [marker for marker in factory_forbidden_demo_markers if marker in factory_text]
    if found_factory_demo_markers:
        raise SystemExit(f"live data violation: FactoryRuntimeView must render parent/backend state, not demo metrics: {found_factory_demo_markers}")

    operations_text = OPERATIONS_API.read_text(encoding="utf-8")
    required_operation_routes = (
        "/api/alerts/",
        "/confirm",
        "/api/nodes/",
        "/isolate",
        "/api/issues/",
        "/actions",
        "/api/ops/escalate",
        "/api/ops/escalations/",
        "/decision",
    )
    missing_operation_routes = [marker for marker in required_operation_routes if marker not in operations_text]
    if missing_operation_routes:
        raise SystemExit(f"frontend/backend contract violation: operationsApi is missing required concrete routes: {missing_operation_routes}")
    if "/api/ops/issue-command" in operations_text:
        raise SystemExit("frontend/backend contract violation: node isolation must use the concrete /api/nodes/{code}/isolate route, not NL issue-command routing")

    polling_text = PROTECTED_POLLING.read_text(encoding="utf-8")
    if "apiFetch" in polling_text or "/api/" in polling_text:
        raise SystemExit("login gate violation: protectedPolling must receive callbacks and must not call APIs directly")
    if "if (!options.systemUnlocked.value) return" not in polling_text:
        raise SystemExit("login gate violation: protectedPolling refresh is not guarded by systemUnlocked")

    print("dashboard login gate check passed")


if __name__ == "__main__":
    main()
