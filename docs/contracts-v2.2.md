# Mini-OGAS v2.2 Contract Baseline

日期：2026-06-13
阶段：`v2.2.0 契约冻结与债务登记`
状态：冻结草案，供 `v2.2.1` 之后实现使用。

## 1. 目标

本文件冻结 Mini-OGAS v2.2 的数据契约。v2.2 的目标不是替换当前运行系统，而是在保留既有 `central-api`、`node-agent`、`dashboard` 链路的前提下，增加可信仿真、规则判断、AI 解释和低风险命令闭环。

本阶段只新增文档，不修改运行代码。

## 2. 保留接口

v2.2 必须保持以下接口可用：

| 接口 | 方向 | 当前用途 | v2.2 处理 |
| --- | --- | --- | --- |
| `GET /health` | Dashboard / 脚本 -> central-api | 系统运行、节点数、AI、VirtualBox 状态 | 保留，后续可增加字段 |
| `GET /api/system/preflight` | Dashboard -> central-api | 登录前自检 | 保留 |
| `POST /api/auth/login` | Dashboard -> central-api | 管理员登录、解锁 AI vault、AI smoke test | 保留 |
| `GET /api/dashboard-state` | Dashboard -> central-api | 当前主驾驶舱事实源 | 保留，v2.2 仍作为旧事实聚合 |
| `POST /api/node-heartbeats` | node-agent -> central-api | 子节点心跳、生产、报警、同步状态 | 保留路径，兼容扩展 heartbeat v2 字段 |
| `POST /api/node-records/sync` | node-agent -> central-api | 子节点断线缓存补传 | 保留 |
| `GET /api/node-dispatches/{node_code}` | node-agent -> central-api | 主机端向子节点下发当前工单 | 保留 |
| `GET /api/alerts` | Dashboard -> central-api | 报警队列 | 保留 |
| `POST /api/alerts/{issue_id}/confirm` | Dashboard -> central-api | 人工确认报警 | 保留 |
| `POST /api/ai/diagnose/{issue_id}` | Dashboard -> central-api -> LLM | 对已确认报警做 AI 诊断 | 保留 |
| `GET /api/ai/decisions` | Dashboard -> central-api | AI 决策缓存 | 保留 |
| `GET /api/audit/events` | Dashboard -> central-api | 日志管理/审计归档 | 保留 |
| `POST /api/ops/dispatch-plan/recalculate` | Dashboard -> central-api | 重新计算调度方案 | 保留 |
| `POST /api/ops/dispatch-plan/approve` | Dashboard -> central-api | 审批调度变更 | 保留 |
| `POST /api/ops/escalations/{id}/decision` | Dashboard -> central-api | 人工升级项审批/驳回 | 保留 |
| `POST /api/issues/{issue_id}/actions` | Dashboard -> central-api | 对问题执行处置动作 | 保留 |

## 3. 新增接口规划

v2.2.3 允许新增以下只读接口：

```text
GET /api/dashboard/snapshot
```

该接口在 v2.2 阶段只作为 `GET /api/dashboard-state` 的稳定快照适配层，不直接替换前端主链路。

## 4. Heartbeat v1 当前契约

当前 `node-agent` 上报的心跳应至少兼容如下结构：

```json
{
  "node_code": "milling-workshop-01",
  "timestamp": "2026-06-13T02:20:00+00:00",
  "status": "running",
  "agent_version": "0.1.0",
  "uptime_sec": 300,
  "runtime": {
    "deployment_mode": "process",
    "simulation_mode": "normal",
    "host": "miniogas-host",
    "pid": 12345,
    "heartbeat_sec": 5
  },
  "metrics": {
    "cpu_usage": 58.2,
    "memory_usage": 62.5,
    "disk_usage": 64.2,
    "network_latency_ms": 41,
    "db_latency_ms": 19
  },
  "production": {
    "active_order": "WO-20260530-004",
    "dispatch_policy": "ai_auto_dispatch",
    "machine_code": "MILL-02",
    "workshop_type": "milling",
    "finished_quantity": 52,
    "defect_quantity": 1,
    "tool_wear_level": 26.2,
    "spindle_temp": 65.4
  },
  "alarms": [],
  "sync": {
    "last_sync_id": 60,
    "pending_records": 0
  }
}
```

