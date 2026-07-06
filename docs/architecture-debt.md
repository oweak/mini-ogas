# Mini-OGAS Architecture Debt Register

日期：2026-06-13
阶段：`v2.2.0 契约冻结与债务登记`

## 1. 目的

本文登记 Mini-OGAS 当前架构债务。债务不是立即全部清理，而是先公开、分类、绑定退出条件，避免 v2.2 继续堆叠不可控复杂度。

## 2. 债务分级

| 级别 | 含义 | 处理原则 |
| --- | --- | --- |
| P0 | 阻止系统可信运行 | 当前阶段或下一小阶段优先处理 |
| P1 | 影响后续架构迁移 | v2.2 或 v2.5 必须处理 |
| P2 | 影响可维护性但不阻断运行 | 进入 v2.5 债务清理 |
| P3 | 长期优化 | v3.x 之后处理 |

## 3. 债务清单

### DEBT-001：Dashboard 仍强依赖 legacy dashboard-state

级别：P1
位置：`GET /api/dashboard-state`、Dashboard 多个视图
现象：前端主事实源来自一个综合聚合接口，页面与后端内部结构耦合较强。
风险：后续引入仿真时间、run、scenario、projection 时，前端可能继续混用旧字段和新字段。
处理阶段：v2.2.3 初步缓解，v2.5.1 完成切换。
退出条件：Dashboard 全量读取 `GET /api/dashboard/snapshot`，`dashboard-state` 退为 wrapper。

状态更新（2026-06-26）：已完成。Dashboard 主轮询优先读取
`GET /api/dashboard/snapshot`，`GET /api/dashboard-state` 已改为由
snapshot 反向适配出的兼容 wrapper，并有后端测试验证 wrapper parity。

### DEBT-002：Heartbeat 缺少正式 schema 版本

级别：P1
位置：`services/node-agent/simulator.py`、`services/central-api/main.py`
现象：当前心跳字段可用，但未显式区分 v1/v2。
风险：后续节点升级时容易出现字段含义漂移。
处理阶段：v2.2.1。
退出条件：三个节点稳定上报 `schema_version`、`run_id`、`scenario_id`、`simulation_time`。

### DEBT-003：仿真事实与展示事实边界不够硬

级别：P0
位置：Dashboard 运行展示、node-agent 心跳
现象：此前用户观察到前端像静态系统，不像真实运行系统。
风险：前端可能展示本地推断而不是后端事实。
处理阶段：v2.2.1、v2.2.2、v2.2.3。
退出条件：页面明确显示 `data_source`，并有测试证明运行字段来自 API。

### DEBT-004：规则引擎与处置副作用边界需继续固化

级别：P1
位置：`alarm_rules.py`、`resolution_effects.py`、`alert_lifecycle.py`
现象：规则能生成多类问题，但规则、生命周期、处置效果之间仍依赖约定。
风险：可能出现已处理报警仍在队列、标题重复嵌套、状态不一致。
处理阶段：v2.2.6。
退出条件：每类报警都有测试覆盖：生成、确认、诊断、处置、消失、归档。

### DEBT-005：AI 决策仍与 central-api 主文件耦合较多

级别：P1
位置：`main.py`、`ai_decision_runtime.py`、`ai_runtime.py`
现象：AI runtime 已有模块，但主流程仍在 central-api 中编排。
风险：后续多 AI 角色、ActionCoordinator、fallback 可观测性会膨胀主文件。
处理阶段：v2.5.4、v3.0.7。
退出条件：AI explanation、command proposal、human approval 分离为独立服务/模块边界。

### DEBT-006：Command 还不是标准队列

级别：P1
位置：`command_planning.py`、`POST /api/ops/issue-command`
现象：现在有命令规划和权限拒绝，但还不是节点可拉取的命令队列。
风险：AI/脚本的实际落地感不足，无法体现主机端下发、子节点执行、回报状态。
处理阶段：v2.2.8。
退出条件：低风险命令支持 pending/claimed/executed/failed 状态，node-agent 能拉取并回报。

### DEBT-007：工件/在制品流动模型不足

级别：P1
位置：`work_orders`、`node_dispatches`、node-agent production
现象：工单和节点有 active_order，但缺少 part_queue 表达。
风险：系统看起来像设备状态面板，而不是生产流动管理。
处理阶段：v2.2.9。
退出条件：至少能表达工序输入、输出、转移、阻塞和调度重排。

### DEBT-008：当前事实源主要是内存态

级别：P1
位置：`main.py` 中 `work_orders`、`node_heartbeats`、`audit_events` 等内存结构
现象：重启后运行事实丢失，审计和 replay 能力有限。
风险：不利于真实系统演示、追溯、回放和长期运行。
处理阶段：v2.2.10 shadow write，v2.5.2 主事实源切换。
退出条件：PostgreSQL 成为 heartbeat、audit、command、scenario 的主事实源。

状态更新（2026-06-26）：已完成一项 v2.5.2 前置能力：启动时可从
`heartbeat_shadow` 恢复最新 v2 心跳事实到运行态，避免重启后完全依赖内存。
这仍不是 PostgreSQL 主事实源完成；audit、command、scenario 的主读写切换仍待完成。

