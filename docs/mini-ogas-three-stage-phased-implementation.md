# Mini-OGAS 三大阶段细化实施文档

日期：2026-06-12
适用路线：`v2.2 兼容式可信闭环 → v2.5 架构债务清理 → v3.0 真分布式理想状态`
目的：把三个大阶段拆成可执行、可验收、可回滚的小阶段，避免一次性大重构。

## 1. 总体原则

Mini-OGAS 后续实施必须遵守以下原则：

```text
1. 不全量重写。
2. 不先删除旧 API。
3. 不先切 PostgreSQL 主事实源。
4. 不先引入 NATS / Redis 作为强依赖。
5. 不让 Dashboard 使用假数据冒充 live。
6. 不让 LLM 直接做数值推理。
7. 不让 AI 直接修改 agent 状态。
8. 每个阶段都必须可运行、可测试、可回滚。
9. 每个临时兼容层都必须记录退出条件。
10. 当前已经跑通的登录、AI vault、告警、日志、节点心跳链路不能被破坏。
```

三大阶段关系：

```text
v2.2：在兼容旧系统的前提下，建立可信闭环。
v2.5：清理 v2.2 留下的兼容债务，统一事实源和接口。
v3.0：进入真正 VM / 边缘节点 / 事件驱动分布式系统。
```

## 2. 大阶段一：v2.2 兼容式可信闭环

v2.2 的目标不是替换当前系统，而是在当前系统上叠加可信仿真、规则、AI 解释和命令闭环。

v2.2 必须保留：

```text
/api/node-heartbeats
/api/dashboard-state
当前 dashboard
当前 node-agent
当前 AI vault
当前告警与日志归档链路
```

v2.2 不做：

```text
NATS
Redis
三 edge VM
完整 model-plane
完整 attack lab
Pyomo / Mesa / RL
旧 API 删除
PostgreSQL 主读写切换
```

### v2.2.0：契约冻结与债务登记

目标：

```text
先写清楚新旧接口、数据结构、债务和验收方式，不改主运行链路。
```

具体任务：

```text
1. 新建 docs/contracts-v2.2.md。
2. 新建 docs/api-compatibility-plan.md。
3. 新建 docs/simulation-contract.md。
4. 新建 docs/test-matrix-v2.2.md。
5. 新建 docs/architecture-debt.md。
6. 定义 heartbeat v2 schema。
7. 定义 dashboard snapshot schema。
8. 定义 rule conclusion schema。
9. 定义 LLM explanation schema。
10. 定义 command schema。
11. 定义 run_id / scenario_id / simulation_time。
```

验收标准：

```text
1. 文档中明确旧 API 与新 API 的映射关系。
2. 每个 schema 至少有一个 JSON 示例。
3. 每个临时兼容层都有退出条件。
4. 没有修改运行代码。
```

回滚策略：

```text
只新增文档，无需代码回滚。
```

禁止事项：

```text
禁止在此阶段改后端 API。
禁止在此阶段改 node-agent 行为。
禁止在此阶段要求前端切换接口。
```

### v2.2.1：Heartbeat v2 兼容扩展

目标：

