# Mini-OGAS v2.1 轻量可信闭环方案可行性与缺陷分析

日期：2026-06-12
审查对象：`C:/Users/hq362/Downloads/mini-ogas-v2.1-lean-trusted-loop-plan.md`
对照代码库：`C:/Users/hq362/Documents/New project/mini-ogas`

## 1. 总体结论

v2.1 方案的总体方向是正确的。它把 Mini-OGAS 从“同时追求 VM、NATS、Redis、多 AI、Kali、Pyomo、Mesa、RL 的大而全系统”收敛为“轻量可信闭环”，这是当前项目最需要的路线。方案提出的几个核心原则，如“先可信，后分布式”“先可见，后复杂”“先 HTTP，后 NATS”“LLM 只解释规则结论，不负责数值推理”，都符合当前项目的真实问题。

但是，该方案仍然存在明显缺陷：它虽然口头上反对大而全，但 Phase 1 仍然把 PostgreSQL、SimPy agent、part_queue、dashboard snapshot、timeline、Dashboard 轮询等多个基础设施同时放进一个阶段，实际执行时仍可能变成一次大迁移。对当前代码库而言，这不是小修补，而是数据源、API 契约、存储层、仿真模型和前端视图的系统性迁移。

因此，本报告的判断是：

```text
战略方向：可采用
工程粒度：需要拆小
当前可直接执行程度：中等
全量照单执行风险：高
推荐执行方式：兼容旧系统、逐层双写、逐步迁移
```

v2.1 不应作为“马上全量实现清单”，而应作为“迁移目标架构与约束文档”。实际开发必须先保护当前已经可运行的 central-api、dashboard、node-agent、AI vault 和本地三节点心跳链路，再逐步加入 SimPy、PostgreSQL、part_queue、command polling 和 snapshot API。

## 2. 当前系统对照

当前代码库已经具备以下能力：

- `central-api` 使用 FastAPI，已暴露 `/health`、`/api/auth/status`、`/api/auth/login`、`/api/dashboard-state`、`/api/alerts`、`/api/ai/diagnose`、`/api/node-heartbeats`、`/api/node-records/sync`、调度审批、人工升级、日志归档等接口。
- `dashboard` 使用 Vue 3 / Vite，当前主要通过 `/api/dashboard-state`、`/api/alerts`、`/api/audit/events`、`/api/ops/escalations` 等接口获取运行状态。
- `node-agent` 是 Python 模拟器，使用 SQLite 本地缓存，通过 `/api/node-heartbeats` 上报状态，并支持离线记录补传。
- 系统已有 AI vault、DeepSeek/OpenAI-compatible runtime、真实 API / rule fallback 状态区分。
- 已有 Kali red-team workflow 脚本，但其主要是通过注入心跳、触发告警、调用 AI 诊断和修复动作来模拟攻防闭环。

当前系统尚不具备以下 v2.1 目标能力：

- 没有真正 SimPy Runtime。
- 没有 PostgreSQL 主存储。
- 没有 `part_queue` 表。
- 没有 `/api/agents/{node_id}/commands/pending` 命令轮询。
- 没有 `/api/commands/{command_id}/result` 命令结果上报。
- 没有 `/api/dashboard/snapshot` 新契约。
- 没有完整 `run_id`、`scenario_id`、`event_timeline` 回放体系。
- 没有严格的 `bottleneck_alert` / `starvation_alert` 基于工件流的规则引擎。
- 没有生产节拍、WIP、饥饿、瓶颈之间的真实因果链。

这意味着 v2.1 的大方向可行，但必须承认它是一次架构迁移，不是简单功能补丁。

## 3. 方案优点

### 3.1 定位收敛是正确的

方案明确指出当前不应继续追求“大而全的分布式 AI 工厂大脑”，而应先完成“可观察、可解释、可调控、可验证”的轻量可信闭环。这一点非常关键。当前 Mini-OGAS 最大的问题不是模块少，而是“显示出来的状态是否真的来自后端运行事实”“AI 是否真的参与”“处置动作是否真的改变系统状态”。