状态更新（2026-07-06）：已完成 replay 相关事实的 `run_id` 绑定。`alerts`、
`ai_diagnosis`、`commands`、`audit_logs`、`command_shadow`、`part_queue_shadow`
均新增 `run_id` 持久化列和索引，启动时会对旧 SQLite/PostgreSQL 库做非破坏性迁移。
运行回放优先按 `run_id` 精确读取命令、队列、审计、告警和 AI 诊断，旧数据再退回时间窗口。
这使 DEBT-012 的退出条件基本满足，但 DEBT-008 的“全部主事实源切换”仍需继续推进。

状态更新（2026-07-06）：已完成计划层 shadow 持久化。`production_plan_shadow`、
`dispatch_task_shadow`、`allocation_order_shadow` 已加入 SQLite/PostgreSQL schema，
生成生产计划、重建调度、提交上级调配和批准调度变更时会写入 shadow 表；启动时可恢复到
`MemoryStore`，`persistence_status()` 与 `replay_readiness_report()` 已纳入这些事实。
这继续推进 DEBT-008，但当前仍是“内存读路径 + PostgreSQL shadow/recovery”，不是所有读写
都直接以 PostgreSQL 为唯一主事实源。

状态更新（2026-07-06）：告警、AI 诊断和人工审计运行事实已加入启动恢复链路。`alerts`、`ai_diagnosis`、`audit_logs`
会恢复到 `MemoryStore`；告警确认、AI 诊断、问题关闭、人工决策、节点退役、调度审批和升级审批会把状态或审计事实写回持久化层。
`shadow_consistency_report()` 与 `replay_readiness_report()` 已纳入 alert / AI / audit 覆盖检查。该项继续削减 DEBT-008，
剩余边界仍是把读路径从“内存优先 + PostgreSQL shadow/recovery”推进到 PostgreSQL 主事实源。

### DEBT-009：VirtualBox 状态与生产节点状态容易混淆

级别：P2
位置：`runtime_status.py`、preflight、dashboard runtime 展示
现象：系统同时有 process 节点和 virtualbox 节点概念。
风险：用户可能误以为 VirtualBox 未运行等于节点未运行。
处理阶段：v2.5.8、v3.0.1。
退出条件：节点 deployment_mode 明确，process/virtualbox/edge VM 状态分开展示。

### DEBT-010：攻击实验室尚未形成安全边界

级别：P1
位置：`scripts/kali_redteam_workflow.py`、未来 Kali VM
现象：已有授权红队脚本规划，但 Kali VM 和攻击范围需要隔离。
风险：若边界不清，容易从演示攻击变成不可控破坏。
处理阶段：v3.0.6。
退出条件：Attack Lab 独立网段、白名单目标、可回滚场景、只攻击测试节点。

### DEBT-011：音效、弹窗、动画与后端事件绑定还需统一

级别：P2
位置：Dashboard 告警工作流、sound policy、弹窗动画
现象：前端已有分级音效和动画方向，但需要严格绑定事件生命周期。
风险：启动即报警、音效常开、处置后不消失会破坏可信感。
处理阶段：v2.2.2、v2.2.6。
退出条件：音效只由新告警或状态升级触发，处置关闭有动画并归档。

### DEBT-012：缺少正式 replay 能力

级别：P2
位置：日志、心跳、审计数据
现象：有运行日志和审计，但尚不能按 run/scenario 回放。
风险：无法复盘 AI 决策是否合理，也不利于报告展示。
处理阶段：v2.5.6。
退出条件：可按 `run_id` 回放节点、报警、AI、命令、处置全过程。

状态更新（2026-07-06）：已完成。回放 API 已不再只按心跳时间窗口拼接事实；
新写入的告警、AI 诊断、命令、处置审计和 part queue 记录都会绑定 `run_id`，
`replay_run()` 优先按 `run_id` 重建全过程，并为旧行保留时间窗口兼容路径。

## 4. 债务与阶段映射

| 阶段 | 主要处理债务 |
| --- | --- |
| v2.2.1 | DEBT-002、DEBT-003 |
| v2.2.2 | DEBT-003、DEBT-011 |
| v2.2.3 | DEBT-001、DEBT-003 |
| v2.2.6 | DEBT-004、DEBT-011 |
| v2.2.7 | DEBT-005 |
| v2.2.8 | DEBT-006 |
| v2.2.9 | DEBT-007 |
| v2.2.10 | DEBT-008 |
| v2.5.1 | DEBT-001 |
| v2.5.2 | DEBT-008 |
| v2.5.4 | DEBT-005、DEBT-006 |
| v2.5.6 | DEBT-012 |
| v3.0.1-v3.0.2 | DEBT-009 |
| v3.0.6 | DEBT-010 |
| v3.0.7 | DEBT-005 |

## 5. 当前禁止事项

在债务未清理前，禁止：

1. 删除 `GET /api/dashboard-state`。
2. 强制所有节点一次性升级 heartbeat v2。
3. 把 PostgreSQL 直接切成主事实源。
4. 让 Dashboard 在 API 缺字段时伪造 live 运行事实。
5. 让 AI 直接执行高风险控制动作。
6. 在未隔离环境中运行攻击脚本。

## 6. v2.2.0 验收

本债务登记完成后，v2.2.0 对架构债务的验收标准为：

1. 已登记当前主要债务。
2. 每项债务有级别、位置、风险、处理阶段和退出条件。
3. 已明确哪些债务不能在 v2.2.0 直接动手处理。
4. 后续实现可按本文件逐项消债。
