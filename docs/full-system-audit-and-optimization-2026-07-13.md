# Mini-OGAS 全系统审计与架构优化报告

审计日期：2026-07-13

审计范围：项目代码、配置、数据库 schema、启动脚本、自动化测试、项目报告、真实本地运行、浏览器界面

验收范围：v2.2 兼容可信闭环 + v2.5 架构债务清理

## 1. 结论

本轮不是仅检查文件是否存在，而是按“实现、配置、自动化、真实运行、浏览器表现”五类证据逐层核查。最终结论如下：

1. v2.2 阶段达到 100% 验收状态。
2. v2.5.0-v2.5.8 在“单机多进程 + PostgreSQL + HTTP 节点”的既定范围内达到 100% 验收状态。
3. 项目当前是一个真实运行的本地分布式原型：八个受监督进程通过 HTTP、JWT、PostgreSQL 和节点命令闭环协同，不是静态前端或纯 fixture。
4. 项目不是 v3.0 真正多主机系统。三个车间节点仍位于同一物理 Windows 主机，NATS 未部署，Kali VM 未注册，中央数据库没有高可用声明。
5. 本轮发现并修复了两个 P0 跨批次事实污染问题、多个 P1 生命周期/契约/安全问题，并同步清理了过时报告。

## 2. 审计方法

### 2.1 静态检查

- 检查 `services/` 下 central-api、dashboard、node-agent、AI dispatcher、market simulator、production planner、supervisor。
- 检查 `config/supervisor.toml`、`.env.example`、数据库 schema 和 PowerShell 启动脚本。
- 对照 `docs/mini-ogas-three-stage-phased-implementation.md` 的 v2.2/v2.5 验收项。
- 检查旧报告中有关 SQLite、PostgreSQL、VirtualBox、AI、NATS、Redis、节点数量和完成度的表述。
- 检查前端 API 调用与后端路由契约。

### 2.2 自动化检查

- Python 单元/集成测试。
- Go node-agent 和 Go supervisor 测试。
- Vue/Vitest 测试和 TypeScript/Vite 生产构建。
- API contract、登录门禁和 secret scan。
- Kali 边界脚本测试。
- command transaction rollback、replay 不污染 live、run/scenario identity 等定向测试。

### 2.3 真实运行检查

- 使用 `scripts/start-miniogas.ps1 -ReplaceRunning -FactSource postgresql` 启动。
- 验证 Go supervisor 会话、PID、启动时间和 8/8 进程健康。
- 验证 3/3 车间心跳、新鲜度、SimPy、run/scenario/seed。
- 管理员登录后执行真实 DeepSeek API 烟测。
- 检查 PostgreSQL projection、schema migration、runs/scenarios 和 write failure 状态。
- 执行真实故障到归档工作流。

### 2.4 浏览器检查

- 验证开机自检动画完全遮挡后台系统。
- 验证自检完成后才出现登录页。
- 登录后检查 3/3、live、SimPy、AI 来源、当前 WIP、告警和日志。
- 检查历史告警是否污染当前弹窗。
- 检查回放只读标识和历史 run 切换。
- 检查 1440x900 桌面和 390x844 移动布局、横向溢出和按钮裁切。

## 3. 当前真实架构

```text
Browser / Vue 3 Dashboard :5173
             |
             | JWT + REST
             v
FastAPI central-api :8080
  |-- snapshot / rules / audit / replay / reports
  |-- Command Manager
  |-- Safety Governor
  |-- AI provider registry
  |-- PostgreSQL repository + in-process projection
  |
  +-- HTTPPublisher -> turning SimPy node process
  +-- HTTPPublisher -> milling SimPy node process
  +-- HTTPPublisher -> grinding SimPy node process
  |
  +-- AI dispatcher :8081
  +-- market simulator :8082
  `-- production planner :8083

