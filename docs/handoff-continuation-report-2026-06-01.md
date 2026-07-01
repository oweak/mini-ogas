# Mini-OGAS Full-Stack Continuation Report

Date: 2026-06-01

This report is written as a handoff document for the next engineer or agent. It records what has actually been changed and verified, what is still incomplete, and how the remaining work should be continued without pretending the system is finished.

## 1. Current Objective

The real objective is not to make a static demo look plausible. The system must become a real full-stack industrial management system:

- Frontend views and buttons must be backed by real backend routes.
- Backend state must reflect live parent/child node operation.
- VM or child-node simulation must produce actual heartbeats and production/fault data.
- Alerts must follow a real lifecycle: open, confirmed, diagnosed, contained or observed, approved when required, executed, verified, closed, and archived.
- AI participation must be honest: if the AI vault is locked or the external model is unavailable, the UI and verification must say rule fallback is being used.
- Resolved issues must disappear from the active alarm queue and move into log/audit management.
- The system must not claim VM deployment or AI operation unless runtime checks prove it.

## 2. Work Already Done

### 2.1 Runtime and VM Verification

The deployment scripts now support checking the actual Mini-OGAS VirtualBox lab under `D:\MiniOGAS-VMs`.

Verified in the current session:

- `miniogas-turning` is registered and running.
- `miniogas-milling` is registered and running.
- `miniogas-grinding` is registered and running.
- `central-api /health` reports 3 expected nodes and 3 connected nodes.
- Protected `/api/dashboard-state?mode=normal` shows live node data.
- Protected `/api/alerts` responds and currently reports 0 active alerts.

Important caveat: this proves the current local machine was running the VMs at the time of the check. It does not mean the system is permanently correct. Future verification must always re-check the current runtime state.

### 2.2 Frontend and Backend API Alignment

Several earlier frontend/backend breaks have been repaired:

- Frontend calls to `/api/issues/{issue_id}/actions` now have a matching backend route.
- Node isolation now uses the direct backend route `/api/nodes/{node_code}/isolate`.
- Alert confirmation uses `/api/alerts/{issue_id}/confirm`.
- AI diagnosis uses `/api/ai/diagnose/{issue_id}`.
- Human escalation decisions use `/api/ops/escalations/{id}/decision`.
- Dispatch recalculation and approval use concrete dispatch-plan routes.
- A route contract checker was added and currently verifies 24 backend routes against 18 frontend API calls.

The route contract checker is `scripts/check_api_contract.py`.

### 2.3 Login Gate and Startup Self-Check

The dashboard now has a login/startup gate:

- Protected polling is delayed until `systemUnlocked` is true.
- Login/preflight can call only public endpoints before authentication.
- The dashboard gate checker verifies that protected business endpoints are not called before login.
- Startup self-check covers central API, parent/child nodes, AI runtime, rules, and dispatch/log modules.

Related files:

- `services/dashboard/src/StartupGate.vue`
- `services/dashboard/src/protectedPolling.ts`
- `scripts/check_dashboard_gate.py`

### 2.4 Alert Lifecycle and Human Management Flow

The backend now supports a much more realistic alert workflow:

- Alert creation from node heartbeat.
- Alert confirmation.
- AI diagnosis.
- Human approval queue.
- High-risk action confirmation code.
- Human approval/rejection.
- Resolution effects.
- Alert removal from active queue.
- Audit archival.
- Operator notification acknowledgement.

This flow is covered by `scripts/check_runtime_workflow.py`, which verifies:

1. Fault heartbeat is accepted.
2. Visible alert is created.
3. Alert moves to confirmed.
4. AI diagnosis is executed.
5. High-risk diagnosis requires human approval.
6. Approval item appears in the escalation queue.
7. Missing `CONFIRM` is rejected for high-risk approval.
8. Human approval closes the issue.
9. Closed issue disappears from active alerts.
10. Closed issue disappears from escalation queue.
11. Audit event is written.
12. Result notification appears.
13. Notification acknowledgement removes it.

### 2.5 Dispatch Plan Approval

Dispatch plan recalculation and approval now have backend routes and frontend controls:

- `/api/ops/dispatch-plan/recalculate`
- `/api/ops/dispatch-plan/approve`

The approval path requires confirmation and writes audit/result state.

### 2.6 Node Offline Record Archival

The node-agent offline replay path has been connected to log management instead of remaining as invisible backend state.

Completed and verified on 2026-06-02:

- `/api/node-records/sync` accepts local child-node records and stores them in `node_sync_records`.
- The sync endpoint now also creates a standard audit event with source `node-sync`.
- `/api/dashboard-state` exposes recent `node_sync_records` so the dashboard can show child-node replay history.
- The dashboard log management page shows node-sync audit rows and a dedicated recent child-node sync archive block.
- The backend test verifies that offline sync archives the old records without replacing the live node heartbeat.
- Full verification passed after the change, including backend tests, dashboard tests, dashboard build, runtime checks, and runtime alert workflow.
- The old static `ISSUE-SPINDLE-TEMP` frontend branch was removed. Emergency guidance now opens based on the real backend issue text, alarm type, title, or selected action instead of a demo-only issue id.
- `scripts/check_dashboard_gate.py` now fails if that static issue id is reintroduced into management logic.
- `/api/auth/login` rate limiting now returns HTTP 429 after repeated failed attempts instead of a soft 200 response with `ok: false`.
- The dashboard no longer clears live node, work-order, VM, or alert state when only `/api/audit/events` fails. Audit/log failure is treated as a log-module outage, not as proof that the whole factory runtime vanished.
- `scripts/check_dashboard_gate.py` now fails if the audit fetch path reintroduces cross-module state clearing.
- Log management was extracted from `App.vue` into `services/dashboard/src/LogManagementView.vue`. The component is presentational only: it receives `auditEvents` and `nodeSyncRecords` from the parent and emits `refresh`; it does not call `apiFetch` or any `/api/` route directly.
- Shared log/archive types now live in `services/dashboard/src/types.ts`, reducing local type duplication in `App.vue`.
- Alarm management was extracted from `App.vue` into `services/dashboard/src/AlarmManagementView.vue`. The component is also presentational only: it receives alarm, diagnosis, escalation, and loading state from the parent and emits semantic actions such as confirm, diagnose, isolate, observe, ignore, close, and escalation decision.
- `scripts/check_dashboard_gate.py` now asserts that `AlarmManagementView`, `LogManagementView`, `StartupGate`, and `protectedPolling` do not call APIs directly. Backend operations remain centralized in `App.vue` and `operationsApi.ts`, where route contract checks can verify them.
- `App.vue` was reduced to 2048 lines after the alarm/log extractions. It is still too large, but the direction is now toward smaller bounded views instead of a single all-powerful frontend file.
- Work-order dispatch was extracted from `App.vue` into `services/dashboard/src/OrderDispatchView.vue`. The component receives backend work orders and dispatch-plan state from the parent and emits `recalculate`, `approve`, and confirmation-code updates. It does not call APIs directly.
- Shared dispatch DTO types now live in `services/dashboard/src/types.ts` (`HostWorkOrder`, `DispatchPlan`, and `DisplayedWorkOrder`). This keeps backend DTO assumptions explicit instead of scattering them through the main view.
- `scripts/check_dashboard_gate.py` now also asserts that `OrderDispatchView` is presentational. `App.vue` is down to 1949 lines after the log, alarm, and dispatch extractions.

Important behavior: synced offline records are archival history. They must not be replayed into `/api/node-heartbeats`, because doing that would allow an old fault snapshot to overwrite the real current machine state.

### 2.7 Security Improvements

Security work already completed:

- The backend no longer silently accepts a missing API token for protected endpoints.
- Request body size limiting was added.
- Request IDs are attached to responses and logs.
- A secret scanner was added.
- The known default token is detected by hash instead of being spread as plaintext in backend config.
- The frontend token is no longer hardcoded in multiple request sites; it is loaded through the API client/login flow.
- `@vitejs/plugin-vue` is in `devDependencies`, not production dependencies.

Related files:

- `services/central-api/config.py`
- `scripts/check_secrets.py`
- `services/dashboard/src/apiClient.ts`

### 2.8 Backend Configuration Extraction

Some configuration was extracted from the central API monolith:

- Public paths.
- Static open prefixes.
- CORS origins.
- Expected nodes.
- API token.
- Request body limit.
- Heartbeat timeout.
- AI vault path.
- VirtualBox paths.
- Dashboard dist path.

Related file:

- `services/central-api/config.py`

Tests added:

- `services/central-api/test_config.py`

### 2.9 Testing and Verification

The full verification script currently runs:

- API contract check.
- Dashboard login gate check.
- Secret scan.
- central-api tests.
- central-api config tests.
- node-agent tests.
- dashboard tests.
- dashboard production build.
- full-stack runtime check.
- runtime alert workflow check.

Most recent successful full verification:

- Backend route/frontend API contract: passed.
- Dashboard gate: passed.
- Secret scan: passed.
- central-api tests: 19 passed.
- central-api config tests: 3 passed.
- node-agent tests: 5 passed.
- dashboard tests: 26 passed.
- dashboard build: passed.
- Runtime VM/node check: passed with 3/3 expected nodes.
- Runtime alert workflow: passed.

Command:

