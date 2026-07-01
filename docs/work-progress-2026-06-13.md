# Mini-OGAS Work Progress - 2026-06-13

## Current Objective

Make Mini-OGAS behave like a running industrial management system instead of a static frontend demo. The current focus is the trusted runtime loop:

1. Node agents simulate workshop production.
2. Central API receives heartbeat v2.
3. Dashboard reads a stable snapshot contract.
4. AI runtime is visibly live and tied to diagnosis/operations.
5. Startup scripts launch the same system that tests verify.

## Completed Work

### Project Consolidation

- Consolidated the active project under `D:\New project\mini-ogas`.
- Removed the old C drive project after backup and merge.
- Preserved migration backups under `D:\New project\_migration-backups`.

### v2.2 Contracts and Planning

- Added v2.2 contract and planning documents:
  - `docs/contracts-v2.2.md`
  - `docs/api-compatibility-plan.md`
  - `docs/simulation-contract.md`
  - `docs/test-matrix-v2.2.md`
  - `docs/architecture-debt.md`
  - `docs/mini-ogas-three-stage-phased-implementation.md`

### Heartbeat v2 Pipeline

- Added central API ingestion for `POST /api/node-heartbeats`.
- Store now records v2 runtime, metrics, production, sync, and alarms.
- Dashboard state can expose v2 runtime and production fields.
- Added tests for heartbeat v2 -> dashboard state flow.

### Dashboard Snapshot Adapter

- Added `GET /api/dashboard/snapshot`.
- Snapshot returns stable v2.2 fields: schema version, data source, run, system, nodes, work orders, alerts, dispatch plan, audit, and timeline.
- Snapshot now filters to active production nodes for dashboard runtime truth.

### SimPy Runtime

- `services/node-agent/simulator.py` supports:
  - `SIMULATION_ENGINE=simple|simpy`
  - `SIMULATION_RANDOM_SEED`
  - `OGAS_RUN_ID`
  - `OGAS_SCENARIO_ID`
  - `SIMULATION_SPEED`
- All three production nodes now run SimPy locally:
  - `turning-workshop-01`: `SCN-TURNING-SIMPY-FLOW-001`
  - `milling-workshop-01`: `SCN-MILLING-SIMPY-SINGLE-001`
  - `grinding-workshop-01`: `SCN-GRINDING-SIMPY-FLOW-001`
- Simple simulator fallback remains available by setting `SIMULATION_ENGINE=simple`.

### Frontend Runtime Link

- Dashboard now prefers `/api/dashboard/snapshot` and falls back to `/api/dashboard-state`.
- Added snapshot adapter in `services/dashboard/src/runtimeState.ts`.
- Frontend displays data source, run id, scenario id, simulation time, and simulation engine.
- Runtime rows now expose each node's simulation engine.

### Read-Only Rule Conclusions

- Added `services/central-api/app/rules.py` as a pure snapshot evaluator.
- `GET /api/dashboard/snapshot` now includes `rule_conclusions`.
- `GET /api/rules/conclusions` exposes the same rule output for direct verification.
- Current implemented rules:
  - `RULE-BOTTLENECK-LOW-OUTPUT`
  - `RULE-STARVATION-LOW-WIP`
- Rule conclusions include `rule_id`, `conclusion_id`, node/machine identity, risk level, evidence, recommended actions, source run metadata, and `read_only=true`.
- Factory page now shows rule conclusions in the runtime evidence panel without creating new alarm-queue items.

### AI Rule Explanation

- Added `services/central-api/app/rule_explanation.py` as a pure AI explanation adapter for rule conclusions.
- Added `GET /api/ai/rule-explanation`.
- Behavior:
  - Stable operation with `0` rule conclusions returns a steady-state explanation without calling the live model.
  - Non-empty rule conclusions can be sent to the active live provider, currently DeepSeek, for a structured explanation.
  - Provider failure falls back to a local rule explanation and marks the response as `fallback`.
- Factory page now includes an "AI 规则解释" card that shows:
  - whether the explanation came from a live model, steady-state monitor, or rule fallback
  - prompt digest
  - rule count
  - reasoning
  - recommended actions
- Frontend only refreshes AI explanations when rule evidence changes or the operator manually clicks refresh.

### Controlled Rule Demo Modes

- Added read-only snapshot modes for rule/AI verification:
  - `mode=milling_bottleneck`
  - `mode=grinding_starvation`