### 3.2 LLM 边界划分合理

方案要求规则引擎负责数值判断，LLM 只负责解释。这可以避免模型凭空计算产能、WIP、瓶颈和风险。对于工业管理系统，这是更可信的 AI 部署方式。

### 3.3 HTTP 优先是合理降复杂度

Phase 1-3 使用 HTTP，后续再考虑 NATS，是合理路线。当前项目还处于演示闭环阶段，如果过早引入 NATS、event-worker、Redis，会拉长调试链路，反而降低系统可信度。

### 3.4 Dashboard 提前是正确产品判断

Dashboard 是用户感知系统价值的窗口。方案要求 Dashboard 在 Phase 1 即可看到真实 SimPy 数据，避免长期做底层而前端没有可见成果，这符合当前项目需求。

### 3.5 反对全量重写是正确约束

方案明确要求“任何修改必须保持现有系统尽量可运行，禁止一口气全量重写”。这条必须严格执行，因为当前系统已经有可运行链路，贸然重写会丢掉已有的登录、自检、AI vault、告警处理、日志归档和节点心跳成果。

## 4. 关键缺陷总览

| 编号 | 缺陷 | 严重性 | 影响 |
|---|---|---:|---|
| D1 | Phase 1 范围仍然过大 | 高 | 容易再次变成大迁移，导致现有系统不可用 |
| D2 | 新 API 与当前 API 不兼容 | 高 | dashboard、node-agent、Kali 脚本会断 |
| D3 | PostgreSQL 引入过早且迁移策略不足 | 高 | 存储层替换风险大，测试成本高 |
| D4 | SimPy 模型定义不够完整 | 高 | 仍可能产生“看起来真实但不可验证”的仿真 |
| D5 | part_queue 并发与事务细节不足 | 高 | 可能重复认领、丢件、状态错乱 |
| D6 | 命令轮询缺少幂等和重试语义 | 高 | agent 重启或网络抖动会造成重复执行 |
| D7 | AI explanation 缺少结构化输出契约 | 中高 | 前端可能仍只显示漂亮文字，不能证明 AI 参与 |
| D8 | Verifier 被弱化得过早 | 中高 | “结果可验证”缺少具体判定逻辑 |
| D9 | RunMode 安全边界不足 | 中高 | ATTACK_LAB_MODE 可能污染正常系统或放大安全风险 |
| D10 | Dashboard 组件清单偏抽象 | 中 | 未说明数据 schema、状态层级、错误态细节 |
| D11 | Mock 策略存在表述冲突 | 中 | “不做后端 mock”与“本地 mock 预览”边界需澄清 |
| D12 | 事件 schema 仍缺少版本迁移策略 | 中 | 后续 replay 和兼容会困难 |
| D13 | 健康分规则太粗 | 中 | alert penalty 不足以代表系统健康 |
| D14 | 安全与权限模型不够细 | 中高 | command、kill switch、attack lab 都需要权限边界 |
| D15 | 资源预算偏理想化 | 中 | 4GB central + PostgreSQL + Dashboard + AI 调用可能仍紧 |
| D16 | 缺少测试验收矩阵 | 高 | 无法判断每个阶段是否真的可信闭环 |

## 5. 详细缺陷分析

### D1. Phase 1 范围仍然过大

方案的 Phase 1 同时包含：

```text
central-api
PostgreSQL
SimPy agent
HTTP heartbeat
metrics 入库
part_queue
dashboard snapshot
timeline 初版
Dashboard 3 秒轮询
```

这些任务相互耦合，但每一个本身都可以成为独立阶段。特别是 PostgreSQL、SimPy agent、part_queue 和 dashboard snapshot 都涉及新的事实源。如果同时实施，会出现三个风险：

- 无法判断 bug 来自仿真、存储、API 还是前端。
- 当前 `/api/dashboard-state` 和 `/api/node-heartbeats` 链路可能被破坏。
- 用户短时间内看不到稳定成果。

建议拆分为：