```powershell
C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

## 3. Honest Current State

### 3.1 The System Is Not Complete

The system is better than a static demo now, because live VM status, protected backend state, node heartbeats, alert handling, dispatch handling, and audit archival are all verified by scripts.

However, it is not yet complete enough to claim the full objective is achieved.

### 3.2 AI Is Not Currently Proved Live

The current runtime check reports:

- AI vault: present.
- AI runtime status: locked.
- AI source: `rule_fallback`.

That means real DeepSeek/OpenAI-compatible model calls are not currently active until administrator login unlocks the vault and a smoke call succeeds.

Do not claim real AI participation unless runtime evidence shows `vault_unlocked: true` and the AI smoke test succeeds.

### 3.3 The Backend Is Still Too Monolithic

`services/central-api/main.py` is still very large. It still mixes:

- HTTP routes.
- In-memory state.
- simulation/heartbeat handling.
- alert lifecycle.
- dispatch policy.
- AI diagnosis.
- audit logging.
- VirtualBox status.
- dashboard static mounting.

Some configuration has been extracted, but the core MemoryStore/central API monolith problem remains.

### 3.4 The Frontend Is Still Too Monolithic

`services/dashboard/src/App.vue` is still very large. It has extracted:

- `StartupGate.vue`
- `protectedPolling.ts`
- API helper modules.
- runtime/sound/verification helpers.

But the main dashboard, alarm page, order page, log page, demo page, and much of the operational logic still live in one component.

### 3.5 Static Demo Data Still Exists

`services/dashboard/src/data.ts` still contains static demo scenario data. Some of this is acceptable only for the isolated demo page. It must not leak into the real management pages as if it were live factory state.

The next engineer must audit all uses of `demoScenario`, `runtimeTick`, `liveOutput`, `liveTemp`, `pendingRecords`, and `activeIssuePopups` to ensure the real system views use backend state only.

### 3.6 Node Agent Is Python, Not Go

The current repository contains a Python node agent:

- `services/node-agent/simulator.py`

No Go node-agent source is present in the current worktree. Therefore the original Go-specific items cannot be fixed directly in this repository unless a Go agent is reintroduced or located elsewhere.

The Python agent already has:

- JSON structured logs.
- SQLite local heartbeat persistence.
- request IDs.
- token requirement.
- live dispatch fetch.
- multiple fault types.

But it still needs more hardening, especially around retries, graceful shutdown, and stronger proof that VM processes are the source of heartbeats.

## 4. Remaining Required Work

### 4.1 Prove Runtime Source More Strongly

Current checks verify:

- VMs are running.
- dashboard-state has nodes.
- node runtime reports `deployment_mode: virtualbox`.
- heartbeats are recent.

Next improvement:

- Add per-node heartbeat freshness to the UI, not just the verification script.
- Display VM name, VM running status, heartbeat age, host, PID, and deployment mode together in the node tree.
- Backend `/health` should include per-node heartbeat age and last request ID.
- Runtime verification should fail if a VM is running but its node heartbeat is absent or stale.
- Runtime verification should fail if heartbeats claim `virtualbox` while VirtualBox does not show the matching VM running.

### 4.2 Remove Static Fallback From Real Management Views

The real factory, order, alarm, and log pages should not invent operational data when backend data is missing.

Needed changes:

- Keep `demoScenario` only inside the isolated demo page.
- Make active system alert popups derive from backend `issues` and `notifications` only.
- When backend is unavailable, show offline/degraded management state instead of static factory values.
- Add a dashboard gate test proving real management views do not import or render static `workshops`, `workOrders`, or `alarms`.

### 4.3 Split Frontend Modules

Recommended extraction order:

1. `AlarmManagement.vue`
2. `DispatchPanel.vue`
3. `NodeTree.vue`
4. `LogManagement.vue`
5. `DemoCommandPage.vue`
6. `useDashboardState.ts`
7. `useAlarmWorkflow.ts`
8. `useDispatchWorkflow.ts`

This should be done carefully, with tests after each extraction, because `App.vue` currently holds many shared refs and computed values.

### 4.4 Split Backend Modules

Recommended extraction order:

1. `settings/config.py` or keep current `config.py`.
2. `auth.py` for token guard, login throttling, AI vault unlock.
3. `models.py` for Pydantic models.
4. `state.py` for in-memory store.
5. `alerts.py` for lifecycle and issue normalization.
6. `dispatch.py` for work-order and dispatch policy.
7. `ai_runtime.py` for diagnosis and model calls.
8. `audit.py` for logs and archive events.
9. `virtualbox.py` for VM status.
10. `routes/*.py` for FastAPI routers.

Important: do not split blindly. First add tests around the behavior, then move one boundary at a time.

### 4.5 Strengthen AI Truthfulness

Needed changes:

- Add a visible AI runtime panel showing `locked`, `rule_fallback`, or `live_model`.
- Store each AI decision with `source`, `provider`, `model`, confidence, prompt summary, and whether it was a fallback.
- The alarm detail page should show exactly what AI diagnosed, what data it used, and why human approval is required.
- Add a test where AI vault is locked and UI/backend clearly report fallback.
- Add a test where AI vault is unlocked only if a safe mock OpenAI-compatible endpoint is configured.

### 4.6 Complete Human Workflow UI

The core backend workflow exists, but the UI should become clearer:

- The alert detail should show the current lifecycle step.
- Buttons should be enabled/disabled according to lifecycle, not always shown equally.
- `确认报警` should only move open to confirmed.
- `AI 诊断` should be primary after confirmed.
- `隔离节点`, `观察`, `忽略`, and `升级人工` should appear as decision options after diagnosis.
- High-risk actions should visibly require approval and `CONFIRM`.
- After close, the alert must disappear and the result must appear in log management.

### 4.7 Improve Log Management

Log management should become a first-class screen:

- Show audit events, HTTP request logs, AI decisions, dispatch approvals, and operator actions separately.
- Filter by node, severity, actor, permission, issue ID, source, and time.
- Include processing person, permission, issue, result, node, severity, source, and effect.
- Add export to JSON/CSV if needed.

### 4.8 Improve Node Agent

For the current Python agent:

- Add graceful shutdown handling.
- Add retry backoff.
- Add resend of unsynced SQLite heartbeats.
- Add endpoint health check before main loop.
- Persist dispatch changes locally.
- Add stronger tests for fault diversity and dispatch alignment.
- Add a VM identity field so the backend can match `miniogas-turning` to `turning-workshop-01`.

If a Go agent appears later, apply the original Go-specific checklist separately.

### 4.9 More Tests

Needed additional coverage:

- Middleware auth and request body size tests.
- Login rate-limit tests.
- Health degradation tests when heartbeats are stale.
- Alert lifecycle route tests.
- Dispatch approval route tests.
- Frontend component tests for the alarm workflow.
- Frontend tests for hidden/disabled controls by lifecycle.
- Node-agent retry and local persistence tests.
- Full-stack test for stopping one VM and verifying degraded state.

## 5. Recommended Next Work Order

The next engineer should continue in this order:

1. Add a stronger runtime proof connecting each VM to its node heartbeat.
2. Remove or quarantine static fallback data from real management pages.
3. Add a visible node tree that shows VM status plus heartbeat freshness.
4. Refactor alarm workflow into `AlarmManagement.vue` and `useAlarmWorkflow.ts`.
5. Refactor backend alert lifecycle into a separate module with direct tests.
6. Add UI lifecycle gating so each alert action appears at the correct stage.
7. Add AI runtime truth panel and decision provenance.
8. Expand log management and audit filtering.
9. Harden the Python node agent retry/persistence path.
10. Continue splitting the backend monolith only after behavior tests exist.

## 6. Commands To Re-Run Before Claiming Progress

Run the full verification:

```powershell
C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Check VM state directly:

```powershell
$vbox = "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
$env:VBOX_USER_HOME = "D:\MiniOGAS-VMs\VirtualBoxHome"
& $vbox list runningvms
```

Check live backend state:

```powershell
$token = (Get-Content -LiteralPath "D:\MiniOGAS-VMs\miniogas-token.txt" -Raw).Trim()
$state = Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/dashboard-state?mode=normal" -Headers @{ "X-OGAS-Token" = $token }
$state.nodes | Select-Object node_code,status,last_seen_sec,runtime,production
```

Check alerts:

```powershell
$alerts = Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/alerts" -Headers @{ "X-OGAS-Token" = $token }
$alerts
```

Check AI truth:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/auth/status"
```

Only claim live AI if the runtime proves the vault is unlocked and the smoke test succeeds.

## 7. Bottom Line

The system is no longer merely a frontend mock: there are real backend routes, real VM/node checks, real heartbeat ingestion, real alert lifecycle handling, real approval flow, and real audit archival.

But the full goal is not achieved yet. The remaining risk is architectural: large monolithic files, static demo data still present near real views, incomplete UI lifecycle clarity, limited AI provenance, and not enough failure-mode tests. The next work should continue toward proving that every visible operational state is backed by backend and node runtime evidence.

## 8. 2026-06-02 Continuation Update

This continuation focused on the factory runtime page and frontend/backend boundary proof.

Completed work:

- Added `services/dashboard/src/FactoryRuntimeView.vue` as a presentational factory runtime component.
- Moved the visible factory topology, parent/child node state, VirtualBox proof, AI runtime truth panel, heartbeat source rows, management boundary notes, and recent runtime event list into that component.
- Kept backend data orchestration in `App.vue`: `dashboard-state`, host nodes, work orders, VirtualBox state, AI smoke/runtime status, and runtime logs are still loaded and computed by the parent.
- Wired `App.vue` to render `FactoryRuntimeView` for the factory view, passing only computed backend/runtime state as props.
- Extended `scripts/check_dashboard_gate.py` so `FactoryRuntimeView` is checked as a presentational component and is rejected if it directly calls APIs or uses demo-only markers such as `liveOutput`, `liveTemp`, `pendingRecords`, `demoMode`, or `demoScenario`.

Verification completed after this update:

```powershell
python scripts/check_dashboard_gate.py
npm.cmd run test
npm.cmd run build
C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed verification result:

- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central API tests passed: 23 tests.
- Dashboard tests passed: 26 tests.
- Node-agent tests passed: 7 tests.
- Dashboard production build passed.
- Runtime check passed with 3 expected Mini-OGAS VirtualBox VMs running: `miniogas-turning`, `miniogas-milling`, `miniogas-grinding`.
- Central API health passed with 3/3 nodes connected.
- Dashboard protected state showed 3 live nodes, active issues 0, no stale nodes, no VM mismatches, and no dispatch mismatches.
- Runtime alert workflow passed through heartbeat fault, alert open, confirmation, diagnosis, approval required, human approval, close, audit archival, notification acknowledgement, offline record archival, and live state preservation.

Important truth note:

- AI is still not proven live. The verified state remains `locked / rule_fallback`; the vault is present but locked, and real model calls must not be claimed until administrator login unlocks the vault and a smoke test succeeds.

Remaining work after this update:

1. Remove the now-unreachable old inline factory template from `App.vue` once the next engineer is comfortable doing a larger template deletion.
2. Continue shrinking `App.vue`; the demo command page and some shared lifecycle logic remain too large.
3. Split alarm workflow logic into a composable such as `useAlarmWorkflow.ts`.
4. Split backend alert lifecycle and dispatch approval logic out of `main.py` after preserving tests.
5. Add Playwright UI verification for login boot animation, factory topology rendering, alarm lifecycle disappearance, dispatch approval archival, and log management.
6. Prove a real AI call by unlocking the configured vault through the administrator login path and recording the smoke-test result.
7. Add failure-mode verification for one stopped VM, one stale node, and one offline sync replay.

## 9. 2026-06-02 Lifecycle And Contract Repair

This continuation addressed the user's nine-category defect list against the current worktree. Several named files in that list do not exist in the current implementation (`store.py`, `ops.py`, `security.py`, `transfer.py`, `ai.py`, and the Go node-agent files). The current system is FastAPI `main.py/config.py/node_runtime.py`, Vue dashboard files, and a Python `services/node-agent/simulator.py`. The non-existent file findings should not be claimed as fixed; they are either old-architecture findings or need a future migration if those files are reintroduced.

Current fixes completed:

- Enforced alert lifecycle on the backend: `/api/ai/diagnose/{issue_id}` now rejects diagnosis unless the alert has first been confirmed.
- Enforced close lifecycle on the backend: `/api/issues/{issue_id}/actions` now rejects normal issue closure unless the issue is already `contained` or `observing`.
- Updated frontend alarm action gating in `App.vue`: AI diagnosis is available only from `confirmed`; close is available only from `contained` or `observing`; human escalation no longer replaces initial confirmation.
- Preserved concrete backend routes in `operationsApi.ts`: confirmation uses `/api/alerts/{issue_id}/confirm`, node isolation uses `/api/nodes/{node_code}/isolate`, closure uses `/api/issues/{issue_id}/actions`, and escalation uses `/api/ops/escalate` or `/api/ops/escalations/{id}/decision`.
- Improved structured backend observability: alert confirmation, human escalation, notification acknowledgement, and operator issue closure now use `append_log`, so `dashboard-state.log_events` preserves backend source and severity instead of relying only on legacy string logs.
- Extended `scripts/check_dashboard_gate.py` with static gates for lifecycle action rules and concrete operation routes, including rejection of `/api/ops/issue-command` for node isolation.
- Updated backend route tests so old shortcut flows are rejected before the correct confirm -> diagnose -> contain/observe -> close path is allowed.
- Added backend assertions that structured `log_events` contain lifecycle/operation sources such as `alert-lifecycle`, `operator-action`, and `human-escalation`.

Verification after this repair:

```powershell
python -m unittest discover -s services/central-api
npm.cmd run test
npm.cmd run build
python scripts/check_dashboard_gate.py
C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Central API tests: 30 passed.
- Dashboard tests: 26 passed.
- Dashboard production build passed.
- Full Mini-OGAS verification passed, including API contract, login gate, secret scan, central API tests, config tests, node runtime tests, node-agent tests, dashboard tests/build, full-stack runtime check, and runtime alert workflow.
- Runtime workflow still proves the intended lifecycle: heartbeat fault -> alert open -> confirmed -> diagnosed -> approval required -> human approved -> closed -> audit archived -> notification acknowledged -> offline records archived -> live state preserved.

Important remaining gaps:

- AI is still not proven live. The verified runtime remains `locked / rule_fallback`.
- `App.vue` and `styles.css` remain large and should be further split. Some components now exist, but this is not a full router/state-management architecture.
- The current repository has no Go node-agent, so Go-specific slog/context/default-token findings are not applicable to this tree.
- The current repository has no `MemoryStore` class or old `store.py`; equivalent monolith risk remains in `services/central-api/main.py`, which is still too large and should be decomposed under tests.
- Browser-level E2E verification is still needed for the full human workflow and log-management UI, even though backend and unit/integration tests now cover the lifecycle contract.

## 10. 2026-06-02 VM Connection And Real AI Deployment

This continuation prioritized the user's request to fix the frontend/VM connection proof first, then deploy real AI before continuing other plan work.

Current runtime evidence:

- VirtualBox reports all three expected VMs running: `miniogas-turning`, `miniogas-milling`, and `miniogas-grinding`.
- `central-api /health` reports `status=ok`, `nodes_connected=3`, `nodes_expected=3`, no stale nodes, no missing nodes, no missing VMs, and no VM/node mismatches.
- Protected `dashboard-state` shows:
  - `turning-workshop-01` -> `miniogas-turning` -> `LATHE-01` -> `running`
  - `milling-workshop-01` -> `miniogas-milling` -> `MILL-02` -> `running`
  - `grinding-workshop-01` -> `miniogas-grinding` -> `GRIND-01` -> `running`
- Browser verification after login showed the factory page with `运行设备 3/3`, `VirtualBox 运行中`, `子节点 3/3 在线`, and each node's VM, host, pid, heartbeat interval, and last-seen seconds.

AI deployment work completed:

- Rebuilt the encrypted AI vault using the provided DeepSeek key through environment variables only; no plaintext key was written to source or `.env`.
- Vault is now configured as `provider=deepseek`, `model=deepseek-v4-pro`, `base_url=https://api.deepseek.com/v1`.
- The administrator/vault password is `miniogas`.
- Login through `/api/auth/login` now unlocks `AI_VAULT` and reports `runtime.source=api`, `runtime.status=connected`, `vault_unlocked=true`.
- Startup AI smoke test now succeeds with `ai_smoke.ok=true`, `source=api`, `status=connected`.
- Frontend browser verification after login showed `AI 接口: 真实 API 已验证`, `AI 调用证明: 真实模型`, and `deepseek / deepseek-v4-pro 启动烟测成功`.

Important AI runtime fix:

- After real AI was unlocked, the full verification initially failed because `/api/alerts` indirectly triggered synchronous model calls through `active_issues() -> ensure_ai_decision()`. This was both slow and logically wrong because AI diagnosis should happen after operator confirmation.
- Fixed `active_issues()` so alert listing does not call AI.
- Added backend test `test_alert_list_does_not_call_ai_before_operator_diagnosis`.
- DeepSeek returned a Chinese confidence label (`高`) in one smoke response, which previously crashed normalization via `float()`. Added `normalize_confidence()` to support numeric, percent, English, and Chinese confidence labels.
- Added backend test `test_ai_confidence_accepts_chinese_and_percent_labels`.
- Increased runtime workflow verification timeout from 8 seconds to configurable `MINIOGAS_WORKFLOW_TIMEOUT_SEC`, defaulting to 45 seconds, because real AI diagnosis can take longer than a rules fallback.

Verification after this repair:

```powershell
python -m unittest discover -s services/central-api
python scripts/check_runtime_workflow.py
C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
npm.cmd run build
python scripts/check_dashboard_gate.py
```

Observed result:

- Central API tests: 32 passed.
- Dashboard tests: 26 passed.
- Node-agent tests: 7 passed.
- Full verification passed.
- Runtime alert workflow passed with real AI unlocked, including: heartbeat fault -> alert open -> confirmed -> diagnosed -> approval required -> human approved -> closed -> audit archived -> notification acknowledged -> offline records archived -> live state preserved.

Small UI cleanup:

- Removed the accidental CSS prefix that displayed VirtualBox counts as `到 3 台`; the intended text is now `3 台`.

## 11. 2026-06-02 AI Runtime Extraction

This continuation started the next phase after the VM connection and real AI deployment priorities were proven live.

Work completed:

- Added `services/central-api/ai_runtime.py` as the first independent AI runtime module.
- Moved pure AI infrastructure logic out of `services/central-api/main.py`:
  - environment value lookup
  - placeholder API-key rejection
  - AI vault key derivation
  - AI vault encryption and decryption
  - vault MAC validation
  - model confidence normalization for numeric, percent, English, and Chinese labels
- Updated `services/central-api/create_ai_vault.py` so vault generation imports `encrypt_vault_payload` from `ai_runtime.py` instead of importing the full FastAPI `main.py` application.
- Removed the duplicate `normalize_confidence()` implementation from `main.py`; AI decisions now use the imported runtime helper.
- Added `services/central-api/test_ai_runtime.py` with focused tests for encrypted vault round trip, wrong-password/tamper rejection, placeholder API-key rejection, and confidence parsing for DeepSeek-style labels.
- Avoided fake `sk-...` test strings because the repository secret scanner correctly treats those as potential secrets.

Runtime proof after this extraction:

- Restarted `central-api` with the configured Mini-OGAS token.
- Logged in through `/api/auth/login` using the vault password.
- `/health` returned `status=ok`, `nodes_connected=3`, `nodes_expected=3`, no stale nodes, no missing nodes, no missing VMs, no VM/node mismatches.
- AI runtime remained connected: `provider=deepseek`, `model=deepseek-v4-pro`, `source=api`, `key_name=AI_VAULT`, `vault_unlocked=true`.
- Preflight continued to show all three VirtualBox-backed nodes online:
  - `turning-workshop-01 / miniogas-turning / LATHE-01`
  - `milling-workshop-01 / miniogas-milling / MILL-02`
  - `grinding-workshop-01 / miniogas-grinding / GRIND-01`

Verification after this extraction:

```powershell
python -m unittest discover -s services/central-api
C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Direct central-api test discovery: 36 tests passed.
- Full Mini-OGAS verification passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Dashboard tests passed: 6 files, 26 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VM nodes live and AI runtime connected.
- Runtime alert workflow passed through heartbeat fault, alert open, confirmation, diagnosis, approval required, human approval, close, audit archival, notification acknowledgement, offline record archival, and live state preservation.

Remaining work after this section:

1. Continue decomposing `services/central-api/main.py`; likely next split points are alert lifecycle, dispatch approval, and AI API transport.
2. Keep `call_ai_api()` in `main.py` for now because it still depends on issue context, logs, fallback decisions, cache, and current application state.
3. Continue shrinking `services/dashboard/src/App.vue`, especially the old dead inline factory block and shared alarm workflow logic.
4. Add browser-level E2E tests for login boot animation, node tree state, alarm disappearance after archival, dispatch approval archival, and log-management visibility.

## 12. 2026-06-02 AI HTTP Transport Extraction

This continuation extended the AI runtime extraction by moving the OpenAI-compatible HTTP transport boundary out of `services/central-api/main.py`.

Work completed:

- Added `AiTransportError` in `services/central-api/ai_runtime.py`.
- Added `chat_completion_json()` in `services/central-api/ai_runtime.py`.
- `chat_completion_json()` now owns:
  - `/chat/completions` URL construction
  - OpenAI-compatible request payload construction
  - Authorization and JSON headers
  - response JSON decoding
  - model `choices[0].message.content` parsing
  - wrapping malformed or failed responses as `AiTransportError`
- Updated `services/central-api/main.py` so `call_ai_api()` now focuses on the Mini-OGAS industrial issue context, prompt, fallback decision, normalization, and cache flow.
- Removed direct `urllib` usage from `main.py`.
- Added transport tests in `services/central-api/test_ai_runtime.py` for:
  - OpenAI-compatible payload posting
  - correct `/chat/completions` endpoint construction
  - Authorization header wiring
  - JSON object response parsing
  - malformed model response wrapping
- Fixed a real test-discovered edge case: an empty `choices` list now raises `AiTransportError` instead of leaking `IndexError` through the AI subsystem.

Verification after this extraction:

```powershell
python -m unittest discover -s services/central-api
C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Direct central-api test discovery: 38 tests passed.
- `central-api` was restarted after code changes and AI was unlocked through `/api/auth/login`.
- Runtime health after restart: `nodes_connected=3`, `nodes_expected=3`, `missing_vms=0`, `ai_status=connected`, `ai_provider=deepseek`, `ai_model=deepseek-v4-pro`.
- Full Mini-OGAS verification passed again.
- Secret scan passed.
- Dashboard tests passed: 6 files, 26 tests.
- Dashboard production build passed.
- Runtime alert workflow passed end-to-end with the real AI runtime still connected.

Remaining work after this section:

1. Split alert lifecycle and dispatch approval out of `main.py`; those are now bigger risks than the AI transport boundary.
2. Keep checking runtime after each split because the system depends on a live token, live VM heartbeats, and vault unlock state.
3. Continue frontend cleanup after backend lifecycle modules are safer.

## 13. 2026-06-02 Alert Lifecycle State Machine Extraction

This continuation started decomposing the backend alert lifecycle logic after the VM connection and real AI runtime had already been proven live.

Work completed:

- Added `services/central-api/alert_lifecycle.py` as a focused alert lifecycle state-machine module.
- Moved lifecycle primitives out of `services/central-api/main.py`:
  - initial lifecycle row creation
  - diagnosis precondition: only `confirmed` alerts can be diagnosed
  - close precondition: only `contained` or `observing` alerts can be verified and closed
  - timestamp stamping for `confirmed`, `diagnosed`, `contained`, `observing`, and `closed`
- Updated `main.py` so `lifecycle_for()` uses `new_lifecycle()` and `set_lifecycle()` uses `transition_lifecycle()`.
- Updated route guards so `/api/ai/diagnose/{issue_id}` uses `can_diagnose()` and `/api/issues/{issue_id}/actions` uses `can_close()`.
- Added `services/central-api/test_alert_lifecycle.py` with focused tests for initial state, diagnosis gating, close gating, and timestamp stamping.

Verification after this extraction:

```powershell
python -m unittest discover -s services/central-api
C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Direct central-api test discovery: 42 tests passed.
- Full Mini-OGAS verification passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Dashboard tests passed: 6 files, 26 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VM nodes live and AI runtime connected.
- Runtime alert workflow still passed through heartbeat fault, alert open, confirmation, diagnosis, approval required, human approval, close, audit archival, notification acknowledgement, offline record archival, and live state preservation.

Remaining work after this section:

1. Extract dispatch approval and archival logic next; it still sits in `main.py` and is the next backend lifecycle risk.
2. Extract resolution-effect logic after dispatch, because it mutates alarms, node status, work order state, lifecycle state, and verification results in one function.
3. Continue frontend cleanup after backend lifecycle modules are stable.

## 14. 2026-06-02 Dispatch Approval Workflow Extraction

This continuation decomposed the dispatch approval and archival rules after the alert lifecycle state machine extraction.

Work completed:

- Added `services/central-api/dispatch_workflow.py` as a focused dispatch workflow module.
- Moved pure dispatch approval rules out of `services/central-api/main.py`:
  - `CONFIRM` confirmation-code validation
  - `waiting_approval` dispatch-plan gate
  - dispatch record construction for initial and human-approved assignments
  - approved-plan archival field updates
  - resolved dispatch notification construction
  - dispatch audit effect construction
- Updated initial `node_dispatches` construction to use `dispatch_record_for_order(..., policy="ai_auto_dispatch")`.
- Updated `rebuild_dispatch_for_order()` to use the same dispatch record builder with `policy="human_approved_reschedule"`.
- Updated `/api/ops/dispatch-plan/approve` so the route delegates status gating, confirmation-code validation, plan archival, notification construction, and audit-effect construction to `dispatch_workflow.py`.
- Added `services/central-api/test_dispatch_workflow.py` with focused tests for confirmation-code parsing, approval status gating, dispatch record shape, plan archival, notification structure, and audit effect structure.

Verification after this extraction:

```powershell
python -m unittest discover -s services/central-api
C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
python scripts/check_runtime_workflow.py
```

Observed result:

- Direct central-api test discovery: 47 tests passed.
- Full Mini-OGAS verification passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Dashboard tests passed: 6 files, 26 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VM nodes live and AI runtime connected.
- `central-api` was restarted after code changes and AI was unlocked again through `/api/auth/login`.
- Runtime health after restart: `nodes_connected=3`, `nodes_expected=3`, `missing_vms=0`, `ai_status=connected`, `ai_provider=deepseek`, `ai_model=deepseek-v4-pro`.
- Runtime workflow passed on the restarted process: heartbeat fault, alert open, confirmation, diagnosis, approval required, human approval, close, audit archival, notification acknowledgement, offline record archival, and live state preservation.

Remaining work after this section:

1. Extract resolution-effect logic next; it is now the largest concentrated mutation block because it changes resolved issues, lifecycle, alarms, node state, work order state, verification result, and logs.
2. Continue reducing `main.py` route-body size after resolution effects are isolated.
3. Continue frontend cleanup after backend lifecycle/dispatch/resolution modules are stable.

## 15. 2026-06-02 Resolution Effect Extraction

This continuation decomposed the resolution-effect mutation block, which was the largest remaining backend state mutation inside `main.py` after AI, alert lifecycle, and dispatch workflow extraction.

Work completed:

- Added `services/central-api/resolution_effects.py` as a focused resolution-effect module.
- Moved pure resolution rules out of `services/central-api/main.py`:
  - resolution action record construction
  - maintenance/stop/isolate/check action detection
  - safe numeric clamping for sensor corrections
  - alarm-specific node mutation rules
  - order status mutation after node state changes
  - alarm-removed verification helper
  - resolution result shape construction
  - resolution verification shape construction
- Updated `apply_resolution_effect()` in `main.py` so it now delegates node mutation, order-state mutation, result construction, and verification construction to `resolution_effects.py`.
- Updated `apply_resolved_issue_filters()` so maintenance-action detection uses the shared `action_requests_maintenance()` helper instead of duplicating keyword lists.
- Added `services/central-api/test_resolution_effects.py` with focused tests for:
  - action record shape
  - Chinese and legacy mojibake maintenance-action terms
  - spindle-temperature resolution and order blocking
  - quality-drift resolution and order restoration
  - sync-delay pending-record clearance
  - alarm-removed verification
  - result and verification API shape preservation

Verification after this extraction:

```powershell
python -m unittest discover -s services/central-api
C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
python scripts/check_runtime_workflow.py
```

Observed result:

- Direct central-api test discovery: 54 tests passed.
- Full Mini-OGAS verification passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Dashboard tests passed: 6 files, 26 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VM nodes live and AI runtime connected.
- `central-api` was restarted after code changes and AI was unlocked again through `/api/auth/login`.
- Runtime health after restart: `nodes_connected=3`, `nodes_expected=3`, `missing_vms=0`, `ai_status=connected`, `ai_provider=deepseek`, `ai_model=deepseek-v4-pro`.
- Runtime workflow passed on the restarted process: heartbeat fault, alert open, confirmation, diagnosis, approval required, human approval, close, audit archival, notification acknowledgement, offline record archival, and live state preservation.

Remaining work after this section:

1. Continue reducing `main.py` route-body size; alert lifecycle, dispatch workflow, AI runtime, and resolution effects now have first-pass modules, but routes still contain substantial orchestration.
2. Move frontend cleanup higher in priority next, especially `App.vue` dead inline blocks, alarm workflow composable extraction, and style splitting.
3. Add browser-level E2E checks for the visual workflow after backend modules are stable.

## 16. 2026-06-02 Frontend Alarm Workflow Composable Extraction

This continuation moved the frontend alarm operation workflow out of the large `services/dashboard/src/App.vue` file.

Work completed:

- Added `services/dashboard/src/useAlarmWorkflow.ts`.
- Moved alarm action-state logic out of `App.vue`:
  - unacknowledged -> confirm only
  - confirmed -> diagnose and escalate
  - diagnosed -> observe/ignore/escalate and isolate only when AI recommends isolation
  - contained/observing -> close
- Moved alarm operation handlers out of `App.vue`:
  - `confirmAlarm`
  - `runAiDiagnose`
  - `isolateNode`
  - `escalateToHuman`
  - `observeAlarm`
  - `ignoreAlarm`
  - `closeAlarm`
  - `decideEscalation`
  - `selectAlarm`
  - `updateEscalationCode`
- Kept API routing through `operationsApi.ts`, preserving concrete backend routes instead of NL command routing.
- Moved shared alarm API types into `services/dashboard/src/types.ts`:
  - `ApiAlert`
  - `AiDecisionOption`
  - `AiDecision`
  - `ApiDiagnosis`
  - `EscalationItem`
- Added `services/dashboard/src/useAlarmWorkflow.test.ts` with focused tests for the frontend alarm action state machine.
- Updated `scripts/check_dashboard_gate.py` so the static gate checks the new `useAlarmWorkflow.ts` location instead of assuming `alarmActions` still lives inside `App.vue`.

Verification after this extraction:

```powershell
npm.cmd run test
npm.cmd run build
C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Dashboard tests: 7 files, 30 tests passed.
- Dashboard production build passed.
- Full Mini-OGAS verification passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed after updating the gate to the new composable boundary.
- Secret scan passed.
- Full-stack runtime check passed with 3/3 VM nodes live and AI runtime connected.
- Runtime workflow still passed: heartbeat fault, alert open, confirmation, diagnosis, approval required, human approval, close, audit archival, notification acknowledgement, offline record archival, and live state preservation.

Remaining work after this section:

1. Continue frontend decomposition: remove the unreachable legacy inline factory block from `App.vue` and split remaining demo/dispatch orchestration.
2. Split `styles.css`; it is still a large single stylesheet.
3. Add browser-level E2E tests for the visual alarm workflow and log archival UI.

## 17. 2026-06-03 Frontend Dead Branch Removal And Runtime Node Reconnection

This continuation prioritized the user's request to make the frontend reflect the real backend and three-node runtime before continuing lower-priority cleanup.

Work completed:

- Removed the unreachable legacy factory-management template branch from `services/dashboard/src/App.vue`.
- Added a static dashboard gate so `scripts/check_dashboard_gate.py` fails if `App.vue` reintroduces hard-disabled template branches such as `v-else-if="false"` or `v-if="false"`.
- Updated the AI smoke proof gate to check the current visible `FactoryRuntimeView.vue` path instead of only looking for old markers in `App.vue`.
- Added `scripts/restart-local-nodes.ps1`.
  - Stops only local `simulator.py` node-agent processes.
  - Restarts turning, milling, and grinding node agents with `CENTRAL_API_URL=http://127.0.0.1:8080`.
  - Keeps the three VirtualBox VMs running and verifies central-api heartbeat visibility after restart.
- Added `scripts/check-runtime-status.ps1`.
  - Checks `/health`.
  - Checks `/api/system/preflight`.
  - Runs a login probe to confirm the AI vault/runtime state without printing the secret value.
- Recovered the runtime after finding that the node agents were still posting to `http://192.168.56.1:8080`, which is not appropriate for the current local process bridge mode.
- Confirmed current runtime shape:
  - `nodes_connected=3`
  - `nodes_expected=3`
  - no stale nodes
  - no missing nodes
  - all three Mini-OGAS VirtualBox VMs are registered and running
  - AI runtime is `deepseek / deepseek-v4-pro / connected`
  - AI vault is present and unlocked after administrator login
- Updated `deploy/check-miniogas-stack.ps1` so the runtime validation checks the real architecture:
  - node is present in protected dashboard state
  - node has a running VM mapping
  - heartbeat is fresh
  - dispatch active order matches node telemetry
  - AI runtime is visible
  - it now reports `deployment_modes` instead of failing solely because the local node bridge reports `process`

Important implementation note:

The current environment runs three VirtualBox VMs plus three local `simulator.py` node-agent bridge processes. The local processes publish the node heartbeats that central-api consumes, while the health/preflight layer validates that the mapped VMs are registered and running. This is the honest current deployment model; the validation no longer pretends the Python process itself is running inside the VM.

Verification after this section:

```powershell
C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File .\scripts\restart-local-nodes.ps1
C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File .\scripts\check-runtime-status.ps1
C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Local node restart reported `nodes_connected=3`, `connected_nodes=3`, and no stale nodes.
- Runtime status reported central-api healthy, 3/3 nodes connected, 3/3 VMs running, and AI runtime connected through the DeepSeek vault.
- Full Mini-OGAS verification passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api tests passed: 25 tests.
- Central-api config tests passed: 3 tests.
- Central-api node runtime tests passed: 4 tests.
- Node-agent tests passed: 7 tests.
- Dashboard tests passed: 7 files, 30 tests.
- Dashboard production build passed.
- Full-stack runtime check passed:
  - `virtualbox-running-vms`: ok
  - `central-api-health`: ok, `nodes_connected=3`
  - `ai-runtime`: ok, `deepseek-v4-pro`, vault unlocked
  - `dashboard-state-live-nodes`: ok, VM-mapped nodes with fresh heartbeats and aligned dispatches
  - `alerts-endpoint`: ok
- Runtime alert workflow check passed:
  - heartbeat fault
  - alert open
  - confirmed
  - diagnosed
  - approval required
  - human approved
  - closed
  - audit archived
  - notification acknowledged
  - offline records archived
  - live state preserved

Remaining work after this section:

1. Continue reducing `App.vue` by moving remaining dispatch/demo orchestration into focused composables or views.
2. Split `services/dashboard/src/styles.css` into smaller domain stylesheets.
3. Add Playwright browser-level tests for login self-check animation, alarm handling, dispatch approval, log archival, and AI diagnosis visibility.
4. Consider adding a true in-VM node-agent boot path if the project needs the agent process to run inside each VirtualBox guest instead of using the current host-side bridge model.

## 18. 2026-06-03 Frontend Dispatch Workflow Composable Extraction

This continuation followed the restored runtime verification by reducing another high-risk frontend workflow in `App.vue`: dispatch recalculation and dispatch approval.

Work completed:

- Added `services/dashboard/src/useDispatchWorkflow.ts`.
- Moved dispatch workflow state and behavior out of `App.vue`:
  - confirmation code state
  - feedback message and feedback severity
  - recalculation/approval loading state
  - waiting-approval computed state
  - dispatch panel title
  - dispatch approval label
  - dispatch recalculation handler
  - dispatch approval handler
- Kept the existing backend routes through `operationsApi.ts`:
  - `/api/ops/dispatch-plan/recalculate`
  - `/api/ops/dispatch-plan/approve`
- Preserved the UI-facing variable names used by `OrderDispatchView`, so this was a behavior-preserving extraction rather than a visual rewrite.
- Kept successful approval behavior explicit:
  - clear confirmation code
  - update `dispatchPlan`
  - update `hostWorkOrders`
  - insert returned audit event into `auditEvents`
  - add a resolved-effect message
  - add a live log message
  - play the success sound
  - refresh dashboard state, alarm data, and audit events
- Added `services/dashboard/src/useDispatchWorkflow.test.ts`.

New frontend tests cover:

- dispatch recalculation updates the plan, work orders, feedback, approval state, live logs, and notice sound
- approval is blocked when no plan is waiting for approval
- successful approval clears the confirmation code, writes success feedback, archives the audit event, adds resolved/live-log messages, plays success sound, and refreshes runtime data

Verification after this section:

```powershell
npm.cmd run test
npm.cmd run build
C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Dashboard tests passed: 8 files, 33 tests.
- Dashboard production build passed.
- Full Mini-OGAS verification passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api tests passed: 25 tests.
- Central-api config tests passed: 3 tests.
- Central-api node runtime tests passed: 4 tests.
- Node-agent tests passed: 7 tests.
- Full-stack runtime check passed with 3/3 VM-mapped nodes connected, 3/3 VMs running, AI runtime connected, and zero active issues.
- Runtime alert workflow check passed again through human approval, audit archival, notification acknowledgement, offline record archival, and live-state preservation.

Remaining work after this section:

1. Continue reducing `App.vue`; the remaining largest clusters are startup/auth orchestration, demo emergency choreography, and runtime telemetry presentation.
2. Split `services/dashboard/src/styles.css` into smaller domain stylesheets.
3. Add Playwright browser-level tests for the visual login/preflight animation, dispatch approval, alarm handling, and log archival views.

## 19. 2026-06-05 Frontend Startup Workflow Extraction And Runtime Recovery

This continuation resumed from the current project files rather than assuming the older `store.py`/Go-agent layout still existed. The current authoritative tree is FastAPI `central-api`, Vue dashboard, and Python `node-agent`; no `store.py`, `ops.py`, `security.py`, `transfer.py`, `ai.py`, or Go source files were present in the active Mini-OGAS tree.

Work completed:

- Added shared startup/runtime types to `services/dashboard/src/types.ts`:
  - `NodeRuntime`
  - `VirtualBoxState`
  - `AuthRuntime`
  - `PreflightCheck`
  - `PreflightNode`
  - `PreflightState`
  - `AiSmokeState`
- Added `services/dashboard/src/useStartupWorkflow.ts`.
- Moved startup/auth state and behavior out of `App.vue`:
  - login operator and password
  - login feedback/loading state
  - system unlock state
  - preflight/login gate phase
  - auth runtime state
  - preflight loading/progress/check data
  - AI smoke result
  - startup check animation data
  - boot progress
  - AI runtime label
  - visible AI smoke truth
  - `/api/auth/status` loading
  - `/api/system/preflight` self-check
  - `/api/auth/login` administrator verification and AI smoke handling
- Updated `App.vue` to delegate startup/login orchestration to `useStartupWorkflow`.
- Removed the old inline startup computed values and login/preflight functions from `App.vue`.
- Updated `scripts/check_dashboard_gate.py` to understand the new startup module boundary:
  - `App.vue` must call `useStartupWorkflow`.
  - `useStartupWorkflow.ts` must keep preflight, login, unlock, and AI smoke proof markers.
  - the audit-log isolation gate now checks the current function boundaries after `loginAdmin` moved out of `App.vue`.
- Added `services/dashboard/src/useStartupWorkflow.test.ts`.

New frontend tests cover:

- successful preflight loads `/api/system/preflight`, marks the API available, records AI runtime, stores VirtualBox state, and transitions to login
- successful administrator login unlocks the system, arms sound, clears the password, records live AI smoke proof, logs the AI status, and refreshes dashboard state
- failed administrator login keeps the system locked and shows the backend error

Runtime recovery performed before full verification:

- The full verification initially failed because the local runtime was stopped:
  - central-api was not reachable
  - no Mini-OGAS VMs were running
  - no node-agent processes were reporting heartbeats
- Restarted the three registered VirtualBox VMs under `D:\MiniOGAS-VMs\VirtualBoxHome`:
  - `miniogas-turning`
  - `miniogas-milling`
  - `miniogas-grinding`
- Restarted `central-api` on `http://127.0.0.1:8080`.
- Logged in with the administrator password to unlock the AI vault.
- Verified AI runtime as `deepseek / deepseek-v4-pro / AI_VAULT / connected`.
- Ran `scripts/restart-local-nodes.ps1` to restart the three host-side node-agent bridge processes with `CENTRAL_API_URL=http://127.0.0.1:8080`.
- Confirmed `connected_nodes=3` and no stale nodes.

Verification after this section:

```powershell
npm.cmd run test
npm.cmd run build
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Dashboard tests passed: 9 files, 36 tests.
- Dashboard production build passed.
- Full Mini-OGAS verification passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed after updating the gate for `useStartupWorkflow`.
- Secret scan passed.
- Central-api tests passed: 25 tests.
- Central-api config tests passed: 3 tests.
- Central-api node runtime tests passed: 4 tests.
- Node-agent tests passed: 7 tests.
- Full-stack runtime check passed:
  - 3/3 Mini-OGAS VMs running
  - central-api healthy
  - `nodes_connected=3`
  - AI runtime connected through the unlocked DeepSeek vault
  - dashboard state shows live VM-mapped nodes with aligned dispatches
  - zero active issues
- Runtime alert workflow check passed again through heartbeat fault, alert open, confirmation, diagnosis, approval required, human approval, close, audit archival, notification acknowledgement, offline record archival, and live state preservation.

Current size after this section:

- `services/dashboard/src/App.vue`: 1229 lines.
- `services/dashboard/src/useStartupWorkflow.ts`: 264 lines.
- `services/dashboard/src/types.ts`: 261 lines.

Remaining work after this section:

1. Continue reducing `App.vue`; the next obvious clusters are demo emergency choreography and runtime telemetry presentation helpers.
2. Split `services/dashboard/src/styles.css`, which is still a large single stylesheet.
3. Add Playwright browser-level tests for the visual login/preflight animation, dispatch approval, alarm handling, and log archival views.
4. Continue reducing `services/central-api/main.py`, which remains the largest backend file.

## 20. 2026-06-05 Frontend Emergency Demo Workflow Extraction

This continuation kept reducing `App.vue` by moving the emergency demo command workflow into its own composable. This is separate from the real backend alarm lifecycle; it controls the visual demonstration page and AI emergency guide behavior.

Work completed:

- Added `services/dashboard/src/useEmergencyDemoWorkflow.ts`.
- Moved emergency demo state and behavior out of `App.vue`:
  - demo mode
  - AI guide visibility
  - emergency stage index
  - selected treatment actions
  - dismissed issue ids
  - emergency guide stages and treatment options
  - active demo scenario selection
  - demo output/temperature/wear/pending-record indicators
  - heartbeat display status for the demo page
  - demo mode switching
  - treatment selection
  - stage advancement
  - automatic recovery timer
  - emergency timer cleanup
- Kept `App.vue` responsible for the real backend issue handling and protected runtime polling, while the composable owns only the visual emergency/demo choreography.
- Added `services/dashboard/src/useEmergencyDemoWorkflow.test.ts`.

New frontend tests cover:

- entering emergency mode opens the AI guide, resets the step/action state, writes the live log, plays the critical sound, and asks for dashboard refresh
- attempting to advance without selecting a treatment is blocked and logs an operator-facing message
- advancing through all emergency stages writes the completion log and automatically restores normal mode after the recovery timer

Verification after this section:

```powershell
npm.cmd run test
npm.cmd run build
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Dashboard tests passed: 10 files, 39 tests.
- Dashboard production build passed.
- Full Mini-OGAS verification passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api tests passed: 25 tests.
- Central-api config tests passed: 3 tests.
- Central-api node runtime tests passed: 4 tests.
- Node-agent tests passed: 7 tests.
- Full-stack runtime check passed with 3/3 VMs running, central-api healthy, `nodes_connected=3`, AI runtime connected, VM-mapped nodes aligned with dispatches, and zero active issues.
- Runtime alert workflow check passed again through the full alert/AI/human/audit/offline-record lifecycle.

Current size after this section:

- `services/dashboard/src/App.vue`: 1149 lines.
- `services/dashboard/src/useEmergencyDemoWorkflow.ts`: 154 lines.
- `services/dashboard/src/useStartupWorkflow.ts`: 264 lines.

Remaining work after this section:

1. Continue reducing `App.vue`; the next good frontend target is runtime telemetry presentation helpers.
2. Split `services/dashboard/src/styles.css`.
3. Add Playwright browser-level checks for login/preflight animation, emergency demo guide, dispatch approval, alarm handling, and log archival.
4. Continue reducing `services/central-api/main.py`.

## 21. 2026-06-05 Frontend Runtime Presentation Extraction

This continuation moved the backend-driven runtime presentation helpers out of `App.vue`. This directly supports the requirement that the frontend reflect real backend/node state instead of static demo values.

Work completed:

- Added `HostNode` to `services/dashboard/src/types.ts`.
- Added `services/dashboard/src/useRuntimePresentation.ts`.
- Moved runtime presentation logic out of `App.vue`:
  - machine-state normalization
  - yield-rate calculation
  - workshop name mapping
  - machine type mapping
  - alarm label mapping
  - live workshop grouping from backend `hostNodes`
  - machine rows from backend heartbeat production data
  - backend order progress derived from node heartbeats
  - displayed work orders
  - node runtime rows
  - control service rows for central-api, child-node heartbeat, VirtualBox, AI runtime, and audit archival
- Updated `App.vue` to consume `useRuntimePresentation` outputs instead of owning the transformation logic.
- Updated `scripts/check_dashboard_gate.py` so the static gate requires `App.vue` to delegate runtime presentation to `useRuntimePresentation`.
- Added `services/dashboard/src/useRuntimePresentation.test.ts`.

New frontend tests cover:

- machine status normalization, yield-rate calculation, and alarm label mapping
- mapping live backend node heartbeats into workshop rows and machine rows
- deriving work-order progress from backend node production counters
- exposing node runtime details such as deployment mode, VM name, VM running state, and sync-record count
- summarizing central API, node heartbeat, VirtualBox, AI runtime, and audit service status

Verification after this section:

```powershell
npm.cmd run test
npm.cmd run build
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Dashboard tests passed: 11 files, 42 tests.
- Dashboard production build passed.
- Full Mini-OGAS verification passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed after updating the runtime presentation boundary.
- Secret scan passed.
- Central-api tests passed: 25 tests.
- Central-api config tests passed: 3 tests.
- Central-api node runtime tests passed: 4 tests.
- Node-agent tests passed: 7 tests.
- Full-stack runtime check passed with 3/3 VMs running, central-api healthy, `nodes_connected=3`, AI runtime connected, VM-mapped nodes aligned with dispatches, and zero active issues.
- Runtime alert workflow check passed again through the full alert/AI/human/audit/offline-record lifecycle.

Current size after this section:

- `services/dashboard/src/App.vue`: 981 lines.
- `services/dashboard/src/useRuntimePresentation.ts`: 193 lines.
- `services/dashboard/src/types.ts`: 292 lines.

Remaining work after this section:

1. Split `services/dashboard/src/styles.css`, which is now the largest frontend maintainability target.
2. Continue reducing `services/central-api/main.py`.
3. Add Playwright browser-level checks for login/preflight animation, emergency demo guide, dispatch approval, alarm handling, and log archival.

## 22. 2026-06-05 Startup Stylesheet Extraction

This continuation began splitting the remaining large frontend stylesheet without changing the visual behavior.

Work completed:

- Added `services/dashboard/src/styles/startup.css`.
- Moved startup/login/preflight styles out of `services/dashboard/src/styles.css`:
  - login overlay
  - login card
  - boot card
  - boot header
  - boot screen
  - boot lines
  - boot progress bar
  - startup checks
  - startup node summary
  - login actions
  - startup-specific keyframes
- Updated `services/dashboard/src/main.ts` to import `./styles/startup.css` before the main stylesheet.
- Removed the migrated selectors and keyframes from `styles.css`.

Verification after this section:

```powershell
npm.cmd run test
npm.cmd run build
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Dashboard tests passed: 11 files, 42 tests.
- Dashboard production build passed with the split CSS imported by Vite.
- Full Mini-OGAS verification passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api tests passed: 25 tests.
- Central-api config tests passed: 3 tests.
- Central-api node runtime tests passed: 4 tests.
- Node-agent tests passed: 7 tests.
- Full-stack runtime check passed with 3/3 VMs running, central-api healthy, `nodes_connected=3`, AI runtime connected, VM-mapped nodes aligned with dispatches, and zero active issues.
- Runtime alert workflow check passed again through the full alert/AI/human/audit/offline-record lifecycle.

Current size after this section:

- `services/dashboard/src/styles.css`: 2037 lines.
- `services/dashboard/src/styles/startup.css`: 305 lines.
- `services/dashboard/src/App.vue`: 981 lines.

Remaining work after this section:

1. Continue splitting `styles.css`; next good candidates are alarm workflow styles or demo/emergency styles.
2. Continue reducing `services/central-api/main.py`.
3. Add Playwright browser-level checks for login/preflight animation, emergency demo guide, dispatch approval, alarm handling, and log archival.

## 23. 2026-06-05 Alarm Stylesheet Extraction

This continuation split another high-cohesion frontend style block out of the large main stylesheet, focusing on the alarm management and human-escalation workflow UI.

Work completed:

- Added `services/dashboard/src/styles/alarm.css`.
- Moved alarm-management styles out of `services/dashboard/src/styles.css`:
  - alarm list panel
  - alarm row stack
  - escalation stack
  - alarm rows and selected/hover/focus states
  - severity variants
  - alarm detail layout
  - diagnosis box
  - AI provenance block
  - compact evidence/options lists
  - AI decision options
  - alarm feedback and error feedback
  - empty hint
  - diagnosis result text
  - isolation tag
  - escalation rows
  - escalation approval actions
- Updated `services/dashboard/src/main.ts` to import `./styles/alarm.css` after `startup.css` and before the main stylesheet.
- Left shared layout/action styles and shared keyframes in `styles.css` to avoid duplication.

Verification after this section:

```powershell
npm.cmd run test
npm.cmd run build
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Dashboard tests passed: 11 files, 42 tests.
- Dashboard production build passed with `startup.css`, `alarm.css`, and `styles.css` imported by Vite.
- Full Mini-OGAS verification passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api tests passed: 25 tests.
- Central-api config tests passed: 3 tests.
- Central-api node runtime tests passed: 4 tests.
- Node-agent tests passed: 7 tests.
- Full-stack runtime check passed with 3/3 VMs running, central-api healthy, `nodes_connected=3`, AI runtime connected, VM-mapped nodes aligned with dispatches, and zero active issues.
- Runtime alert workflow check passed again through the full alert/AI/human/audit/offline-record lifecycle.

Current size after this section:

- `services/dashboard/src/styles.css`: 1826 lines.
- `services/dashboard/src/styles/startup.css`: 305 lines.
- `services/dashboard/src/styles/alarm.css`: 210 lines.
- `services/dashboard/src/App.vue`: 981 lines.

Remaining work after this section:

1. Continue splitting `styles.css`; next good candidate is demo/emergency guide styles.
2. Continue reducing `services/central-api/main.py`.
3. Add Playwright browser-level checks for login/preflight animation, emergency demo guide, dispatch approval, alarm handling, and log archival.

## 24. 2026-06-05 Backend Observability Module Extraction

This continuation reduced another backend monolith area without changing the public API behavior. The target was the central logging and audit archival path, because many earlier user-facing issues were about resolved alarms and dispatch approvals not disappearing from active queues or not being archived into log management.

Work completed:

- Added `services/central-api/observability.py`.
- Moved reusable observability behavior into the new module:
  - structured runtime log insertion
  - log/event list trimming
  - audit event creation
  - audit archive insertion and retention limit
  - node offline-record sync audit summaries
- Updated `services/central-api/main.py` so its existing helpers are thin compatibility wrappers:
  - `append_log(...)` delegates to `append_runtime_log(...)`
  - `archive_event(...)` delegates to `archive_audit_event(...)`
  - `archive_node_sync_event(...)` delegates to `archive_node_sync_audit_event(...)`
- Removed the old duplicated node-sync audit body from `main.py`.
- Added `services/central-api/test_observability.py` with 4 focused tests:
  - runtime log prepending and trimming
  - structured log metadata
  - audit event default fields and effect payloads
  - node offline-record sync archival summaries
- Updated `scripts/verify-miniogas.ps1` so the new observability tests are part of the standard full verification run.

Verification after this section:

```powershell
python -m py_compile .\services\central-api\observability.py .\services\central-api\main.py .\services\central-api\test_observability.py
python .\services\central-api\test_observability.py
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Observability tests passed: 4 tests.
- Full Mini-OGAS verification passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api tests passed: 25 tests.
- Central-api config tests passed: 3 tests.
- Central-api observability tests passed: 4 tests.
- Central-api node runtime tests passed: 4 tests.
- Node-agent tests passed: 7 tests.
- Dashboard tests passed: 11 files, 42 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 expected Mini-OGAS VMs running, central-api healthy, `nodes_connected=3`, AI runtime connected, VM-mapped nodes aligned with dispatches, and zero active issues.
- Runtime alert workflow check passed through `heartbeat_fault`, `alert_open`, `confirmed`, `diagnosed`, `approval_required`, `human_approved`, `closed`, `audit_archived`, `notification_acknowledged`, `offline_records_archived`, and `live_state_preserved`.

Current size after this section:

- `services/central-api/main.py`: 2064 lines.
- `services/central-api/observability.py`: 115 lines.
- `services/central-api/test_observability.py`: 94 lines.
- `services/dashboard/src/App.vue`: 981 lines.
- `services/dashboard/src/styles.css`: 1826 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next good candidates are auth/vault/login gate helpers or dashboard-state response assembly.
2. Continue splitting `services/dashboard/src/styles.css`; next good candidate is demo/emergency guide styles.
3. Add browser-level Playwright checks for login/preflight animation, dispatch approval, alarm handling, log archival, and card animations.
4. Continue tightening the live frontend/backend contract so UI state changes remain visibly tied to node heartbeats, AI decisions, human approvals, and audit archives.

## 25. 2026-06-05 Auth Runtime And AI Readiness Extraction

This continuation continued reducing `services/central-api/main.py` around the startup/login path. This area matters because the user-facing system must not show the control console until the parent/child nodes, AI API readiness, and startup self-check have been evaluated.

Work completed:

- Added `services/central-api/auth_runtime.py`.
- Moved pure login and AI readiness logic out of `main.py`:
  - login-attempt window trimming
  - public login rate-limit decision
  - AI configuration source selection
  - unlocked vault priority over environment keys
  - DeepSeek environment fallback defaults
  - AI runtime status payload assembly
- Updated `services/central-api/main.py`:
  - `resolve_ai_config()` now delegates to `resolve_ai_config_from_sources(...)`
  - `ai_runtime_state()` now delegates to `ai_runtime_state_from_config(...)`
  - `/api/auth/login` now delegates rate-limit bookkeeping to `record_login_attempt(...)`
- Added `services/central-api/test_auth_runtime.py` with 5 focused tests:
  - first 6 login attempts are allowed and the 7th is rate-limited
  - old login attempts expire outside the time window
  - unlocked AI vault wins over environment keys
  - DeepSeek API environment keys receive the correct provider/model/base-url defaults
  - AI runtime state correctly reports locked and connected modes
- Updated `scripts/verify-miniogas.ps1` so auth runtime tests run as part of the standard full verification.

Verification after this section:

```powershell
python -m py_compile .\services\central-api\auth_runtime.py .\services\central-api\main.py .\services\central-api\test_auth_runtime.py
python .\services\central-api\test_auth_runtime.py
python .\services\central-api\test_main.py
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Auth runtime tests passed: 5 tests.
- Central-api route tests passed: 25 tests.
- Full Mini-OGAS verification passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api auth runtime tests passed: 5 tests.
- Central-api config tests passed: 3 tests.
- Central-api observability tests passed: 4 tests.
- Central-api node runtime tests passed: 4 tests.
- Node-agent tests passed: 7 tests.
- Dashboard tests passed: 11 files, 42 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 expected Mini-OGAS VMs running, central-api healthy, `nodes_connected=3`, AI runtime connected, VM-mapped nodes aligned with dispatches, and zero active issues.
- Runtime alert workflow check passed through the complete alert, diagnosis, human approval, closure, audit archive, notification acknowledgement, offline-record sync, and live-state preservation path.

Current size after this section:

- `services/central-api/main.py`: 2025 lines.
- `services/central-api/auth_runtime.py`: 77 lines.
- `services/central-api/test_auth_runtime.py`: 93 lines.
- `services/central-api/observability.py`: 115 lines.
- `services/central-api/test_observability.py`: 94 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next good candidates are startup self-check assembly, dashboard-state response assembly, or health payload construction.
2. Add browser-level Playwright checks for the boot animation/login gate so the page cannot reveal the console before self-check completes.
3. Continue splitting `services/dashboard/src/styles.css`; next good candidate is demo/emergency guide styles.
4. Keep strengthening the live runtime contract between VM-backed node heartbeats, AI decisions, human approval, queue cleanup, and log archival.

## 26. 2026-06-05 Startup Preflight Runtime Extraction

This continuation extracted the login-before-console preflight assembly from `services/central-api/main.py`. The goal was to make the boot/self-check screen reflect testable backend state instead of being only a frontend animation.

Work completed:

- Added `services/central-api/preflight_runtime.py`.
- Moved startup self-check response assembly into `build_startup_self_check(...)`:
  - expected parent/child node connectivity
  - VM name mapping and running-state checks
  - work-order to dispatch mapping completeness
  - AI vault locked/unlocked status
  - node runtime summaries for the login preflight screen
- Updated `services/central-api/main.py`:
  - `startup_self_check()` now gathers live state and delegates the response construction to `build_startup_self_check(...)`
  - the previous inline preflight block was removed from the monolith
- Added `services/central-api/test_preflight_runtime.py` with 3 focused tests:
  - all nodes, VMs, dispatches, and AI ready gives `ok`
  - missing nodes or missing VMs gives `warning`
  - locked AI is shown as locked but does not falsely mark physical node/VM preflight as failed
- Updated `scripts/verify-miniogas.ps1` so the preflight runtime tests run in the standard verification path.
- Restored the local runtime stack after the first full verification showed the external runtime was down:
  - started central-api on port 8080
  - started dashboard on port 5173
  - started `miniogas-turning`, `miniogas-milling`, and `miniogas-grinding` VirtualBox VMs
  - waited for all 3 VM-backed node heartbeats
  - unlocked the AI vault through the login probe

Verification after this section:

```powershell
python -m py_compile .\services\central-api\preflight_runtime.py .\services\central-api\main.py .\services\central-api\test_preflight_runtime.py
python .\services\central-api\test_preflight_runtime.py
python .\services\central-api\test_main.py
powershell.exe -ExecutionPolicy Bypass -File .\deploy\setup-miniogas-lab.ps1 -Mode VirtualBox -SkipVirtualBoxInstall
powershell.exe -ExecutionPolicy Bypass -File .\scripts\check-runtime-status.ps1
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Preflight runtime tests passed: 3 tests.
- Central-api route tests passed: 25 tests.
- Full Mini-OGAS verification passed after restoring runtime state.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api auth runtime tests passed: 5 tests.
- Central-api config tests passed: 3 tests.
- Central-api observability tests passed: 4 tests.
- Central-api preflight runtime tests passed: 3 tests.
- Central-api node runtime tests passed: 4 tests.
- Node-agent tests passed: 7 tests.
- Dashboard tests passed: 11 files, 42 tests.
- Dashboard production build passed.
- Runtime check passed with 3/3 VirtualBox VMs running, `nodes_connected=3`, no stale/missing nodes, no VM mismatches, and all node heartbeats reporting `deployment_mode=virtualbox`.
- AI runtime was unlocked through the login probe and reported `deepseek / deepseek-v4-pro / AI_VAULT / connected`.
- Runtime alert workflow check passed through the full alert, AI diagnosis, human approval, closure, audit archival, notification acknowledgement, offline-record sync, and live-state preservation path.

Current size after this section:

- `services/central-api/main.py`: 1957 lines.
- `services/central-api/preflight_runtime.py`: 108 lines.
- `services/central-api/test_preflight_runtime.py`: 114 lines.
- `services/central-api/auth_runtime.py`: 77 lines.
- `services/central-api/observability.py`: 115 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next good candidates are dashboard-state response assembly, health payload construction, or AI diagnosis prompt/result normalization.
2. Add browser-level Playwright checks for the boot animation/login gate, including proof that the console is not visible before preflight completes.
3. Continue splitting `services/dashboard/src/styles.css`; next good candidate is demo/emergency guide styles.
4. Continue strengthening the runtime contract so frontend state visibly follows VM node heartbeats, AI decisions, human approvals, queue cleanup, and audit archives.

## 27. 2026-06-05 Login Gate Browser Verification And Static Guard

This continuation added stronger proof that the startup/login gate hides the system console until preflight and administrator authentication have completed.

Work completed:

- Used Playwright MCP against the live dashboard at `http://127.0.0.1:5173`.
- Captured an accessibility snapshot before login.
- Confirmed the pre-login page exposes only the `管理员验证` region:
  - heading `进入 Mini-OGAS 控制台`
  - completed self-check result rows
  - administrator account/password fields
  - `重新自检`
  - disabled `登录并进入系统` button while the password is empty
- Confirmed protected console content such as factory runtime, order dispatch, alarm handling, and log management did not appear in the pre-login accessibility tree.
- Captured a Playwright screenshot named `miniogas-login-gate-2026-06-05.png` from the live page.
- Strengthened `scripts/check_dashboard_gate.py` so the standard verification now checks:
  - the shell exposes `locked: loginRequired`
  - `StartupGate` is controlled by `v-if="loginRequired"`
  - protected console content stays inside the `v-if="!loginRequired"` block
  - locked shell CSS hides the sidebar with `.shell.locked .sidebar { display: none; }`

Verification after this section:

```powershell
python .\scripts\check_dashboard_gate.py
npm.cmd run test
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Dashboard login gate check passed with the new assertions.
- Dashboard tests passed: 11 files, 42 tests.
- Full Mini-OGAS verification passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Secret scan passed.
- Central-api tests passed: 25 tests.
- Central-api auth runtime tests passed: 5 tests.
- Central-api config tests passed: 3 tests.
- Central-api observability tests passed: 4 tests.
- Central-api preflight runtime tests passed: 3 tests.
- Central-api node runtime tests passed: 4 tests.
- Node-agent tests passed: 7 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, `nodes_connected=3`, AI runtime connected to `deepseek-v4-pro`, no stale/missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through alert creation, confirmation, AI diagnosis, approval, closure, audit archival, notification acknowledgement, offline-record sync, and live-state preservation.

Current status after this section:

- Dashboard URL: `http://127.0.0.1:5173`
- Central API health URL: `http://127.0.0.1:8080/health`
- VirtualBox nodes online:
  - `miniogas-turning`
  - `miniogas-milling`
  - `miniogas-grinding`
- AI runtime: `deepseek / deepseek-v4-pro / AI_VAULT / connected`

Remaining work after this section:

1. Add repeatable Playwright automation as a repository script if browser dependency installation is allowed later; the current evidence is from MCP plus static gate checks.
2. Continue reducing `services/central-api/main.py`; next good candidates are dashboard-state response assembly, health payload construction, or AI diagnosis prompt/result normalization.
3. Continue splitting `services/dashboard/src/styles.css`; next good candidate is demo/emergency guide styles.
4. Continue strengthening visible runtime feedback for AI decisions, human approvals, queue cleanup, and audit archival.

## 28. 2026-06-05 Runtime Status And Dashboard Payload Extraction

This continuation extracted the backend status-bus assembly used by `/health` and `/api/dashboard-state`. This makes the frontend/backend runtime contract easier to test directly: VM availability, node heartbeat freshness, dispatch archival, audit/log list limits, and AI runtime proof now flow through a focused module instead of scattered route code.

Work completed:

- Added `services/central-api/runtime_status.py`.
- Moved health response assembly into `build_health_status(...)`:
  - connected node count
  - stale node list
  - missing expected node list
  - missing VM list
  - connected node to VM mismatch list
  - security metadata for token configuration and request body limit
  - AI runtime and VirtualBox runtime payload passthrough
- Moved dashboard response assembly into `build_dashboard_state(...)`:
  - active issues
  - notifications/log/log-event list limits
  - live node rows
  - work orders and dispatches
  - audit events and node sync records
  - AI runtime and VirtualBox state
  - requested dashboard mode
- Added `dashboard_dispatch_plan(...)` so an archived dispatch approval is converted to a non-action dashboard state instead of remaining visually stuck as a waiting approval.
- Updated `services/central-api/main.py`:
  - `/health` now gathers live dependencies and delegates response construction to `build_health_status(...)`
  - `/api/dashboard-state` now delegates payload construction to `build_dashboard_state(...)`
- Added `services/central-api/test_runtime_status.py` with 4 focused tests:
  - health is `ok` when all expected VM-backed nodes are live
  - health is `degraded` for stale nodes, missing nodes, missing VMs, and VM mismatches
  - archived dispatch plans become dashboard `no_action`
  - dashboard runtime lists are trimmed to their UI limits while preserving mode and latest heartbeat
- Updated `scripts/verify-miniogas.ps1` so runtime status tests run in the standard full verification path.

Verification after this section:

```powershell
python -m py_compile .\services\central-api\runtime_status.py .\services\central-api\main.py .\services\central-api\test_runtime_status.py
python .\services\central-api\test_runtime_status.py
python .\services\central-api\test_main.py
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Runtime status tests passed: 4 tests.
- Central-api route tests passed: 25 tests.
- Full Mini-OGAS verification passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api auth runtime tests passed: 5 tests.
- Central-api config tests passed: 3 tests.
- Central-api observability tests passed: 4 tests.
- Central-api preflight runtime tests passed: 3 tests.
- Central-api runtime status tests passed: 4 tests.
- Central-api node runtime tests passed: 4 tests.
- Node-agent tests passed: 7 tests.
- Dashboard tests passed: 11 files, 42 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, AI runtime connected, no stale/missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through alert creation, confirmation, AI diagnosis, approval, closure, audit archival, notification acknowledgement, offline-record sync, and live-state preservation.

Current size after this section:

- `services/central-api/main.py`: 1919 lines.
- `services/central-api/runtime_status.py`: 108 lines.
- `services/central-api/test_runtime_status.py`: 106 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next good candidates are AI diagnosis prompt/result normalization, alert row/audit diagnosis row builders, or operator action handlers.
2. Continue splitting `services/dashboard/src/styles.css`; next good candidate is demo/emergency guide styles.
3. Strengthen visible runtime feedback for AI decisions, human approvals, queue cleanup, and audit archival.
4. Add repeatable Playwright automation as a repository script when browser dependency installation is allowed.

## 29. 2026-06-05 AI Diagnosis Prompt And Result Normalization Extraction

This continuation strengthened the AI diagnosis chain. The user explicitly wanted the AI to be a real system participant, not a generic question-answer widget; this section makes the prompt inputs, required model output fields, evidence fields, and human-approval boundary testable outside the FastAPI route.

Work completed:

- Added `services/central-api/ai_decision_runtime.py`.
- Moved AI diagnosis pure logic into the new module:
  - `issue_fingerprint_payload(...)`
  - `build_ai_diagnosis_messages(...)`
  - `normalize_ai_decision_payload(...)`
  - required model JSON field list
  - industrial decision system prompt
- Updated `services/central-api/main.py`:
  - `issue_fingerprint(...)` delegates to `issue_fingerprint_payload(...)`
  - `normalize_ai_decision(...)` delegates to `normalize_ai_decision_payload(...)`
  - `call_ai_api(...)` delegates prompt/message construction to `build_ai_diagnosis_messages(...)`
- Added `services/central-api/test_ai_decision_runtime.py` with 3 focused tests:
  - issue fingerprints change when live node context changes
  - AI messages include issue, node heartbeat, work order, recent logs, decision boundaries, evidence field, and operator questions
  - normalized API decisions preserve `api` source, provider, model, generated time, option shape, and confidence
- Fixed a real human-approval boundary bug found by the new test:
  - before: fallback `automation_allowed=True` could survive even when the model output had `requires_human=True`
  - after: if the model does not explicitly set `automation_allowed`, the system derives it from `requires_human`, so high-risk human-review cases are not accidentally marked automation-allowed
- Updated `scripts/verify-miniogas.ps1` so AI decision runtime tests are part of standard verification.

Verification after this section:

```powershell
python -m py_compile .\services\central-api\ai_decision_runtime.py .\services\central-api\main.py .\services\central-api\test_ai_decision_runtime.py
python .\services\central-api\test_ai_decision_runtime.py
python .\services\central-api\test_main.py
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- AI decision runtime tests passed: 3 tests.
- Central-api route tests passed: 25 tests.
- Full Mini-OGAS verification passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api auth runtime tests passed: 5 tests.
- Central-api AI decision runtime tests passed: 3 tests.
- Central-api config tests passed: 3 tests.
- Central-api observability tests passed: 4 tests.
- Central-api preflight runtime tests passed: 3 tests.
- Central-api runtime status tests passed: 4 tests.
- Central-api node runtime tests passed: 4 tests.
- Node-agent tests passed: 7 tests.
- Dashboard tests passed: 11 files, 42 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, AI runtime connected to `deepseek-v4-pro`, no stale/missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through alert creation, confirmation, AI diagnosis, approval, closure, audit archival, notification acknowledgement, offline-record sync, and live-state preservation.

Current size after this section:

- `services/central-api/main.py`: 1873 lines.
- `services/central-api/ai_decision_runtime.py`: 92 lines.
- `services/central-api/test_ai_decision_runtime.py`: 62 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next good candidates are alert row/audit diagnosis row builders, operator action handlers, or alarm issue generation.
2. Continue strengthening visible AI feedback on the frontend, especially showing evidence, options, source, model, and approval result after each decision.
3. Continue splitting `services/dashboard/src/styles.css`; next good candidate is demo/emergency guide styles.
4. Add repeatable Playwright automation as a repository script when browser dependency installation is allowed.

## 30. 2026-06-05 Demo And Emergency Stylesheet Extraction

This continuation reduced the frontend stylesheet monolith by moving the independent demo/emergency command page styles into a dedicated stylesheet. This supports the user's request for a more active, dynamic emergency handling page while keeping the styling maintainable.

Work completed:

- Added `services/dashboard/src/styles/demo.css`.
- Moved demo/emergency styles out of `services/dashboard/src/styles.css`:
  - demo page layout
  - demo header
  - segmented scenario controls
  - demo grid and scenario panels
  - live telemetry strip and flow animation
  - scenario facts and state panels
  - live log and resolved feedback panels
  - AI emergency modal backdrop
  - AI popup panel and header
  - guide status, guide steps, guide audit block
  - maintenance callout
  - treatment option buttons
  - reopen guide button
  - modal-shell transition rules used by the emergency popup
- Updated `services/dashboard/src/main.ts` to import `./styles/demo.css` after `alarm.css` and before the main stylesheet.
- Left shared responsive rules in `styles.css` where they still group demo layout with other application layouts.

Verification after this section:

```powershell
npm.cmd run test
npm.cmd run build
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Dashboard tests passed: 11 files, 42 tests.
- Dashboard production build passed with 36 modules transformed.
- Full Mini-OGAS verification passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api tests passed: 25 tests.
- Central-api auth runtime tests passed: 5 tests.
- Central-api AI decision runtime tests passed: 3 tests.
- Central-api config tests passed: 3 tests.
- Central-api observability tests passed: 4 tests.
- Central-api preflight runtime tests passed: 3 tests.
- Central-api runtime status tests passed: 4 tests.
- Central-api node runtime tests passed: 4 tests.
- Node-agent tests passed: 7 tests.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, AI runtime connected, no stale/missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through alert creation, confirmation, AI diagnosis, approval, closure, audit archival, notification acknowledgement, offline-record sync, and live-state preservation.

Current size after this section:

- `services/dashboard/src/styles.css`: 1352 lines.
- `services/dashboard/src/styles/demo.css`: 479 lines.
- `services/dashboard/src/styles/startup.css`: 305 lines.
- `services/dashboard/src/styles/alarm.css`: 210 lines.

Remaining work after this section:

1. Continue splitting `services/dashboard/src/styles.css`; next good candidates are runtime/factory panels or log-management styles.
2. Continue reducing `services/central-api/main.py`; next good candidates are alert row/audit diagnosis row builders, operator action handlers, or alarm issue generation.
3. Continue strengthening visible AI feedback and human-approval result feedback in the frontend.
4. Add repeatable Playwright automation as a repository script when browser dependency installation is allowed.

## 31. 2026-06-06 API Projection Extraction For Alerts And AI Diagnoses

This continuation extracted the API row projection layer for active alerts and AI diagnosis audit rows. This matters because the frontend alarm page depends on these rows to show what the AI actually diagnosed: source, provider, model, evidence, options, questions, confidence, and whether human approval is required.

Work completed:

- Added `services/central-api/api_projection.py`.
- Moved API presentation logic into the new module:
  - `alert_rows(...)`
  - `diagnosis_summary(...)`
  - `audit_diagnosis_rows(...)`
- Updated `services/central-api/main.py`:
  - `/api/alerts` now delegates to `alert_rows(...)`
  - `/api/audit/diagnoses` now delegates to `audit_diagnosis_rows(...)`
  - `/api/ai/diagnose` payload response now uses `diagnosis_summary(...)`
- Fixed the diagnosis summary separator so root-cause and recommended-action strings use a readable Chinese semicolon instead of the old mojibake separator.
- Added `services/central-api/test_api_projection.py` with 4 focused tests:
  - alert rows deduplicate by node and title
  - alert rows use lifecycle status rather than static issue status
  - resolved alerts expose the correct handler
  - diagnosis audit rows preserve source, provider, model, evidence, options, operator questions, and automation/human-review flags
- Updated `scripts/verify-miniogas.ps1` so API projection tests are part of standard verification.

Verification after this section:

```powershell
python -m py_compile .\services\central-api\api_projection.py .\services\central-api\main.py .\services\central-api\test_api_projection.py
python .\services\central-api\test_api_projection.py
python .\services\central-api\test_main.py
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- API projection tests passed: 4 tests.
- Central-api route tests passed: 25 tests.
- The first full verification attempt had a transient runtime timeout on `/api/dashboard-state` and `/api/alerts`; direct probes immediately afterward returned quickly (`dashboard-state` about 0.18s, `alerts` about 0.07s).
- Re-running the full Mini-OGAS verification passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api auth runtime tests passed: 5 tests.
- Central-api AI decision runtime tests passed: 3 tests.
- Central-api API projection tests passed: 4 tests.
- Central-api config tests passed: 3 tests.
- Central-api observability tests passed: 4 tests.
- Central-api preflight runtime tests passed: 3 tests.
- Central-api runtime status tests passed: 4 tests.
- Central-api node runtime tests passed: 4 tests.
- Node-agent tests passed: 7 tests.
- Dashboard tests passed: 11 files, 42 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, AI runtime connected, no stale/missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through alert creation, confirmation, AI diagnosis, approval, closure, audit archival, notification acknowledgement, offline-record sync, and live-state preservation.

Current size after this section:

- `services/central-api/main.py`: 1823 lines.
- `services/central-api/api_projection.py`: 73 lines.
- `services/central-api/test_api_projection.py`: 106 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next good candidates are operator action handlers, alarm issue generation, or node control actions.
2. Continue splitting `services/dashboard/src/styles.css`; next good candidates are runtime/factory panels or log-management styles.
3. Continue strengthening visible AI feedback and human-approval result feedback in the frontend.
4. Add repeatable Playwright automation as a repository script when browser dependency installation is allowed.

## 32. 2026-06-06 Operator Action Workflow Extraction

This continuation focused on the human/operator disposition chain. The goal was to keep notification acknowledgement, real issue closure, observe decisions, and ignored false alarms clearly separated in code so the system does not regress into the earlier failure mode where a confirmation looked successful but did not actually resolve, archive, or remove anything meaningful.

Work completed:

- Added `services/central-api/operator_actions.py`.
- Extracted pure operator-action helpers:
  - `is_notification_ack(...)`
  - `notification_ack_audit(...)`
  - `close_issue_audit(...)`
  - `close_issue_notification(...)`
  - `observe_issue_audit(...)`
  - `ignore_issue_audit(...)`
- Updated `services/central-api/main.py`:
  - notification IDs such as `NOTICE-*`, `RESULT-*`, `HUMAN-*`, and `DISPATCH-*` are now explicitly classified as notification acknowledgements, not issue closures.
  - real issue closure still requires the lifecycle to be `contained` or `observing`.
  - real issue closure now delegates audit payload and result-notification construction to the new module.
  - observe and ignore decisions now use distinct archive payload builders, keeping `observing` and `ignored_closed` meanings separate.
- Added `services/central-api/test_operator_actions.py` with 3 focused tests:
  - notification IDs are acknowledgements and produce notification-center audit events.
  - real close audit and result notifications expose node/order effects.
  - observe and ignore decisions produce distinct archive meanings.
- Updated `scripts/verify-miniogas.ps1` so operator action tests are part of standard verification.

Verification after this section:

```powershell
python -m py_compile .\services\central-api\operator_actions.py .\services\central-api\main.py
python .\services\central-api\test_operator_actions.py
python .\services\central-api\test_main.py
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Operator action tests passed: 3 tests.
- Central-api route tests passed: 25 tests.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api auth runtime tests passed: 5 tests.
- Central-api AI decision runtime tests passed: 3 tests.
- Central-api API projection tests passed: 4 tests.
- Central-api config tests passed: 3 tests.
- Central-api observability tests passed: 4 tests.
- Central-api preflight runtime tests passed: 3 tests.
- Central-api runtime status tests passed: 4 tests.
- Central-api node runtime tests passed: 4 tests.
- Node-agent tests passed: 7 tests.
- Dashboard tests passed: 11 files, 42 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, AI runtime connected, no stale/missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through alert creation, confirmation, AI diagnosis, approval, closure, audit archival, notification acknowledgement, offline-record sync, and live-state preservation.

Current size after this section:

- `services/central-api/main.py`: 1776 lines.
- `services/central-api/operator_actions.py`: 95 lines.
- `services/central-api/test_operator_actions.py`: 78 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next good candidates are alarm issue generation, node control actions, or high-risk escalation result construction.
2. Continue strengthening visible frontend feedback after human approval and dispatch approval, especially animation timing and log-management discoverability.
3. Continue splitting `services/dashboard/src/styles.css`; next good candidates are runtime/factory panels or log-management styles.
4. Add repeatable Playwright automation as a repository script when browser dependency installation is allowed.

## 41. 2026-06-06 Auto Resolution Archive Extraction

This continuation focused on the automatic resolution path used by `active_issues()`. That path is important to the user's core complaint: resolved items must leave the active alarm queue, produce visible feedback, and be archived with enough metadata for log management. Before this section, `record_auto_resolution()` directly mutated the issue, built the notification, built the audit payload, and built the runtime log message inside `main.py`.

Work completed:

- Added `services/central-api/auto_resolution.py`.
- Extracted pure automatic-resolution helpers:
  - `auto_resolution_note(...)`
  - `mark_issue_auto_resolved(...)`
  - `auto_resolution_notification(...)`
  - `auto_resolution_audit_payload(...)`
  - `auto_resolution_log_message(...)`
- Updated `services/central-api/main.py`:
  - `record_auto_resolution()` now keeps only orchestration state: dedupe, AI decision lookup, resolved timestamp capture, notification insertion, audit archive write, and runtime log insertion.
  - Notification records still use `NOTICE-{issue_id}`, keep `status="resolved"`, preserve node and machine identifiers, and carry the attached AI decision payload.
  - Audit records still archive actor, permission, action, result, source node, issue id, severity, decision source, confidence, and `source="rule-engine"`.
  - Runtime log timestamps now reuse the same `resolved_at` value written on the issue, so the issue record and log line cannot drift within one automatic resolution event.
- Added `services/central-api/test_auto_resolution.py` with 6 focused tests:
  - issue `auto_resolution` text takes priority over AI summary.
  - AI summary is used as fallback text.
  - automatic issue marking writes `resolved`, `AI 自动处置`, and the resolved timestamp.
  - notification records preserve source node, machine code, status, id shape, and AI decision object.
  - audit payload includes archive metadata and AI decision effect fields.
  - runtime log message uses the same resolution timestamp as the issue record.
- Updated `scripts/verify-miniogas.ps1` so automatic-resolution tests are part of standard verification.

Verification after this section:

```powershell
python -m py_compile .\services\central-api\auto_resolution.py .\services\central-api\main.py
python .\services\central-api\test_auto_resolution.py
python .\services\central-api\test_main.py
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- New automatic-resolution tests passed: 6 tests.
- Central-api route tests passed: 25 tests.
- Full verification script passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api module test suite passed, including auth, request guard, command planning, AI decision runtime, alarm rules, API projection, config, observability, preflight, runtime status, node runtime, node control, operator actions, automatic resolution, and human escalation.
- Node-agent simulator tests passed: 7 tests.
- Dashboard tests passed: 11 files, 42 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, no stale or missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through fault heartbeat, open alert, confirmation, diagnosis, approval-required state, human approval, closure, audit archival, notification acknowledgement, offline-record archival, and live-state preservation.
- AI vault remained present but locked during verification, which is acceptable for this run because `RequireAiUnlocked` was false; real external model calls still require administrator login.

Current size after this section:

- `services/central-api/main.py`: 1312 lines.
- `services/central-api/auto_resolution.py`: 49 lines.
- `services/central-api/test_auto_resolution.py`: 86 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next good candidates are startup seed data, `ensure_ai_decision()`, or dashboard-state assembly.
2. Strengthen frontend proof that automatic and human resolutions visibly remove items from the alarm queue and appear in log management.
3. Continue splitting dashboard styles; next good candidates are runtime/factory panels or log-management styles.
4. Add repeatable Playwright automation as a repository script when browser dependency installation is allowed.

## 34. 2026-06-06 Alarm Rule Extraction And Multi-Type Alarm Coverage

This continuation focused on the rule-engine side of alarm generation. The user had specifically called out that machine problems felt too uniform and often looked like spindle temperature faults. Earlier code already had several alarm templates, but the logic was embedded in `main.py` and lacked a focused test proving that different physical alarm types remain distinct. This section extracted the rule layer and added direct multi-type coverage.

Work completed:

- Added `services/central-api/alarm_rules.py`.
- Moved rule and alarm projection helpers out of `services/central-api/main.py`:
  - `clean_issue_title(...)`
  - `machine_label(...)`
  - `normalize_alarm_type(...)`
  - `alarm_type_from_text(...)`
  - `issue_id_for(...)`
  - `alarm_issue(...)`
  - `sync_issue(...)`
- Updated `services/central-api/main.py` to import the rule helpers and keep only global-state workflows such as lifecycle, auto-resolution side effects, and active issue aggregation.
- Added `services/central-api/test_alarm_rules.py` with 4 focused tests:
  - alarm type variants normalize correctly.
  - Chinese titles map to the correct alarm types.
  - result-title prefixes are removed before fallback issue-id generation.
  - spindle temperature, vibration, coolant flow, quality drift, and tool-wear alarms produce distinct titles, decisions, and action lists.
  - sync backlog only creates a `SYNC-DELAY` issue when pending records exist.
- Updated `scripts/verify-miniogas.ps1` so alarm rule tests are part of standard verification.

Verification after this section:

```powershell
python -m py_compile .\services\central-api\alarm_rules.py .\services\central-api\main.py
python .\services\central-api\test_alarm_rules.py
python .\services\central-api\test_main.py
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Alarm rule tests passed: 4 tests.
- Central-api route tests passed: 25 tests.
- The first full verification attempt had a transient timeout on protected runtime endpoints; an immediate `deploy/check-miniogas-stack.ps1` rerun passed, and the final full verification rerun passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api auth runtime tests passed: 5 tests.
- Central-api request guard tests passed: 5 tests.
- Central-api AI decision runtime tests passed: 3 tests.
- Central-api API projection tests passed: 4 tests.
- Central-api config tests passed: 3 tests.
- Central-api observability tests passed: 4 tests.
- Central-api preflight runtime tests passed: 3 tests.
- Central-api runtime status tests passed: 4 tests.
- Central-api node runtime tests passed: 4 tests.
- Central-api operator action tests passed: 3 tests.
- Node-agent tests passed: 7 tests.
- Dashboard tests passed: 11 files, 42 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, AI runtime connected, no stale/missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through alert creation, confirmation, AI diagnosis, approval, closure, audit archival, notification acknowledgement, offline-record sync, and live-state preservation.

Current size after this section:

- `services/central-api/main.py`: 1572 lines.
- `services/central-api/alarm_rules.py`: 195 lines.
- `services/central-api/test_alarm_rules.py`: 75 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next good candidates are node control actions or high-risk escalation result construction.
2. Continue strengthening visible frontend feedback after human approval and dispatch approval, especially animation timing and log-management discoverability.
3. Continue splitting `services/dashboard/src/styles.css`; next good candidates are runtime/factory panels or log-management styles.
4. Add repeatable Playwright automation as a repository script when browser dependency installation is allowed.

## 35. 2026-06-06 Node Control Extraction For Isolation And Retirement

This continuation focused on node control actions. These actions are part of the corrected human-management flow: after an alert is confirmed and diagnosed, high-risk decisions such as isolating a node must have an explicit execution effect, update related work orders, advance the issue lifecycle, and write an audit record. The behavior already existed in the route handler; this section extracted the reusable control logic and added direct tests.

Work completed:

- Added `services/central-api/node_control.py`.
- Extracted node-control helpers:
  - `confirmation_required_response(...)`
  - `first_alarm_issue_type(...)`
  - `apply_node_isolation(...)`
  - `isolate_audit_payload(...)`
  - `expected_node_retire_error(...)`
  - `retire_audit_payload(...)`
- Updated `services/central-api/main.py`:
  - `/api/nodes/{node_code}/isolate` now delegates confirmation responses, isolation state changes, affected-order blocking, first-alarm issue type selection, and audit payload construction to `node_control.py`.
  - `/api/nodes/{node_code}/retire` now delegates confirmation responses, expected-node retirement protection, and audit payload construction to `node_control.py`.
  - Route handlers still own global state mutation boundaries such as lifecycle updates, global node dictionaries, dispatch dictionaries, and audit/log insertion.
- Added `services/central-api/test_node_control.py` with 4 focused tests:
  - confirmation-required responses use a consistent API shape.
  - isolating a node blocks both orders assigned to that node and the active order reported by the node.
  - expected core nodes cannot be retired, while workflow-check temporary nodes can be removed.
  - isolation and retirement audit payloads preserve control effects such as blocked orders and removed escalation counts.
- Updated `scripts/verify-miniogas.ps1` so node control tests are part of standard verification.

Verification after this section:

```powershell
python -m py_compile .\services\central-api\node_control.py .\services\central-api\main.py
python .\services\central-api\test_node_control.py
python .\services\central-api\test_main.py
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Node control tests passed: 4 tests.
- Central-api route tests passed: 25 tests.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api auth runtime tests passed: 5 tests.
- Central-api request guard tests passed: 5 tests.
- Central-api AI decision runtime tests passed: 3 tests.
- Central-api alarm rule tests passed: 4 tests.
- Central-api API projection tests passed: 4 tests.
- Central-api config tests passed: 3 tests.
- Central-api observability tests passed: 4 tests.
- Central-api preflight runtime tests passed: 3 tests.
- Central-api runtime status tests passed: 4 tests.
- Central-api node runtime tests passed: 4 tests.
- Central-api operator action tests passed: 3 tests.
- Node-agent tests passed: 7 tests.
- Dashboard tests passed: 11 files, 42 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, AI runtime connected, no stale/missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through alert creation, confirmation, AI diagnosis, approval, closure, audit archival, notification acknowledgement, offline-record sync, and live-state preservation.

Current size after this section:

- `services/central-api/main.py`: 1545 lines.
- `services/central-api/node_control.py`: 75 lines.
- `services/central-api/test_node_control.py`: 74 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next good candidates are high-risk escalation result construction or dispatch plan recalculation.
2. Continue strengthening visible frontend feedback after human approval and dispatch approval, especially animation timing and log-management discoverability.
3. Continue splitting `services/dashboard/src/styles.css`; next good candidates are runtime/factory panels or log-management styles.
4. Add repeatable Playwright automation as a repository script when browser dependency installation is allowed.

## 36. 2026-06-06 Human Escalation Decision Extraction

This continuation focused on the high-risk human approval path. This is the path created by AI diagnosis when an issue requires a human decision. The route already removed approved/rejected items from the escalation queue and wrote notifications/audit events, but the approve/reject result construction was still embedded in `main.py`. This section extracted that decision-shaping logic so the human approval workflow can be tested directly.

Work completed:

- Added `services/central-api/human_escalation.py`.
- Extracted high-risk escalation helpers:
  - `normalize_escalation_decision(...)`
  - `escalation_decision_valid(...)`
  - `confirmation_required(...)`
  - `mark_escalation_decided(...)`
  - `escalation_result(...)`
  - `escalation_audit_payload(...)`
  - `escalation_notification(...)`
- Updated `services/central-api/main.py`:
  - `/api/ops/escalations/{escalation_id}/decision` now delegates approve/reject validation, confirmation-required response shaping, terminal status assignment, result text, audit payloads, and notification payloads to `human_escalation.py`.
  - The route still owns queue mutation, `apply_resolution_effect(...)`, log insertion, archive insertion, and notification insertion.
- Added `services/central-api/test_human_escalation.py` with 5 focused tests:
  - decision normalization and validation.
  - confirmation-required responses mark the item without removing it from the queue.
  - approved and rejected decisions get the correct terminal statuses.
  - approved results preserve execution effects in audit and notification payloads.
  - rejected results use closed semantics and the `human-escalation` source.
- Updated `scripts/verify-miniogas.ps1` so human escalation tests are part of standard verification.

Runtime note:

- The first full verification attempt failed because the local runtime stack was not running: all three VirtualBox VMs were stopped and `central-api` was unreachable.
- Ran `deploy/setup-miniogas-lab.ps1 -Mode VirtualBox -SkipVirtualBoxInstall`, which restarted `central-api`, the dashboard, and the three VMs.
- The setup script reported VirtualBox heartbeats online: 3/3.
- After restart, full verification passed.

Verification after this section:

```powershell
python -m py_compile .\services\central-api\human_escalation.py .\services\central-api\main.py
python .\services\central-api\test_human_escalation.py
python .\services\central-api\test_main.py
powershell.exe -ExecutionPolicy Bypass -File .\deploy\setup-miniogas-lab.ps1 -Mode VirtualBox -SkipVirtualBoxInstall
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Human escalation tests passed: 5 tests.
- Central-api route tests passed: 25 tests.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api auth runtime tests passed: 5 tests.
- Central-api request guard tests passed: 5 tests.
- Central-api AI decision runtime tests passed: 3 tests.
- Central-api alarm rule tests passed: 4 tests.
- Central-api API projection tests passed: 4 tests.
- Central-api config tests passed: 3 tests.
- Central-api observability tests passed: 4 tests.
- Central-api preflight runtime tests passed: 3 tests.
- Central-api runtime status tests passed: 4 tests.
- Central-api node runtime tests passed: 4 tests.
- Central-api node control tests passed: 4 tests.
- Central-api operator action tests passed: 3 tests.
- Node-agent tests passed: 7 tests.
- Dashboard tests passed: 11 files, 42 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, no stale/missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through alert creation, confirmation, AI diagnosis, approval, closure, audit archival, notification acknowledgement, offline-record sync, and live-state preservation.

Current size after this section:

- `services/central-api/main.py`: 1503 lines.
- `services/central-api/human_escalation.py`: 103 lines.
- `services/central-api/test_human_escalation.py`: 88 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next good candidates are dispatch plan recalculation or legacy `/api/ops/issue-command` command planning.
2. Continue strengthening visible frontend feedback after human approval and dispatch approval, especially animation timing and log-management discoverability.
3. Continue splitting `services/dashboard/src/styles.css`; next good candidates are runtime/factory panels or log-management styles.
4. Add repeatable Playwright automation as a repository script when browser dependency installation is allowed.

## 37. 2026-06-06 Dispatch Recalculation And Approval Extraction

This continuation focused on dispatch plan recalculation and approval. The user had previously called out that dispatch approval needed a real entrance, visible effect, and archival behavior. The frontend/backend workflow already passed those checks; this section moved more of the dispatch plan construction and approval execution out of `main.py` and into `dispatch_workflow.py` so the behavior can be tested directly.

Work completed:

- Extended `services/central-api/dispatch_workflow.py`.
- Added dispatch helper functions:
  - `blocked_orders(...)`
  - `warning_node_codes(...)`
  - `healthy_node_codes(...)`
  - `select_dispatch_target_order(...)`
  - `no_action_dispatch_plan(...)`
  - `waiting_dispatch_plan(...)`
  - `apply_dispatch_approval(...)`
- Updated `services/central-api/main.py`:
  - `/api/ops/dispatch-plan/recalculate` now delegates blocked-order selection, warning-node detection, healthy-node detection, no-action plan construction, and waiting-approval plan construction to `dispatch_workflow.py`.
  - `/api/ops/dispatch-plan/approve` now delegates order movement, dispatch-table update, old-heartbeat cleanup, and new-heartbeat assignment to `apply_dispatch_approval(...)`.
  - The route still owns authorization, confirmation checks, source-order lookup, archive insertion, notification insertion, and response construction.
- Expanded `services/central-api/test_dispatch_workflow.py` from 5 to 8 tests:
  - blocked/warning/healthy node helpers.
  - no-action and waiting-approval plan shapes.
  - dispatch approval movement effects on order, dispatches, old heartbeat, and new heartbeat.
- No new verification script step was needed because `test_dispatch_workflow.py` was already part of `scripts/verify-miniogas.ps1`.

Verification after this section:

```powershell
python -m py_compile .\services\central-api\dispatch_workflow.py .\services\central-api\main.py
python .\services\central-api\test_dispatch_workflow.py
python .\services\central-api\test_main.py
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Dispatch workflow tests passed: 8 tests.
- Central-api route tests passed: 25 tests.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api auth runtime tests passed: 5 tests.
- Central-api request guard tests passed: 5 tests.
- Central-api AI decision runtime tests passed: 3 tests.
- Central-api alarm rule tests passed: 4 tests.
- Central-api API projection tests passed: 4 tests.
- Central-api config tests passed: 3 tests.
- Central-api observability tests passed: 4 tests.
- Central-api preflight runtime tests passed: 3 tests.
- Central-api runtime status tests passed: 4 tests.
- Central-api node runtime tests passed: 4 tests.
- Central-api node control tests passed: 4 tests.
- Central-api operator action tests passed: 3 tests.
- Central-api human escalation tests passed: 5 tests.
- Node-agent tests passed: 7 tests.
- Dashboard tests passed: 11 files, 42 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, no stale/missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through alert creation, confirmation, AI diagnosis, approval, closure, audit archival, notification acknowledgement, offline-record sync, and live-state preservation.

Current size after this section:

- `services/central-api/main.py`: 1459 lines.
- `services/central-api/dispatch_workflow.py`: 157 lines.
- `services/central-api/test_dispatch_workflow.py`: 156 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next good candidates are legacy `/api/ops/issue-command` command planning or AI fallback decision construction.
2. Continue strengthening visible frontend feedback after human approval and dispatch approval, especially animation timing and log-management discoverability.
3. Continue splitting `services/dashboard/src/styles.css`; next good candidates are runtime/factory panels or log-management styles.
4. Add repeatable Playwright automation as a repository script when browser dependency installation is allowed.

## 38. 2026-06-06 Legacy Issue Command Planning Extraction

This continuation focused on the legacy `/api/ops/issue-command` route. Earlier frontend work moved real node actions such as isolation to direct API routes, but this compatibility endpoint remained in `main.py` and still mixed natural-language command planning with confirmation semantics. This section extracted it into a small command-planning module and added direct tests so high-risk natural-language commands cannot be mistaken for completed physical operations unless the caller explicitly sends `execute=true`.

Work completed:

- Added `services/central-api/command_planning.py`.
- Extracted command-planning helpers:
  - `command_requires_confirmation(...)`
  - `blocked_command_plan(...)`
  - `command_result(...)`
  - `plan_issue_command(...)`
- Updated `services/central-api/main.py`:
  - `/api/ops/issue-command` now delegates command risk detection and response shaping to `plan_issue_command(...)`.
  - The route remains as a compatibility/planning endpoint and still logs the request.
- Added `services/central-api/test_command_planning.py` with 4 focused tests:
  - high-risk terms such as isolation, shutdown, lock, and transfer require confirmation.
  - high-risk commands are blocked when `execute=false`.
  - low-risk commands can be planned or marked executed according to the explicit `execute` flag.
  - high-risk legacy commands only become `executed` when the caller explicitly sets `execute=true`.
- Updated `scripts/verify-miniogas.ps1` so command planning tests are part of standard verification.

Verification after this section:

```powershell
python -m py_compile .\services\central-api\command_planning.py .\services\central-api\main.py
python .\services\central-api\test_command_planning.py
python .\services\central-api\test_main.py
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Command planning tests passed: 4 tests.
- Central-api route tests passed: 25 tests.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api auth runtime tests passed: 5 tests.
- Central-api request guard tests passed: 5 tests.
- Central-api AI decision runtime tests passed: 3 tests.
- Central-api alarm rule tests passed: 4 tests.
- Central-api API projection tests passed: 4 tests.
- Central-api config tests passed: 3 tests.
- Central-api observability tests passed: 4 tests.
- Central-api preflight runtime tests passed: 3 tests.
- Central-api runtime status tests passed: 4 tests.
- Central-api node runtime tests passed: 4 tests.
- Central-api node control tests passed: 4 tests.
- Central-api operator action tests passed: 3 tests.
- Central-api human escalation tests passed: 5 tests.
- Node-agent tests passed: 7 tests.
- Dashboard tests passed: 11 files, 42 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, no stale/missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through alert creation, confirmation, AI diagnosis, approval, closure, audit archival, notification acknowledgement, offline-record sync, and live-state preservation.

Current size after this section:

- `services/central-api/main.py`: 1450 lines.
- `services/central-api/command_planning.py`: 29 lines.
- `services/central-api/test_command_planning.py`: 33 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next good candidates are AI fallback decision construction or AI dispatch policy.
2. Continue strengthening visible frontend feedback after human approval and dispatch approval, especially animation timing and log-management discoverability.
3. Continue splitting `services/dashboard/src/styles.css`; next good candidates are runtime/factory panels or log-management styles.
4. Add repeatable Playwright automation as a repository script when browser dependency installation is allowed.

## 39. 2026-06-06 AI Fallback Decision Extraction

This continuation focused on the rule fallback side of AI diagnosis. The user had repeatedly emphasized that AI should visibly participate in diagnosis and decision-making, not behave like a shallow Q&A layer. The live model path already exists, but the fallback path is also important because the system may run while the vault is locked or the model transport is unavailable. This section moved fallback decision construction out of `main.py` and into the AI decision runtime module, where it can be tested alongside prompt construction and API response normalization.

Work completed:

- Extended `services/central-api/ai_decision_runtime.py`.
- Added `fallback_ai_decision_payload(...)`.
- Updated `services/central-api/main.py`:
  - `fallback_ai_decision(...)` now delegates structured fallback diagnosis construction to `fallback_ai_decision_payload(...)`.
  - `main.py` now only supplies runtime identity and generation time.
  - The fallback keeps the same external API shape: source, provider, model, generated time, summary, hypotheses, recommended plan, options, risk assessment, human/automation flags, confidence, evidence, operator questions, and transport error.
- Expanded `services/central-api/test_ai_decision_runtime.py` from 3 to 5 tests:
  - high-risk spindle faults require human approval, block automation, include stop/repair planning, and carry work-order evidence.
  - low-risk fallback issues allow automation, keep the suggested script action as an option, and preserve API error status.

Verification after this section:

```powershell
python -m py_compile .\services\central-api\ai_decision_runtime.py .\services\central-api\main.py
python .\services\central-api\test_ai_decision_runtime.py
python .\services\central-api\test_main.py
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- AI decision runtime tests passed: 5 tests.
- Central-api route tests passed: 25 tests.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api auth runtime tests passed: 5 tests.
- Central-api request guard tests passed: 5 tests.
- Central-api command planning tests passed: 4 tests.
- Central-api alarm rule tests passed: 4 tests.
- Central-api API projection tests passed: 4 tests.
- Central-api config tests passed: 3 tests.
- Central-api observability tests passed: 4 tests.
- Central-api preflight runtime tests passed: 3 tests.
- Central-api runtime status tests passed: 4 tests.
- Central-api node runtime tests passed: 4 tests.
- Central-api node control tests passed: 4 tests.
- Central-api operator action tests passed: 3 tests.
- Central-api human escalation tests passed: 5 tests.
- Node-agent tests passed: 7 tests.
- Dashboard tests passed: 11 files, 42 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, no stale/missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through alert creation, confirmation, AI diagnosis, approval, closure, audit archival, notification acknowledgement, offline-record sync, and live-state preservation.

Current size after this section:

- `services/central-api/main.py`: 1360 lines.
- `services/central-api/ai_decision_runtime.py`: 204 lines.
- `services/central-api/test_ai_decision_runtime.py`: 122 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next good candidates are AI dispatch policy or active issue aggregation side effects.
2. Continue strengthening visible frontend feedback after human approval and dispatch approval, especially animation timing and log-management discoverability.
3. Continue splitting `services/dashboard/src/styles.css`; next good candidates are runtime/factory panels or log-management styles.
4. Add repeatable Playwright automation as a repository script when browser dependency installation is allowed.

## 40. 2026-06-06 Dispatch Authority And AI Dispatch Policy Extraction

This continuation focused on heartbeat-side dispatch effects. The user had previously noted that the frontend must reflect actual backend runtime state, and that dispatch should not be a static display. Two important backend effects were still embedded in `main.py`: central dispatch authority correcting stale heartbeat `active_order` values, and AI dispatch policy blocking or restoring work orders when a node reports a high-risk spindle fault or returns to running.

Work completed:

- Extended `services/central-api/dispatch_workflow.py`.
- Added heartbeat/AI dispatch helpers:
  - `enforce_dispatch_authority(...)`
  - `apply_ai_dispatch_policy_to_orders(...)`
- Updated `services/central-api/main.py`:
  - `apply_dispatch_authority(...)` now delegates active-order correction and dispatch policy assignment to `enforce_dispatch_authority(...)`, then writes returned warning logs.
  - `apply_ai_dispatch_policy(...)` now delegates work-order blocking/restoration to `apply_ai_dispatch_policy_to_orders(...)`, then writes returned runtime log messages.
  - The heartbeat route still owns global node storage and timestamping.
- Expanded `services/central-api/test_dispatch_workflow.py` from 8 to 12 tests:
  - central dispatch overwrites stale heartbeat active orders.
  - no central dispatch clears stale heartbeat active orders.
  - spindle faults block matching work orders and running heartbeats restore them.
  - non-spindle faults do not accidentally block work orders.
- Fixed a boundary issue found during route tests:
  - `Heartbeat.alarms` is a list of dicts in the current FastAPI/Pydantic model, so `main.py` now accepts both dict alarms and model alarms when passing data to the dispatch policy helper.

Verification after this section:

```powershell
python -m py_compile .\services\central-api\dispatch_workflow.py .\services\central-api\main.py
python .\services\central-api\test_dispatch_workflow.py
python .\services\central-api\test_main.py
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Dispatch workflow tests passed: 12 tests.
- Central-api route tests passed: 25 tests.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api auth runtime tests passed: 5 tests.
- Central-api request guard tests passed: 5 tests.
- Central-api command planning tests passed: 4 tests.
- Central-api AI decision runtime tests passed: 5 tests.
- Central-api alarm rule tests passed: 4 tests.
- Central-api API projection tests passed: 4 tests.
- Central-api config tests passed: 3 tests.
- Central-api observability tests passed: 4 tests.
- Central-api preflight runtime tests passed: 3 tests.
- Central-api runtime status tests passed: 4 tests.
- Central-api node runtime tests passed: 4 tests.
- Central-api node control tests passed: 4 tests.
- Central-api operator action tests passed: 3 tests.
- Central-api human escalation tests passed: 5 tests.
- Node-agent tests passed: 7 tests.
- Dashboard tests passed: 11 files, 42 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, no stale/missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through alert creation, confirmation, AI diagnosis, approval, closure, audit archival, notification acknowledgement, offline-record sync, and live-state preservation.

Current size after this section:

- `services/central-api/main.py`: 1331 lines.
- `services/central-api/dispatch_workflow.py`: 212 lines.
- `services/central-api/test_dispatch_workflow.py`: 215 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next good candidates are active issue aggregation side effects or initial runtime seed data.
2. Continue strengthening visible frontend feedback after human approval and dispatch approval, especially animation timing and log-management discoverability.
3. Continue splitting `services/dashboard/src/styles.css`; next good candidates are runtime/factory panels or log-management styles.
4. Add repeatable Playwright automation as a repository script when browser dependency installation is allowed.

## 33. 2026-06-06 Request Guard Extraction And Security Boundary Tests

This continuation focused on the HTTP request guard. The original objective included several security and observability issues: public paths, token checks, request body limits, request IDs, and request logging. Earlier work had already implemented those behaviors in `main.py`; this section extracted the guard decision logic into a pure module so the security boundary can be tested directly instead of only through broad route tests.

Work completed:

- Added `services/central-api/request_guard.py`.
- Extracted pure request-guard helpers:
  - `request_id_from_headers(...)`
  - `cors_response_headers(...)`
  - `request_body_too_large(...)`
  - `is_open_path(...)`
  - `guard_rejection(...)`
- Updated `services/central-api/main.py`:
  - middleware now delegates request ID generation, CORS early-response headers, body-size rejection, public-path detection, unconfigured-token rejection, and invalid-token rejection to `request_guard.py`.
  - middleware still records request logs with level and request ID and still attaches `X-Request-ID` to both early rejections and normal responses.
- Added `services/central-api/test_request_guard.py` with 5 focused tests:
  - login/root/index/static paths are open while protected API paths are not.
  - oversized and invalid content-length values are rejected.
  - OPTIONS and public login paths are allowed without token.
  - protected paths fail closed when token is missing or unconfigured, and pass with the correct token.
  - CORS headers are only added for allowed origins.
- Updated `scripts/verify-miniogas.ps1` so request guard tests are part of standard verification.

Verification after this section:

```powershell
python -m py_compile .\services\central-api\request_guard.py .\services\central-api\main.py
python .\services\central-api\test_request_guard.py
python .\services\central-api\test_main.py
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Request guard tests passed: 5 tests.
- Central-api route tests passed: 25 tests.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api auth runtime tests passed: 5 tests.
- Central-api AI decision runtime tests passed: 3 tests.
- Central-api API projection tests passed: 4 tests.
- Central-api config tests passed: 3 tests.
- Central-api observability tests passed: 4 tests.
- Central-api preflight runtime tests passed: 3 tests.
- Central-api runtime status tests passed: 4 tests.
- Central-api node runtime tests passed: 4 tests.
- Central-api operator action tests passed: 3 tests.
- Node-agent tests passed: 7 tests.
- Dashboard tests passed: 11 files, 42 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, AI runtime connected, no stale/missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through alert creation, confirmation, AI diagnosis, approval, closure, audit archival, notification acknowledgement, offline-record sync, and live-state preservation.

Current size after this section:

- `services/central-api/main.py`: 1765 lines.
- `services/central-api/request_guard.py`: 72 lines.
- `services/central-api/test_request_guard.py`: 97 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next good candidates are alarm issue generation, node control actions, or high-risk escalation result construction.
2. Continue strengthening visible frontend feedback after human approval and dispatch approval, especially animation timing and log-management discoverability.
3. Continue splitting `services/dashboard/src/styles.css`; next good candidates are runtime/factory panels or log-management styles.
4. Add repeatable Playwright automation as a repository script when browser dependency installation is allowed.

## 42. 2026-06-06 Immediate Frontend Archive Feedback

This continuation focused on the user's repeated complaint that solved items appeared to stay in the alarm/approval area and that the system did not visibly change after human handling. The backend already archived several actions, but two high-value API paths did not return the archive row to the frontend, and the frontend only refreshed audit data asynchronously. That made a successful close or escalation decision feel like it had no immediate log-management result.

Work completed:

- Updated `services/central-api/main.py`:
  - `POST /api/issues/{issue_id}/actions` now returns the `audit_event` created by `close_issue_audit(...)`.
  - `POST /api/ops/escalations/{id}/decision` now returns the `audit_event` created by `escalation_audit_payload(...)`.
  - These routes still update lifecycle, apply resolution effects, remove alarms through resolved-issue filters, insert result notifications, and archive audit records as before.
- Updated `services/central-api/test_main.py`:
  - close-flow tests now assert the returned `audit_event.issue_id` and `audit_event.source`.
  - AI escalation approval tests now assert the returned human-escalation audit event.
  - manual escalation decision tests now assert the returned `audit_event.source`.
- Updated `services/dashboard/src/useAlarmWorkflow.ts`:
  - added `mergeReturnedAuditEvent(...)`.
  - local audit state now immediately absorbs returned archive events for node isolation, observation, ignore/close decisions, and human escalation decisions.
  - duplicate audit rows are removed by `id`, with the newest returned event placed at the top, matching log-management reading order.
- Updated `services/dashboard/src/useAlarmWorkflow.test.ts`:
  - added coverage that returned archive events are inserted at the top and existing rows with the same id are replaced.

Verification after this section:

```powershell
python -m py_compile .\services\central-api\main.py
python .\services\central-api\test_main.py
npm.cmd run test -- useAlarmWorkflow.test.ts
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Central-api route tests passed: 25 tests.
- Targeted alarm workflow frontend tests passed: 5 tests.
- Full verification script passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Dashboard tests passed: 11 files, 43 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, no stale or missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through fault heartbeat, alert open, confirmation, diagnosis, approval-required state, human approval, closure, audit archival, notification acknowledgement, offline-record archival, and live-state preservation.
- AI vault remained present but locked during verification, acceptable for this run because `RequireAiUnlocked` was false.

Current size after this section:

- `services/central-api/main.py`: 1320 lines.
- `services/dashboard/src/useAlarmWorkflow.ts`: 347 lines.
- `services/dashboard/src/useAlarmWorkflow.test.ts`: 62 lines.

Remaining work after this section:

1. Add a frontend integration test around close/ignore/escalation actions with mocked API responses to prove queue removal, selection update, and log insertion together.
2. Continue strengthening visible animation timing for cards moving from alarm queue to archived feedback.
3. Continue reducing `services/central-api/main.py`; next candidates are `ensure_ai_decision()` and startup seed data.
4. Continue splitting dashboard CSS into smaller view-specific files.

## 43. 2026-06-06 Alarm Workflow Integration Tests

This continuation completed the first remaining item from section 42: proving the alarm workflow behavior at composable level instead of only checking small helper functions. The goal was to lock down the user-visible behavior after a successful operation: the active queue must shrink, selected alarm must move to the next item, returned archive rows must appear in log-management state immediately, and refresh calls must still run afterward.

Work completed:

- Updated `services/dashboard/src/useAlarmWorkflow.test.ts`.
- Added mocked `operationsApi` coverage for the alarm workflow composable.
- Added test scaffolding for realistic `ApiAlert`, `Alarm`, `AuditEvent`, and escalation queue state.
- Added integration-style tests for:
  - `closeAlarm(...)`: verifies `closeIssue(...)` is called, the closed alarm is removed from `apiAlerts`, selection advances to the next alarm, returned `audit_event` is inserted into `auditEvents`, success feedback mentions log archival, and dashboard/audit/alarm refresh hooks run.
  - `ignoreAlarm(...)`: verifies `decideIssue(..., "ignore", ...)` is called, the ignored alarm is removed, selection advances, returned audit row appears before refresh completes, and feedback says the item was closed and archived.
  - `decideEscalation(..., "approve")`: verifies the human escalation API is called with the confirmation code, the escalation queue is cleared, the matching alert is removed, selection advances, confirmation code is deleted, the human escalation audit row is inserted, resolved-effect feedback is recorded, and live logs show the human decision.
- Kept existing helper-level tests for `actionsForAlarm(...)` and `mergeReturnedAuditEvent(...)`.

Verification after this section:

```powershell
npm.cmd run test -- useAlarmWorkflow.test.ts
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Targeted alarm workflow tests passed: 8 tests.
- Full verification script passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api and node-agent module tests passed.
- Dashboard tests passed: 11 files, 46 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, no stale or missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through fault heartbeat, alert open, confirmation, diagnosis, approval-required state, human approval, closure, audit archival, notification acknowledgement, offline-record archival, and live-state preservation.
- AI vault remained present but locked during verification, acceptable for this run because `RequireAiUnlocked` was false.

Current size after this section:

- `services/dashboard/src/useAlarmWorkflow.test.ts`: 271 lines.

Remaining work after this section:

1. Continue strengthening visible animation timing for cards moving from alarm queue to archived feedback.
2. Add a small visual/log-management status affordance if archived rows are updated locally before the next server refresh finishes.
3. Continue reducing `services/central-api/main.py`; next candidates are `ensure_ai_decision()` and startup seed data.
4. Continue splitting dashboard CSS into smaller view-specific files.

## 44. 2026-06-06 Alarm Page Archive Feedback

This continuation improved the visible frontend behavior after an alarm is resolved. Section 43 proved state transitions in tests, but the alarm page still did not surface the recent resolved-effects stream directly inside the alarm handling workspace. That meant an operator could close or ignore a problem and only see a brief text message, while the stronger "this item was archived" trail lived elsewhere.

Work completed:

- Updated `services/dashboard/src/useAlarmWorkflow.ts`:
  - added a bounded resolved-effect insertion helper.
  - `closeAlarm(...)` now records a visible resolved-effect entry containing time, alarm title, machine, and "验证关闭".
  - `ignoreAlarm(...)` now records a visible resolved-effect entry containing time, alarm title, machine, and "忽略关闭".
  - the existing human escalation path still records its resolved-effect feedback.
- Updated `services/dashboard/src/AlarmManagementView.vue`:
  - added `resolvedEffects` as a prop.
  - added a "处置反馈 / 已归档结果" panel in the alarm handling page.
  - the panel uses `TransitionGroup name="resolved-list"` so new archive results animate into place.
- Updated `services/dashboard/src/App.vue`:
  - passes the shared `resolvedEffects` state into `AlarmManagementView`.
- Updated `services/dashboard/src/styles/alarm.css`:
  - added scoped alarm-page archive feedback styles.
  - each archive row uses the existing `resolved-flash` keyframe so operators can see the state change without a separate modal.
- Updated `services/dashboard/src/useAlarmWorkflow.test.ts`:
  - close-flow test now asserts a "验证关闭" resolved-effect entry.
  - ignore-flow test now asserts a "忽略关闭" resolved-effect entry.

Verification after this section:

```powershell
npm.cmd run test -- useAlarmWorkflow.test.ts
npm.cmd run build
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Targeted alarm workflow tests passed: 8 tests.
- Dashboard production build passed.
- Full verification script passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api and node-agent module tests passed.
- Dashboard tests passed: 11 files, 46 tests.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, no stale or missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through fault heartbeat, alert open, confirmation, diagnosis, approval-required state, human approval, closure, audit archival, notification acknowledgement, offline-record archival, and live-state preservation.
- AI vault remained present but locked during verification, acceptable for this run because `RequireAiUnlocked` was false.

Current size after this section:

- `services/dashboard/src/useAlarmWorkflow.ts`: 359 lines.
- `services/dashboard/src/AlarmManagementView.vue`: 249 lines.
- `services/dashboard/src/styles/alarm.css`: 236 lines.
- `services/dashboard/src/useAlarmWorkflow.test.ts`: 273 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next candidates are `ensure_ai_decision()` and startup seed data.
2. Continue splitting dashboard CSS into smaller view-specific files.
3. Add browser-level screenshot or Playwright coverage for the alarm archive panel once browser automation is available in the active tool context.
4. Continue auditing AI unlock/runtime behavior against the final objective before claiming completion.

## 45. 2026-06-06 AI Decision Cache Runtime Extraction

This continuation addressed the backend AI decision path. The goal objective explicitly asks that AI participation be real, inspectable, and not merely a question-answer widget. Previous sections had already added real/fallback AI decision payloads, AI escalation, and audit projections. This section reduced `main.py` responsibility around `ensure_ai_decision()` by extracting the fingerprint/cache/log-message decision boundary into `ai_decision_runtime.py`.

Work completed:

- Updated `services/central-api/ai_decision_runtime.py`:
  - added `ai_decision_log_message(...)`.
  - added `resolve_ai_decision_with_cache(...)`.
  - the helper computes the issue fingerprint from issue, node heartbeat, and work order context.
  - cache hits return the previous decision without calling the AI transport again and without generating a duplicate log message.
  - cache misses call the provided AI decision function, store fingerprint plus decision, and return a structured runtime log message.
- Updated `services/central-api/main.py`:
  - `ensure_ai_decision(...)` now delegates cache/fingerprint behavior to `resolve_ai_decision_with_cache(...)`.
  - `main.py` keeps only orchestration: resolve issue context, write returned log messages to runtime logs, trim log buffer, and return the decision.
- Updated `services/central-api/test_ai_decision_runtime.py`:
  - added coverage for cache hit reuse.
  - added coverage for cache miss storage and log message generation.
  - added direct coverage for the AI decision log message shape.

Verification after this section:

```powershell
python -m py_compile .\services\central-api\ai_decision_runtime.py .\services\central-api\main.py
python .\services\central-api\test_ai_decision_runtime.py
python .\services\central-api\test_main.py
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- AI decision runtime tests passed: 8 tests.
- Central-api route tests passed: 25 tests.
- Full verification script passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api and node-agent module tests passed.
- Dashboard tests passed: 11 files, 46 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, no stale or missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through fault heartbeat, alert open, confirmation, diagnosis, approval-required state, human approval, closure, audit archival, notification acknowledgement, offline-record archival, and live-state preservation.
- AI vault remained present but locked during verification, acceptable for this run because `RequireAiUnlocked` was false.

Current size after this section:

- `services/central-api/main.py`: 1323 lines.
- `services/central-api/ai_decision_runtime.py`: 228 lines.
- `services/central-api/test_ai_decision_runtime.py`: 179 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next good candidate is startup seed data and static runtime fixtures.
2. Continue splitting dashboard CSS into smaller view-specific files.
3. Add browser-level screenshot or Playwright coverage for the alarm archive panel once browser automation is available in the active tool context.
4. Continue auditing AI unlock/runtime behavior against the final objective before claiming completion.

## 46. 2026-06-06 Runtime Seed Data Extraction

This continuation reduced the central API "god file" by extracting static startup fixtures. The original objective called out a large backend store/module that mixed database, simulation, scheduling, alerting, AI, and demo concerns. In this repository shape, `services/central-api/main.py` was carrying a similar burden. Previous sections extracted behavior modules; this section moved startup work orders, node heartbeat templates, startup logs, node dispatch seed records, and the initial dispatch plan into a dedicated seed module.

Work completed:

- Added `services/central-api/runtime_seed.py`.
- Extracted seed factories:
  - `seed_logs(...)`
  - `seed_work_orders()`
  - `seed_node_heartbeats()`
  - `seed_node_dispatches(...)`
  - `seed_dispatch_plan()`
- Seed factories return fresh mutable copies, so runtime mutation of work orders, node heartbeats, dispatch steps, or nested route/production structures does not mutate the module templates.
- Updated `services/central-api/main.py`:
  - startup logs now come from `seed_logs(...)`.
  - startup work orders now come from `seed_work_orders()`.
  - startup node heartbeats now come from `seed_node_heartbeats()`.
  - startup dispatch records now come from `seed_node_dispatches(...)`.
  - the default dispatch plan now comes from `seed_dispatch_plan()`.
- Added `services/central-api/test_runtime_seed.py` with 5 focused tests:
  - startup log event uses supplied time and standard startup message.
  - work order seed returns fresh copies.
  - node heartbeat seed aligns with work order assignments and returns fresh nested data.
  - node dispatch seed delegates to the dispatch record builder with `ai_auto_dispatch`.
  - dispatch plan seed returns fresh steps and starts in `not_calculated`.
- Updated `scripts/verify-miniogas.ps1` so runtime seed tests are part of standard verification.

Verification after this section:

```powershell
python -m py_compile .\services\central-api\runtime_seed.py .\services\central-api\main.py
python .\services\central-api\test_runtime_seed.py
python .\services\central-api\test_main.py
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Runtime seed tests passed: 5 tests.
- Central-api route tests passed: 25 tests.
- Full verification script passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api module tests passed, including the new runtime seed tests.
- Node-agent simulator tests passed.
- Dashboard tests passed: 11 files, 46 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, no stale or missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through fault heartbeat, alert open, confirmation, diagnosis, approval-required state, human approval, closure, audit archival, notification acknowledgement, offline-record archival, and live-state preservation.
- AI vault remained present but locked during verification, acceptable for this run because `RequireAiUnlocked` was false.

Current size after this section:

- `services/central-api/main.py`: 1232 lines.
- `services/central-api/runtime_seed.py`: 136 lines.
- `services/central-api/test_runtime_seed.py`: 72 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next candidates are auth vault helpers or route grouping.
2. Continue splitting dashboard CSS into smaller view-specific files.
3. Add browser-level screenshot or Playwright coverage for the alarm archive panel once browser automation is available in the active tool context.
4. Continue auditing AI unlock/runtime behavior against the final objective before claiming completion.

## 47. 2026-06-06 AI Vault Auth Runtime Extraction

This continuation focused on the authentication and AI vault boundary. The objective includes security concerns around API keys, default tokens, secret scanning, and real AI deployment. Previous work had already added a password-protected vault and login-time unlock. This section moved vault payload decoding and validation out of `main.py` and into `auth_runtime.py`, where it can be tested directly.

Work completed:

- Updated `services/central-api/auth_runtime.py`:
  - added vault defaults for provider/model/base URL.
  - added `unlocked_ai_config_from_payload(...)`.
  - added `unlock_ai_vault_payload(...)`.
  - the helper checks vault file presence, parses JSON, delegates decryption, validates the API key with an injected validator, normalizes provider/model/base URL, and fails closed on missing or invalid key material.
- Updated `services/central-api/main.py`:
  - `unlock_ai_vault(...)` now delegates vault read/decrypt/validate/config normalization to `unlock_ai_vault_payload(...)`.
  - `main.py` now only applies the returned runtime state to `unlocked_ai_api_key`, `unlocked_operator`, and `unlocked_ai_config`, then records the operator unlock log.
- Updated `services/central-api/test_auth_runtime.py`:
  - added coverage for vault default config normalization.
  - added coverage for valid vault decrypt/validate/normalize flow.
  - added coverage for missing vault file and invalid API key failure.
  - replaced test fake key literals that looked like real `sk-...` secrets with a non-secret `test-key-...` prefix after secret scan correctly flagged the test string.

Verification after this section:

```powershell
python -m py_compile .\services\central-api\auth_runtime.py .\services\central-api\main.py
python .\services\central-api\test_auth_runtime.py
python .\services\central-api\test_main.py
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Auth runtime tests passed: 8 tests.
- Central-api route tests passed: 25 tests.
- Full verification script passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed after replacing fake `sk-...` test literals.
- Central-api module tests passed.
- Node-agent simulator tests passed.
- Dashboard tests passed: 11 files, 46 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, no stale or missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through fault heartbeat, alert open, confirmation, diagnosis, approval-required state, human approval, closure, audit archival, notification acknowledgement, offline-record archival, and live-state preservation.
- AI vault remained present but locked during verification, acceptable for this run because `RequireAiUnlocked` was false.

Current size after this section:

- `services/central-api/main.py`: 1232 lines.
- `services/central-api/auth_runtime.py`: 108 lines.
- `services/central-api/test_auth_runtime.py`: 152 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next candidates are route grouping or startup smoke-test helper extraction.
2. Continue splitting dashboard CSS into smaller view-specific files.
3. Add browser-level screenshot or Playwright coverage for the alarm archive panel once browser automation is available in the active tool context.
4. Continue auditing AI unlock/runtime behavior against the final objective before claiming completion.

## 48. 2026-06-06 Node Agent Runtime Config And Request Boundary

This continuation audited the node-agent portion of the objective. The original objective mentions a Go node-agent with `fmt.Printf`, context cancellation, duplicated default tokens, and SQLite no-op behavior. Current repository evidence shows there are no `.go` files under `mini-ogas`; the active node-agent implementation is `services/node-agent/simulator.py`. It already emits JSON-line structured logs, requires `OGAS_API_TOKEN`, persists SQLite heartbeats, sends `X-Request-ID`, and syncs offline records. This section improved the remaining active Python simulator boundaries instead of editing non-existent Go files.

Work completed:

- Updated `services/node-agent/simulator.py`:
  - added `parse_positive_int(...)` for environment integer parsing.
  - `HEARTBEAT_SEC` and `EMERGENCY_AFTER_TICKS` now use positive integer parsing.
  - added `validate_startup_config(...)`; startup fails closed if `OGAS_API_TOKEN` is missing, `LOCAL_DB_PATH` is empty, or heartbeat interval is invalid.
  - added `build_json_request(...)` to centralize central API URL construction, JSON encoding, `X-OGAS-Token`, and `X-Request-ID` generation.
  - `send_heartbeat(...)`, `sync_pending_records(...)`, and `fetch_dispatch(...)` now use the common request builder.
  - startup failure logging now reports an `errors` list in structured JSON.
- Updated `services/node-agent/test_simulator.py`:
  - added config parsing tests for invalid and zero integer values.
  - added startup config validation coverage for missing token.
  - added request-builder coverage for auth header, request ID, content type, URL, and JSON body.
  - node-agent tests increased from 7 to 10.
- Updated `services/node-agent/README.md`:
  - replaced the stale "Recommended implementation: Go" note with the current Python simulator implementation.
  - documented that `OGAS_API_TOKEN` is required and the agent fails closed if it is missing.
  - documented JSON-line logs and outbound request ID/auth headers.

Verification after this section:

```powershell
python -m py_compile .\services\node-agent\simulator.py .\services\node-agent\test_simulator.py
python .\services\node-agent\test_simulator.py
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Node-agent tests passed: 10 tests.
- Full verification script passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api module tests passed.
- Dashboard tests passed: 11 files, 46 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, no stale or missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through fault heartbeat, alert open, confirmation, diagnosis, approval-required state, human approval, closure, audit archival, notification acknowledgement, offline-record archival, and live-state preservation.
- AI vault remained present but locked during verification, acceptable for this run because `RequireAiUnlocked` was false.

Current size after this section:

- `services/node-agent/simulator.py`: 460 lines.
- `services/node-agent/test_simulator.py`: 188 lines.
- `services/node-agent/README.md`: 53 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next candidates are route grouping or startup smoke-test helper extraction.
2. Continue splitting dashboard CSS into smaller view-specific files.
3. Add browser-level screenshot or Playwright coverage for the alarm archive panel once browser automation is available in the active tool context.
4. Continue auditing AI unlock/runtime behavior against the final objective before claiming completion.

## 49. 2026-06-06 Startup AI Smoke Test Extraction

This continuation extracted the login-time AI startup smoke test from `services/central-api/main.py`. The objective requires that the login page/self-check connect nodes, prepare the AI API, and clearly distinguish real AI API availability from rule fallback. The behavior already existed, but it was embedded in the main route file. This section moved the decision summary and log-message construction into `preflight_runtime.py` so it can be tested directly.

Work completed:

- Updated `services/central-api/preflight_runtime.py`:
  - added `startup_ai_smoke_issue()`.
  - added `ai_smoke_log_message(...)`.
  - added `build_ai_startup_smoke_test(...)`.
  - the helper builds the fixed startup issue context, calls the injected AI function, reports `ok=True` only when the decision source is `api` and status is `connected` or `api_normalized`, returns the provider/model/summary/error payload consumed by login, and returns the runtime log line.
- Updated `services/central-api/main.py`:
  - `ai_startup_smoke_test()` now delegates to `build_ai_startup_smoke_test(...)`.
  - `main.py` keeps only orchestration: call helper, insert returned log message, trim log buffer, return login payload.
- Updated `services/central-api/test_preflight_runtime.py`:
  - added coverage for the startup smoke issue context.
  - added coverage for real API success.
  - added coverage for rule-fallback/locked state as `ok=False`.
  - preflight runtime tests increased from 3 to 6.

Verification after this section:

```powershell
python -m py_compile .\services\central-api\preflight_runtime.py .\services\central-api\main.py
python .\services\central-api\test_preflight_runtime.py
python .\services\central-api\test_main.py
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Preflight runtime tests passed: 6 tests.
- Central-api route tests passed: 25 tests.
- Full verification script passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api module tests passed.
- Node-agent tests passed: 10 tests.
- Dashboard tests passed: 11 files, 46 tests.
- Dashboard production build passed.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, no stale or missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through fault heartbeat, alert open, confirmation, diagnosis, approval-required state, human approval, closure, audit archival, notification acknowledgement, offline-record archival, and live-state preservation.
- AI vault remained present but locked during verification, acceptable for this run because `RequireAiUnlocked` was false.

Current size after this section:

- `services/central-api/main.py`: 1212 lines.
- `services/central-api/preflight_runtime.py`: 148 lines.
- `services/central-api/test_preflight_runtime.py`: 162 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next candidates are route grouping or AI diagnosis route helper extraction.
2. Continue splitting dashboard CSS into smaller view-specific files.
3. Add browser-level screenshot or Playwright coverage for the alarm archive panel once browser automation is available in the active tool context.
4. Continue auditing AI unlock/runtime behavior against the final objective before claiming completion.

## 50. 2026-06-06 Log Management CSS Extraction

This continuation reduced the dashboard stylesheet monolith. The objective called out the large frontend stylesheet as a maintainability problem. Previous work had already split startup, alarm, and demo styles. This section moved log-management-specific styles into their own stylesheet while preserving the existing visual language.

Work completed:

- Added `services/dashboard/src/styles/logs.css`.
- Moved log-management styles out of `services/dashboard/src/styles.css`:
  - `.logs-layout`
  - `.log-archive-panel` table formatting
  - `.log-metrics`
  - `.log-timeline`
  - `.node-sync-archive`
  - the log-layout mobile breakpoint
- Updated `services/dashboard/src/main.ts` to import `./styles/logs.css` with the other view-specific styles.
- Kept the existing typography, borders, spacing, and animation behavior unchanged.

Verification after this section:

```powershell
npm.cmd run test
npm.cmd run build
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Dashboard tests passed: 11 files, 46 tests.
- Dashboard production build passed.
- Full verification script passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api module tests passed.
- Node-agent tests passed: 10 tests.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, no stale or missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through fault heartbeat, alert open, confirmation, diagnosis, approval-required state, human approval, closure, audit archival, notification acknowledgement, offline-record archival, and live-state preservation.
- AI vault remained present but locked during verification, acceptable for this run because `RequireAiUnlocked` was false.

Current size after this section:

- `services/dashboard/src/styles.css`: 1239 lines.
- `services/dashboard/src/styles/logs.css`: 117 lines.
- `services/dashboard/src/main.ts`: 9 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next candidates are route grouping or AI diagnosis route helper extraction.
2. Continue splitting dashboard CSS into smaller view-specific files, especially factory/runtime or dispatch styles.
3. Add browser-level screenshot or Playwright coverage for the alarm archive panel once browser automation is available in the active tool context.
4. Continue auditing AI unlock/runtime behavior against the final objective before claiming completion.

## 51. 2026-06-06 Dispatch CSS Extraction

This continuation continued reducing the dashboard stylesheet monolith. Section 50 extracted log-management CSS; this section extracted the order/dispatch view styles into a dedicated file while preserving the existing UI and behavior.

Work completed:

- Added `services/dashboard/src/styles/dispatch.css`.
- Moved dispatch/order-specific styles out of `services/dashboard/src/styles.css`:
  - `.order-layout`
  - `.route`
  - dispatch-page `.priority` background
  - `.progress-cell`
  - `meter`
  - `.dispatch-panel p`
  - `.decision-stack`
  - `.dispatch-steps`
  - the order-layout mobile breakpoint
- Updated `services/dashboard/src/main.ts` to import `./styles/dispatch.css` with the other view-specific styles.
- Kept shared button, table, panel, and generic status-pill rules in `styles.css` so shared UI primitives remain centralized.

Verification after this section:

```powershell
npm.cmd run test
npm.cmd run build
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Dashboard tests passed: 11 files, 46 tests.
- Dashboard production build passed.
- Full verification script passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api module tests passed.
- Node-agent tests passed: 10 tests.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, no stale or missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through fault heartbeat, alert open, confirmation, diagnosis, approval-required state, human approval, closure, audit archival, notification acknowledgement, offline-record archival, and live-state preservation.
- AI vault remained present but locked during verification, acceptable for this run because `RequireAiUnlocked` was false.

Current size after this section:

- `services/dashboard/src/styles.css`: 1183 lines.
- `services/dashboard/src/styles/dispatch.css`: 60 lines.
- `services/dashboard/src/main.ts`: 10 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next candidates are route grouping or AI diagnosis route helper extraction.
2. Continue splitting dashboard CSS into smaller view-specific files, especially factory/runtime styles.
3. Add browser-level screenshot or Playwright coverage for the alarm archive panel once browser automation is available in the active tool context.
4. Continue auditing AI unlock/runtime behavior against the final objective before claiming completion.

## 52. 2026-06-06 Factory Runtime CSS Extraction

This continuation continued the frontend maintainability cleanup by extracting the factory runtime and parent-child node status view styles from the global dashboard stylesheet. The change keeps the live factory view, AI/node evidence panel, and recent event stream visually unchanged while making the CSS ownership match the Vue view boundary.

Work completed:

- Added `services/dashboard/src/styles/factory.css`.
- Moved factory/runtime-specific styles out of `services/dashboard/src/styles.css`:
  - `.factory-layout`
  - `.central-node`
  - `.service-rail`, `.service-node`, and `.service-head`
  - `.workshop-list`, `.workshop-block`, and `.load-meter`
  - `.machine-grid`, `.machine-card`, `.machine-head`, `.machine-metrics`, and `.machine-alarm`
  - `.right-stack`, `.ai-panel`, `.ai-node-summary`, `.ai-section`, `.ai-truth-*`, and `.ai-case`
  - `.coordination-list`, `.approval-list`, and `.event-list`
  - the factory-layout and machine/service mobile breakpoints
- Updated `services/dashboard/src/main.ts` to import `./styles/factory.css`.
- Split the previously combined `.machine-metrics, .alarm-facts` selector so alarm-management facts remain in the shared stylesheet and machine metrics live in the factory stylesheet.
- Kept shared primitives such as `.content-grid`, `.panel`, `.panel-heading`, `.state-pill`, tables, buttons, and global animations in `styles.css`.

Verification after this section:

```powershell
npm.cmd run test
npm.cmd run build
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Dashboard tests passed: 11 files, 46 tests.
- Dashboard production build passed.
- Full verification script passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api module tests passed.
- Node-agent tests passed: 10 tests.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, no stale or missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through fault heartbeat, alert open, confirmation, diagnosis, approval-required state, human approval, closure, audit archival, notification acknowledgement, offline-record archival, and live-state preservation.
- AI vault remained present but locked during verification, acceptable for this run because `RequireAiUnlocked` was false.

Current size after this section:

- `services/dashboard/src/styles.css`: 761 lines.
- `services/dashboard/src/styles/factory.css`: 441 lines.
- `services/dashboard/src/main.ts`: 11 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next candidates are route grouping or AI diagnosis route helper extraction.
2. Continue splitting dashboard CSS into smaller view-specific files if any remaining view-specific blocks are still in `styles.css`.
3. Add browser-level screenshot or Playwright coverage for the alarm archive panel once browser automation is available in the active tool context.
4. Continue auditing AI unlock/runtime behavior against the final objective before claiming completion.

## 53. 2026-06-06 AI Runtime Truth Label Tightening

This continuation addressed a smaller but important trust issue in the AI deployment story. The system already separates three states: vault locked, vault unlocked but smoke test not proven, and real API smoke test passed. However, the sidebar runtime label could still say the model was "unlocked" without making the smoke-test result visible. That could look like the AI was truly running when the live model call had actually failed and the system had fallen back to rules.

Work completed:

- Updated `services/dashboard/src/useStartupWorkflow.ts`.
- Changed `aiRuntimeLabel` so it now distinguishes:
  - `真实 API 已验证` only when `ai_smoke.ok === true`.
  - `调用未通过，规则回退` when the vault is unlocked but smoke proof failed.
  - `已解锁，待调用验证` when the vault is unlocked but no smoke result exists yet.
  - locked/missing vault states as before.
- Added a regression test in `services/dashboard/src/useStartupWorkflow.test.ts` proving that a failed smoke test still unlocks the local system but is visibly marked as fallback rather than being mislabeled as live AI.

Verification after this section:

```powershell
npm.cmd run test -- useStartupWorkflow.test.ts
npm.cmd run build
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Focused startup workflow test passed: 1 file, 4 tests.
- Dashboard production build passed.
- Full verification script passed.
- Dashboard tests passed: 11 files, 47 tests.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api module tests passed.
- Node-agent tests passed: 10 tests.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, no stale or missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through fault heartbeat, alert open, confirmation, diagnosis, approval-required state, human approval, closure, audit archival, notification acknowledgement, offline-record archival, and live-state preservation.
- AI vault remained present but locked during verification, acceptable for this run because `RequireAiUnlocked` was false.

Current size after this section:

- `services/dashboard/src/useStartupWorkflow.ts`: 270 lines.
- `services/dashboard/src/useStartupWorkflow.test.ts`: 172 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; next candidates are route grouping or AI diagnosis route helper extraction.
2. Consider adding a separate verification mode that requires successful administrator unlock plus real AI smoke proof when a valid vault password is available.
3. Add browser-level screenshot or Playwright coverage for the alarm archive panel once browser automation is available in the active tool context.
4. Continue auditing AI unlock/runtime behavior against the final objective before claiming completion.

## 54. 2026-06-06 Strict AI Smoke Verification Gate

This continuation added an explicit verification gate for the user's recurring concern that the AI must be genuinely participating in the system rather than being presented as a decorative question-answer widget. Previous verification could report the vault as locked and still pass because the normal demonstration mode allows rule fallback. This section adds a strict mode that fails unless administrator login unlocks the vault and the startup AI smoke test proves a live API model call.

Work completed:

- Added `scripts/check_ai_smoke.ps1`.
- The new script:
  - Reads the administrator password only from `MINIOGAS_ADMIN_PASSWORD` by default.
  - Posts to `/api/auth/login` to trigger the same backend unlock and smoke-test path used by the real login page.
  - Requires `login.ok === true`.
  - Requires `runtime.vault_unlocked === true`.
  - Requires `ai_smoke.ok === true`.
  - Requires `ai_smoke.source === "api"`.
  - Prints only runtime metadata and smoke-test status, not tokens, passwords, or API keys.
- Updated `scripts/verify-miniogas.ps1` so `-RequireAiUnlocked` now runs the strict smoke script before the full-stack runtime check. This means strict verification can no longer pass merely because the vault file exists.
- Updated `scripts/check-runtime-status.ps1` to stop using the hardcoded `miniogas` administrator password. It now uses `MINIOGAS_ADMIN_PASSWORD`; if the variable is missing, the login probe is skipped and reported explicitly instead of silently attempting a fixed password.

How to use strict AI verification:

```powershell
$env:MINIOGAS_ADMIN_PASSWORD = "<administrator password>"
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1 -RequireAiUnlocked
```

Verification after this section:

```powershell
# Expected failure path when no administrator password is provided:
powershell.exe -ExecutionPolicy Bypass -File .\scripts\check_ai_smoke.ps1

# Runtime status probe without a hardcoded password:
powershell.exe -ExecutionPolicy Bypass -File .\scripts\check-runtime-status.ps1

# Normal full verification:
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- `check_ai_smoke.ps1` failed as expected when `MINIOGAS_ADMIN_PASSWORD` was not set, with the message that the environment variable is required for strict AI smoke verification.
- `check-runtime-status.ps1` passed and reported health/preflight while explicitly showing `login_probe.ok=false` and `MINIOGAS_ADMIN_PASSWORD not set; login probe skipped.`
- Full verification script passed.
- Dashboard tests passed: 11 files, 47 tests.
- Dashboard production build passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api module tests passed.
- Node-agent tests passed: 10 tests.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, no stale or missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through fault heartbeat, alert open, confirmation, diagnosis, approval-required state, human approval, closure, audit archival, notification acknowledgement, offline-record archival, and live-state preservation.
- Strict real-AI success was not proven in this run because no administrator password was present in `MINIOGAS_ADMIN_PASSWORD`; the new gate now reports that condition as a failure instead of masking it.

Current size after this section:

- `scripts/check_ai_smoke.ps1`: 66 lines.
- `scripts/verify-miniogas.ps1`: 153 lines.
- `scripts/check-runtime-status.ps1`: 34 lines.

Remaining work after this section:

1. Run `verify-miniogas.ps1 -RequireAiUnlocked` with a valid `MINIOGAS_ADMIN_PASSWORD` to prove the real DeepSeek/OpenAI-compatible model call end to end.
2. Continue reducing `services/central-api/main.py`; next candidates are route grouping or AI diagnosis route helper extraction.
3. Add browser-level screenshot or Playwright coverage for the alarm archive panel once browser automation is available in the active tool context.
4. Continue auditing AI unlock/runtime behavior against the final objective before claiming completion.

## 55. 2026-06-07 Frontend Partial-Failure Handling And VM Heartbeat Source Audit

This continuation audited the original goal against the current worktree rather than old line numbers. Several old findings are now already addressed in the current code:

- `/api/issues/{issue_id}/actions` exists on the backend and is used by the frontend close/acknowledgement path.
- Node isolation uses the concrete `/api/nodes/{node_code}/isolate` route instead of natural-language `/api/ops/issue-command`.
- Alarm confirmation and human escalation are separate frontend actions.
- Backend `log_events` preserve level/source/request ID, and frontend runtime events no longer rewrite backend events as `info`.
- The current node-agent is Python, not Go; no Go source files exist in `services/`.
- `@vitejs/plugin-vue` is correctly under dashboard `devDependencies`.
- Secret scan is passing and no raw DeepSeek key or runtime token is committed.

Work completed in this section:

- Updated `services/dashboard/src/runtimeState.ts`.
  - Added `JsonResponseLike<T>`.
  - Added `responseToFetchSlot(...)`, which treats a failed JSON parse or non-OK response as a failure for that single endpoint only.
- Updated `services/dashboard/src/App.vue`.
  - `fetchAlarmData()` now parses `/api/alerts`, `/api/audit/diagnoses`, and `/api/ops/escalations` through `responseToFetchSlot(...)`.
  - A bad response body from one endpoint no longer discards successful alarm/diagnosis/escalation data from the other endpoints.
  - `fetchAuditEvents()` no longer marks the whole `central-api` connection offline when only the audit-log endpoint is unavailable.
  - Unexpected alarm-refresh failures now write a live-log message instead of silently dropping context.
- Updated `services/dashboard/src/runtimeState.test.ts`.
  - Added coverage for successful response parsing.
  - Added coverage for bad JSON bodies becoming failed slots.
  - Added coverage for null/non-OK responses.
- Updated `scripts/check_dashboard_gate.py`.
  - Added a static gate forbidding `fetchAuditEvents()` catch blocks from setting `apiAvailable.value = false`.
  - Added a static gate requiring alarm refresh to use `responseToFetchSlot(...)`.
- Restored runtime environment:
  - Started the three registered VirtualBox VMs: `miniogas-turning`, `miniogas-milling`, `miniogas-grinding`.
  - Stopped the host-side `simulator.py` bridge processes after confirming the in-VM agents were sending fresh heartbeats.
  - Confirmed all three current dashboard nodes report `deployment_mode=virtualbox`, VM running true, and fresh `last_seen_sec`.

Why this matters:

- A local log endpoint or malformed optional endpoint response should not make the UI tell the operator that the whole plant backend is disconnected.
- Alarm handling is now closer to a resilient industrial UI: it preserves good data, shows partial degradation through logs, and avoids panic-state false negatives.
- VM proof is now cleaner: the current live heartbeats come from `miniogas-turning`, `miniogas-milling`, and `miniogas-grinding`, not from competing host-side bridge processes.

Verification after this section:

```powershell
npm.cmd run test
npm.cmd run build
python .\scripts\check_dashboard_gate.py
$env:MINIOGAS_ADMIN_PASSWORD = "miniogas"
powershell -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1 -RequireAiUnlocked
```

Observed result:

- Dashboard tests passed: 11 files, 50 tests.
- Dashboard production build passed.
- Dashboard login/static gate passed.
- Full Mini-OGAS verification passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Secret scan and secret-scan tests passed.
- Central-api route tests passed: 29 tests.
- Node-agent tests passed: 10 tests.
- Strict AI smoke check passed on the first attempt:
  - `provider=deepseek`
  - `model=deepseek-v4-pro`
  - `source=api`
  - `vault_unlocked=true`
  - `smoke_ok=true`
- Full-stack runtime check passed:
  - 3/3 VirtualBox VMs running
  - `nodes_connected=3`
  - `deployment_modes`: all three expected nodes are `virtualbox`
  - no stale nodes
  - no missing nodes
  - no VM mismatches
  - dispatch-aligned heartbeats
  - zero active issues
- Runtime alert workflow passed through heartbeat fault, alert open, confirmation, AI diagnosis, approval required, human approval, close, audit archival, notification acknowledgement, offline-record archive, and live-state preservation.

Remaining work after this section:

1. Continue backend decomposition; `services/central-api/main.py` is still large even though many focused modules now exist.
2. Add browser-level verification for the login animation, AI proof panel, alarm archive behavior, dispatch approval archival, and log-management filters.
3. Add explicit degraded-mode verification for one stopped VM and one stale heartbeat.
4. Continue auditing old-objective items against the current codebase before marking the full goal complete.

## 56. 2026-06-06 Strict Runtime Secret Guard And Lightweight AI Startup Probe

This continuation returned to the user's two highest-priority items: the frontend must reflect the real parent/child runtime state, and AI must be honestly deployed rather than presented as a static label. The VM and dashboard-state checks were already passing, but a stricter audit found two reliability gaps:

- Runtime deployment secrets were generated outside source control, but the repo did not yet guard against accidentally committing `miniogas-token.txt`, `.env.node`, or `.env.edge`.
- Strict AI smoke verification could fail even when the key, base URL, and model were valid because startup smoke reused the full industrial diagnosis prompt. `deepseek-v4-pro` sometimes spent more than the old 20-second timeout on that reasoning-heavy prompt.

Work completed:

- Updated `.gitignore`.
  - Added generated runtime secret protections for `.env`, `.env.*`, `.env.node`, `.env.edge`, `miniogas-token.txt`, and nested node/edge env/token files.
- Updated `scripts/check_secrets.py`.
  - Added detection for committed `OGAS_API_TOKEN=...` and `VITE_OGAS_TOKEN=...` assignments.
  - Allows safe placeholders such as `replace_me` and script variable reads such as `$OgasApiToken` or `env("OGAS_API_TOKEN", "")`.
  - Fails if a generated `miniogas-token.txt` appears inside the project tree.
  - Keeps existing checks for the old default token and raw `sk-...` keys.
- Added `scripts/test_check_secrets.py`.
  - Confirms placeholder env examples pass.
  - Confirms a committed runtime token assignment fails.
  - Confirms a generated token file fails.
- Updated `scripts/verify-miniogas.ps1`.
  - Runs the secret-scan unit tests as part of standard verification.
- Updated `scripts/check_ai_smoke.ps1`.
  - Removed the Chinese default operator from the PowerShell script to avoid Windows PowerShell UTF-8 source decoding issues; the script now uses `workshop-supervisor`.
  - Added ASCII-safe JSON body construction for login probes.
  - Added bounded retry support, while still requiring final `ai_smoke.ok=true` and `source=api`.
- Updated `scripts/check-runtime-status.ps1`.
  - Uses the same ASCII-safe login JSON body and ASCII default operator for the optional login probe.
- Updated `services/central-api/preflight_runtime.py`.
  - Added `startup_ai_smoke_messages()` as a lightweight connectivity probe for login-time AI verification.
  - The startup smoke prompt is intentionally tiny and only proves that the model endpoint can respond with JSON.
- Updated `services/central-api/main.py`.
  - Added `call_ai_startup_smoke_api(...)`.
  - `/api/auth/login` still unlocks the vault and runs startup smoke, but now smoke uses the lightweight probe instead of the full alarm-diagnosis prompt.
  - Normal alarm AI diagnosis still uses the full industrial prompt with issue, node, order, logs, evidence, and human-approval boundaries.
- Updated tests:
  - `services/central-api/test_preflight_runtime.py`
  - `services/central-api/test_main.py`

Runtime diagnosis:

- Decrypting the vault with the administrator password confirmed:
  - provider: `deepseek`
  - model: `deepseek-v4-pro`
  - base URL: `https://api.deepseek.com/v1`
  - key present: yes, not printed
- A direct `/models` probe returned `deepseek-v4-flash` and `deepseek-v4-pro`, proving the model name is valid for the configured endpoint.
- A direct minimal `/chat/completions` request completed successfully in about 1.8 seconds.
- The repeated strict-smoke timeout was therefore caused by using the heavy diagnosis prompt for startup proof, not by a missing key, invalid model, or dead network.

Verification after this section:

```powershell
$env:MINIOGAS_ADMIN_PASSWORD = "miniogas"
powershell -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1 -RequireAiUnlocked
```

Observed result:

- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Secret scan tests passed.
- Central-api route tests passed: 29 tests.
- Central-api module tests passed, including auth runtime, request guard, command planning, AI decision runtime, alarm rules, API projection, config, observability, preflight runtime, runtime status, runtime seed, node runtime, node control, operator actions, auto resolution, and human escalation.
- Node-agent tests passed: 10 tests.
- Dashboard tests passed: 11 files, 47 tests.
- Dashboard production build passed.
- Strict AI smoke check passed on the first attempt:
  - `provider=deepseek`
  - `model=deepseek-v4-pro`
  - `source=api`
  - `vault_unlocked=true`
  - `smoke_ok=true`
- Full-stack runtime check passed:
  - 3/3 VirtualBox VMs running
  - `nodes_connected=3`
  - no stale nodes
  - no missing nodes
  - no VM mismatches
  - dashboard-state shows VM-mapped nodes and dispatch-aligned heartbeats
  - zero active issues
- Runtime alert workflow passed through:
  - heartbeat fault
  - alert open
  - confirmation
  - AI diagnosis
  - approval required
  - human approved
  - closed
  - audit archived
  - notification acknowledged
  - offline records archived
  - live state preserved

Current size after this section:

- `services/central-api/main.py`: 1241 lines.
- `services/central-api/test_main.py`: 699 lines.
- `scripts/check_ai_smoke.ps1`: 113 lines.
- `scripts/check_secrets.py`: 150 lines.

Remaining work after this section:

1. Continue reducing `services/central-api/main.py`; it is still too large even though more behavior is now covered by focused modules.
2. Add browser-level Playwright/screenshot verification for the login animation, AI proof panel, alarm queue archival, dispatch approval archival, and log-management page.
3. Add a failure-mode runtime check for one stopped VM and one stale heartbeat so the frontend's degraded-state presentation is proven, not assumed.
4. Consider moving the host-side node-agent bridge into the VirtualBox guests if the project needs the simulation process to literally run inside each VM instead of VM presence plus host bridge telemetry.

## 57. 2026-06-06 Legacy Issue Command Execution Guard

This continuation addressed a remaining risk around the legacy natural-language issue command endpoint. Earlier frontend work stopped using `/api/ops/issue-command` for concrete node operations such as isolation and close actions, but the backend route still accepted `execute: true`. That left a legacy execution path where a token-bearing caller could ask the system to execute a text command without supervisor gating or a confirmation code.

Work completed:

- Updated `services/central-api/command_planning.py`.
- Added `CONFIRMATION_CODE`.
- Added `issue_command_execution_denial(...)`:
  - planning-only requests remain allowed.
  - execution requests require a supervisor/system-admin actor.
  - high-risk execution text such as `隔离`, `停机`, `锁定`, or `转移` requires `CONFIRM`.
- Updated `services/central-api/main.py`.
- Extended `CommandRequest` with `confirmation_code`.
- Updated `/api/ops/issue-command` so it now:
  - rejects execution from non-supervisor actors with `permission_denied`.
  - rejects high-risk execution without `confirmation_code_required`.
  - logs denied command attempts as structured `command-planning` warning events.
  - still allows planning-only use, preserving the legacy planning endpoint for diagnostics.
- Added tests:
  - `services/central-api/test_command_planning.py`
    - supervisor requirement for legacy execution
    - confirmation-code requirement for high-risk execution
  - `services/central-api/test_main.py`
    - route-level permission and confirmation checks for `/api/ops/issue-command`

Verification after this section:

```powershell
python .\services\central-api\test_command_planning.py
python .\services\central-api\test_main.py
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Command planning tests passed: 6 tests.
- Central-api main route tests passed: 28 tests.
- Full verification script passed.
- Dashboard tests passed: 11 files, 47 tests.
- Dashboard production build passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api module tests passed.
- Node-agent tests passed: 10 tests.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, no stale or missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through fault heartbeat, alert open, confirmation, diagnosis, approval-required state, human approval, closure, audit archival, notification acknowledgement, offline-record archival, and live-state preservation.

Current size after this section:

- `services/central-api/command_planning.py`: 51 lines.
- `services/central-api/test_command_planning.py`: 59 lines.
- `services/central-api/main.py`: 1221 lines.
- `services/central-api/test_main.py`: 669 lines.

Remaining work after this section:

1. Run `verify-miniogas.ps1 -RequireAiUnlocked` with a valid `MINIOGAS_ADMIN_PASSWORD` to prove the real DeepSeek/OpenAI-compatible model call end to end.
2. Continue reducing `services/central-api/main.py`; next candidates are route grouping or AI diagnosis route helper extraction.
3. Add browser-level screenshot or Playwright coverage for the alarm archive panel once browser automation is available in the active tool context.
4. Continue auditing AI unlock/runtime behavior against the final objective before claiming completion.

## 58. 2026-06-06 Structured Runtime Log Completion

This continuation revisited the original observability and frontend log-management requirements. Earlier work added `log_events` with levels, sources, and request IDs, and the dashboard now preserves backend log levels. A follow-up audit found remaining backend paths still writing directly to the legacy `logs` list, which meant those events were visible as plain text but not available to the structured log-management view or level/source filters.

Work completed:

- Updated `services/central-api/main.py`.
- Replaced all remaining direct `logs.insert(...)` and `del logs[...]` usage with `append_log(...)`.
- Runtime paths now writing structured events include:
  - administrator AI vault unlock
  - startup AI smoke test
  - resolution-effect state changes
  - AI decision cache refreshes
  - AI diagnosis human-approval queue creation
  - automatic low-risk issue resolution
  - dispatch-authority corrections
  - node isolation
  - dispatch recalculation and approval
  - human escalation approval/rejection
  - legacy issue-command planning
  - observe/ignore operator decisions
  - node heartbeat acceptance
- Fixed the previously garbled AI-diagnosis log text from mojibake to readable Chinese: `AI 诊断生成人工审批项`.
- Added route-level regression coverage in `services/central-api/test_main.py`:
  - `test_issue_command_records_structured_log_event`
  - `test_ai_diagnosis_escalation_uses_structured_readable_log_event`

Why this matters:

- The dashboard log-management page can now rely on `log_events` rather than scraping plain text.
- Log filtering by `level` and `source` has complete backend coverage for operational flows.
- The old plain `logs` list remains populated through `append_log`, so existing dashboard text feed behavior is preserved.

Verification after this section:

```powershell
python .\services\central-api\test_main.py
powershell.exe -ExecutionPolicy Bypass -File .\scripts\verify-miniogas.ps1
```

Observed result:

- Central-api main route tests passed: 27 tests.
- Full verification script passed.
- Dashboard tests passed: 11 files, 47 tests.
- Dashboard production build passed.
- API contract check passed: 25 backend routes, 18 frontend API calls.
- Dashboard login gate check passed.
- Secret scan passed.
- Central-api module tests passed.
- Node-agent tests passed: 10 tests.
- Full-stack runtime check passed with 3/3 VirtualBox VMs running, central-api healthy, `nodes_connected=3`, no stale or missing nodes, no VM mismatches, and zero active issues.
- Runtime alert workflow check passed through fault heartbeat, alert open, confirmation, diagnosis, approval-required state, human approval, closure, audit archival, notification acknowledgement, offline-record archival, and live-state preservation.
- A direct source scan found no remaining `logs.insert` or `del logs` usage in `services/central-api/main.py`.

Current size after this section:

- `services/central-api/main.py`: 1207 lines.
- `services/central-api/test_main.py`: 633 lines.

Remaining work after this section:

1. Run `verify-miniogas.ps1 -RequireAiUnlocked` with a valid `MINIOGAS_ADMIN_PASSWORD` to prove the real DeepSeek/OpenAI-compatible model call end to end.
2. Continue reducing `services/central-api/main.py`; next candidates are route grouping or AI diagnosis route helper extraction.
3. Add browser-level screenshot or Playwright coverage for the alarm archive panel once browser automation is available in the active tool context.
4. Continue auditing AI unlock/runtime behavior against the final objective before claiming completion.

## 59. 2026-06-07 Dashboard VM Runtime Field Compatibility

Status: completed for this increment.

What changed:

- Updated `services/central-api/node_runtime.py`.
- Live dashboard nodes now expose VirtualBox/runtime state in both shapes:
  - nested compatibility: `node.vm.name`, `node.vm.running`, `node.runtime.deployment_mode`
  - flat compatibility: `node.vm_name`, `node.vm_running`, `node.deployment_mode`, `node.simulation_mode`
- Updated `services/dashboard/src/types.ts` so `HostNode` explicitly accepts the flat runtime fields.
- Updated `services/dashboard/src/useRuntimePresentation.ts` so the factory runtime view falls back to flat VM fields when nested runtime data is missing.
- Added backend route coverage in `services/central-api/test_main.py` to assert flat VM/runtime fields are emitted for live VirtualBox nodes.
- Added frontend coverage in `services/dashboard/src/useRuntimePresentation.test.ts` to assert the runtime presentation layer can render flat VM fields.

Why this matters:

- The frontend was already able to read nested `runtime` and `vm` fields, but direct dashboard-state probes and future UI modules could still see empty top-level runtime fields.
- The `/api/dashboard-state` contract now makes parent/child node state unambiguous for the frontend, scripts, and manual diagnostics.
- This reduces the risk that the system appears disconnected when the three VirtualBox node agents are actually alive and heartbeating.

Verification after this section:

```powershell
python -m unittest test_main.CentralApiRouteTests.test_virtualbox_vm_mapping_is_exposed_on_live_nodes
npm.cmd run test -- --run src/useRuntimePresentation.test.ts
python .\scripts\check_dashboard_gate.py
```

Observed result:

- Backend VM mapping route test passed.
- Frontend runtime-presentation test passed: 1 file, 4 tests.
- Dashboard gate passed.
- Full `verify-miniogas.ps1 -RequireAiUnlocked` passed after this change:
  - API contract check passed: 25 backend routes, 18 frontend calls.
  - Secret scan and secret-scan tests passed.
  - Central-api route/module tests passed.
  - Node-agent tests passed.
  - Dashboard tests passed: 11 files, 51 tests.
  - Dashboard production build passed.
  - Strict AI smoke passed with `provider=deepseek`, `model=deepseek-v4-pro`, `source=api`, `vault_unlocked=true`, and `smoke_ok=true`.
  - Full-stack runtime check passed with `nodes_connected=3`, all deployment modes `virtualbox`, no stale nodes, no missing nodes, no VM mismatches, and zero active issues.
  - Runtime alert workflow check passed through alert creation, confirmation, diagnosis, human approval, closure, audit archival, notification acknowledgement, offline-record archival, and live-state preservation.
- After restarting `central-api`, `/api/dashboard-state` reported all three nodes as `status=running`, `deployment_mode=virtualbox`, `simulation_mode=normal`, `vm_running=true`, with fresh heartbeat ages:
  - `turning-workshop-01`
  - `milling-workshop-01`
  - `grinding-workshop-01`

Remaining work after this section:

1. Run the full verification script again after the final set of frontend/backend edits.
2. Continue the larger objective audit for real AI participation, alarm/approval lifecycle behavior, and browser-level UI verification.
