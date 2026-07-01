# Mini-OGAS Final Ideal Path 方案审查报告

日期：2026-06-12
审查对象：`C:/Users/hq362/Downloads/mini-ogas-final-ideal-path-plan.md`
对照项目：`C:/Users/hq362/Documents/New project/mini-ogas`

## 1. 总体判断

这份“最终理想状态与分阶段实现路径”比 v2.1 方案更完整，也更适合作为 Mini-OGAS 的长期路线图。它最大的进步在于：不再只讨论“现在应该轻量化”，而是明确了轻量化只是通向最终理想架构的过渡，并且为每个临时妥协设定了退出条件。

总体判断如下：

```text
战略价值：高
长期架构方向：基本合理
当前直接执行风险：中高
作为路线图：适合
作为近期任务清单：过重
最需要补充：可执行验收矩阵、资源预算、接口兼容细则、安全边界
```

这份方案的核心价值不是“马上做 NATS、Redis、多 VM、model-plane”，而是建立一个清晰的阶梯：

```text
v2.2：兼容式可信闭环
v2.5：架构债务清理
v3.0：真正分布式理想状态
v3.x：多模型、真实服务器、工程硬化
```

这个方向是可以采纳的。但必须注意：v2.2 依然不能写成一个大包阶段，否则它会重复 v2.1 的问题，即看似渐进，实际把 SimPy、snapshot、part_queue、rule-engine、LLM、command polling、Dashboard 改造全部压在同一阶段。

## 2. 方案最有价值的改进

### 2.1 明确“妥协不是终点”

方案强调 v2.2 是过渡架构，v2.5 是债务清理，v3.0 才是真分布式理想状态。这一点很重要。当前项目确实不能一口气推倒重写，但如果只停在本地 Python 进程和 HTTP 心跳，也会变成“能演示但不再进化”的系统。

该方案避免了两个极端：

```text
一口气做大系统，导致系统不可运行；
永远停留在轻量 demo，导致项目没有技术纵深。
```

### 2.2 临时妥协有退出条件

方案对 HTTP、旧 API、PostgreSQL 双写、single ai_loop、simple safety_check、简化命令状态、单 edge VM、Mock fixture 都登记为架构债务。这比普通路线图更好，因为它迫使开发者回答：

```text
为什么暂时这样做？
影响范围是什么？
什么时候退出？
最终目标是什么？
```

这可以减少“临时方案永久化”的风险。

### 2.3 v2.2 / v2.5 / v3.0 的职责区分清楚

方案把近期目标、中期清债和远期理想状态分开，这对控制开发节奏很有帮助：

- v2.2 重点是兼容旧系统并跑通可信闭环。
- v2.5 重点是清理兼容债务和切换事实源。
- v3.0 重点是真 VM 分布式、NATS、Redis、event-worker、attack lab。
- v3.x 才进入 Pyomo、System Dynamics、Mesa、RL 和工程硬化。

这个分层合理。

### 2.4 对 AI 控制边界的判断正确

方案继续坚持：

```text
AI 不直接控制系统；
LLM 不做核心数值推理；
model-plane 只能提交 action_proposal；
Safety Governor 和 Command Manager 必须在执行链路上。
```

这对于工业控制系统非常关键。AI 应是解释、建议、辅助决策，不应绕过规则、安全仲裁和命令验证。

## 3. 主要缺陷总览