### 兼容要求

1. `node_code`、`status` 是强依赖字段。
2. `metrics`、`production`、`sync`、`runtime` 允许为空或缺失，但缺失时不能导致 `central-api` 崩溃。
3. `alarms` 必须默认为数组。
4. `central-api` 不应要求 v1 节点立即提供 v2 字段。

## 5. Heartbeat v2 新增字段

v2.2.1 在旧 `POST /api/node-heartbeats` 上兼容增加以下字段。

```json
{
  "node_code": "milling-workshop-01",
  "timestamp": "2026-06-13T02:20:00+00:00",
  "status": "running",
  "runtime": {
    "deployment_mode": "process",
    "simulation_mode": "normal",
    "host": "miniogas-host",
    "pid": 12345,
    "heartbeat_sec": 5,
    "run_id": "RUN-20260613-001",
    "scenario_id": "SCN-NORMAL-MIXED-001",
    "simulation_time": "2026-06-13T10:20:00+08:00",
    "simulation_speed": 12,
    "runtime_source": "node-agent"
  },
  "production": {
    "active_order": "WO-20260530-004",
    "dispatch_policy": "ai_auto_dispatch",
    "machine_code": "MILL-02",
    "workshop_type": "milling",
    "finished_quantity": 52,
    "defect_quantity": 1,
    "tool_wear_level": 26.2,
    "spindle_temp": 65.4,
    "wip_input": 18,
    "wip_output": 11,
    "target_rate": 1.0,
    "actual_rate": 0.93,
    "utilization": 0.78,
    "defect_rate": 0.019
  },
  "alarms": [
    {
      "type": "COOLANT_FLOW_LOW",
      "severity": "medium",
      "status": "open",
      "evidence": {
        "coolant_flow_lpm": 11.4,
        "threshold_lpm": 14.0
      }
    }
  ],
  "sync": {
    "last_sync_id": 60,
    "pending_records": 2
  }
}
```

### Heartbeat v2 字段语义

| 字段 | 类型 | 位置 | 说明 |
| --- | --- | --- | --- |
| `run_id` | string | `runtime` | 一次仿真/运行批次 ID |
| `scenario_id` | string | `runtime` | 场景 ID，例如正常生产、刀具磨损、网络延迟 |
| `simulation_time` | ISO string | `runtime` | 仿真内部时间，不等同于系统墙钟 |
| `simulation_speed` | number | `runtime` | 仿真倍率，例如 1、12、60 |
| `runtime_source` | string | `runtime` | `node-agent`、`simpy-runtime`、`fixture`、`fallback` |
| `wip_input` | number | `production` | 当前工序输入在制品 |
| `wip_output` | number | `production` | 当前工序输出在制品 |
| `target_rate` | number | `production` | 目标节拍/产出速率，单位由仿真契约定义 |
| `actual_rate` | number | `production` | 实际节拍/产出速率 |
| `utilization` | number | `production` | 设备利用率，范围 0 到 1 |
| `defect_rate` | number | `production` | 缺陷率，范围 0 到 1 |

## 6. Dashboard Snapshot Schema

v2.2.3 新接口 `GET /api/dashboard/snapshot` 应返回稳定快照，不要求前端理解旧聚合细节。