```text
Phase 1A：现有 node-agent 增加 simulation_time / simulation_speed / WIP 字段，仍走 /api/node-heartbeats
Phase 1B：central-api 从现有心跳生成 snapshot adapter，新增 /api/dashboard/snapshot，但不替换旧接口
Phase 1C：SimPyRuntime 接入单节点，保留旧模拟器 fallback
Phase 1D：PostgreSQL 双写，不切主事实源
Phase 1E：part_queue 只处理一个工序链路，先验证 turning → milling
```

### D2. 新 API 与当前实现不兼容

方案建议统一为：

```http
POST /api/agents/{node_id}/heartbeat
GET  /api/agents/{node_id}/commands/pending
POST /api/commands/{command_id}/result
GET  /api/dashboard/snapshot
```

但当前系统大量代码使用：

```http
POST /api/node-heartbeats
GET  /api/dashboard-state
GET  /api/node-dispatches/{node_code}
POST /api/ops/dispatch-plan/recalculate
POST /api/ops/dispatch-plan/approve
```

如果直接替换，当前 dashboard、operationsApi、node-agent、Kali red-team workflow、测试套件都会断。API 命名统一是正确目标，但必须提供兼容层。

建议：

```text
保留 /api/node-heartbeats，内部转发到新的 agent heartbeat handler
新增 /api/agents/{node_id}/heartbeat，但短期只作为别名
保留 /api/dashboard-state，新增 /api/dashboard/snapshot
前端逐页迁移，不一次切换所有页面
为每个旧接口写 deprecation note，但不要立即删除
```

### D3. PostgreSQL 引入过早且迁移策略不足

方案把 PostgreSQL 放入当前最小架构，但当前系统的 node-agent 本地缓存是 SQLite，central-api 也主要依赖内存态和模块化 Python 数据结构。直接引入 PostgreSQL 会带来：

- 本机安装、启动、账号、端口、初始化 schema 的额外复杂度。
- 测试从纯 Python/内存测试变成依赖外部服务。
- 数据迁移、清理、重置演示状态变复杂。
- 演示机器资源占用增加。

PostgreSQL 是必要的中期目标，但不应作为第一刀。更合理的策略：

```text
先定义 Repository 接口
默认 MemoryRepository / SQLiteRepository
PostgresRepository 后置
关键事件先双写到 JSONL 或 SQLite
PostgreSQL 只在 schema 稳定后成为主存储
```

如果坚持 Phase 1 引入 PostgreSQL，至少必须补充：

- schema migration 工具，例如 Alembic。
- 本地初始化脚本。
- 数据重置脚本。
- 测试数据库隔离策略。
- 连接失败时的降级行为。

### D4. SimPy 模型定义不够完整

方案提出产能：

```text
Turning：80/h
Milling：50/h
Grinding：65/h
```

并提出加工时间反推和 `simulation_speed`，这是好方向。但 SimPy 模型还缺很多决定可信度的细节：

- 初始 WIP 数量。
- 每个工序的输入队列容量。
- 批次大小。
- 是否有运输/等待时间。
- 机床故障分布。
- 刀具磨损函数。
- 缺陷率与刀具磨损、温度、负载之间的关系。
- warm-up 时间。
- 随机种子。
- 同一 scenario 下是否可复现。
- agent 重启后业务状态如何恢复。

如果这些不定义，SimPy 虽然听起来比当前模拟器“科学”，但仍可能只是换一种方式生成随机数。

建议增加 `simulation-contract.md`，最少定义：

```text
scenario_id
random_seed
simulation_speed
warmup_duration
operation_cycle_time
machine_count
input_wip_initial
queue_capacity
failure_distribution
quality_distribution
tool_wear_formula
temperature_formula
```

### D5. part_queue 并发与事务细节不足

方案提出用 PostgreSQL 作为工件交接队列，并要求在事务中完成 ready part 查找、锁定、标记 claimed、返回给 agent。这是正确的，但还不够。

缺失点：

- 是否使用 `SELECT ... FOR UPDATE SKIP LOCKED`。
- `claimed` 超时后如何释放。
- agent 拿到 part 后崩溃怎么办。
- 同一 part 是否允许重试。
- `processing` 和 `claimed` 的区别。
- `scrapped` 后是否进入返工。
- 工件跨工序失败后是否进入异常队列。
- part_id 是否全局唯一。
- run_id / scenario_id 是否参与唯一键。

