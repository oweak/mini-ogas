# Mini-OGAS Final Ideal Path 优缺点与采用决策报告

日期：2026-06-12
来源方案：`C:/Users/hq362/Downloads/mini-ogas-final-ideal-path-plan.md`
关联报告：

- `docs/mini-ogas-v2.1-feasibility-defect-analysis.md`
- `docs/mini-ogas-final-ideal-path-analysis.md`

## 1. 报告结论

`mini-ogas-final-ideal-path-plan.md` 适合作为 Mini-OGAS 的长期路线图，也适合作为后续开发时的架构边界文件。它最大的意义不是要求项目马上进入 NATS、Redis、多 VM 和多模型阶段，而是明确说明：当前的轻量闭环只是过渡，最终仍要走向真正分布式、事件驱动、AI 受控、安全可审计、前端可解释的工业仿真控制系统。

本报告建议：

```text
采纳它的长期目标；
采纳它的架构债务思想；
采纳 v2.2 → v2.5 → v3.0 → v3.x 的路线；
但不要直接按原文的大阶段施工；
必须先拆成更小的 v2.2.x 微阶段。
```

一句话判断：

> 这份方案可以作为 Mini-OGAS 的“北极星”，但不能直接作为下一步施工图。

## 2. 方案核心价值

这份方案解决了前几轮设计讨论中的一个关键矛盾：

```text
如果只追求轻量，项目可能停在 demo；
如果直接追求理想架构，项目可能改崩；
所以需要一条既能保护当前系统，又不放弃最终目标的迁移路线。
```

它给出的路线是：

```text
v2.2：兼容式可信闭环
v2.5：架构债务清理
v3.0：真正分布式理想状态
v3.x：多模型、真实服务器、工程硬化
```

这个路线总体合理。它使当前每个临时妥协都有解释，也要求每个妥协最终被清理。

## 3. 主要优点

### 3.1 终点没有被降低

方案明确 Mini-OGAS 最终不是轻量演示壳，而是：

```text
多 VM / 多服务器分布式边缘节点
事件驱动通信
PostgreSQL 历史事实源
Redis current_state
NATS 事件总线
Safety Governor
Command Manager
Verifier
model-plane
Dashboard 可解释视图
Replay / Scenario / Run
Kali / attack lab
真实服务器接入协议
```

这能避免项目因为当前资源限制而永久停在本地模拟。

### 3.2 允许现实妥协

方案没有要求立即推倒现有系统，而是允许：

```text
保留旧 API
保留旧 dashboard-state
保留旧 node-agent 上报路径
PostgreSQL 先 shadow write
SimPyRuntime 先嵌入旧 agent
Dashboard 局部迁移
single ai_loop 先替代三 AI 并行
HTTP command polling 先替代 NATS
```

这与当前代码库情况匹配。当前系统已经有 central-api、dashboard、node-agent、heartbeat、AI vault、告警、日志归档和 Kali workflow，不能一口气重写。

### 3.3 架构债务意识强

方案把临时妥协登记为债务，例如：

```text
HTTP 临时事件通道
旧 API 兼容层
PostgreSQL shadow write
single ai_loop
simple safety_check
简化命令状态
单 edge VM
Mock 前端 fixture
```

这非常重要。许多项目失败不是因为临时方案错误，而是因为临时方案没有退出条件，最后变成永久架构。该方案已经开始避免这个问题。

### 3.4 AI 边界清楚

方案坚持：

```text
AI 不直接控制系统
LLM 不承担核心数值推理
model-plane 只能提交 action_proposal
所有动作必须经过 Safety Governor
所有命令必须进入 Command Manager
所有结果必须经过 Verifier
```

这符合工业系统的可信原则。AI 可以解释、建议、辅助决策，但不能绕开规则、安全、权限和验证。

### 3.5 阶段划分比 v2.1 更成熟

v2.1 强调“当前先轻量可信闭环”，但长期终点不够强。final path 补上了长期方向，并明确 v2.5 是债务清理阶段，v3.0 才是真分布式阶段。

这使路线更完整：

```text
v2.1 解决当前收敛；
final path 解决长期终点；
两者结合后，路线更稳。
```

## 4. 主要缺点

### 4.1 v2.2 仍然太大

原方案中的 v2.2 包含：