```json
{
  "schema_version": "2.2",
  "generated_at": "2026-06-13T10:21:00+08:00",
  "data_source": "live",
  "run": {
    "run_id": "RUN-20260613-001",
    "scenario_id": "SCN-NORMAL-MIXED-001",
    "simulation_time": "2026-06-13T10:20:00+08:00",
    "simulation_speed": 12
  },
  "system": {
    "status": "ok",
    "nodes_connected": 3,
    "nodes_expected": 3,
    "ai_runtime": {
      "status": "configured",
      "provider": "deepseek",
      "model": "deepseek-v4-pro",
      "source": "vault",
      "vault_present": true,
      "vault_unlocked": true
    }
  },
  "nodes": [
    {
      "node_code": "milling-workshop-01",
      "status": "running",
      "machine_code": "MILL-02",
      "active_order": "WO-20260530-004",
      "runtime_source": "node-agent",
      "last_seen_sec": 2,
      "production": {
        "finished_quantity": 52,
        "defect_quantity": 1,
        "wip_input": 18,
        "wip_output": 11,
        "target_rate": 1.0,
        "actual_rate": 0.93,
        "utilization": 0.78,
        "defect_rate": 0.019
      },
      "alarms": []
    }
  ],
  "work_orders": [
    {
      "id": "WO-20260530-004",
      "product": "阀体",
      "quantity": 160,
      "completed": 52,
      "assigned_node": "milling-workshop-01",
      "status": "in_progress"
    }
  ],
  "alerts": [],
  "dispatch_plan": {
    "id": "DP-20260613-001",
    "status": "no_action",
    "summary": "当前无需调度变更。"
  },
  "audit": {
    "recent_events": []
  }
}
```

### Snapshot 来源标记

| 值 | 含义 | 前端展示规则 |
| --- | --- | --- |
| `live` | 来自真实 `central-api` 和节点心跳 | 可显示为实时运行 |
| `fallback` | 后端降级结果 | 必须显示降级，不得冒充实时 |
| `fixture` | 前端或测试夹具 | 只用于测试/演示，不得显示为真实生产 |
| `replay` | 回放数据 | 必须显示回放批次 |

## 7. Rule Conclusion Schema

规则引擎输出必须是可解释结论，而不是直接修改节点状态。

```json
{
  "schema_version": "2.2",
  "rule_id": "RULE-SPINDLE-TEMP-HIGH",
  "issue_id": "milling-workshop-01-SPINDLE_TEMP_HIGH",
  "node_code": "milling-workshop-01",
  "machine_code": "MILL-02",
  "severity": "high",
  "title": "MILL-02 主轴温度过高",
  "status": "open",
  "decision": "human",
  "evidence": [
    {
      "name": "spindle_temp",
      "value": 89.0,
      "threshold": 82.0,
      "unit": "C"
    }
  ],
  "recommended_actions": [
    "派遣维修工人",
    "停机挂牌",
    "创建主轴检查工单"
  ],
  "created_at": "2026-06-13T10:22:00+08:00"
}
```

### 规则边界

1. 规则引擎可以生成报警、处置建议、风险等级。
2. 规则引擎不能直接删除报警。
3. 规则引擎不能直接把故障节点改为正常。
4. 自动处置必须经过后端处置函数并写入审计事件。

## 8. LLM Explanation Schema

AI 的作用是解释、诊断、给方案和提出追问，不直接控制设备。

```json
{
  "schema_version": "2.2",
  "issue_id": "milling-workshop-01-SPINDLE_TEMP_HIGH",
  "source": "api",
  "provider": "deepseek",
  "model": "deepseek-v4-pro",
  "status": "connected",
  "generated_at": "2026-06-13T10:23:00+08:00",
  "summary": "主轴温度超过阈值，且伴随刀具磨损升高，应优先按设备物理风险处理。",
  "risk_assessment": "继续生产可能导致主轴轴承损伤或工件报废。",
  "requires_human": true,
  "automation_allowed": false,
  "confidence": 0.76,
  "root_cause_hypotheses": [
    "冷却液循环不足",
    "主轴轴承润滑异常",
    "刀具磨损导致切削热增加"
  ],
  "evidence": [
    "spindle_temp=89 C > threshold=82 C",
    "tool_wear_level=78%",
    "active_order=WO-20260530-004"
  ],
  "recommended_plan": [
    "暂停当前节点新工件进入",
    "派遣维修工人检查冷却、轴承和润滑",
    "将未开始工单转移到健康节点",
    "维修后观察 3 个心跳周期"
  ],
  "options": [
    {
      "label": "停机检修",
      "risk": "低",
      "automation": false,
      "rationale": "该动作影响生产，需要人工确认。"
    },
    {
      "label": "降载观察",
      "risk": "中",
      "automation": true,
      "rationale": "适用于未达到高危阈值的预警。"
    }
  ],
  "questions_to_operator": [
    "现场是否观察到冷却液流量下降？",
    "该主轴最近一次保养时间是什么？"
  ]
}
```