建议 part_queue 状态机明确为：

```text
ready → claimed → processing → completed
                  ↘ failed → ready / scrapped / interrupted
```

并补充：

```text
claim_token
claim_expires_at
attempt_count
last_error
idempotency_key
```

### D6. 命令轮询缺少幂等和重试语义

方案提出：

```text
pending → applied → verified / failed
```

这个状态机够简洁，但 HTTP 轮询无法天然保证 exactly-once。实际情况会出现：

- agent 拉到命令，执行成功，但上报结果失败。
- central-api 重发同一命令。
- agent 重启后重复执行。
- 网络超时导致 central 误判未执行。
- 命令执行后效果不符合预期，但 agent 上报 success。

必须补充：

```text
command_id 全局唯一
agent 保存已执行 command_id
command 带 expected_precondition
command 带 idempotency_key
command result 带 observed_state
central verifier 用 observed_state 判断 verified
超时后进入 expired / retryable_failed
重复 result 必须幂等
```

否则“命令确实能到达 agent，执行后结果能被验证”仍停留在口号层面。

### D7. AI explanation 缺少结构化输出契约

方案规定 LLM 只解释规则引擎结论，但没有定义 AI explanation 的输出 schema。当前系统已经有 `source=api` / `rule_fallback` 区分，如果 v2.1 不延续这种证明机制，会退回“AI 说了一段话”的状态。

建议定义：

```json
{
  "explanation_id": "exp_...",
  "source": "api | rule_fallback",
  "provider": "deepseek",
  "model": "deepseek-v4-pro",
  "rule_ids": ["bottleneck.milling.wip_growth"],
  "evidence_ids": ["metric_...", "event_..."],
  "summary": "...",
  "risk_level": "low | medium | high",
  "recommended_action_id": "cmd_proposal_...",
  "confidence": 0.0,
  "requires_human": true,
  "created_at": "..."
}
```

并要求 Dashboard 显示：

```text
AI 来源
模型名
规则依据
证据摘要
是否真实 API
是否 fallback
```

### D8. Verifier 被弱化得过早

方案说当前不做完整 Verifier，但又要求“agent 执行后结果能被验证”。这两者存在张力。

可以不做复杂 Verifier 服务，但必须有最小 verifier 函数。否则 command result 的 `applied` 很容易被误当成 `verified`。

最小验证策略：

```text
命令：turning target_rate 80 → 65
验证：下一轮 heartbeat 中 target_rate == 65，且 run_id 一致，且 command_id 被 agent 回传

命令：pause node
验证：heartbeat status == paused，且 no new part claimed

命令：isolate node
验证：node status == isolated，且 dispatch 不再分配新工件
```

建议在 Phase 2 就实现 `verify_command_result(command, heartbeat, snapshot)`，不必等完整 Verifier。

### D9. RunMode 安全边界不足

方案定义了 NORMAL_MODE、DEMO_MODE、ATTACK_LAB_MODE、SAFE_MODE，但对权限、token、网络边界、审计策略描述不够细。

尤其是 ATTACK_LAB_MODE：

- 弱 token 可选启用，但没定义 token 生命周期。
- Kali 转发临时允许，但没定义开放哪些端口。
- 攻击模式数据如何不污染 normal run。
- 退出攻击模式后如何撤销 token 和网络规则。
- 攻击注入是否允许触发真实命令。

建议补充：

```text
attack_lab_token 只允许 /api/security-lab/* 或指定注入端点
TTL 默认 15 分钟
只能在 ATTACK_LAB_MODE 下创建
所有请求写入 security_event
退出模式自动吊销 token
attack_lab run_id 与 normal run_id 隔离
攻击模式下 AI 默认只建议，不自动执行
```

### D10. Dashboard 组件清单偏抽象

方案列出：