```text
heartbeat v2
simulation_time / simulation_speed
run_id / scenario_id
snapshot adapter
SimPyRuntime 嵌入 node-agent
part_queue 最小链路
rule-engine
LLM explanation
command polling
低风险 set_target_rate 命令
Dashboard 显示 WIP / 产速 / 饥饿 / 瓶颈
```

这些都该做，但不能一起做。如果按这个列表一次性施工，仍然会变成大重构。

风险：

```text
后端 API 变动
node-agent 变动
前端数据契约变动
仿真模型变动
存储模型变动
AI 解释链路变动
命令链路变动
```

多个边界同时变，问题很难定位。

### 4.2 v3.0 理想状态过满

v3.0 目标包含：

```text
ogas-router
ogas-central
ogas-turning-edge
ogas-milling-edge
ogas-grinding-edge
ogas-model
ogas-kali
NATS
Redis
PostgreSQL
event-worker
Command Manager
Safety Governor
ActionCoordinator
Kali attack lab
```

这个终点很有吸引力，但作为一个版本目标仍然过大。建议拆成：

```text
v3.0-min：central + 3 edge + EventPublisher + PostgreSQL event store
v3.1-sec：router + attack lab + Kali 隔离
v3.2-model：ogas-model + Pyomo
v3.3-hardening：观测体系、CI/CD、Chaos Test
```

### 4.3 NATS 和 Redis 不应被过早写死

事件驱动是架构原则，current_state 可重建缓存也是原则。但 NATS 和 Redis 是具体技术。

更稳妥的表述应该是：

```text
默认候选：NATS + Redis
不可退让原则：事件驱动 + current_state 可重建
允许未来用等价技术替代
```

否则未来一旦 NATS 或 Redis 在本项目环境里不合适，会被路线图反向绑架。

### 4.4 attack lab 安全边界不足

方案提到：

```text
Kali
弱 token
伪造心跳
重放攻击
ATTACK_LAB_MODE
router DNAT
```

但还缺更硬的安全设计：

```text
attack_lab_token TTL
attack_lab_token scope
attack_run_id
security_event
退出攻击模式自动吊销
NORMAL_MODE 默认网络隔离
攻击数据不得污染 normal run
```

Kali 攻击实验是亮点，但如果安全边界不清楚，就会变成“用管理员脚本给系统注入假数据”。

### 4.5 Command Manager 生命周期不完整

方案承认当前命令状态可以简化为：

```text
pending → applied → verified / failed
```

但最终 Command Manager 还需要更完整的生命周期：

```text
created
queued
sent
received
applied
reported
verified
failed
expired
cancelled
superseded
rollback_requested
rollback_applied
```

即使前端不暴露所有状态，内部也要为 retry、timeout、幂等、回滚、重复 result、agent 重启恢复留字段。

### 4.6 Replay / Scenario / Run 还缺 schema

方案把 Replay / Scenario / Run 放在核心能力里，这是对的。但还需要具体 schema。

至少要定义：

```text
scenario_id
run_id
random_seed
simulation_time
wall_time
event_id
event_type
caused_by_event_id
attack_run_id
mode
operator
```

没有这些字段，演示复现、攻击实验隔离、事件回放和因果链展示都会缺基础。

### 4.7 缺少测试矩阵

方案强调每个阶段都要可运行验收，但缺少可执行测试清单。

应补充：

```text
heartbeat v2 contract tests
SimPy deterministic seed tests
snapshot adapter tests
part_queue transaction tests
command idempotency tests
LLM explanation source tests
Safety Governor rejection tests
RunMode isolation tests
attack lab token TTL tests
Replay reconstruction tests
Dashboard data-source tests
```

没有测试矩阵，阶段完成只能靠主观判断。

## 5. 适合采纳的内容

建议直接采纳：

```text
v2.2 / v2.5 / v3.0 / v3.x 总路线
架构债务登记思想
临时妥协必须有退出条件
AI 不直接控制系统
LLM 不做数值推理
model-plane 只能提交 proposal
HTTP 只是过渡
旧 API 暂时保留
PostgreSQL 先 shadow write
single ai_loop 作为过渡
```

这些是这份方案最稳的部分。

## 6. 不建议立即执行的内容

不建议马上做：