| 编号 | 缺陷 | 严重性 | 影响 |
|---|---|---:|---|
| F1 | 最终理想状态组件过多，缺少最小 v3.0 边界 | 高 | v3.0 可能再次膨胀 |
| F2 | v2.2 仍然是大包阶段 | 高 | 容易一次性改崩当前系统 |
| F3 | v2.5 债务清理缺少量化退出门槛 | 中高 | 兼容层可能无法真正退役 |
| F4 | NATS / Redis 被写成最终必须项，技术选择过早锁死 | 中 | 未来可能被具体实现反噬 |
| F5 | VM 拓扑资源压力和网络复杂度低估 | 高 | 本机环境可能难以稳定运行 |
| F6 | attack lab 安全边界仍不够工程化 | 高 | Kali、弱 token、伪造心跳可能污染正常系统 |
| F7 | 架构债务表缺少 owner、验证方式和阻塞级别 | 中 | 债务登记可能变成文档装饰 |
| F8 | PostgreSQL shadow write 缺少一致性校验机制细节 | 高 | 双写可能只写了，但没人知道是否一致 |
| F9 | Command Manager 生命周期仍未具体化 | 高 | 命令闭环容易停留在 pending/applied 级别 |
| F10 | Safety Governor 升级条件过于粗略 | 中高 | “命令类型超过 3 类”不是充分条件 |
| F11 | model-plane 范围太大，缺少优先裁剪 | 中 | Pyomo、SD、Mesa、RL 容易再次并发膨胀 |
| F12 | 真实服务器接入协议描述不足 | 中 | “未来可接入”还没有协议基础 |
| F13 | Dashboard 跨节点因果链缺少具体数据模型 | 中高 | 前端可能仍只能展示状态，不能展示因果 |
| F14 | Replay / Scenario / Run 是核心，但没有落地 schema | 高 | 攻击实验、演示复现、回放都会受影响 |
| F15 | 缺少完整测试与验收矩阵 | 高 | 每个阶段是否完成无法客观判断 |

## 4. 详细缺陷分析

### F1. 最终理想状态组件过多，缺少最小 v3.0 边界

方案定义的最终理想状态包括：

```text
多 VM / 多服务器
SimPy / 真实设备适配
PostgreSQL
Redis
NATS
Safety Governor
Command Manager
Verifier
model-plane
Dashboard
Replay / Scenario / Run
Kali / attack lab
未来真实服务器接入
```

这些方向都合理，但“最终理想状态”仍然偏满。问题不是不能做，而是缺少“v3.0 最小完成定义”。如果 v3.0 同时要求 ogas-router、ogas-central、三 edge、ogas-model、ogas-kali、NATS、Redis、PostgreSQL、event-worker、model-plane 和 attack lab 全部成熟，阶段会变得过大。

建议把 v3.0 分成：

```text
v3.0-min：central + 3 edge + NATS/EventPublisher + PostgreSQL event store + Dashboard 因果链
v3.1-sec：router + attack lab + Kali 隔离
v3.2-model：ogas-model + Pyomo first
v3.3-hardening：observability + CI/CD + chaos test
```

这样可以避免“理想状态”再次变成不可交付的大目标。

### F2. v2.2 仍然是大包阶段