```text
HealthScoreCard
ProductionFlow
NodeStatusCards
AiDecisionPanel
TimelinePanel
TodoDonePanel
NotificationToast
RunModeBanner
SimulationClockBadge
```

这些组件方向合理，但没有定义每个组件的数据输入和状态来源。对当前项目而言，前端最大风险正是“看起来有组件，但不是后端事实驱动”。

每个组件都应补：

```text
数据来源 API
必要字段
loading 状态
stale 状态
error 状态
fallback 状态
是否允许本地 mock
是否允许本地修改业务状态
```

否则 v2.1 仍可能做出一套漂亮但不可信的 UI。

### D11. Mock 策略存在表述冲突

方案说：

```text
Mock 只作为前端 fixture，不做后端主数据源
```

但 Dashboard 错误态又提到：

```text
进入本地 mock 预览的提示
```

这不是不可行，但必须严格区分：

```text
Live Mode：真实后端数据
Offline Preview：前端 fixture，只用于看布局，不代表系统运行
Replay Mode：来自 event_timeline 的历史真实事件
```

Dashboard 上必须明确显示当前数据源，避免用户把 fixture 当成实时系统。

### D12. 事件 schema 缺少版本迁移策略

方案定义了 event 必带字段，这是正确的。但还缺：

- schema_version 如何演进。
- 老事件如何 replay。
- 字段缺失如何处理。
- event_time 是仿真时间还是真实时间。
- ingest_time 是否单独记录。
- event_id 是 UUID 还是可排序 ID。
- 多 agent 并发事件如何排序。

建议事件基础字段改为：

```text
event_id
schema_version
event_type
run_id
scenario_id
node_id
simulation_time
event_time
ingested_at
sequence
source
payload
```

其中 `simulation_time` 与 `ingested_at` 必须分开，否则 replay 和实时显示会混乱。

### D13. 健康分规则太粗

方案提出：

```text
health_score = 100 - sum(active_alert_penalties)
```

这比魔法数字好，但仍然过粗。健康分只来自 active alerts 会遗漏：

- 数据新鲜度。
- agent stale 时间。
- AI 降级状态。
- command 积压。
- part_queue 积压。
- PostgreSQL 写入延迟。
- replay/live 数据源状态。
- 攻击模式是否开启。

建议健康分至少分为：

```text
production_health
node_connectivity_health
data_freshness_health
ai_runtime_health
command_loop_health
security_mode_health
```

总分可以综合，但 Dashboard 应显示分项，否则用户看见 82 分也不知道哪里有问题。

### D14. 安全与权限模型不够细

方案有 Kill Switch 和 Emergency Stop，但没定义：

- 谁可以触发。
- 是否需要确认码。
- 是否需要二次确认。
- 是否写审计。
- 是否可撤销。
- API token 权限范围。
- agent token 与 dashboard token 是否分离。
- 攻击实验 token 是否隔离。

当前系统已经有管理员登录、`CONFIRM` 确认码、AI vault 解锁、操作日志等基础能力。v2.1 应明确继承这些能力，而不是重新定义一套模糊权限。

建议最小角色：

```text
viewer：只读 dashboard
operator：确认普通告警、查看 AI 建议
supervisor：执行调度变更、隔离、恢复、关闭问题
system_admin：RunMode、Kill Switch、AI vault、attack lab
agent：只允许 heartbeat、claim、command result
attack_lab：只允许安全实验注入端点
```

### D15. 资源预算偏理想化

方案建议：

```text
central：4GB
edge：1.5GB
router：256MB
kali：2GB
```

这个预算可以作为最低演示配置，但不应被写成稳定配置。central 如果同时运行 PostgreSQL、FastAPI、Dashboard 静态服务、SimPy 管理、AI 调用日志和浏览器，4GB 会比较紧。Windows 宿主机 + VirtualBox + Kali 的开销也需要额外考虑。

建议写成：

```text
最低演示配置：4GB central
推荐开发配置：6-8GB central
Kali 仅攻击时启动
PostgreSQL shared_buffers 保守配置
Dashboard 展示用 build 产物，不用 Vite dev server
```

### D16. 缺少测试验收矩阵