```text
NATS
Redis
三 edge VM
ogas-router
ogas-model
完整 attack lab 网络
Pyomo / System Dynamics / Mesa / RL
完整 Command Manager 服务化
完整 Safety Governor 服务化
旧 API 删除
PostgreSQL 主读写切换
```

这些应该在 v2.2 可信闭环稳定之后，再进入 v2.5 或 v3.0。

## 7. 推荐拆分后的 v2.2 施工图

原文 v2.2 应拆成以下微阶段：

### v2.2.0：契约文档

输出：

```text
docs/architecture-debt.md
docs/contracts-v2.2.md
docs/simulation-contract.md
docs/test-matrix-v2.2.md
docs/api-compatibility-plan.md
```

目标是先冻结 schema，不动运行链路。

### v2.2.1：Heartbeat v2

保留旧 `/api/node-heartbeats`，增加：

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

Dashboard 只读展示。

### v2.2.2：Snapshot Adapter

新增：

```http
GET /api/dashboard/snapshot
```

内部先复用旧 `/api/dashboard-state` 聚合逻辑。不要立刻迁移所有前端页面。

### v2.2.3：Deterministic SimPyRuntime

先做单节点或单工序：

```text
固定 random_seed
固定 scenario_id
相同输入输出相同 WIP 曲线
旧 simulator fallback 保留
```

### v2.2.4：Rule Engine Only

先只生成规则结论：

```text
bottleneck_alert
starvation_alert
rule_id
evidence
recommended_action
```

不调用 LLM，不发命令。

### v2.2.5：LLM Explanation

LLM 只解释 rule conclusion：

```text
source
provider
model
rule_ids
evidence_ids
summary
requires_human
```

Dashboard 必须显示 `source=api/rule_fallback`。

### v2.2.6：Command Polling

只做一个低风险命令：

```text
set_target_rate
```

必须有：

```text
command_id
idempotency_key
result
verification
```

### v2.2.7：part_queue MVP

只做：

```text
turning → milling
```

必须保证：

```text
事务认领
不重复认领
claim 超时处理
agent 崩溃后可恢复
```

### v2.2.8：PostgreSQL Shadow Write

只双写，不切主读。

必须有：

```text
一致性检查脚本
数据重置脚本
PostgreSQL 断开降级策略
```

## 8. 与现有系统的关系

当前系统已经有：

```text
central-api
dashboard
node-agent
/api/node-heartbeats
/api/dashboard-state
AI vault
DeepSeek runtime
rule fallback
告警处理
日志归档
Kali workflow
```

所以新路线必须围绕现有系统做兼容迁移：

```text
不能删除旧 API
不能推倒 dashboard
不能绕过 AI vault
不能破坏告警/日志闭环
不能让 Kali 实验污染 normal run
```

最合理的开发方式是：

```text
先 adapter，后替换；
先 shadow write，后主事实源；
先 rule conclusion，后 LLM explanation；
先低风险 command，后完整 Command Manager；
先单节点 SimPy，后三工序 SimPy；
先 local-process，后 VM 分布式。
```

## 9. 采用决策

建议采用等级：

| 内容 | 采用建议 |
|---|---|
| 长期目标 | 采用 |
| v2.2 / v2.5 / v3.0 分层 | 采用 |
| 架构债务表 | 采用并增强 |
| v2.2 原始任务包 | 拆小后采用 |
| NATS / Redis 作为最终唯一技术 | 调整为默认候选 |
| v3.0 全拓扑 | 拆成 v3.0-min / v3.1 / v3.2 |
| attack lab | 采用，但必须补安全边界 |
| model-plane | 后置，先 Pyomo，不并发多模型 |
| 旧 API 退役 | v2.5 后再做 |

## 10. 最终建议

这份方案应该进入项目文档体系，但建议命名为：

```text
docs/final-architecture-roadmap.md
```

同时新增：

```text
docs/architecture-debt.md
docs/contracts-v2.2.md
docs/test-matrix-v2.2.md
docs/api-compatibility-plan.md
```

下一步真正施工不要从 VM、NATS、Redis 开始，而应从：

```text
heartbeat v2
snapshot adapter
rule conclusion
LLM explanation schema
set_target_rate command polling
```

开始。

最终结论：

> 这份方案的方向值得采纳，但必须把 v2.2 拆成更小、可验证、可回滚的施工步骤。它适合定义终点，不适合直接照单全量实现。