v2.2 写入的核心任务包括：

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
Dashboard 显示真实 WIP / 产速 / 饥饿 / 瓶颈
```

这比 v2.1 已经更清晰，但仍然是多个系统边界同时变化。对当前代码库而言，v2.2 应进一步拆成微阶段：

```text
v2.2.0：契约冻结，不改运行链路
v2.2.1：heartbeat v2 字段进入旧 /api/node-heartbeats
v2.2.2：Dashboard 显示 simulation_time / speed / run_id / scenario_id
v2.2.3：SimPyRuntime 单节点试运行
v2.2.4：snapshot adapter
v2.2.5：rule-engine 只读判断
v2.2.6：LLM explanation 只解释，不生成命令
v2.2.7：command polling 只做 set_target_rate
v2.2.8：part_queue turning → milling
```

否则 Codex 或其他开发者按 v2.2 一口气做，很容易破坏当前已经可运行的登录、AI vault、告警、日志归档和节点心跳。

### F3. v2.5 债务清理缺少量化退出门槛

方案说 v2.5 要让 PostgreSQL 成为主事实源、旧 API 退役、Command Manager 分离、Safety Governor 升级、Replay 正式上线。但没有写清楚每项债务退出时必须满足什么测试。

例如“旧 `/api/dashboard-state` 退役”至少需要：

```text
Dashboard 所有核心页面不再调用 dashboard-state
Kali workflow 不再依赖 dashboard-state
verify-miniogas 不再依赖 dashboard-state
旧 endpoint 保留 wrapper 至少一个版本
对旧 endpoint 的访问会写 deprecated log
```

例如“PostgreSQL 成为主事实源”至少需要：

```text
shadow write 一致性连续通过 N 次
重启 central 后 state 可从 PostgreSQL 重建
PostgreSQL 断开时系统进入 degraded 而不是静默错乱
测试库可自动创建和清理
```

建议每项债务表增加：

```text
exit_tests
blocking_dependencies
owner_module
target_version
rollback_strategy
```

### F4. NATS / Redis 被写成最终必须项，技术选择过早锁死

方案说最终必须事件驱动，必须 Redis 或等价缓存，必须 NATS 事件总线。其中“事件驱动”和“current_state 可重建缓存”是原则；但“NATS”和“Redis”是具体技术实现。

把具体技术写成最终不可退让项有一定风险。未来可能出现：

- Redis 对当前规模过重，SQLite/内存投影已足够。
- NATS 部署复杂度高，ZeroMQ、MQTT、RabbitMQ 或 PostgreSQL logical queue 更合适。
- Windows / VirtualBox 环境下 NATS 运维成本高于收益。

建议改写为：

```text
最终必须事件驱动，默认候选 NATS。
最终必须有 current_state 缓存，默认候选 Redis。
技术可替换，但必须满足事件顺序、断线恢复、可观测、可重放、可重建。
```

这样保留架构原则，又不把未来锁死。

### F5. VM 拓扑资源压力和网络复杂度低估

最终 VM 拓扑包括：

```text
ogas-router
ogas-central
ogas-turning-edge
ogas-milling-edge
ogas-grinding-edge
ogas-model
ogas-kali
```

这对于普通本机开发环境压力很大。尤其是 Windows + VirtualBox + Dashboard 浏览器 + Python/FastAPI + PostgreSQL + Redis + NATS + Kali，内存、CPU、磁盘和网络复杂度都不低。

建议把部署模式分层：

```text
local-process：当前主开发模式
single-edge-vm：一个 edge VM 跑三个 agent
three-edge-vm：三 edge VM
full-lab：router + central + three edge + kali
model-lab：额外 ogas-model
```

并且每个模式有明确资源预算：

```text
local-process：最低 8GB RAM 主机
single-edge-vm：推荐 16GB RAM
full-lab：推荐 24GB+ RAM 或云主机
```

否则 v3.0 会在部署层面变得不稳定。

### F6. attack lab 安全边界仍不够工程化

方案提出 ogas-kali、弱 token、伪造心跳、重放攻击、ATTACK_LAB_MODE，这些对演示很有价值。但安全边界仍需更硬。

必须补充：

```text
attack_lab_token 与 normal token 完全分离
attack_lab_token 默认 TTL，例如 15 分钟
attack_lab_token 只能调用 /api/security-lab/*
attack_lab 注入的数据必须带 attack_run_id
attack_lab 数据不进入 normal run
退出 ATTACK_LAB_MODE 自动吊销 token
所有攻击请求写入 security_event
Kali 网络转发必须由 router 开关控制
NORMAL_MODE 下 Kali 到 central 的路径默认断开
```

不能让 Kali 脚本直接复用生产管理 token，否则攻击实验会变成“管理员脚本注入”，技术含量和安全边界都不清晰。

### F7. 架构债务表缺少 owner、验证方式和阻塞级别

债务表是好设计，但目前偏文档化。每个 DEBT 应增加：

```text
owner_module
risk_level
blocks_version
exit_tests
current_status
created_at
last_reviewed_at
```

例如：

```text
DEBT-002 旧 API 兼容层
owner_module: central-api/api_compat.py + dashboard/apiClient.ts
risk_level: high
blocks_version: v2.5
exit_tests:
  - dashboard no longer calls /api/dashboard-state
  - node-agent no longer calls /api/node-heartbeats
  - compatibility wrapper covered by tests
```

否则债务表很容易成为“知道有债，但没人清”的清单。

### F8. PostgreSQL shadow write 缺少一致性校验机制细节

方案说 PostgreSQL 先双写，这是正确做法。但双写的关键不在“写两份”，而在“如何证明两份一致”。

必须定义：

```text
shadow_write_id
source_store_hash
postgres_row_hash
comparison_window
consistency_report
divergence_alert
repair_strategy
```

最小实现可以是一个脚本：

```text
scripts/check-shadow-write-consistency.py
```

它比较：

```text
最近 N 条 heartbeat
最近 N 条 event
最近 N 条 command
最近 N 条 audit
```

如果没有一致性报告，PostgreSQL shadow write 只是“多写一份”，不能作为切主依据。

### F9. Command Manager 生命周期仍未具体化

方案里有简化命令状态：

```text
pending → applied → verified / failed
```

并说 v2.5 走向完整 Command Manager。但完整 Command Manager 至少需要：

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

不一定一开始全部暴露给前端，但内部必须支持：

- 幂等。
- 超时。
- 重试。
- agent 重启恢复。
- 重复 result。
- command precondition。
- command postcondition。
- manual approval。
- safety rejection。

建议 v2.2 就把 command 表字段设计得足够兼容未来：

```text
command_id
run_id
node_id
command_type
payload
precondition
postcondition
status
attempt_count
created_at
sent_at
applied_at
reported_at
verified_at
expires_at
superseded_by
failure_reason
```

### F10. Safety Governor 升级条件过于粗略

方案说 simple safety_check 的退出条件是“命令类型超过 3 类”。这不够。Safety Governor 是否独立，不只取决于命令数量，还取决于风险级别和调用方数量。

应该满足任意条件即升级：

```text
出现 high-risk command
出现 attack lab command
出现 model-plane action_proposal
出现自动执行命令
命令调用方超过一个
需要统一审批策略
需要审计每次拒绝原因
```

否则即使命令类型只有两类，只要涉及 emergency_stop 或 isolate，也需要更强的安全仲裁。

### F11. model-plane 范围太大，缺少优先裁剪

方案列出：

```text
Pyomo
System Dynamics
Mesa
RL / Gymnasium
LLM
what-if 分析
```

并给出优先级 Pyomo > System Dynamics > Mesa > RL。这是对的，但仍需更细：

```text
v3.2 只做 Pyomo 排产优化
v3.3 才做 System Dynamics
Mesa 和 RL 作为研究分支，不进入主线
model-plane 的统一输出只能是 action_proposal
每个模型必须有 baseline 对照
```

否则 model-plane 会成为新的膨胀源。

### F12. 真实服务器接入协议描述不足

方案多次提到未来真实服务器 / 边缘节点接入协议，但没有定义 Agent Protocol 的最低要求。

建议补充：

```text
agent_id / node_id 注册
agent capability 上报
heartbeat schema
metrics schema
command polling schema
command result schema
token scope
clock sync
version negotiation
offline outbox
```

真实服务器接入不是“把 URL 改成远程地址”这么简单。必须有版本、权限、能力、离线补偿和安全边界。

### F13. Dashboard 跨节点因果链缺少具体数据模型

方案最终验收要求 Dashboard 能展示跨节点因果链。但因果链需要数据模型支持：

```text
event_id
caused_by_event_id
triggered_rule_id
generated_explanation_id
generated_command_id
command_result_id
verification_id
affected_node_id
affected_part_id
```

否则前端只能把日志按时间排序，不能真正展示：

```text
哪个事件触发哪个规则；
哪个规则触发哪个 AI 解释；
哪个解释生成哪个命令；
哪个命令改变哪个 agent；
哪个 heartbeat 验证命令结果。
```

建议在 v2.2 就加入 `causal_links` 或 `trace_id`。

### F14. Replay / Scenario / Run 是核心，但没有落地 schema

方案正确地把 Replay / Scenario / Run 作为最终能力，但没有定义它们的存储结构。

建议至少定义：

```text
scenario:
  scenario_id
  name
  description
  random_seed
  simulation_speed
  initial_wip
  target_rates
  fault_schedule

run:
  run_id
  scenario_id
  started_at
  ended_at
  status
  mode
  seed
  operator

event:
  event_id
  run_id
  scenario_id
  simulation_time
  wall_time
  event_type
  payload
```

没有这套 schema，Replay 会很难和 attack lab、normal run、demo run 隔离。

### F15. 缺少完整测试与验收矩阵

方案强调每个阶段必须可运行验收，但还没有具体测试矩阵。建议新增：

```text
docs/test-matrix-final-path.md
```

至少包含：

```text
v2.2 heartbeat v2 contract tests
SimPy deterministic seed tests
snapshot adapter API tests
part_queue transaction tests
command idempotency tests
LLM explanation source tests
Safety Governor rejection tests
RunMode isolation tests
attack lab TTL/token tests
Replay reconstruction tests
Dashboard data-source tests
```

没有测试矩阵，路线图无法被客观推进。

## 5. 与上一份 v2.1 方案的关系

v2.1 方案解决的是“当前阶段不要过度膨胀”；这份 final path 解决的是“不要因为当前妥协而放弃最终理想状态”。

两份文档应合并理解：

```text
v2.1：收敛当前实现
final path：定义长期终点和退出条件
```

推荐组合方式：

```text
短期执行：采用 v2.1 的轻量可信闭环原则
中期治理：采用 final path 的债务登记表和退出条件
长期路线：采用 final path 的 v2.5 / v3.0 / v3.x 阶段
```

不能只看 final path，因为它会让人重新兴奋于大架构；也不能只看 v2.1，因为它可能让项目停留在轻量闭环。二者需要搭配。

## 6. 当前代码库落地建议

当前 Mini-OGAS 已经有可运行链路，因此第一步不应做 VM、NATS、Redis 或 model-plane。

推荐近期动作：

```text
1. 把 final path 的债务登记表保存为 docs/architecture-debt.md。
2. 写 docs/contracts-v2.2.md，冻结 heartbeat v2 / snapshot / command / explanation schema。
3. 在现有 /api/node-heartbeats 中增加 heartbeat v2 字段。
4. Dashboard 显示 simulation_time、simulation_speed、run_id、scenario_id。
5. 新增 /api/dashboard/snapshot，但内部先复用 dashboard-state。
6. 给 node-agent 增加 deterministic seed 和 scenario_id。
7. 先做 rule-engine 只读判断，不立刻发命令。
8. 再做 set_target_rate 的 command polling。
```

暂缓：

```text
PostgreSQL 主事实源
NATS
Redis
多 VM edge
ogas-router
ogas-model
Kali 弱 token 自动化
Pyomo / Mesa / RL
```

## 7. 修正后的阶段建议

### v2.2.0：文档与契约

```text
architecture-debt.md
contracts-v2.2.md
simulation-contract.md
test-matrix-v2.2.md
api-compatibility-plan.md
```

### v2.2.1：Heartbeat v2

```text
旧 /api/node-heartbeats 不变
新增 simulation_time / speed / run_id / scenario_id / WIP / target_rate / actual_rate
前端只读展示
```

### v2.2.2：Snapshot Adapter

```text
新增 /api/dashboard/snapshot
内部复用 dashboard-state
Dashboard 局部迁移
```

### v2.2.3：Deterministic SimPyRuntime

```text
单节点试运行
固定 random_seed
可复现 WIP 曲线
旧模拟器 fallback
```

### v2.2.4：Rule Engine Only

```text
bottleneck_alert
starvation_alert
只生成 rule conclusion
不生成命令
```

### v2.2.5：LLM Explanation

```text
LLM 只解释 rule conclusion
Dashboard 显示 source/model/rule/evidence
```

### v2.2.6：Command Polling

```text
只做 set_target_rate
command_id 幂等
agent result
central verification
```

### v2.2.7：part_queue MVP

```text
只做 turning → milling
事务认领
超时释放
不重复认领
```

### v2.2.8：PostgreSQL Shadow Write

```text
只双写
不切主读
一致性检查
```

## 8. 最终结论

这份 final path 是一份有价值的长期路线图，但还不能直接当作开发任务执行。它的正确用法是：

```text
用它定义终点；
用 v2.1 定义当前收敛原则；
用 v2.2.x 微阶段执行；
用债务表防止临时方案永久化；
用测试矩阵证明每一步可信。
```

最终建议：

```text
采纳长期目标；
保留债务登记表；
拆小 v2.2；
推迟 v3.0 大拓扑；
先做 heartbeat v2、snapshot adapter、rule conclusion、command polling。
```

一句话：

> 这份方案适合做 Mini-OGAS 的“北极星”，但不能当作下一步施工图。下一步施工图必须从 v2.2.0 到 v2.2.8 拆细，否则理想架构会重新压垮当前已经跑通的系统。