方案有验收文字，但缺少可执行测试矩阵。可信闭环必须靠测试证明。

建议每个 Phase 必须附：

```text
单元测试
API 合约测试
仿真确定性测试
前端数据来源测试
端到端脚本
故障注入测试
回归测试
人工演示 checklist
```

例如 Phase 1 至少应有：

```text
给定 random_seed，相同 scenario 产出相同 WIP 曲线
停止 milling agent 后 dashboard 30 秒内显示 stale
turning 完成工件后 part_queue 出现 ready milling part
milling claim-next 不会重复认领同一 part
dashboard snapshot 不读取 mock
```

## 6. 与当前系统的主要差距

### 6.1 数据事实源差距

当前事实源主要来自：

```text
node-agent 生成 heartbeat
central-api 内存态聚合
dashboard-state 返回当前快照
SQLite 只作为 node-agent 离线缓存
```

v2.1 目标事实源是：

```text
SimPy event
PostgreSQL metrics / part_queue / event_timeline
dashboard snapshot
Replay / scenario / run_id
```

迁移必须先做 adapter，不能直接切换。

### 6.2 仿真模型差距

当前 simulator 通过 tick、cycle_time、random、tool_wear、spindle_temp 等逻辑生成生产状态。它有一定工况变化，但不是严格 SimPy 离散事件模型，也没有真实工件跨工序队列。

v2.1 需要的不是“多几个随机报警”，而是：

```text
part 从 turning 进入 milling
milling 处理能力较低导致 WIP 上升
grinding 因输入不足出现 starvation
规则引擎从 WIP 和利用率判断瓶颈/饥饿
命令改变 target_rate 后曲线发生可验证变化
```

这是当前系统最主要缺口。

### 6.3 AI 链路差距

当前系统已有 AI vault 和真实 API smoke，但 AI 主要仍围绕告警诊断、建议和日志说明。v2.1 要求 AI explanation 绑定规则引擎结论和 command proposal。

差距在于：

```text
当前：告警 → AI 诊断 → 人工/自动处置
目标：规则引擎判断瓶颈/饥饿 → AI 解释规则结论 → command proposal → agent 执行 → verifier 验证
```

这需要新增 action proposal / command / verifier 数据结构。

### 6.4 前端差距

当前 Dashboard 已经能显示运行证据、告警、调度、日志和 AI 状态，但还缺：

```text
SimulationClockBadge
ProductionFlow 中的真实 WIP 流动
RunModeBanner
HealthScoreCard 分项健康
因果链视图
command pending/applied/verified 状态
scenario/run 标识
```

前端不是从零开始，但需要从“管理状态看板”升级为“仿真因果链可视化”。

## 7. 推荐修正后的执行路线

### Phase 0：契约冻结

先写文档和契约，不动主链路：

```text
docs/architecture-v2.1.md
docs/contracts-v2.1.md
docs/simulation-contract.md
docs/api-compatibility-plan.md
docs/test-matrix-v2.1.md
```

必须定义：

```text
旧 API 与新 API 的兼容关系
heartbeat v1/v2 schema
snapshot schema
command schema
event schema
simulation_time 与 wall_time
run_id / scenario_id
```

### Phase 1A：现有 heartbeat 加可信仿真字段

不引入 PostgreSQL，不替换 API。

新增字段：

```text
simulation_time
simulation_speed
run_id
scenario_id
wip_input
wip_output
target_rate
actual_rate
utilization
```

Dashboard 先显示这些字段，证明“数据动起来”。

### Phase 1B：SimPyRuntime 嵌入 node-agent

在现有 `simulator.py` 中引入 SimPyRuntime，但输出仍转换成当前 heartbeat payload。这样前端和中心 API 不会断。

验收：

```text
相同 seed 生成相同曲线
不同 scenario 生成不同瓶颈/饥饿模式
Dashboard 不改大结构也能显示新指标
```

### Phase 1C：新增 snapshot adapter

新增 `/api/dashboard/snapshot`，但内部先复用当前 `/api/dashboard-state` 聚合逻辑。目标是让前端有新契约，而不是立即切换所有页面。