### AI 边界

1. LLM 不得直接生成设备写入命令。
2. LLM 不得绕过 `CONFIRM` 人工确认。
3. LLM 不负责精确数值仿真，数值事实来自仿真/心跳/数据库。
4. LLM 回退到规则解释时必须标记 `source` 和 `status`，不能冒充 API 调用成功。

## 9. Command Schema

命令对象用于后续低风险 command polling。命令不是 AI 直接写设备，而是由主机端生成，子节点拉取，节点按权限执行并回报。

```json
{
  "schema_version": "2.2",
  "command_id": "CMD-20260613-001",
  "node_code": "milling-workshop-01",
  "issue_id": "milling-workshop-01-COOLANT_FLOW_LOW",
  "command_type": "adjust_load_limit",
  "risk_level": "low",
  "requires_human": false,
  "created_by": "central-api",
  "approved_by": "system",
  "created_at": "2026-06-13T10:24:00+08:00",
  "payload": {
    "load_limit": 0.72,
    "observe_heartbeat_count": 3
  },
  "expected_effect": {
    "node_status": "running",
    "alarm_status": "observing",
    "audit_required": true
  },
  "status": "pending"
}
```

高风险命令示例：

```json
{
  "schema_version": "2.2",
  "command_id": "CMD-20260613-002",
  "node_code": "milling-workshop-01",
  "issue_id": "milling-workshop-01-SPINDLE_TEMP_HIGH",
  "command_type": "stop_machine_for_maintenance",
  "risk_level": "high",
  "requires_human": true,
  "created_by": "central-api",
  "approved_by": "车间主管",
  "confirmation_code": "CONFIRM",
  "payload": {
    "maintenance_reason": "spindle temperature exceeded physical risk threshold"
  },
  "status": "approved"
}
```

## 10. ID 约定

| ID | 格式 | 示例 |
| --- | --- | --- |
| `run_id` | `RUN-YYYYMMDD-NNN` | `RUN-20260613-001` |
| `scenario_id` | `SCN-{domain}-{case}-{NNN}` | `SCN-NORMAL-MIXED-001` |
| `issue_id` | `{node_code}-{alarm_type}` | `milling-workshop-01-SPINDLE_TEMP_HIGH` |
| `command_id` | `CMD-YYYYMMDD-NNN` | `CMD-20260613-001` |
| `dispatch_plan.id` | `DP-YYYYMMDD-HHMMSS` | `DP-20260613-103012` |

## 11. 临时兼容层退出条件

| 兼容层 | 用途 | 退出条件 |
| --- | --- | --- |
| `GET /api/dashboard-state` 作为主前端事实源 | 保持当前 Dashboard 运行 | `GET /api/dashboard/snapshot` 覆盖所有前端所需字段并通过测试 |
| Heartbeat v1/v2 混合 | 允许旧节点继续上报 | 三个节点均稳定上报 v2 字段 72 小时或 1000 个心跳周期 |
| Snapshot Adapter 从旧聚合转换 | 避免一次性重写 | PostgreSQL 主事实源和 replay 通过 v2.5 验收 |
| AI fallback 规则解释 | 外部模型失败时保持系统可运行 | AI API 可观测性、超时、错误状态均完整展示，且测试覆盖 |
| VirtualBox 可选状态 | 本机/VM 混合运行 | 三 Edge VM 稳定后，将 VM 状态改为真实分布式部署证据 |

## 12. 不变量

1. Dashboard 不得把 fixture/fallback 标记为 live。
2. 已处理问题必须进入审计归档。
3. 已关闭问题不能继续出现在报警处置主队列。
4. AI 诊断必须显示来源、模型、置信度、证据、建议和是否需要人工。
5. 高风险动作必须要求 `CONFIRM`。
6. 子节点心跳是运行事实的主要来源，前端不得单独伪造生产事实。