- These modes derive from the current live snapshot but override selected WIP/rate/utilization fields in the returned snapshot only.
- They do not mutate `store`, do not create alerts, and do not leave stale alarm-queue items.
- `GET /api/ai/rule-explanation?mode=milling_bottleneck&use_live=false` now proves the rule explanation path without consuming live model quota.

### Low-Risk Command Polling

- Added v2.2.8 command polling routes:
  - `GET /api/agents/{node_code}/commands/pending`
  - `POST /api/agents/{node_code}/commands`
  - `POST /api/commands/{command_id}/result`
- `NodeCommand` now carries command parameters, `claimed_by`, and result message.
- Central command lifecycle now supports:
  - `pending`
  - `claimed`
  - `executed`
  - `verified`
  - `failed`
- Node-agent `simulator.py` now polls central for pending commands.
- The only executable command in this phase is low-risk `set_target_rate`.
- Agent applies `set_target_rate` locally, reports `executed`, and the next heartbeat verifies the target rate before central marks the command `verified`.
- Repeated command polling no longer returns the same claimed command, preventing duplicate execution.

## v2.2 Implementation Degree

Current estimate after the latest check:

| Stage | Status | Implementation Degree |
|---|---:|---:|
| v2.2.0 Contracts | Implemented | 100% |
| v2.2.1 Heartbeat v2 | Implemented | 90% |
| v2.2.2 Dashboard runtime fields | Implemented | 85% |
## 2026-06-14 v2.2.9 part_queue MVP 落实

本轮已把 turning -> milling 的单向零件转移闭环从“计划项”落实为可测试、可运行的数据链路：

- 中心端新增 `PartQueueItem` 模型，字段包含 `part_id`、`order_id`、`product_code`、`current_step`、`status`、`source_node`、`target_node`、`claimed_by`、`claim_token`、`claim_expires_at`、`created_at`、`updated_at`。
- `MemoryStore` 新增 `part_queue`、`part_seq`、`part_completion_watermark`，支持 ready/claimed/completed 状态。
- turning 节点 v2 heartbeat 的 `finished_quantity` 增量会自动生成待 milling 领取的 ready part，单次心跳最多创建 5 个，避免历史产量刷爆队列。
- 中心端新增 agent 路由：
  - `GET /api/part-queue`
  - `POST /api/agents/{node_code}/parts/claim-next`
  - `POST /api/agents/{node_code}/parts/{part_id}/complete`
- claim 采用 `claim_token` 和 `claim_expires_at`；同一 part 在 claimed 状态不会被重复领取。
- claim 过期后会自动释放回 ready，避免 agent 崩溃造成零件永久卡死。
- node-agent `simulator.py` 已接入 milling 节点 part queue 轮询：领取 part、写入本地 active part、若干 tick 后携带 token 回报完成。
- heartbeat 的 `production` 增加 `active_part_id`，active order 优先使用当前 claimed part 的 `order_id`。
- dashboard snapshot 增加 `part_queue` 字段。
- 工厂运行页新增“WIP 转移队列”区块，显示待领料、加工中、已归档数量，以及最近零件从 turning 到 milling 的状态流。

本轮验证结果：

- `services/central-api`: 41 tests passing.
- `services/node-agent`: 21 tests passing.
- `services/dashboard`: 56 tests passing.
- `services/dashboard`: production build passing.

落实后 v2.2.9 完成度：约 80%。仍未完成的部分是跨三工序完整物料链（milling -> grinding）和持久化队列表。

## 2026-06-14 v2.2.9 二段工序链路继续落实

本轮已把 part_queue 从单段 `turning -> milling` 扩展为 `turning -> milling -> grinding`：

- `PartQueueItem` 新增 `parent_part_id`，用于记录 milling 完成后生成 grinding 下游任务的 lineage。
- `complete_claimed_part()` 新增下游工序状态机：
  - milling 完成 A3 产品的 milling step 后，自动生成 `current_step=grinding`、`target_node=grinding-workshop-01` 的 ready part。
  - grinding 完成后不再生成下游加工 part，直接归档为 completed。
- node-agent `poll_part_queue()` 扩展为 milling 与 grinding 都会轮询 part queue。
- Dashboard WIP 转移队列标签从“待铣削”改为“待加工”，避免三工序链路显示误导。
- 中心端 API 测试新增完整 `milling -> grinding` 链路覆盖。
- node-agent 测试新增 grinding 节点自动领取覆盖。