```text
在旧 /api/node-heartbeats 上增加可信仿真字段，但不改变旧字段语义。
```

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
defect_rate
```

具体任务：

```text
1. 扩展 node-agent heartbeat payload。
2. central-api 接收并保存新增字段。
3. dashboard-state 透出新增字段。
4. 保持旧字段兼容。
5. 添加后端测试：旧 payload 仍可用，新 payload 可透传。
6. 添加 node-agent 测试：heartbeat v2 字段存在且类型正确。
```

验收标准：

```text
1. 旧 node-agent 不带新字段时系统仍正常。
2. 新 node-agent 带新字段时 dashboard-state 可看到。
3. Dashboard 不报错。
4. 后端测试通过。
```

回滚策略：

```text
忽略新增字段即可回到旧行为。
```

禁止事项：

```text
禁止删除 node_code / production / metrics 等旧字段。
禁止改 /api/node-heartbeats 路径。
禁止让前端本地生成这些字段冒充后端数据。
```

### v2.2.2：Dashboard 仿真时间与运行来源显示

目标：

```text
让前端显示 simulation_time、simulation_speed、run_id、scenario_id 和数据来源。
```

具体任务：

```text
1. 增加 SimulationClockBadge。
2. 增加 Run / Scenario 显示。
3. 在运行证据区显示数据来源：live / fallback / fixture。
4. 在节点卡片显示 target_rate、actual_rate、utilization。
5. 添加前端测试，证明这些字段来自 API state。
```

验收标准：

```text
1. 页面明确显示仿真时间和倍率。
2. 页面明确显示 run_id / scenario_id。
3. 页面不把 fixture 标为 live。
4. 前端测试通过。
```

回滚策略：

```text
移除新增展示组件，不影响后端运行。
```

禁止事项：

```text
禁止在前端本地计算业务事实并当成真实状态。
禁止在 API 缺字段时伪造 live 值。
```

### v2.2.3：Snapshot Adapter 初版

目标：

```text
新增 /api/dashboard/snapshot，但内部先复用旧 dashboard-state 聚合逻辑。
```

具体任务：

```text
1. 新增 GET /api/dashboard/snapshot。
2. 返回 v2.2 snapshot schema。
3. snapshot 内部可从现有 dashboard-state 数据转换。
4. 添加 API contract test。
5. 前端暂不强制切换，只做可选读取。
```

验收标准：

```text
1. /api/dashboard-state 仍可用。
2. /api/dashboard/snapshot 可用。
3. snapshot 包含 data_source、run_id、scenario_id、nodes、alerts、timeline 摘要。
4. API 测试通过。
```

回滚策略：

```text
禁用 snapshot 路由，旧 dashboard-state 继续工作。
```

禁止事项：

```text
禁止此阶段删除 dashboard-state。
禁止要求所有前端页面立刻迁移。
```

### v2.2.4：Deterministic SimPyRuntime 单节点试运行

目标：

```text
把 SimPyRuntime 作为 node-agent 内部运行模式加入，但先只做一个节点或一个工序。
```

具体任务：

```text
1. 新增 SIMULATION_ENGINE=simple|simpy。
2. 新增 random_seed 配置。
3. 新增 scenario_id 配置。
4. 实现单节点 SimPyRuntime。
5. 输出仍转换为 heartbeat v2。
6. 保留旧 simple simulator fallback。
```

验收标准：

```text
1. 相同 random_seed 生成相同指标曲线。
2. 不同 scenario_id 可生成不同状态。
3. SimPy 模式关闭后旧模拟器仍运行。
4. node-agent 测试通过。
```

回滚策略：

```text
设置 SIMULATION_ENGINE=simple 回到旧模拟器。
```

禁止事项：

```text
禁止一次性把三工序都迁到 SimPy。
禁止移除旧 simulator。
禁止让 SimPy 输出绕过 heartbeat v2 schema。
```

### v2.2.5：三工序 SimPy 指标闭环

目标：

```text
让 turning、milling、grinding 三个逻辑工序都输出可信 WIP、产速和利用率。
```

具体任务：

```text
1. 定义 turning / milling / grinding cycle time。
2. 定义 80/h、50/h、65/h 产能目标。
3. 定义 WIP 输入输出。
4. 定义 starvation 初步指标。
5. 定义 bottleneck 初步指标。
6. Dashboard 显示三工序 WIP 和 utilization。
```

验收标准：

```text
1. milling_bottleneck 场景下 milling 前 WIP 上升。
2. starvation_demo 场景下 grinding utilization 下降。
3. Dashboard 能显示曲线或数值变化。
4. 相同 seed 可复现。
```

回滚策略：

```text
退回 v2.2.4 单节点 SimPy 或 simple simulator。
```

禁止事项：

```text
禁止把 WIP 写死成前端演示值。
禁止让 Dashboard 自己推导瓶颈。
```

### v2.2.6：Rule Engine 只读判断

目标：

```text
先让规则引擎根据 snapshot 判断瓶颈和饥饿，但不生成命令。
```

具体任务：

```text
1. 新增 bottleneck_alert 规则。
2. 新增 starvation_alert 规则。
3. 输出 rule conclusion。
4. conclusion 包含 rule_id、evidence、risk_level、recommended_action。
5. Dashboard 显示规则结论。
```

验收标准：

```text
1. milling_bottleneck 稳定触发 bottleneck_alert。
2. starvation_demo 稳定触发 starvation_alert。
3. 关闭 LLM 时规则引擎仍可运行。
4. conclusion 可追溯到输入指标。
```

回滚策略：

```text
关闭新 rule-engine 输出，不影响旧告警。
```

禁止事项：

```text
禁止此阶段自动生成 command。
禁止让 LLM 参与数值判断。
```

### v2.2.7：LLM Explanation 接入

目标：

```text
LLM 只解释 rule conclusion，不做数值推理。
```

具体任务：

```text
1. 新增 llm_explain(rule_conclusion, snapshot_summary)。
2. 只允许输入经过校验的结构化摘要。
3. 输出 explanation schema。
4. Dashboard 显示 source、provider、model、rule_id、evidence。
5. 保留 rule_fallback 状态显示。
```

验收标准：

```text
1. AI vault 解锁时 source=api。
2. AI 不可用时 source=rule_fallback。
3. Dashboard 明确显示真实 API 或规则回退。
4. explanation 可追溯到 rule conclusion。
```

回滚策略：

```text
关闭 LLM explanation，规则结论仍然可显示。
```

禁止事项：

```text
禁止把原始 agent 日志直接输入 LLM。
禁止让 LLM 生成未经规则支持的数字。
禁止隐藏 rule_fallback。
```

### v2.2.8：低风险 Command Polling

目标：

```text
先实现 set_target_rate 命令闭环。
```

具体任务：

```text
1. 新增 command schema。
2. 新增 command_id。
3. 新增 GET /api/agents/{node_id}/commands/pending。
4. 新增 POST /api/commands/{command_id}/result。
5. agent 轮询并执行 set_target_rate。
6. central 根据下一轮 heartbeat 验证 target_rate。
```

验收标准：

```text
1. central 创建 pending command。
2. agent 能拉取 command。
3. agent 重复拉取不会重复执行同一 command_id。
4. result 上报后状态变 applied。
5. heartbeat 验证后状态变 verified。
6. Dashboard timeline 显示完整链路。
```

回滚策略：

```text
关闭 command polling，规则结论仍可显示。
```

禁止事项：

```text
禁止一开始实现 emergency_stop 自动执行。
禁止命令没有 command_id。
禁止没有验证就标记 verified。
```

### v2.2.9：part_queue MVP

目标：

```text
只实现 turning → milling 的工件交接。
```

具体任务：

```text
1. 定义 part_queue schema。
2. turning completed event 创建 ready part。
3. milling claim-next 原子认领。
4. 增加 claim_token。
5. 增加 claim_expires_at。
6. 增加重复认领测试。
```

验收标准：

```text
1. 同一个 part 不会被两个 agent 认领。
2. claim 超时后可释放或标记 interrupted。
3. agent 崩溃不会让 part 永久卡死。
4. Dashboard 能显示 WIP 转移。
```

回滚策略：

```text
关闭 part_queue，退回纯 heartbeat 聚合。
```

禁止事项：

```text
禁止非事务认领。
禁止一次性做完整三工序复杂返工流。
```

### v2.2.10：PostgreSQL Shadow Write

目标：

```text
PostgreSQL 先双写，不作为主事实源。
```

具体任务：

```text
1. 新增 repository 抽象。
2. 新增 PostgresRepository。
3. heartbeat / event / command 写入 PostgreSQL。
4. 读取仍默认来自旧事实源。
5. 新增 shadow write 一致性检查脚本。
6. 新增数据重置脚本。
```

验收标准：

```text
1. PostgreSQL 不可用时旧系统仍可运行或明确 degraded。
2. shadow write 有一致性报告。
3. 最近 N 条 heartbeat / event / command 可比对。
4. 不切主读。
```

回滚策略：

```text
关闭 PostgresRepository，旧系统继续运行。
```

禁止事项：

```text
禁止此阶段切 PostgreSQL 为主事实源。
禁止没有一致性检查就认为 shadow write 成功。
```

## 3. 大阶段二：v2.5 架构债务清理

v2.5 的目标不是继续疯狂加功能，而是把 v2.2 的兼容层逐步清掉，使系统边界更干净。

v2.5 不做：

```text
NATS 强依赖
三 edge VM
完整 model-plane
Pyomo / Mesa / RL
复杂 attack lab 网络
```

### v2.5.0：债务审计冻结

目标：

```text
审查 v2.2 留下的所有兼容层，确定哪些可以退出。
```

具体任务：

```text
1. 更新 architecture-debt.md。
2. 给每个 debt 增加 current_status。
3. 给每个 debt 增加 exit_tests。
4. 标记阻塞 v2.5 的债务。
```

验收标准：

```text
1. 每个 debt 都有 owner_module。
2. 每个 debt 都有退出测试。
3. 没有无主债务。
```

### v2.5.1：Dashboard 全量切换 Snapshot

目标：

```text
所有核心前端页面读取 /api/dashboard/snapshot。
```

具体任务：

```text
1. Factory Runtime 切 snapshot。
2. Alarm Management 切 snapshot 或 snapshot 派生接口。
3. Order Dispatch 切 snapshot / command projection。
4. Log Management 切 event timeline。
5. 保留 dashboard-state wrapper。
```

验收标准：

```text
1. 前端核心页面不再直接依赖 /api/dashboard-state。
2. /api/dashboard-state 仍能作为兼容 wrapper 返回。
3. 前端测试覆盖新请求路径。
```

### v2.5.2：PostgreSQL 切为主事实源

目标：

```text
从 shadow write 过渡为主读写。
```

前置条件：

```text
1. shadow write 一致性连续通过。
2. schema migration 稳定。
3. 重启 central 后可重建 state。
```

具体任务：

```text
1. dashboard snapshot 从 PostgreSQL 读取。
2. event_timeline 从 PostgreSQL 读取。
3. command 状态从 PostgreSQL 读取。
4. 内存态降级为 cache 或 projection。
5. 增加 DB degraded 状态。
```

验收标准：

```text
1. 重启 central 后 Dashboard 状态可恢复。
2. 最近 run 的 event timeline 不丢。
3. PostgreSQL 断开时系统显示 degraded。
4. 自动化测试通过。
```

回滚策略：

```text
配置切回旧事实源或 shadow read。
```

### v2.5.3：旧 API 退役为 Wrapper

目标：

```text
旧 /api/node-heartbeats 和 /api/dashboard-state 不再是主路径。
```

具体任务：

```text
1. /api/node-heartbeats 内部调用 /api/agents/{node_id}/heartbeat handler。
2. /api/dashboard-state 内部调用 snapshot projection。
3. 旧 API 返回 header 或 log 标记 deprecated。
4. 更新脚本和测试。
```

验收标准：

```text
1. 新 agent 使用新 API。
2. 旧 API 仍可兼容旧脚本。
3. deprecated 调用被记录。
4. 无核心模块直接依赖旧 API。
```

### v2.5.4：Command Manager 模块化

目标：

```text
把命令生命周期从 central-api 主流程中抽出。
```

具体任务：

```text
1. 新增 command_manager.py。
2. 定义完整内部状态。
3. 支持 timeout。
4. 支持 retry。
5. 支持 superseded。
6. 支持 cancellation。
7. Dashboard 显示对外简化状态。
```

验收标准：

```text
1. command 重复 result 幂等。
2. command 超时进入 expired 或 failed。
3. 被新高优先级命令覆盖时进入 superseded。
4. 测试覆盖生命周期。
```

### v2.5.5：Safety Governor 模块化

目标：

```text
把 simple safety_check 升级为统一安全仲裁模块。
```

触发条件：

```text
1. 命令超过低风险 set_target_rate。
2. 出现 pause、resume、isolate、emergency_stop。
3. 出现 model-plane proposal。
4. 出现 attack lab 注入。
```

具体任务：

```text
1. 新增 safety_governor.py。
2. 定义 action risk level。
3. 定义 required role。
4. 定义 confirmation policy。
5. 定义 RunMode policy。
6. 所有 command 创建前必须经过 Safety Governor。
```

验收标准：

```text
1. DEMO_MODE 不能跳过 safety。
2. HIGH risk 需要人工确认。
3. ATTACK_LAB_MODE 默认只建议。
4. 拒绝原因写入审计。
```

### v2.5.6：Replay 初版

目标：

```text
基于 event_timeline 回放一次成功演示。
```

具体任务：

```text
1. 定义 replay API。
2. replay 只读，不影响 live run。
3. Dashboard 可切换 live / replay。
4. Replay 显示 data_source=replay。
```

验收标准：

```text
1. 可回放一次 bottleneck → rule → AI explanation → command → verified 链路。
2. replay 不产生新 command。
3. replay 不污染 normal run。
```

### v2.5.7：Scenario / Run 稳定化

目标：

```text
Scenario 和 Run 成为标准运行单位。
```

具体任务：

```text
1. 定义 scenario 表。
2. 定义 run 表。
3. 所有关键 event 带 run_id。
4. attack run 与 normal run 隔离。
5. Dashboard 显示当前 run。
```

验收标准：

```text
1. 同一 scenario + seed 可复现。
2. 不同 run 数据不混淆。
3. attack_lab_demo 不污染 normal_day。
```

### v2.5.8：EventPublisher / RuntimeAdapter 抽象

目标：

```text
为 v3.0 分布式做接口预留，但不引入 NATS 强依赖。
```

具体任务：

```text
1. 新增 EventPublisher interface。
2. HTTPPublisher 作为当前实现。
3. 新增 RuntimeAdapter interface。
4. SimPyRuntimeAdapter 作为当前实现。
5. 测试确保 central 不依赖具体实现。
```

验收标准：

```text
1. 未来可替换为 NATSPublisher。
2. 当前 HTTP 行为不变。
3. RuntimeAdapter 可支持未来真实设备适配。
```

## 4. 大阶段三：v3.0 真分布式理想状态

v3.0 的目标是真正分布式，但仍要继续拆小，不一次性上满所有 VM 和模型。

### v3.0.0：分布式部署契约

目标：

```text
先冻结 VM、网络、端口、token、Agent Protocol，不直接部署。
```

具体任务：

```text
1. 定义 ogas-central。
2. 定义 ogas-turning-edge。
3. 定义 ogas-milling-edge。
4. 定义 ogas-grinding-edge。
5. 定义 Agent Protocol。
6. 定义 network profile。
7. 定义 token scope。
```

验收标准：

```text
1. 每个 VM 职责明确。
2. 每个端口用途明确。
3. 每类 token 权限明确。
4. 有部署前检查清单。
```

### v3.0.1：单 Edge VM 迁移

目标：

```text
先把一个 agent 迁移到 edge VM，验证网络和协议。
```

具体任务：

```text
1. 启动 ogas-milling-edge。
2. milling-agent 使用 Agent Protocol 连接 central。
3. central 检测 edge stale / offline。
4. edge 断线后本地 outbox 缓存。
5. edge 恢复后补发。
```

验收标准：

```text
1. 停止 edge VM 后 Dashboard 显示 offline。
2. 恢复后事件可补发。
3. 命令能跨网络到达 agent。
```

### v3.0.2：三 Edge VM

目标：

```text
turning、milling、grinding 分别运行在独立 VM。
```

具体任务：

```text
1. ogas-turning-edge。
2. ogas-milling-edge。
3. ogas-grinding-edge。
4. 每个 edge 有独立 agent token。
5. 每个 edge 有本地 outbox。
6. part 不通过共享内存传递。
```

验收标准：

```text
1. 任意 edge 停止，central 检测 degraded。
2. 三工序事件通过网络流转。
3. Dashboard 展示跨节点因果链。
```

### v3.0.3：NATS EventPublisher

目标：

```text
把 HTTPPublisher 替换或并行为 NATSPublisher。
```

具体任务：

```text
1. 部署 NATS。
2. 实现 NATSPublisher。
3. 实现 event-worker。
4. PostgreSQL 作为 event store。
5. Redis 或 current_state projection 作为当前状态缓存。
```

验收标准：

```text
1. edge 事件进入 NATS。
2. event-worker 写入 PostgreSQL。
3. current_state 可从 event store 重建。
4. HTTP 兼容路径可降级。
```

### v3.0.4：Redis Current State Projection

目标：

```text
把 current_state 从主事实源中分离为可重建缓存。
```

具体任务：

```text
1. Redis 保存 current node state。
2. Redis 保存 active alerts。
3. Redis 保存 command visible state。
4. Redis 可由 PostgreSQL event store 重建。
```

验收标准：

```text
1. 清空 Redis 后可重建。
2. PostgreSQL 仍是历史事实源。
3. Dashboard 读取 current_state 更快。
```

### v3.0.5：Router 与网络边界

目标：

```text
引入 ogas-router，管理 Host-Only / Internal Network / DNAT / 审计。
```

具体任务：

```text
1. router VM。
2. edge 与 central 网络隔离。
3. Kali 默认无法访问 normal network。
4. router 记录流量摘要。
```

验收标准：

```text
1. NORMAL_MODE 下 Kali 无法访问 central。
2. ATTACK_LAB_MODE 下临时放行指定端口。
3. 退出 attack lab 后规则恢复。
```

### v3.0.6：Attack Lab 安全实验

目标：

```text
让 Kali 攻击实验成为受控系统能力，而不是手工脚本注入。
```

具体任务：

```text
1. attack_lab_token。
2. token TTL。
3. attack_run_id。
4. /api/security-lab/*。
5. security_event。
6. weak token 只在 ATTACK_LAB_MODE 可用。
```

验收标准：

```text
1. attack lab 不污染 normal run。
2. 所有攻击请求可审计。
3. 退出模式后 token 失效。
4. Dashboard 显示攻击实验模式。
```

### v3.0.7：ActionCoordinator 与多 AI 角色

目标：

```text
把 single ai_loop 过渡为多角色 AI proposal 协同，但仍不直接执行。
```

具体任务：

```text
1. emergency AI 只提交 proposal。
2. maintenance AI 只提交 proposal。
3. scheduling AI 只提交 proposal。
4. ActionCoordinator 合并冲突。
5. Safety Governor 审核。
6. Command Manager 执行。
```

验收标准：

```text
1. 多 AI 冲突时只有一个最终 action。
2. 被覆盖 proposal 标记 superseded。
3. 高风险 proposal 进入人工确认。
```

### v3.0.8：v3.0 最终验收

目标：

```text
证明 Mini-OGAS 已进入真正分布式状态。
```

验收清单：

```text
1. 三 edge VM 独立运行。
2. 任意 edge 停止，central 检测 degraded。
3. edge 恢复后事件补发。
4. NATS 作为主事件路径。
5. PostgreSQL 作为历史事实源。
6. Redis/current_state 可重建。
7. Command 跨网络到达 agent。
8. Safety Governor 不能被绕过。
9. Dashboard 展示跨节点因果链。
10. Kali attack lab 被隔离并可审计。
```

## 5. v3.x 后续扩展

v3.x 不属于前三大阶段，但作为远期扩展保留。

优先级：

```text
v3.1：Pyomo 排产优化
v3.2：System Dynamics 慢变量模型
v3.3：Mesa 多主体环境
v3.4：RL / Gymnasium 调度训练
v3.5：Prometheus / Grafana / Loki / CI/CD / Chaos Test
```

原则：

```text
任何模型只能提交 action_proposal。
任何模型不能直接写 command。
任何模型不能绕过 Safety Governor。
任何模型必须有 baseline 和验证指标。
```

## 6. 执行顺序总表

| 阶段 | 名称 | 主要目标 |
|---|---|---|
| v2.2.0 | 契约冻结 | 写 schema、债务、测试矩阵 |
| v2.2.1 | Heartbeat v2 | 旧心跳增加可信仿真字段 |
| v2.2.2 | Dashboard 仿真显示 | 显示时间、倍率、run、scenario |
| v2.2.3 | Snapshot Adapter | 新 snapshot API 兼容旧聚合 |
| v2.2.4 | 单节点 SimPy | deterministic SimPyRuntime |
| v2.2.5 | 三工序 SimPy | WIP、产速、利用率闭环 |
| v2.2.6 | Rule Engine | 瓶颈、饥饿只读判断 |
| v2.2.7 | LLM Explanation | 只解释规则结论 |
| v2.2.8 | Command Polling | set_target_rate 闭环 |
| v2.2.9 | part_queue MVP | turning → milling 事务认领 |
| v2.2.10 | PostgreSQL Shadow Write | 双写与一致性检查 |
| v2.5.0 | 债务审计 | 确认债务退出条件 |
| v2.5.1 | Dashboard 切 snapshot | 前端主路径迁移 |
| v2.5.2 | PostgreSQL 主事实源 | 切主读写 |
| v2.5.3 | 旧 API wrapper | 旧 API 退主路径 |
| v2.5.4 | Command Manager | 命令生命周期模块化 |
| v2.5.5 | Safety Governor | 安全仲裁模块化 |
| v2.5.6 | Replay | 事件回放 |
| v2.5.7 | Scenario / Run | 标准运行单位 |
| v2.5.8 | EventPublisher / RuntimeAdapter | 为分布式抽象 |
| v3.0.0 | 分布式契约 | VM、网络、Agent Protocol |
| v3.0.1 | 单 Edge VM | 先迁移一个 agent |
| v3.0.2 | 三 Edge VM | 三工序独立 VM |
| v3.0.3 | NATS EventPublisher | 事件总线 |
| v3.0.4 | Redis Projection | current_state 缓存 |
| v3.0.5 | Router 网络边界 | 隔离与 DNAT |
| v3.0.6 | Attack Lab | 受控安全实验 |
| v3.0.7 | ActionCoordinator | 多 AI proposal 协同 |
| v3.0.8 | v3.0 验收 | 真分布式完成证明 |

## 7. 小阶段技术指导、应用提醒与注意事项

本章节用于指导后续执行者落地每个小阶段。每个小阶段都必须先读对应文档、再改代码、再验证，不能只按标题猜实现。

### v2.2.0：契约冻结与债务登记

技术指导：

```text
1. 只新增 docs，不修改 services、scripts、dashboard 运行代码。
2. 优先阅读当前代码中的真实接口，再写 schema。
3. contracts-v2.2.md 必须覆盖 heartbeat、snapshot、rule conclusion、LLM explanation、command。
4. api-compatibility-plan.md 必须说明旧 API 如何保留、新 API 如何逐步接管。
5. simulation-contract.md 必须明确真实仿真指标、报警类型、处置效果。
6. test-matrix-v2.2.md 必须把后续小阶段的测试方式写清楚。
7. architecture-debt.md 必须记录债务级别、位置、风险、处理阶段、退出条件。
```

技术应用提醒：

```text
重点不是写漂亮文档，而是冻结后续实现不能偏离的技术契约。
文档中所有字段都要能在现有系统或下一阶段实现中找到落点。
不要写无法验证的“智能化”“实时化”空话。
```

注意事项：

```text
禁止此阶段改接口。
禁止此阶段改 node-agent 行为。
禁止此阶段让 Dashboard 切换数据源。
如果发现代码与原计划不一致，以代码事实为准修正文档。
```

### v2.2.1：Heartbeat v2 兼容扩展

技术指导：

```text
1. 在 services/node-agent/simulator.py 的 heartbeat_payload 中增加 v2 字段。
2. 新字段优先放入 runtime 和 production，避免顶层字段失控。
3. central-api 的 Heartbeat 模型保持可选 dict，先接收和透传，不做强校验拒绝。
4. visible_nodes、dashboard-state 或 snapshot adapter 必须能读到新增字段。
5. 给旧 payload 和新 payload 各写一组后端测试。
6. 给 node-agent heartbeat_payload 写字段存在和类型测试。
```

技术应用提醒：

```text
Heartbeat v2 是后续可信运行的基础。
run_id、scenario_id、simulation_time、simulation_speed 代表运行上下文。
wip_input、wip_output、target_rate、actual_rate、utilization、defect_rate 代表生产流动。
前端只能展示这些字段，不能自己生成这些字段。
```

注意事项：

```text
不要删除 node_code、status、metrics、production、alarms、sync、runtime 等旧字段。
不要把缺少 v2 字段的旧节点判为故障。
不要在普通模式下让损耗和报警增长过快。
```

### v2.2.2：Dashboard 仿真时间与运行来源显示

技术指导：

```text
1. 在 dashboard types 中补充 v2 字段类型。
2. 新建或扩展运行状态展示组件，显示 simulation_time、simulation_speed、run_id、scenario_id。
3. 在节点卡片展示 target_rate、actual_rate、utilization。
4. 增加 data_source 展示：live、fallback、fixture、replay。
5. 编写前端测试，证明字段来自 API state。
6. API 缺字段时显示“未上报”或 unknown，不显示伪造值。
```

技术应用提醒：

```text
这个阶段要解决“前端像静态页面”的问题。
页面必须让人看出系统在按后端心跳运行。
运行来源必须可见，否则无法证明是真实后端支撑。
```

注意事项：

```text
不要在前端用 setInterval 自己推进业务事实。
不要把 fixture 数据标成 live。
不要为了视觉效果牺牲状态真实性。
动画只能表现状态变化，不能制造状态事实。
```

### v2.2.3：Snapshot Adapter 初版

技术指导：

```text
1. 在 central-api 新增 GET /api/dashboard/snapshot。
2. 内部先调用或复用 dashboard-state 的聚合结果。
3. 对外转换为 contracts-v2.2.md 中的 snapshot schema。
4. 必须返回 schema_version、generated_at、data_source、run、system、nodes、work_orders、alerts。
5. 增加 API contract test，检查字段结构和 legacy parity。
6. 前端可以增加可选读取开关，但不要强制迁移主路径。
```

技术应用提醒：

```text
Snapshot Adapter 是旧系统到新事实源的桥。
它的价值在于稳定前端契约，而不是立即重写后端。
后续 PostgreSQL 和 replay 都会围绕 snapshot 统一输出。
```

注意事项：

```text
不要在 adapter 中复制一套新的业务规则。
不要让 snapshot 与 dashboard-state 的关键事实矛盾。
不要在 v2.2.3 删除 dashboard-state。
```

### v2.2.4：Deterministic SimPyRuntime 单节点试运行

技术指导：

```text
1. 新建独立 simulation runtime 模块，不直接塞进 main.py。
2. 使用固定 seed，保证相同输入产生相同输出。
3. 先只模拟一个节点、一个工序、一个工单。
4. 输出必须能转换成 Heartbeat v2。
5. 保留现有 node-agent 运行方式，SimPyRuntime 先作为可选模式。
6. 为 cycle time、downtime、defect、utilization 写单元测试。
```

技术应用提醒：

```text
SimPy 只负责离散事件仿真，不负责 AI 判断。
仿真输出要成为心跳事实，而不是直接改前端。
deterministic 是为了可测试、可复盘、可解释。
```

注意事项：

```text
不要一开始就做三节点和复杂优化。
不要把随机数散落在多个模块里。
不要让 SimPyRuntime 破坏当前正常 node-agent。
```

### v2.2.5：三工序 SimPy 指标闭环

技术指导：

```text
1. 扩展单节点仿真为 turning、milling、grinding 三工序。
2. 明确工序输入、输出、队列等待、设备占用、完成件、缺陷件。
3. 每个工序输出 Heartbeat v2 production 指标。
4. 工单 route 必须驱动工件流转。
5. Dashboard 展示 WIP、产速、利用率、缺陷率。
6. 增加三工序正常流转和阻塞流转测试。
```

技术应用提醒：

```text
这是让系统出现“流动性管理页面迹象”的核心阶段。
用户应该能看到工件从一个工序流到下一个工序。
调度建议必须基于阻塞、负载、产能，而不是固定文案。
```

注意事项：

```text
不要把 WIP 只做成静态数字。
不要让三个节点同时出现同类故障。
不要让工单状态与节点 active_order 冲突。
```

### v2.2.6：Rule Engine 只读判断

技术指导：

```text
1. 规则引擎只接收事实输入，输出 rule conclusion。
2. 每条规则必须有 rule_id、evidence、severity、recommended_actions。
3. 规则输出不能直接修改 node_heartbeats、work_orders、alert_lifecycle。
4. 自动处置必须经过 resolution_effects 或后续 Command Manager。
5. 为每类报警写生成、去重、关闭过滤测试。
6. 对已 resolved issue_id 必须过滤，不再进入报警队列。
```

技术应用提醒：

```text
规则引擎负责“判断发生了什么”。
处置模块负责“执行后系统怎么变化”。
AI 负责“解释为什么和建议怎么做”。
三者边界必须分清。
```

注意事项：

```text
不要让规则引擎成为第二套状态机。
不要在标题中重复拼接“人工确认已执行”之类结果前缀。
不要让已处理问题重新出现，除非新心跳带来新的 issue_id 或新 run。
```

### v2.2.7：LLM Explanation 接入

技术指导：

```text
1. AI API 调用入口继续通过 central-api 统一管理。
2. LLM 输入必须包含 issue、node、order、recent_logs、rule conclusion。
3. LLM 输出必须 normalize 成固定 schema。
4. API 成功、API 超时、fallback 三种状态必须可区分。
5. Dashboard 必须显示模型、来源、置信度、证据、方案、是否需要人工。
6. 增加 AI runtime、fallback、normalization 测试。
```

技术应用提醒：

```text
AI 的亮点不是聊天，而是参与诊断链路。
AI 必须围绕具体报警给出根因假设、证据、处置选项和人工追问。
高风险问题必须让 AI 解释为什么需要人工确认。
```

注意事项：

```text
不要让 AI 编造后端没有提供的传感器数据。
不要把 fallback 文案伪装成真实 API。
不要让 AI 直接绕过 CONFIRM 执行动作。
不要把 API key 写进普通源码或文档。
```

### v2.2.8：低风险 Command Polling

技术指导：

```text
1. 增加 command schema 和 command store。
2. central-api 生成 command，node-agent 通过轮询拉取。
3. command 状态至少包含 pending、claimed、executed、failed、expired。
4. 先只支持低风险命令，例如 set_target_rate、adjust_load_limit、create_inspection_task。
5. node-agent 执行后回报结果。
6. 每条 command 必须写 audit_event。
```

技术应用提醒：

```text
这是“AI/脚本真的落地执行”的关键阶段。
AI 可以提出 proposal，central-api 将低风险 proposal 转成 command。
node-agent 只执行后端批准且属于自己的命令。
```

注意事项：

```text
不要支持 stop_machine、retire_node 等高风险自动命令。
不要让 node-agent 执行其他节点的 command。
不要丢失失败命令，失败也必须可审计。
```

### v2.2.9：part_queue MVP

技术指导：

```text
1. 为每个 work_order 增加 part_queue 或等价结构。
2. part 至少包含 id、order_id、current_step、status、claimed_by、updated_at。
3. 节点按 route 认领属于当前工序的 part。
4. 完成后把 part 推进到下一工序。
5. 节点故障时，未开始 part 可释放并重新调度。
6. 写事务测试，避免重复认领和重复完成。
```

技术应用提醒：

```text
part_queue 是系统从“设备面板”变成“生产流动系统”的关键。
调度变更必须能影响后续 part，而不是只改一个显示字段。
```

注意事项：

```text
不要一次性实现复杂 MES。
不要让同一个 part 同时被两个节点认领。
不要把已完成 part 因调度变化退回。
```

### v2.2.10：PostgreSQL Shadow Write

技术指导：

```text
1. 新增 PostgreSQL 连接配置，但默认不阻断主系统启动。
2. 先做 shadow write，不做主读写切换。
3. 写入 heartbeat、audit_event、command、run、scenario 基础表。
4. 内存状态仍是主事实源。
5. PostgreSQL 不可用时记录 degraded，不影响 demo 主链路。
6. 增加双写一致性和数据库不可用测试。
```

技术应用提醒：

```text
Shadow Write 是为 replay、审计和长期运行准备。
它不能一上来就替换内存状态，否则风险太大。
```

注意事项：

```text
不要直接把 PostgreSQL 切成主事实源。
不要让数据库连接失败导致 central-api 退出。
不要把敏感 AI vault 内容写入数据库。
```

### v2.5.0：债务审计冻结

技术指导：

```text
1. 回读 architecture-debt.md。
2. 检查每项债务是否已解决、仍存在、或需要拆分。
3. 将 v2.2 产生的临时兼容层补录进债务表。
4. 为 v2.5 每个债务指定代码位置和退出 PR。
5. 生成 v2.5 debt checklist。
```

技术应用提醒：

```text
v2.5 的核心不是加功能，而是把 v2.2 的兼容债务清理成稳定架构。
先冻结债务再改代码，避免边改边忘。
```

注意事项：

```text
不要把 v2.5 当成新功能堆叠阶段。
不要在债务未确认前删除旧接口。
不要忽略测试债务和文档债务。
```

### v2.5.1：Dashboard 全量切换 Snapshot

技术指导：

```text
1. 为 Dashboard 建立 snapshot client。
2. 将运行总览、报警、调度、日志、节点树逐步切到 snapshot。
3. 保留 dashboard-state fallback 开关。
4. 每迁移一个页面都写前端测试。
5. 对比 snapshot 与 legacy state 的关键字段。
6. 迁移完成后 dashboard-state 只作为兼容 wrapper。
```

技术应用提醒：

```text
Snapshot 是前端稳定契约。
前端页面不应再理解 central-api 内部内存结构。
```

注意事项：

```text
不要一次性替换所有页面后才测试。
不要删除 fallback，直到 snapshot 稳定。
不要让不同页面分别定义自己的后端类型。
```

### v2.5.2：PostgreSQL 切为主事实源

技术指导：

```text
1. 先确认 shadow write 数据完整。
2. 定义 repository 层，隔离 SQL 与 API handler。
3. heartbeat、audit_event、command、run、scenario 分批切主。
4. 每切一个实体都提供迁移脚本和回滚脚本。
5. 使用事务保证 command 和 audit 的一致性。
6. 增加重启后状态恢复测试。
```

技术应用提醒：

```text
主事实源切换是 v2.5 风险最高阶段之一。
必须能证明重启后系统不是重新从 seed 数据开始。
```

注意事项：

```text
不要在 API handler 中散写 SQL。
不要切换未被 shadow write 覆盖的实体。
不要忽略数据库 schema version。
```

### v2.5.3：旧 API 退役为 Wrapper

技术指导：

```text
1. 为每个 legacy API 标注 wrapper 来源。
2. legacy API 内部调用新 repository 或 snapshot service。
3. 保持响应字段兼容旧前端和脚本。
4. 加入 deprecation 注释和测试。
5. 更新 api-compatibility-plan.md 中的退出状态。
```

技术应用提醒：

```text
退役不是删除，而是从主实现降级为兼容壳。
外部调用者不应感知破坏性变化。
```

注意事项：

```text
不要直接删除 /api/dashboard-state。
不要改变旧字段含义。
不要让 wrapper 再复制一套业务逻辑。
```

### v2.5.4：Command Manager 模块化

技术指导：

```text
1. 将 command 创建、审批、下发、回报、过期、审计拆出模块。
2. 定义 CommandManager 类或服务层。
3. central-api handler 只做参数校验和调用。
4. 支持 idempotency key，避免重复执行。
5. command 状态变化必须写 audit_event。
6. 测试覆盖并发认领、重复回报、失败重试。
```

技术应用提醒：

```text
Command Manager 是 AI proposal 到真实执行之间的闸门。
它必须可审计、可回滚、可防重复。
```

注意事项：

```text
不要让 AI 或 Dashboard 直接写 agent 状态。
不要允许未审批高风险命令进入 executable 状态。
不要忽略 command 超时和过期。
```

### v2.5.5：Safety Governor 模块化

技术指导：

```text
1. 将风险判断、权限判断、CONFIRM 判断、设备影响判断集中到 Safety Governor。
2. 输入为 action_proposal 或 command，输出 allow、deny、require_human。
3. 为每个 deny 提供机器可读 error 和中文 message。
4. 将现有 require_supervisor、confirmation_code_valid 等逻辑逐步收口。
5. 测试高风险、低风险、权限不足、确认码错误、节点状态冲突。
```

技术应用提醒：

```text
Safety Governor 是系统可信闭环的安全边界。
后续多 AI、攻击实验、自动命令都必须经过它。
```

注意事项：

```text
不要把安全判断散落在多个 handler。
不要让前端承担安全判断。
不要为了演示方便跳过 CONFIRM。
```

### v2.5.6：Replay 初版

技术指导：

```text
1. 基于 PostgreSQL 中的 run、heartbeat、alert、AI decision、command、audit_event 实现回放。
2. 先支持按 run_id 查询时间线。
3. 提供 replay snapshot，不影响 live snapshot。
4. Dashboard 必须明显标记 replay。
5. 测试同一 run 回放顺序稳定。
```

技术应用提醒：

```text
Replay 用于复盘系统是否真实运行过。
它也是向别人证明 AI 和规则参与了生产过程的证据链。
```

注意事项：

```text
不要把 replay 数据标成 live。
不要让 replay 触发真实 command。
不要在回放中修改当前生产状态。
```

### v2.5.7：Scenario / Run 稳定化

技术指导：

```text
1. 定义 scenario 表和 run 表。
2. scenario 存配置，run 存一次执行实例。
3. 所有 heartbeat、command、audit_event、AI decision 关联 run_id。
4. Dashboard 可按 scenario/run 过滤。
5. 增加 run lifecycle：created、running、paused、completed、failed。
```

技术应用提醒：

```text
Scenario 是“要模拟什么”，Run 是“这一次实际跑了什么”。
二者分开后，系统才能复现实验和生成可信报告。
```

注意事项：

```text
不要把 scenario_id 当成 run_id。
不要让一个 run 混入多个不兼容 scenario 的事件。
不要在运行中随意修改 scenario 配置。
```

### v2.5.8：EventPublisher / RuntimeAdapter 抽象

技术指导：

```text
1. 定义 EventPublisher 接口，先实现 in-process publisher。
2. 定义 RuntimeAdapter 接口，支持 process、virtualbox、future edge。
3. central-api 依赖接口，不依赖具体 NATS 或 VM。
4. 现有 process node-agent 通过 adapter 暴露状态。
5. 写 adapter contract tests。
```

技术应用提醒：

```text
这是进入 v3.0 前的架构准备。
抽象先稳定，NATS 和 VM 后接入。
```

注意事项：

```text
不要在 v2.5.8 就强依赖 NATS。
不要让 RuntimeAdapter 变成万能对象。
不要把 VirtualBox 检查和生产心跳混为同一件事。
```

### v3.0.0：分布式部署契约

技术指导：

```text
1. 编写 edge VM、central、network、agent protocol 的部署契约。
2. 明确端口、token、证书、时间同步、日志路径。
3. 定义 edge agent 启动、心跳、命令拉取、缓存补传流程。
4. 定义 central 与 edge 的故障判定。
5. 写一键部署脚本的参数契约。
```

技术应用提醒：

```text
v3.0 不再是单机模拟，而是真分布式系统。
部署契约必须比代码更先稳定，否则后续 VM 会乱。
```

注意事项：

```text
不要手工配置到无法复现。
不要把开发机绝对路径写死进 edge。
不要在未定义网络边界时接入攻击实验。
```

### v3.0.1：单 Edge VM 迁移

技术指导：

```text
1. 先迁移一个低风险节点到 VM。
2. VM 内运行 node-agent，central 仍在主机。
3. 使用真实网络地址连接 central-api。
4. 验证心跳、工单拉取、缓存补传、命令执行。
5. 保留 process 模式回滚路径。
```

技术应用提醒：

```text
单 Edge VM 是真分布式的最小证明。
只要一个节点跑通，就能验证部署、网络、权限和日志链路。
```

注意事项：

```text
不要一次迁移三个节点。
不要把 VM running 当作节点健康，健康仍以心跳为准。
不要关闭 process fallback，直到 VM 稳定。
```

### v3.0.2：三 Edge VM

技术指导：

```text
1. 为 turning、milling、grinding 建三个独立 VM 或独立 edge 环境。
2. 每个 VM 使用独立 NODE_CODE、WORKSHOP_TYPE、LOCAL_DB_PATH。
3. central 识别三个独立心跳。
4. 验证任意 VM 停止时系统 degraded。
5. 验证 VM 恢复后缓存补传。
```

技术应用提醒：

```text
三 Edge VM 才能证明父子节点结构真实存在。
此阶段前端节点树应能直观看到每个子节点状态。
```

注意事项：

```text
不要复制同一个 node_code。
不要让三个 VM 共享同一个本地数据库文件。
不要让某个 VM 断线导致 central 崩溃。
```

### v3.0.3：NATS EventPublisher

技术指导：

```text
1. 在 EventPublisher 接口下新增 NATS 实现。
2. 先旁路发布 heartbeat/audit/command event。
3. 确认消费者可订阅并写入日志或 projection。
4. NATS 不可用时系统明确 degraded。
5. 加入 subject 命名规范和消息 schema。
```

技术应用提醒：

```text
NATS 是事件总线，不是业务数据库。
它解决分布式事件流，不替代 PostgreSQL 历史事实源。
```

注意事项：

```text
不要一接入 NATS 就删除 REST 心跳。
不要发布无 schema 的随意 JSON。
不要让 NATS 故障导致本地缓存丢失。
```

### v3.0.4：Redis Current State Projection

技术指导：

```text
1. 从事件流构建 current_state projection。
2. Redis 只存当前状态和短期缓存。
3. PostgreSQL 仍保存历史事实。
4. 提供 rebuild projection 的脚本。
5. Dashboard snapshot 可从 projection 读取。
```

技术应用提醒：

```text
Redis 用于快读当前态。
任何 Redis 数据都必须能从 PostgreSQL 或事件流重建。
```

注意事项：

```text
不要把 Redis 当作唯一事实源。
不要把长期审计日志只放 Redis。
不要在 projection 中写复杂业务规则。
```

### v3.0.5：Router 与网络边界

技术指导：

```text
1. 明确 central、edge、attack lab、dashboard 的网络分区。
2. 使用白名单控制 edge 到 central 的方向。
3. 管理端口和攻击实验端口分离。
4. 记录 DNAT、host-only、NAT 或 bridge 配置。
5. 增加网络连通性和隔离性检查脚本。
```

技术应用提醒：

```text
网络边界决定攻击实验是否安全。
真正工业系统管理必须能解释数据从哪里来、命令从哪里去。
```

注意事项：

```text
不要让 Kali 或攻击脚本访问宿主机敏感网段。
不要把 API token 暴露在截图和日志中。
不要把所有 VM 放在无边界的同一网络里。
```

### v3.0.6：Attack Lab 安全实验

技术指导：

```text
1. Kali 或攻击节点只攻击授权测试 edge。
2. 攻击脚本必须有 allowlist、scenario_id、attack_id。
3. 攻击效果表现为节点断线、数据积压、质量异常或命令拒绝。
4. AI 诊断必须引用攻击事件和节点状态。
5. 修复脚本必须可审计、可回滚。
6. 全流程必须写入 audit_event。
```

技术应用提醒：

```text
Attack Lab 的价值是证明防护、诊断、隔离、修复链路。
它不是单纯展示攻击成功，而是展示系统如何受控恢复。
```

注意事项：

```text
不要攻击非授权目标。
不要运行不可控破坏性命令。
不要把攻击脚本和生产脚本混在同一权限下。
不要让攻击实验绕过 Safety Governor。
```

### v3.0.7：ActionCoordinator 与多 AI 角色

技术指导：

```text
1. 定义 action_proposal schema。
2. emergency AI、maintenance AI、scheduling AI 只能提交 proposal。
3. ActionCoordinator 合并 proposal，处理冲突和优先级。
4. Safety Governor 审核最终 action。
5. Command Manager 执行被批准的 action。
6. 记录被采纳、被拒绝、被覆盖的 proposal。
```

技术应用提醒：

```text
多 AI 的价值是分工，不是多个模型同时乱发命令。
系统必须能解释为什么采用某个建议、拒绝另一个建议。
```

注意事项：

```text
不要让任何 AI 角色直接写 command。
不要让多个 proposal 同时作用同一节点同一资源。
不要忽略人工确认优先级。
```

### v3.0.8：v3.0 最终验收

技术指导：

```text
1. 准备完整验收脚本，覆盖启动、登录、自检、三 VM、AI、NATS、Redis、PostgreSQL。
2. 准备正常生产场景、故障场景、攻击场景、恢复场景。
3. 每个场景都生成 run_id 和审计日志。
4. Dashboard 展示 live，不得使用 fixture。
5. 输出验收报告和失败回滚步骤。
```

技术应用提醒：

```text
最终验收要证明 Mini-OGAS 是运行中的分布式管理系统。
证据包括节点心跳、事件流、AI 诊断、命令闭环、日志归档、回放能力。
```

注意事项：

```text
不要用截图替代可重复验收。
不要隐藏 degraded 状态。
不要在验收时临时改代码绕过问题。
```

## 8. 最终说明

这份分阶段文档的核心目标是防止两个问题：

```text
1. 目标太理想，导致一口气大重构。
2. 当前太妥协，导致永远停留在 demo。
```

正确路线是：

```text
每一步都保护当前系统可运行；
每一步都增加一点真实可信能力；
每一步都有验收和回滚；
每一个临时方案都有退出条件；
最终逐步抵达真分布式理想系统。
```

最终建议从 `v2.2.0 契约冻结` 开始执行，而不是直接写 SimPy、PostgreSQL、NATS 或 VM。