Go supervisor :9099 owns central-api, dashboard, three services and three nodes.
PostgreSQL owns durable central facts.
```

### 3.1 事实源边界

当前正常启动参数是 `CENTRAL_FACT_SOURCE=postgresql`。`MemoryStore` 仍存在，但其角色已从“唯一事实源”收缩为：

1. PostgreSQL 数据的内存 projection/cache。
2. 规则计算和 UI 快照的低延迟读取模型。
3. 数据库不可用时可明确标记的降级状态。

关键事实写入包括 heartbeat、scenario、run、command、audit event、alert、AI diagnosis、part queue。命令状态和命令事件通过 repository 事务同时提交。数据库写入或 projection 加载失败会进入 persistence degraded，不再静默伪装正常。

### 3.2 节点边界

三个生产节点是独立进程，但共享物理主机。生产在线数量只由 fresh heartbeat 决定。VirtualBox/Kali 信息不会影响 3/3 生产节点计数。

节点通过以下边界与中心协作：

- canonical heartbeat：`POST /api/agents/{node_code}/heartbeat`。
- command claim：节点轮询 pending command。
- command result：节点回报 executed/failed。
- heartbeat verification：后续心跳证明目标参数已经生效。
- local/edge fallback：SQLite 只用于本地队列、测试或显式 fallback。

### 3.3 AI 边界

AI 不是前端问答装饰。当前参与点包括：

1. 登录解锁后真实 provider 烟测。
2. 报警根因诊断、建议动作和是否需要隔离。
3. 规则结论解释。
4. 控制/调度 proposal。
5. attack-lab 处置建议。

所有输出携带实际 `provider`、`model`、`source`。真实 API 失败时使用规则或下一 provider，UI 必须显示 fallback，不能把配置名冒充实际响应。AI proposal 不能直接越过 Command Manager 和 Safety Governor。

## 4. 重大问题与修复

### 4.1 P0：历史告警污染当前运行

现象：浏览器顶部显示“活动故障 0”，右侧却出现十张 `disk_pressure`、`cpu_latency_correlation` 弹窗。

根因：PostgreSQL 的 `alerts` 表已有 `run_id`，但 Pydantic `Alert` 模型和恢复路径没有读取它。重启后所有历史 `open` 行被装入当前 projection，快照只按状态过滤，造成显示事实和当前心跳事实矛盾。

修复：

- `Alert` 增加 `run_id`。
- alert 写入、恢复、查询、AI 诊断、升级审批、报表和节点 alarm 投影统一按当前 node run 过滤。
- 历史 alert 仍保留在 PostgreSQL audit/replay。
- 前端对 terminal status 和 current run 再做防御过滤。

结果：真实浏览器中 summary=0、snapshot alerts=0、popup=0 三者一致。

### 4.2 P0：WIP 批次身份只存在于 SQL

现象：组合测试中 replay 找不到刚创建的 part；进一步分析发现 part 的 `run_id` 是持久化时从目标节点心跳临时推断。如果目标节点还保留旧 run，零件会被写到错误批次。

根因：`part_queue_shadow.run_id` 已存在，但 `PartQueueItem` 没有 `run_id` 字段，领域模型丢失事实身份。

修复：

- `PartQueueItem` 增加不可随目标节点变化的 `run_id`。
- 初始零件从 source node/current system run 获取身份。
- milling/grinding 下游零件继承父零件 run。
- live WIP snapshot、claim 和 expired claim 只处理当前 run。
- replay 继续按数据库 run 精确读取历史 WIP。

结果：组合数据库/replay 测试恢复通过，live snapshot 不再展示或领取历史 WIP。

### 4.3 P1：人工结果通知缺少运行身份

根因：`IncidentEvent` 没有 `run_id`。如果结果事件来自临时工作流节点，它既无法归入节点 run，也会在 current-run 过滤中消失。

修复：事件保存/恢复 `run_id`；有节点心跳时取 node run，没有节点 run 时继承 current system run。结果通知只显示当前 run 中未确认的 `human-escalation`，确认后写入 `notification-acknowledged`。

结果：真实故障工作流重新通过，完成通知可见且确认后消失归档。

### 4.4 P1：审计 API 与前端类型不一致

现象：工厂拓扑“日志归档”卡片显示 `undefined 条归档`。

根因：后端统一审计接口返回分页对象 `{total, limit, offset, events}`，前端直接把整个对象赋给 `AuditEvent[]`。

修复：新增 `normalizeAuditEvents()`，同时兼容旧数组和新分页合同，把统一事件映射成日志页面所需字段；畸形 payload 返回空数组而不是污染 UI。

结果：新增两项 Vitest，前端测试从 61 增至 63，生产构建和浏览器检查通过。

### 4.5 P1：命令事件重复

根因：agent command 路由和 Store 都写 `command-created`。

修复：路由只负责校验和调用，Command Manager/Store 成为唯一生命周期事件所有者。command 与 incident event 使用同一数据库事务，失败注入证明两者一起回滚。

### 4.6 P1：Run/Scenario/Seed 不一致

此前三个节点可在同一个 run 下使用不同 scenario/seed，导致 `runs` 行被后到心跳覆盖。

修复：

- supervised normal nodes 统一 `SCN-NORMAL-SIMPY-FLOW-001` 和 master seed。
- 每次启动生成唯一 timestamp run ID。
- central 在内存状态变更和数据库写入前拒绝 mixed scenario/seed。
- Kali workflow 使用独立 `RUN-ATTACK-LAB-*` / `SCN-ATTACK-LAB-*`。

### 4.7 P1：安全策略入口不统一

修复后，isolate/restore/retire、control execute、ops execute、demo scenario、dispatch approval、escalation approval 和 attack lab 均经过 Safety Governor。高风险需要适当角色和确认；拒绝写 audit 并包含 reason code。演示模式不能跳过安全规则。

## 5. v2.2 验收

| 子阶段 | 状态 | 证据摘要 |
| --- | --- | --- |
| v2.2.0 契约冻结 | 完成 | 五份契约/债务文档存在并已同步。 |
| v2.2.1 Heartbeat v2 | 完成 | 三节点上报 runtime/production/WIP/run/scenario。 |
| v2.2.2 Dashboard runtime | 完成 | live/fallback/replay、run、SimPy、节点指标可见。 |
| v2.2.3 Snapshot | 完成 | 主 snapshot + legacy wrapper parity。 |
| v2.2.4 SimPy 单节点 | 完成 | simple/simpy adapter 与 deterministic seed。 |
| v2.2.5 三节点 WIP | 完成 | turning -> milling -> grinding 流转。 |
| v2.2.6 规则引擎 | 完成 | 瓶颈/饥饿和多类设备/主机告警。 |
| v2.2.7 LLM 解释 | 完成 | provider provenance 和 fallback。 |
| v2.2.8 命令轮询 | 完成 | claim/result/heartbeat verification。 |
| v2.2.9 part_queue | 完成 | 领域 run 身份、持久化、当前投影、回放。 |
| v2.2.10 PostgreSQL | 完成 | 正常 central runtime 为 PostgreSQL。 |

## 6. v2.5 验收

| 子阶段 | 状态 | 证据摘要 |
| --- | --- | --- |
| v2.5.0 债务审计 | 完成 | 每项 debt 有 current status、owner、exit evidence。 |
| v2.5.1 Snapshot 全量切换 | 完成 | 核心运行页读取 snapshot；audit/replay 使用独立稳定查询。 |
| v2.5.2 PostgreSQL 主事实 | 完成 | repository、transaction、migration、degraded、recovery、rollback mode。 |
| v2.5.3 Legacy wrappers | 完成 | canonical agent route + deprecation wrappers。 |
| v2.5.4 Command Manager | 完成 | timeout/retry/supersede/cancel/idempotency/concurrency。 |
| v2.5.5 Safety Governor | 完成 | risk/role/confirm/RunMode/all supported high-risk routes。 |
| v2.5.6 Replay | 完成 | read-only, DB-backed, live isolation, UI marker。 |
| v2.5.7 Scenario/Run | 完成 | formal tables, lifecycle, deterministic seed, run isolation。 |
| v2.5.8 Adapter interfaces | 完成 | HTTPPublisher + Simple/SimPy RuntimeAdapter。 |

## 7. 测试与运行证据

`scripts/verify-miniogas.ps1 -RequireAiUnlocked` 最终结果：

| Gate | Result |
| --- | --- |
| API contract | passed |
| Dashboard login gate | passed |
| Secret scan + scanner tests | passed |
| central-api | 162 passed |
| Python simulator | 35 passed |
| Go node-agent | passed |
| Go supervisor | passed |
| AI dispatcher | 4 passed |
| CLI/workflow | 31 passed + 9 subtests |
| Dashboard | 69 passed |
| Dashboard build | passed |
| Ruff correctness lint | passed |
| Strict live runtime | passed |

严格运行检查记录：

- supervisor process session fresh。
- 8/8 processes healthy。
- 3/3 production nodes online。
- snapshot `schema_version=2.2`、`data_source=live`、SimPy。
- live DeepSeek source=`api`。
- PostgreSQL persistence normal。
- production snapshot active issues=0。

真实闭环记录：

```text
heartbeat_fault
-> alert_open
-> confirmed
-> diagnosed
-> approval_required
-> human_approved
-> closed
-> audit_archived
-> notification_acknowledged
-> offline_records_archived
-> live_state_preserved
```

## 8. 报告一致性修复

旧文档存在以下过时表述：

1. 把 PostgreSQL 仍写成 planned/shadow-only。
2. 把 Redis/NATS 画成已运行组件。
3. 把 VirtualBox 状态和生产节点状态混在一起。
4. 记录 2026-07-03 的节点/测试/commit 证据为当前事实。
5. 声称无 issue，却未覆盖 historical alert、WIP run、audit pagination 问题。

本轮已同步：

- `README.md`
- `CODEX_ISSUES.md`
- `PROJECT_STATUS.md`
- `SYSTEM_ISSUES.md`
- `docs/ARCHITECTURE_DEBT.md`
- `docs/api-compatibility-plan.md`
- 本报告

历史报告保留作为阶段记录，不再作为当前运行事实来源。

## 9. 剩余风险与建议

### 9.1 v3.0 前必须先做

1. 冻结 central、三个 edge、Kali lab 的网络和身份契约。
2. 为 edge agent 定义证书、token rotation、clock sync、offline queue 和 upgrade policy。
3. 定义 PostgreSQL backup/restore、RPO/RTO 和 schema rollout。
4. 在单独网段注册 Kali VM，限制白名单目标，禁止公共地址。
5. 冻结 Agent Protocol 后再实现 NATSPublisher，不要直接把 NATS 写进业务层。

### 9.2 不建议现在做

- 不应仅为“看起来分布式”增加 Redis/NATS/VM 数量。
- 不应把 memory projection 全部删除；应先用负载和故障数据决定拆分边界。
- 不应让 AI 自动执行任何新高风险动作，除非 Safety Governor 增加明确 policy 和测试。
- 不应清空旧告警/WIP 数据来解决污染；历史应留在 replay，live 必须按 run 隔离。

## 10. 最终判断

Mini-OGAS 已从“页面能动、后端部分存在”的演示原型，推进为一个可启动、可登录、可验证 AI、可运行三节点仿真、可下发命令、可人工审批、可归档、可重启恢复、可按 run 回放的本地工业管理原型。

当前最重要的架构成果不是增加更多页面，而是建立了可信边界：

- live 与 history 分离；
- rule fallback 与 real AI 分离；
- proposal 与 execution 分离；
- low risk automation 与 high risk human approval 分离；
- PostgreSQL fact 与 memory projection 分离；
- production heartbeat 与 optional attack-lab VM 分离。

在这一边界内，v2.2 和 v2.5 可以结项。下一步应进入 v3.0 部署契约，而不是继续在同一台主机上堆叠伪分布式组件。

## 11. 第二轮深度检查补充

在首轮报告完成后，又按更严格的“物理效果、调用成本、最新状态语义、
密钥输出、移动端和静态质量”标准继续检查。新增结论如下。

### 11.1 命令不再只是修改显示字段

节点将 SimPy 原始完工量与命令约束完工量分离。`set_target_rate` 作用于
增量完工输出，并受车间机器数和加工节拍计算出的物理上限约束。Central
operator gateway 和 edge restore/apply 都拒绝超过物理能力的目标值。

实时命令证据：

1. 命令 54 将 Turning 从 1.333 降至 0.5 件/分钟。
2. 随后的心跳中原始 SimPy 完工继续增加，而命令约束完工保持不变，证明
   限速发生在仿真生产层，不是只改 Dashboard 标签。
3. 命令 55 恢复 1.333 件/分钟，节点实际速率上升，三次后续观察后成为
   `verified/effective`。
4. 旧命令 54 的 `partial` 留在审计/回放，但被命令 55 supersede 后退出
   实时规则结论。

### 11.2 AI 请求放大被消除

此前 Dashboard 每秒读取 snapshot，并把每秒变化的 evidence value 放入 AI
刷新签名，导致规则身份不变时仍持续调用 DeepSeek。修复包括：

- 前端只对 run/scenario、规则身份、严重度、阈值形状和建议动作做语义签名；
- 同一时刻只允许一个 AI 请求；失败后同签名冷却 60 秒；
- 锁屏清理页面内 AI 缓存，重新登录后重新验证；
- Central 使用相同语义键做 60 秒 single-flight cache；
- 人工“刷新解释”显式 `bypass` 缓存；
- provider 返回数组形式 summary 时规范为单一可读字符串。

Playwright 清洁会话中，12 秒内 snapshot 连续刷新 13 次，AI explanation 仅
请求 1 次，响应为 `deepseek-v4-pro`、`source=api`、`cache_status=miss`，没有
新的 console warning/error。

### 11.3 密钥和静态正确性

Ruff 正确性规则发现 `mogas doctor` 会输出密钥前缀。现已改为只输出
`SET (redacted)`，并增加防回归测试。Repository-owned Python 的 Ruff `F`
类检查现为总验收的一部分并全部通过。全量 Ruff 仍有历史行宽、导入排序
和复杂度风格债务，不把这些样式告警伪装成已经清零。

### 11.4 结构性债务

静态质量审计确认两个下一阶段拆分重点：

- `services/central-api/app/store.py`：4098 行、117 个方法，混合 projection、
  orchestration、replay 和兼容行为；
- `services/node-agent/simulator.py`：1059 行，混合 SimPy、SQLite outbox、
  command loop、heartbeat 和 transport。

本轮没有进行一次性大重写，因为那会扩大可信闭环的回归面。现有
Command Manager、Verifier、Safety Governor、Persistence Repository、
RuntimeAdapter 和 EventPublisher 已形成可逐步迁移的边界。v3 开始前应按
这些边界小步拆分，并要求每一步继续通过当前 162/35/69 和实时闭环门禁。

### 11.5 最新运行事实

- 8/8 supervisor 进程健康，3/3 production nodes online；
- `run_id=RUN-LOCAL-20260713-153118`，统一 scenario，SimPy live；
- PostgreSQL `status=ok`、`fact_source=postgresql`、无未报告写失败；
- live nominal capacity 为 Turning 80、Milling 50、Grinding 64.9 件/小时；
- AI runtime 为 DeepSeek `deepseek-v4-pro`，来源 `api`；
- rule conclusions 随实时 WIP/产速证据进入或退出，命令历史不会反向污染当前结论；
- 当前事实与历史命令、告警和事件同时保留在 PostgreSQL 审计/回放中。

### 11.6 AI 空响应真实性与推理预算

最终浏览器联调又发现一项高影响真实性缺陷：供应商调用未抛异常时，即使
`content` 为空或仅返回 `{}`，系统也会写成 `status=explained`、
`used_live_ai=true`。这会把“接口连通”错误等同于“已经完成诊断”。

根因探针确认当前 `deepseek-v4-pro` 属于会消耗推理 token 的模型。复杂规则
提示在原 400 token 上限下可能先耗尽推理预算，导致最终正文为空；简单登录
连通探针则仍可成功，因此两个现象可以同时出现。

修复包括：

- DeepSeek 对话上限改为 `AI_CHAT_MAX_TOKENS=4096`，并保留环境变量配置；
- provider registry 拒绝空字符串，继续走下一 provider 或规则回退；
- DeepSeek adapter 拒绝空 `content`，错误中只记录 `finish_reason` 和长度，
  不泄露推理正文；
- 规则解释只接受至少包含一个有效结构化字段的 JSON；空字符串、空 JSON、
  非结构化空载荷都返回 `provider=rule_fallback`、`used_live_ai=false`，并单独
  记录 `attempted_provider`；
- 增加 provider、registry 和 rule-explanation 回归测试。

修复后的真实调用结果为：`provider=deepseek`、`model=deepseek-v4-pro`、
`source=api`、`used_live_ai=true`，并返回非空摘要、2 条推理、3 条建议和
2 条证据。若供应商再次返回空正文，系统会如实降级，不再显示伪成功。

### 11.7 规则证据只暴露已满足谓词

浏览器内容审查发现，积压条件单独触发瓶颈时，规则结论仍把未满足的
`actual_rate / target_rate <= 0.75` 候选条件放进 evidence。模型据此把
`0.94 <= 0.75` 错误解释为成立。问题根因不是模型接口，而是确定性规则的
证据契约把“候选条件”和“已满足条件”混在了一起。

修复后，瓶颈规则只输出实际成立的积压、利用率、产速比和输入 WIP 谓词，
并按 backlog-only、rate-only 或二者同时触发选择不同摘要。回归测试证明
当比值为 `0.94` 时，不会再把 `<= 0.75` 发送给 AI，也不会声称产出低于目标。