本轮验证结果：

- `services/central-api`: 43 tests passing.
- `services/node-agent`: 22 tests passing.
- `services/dashboard`: 56 tests passing.
- `services/dashboard`: production build passing.
- 运行时 API 冒烟：
  - `PART-00001` milling 完成后生成 `PART-00009` grinding 下游任务。
  - `PART-00009` grinding 完成归档。
- 运行时自动 agent 冒烟：
  - milling agent 自动完成 `PART-00002`，生成 `PART-00011` grinding 下游任务。
  - grinding agent 自动领取 `PART-00011`，状态进入 `claimed`。

落实后 v2.2.9 完成度：约 90%。剩余主要风险是 part queue 仍为内存态，重启后队列历史丢失；这应由 v2.2.10 PostgreSQL shadow write 解决。

## 2026-06-16 v2.2.10 shadow write 初步落实

本轮已启动 v2.2.10 的可运行版本：先用现有 SQLite 持久化通道实现 PostgreSQL 兼容表结构的 shadow writer，保证本机环境无需额外数据库服务也能验证“状态写入与恢复”语义。后续切到 PostgreSQL 时，主要替换连接层和 SQL 参数风格即可。

- `core/database.py` 新增 `part_queue_shadow` 表：
  - 保存 `part_id`、`parent_part_id`、`order_id`、`product_code`、`current_step`、`status`、`source_node`、`target_node`、`claimed_by`、`claim_token`、`claim_expires_at`、`created_at`、`updated_at`。
  - 使用 `part_id` 主键做 upsert，覆盖 ready/claimed/completed 等状态变化。
- `core/database.py` 新增 `command_shadow` 表：
  - 保存 command id、节点、命令类型、风险级别、状态、operator、parameters、claimed_by、result_message、创建/更新时间。
  - command claim、result、approve/reject、heartbeat verified 都会写入 shadow 状态。
- `MemoryStore` 新增：
  - `persist_part_queue_item()`
  - `load_part_queue_shadow()`
  - `persist_command_shadow()`
  - `load_command_shadow()`
- `MemoryStore.__init__()` 在 `PERSIST_ENABLED=true` 时会初始化数据库，并在 seed 后恢复 command 与 part queue shadow 状态。
- `add_command()` 改为按现有最大 command id 递增，避免 shadow 恢复后产生 id 撞车。
- `scripts/start-system.ps1` 已默认设置：
  - `PERSIST_ENABLED=true`
  - `CENTRAL_DB_PATH=<project>/.runtime/central.db`

本轮验证结果：

- `services/central-api`: 44 tests passing.
- `services/node-agent`: 22 tests passing.
- `services/dashboard`: 56 tests passing.
- `services/dashboard`: production build passing.
- 新增测试验证：创建/claim/complete 后的 part queue 可由新的 `MemoryStore` 实例恢复；command claim/result 也可从 shadow 表恢复。
- 运行时冒烟验证：
  - `D:\New project\mini-ogas\.runtime\central.db` 已创建。
  - `part_queue_shadow` 写入 ready 工件。
  - `command_shadow` 写入 `set_target_rate=0.91`，状态到达 `executed`，`claimed_by=milling-workshop-01`，`result_message=shadow smoke applied`。

落实后 v2.2.10 完成度：约 45%。当前是 SQLite-backed shadow write；真正 PostgreSQL 服务、DSN 配置、迁移脚本、运行时健康检查仍未完成。

| v2.2.3 Snapshot adapter | Implemented | 85% |
| v2.2.4 SimPyRuntime | Implemented | 85% |
| v2.2.5 Three-process WIP flow | Partial | 45% |
| v2.2.6 Read-only rule engine | Implemented | 85% |
| v2.2.7 LLM explanation | Implemented | 75% |
| v2.2.8 Low-risk command polling | Implemented initial loop | 70% |
| v2.2.9 part_queue MVP | Implemented two-step loop | 90% |
| v2.2.10 PostgreSQL shadow write | SQLite-backed shadow writer plus health exposure | 55% |

Historical estimate at that time: overall v2.2 degree was approximately 80%.
This estimate is superseded by `docs/v2.2-first-phase-completion.md`, which
records the 2026-06-25 v2.2 first-phase completion evidence.

Main remaining gap:

