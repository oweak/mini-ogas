# Mini-OGAS v2.2 API Compatibility Plan

日期：2026-06-13
阶段：`v2.2.0 契约冻结与债务登记`

## 1. 目的

本文定义 v2.2 如何在不破坏当前 Mini-OGAS 的情况下扩展 API。原则是先兼容、后迁移、再退役。当前已经可运行的登录、自检、AI vault、告警、日志、节点心跳和工单调度链路不得被破坏。

## 2. 兼容策略

```text
v2.2.0：只写文档，冻结接口和债务。
v2.2.1：在旧 heartbeat 上增加可选字段。
v2.2.2：Dashboard 只展示后端传来的新增字段。
v2.2.3：新增 snapshot adapter，只读，不强制切换。
v2.5：再把 snapshot 变成主事实接口。
```

## 3. 旧接口到 v2.2 的映射

| 当前接口 | 当前消费者 | 当前生产者 | v2.2 目标 | 兼容要求 |
| --- | --- | --- | --- | --- |
| `GET /api/dashboard-state` | Dashboard | central-api | 保留为 legacy state | 字段只增不删 |
| `POST /api/node-heartbeats` | node-agent | central-api | 承载 Heartbeat v1/v2 混合 | v1 payload 必须继续可用 |
| `POST /api/node-records/sync` | node-agent | central-api | 保留本地缓存补传 | 不改变 records 包装结构 |
| `GET /api/node-dispatches/{node_code}` | node-agent | central-api | 保留工单下发 | 不改变 active_order / policy 语义 |
| `GET /api/alerts` | Dashboard | central-api | 保留报警列表 | 已关闭问题不得出现 |
| `POST /api/alerts/{issue_id}/confirm` | Dashboard | central-api | 保留人工确认 | 只允许主管/管理员 |
| `POST /api/ai/diagnose/{issue_id}` | Dashboard | central-api + LLM | 保留 AI 诊断 | 诊断前必须确认报警 |
| `POST /api/issues/{issue_id}/actions` | Dashboard | central-api | 保留问题动作入口 | 动作结果必须写日志和归档 |
| `POST /api/ops/dispatch-plan/approve` | Dashboard | central-api | 保留调度审批 | 审批后必须归档并从待审批视图消失 |

## 4. 新增接口

### `GET /api/dashboard/snapshot`

用途：稳定提供前端需要的运行快照。

v2.2.3 初版实现约束：

1. 内部允许复用 `build_dashboard_state` 的数据。
2. 对外返回 `schema_version=2.2`。
3. 必须提供 `data_source`。
4. 必须提供 `run` 对象，即使旧数据缺字段也要标记为空/unknown，不能冒充 live。
5. 前端在 v2.2.3 只可选读取，不强制切换。

示例：

```json
{
  "schema_version": "2.2",
  "generated_at": "2026-06-13T10:30:00+08:00",
  "data_source": "live",
  "run": {
    "run_id": "RUN-20260613-001",
    "scenario_id": "SCN-NORMAL-MIXED-001",
    "simulation_time": "2026-06-13T10:30:00+08:00",
    "simulation_speed": 12
  },
  "nodes": [],
  "work_orders": [],
  "alerts": []
}
```

## 5. 字段兼容规则

### 后端接收规则

1. `Heartbeat` 模型继续允许 `metrics`、`production`、`sync`、`runtime` 为可选对象。
2. 新增 v2 字段必须放在现有对象内，避免顶层膨胀。
3. 后端存储未知字段时可以透传，但不能依赖未知字段做关键状态判断。
4. 错误 payload 必须返回可解释错误，不得导致服务退出。

### 前端读取规则

1. 优先读取后端字段。
2. 缺字段时显示 `未上报`、`unknown` 或降级状态。
3. 不允许前端本地生成 `run_id`、`scenario_id`、`simulation_time` 并显示为 live。
4. `fixture` 和 `fallback` 必须在界面上可见。

## 6. 版本字段

v2.2 建议引入但不强制 v1 节点提供：

```json
{
  "schema_version": "2.2",
  "agent_version": "0.2.0"
}
```

兼容规则：

1. 没有 `schema_version` 的心跳视为 v1。
2. `schema_version=2.2` 的心跳必须接受 v2 字段校验。
3. `agent_version` 只用于观测和排错，不用于拒绝心跳。

## 7. API 错误响应基线

所有新增接口和后续改造接口应使用统一错误形状。

```json
{
  "ok": false,
  "error": "confirmation_code_required",
  "message": "调度变更会影响生产，需要输入 CONFIRM 后执行。",
  "request_id": "REQ-20260613-001"
}
```

其中：

| 字段 | 要求 |
| --- | --- |
| `ok` | 失败时为 `false` |
| `error` | 机器可读错误码 |
| `message` | 人可读中文说明 |
| `request_id` | 如可获得则返回 |

## 8. 权限兼容

当前系统使用 `actor` / `operator` 字段判断主管权限。v2.2 不改变该机制。

高风险接口继续要求：

```json
{
  "actor": "车间主管",
  "confirmation_code": "CONFIRM"
}
```

受影响接口：

1. `POST /api/nodes/{node_code}/isolate`
2. `POST /api/nodes/{node_code}/retire`
3. `POST /api/ops/dispatch-plan/approve`
4. `POST /api/ops/escalations/{id}/decision`
5. `POST /api/issues/{issue_id}/decision`

## 9. 迁移路径

### 阶段 A：v2.2 兼容

1. `node-agent` 上报 v1 + v2 可选字段。
2. `central-api` 接收并透传 v2 字段。
3. Dashboard 增加只读展示。
4. `GET /api/dashboard/snapshot` 只作为 adapter。

### 阶段 B：v2.5 切换

1. Dashboard 主读取切换到 snapshot。
2. `dashboard-state` 改为 wrapper。
3. PostgreSQL 成为主事实源。
4. legacy 字段保留一段时间。

### 阶段 C：v3.0 分布式

1. 节点心跳进入事件总线。
2. 当前状态进入 projection。
3. REST 主要提供查询和管理动作。

## 10. 退出条件

| 旧能力 | 可退役条件 |
| --- | --- |
| Dashboard 直接依赖 `dashboard-state` | Snapshot 覆盖所有页面字段并通过前端测试 |
| Heartbeat v1 无 schema 版本 | 三个节点均上报 v2 字段且兼容测试通过 |
| 前端读取 `virtualbox` 判断生产节点 | 心跳 deployment_mode 与分布式部署状态成为主证据 |
| AI fallback 文案混入 API 成功态 | AI runtime 状态全链路展示，测试覆盖 API/fallback 区分 |

## 11. v2.2.0 验收

本文件完成后，v2.2.0 对 API 的验收标准为：

1. 旧接口清单明确。
2. 新 snapshot 接口边界明确。
3. 心跳 v1/v2 兼容策略明确。
4. 权限和错误响应基线明确。
5. 每个临时兼容层有退出条件。