### Phase 1D：part_queue 最小闭环

只做 turning → milling，不一次做全三工序。

验收：

```text
turning completed event 创建 ready part
milling claim-next 原子认领
重复 claim 不会拿到同一 part
agent 崩溃后 claim 超时释放或标记 interrupted
```

### Phase 1E：PostgreSQL 双写

先写入 PostgreSQL，但读取仍可来自当前内存态。通过测试确认数据一致后再切读。

### Phase 2A：规则引擎先行

先不接 LLM，规则引擎输出结构化结论：

```text
rule_id
alert_type
evidence
recommended_action
risk_level
requires_human
```

### Phase 2B：LLM explanation 后接

LLM 只能读取规则结论和经过校验的指标摘要。输出必须结构化，并显示 `source=api/rule_fallback`。

### Phase 2C：command polling

先实现低风险命令：

```text
set_target_rate
pause_after_current_part
resume
```

不要一开始做 emergency_stop 和 isolate 的自动执行。

### Phase 3：Verifier、Replay、RunMode

在 command loop 跑通后，再做：

```text
verified/failed 判定
event_timeline
Replay
RunMode
AI kill switch
attack lab 隔离
```

## 8. 优先级建议

### 必须优先

1. API 兼容计划。
2. SimPy 时间模型和 random_seed。
3. heartbeat v2 schema。
4. snapshot schema。
5. rule-engine 结构化输出。
6. command 幂等语义。
7. Dashboard 数据源标识。

### 暂缓

1. PostgreSQL 主存储切换。
2. 完整 VM 分布式。
3. NATS / Redis。
4. Kali 自动攻击实验扩展。
5. Pyomo / Mesa / System Dynamics / RL。
6. 完整多 AI 服务。

### 不建议现在做

1. 全量替换 `/api/dashboard-state`。
2. 删除当前 node-agent。
3. 删除当前告警/日志/AI vault 链路。
4. 一次性重构 central-api 主文件。
5. 把 DEMO_MODE 作为跳过安全检查的捷径。

## 9. 最小验收标准

如果 v2.1 第一阶段完成，至少应证明：

```text
1. Dashboard 显示 simulation_time 和 simulation_speed。
2. 三个节点数据来自 agent heartbeat，不来自前端 mock。
3. WIP 曲线随仿真时间变化。
4. milling 瓶颈可由规则引擎计算出来。
5. grinding 饥饿可由规则引擎计算出来。
6. AI explanation 显示 rule_id、evidence、source、model。
7. 一个低风险 command 能从 central 到 agent。
8. agent 执行后，下一轮 heartbeat 能验证结果。
9. command 和 explanation 都能在 timeline 中追溯。
10. 关闭 agent 后 dashboard 显示 stale/offline。
```

如果做不到这些，就不能声称 v2.1 可信闭环已经跑通。

## 10. 结论

v2.1 方案最有价值的地方，不是它列出的 PostgreSQL、SimPy、part_queue、single ai_loop 等组件，而是它提出的判断标准：

```text
每一个显示出来的数都有来源；
每一个 AI 动作都有规则依据；
每一个命令都有传递通道；
每一个执行结果都能验证；
每一次演示都能复现。
```

这正是当前 Mini-OGAS 应该追求的方向。

但方案最大的缺陷是工程粒度仍然偏大。它需要从“阶段计划”进一步拆成“兼容旧系统的小步迁移任务”。当前系统已经有可运行的主控、前端、节点心跳、AI vault、告警处理和日志归档。v2.1 的正确做法不是推倒重写，而是在这些已验证链路上逐层增加：

```text
SimPy 指标 → snapshot 契约 → part_queue → rule-engine → LLM explanation → command polling → verifier → replay
```

最终建议：

```text
采纳 v2.1 的架构方向；
拒绝 Phase 1 的大包实现方式；
先写契约和测试矩阵；
再用 adapter 兼容旧 API；
最后逐步替换事实源。
```

只要按这个节奏执行，v2.1 是可行的；如果直接按文档一口气实现，风险会很高。
