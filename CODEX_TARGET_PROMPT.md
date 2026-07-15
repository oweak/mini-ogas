# Mini-OGAS v3.0 分布式智能工厂系统 — Codex 目标提示词

> **用途**：将此文件输入 Codex / Claude Code / Cursor 等 AI 编程代理，使其能够理解项目全貌并继续开发。
> **最后更新**：2026-07-13
> **当前阶段**：v2.5 已完成 → v3.0 待启动

---

## 目录

1. [项目身份](#1-项目身份)
2. [领域模型（借鉴 ISA-95）](#2-领域模型)
3. [当前架构（v2.5 已实现）](#3-当前架构)
4. [已实现功能清单](#4-已实现功能清单)
5. [技术栈](#5-技术栈)
6. [v3.0 目标架构](#6-v3.0-目标架构)
7. [v3.0 任务分解](#7-v3.0-任务分解)
8. [不可变原则](#8-不可变原则)
9. [禁止事项（反模式）](#9-禁止事项)
10. [借鉴的业界模式](#10-借鉴的业界模式)
11. [验收标准](#11-验收标准)
12. [关键文件路径索引](#12-关键文件路径索引)

---

## 1. 项目身份

### 项目名称
**Mini-OGAS** — 轻量级分布式工厂运营与生产计划系统

### 一句话描述
面向研究生面试演示的国产化离散制造仿真系统，模拟车削/铣削/磨削三工序工厂，支持从设备心跳采集、规则引擎诊断、AI 语义解释、命令闭环执行到 PostgreSQL 审计归档的完整可信链路。

### 业务场景
- 一个小型汽车零部件加工工厂（产品：标准轴、法兰、齿轮毛坯、精密套筒、定制连接器）
- 3 个生产车间：车削车间（turning）、铣削车间（milling）、磨削车间（grinding）
- 从上级调度中心接收生产订单，按工艺路线（route）分配至车间设备
- 设备状态实时监控（温度、振动、刀具磨损、冷却液、良品率）
- 故障分级处理：L0 脚本修复 → L1 规则引擎告警 → L2 AI 诊断 → L3 节点隔离

### 核心约束
- **不是**真实工厂的 MES 系统，而是**研究生面试用的可信仿真演示系统**
- 所有数据必须来自真实后端进程（SimPy 仿真器 + PostgreSQL），**禁止前端伪造**
- AI（DeepSeek）只能做解释和建议，**不能直接修改生产状态**
- 高风险操作必须经过 Safety Governor + 人工确认码

---

## 2. 领域模型（借鉴 ISA-95 / IEC 62264）

项目隐含遵循 ISA-95 层次模型，但不强制套用全部术语：

| ISA-95 层次 | Mini-OGAS 对应 | 说明 |
|-----------|--------------|------|
| Level 4 — 业务计划与物流 | `market-simulator` + `production-planner` | 市场信号、生产计划、调配订单 |
| Level 3 — 制造运营管理 | `central-api` + `command_manager` + `safety_governor` | 调度、规则引擎、AI 诊断、命令闭环 |
| Level 2 — 监控与数据采集 | `node-agent` + SimPy 仿真器 | 心跳上报、指标采集、命令执行 |
| Level 1 — 设备控制 | `MachineProfile` + 物理/仿真设备模型 | 主轴温度、刀具磨损、振动、冷却液 |

### 核心领域对象
```
Node (车间设备) 1──N Machine (机床)
Node 1──N Heartbeat (心跳)
Node 1──N Alert (告警)
Alert 1──1 AiDiagnosis (AI 诊断)
Order (生产订单) 1──N DispatchTask (调度任务)
Order 1──N PartQueueItem (在制品流转)
Command (控制命令) 1──N AuditLog (审计记录)
Scenario (场景配置) 1──N Run (运行实例)
Run 1──N Heartbeat / Alert / Command / AuditLog
```

### 关键业务流程
```
Market Signal → Production Plan → Dispatch Task → Node Heartbeat
                                                      ↓
                                               Rule Engine 判断
                                                      ↓
                                               AI Explanation 解释
                                                      ↓
                                               Safety Governor 审核
                                                      ↓
                                               Command Manager 下发
                                                      ↓
                                               Node Agent 执行 → Heartbeat 验证
                                                      ↓
                                               PostgreSQL 持久化 → Audit 归档
```

---

## 3. 当前架构（v2.5 已实现）

### 部署拓扑（单机多进程）

```
Windows 工作站 (Lenovo Legion Y7000P 2023)
│
├── Go Supervisor :9099 （进程管理器）
│   ├── 会话管理（session token + PID + 启动时间）
│   ├── 健康检查（HTTP health probe，拒绝陈旧监听器）
│   ├── 进程重启（指数退避，世代跟踪）
│   └── API：/supervisor/status, /supervisor/restart/{name}, /supervisor/stopall
│
├── FastAPI central-api :8080 （中央控制服务）
│   ├── 16 个路由模块（见下方）
│   ├── Python MemoryStore（主内存事实源）
│   ├── PostgreSQL 持久化层（主读写）
│   ├── CommandManager（命令生命周期 + 验证器）
│   ├── SafetyGovernor（角色/风险/确认码/运行模式门控）
│   ├── Rule Engine（瓶颈/饥饿/离线/过期/缺陷检测）
│   ├── AI Provider Chain（deepseek → ollama → lm_studio → groq → rule_fallback）
│   └── AI Vault（加密 API key，管理员登录后解锁）
│
├── Vue 3 Dashboard :5173
│   ├── FactoryRuntimeView（工厂总览 + 运行时证明）
│   ├── OrderDispatchView（工单调度）
│   ├── AlarmManagementView（告警管理）
│   ├── LogManagementView（日志与审计）
│   ├── ReplayTimelineView（运行回放）
│   ├── ProductionReportView（生产报告 + 导出）
│   └── DemoControlView（演示场景控制）
│
├── 3 个 SimPy 工序进程（被 Supervisor 管理）
│   ├── turning-simpy   → LATHE-01（3 台数控车床）
│   ├── milling-simpy   → MILL-02（2 台数控铣床）
│   └── grinding-simpy  → GRIND-01（2 台精密磨床）
│
├── 3 个 Python 微服务（被 Supervisor 管理）
│   ├── ai-dispatcher :8081
│   ├── market-simulator :8082
│   └── production-planner :8083
│
└── PostgreSQL （主事实源）
    ├── 13 张业务表 + 2 张索引
    ├── event_store（事件溯源）
    ├── shadow tables（heartbeat / command / part_queue）
    ├── node_record_receipts（离线重放去重）
    └── schema_migrations（版本管理）
```

### central-api 路由模块（16 个）

| 路由模块 | 路径前缀 | 职责 |
|---------|---------|------|
| `preflight` | `/system/preflight` | 启动前自检 |
| `compat` | `/auth/*`, `/alerts/*`, `/ai/*`, `/ops/*` | Codex dashboard 兼容层 |
| `health` | `/health`, `/summary`, `/hosts/status` | 健康检查 |
| `history` | `/history/*` | 历史数据 |
| `ops` | `/ops/*` | 运维操作 |
| `nodes` | `/node-heartbeats`, `/agents/*` | 心跳、命令轮询、零件认领 |
| `dispatch` | `/dispatch/*` | 调度任务 |
| `market` | `/market/*` | 市场信号 |
| `production` | `/production/*` | 生产计划 |
| `replay` | `/api/replay/*` | 运行回放 |
| `reports` | `/reports/*` | 生产报告 |
| `ai` | `/ai/*` | AI 诊断、聊天、规则解释 |
| `audit` | `/audit/*`, `/alerts/*`, `/events/*` | 审计日志 |
| `simulation` | `/simulation/*` | 仿真控制 |
| `demo` | `/demo/*`, `/dashboard-state`, `/dashboard/snapshot` | 演示场景 |
| `control` | `/control/*` | 自然语言控制 |

---

## 4. 已实现功能清单

### v2.2 兼容式可信闭环（100%）

| 子阶段 | 功能 | 证据 |
|--------|------|------|
| v2.2.0 | 契约冻结（5 份技术文档 + schema 定义） | `docs/contracts-v2.2.md` 等 |
| v2.2.1 | Heartbeat v2（仿真时间/WIP/产速/利用率字段） | `node-agent/simulator.py:heartbeat_payload()` |
| v2.2.2 | Dashboard 仿真时间与数据源显示 | `useRuntimePresentation.ts` + `FactoryRuntimeView.vue` |
| v2.2.3 | Snapshot Adapter（`/api/dashboard/snapshot`） | `routers/demo.py:_build_dashboard_snapshot()` |
| v2.2.4 | Deterministic SimPyRuntime（固定 seed 可复现） | `simulator.py:simpy_machine_state()` |
| v2.2.5 | 三工序 WIP/产速/利用率闭环 | `PROFILES` + `production_flow_metrics()` |
| v2.2.6 | Rule Engine（瓶颈/饥饿只读判断） | `rules.py`（bottleneck + starvation + offline + stale + defect） |
| v2.2.7 | LLM Explanation（只解释不推理） | `rule_explanation.py:explain_rule_conclusions()` |
| v2.2.8 | Command Polling（set_target_rate 闭环） | `nodes.py` + `simulator.py:poll_agent_commands()` |
| v2.2.9 | part_queue MVP（turning→milling 工件交接） | `nodes.py` + `simulator.py:poll_part_queue()` |
| v2.2.10 | PostgreSQL Shadow Write（双写+一致性检查） | `store.py:persist_heartbeat_shadow()` 等 |

### v2.5 架构债务清理（100%）

| 子阶段 | 功能 | 证据 |
|--------|------|------|
| v2.5.0 | 债务审计冻结（20 项债务全部登记） | `docs/ARCHITECTURE_DEBT.md` |
| v2.5.1 | Dashboard 全量切换 Snapshot | `runtimeState.ts:dashboardSnapshotToState()` |
| v2.5.2 | PostgreSQL 切为主事实源 | `store.py:refresh_primary_projection()` |
| v2.5.3 | 旧 API 退役为 Wrapper | `demo.py:_dashboard_state_from_snapshot()` |
| v2.5.4 | Command Manager 模块化 | `command_manager.py`（完整生命周期 + 验证器） |
| v2.5.5 | Safety Governor 模块化 | `safety_governor.py`（角色/风险/确认码门控） |
| v2.5.6 | Replay 初版 | `routers/replay.py` + `ReplayTimelineView.vue` |
| v2.5.7 | Scenario / Run 稳定化 | PostgreSQL `scenarios` + `runs` 表 |
| v2.5.8 | EventPublisher / RuntimeAdapter 抽象 | `event_publishers.py` + `runtime_adapters.py` |

### v2.5 新增的安全/质量模块

| 模块 | 文件 | 测试数 |
|------|------|--------|
| Safety Governor | `safety_governor.py` | 6 |
| Command Manager | `command_manager.py` | 6（验证器） |
| Replay Router | `routers/replay.py` | 集成在 store 测试中 |
| Event Store（事件溯源） | PostgreSQL `event_store` 表 | `test_event_store.py` |
| Part Queue Flow Projection | `store.py:part_queue_flow_projection()` | 集成测试 |
| Alert Run Isolation | `store.py:alert_in_current_run()` | 集成测试 |
| Go Supervisor | `services/supervisor/` | 3 个 Go 测试文件 |

### 测试覆盖总计

| 层级 | 测试通过数 |
|------|----------|
| central-api（Python） | 162 |
| node-agent（Python） | 35 |
| Dashboard（TypeScript） | 69 |
| ai-dispatcher（Python） | 4 |
| CLI / 工作流脚本（Python） | 31 + 9 子测试 |
| Go node-agent | 通过 |
| Go supervisor | 通过 |

---

## 5. 技术栈

| 层级 | 当前实现 | v3.0 选项 |
|------|---------|---------|
| Dashboard | Vue 3 + TypeScript + Vite + ECharts | 不变 |
| Central API | Python FastAPI + Pydantic v2 | 不变 |
| 进程管理 | Go Supervisor（HTTP 健康检查 + 重启） | 不变 |
| 节点仿真 | Python SimPy（离散事件仿真） | 不变；可替换 Adapter |
| 事件传输 | `HTTPPublisher`（urllib POST） | **NATSPublisher**（v3.0） |
| 消息总线 | 无（REST 直连） | **NATS**（v3.0） |
| 中央数据库 | PostgreSQL（主事实源） | 不变 |
| 节点本地数据库 | SQLite（心跳缓存 + 离线补偿） | 不变 |
| 缓存/投影 | 内存态（Python dict） | 可选 **Redis**（v3.0） |
| AI 提供商 | DeepSeek + Ollama + LM Studio + Groq 链式降级 | 不变 |
| 认证 | JWT + RBAC + API Token | 不变 |
| 部署 | 本地 Go Supervisor 进程管理 | Docker Compose 可选 |
| 开发环境 | Windows 11 + Python 3.12 + Node 22 + Go 1.22 | 不变 |

---

## 6. v3.0 目标架构

### 目标拓扑（多主机分布式）

```
┌─────────────────────────────────────────────────────┐
│  Central Host (Windows 工作站)                        │
│                                                       │
│  Dashboard :5173 ──→ central-api :8080                │
│                       │   ├── PostgreSQL (主事实源)      │
│                       │   ├── NATS Server (事件总线)     │
│                       │   ├── Redis (current_state 投影) │
│                       │   ├── ai-dispatcher :8081       │
│                       │   ├── market-simulator :8082    │
│                       │   └── production-planner :8083  │
│                       │                                 │
│  Go Supervisor :9099 ──┘                               │
└─────────────────────────────────────────────────────┘
         │                    │                    │
         │ NATS               │ NATS               │ NATS
         ▼                    ▼                    ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Turning Edge │  │ Milling Edge │  │Grinding Edge │
│ VM / Cloud   │  │ VM / Cloud   │  │ VM / Cloud   │
│              │  │              │  │              │
│ node-agent   │  │ node-agent   │  │ node-agent   │
│ SimPy        │  │ SimPy        │  │ SimPy        │
│ SQLite       │  │ SQLite       │  │ SQLite       │
│ outbox cache │  │ outbox cache │  │ outbox cache │
└──────────────┘  └──────────────┘  └──────────────┘
         ║
         ║ Host-Only Network (隔离)
         ║
┌──────────────┐
│  Kali VM     │  ← 仅 ATTACK_LAB_MODE 可访问
│ 攻击实验节点  │
└──────────────┘
```

### v3.0 新增组件

| 组件 | 部署位置 | 职责 |
|------|---------|------|
| **NATS Server** | Central Host | 事件总线，解耦心跳/命令/告警/审计事件 |
| **NATSPublisher** | Central + Edge | 实现 `EventPublisher` 接口，替代 `HTTPPublisher` |
| **Redis** | Central Host | 当前状态投影缓存，可从 event_store 重建 |
| **Router VM** | 独立 VM | 网络隔离：Host-Only / Internal Network / DNAT |
| **3 Edge VM** | 独立 VM/云服务器 | 运行 node-agent + SimPy + SQLite + 本地 outbox |
| **Kali VM** | 独立 VM | 攻击实验节点（仅在 ATTACK_LAB_MODE 下连通） |

---

## 7. v3.0 任务分解

### v3.0.0：分布式部署契约（仅文档，不改代码）

**目标**：冻结 VM、网络、端口、Token、Agent Protocol 的部署契约

**具体任务**：
1. 编写 `docs/deployment-contract-v3.0.md`
   - 定义 `ogas-central`、`ogas-turning-edge`、`ogas-milling-edge`、`ogas-grinding-edge` 的角色和资源规格
   - 明确每个 VM 的端口映射、网络接口类型（Host-Only / NAT / Bridge）
   - 定义 Agent Protocol：心跳格式、命令拉取格式、离线补传格式
   - 定义 Token Scope：edge-token、central-token、attack-lab-token 的权限边界
   - 定义时间同步策略（NTP）和证书策略（自签名 CA）
   - 定义故障判定规则：heartbeat timeout、edge stale、edge offline 的判定阈值
2. 编写 `docs/network-profile-v3.0.md`
   - 网络拓扑图（ASCII 或 Mermaid）
   - 每个网络的 IP 段、子网掩码、网关
   - DNAT / 端口转发规则
   - 白名单/黑名单规则
3. 编写 `docs/backup-restore-v3.0.md`
   - PostgreSQL 备份策略
   - 节点 SQLite 备份策略
   - 恢复流程和验证步骤
4. 设计 Agent Protocol 的 JSON Schema（作为 `contracts-v3.0.md` 的一部分）

**验收标准**：
- 每个 VM 的职责、端口、网络明确，无歧义
- Token 权限边界清楚
- 有部署前自检清单

**回滚策略**：仅新增文档，无需回滚代码

**借鉴参考**：
- NATS 官方文档的 [subject 命名规范](https://docs.nats.io/reference/patterns/subjects)
- HashiCorp Nomad 的 [job specification](https://developer.hashicorp.com/nomad/docs/job-specification) 格式
- Kubernetes Pod 的资源规格声明方式

---

### v3.0.1：NATS EventPublisher（在 Central 引入 NATS）

**前置条件**：v3.0.0 契约冻结完成

**目标**：在 `EventPublisher` 接口下新增 `NATSPublisher` 实现，先旁路发布

**具体任务**：
1. 安装 NATS Server（本地开发用 `nats-server -js` 单节点）
2. 在 `services/central-api/app/core/` 下新增 `nats_publisher.py`
   ```python
   class NATSPublisher(EventPublisher):
       async def publish_event(self, event: Event) -> None: ...
       async def publish_heartbeat(self, heartbeat: dict) -> None: ...
       async def publish_command(self, command: NodeCommand) -> None: ...
       async def publish_audit(self, audit: AuditLog) -> None: ...
   ```
3. Subject 命名规范（遵循 NATS 最佳实践）：
   - `ogas.events.{event_type}.{node_code}` — 事件流
   - `ogas.heartbeats.{node_code}` — 心跳流
   - `ogas.commands.{node_code}` — 命令流
   - `ogas.audit.{resource_type}` — 审计流
4. 实现 JetStream 持久化（保证事件不丢）
5. 先以**旁路模式**运行：发布到 NATS 但不替代 HTTP 路径
6. 编写 `NATSEventWorker` 消费事件写入 PostgreSQL
7. 编写测试：`test_nats_publisher.py`

**验收标准**：
- NATS 不可用时系统明确显示 `degraded`（不崩溃）
- 事件能通过 NATS 发布并被 worker 消费写入 PostgreSQL
- 与现有 HTTP 路径共存，不破坏现有功能
- 测试通过

**禁止**：删除 REST 心跳路径、发布无 schema 的随意 JSON

**借鉴参考**：
- NATS 官方 Python 客户端 [nats-py](https://github.com/nats-io/nats.py)
- Synadia 的 [NATS by Example](https://natsbyexample.com/) 中的 JetStream WorkQueue 模式
- Uber 的 [Cadence](https://github.com/uber/cadence) 事件驱动架构思想

---

### v3.0.2：Redis Current State Projection

**前置条件**：v3.0.1 NATS 旁路运行稳定

**目标**：把 `current_state` 从内存态分离为可重建的 Redis 缓存

**具体任务**：
1. 安装 Redis（本地开发单节点）
2. 在 `services/central-api/app/core/` 下新增 `redis_projection.py`
   ```python
   class RedisProjection:
       def set_node_state(self, node_code: str, state: dict) -> None: ...
       def get_node_state(self, node_code: str) -> dict | None: ...
       def set_active_alerts(self, alerts: list[dict]) -> None: ...
       def set_command_visible_state(self, commands: list[dict]) -> None: ...
       def rebuild_from_event_store(self, run_id: str) -> None: ...
   ```
3. Redis Key 命名规范：
   - `ogas:current:nodes:{node_code}` — 节点当前状态
   - `ogas:current:alerts` — 活跃告警列表
   - `ogas:current:commands` — 命令可见状态
   - `ogas:current:run:{run_id}` — 当前运行元数据
4. 实现 `rebuild from event_store`：清空 Redis → 从 PostgreSQL 回放事件 → 重建投影
5. Dashboard snapshot 可从 Redis projection 读取
6. 编写测试：`test_redis_projection.py`

**验收标准**：
- 清空 Redis 后可从 PostgreSQL event_store 重建
- PostgreSQL 仍是历史事实源（Redis 不是唯一事实源）
- Dashboard 读取 current_state 更快（可选指标，不强制）

**禁止**：把 Redis 当作唯一事实源、把长期审计日志只放 Redis、在 projection 中写复杂业务规则

**借鉴参考**：
- Event Store 的 [Projections](https://www.eventstore.com/blog/event-sourcing-and-cqrs) 模式
- Martin Fowler 的 [CQRS 模式](https://martinfowler.com/bliki/CQRS.html)
- Redis 官方 [RedisOM for Python](https://github.com/redis/redis-om-python) 的对象映射

---

### v3.0.3：单 Edge VM 迁移

**前置条件**：v3.0.0 契约冻结 + v3.0.1 NATS 可用

**目标**：先把一个 agent 迁移到独立的 Edge VM/云服务器

**具体任务**：
1. 在低配云服务器（2C4G）上部署 `ogas-milling-edge`
2. 安装 Python 3.12 + node-agent 依赖
3. 配置 `node.env`：指向 central-api 的 NATS/host:port
4. 验证心跳通过 NATS 到达 central
5. 验证命令能从 central 跨网络到达 edge agent
6. 验证 edge 断线后：
   - Dashboard 显示 `offline`
   - 本地 SQLite outbox 缓存心跳
7. 验证 edge 恢复后：
   - 本地缓存补发（outbox drain）
   - central 更新状态为 `online`
8. 保留 process 模式回滚路径

**验收标准**：
- 停止 edge VM 后 Dashboard 显示 offline
- 恢复后事件可补发
- 命令能跨网络到达 agent
- process 模式仍可用作 fallback

**禁止**：一次迁移三个节点、把 VM running 当作节点健康、关闭 process fallback

**借鉴参考**：
- AWS IoT Greengrass 的 [边缘设备管理](https://docs.aws.amazon.com/greengrass/) 离线缓存模式
- Kubernetes 的 [Node Controller](https://kubernetes.io/docs/concepts/architecture/nodes/) 心跳超时机制
- HashiCorp Consul 的 [health check](https://developer.hashicorp.com/consul/docs/services/usage/checks) 模式

---

### v3.0.4：三 Edge VM

**目标**：turning、milling、grinding 全部运行在独立 VM

**具体任务**：
1. 为三个车间各建一个 VM/云实例
2. 每个 VM 使用独立的 `NODE_CODE`、`WORKSHOP_TYPE`、`LOCAL_DB_PATH`
3. 每个 VM 有独立的 `OGAS_API_TOKEN`
4. central 识别三个独立心跳
5. 验证任意 VM 停止时：
   - central 检测 `degraded`
   - 相应工单状态变更为 `blocked`
   - 其他节点不受影响
6. 验证 VM 恢复后缓存补传 + 工单恢复
7. Dashboard 节点树/拓扑图显示每个子节点独立状态

**验收标准**：
- 任意 edge 停止，central 检测 degraded
- 三工序事件通过网络流转（不通过共享内存）
- Dashboard 展示跨节点因果链

**禁止**：复制同一个 node_code、三个 VM 共享同一个数据库、某节点断线导致 central 崩溃

---

### v3.0.5：Router 与网络边界

**目标**：引入 `ogas-router` VM，管理网络分区

**具体任务**：
1. 创建 Router VM（可用轻量 Linux + iptables/nftables）
2. 定义 3 个网络区域：
   - **管理网络**：Dashboard + central-api 使用的网络
   - **生产网络**：3 个 Edge VM 使用的 Host-Only 网络
   - **实验网络**：Kali VM 使用的隔离网络
3. Router 白名单规则：
   - Edge → Central：允许心跳、命令轮询、零件认领
   - Central → Edge：允许命令下发
   - Kali → Edge：仅在 `ATTACK_LAB_MODE` 下放行指定端口
4. 记录 DNAT / 端口转发配置
5. 编写网络连通性和隔离性检查脚本

**验收标准**：
- NORMAL_MODE 下 Kali 无法访问 central 或 edge
- ATTACK_LAB_MODE 下临时放行指定端口
- 退出 attack lab 后规则自动恢复
- 所有跨网络流量被记录（摘要级）

**禁止**：Kali 访问宿主机敏感网段、API token 暴露在日志、所有 VM 在同一无边界的网络

**借鉴参考**：
- OWASP 的 [Network Segmentation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Network_Segmentation_Cheat_Sheet.html)
- NIST SP 800-82 工业控制系统安全指南的[网络分区](https://csrc.nist.gov/pubs/sp/800/82/r3/final)原则
- pfSense / OPNsense 的 VLAN 隔离配置模式

---

### v3.0.6：Attack Lab 安全实验

**目标**：让 Kali 攻击实验成为受控系统能力

**具体任务**：
1. 实现 `attack_lab_token` 机制
   - Token 有 TTL（默认 30 分钟）
   - Token 绑定 `attack_run_id`
2. 实现 `/api/security-lab/*` 路由组
   - `POST /api/security-lab/register` — 注册攻击节点
   - `POST /api/security-lab/attack-event` — 上报攻击事件
   - `GET /api/security-lab/status` — 查询实验状态
3. 攻击脚本白名单化（只能攻击授权 edge）
4. 攻击效果表现：节点断线 → 数据积压 → 质量异常 → 命令拒绝
5. AI 诊断引用攻击事件和节点状态
6. 修复脚本可审计、可回滚
7. 全流程写入 `audit_event`（攻击事件 + 防御响应）

**验收标准**：
- Attack lab 不污染 normal run（run_id 隔离）
- 所有攻击请求可审计
- 退出模式后 token 失效
- Dashboard 显示攻击实验模式标记

**禁止**：攻击非授权目标、运行不可控破坏性命令、攻击脚本和生产脚本同权限、绕过 Safety Governor

**借鉴参考**：
- MITRE ATT&CK 的 [ICS Matrix](https://attack.mitre.org/matrices/ics/) 攻击技术分类
- NSA 的 [Network Infrastructure Security Guidance](https://media.defense.gov/) 红蓝对抗方法论
- OWASP 的 [Web Security Testing Guide](https://owasp.org/www-project-web-security-testing-guide/) 测试分类法

---

### v3.0.7：ActionCoordinator 与多 AI 角色

**目标**：把 single AI loop 升级为多角色 AI proposal 协同

**具体任务**：
1. 定义 `action_proposal` schema
2. 实现 3 个 AI 角色（每个只提交 proposal，不直接执行）：
   - **Emergency AI**：处理设备故障、安全风险
   - **Maintenance AI**：处理刀具磨损、计划维护
   - **Scheduling AI**：处理排产优化、产能调配
3. 实现 `ActionCoordinator`
   - 合并冲突 proposal（同一节点同一资源的多个 proposal）
   - 优先级排序
   - 输出最终候选 action
4. Safety Governor 审核最终 action
5. Command Manager 执行被批准的 action
6. 记录被采纳/被拒绝/被覆盖的 proposal

**验收标准**：
- 多 AI 冲突时只有一个最终 action
- 被覆盖 proposal 标记 `superseded`
- 高风险 proposal 进入人工确认
- Dashboard 可查看 proposal 决策链

**禁止**：AI 直接写 command、多个 proposal 同时作用同一节点、忽略人工确认优先级

**借鉴参考**：
- Anthropic 的 [Multi-Agent Research](https://www.anthropic.com/research/building-effective-agents) 关于 agent 角色分工
- AWS 的 [Multi-Agent Orchestrator](https://github.com/awslabs/multi-agent-orchestrator) 框架
- Microsoft 的 [AutoGen](https://github.com/microsoft/autogen) 多 agent 对话模式

---

### v3.0.8：v3.0 最终验收

**目标**：证明 Mini-OGAS 已进入真正分布式状态

**验收清单**（10 项）：
1. 三 edge VM 独立运行（不同 host/网络）
2. 任意 edge 停止，central 检测 degraded
3. edge 恢复后事件补发（outbox drain）
4. NATS 作为主事件路径（HTTP 降级为 fallback）
5. PostgreSQL 作为历史事实源（event_store 可重建投影）
6. Redis/current_state 可重建
7. Command 跨网络到达 agent 并被 heartbeat 验证
8. Safety Governor 不能被绕过（人工确认码 + 角色检查 + 风险门控）
9. Dashboard 展示跨节点因果链（WIP transfer / command trace）
10. Kali attack lab 被隔离且全部操作可审计

**交付物**：
1. `docs/v3.0-acceptance-report.md` — 验收报告
2. `scripts/verify-v3.0-distributed.ps1` — 自动化验收脚本
3. 每个场景的 run_id 和审计日志

---

## 8. 不可变原则

以下 10 条原则在任何阶段都必须遵守，不得违反：

```text
1.  不全量重写 —— 增量演进，每次只改一个子系统
2.  不先删除旧 API —— 新 API 稳定后旧 API 退化为 wrapper
3.  不先切主事实源 —— 先 shadow write，验证一致性后再切主读
4.  不先引入 NATS/Redis 作为强依赖 —— 新传输路径先旁路运行
5.  不让 Dashboard 使用假数据冒充 live —— data_source 必须透明
6.  不让 LLM 直接做数值推理 —— LLM 只解释 rule conclusion
7.  不让 AI 直接修改 agent 状态 —— 必须经过 Safety Governor + Command Manager
8.  每个阶段都必须可运行、可测试、可回滚
9.  每个临时兼容层都必须记录退出条件（在 ARCHITECTURE_DEBT.md 中）
10. 当前已经跑通的链路不能被破坏：
    - 登录 → JWT → AI vault 解锁
    - 心跳 → Snapshot → Dashboard 渲染
    - 告警 → 规则引擎 → AI 解释 → 人工确认 → 关闭归档
    - 命令 → 轮询 → 执行 → 上报 → Heartbeat 验证
```

---

## 9. 禁止事项（反模式）

### 全局禁止

```text
- 禁止让 LLM 生成未经规则支持的数字
- 禁止隐藏 rule_fallback（必须透明显示 AI 是否参与）
- 禁止把原始 agent 日志直接输入 LLM（必须先经过规则引擎结构化）
- 禁止在前端本地计算业务事实并当成真实状态
- 禁止在 API 缺字段时伪造 live 值
- 禁止 Demo 模式跳过 Safety Governor
- 禁止把 API key 写进普通源码或文档
- 禁止一次性大重构（每个 PR 只改一个子系统）
```

### v3.0 阶段专属禁止

```text
- 禁止一次迁移三个节点到 VM（先做一个，验证后再推广）
- 禁止在未冻结部署契约前部署 VM
- 禁止关闭 process fallback 直到每个 VM 验证稳定
- 禁止让 Kali 攻击脚本访问宿主机敏感网段
- 禁止复制同一个 node_code 到多个 VM
- 禁止让某个节点断线导致 central 崩溃
- 禁止 NATS 故障导致本地 SQLite 缓存丢失
- 禁止发布无 schema 的随意 JSON 到 NATS
```

---

## 10. 借鉴的业界模式

### 事件驱动架构（Event-Driven Architecture）

| 模式 | 来源 | 在本项目的应用 |
|------|------|-------------|
| **Event Sourcing** | Event Store / Martin Fowler | PostgreSQL `event_store` 表记录所有状态变更 |
| **CQRS** | Greg Young / Microsoft | Dashboard 读投影（snapshot）与命令写（command_manager）分离 |
| **Outbox Pattern** | Chris Richardson / microservices.io | edge agent 断线时 SQLite 缓存心跳，恢复后补发 |
| **Idempotency Key** | Stripe API | 命令的 `command_id` + `version` 防止重复执行 |
| **Circuit Breaker** | Michael Nygard / Resilience4j | AI provider chain 降级链（deepseek → ollama → lm_studio → groq → fallback） |
| **Saga** | Hector Garcia-Molina / microservices.io | 命令生命周期（pending → claimed → executed → verified）为简化版 Saga |

### MES / 工业自动化

| 模式 | 来源 | 在本项目的应用 |
|------|------|-------------|
| **ISA-95 Activity Model** | ISA-95 Part 3 | 生产计划→调度→执行→数据采集的层次模型 |
| **OPC UA PubSub** | OPC Foundation | NATS subject 命名模拟 OPC UA 的 PubSub 信息模型 |
| **Asset Administration Shell** | Industrie 4.0 / IEC 63278 | 每个 node 有完整的 digital representation（心跳+生产+告警+运行时） |
| **Alarm Lifecycle (EEMUA 191)** | EEMUA Publication 191 | 告警状态机：unacknowledged → confirmed → diagnosed → contained → observing → closed |

### 安全架构

| 模式 | 来源 | 在本项目的应用 |
|------|------|-------------|
| **Purdue Model** | ISA-99 / IEC 62443 | Router VM 实现 Level 3-4（管理）与 Level 0-2（生产）的分区 |
| **Zero Trust** | NIST SP 800-207 | 每个 edge agent 有独立 token，命令需要验证+确认 |
| **Defense in Depth** | NSA / CISA | Safety Governor + Command Manager + Audit Trail 三层防护 |
| **Red Team / Blue Team** | MITRE ATT&CK | Attack Lab 为红队剧本，Safety Governor + Audit 为蓝队防御 |

---

## 11. 验收标准

### 每个 v3.0 子阶段的通用验收

```text
1. 前后端测试全部通过
2. git diff --check 无空白/换行问题
3. 新增代码有对应测试
4. 不破坏已有 API 兼容性（或已标记 deprecated）
5. Dashboard 无假数据，data_source 准确
6. 回滚路径可用
```

### v3.0 全局可用性指标

```text
- central-api 启动自检通过（preflight all_pass=true）
- 3/3 生产节点心跳正常
- PostgreSQL primary projection healthy
- AI vault unlockable via administrator login
- DeepSeek smoke test passes
- Go supervisor 管理所有进程健康
- Dashboard snapshot data_source=live, simulation_engine=simpy
```

---

## 12. 关键文件路径索引

### 核心服务代码

| 路径 | 说明 |
|------|------|
| `services/central-api/app/store.py` | 中央状态存储（~4000 行，核心逻辑） |
| `services/central-api/app/models.py` | Pydantic 数据模型 |
| `services/central-api/app/rules.py` | 规则引擎（瓶颈/饥饿/离线/过期/缺陷检测） |
| `services/central-api/app/rule_explanation.py` | AI 规则解释（含缓存和单飞模式） |
| `services/central-api/app/safety_governor.py` | 安全仲裁器（角色/风险/确认码门控） |
| `services/central-api/app/command_manager.py` | 命令生命周期管理器 |
| `services/central-api/app/command_verifier.py` | 命令效果验证器 |
| `services/central-api/app/core/database.py` | 数据库抽象层（PostgreSQL/SQLite） |
| `services/central-api/app/persistence_repository.py` | 持久化仓储 |
| `services/central-api/app/routers/demo.py` | Snapshot 构建 + Dashboard 状态 |
| `services/central-api/app/routers/compat.py` | Codex 前端兼容层 |
| `services/central-api/app/routers/replay.py` | 运行回放 API |
| `services/central-api/app/routers/nodes.py` | 心跳/命令/零件队列 API |
| `services/node-agent/simulator.py` | SimPy 仿真器 + HTTP heartbeat |
| `services/node-agent/agent.py` | 旧版 agent（向后兼容） |
| `services/node-agent/event_publishers.py` | EventPublisher 接口 + HTTPPublisher |
| `services/node-agent/runtime_adapters.py` | RuntimeAdapter 接口 + SimPy/Simple 实现 |

### Dashboard

| 路径 | 说明 |
|------|------|
| `services/dashboard/src/types.ts` | 全部 TypeScript 类型定义 |
| `services/dashboard/src/runtimeState.ts` | Snapshot 到 DashboardState 的转换 |
| `services/dashboard/src/FactoryRuntimeView.vue` | 工厂总览主视图 |
| `services/dashboard/src/useRuntimePresentation.ts` | 运行时数据到 UI 模型的映射 |

### 数据库与配置

| 路径 | 说明 |
|------|------|
| `database/central-schema.sql` | PostgreSQL 完整 schema |
| `database/node-schema.sql` | SQLite 本地节点 schema |
| `config/supervisor.toml` | Go Supervisor 进程定义 |
| `.env.example` | 完整环境变量定义（45 个变量） |

### 文档

| 路径 | 说明 |
|------|------|
| `PROJECT_STATUS.md` | 项目当前状态（单页概览） |
| `docs/mini-ogas-three-stage-phased-implementation.md` | 三阶段实施总计划 |
| `docs/ARCHITECTURE_DEBT.md` | 架构债务登记册（20 项） |
| `docs/architecture.md` | 架构设计文档 |
| `docs/contracts-v2.2.md` | v2.2 API 契约 |
| `docs/database-design.md` | 数据库设计 |
| `docs/permission-design.md` | 权限设计（RBAC） |
| `docs/supervisor-runtime.md` | Go Supervisor 运行时设计 |

### 验证脚本

| 路径 | 说明 |
|------|------|
| `scripts/verify-miniogas.ps1` | 综合验收脚本（最权威） |
| `scripts/check_runtime_workflow.py` | 运行时全链路验证 |
| `scripts/check_api_contract.py` | API 契约检查 |
| `scripts/start-miniogas.ps1` | 系统启动入口 |
| `scripts/start-supervisor.ps1` | Go Supervisor 启动 |

---

## 使用说明

将此文件作为 AI 编程代理的系统提示词使用时：

1. **首次对话**：将完整文件粘贴给代理，并要求其先阅读理解再回答
2. **具体任务**：引用文件中的子阶段编号（如 "实现 v3.0.1 NATS EventPublisher"）
3. **上下文压缩**：如果对话过长，可以只提供 §7（任务分解）+ §8（原则）+ §12（文件索引）
4. **验收**：每个子阶段完成后，要求代理对照 §11 验收标准逐项检查

**禁止代理的行为**：
- 跳过 v3.0.0 契约冻结直接开始写代码
- 在未做 shadow write 验证的情况下切主事实源
- 删除 REST 心跳路径（应用 NATS 并行模式）
- 让 Kali VM 访问生产网络
- 绕过 Safety Governor

---

*此文件基于 2026-07-13 的项目快照生成，代码版本对应 git commit 序列 f3d8d88 及之前。*