- The system now has node heartbeats, rules, AI explanation, and low-risk command execution.
- It still lacks a true part queue / material-transfer model, so the three workshop nodes are not yet coupled by real workpiece handoff.
- Central state is still memory-first, but part queue and command shadow state now have SQLite-backed restore and health status exposure.

### Startup and Local Runtime

- `scripts/start-system.ps1` now starts `app.main:app`, matching the tested FastAPI app.
- Local API/node tokens are unified through `miniogas123`.
- `scripts/restart-local-nodes.ps1` copies the latest `simulator.py` into local node directories before starting nodes.
- Node Docker image installs SimPy.
- Process/VirtualBox/cloud edge deployment scripts include simulation config fields.

### Current Runtime Facts

- Dashboard: `http://127.0.0.1:5173`
- Admin password: `miniogas123`
- Snapshot data source: `live`
- AI runtime: `live / deepseek`
- Production nodes: `3/3`
- Production simulation engine: `simpy`

## Verification

Latest verified checks:

- `services/central-api`: 45 tests passing.
- `services/node-agent`: 22 tests passing.
- `services/dashboard`: 56 tests passing.
- Dashboard production build passes.
- Runtime snapshot confirms three production nodes are online and reporting SimPy flow metrics.
- Runtime persistence status confirms `PERSIST_ENABLED=true`, `.runtime\central.db` exists, `part_queue_shadow`, `command_shadow`, `audit_logs`, and `commands` tables are readable.
- Startup preflight and `/api/system/preflight` now expose the `persistence` check.
- Startup process freshness is now verified with `OGAS_SESSION_TOKEN`; stale 8080 listeners are restarted, and `-CheckOnly` validates against `D:\MiniOGAS-VMs\miniogas-session-token.txt`.
- Local SimPy node heartbeats now include the same launch session token as central-api.
- Dashboard node connectivity now prefers the v2.2 snapshot `system.nodes_connected/nodes_expected` fields, avoiding transient `0/3` display when local node arrays have not hydrated yet.
- Runtime rule endpoint is available; normal live SimPy conditions currently produce `0` rule conclusions, which is expected for steady operation.
- Runtime AI rule explanation endpoint is available; normal live SimPy conditions return `steady` without calling the live model.
- Runtime controlled mode check:
  - `mode=normal`: `0` rule conclusions, `0` active alerts.
  - `mode=milling_bottleneck`: `1` bottleneck conclusion, no store mutation.
- Runtime command polling check:
  - command `set_target_rate=0.73` for `milling-workshop-01` reached `verified`.
  - restore command `set_target_rate=1.0` reached `verified`.
  - final normal snapshot shows `milling-workshop-01` target rate restored to `1.0`.

Known non-functional warning:

- Pytest cannot write `.pytest_cache` under `D:\New project\mini-ogas` due a local permission issue. Tests still run and pass.

## Remaining Work

### Immediate

- Continue v2.2.5 by strengthening three-process WIP flow semantics, not only per-node independent metrics.
- Add an end-to-end fixture or operator trigger that proves DeepSeek explains a live rule conclusion without requiring manual heartbeat injection.
- Add PostgreSQL DSN/driver path for v2.2.10 and keep SQLite as local fallback.
- Continue hardening persistence from SQLite local shadow mode toward the planned PostgreSQL path and replay policy.
- Add a real process supervisor for central-api/dashboard/node agents; current startup freshness detection is script-level, not a long-running daemon.

### Next Technical Milestones

- v2.2.6: expand read-only rule coverage beyond bottleneck/starvation and add scenario-level rule fixtures.
- v2.2.7: expand AI explanation into operator workflow decisions and audit logs.
- v2.2.8: expand command manager status and Dashboard timeline projection.
- v2.2.9: remaining polish only; add clearer dashboard grouping by target node if needed.
- v2.2.10: PostgreSQL driver path, migration script, stronger replay policy, and failure-drill tests.

## Risks

- Central state is still mostly in memory; restart loses runtime facts.
- Three SimPy nodes now have a two-step transfer queue; local shadow persistence exists and is visible in preflight/snapshot, but PostgreSQL deployment and replay policy remain unfinished.
- Command polling exists in API shape, and the SimPy node loop handles low-risk command execution; broader command execution and daemon supervision still need hardening.
- Kali red-team VM image exists but is not registered/running.
- Some older compatibility files under `services/central-api/*.py` remain in the repo and can confuse startup paths if scripts are not kept aligned with `app.main:app`.
