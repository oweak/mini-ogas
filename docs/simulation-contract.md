# Mini-OGAS v2.2 Simulation Contract

日期：2026-06-13
阶段：`v2.2.0 契约冻结与债务登记`

## 1. 目的

Mini-OGAS 的仿真必须服务于真实工业管理系统的表达：节点持续运行、工单持续推进、设备损耗缓慢积累、报警由实际状态触发、处置后状态有可见变化、结果进入日志归档。仿真不能只是前端动画，也不能让所有问题都变成同一种温度故障。

## 2. 当前仿真事实

当前 `services/node-agent/simulator.py` 已包含三类车间节点：

| workshop_type | node_code 示例 | machine_code | cycle_time_sec | base_yield_rate |
| --- | --- | --- | --- | --- |
| `milling` | `milling-workshop-01` | `MILL-02` | 60 | 0.965 |
| `turning` | `turning-workshop-01` | `LATHE-01` | 45 | 0.975 |
| `grinding` | `grinding-workshop-01` | `GRIND-01` | 75 | 0.982 |

当前已支持的异常类型：

| 类型 | 来源 | 决策倾向 |
| --- | --- | --- |
| `SPINDLE_TEMP_HIGH` | 主轴温度过高 | 高风险，人工决策 |
| `TOOL_WEAR_WARNING` | 刀具/砂轮磨损接近上限 | 中风险，自动处置或维护提醒 |
| `QUALITY_DRIFT` | 良品率漂移 | 中风险，自动抽检/参数复核 |
| `VIBRATION_HIGH` | 振动异常 | 高风险，人工决策 |
| `COOLANT_FLOW_LOW` | 冷却液流量偏低 | 中风险，自动降载/现场检查提醒 |
| `SYNC-DELAY` | 本地记录积压 | 中低风险，自动重连/补传 |

## 3. 仿真时间

v2.2 引入仿真时间，不直接等同于系统时间。

```json
{
  "run_id": "RUN-20260613-001",
  "scenario_id": "SCN-NORMAL-MIXED-001",
  "simulation_time": "2026-06-13T10:00:00+08:00",
  "simulation_speed": 12,
  "wall_time": "2026-06-13T09:05:00+08:00"
}
```

规则：

1. `simulation_time` 由仿真运行时或 node-agent 产生。
2. `simulation_speed=1` 表示等速，`12` 表示仿真 12 倍速。
3. Dashboard 只能展示后端传来的仿真时间。
4. 缺少仿真时间时显示 `未上报`，不能在前端伪造。

## 4. 生产状态指标

v2.2 心跳应逐步补齐以下指标。

| 指标 | 含义 | 合法范围/单位 |
| --- | --- | --- |
| `finished_quantity` | 已完成件数 | 非负整数 |
| `defect_quantity` | 缺陷件数 | 非负整数，不能大于 finished |
| `wip_input` | 工序入口在制品 | 非负整数 |
| `wip_output` | 工序出口在制品 | 非负整数 |
| `target_rate` | 目标产出速率 | 件/分钟或契约指定单位 |
| `actual_rate` | 实际产出速率 | 同 target_rate |
| `utilization` | 设备利用率 | 0 到 1 |
| `defect_rate` | 缺陷率 | 0 到 1 |
| `tool_wear_level` | 刀具/砂轮磨损 | 0 到 100 |
| `spindle_temp` | 主轴温度 | 摄氏度 |
| `pending_records` | 本地待同步记录 | 非负整数 |

示例：

```json
{
  "production": {
    "machine_code": "GRIND-01",
    "workshop_type": "grinding",
    "active_order": "WO-20260530-006",
    "finished_quantity": 69,
    "defect_quantity": 1,
    "wip_input": 9,
    "wip_output": 6,
    "target_rate": 0.8,
    "actual_rate": 0.72,
    "utilization": 0.81,
    "defect_rate": 0.014,
    "tool_wear_level": 66.4,
    "spindle_temp": 69.8
  }
}
```

## 5. 场景定义

### 正常混合生产

```json
{
  "scenario_id": "SCN-NORMAL-MIXED-001",
  "description": "三节点正常生产，设备损耗缓慢增长，偶发轻微同步积压。",
  "expected_alerts": [],
  "duration_sim_minutes": 480
}
```

要求：

1. 系统启动后不应立刻堆满报警。
2. 前 30 个心跳默认保持稳定。
3. 损耗部件增长必须缓慢，不能每次进入系统都立即报废。

### 冷却流量偏低

```json
{
  "scenario_id": "SCN-MILLING-COOLANT-LOW-001",
  "affected_node": "milling-workshop-01",
  "alarm_type": "COOLANT_FLOW_LOW",
  "severity": "medium",
  "expected_resolution": "自动降载并创建现场检查提醒"
}
```

### 良品率漂移

```json
{
  "scenario_id": "SCN-TURNING-QUALITY-DRIFT-001",
  "affected_node": "turning-workshop-01",
  "alarm_type": "QUALITY_DRIFT",
  "severity": "medium",
  "expected_resolution": "创建抽检任务并建议复核刀补参数"
}
```

### 砂轮磨损预警

```json
{
  "scenario_id": "SCN-GRINDING-WEAR-001",
  "affected_node": "grinding-workshop-01",
  "alarm_type": "TOOL_WEAR_WARNING",
  "severity": "medium",
  "expected_resolution": "降低进给速度并创建维护提醒"
}
```

### 振动高危

```json
{
  "scenario_id": "SCN-GRINDING-VIBRATION-HIGH-001",
  "affected_node": "grinding-workshop-01",
  "alarm_type": "VIBRATION_HIGH",
  "severity": "high",
  "expected_resolution": "人工确认后暂停加工、派遣维修、转移剩余工单"
}
```

### 主轴温度高危

```json
{
  "scenario_id": "SCN-SPINDLE-TEMP-HIGH-001",
  "affected_node": "turning-workshop-01",
  "alarm_type": "SPINDLE_TEMP_HIGH",
  "severity": "high",
  "expected_resolution": "人工确认后停机检修并观察恢复"
}
```

### 同步积压

```json
{
  "scenario_id": "SCN-SYNC-DELAY-001",
  "affected_node": "milling-workshop-01",
  "alarm_type": "SYNC-DELAY",
  "severity": "medium",
  "expected_resolution": "脚本重连 central-api，本地缓存保留并补传"
}
```

## 6. 规则触发边界

规则引擎只能基于后端收到的事实触发。

| 报警 | 触发依据 |
| --- | --- |
| 主轴温度过高 | `spindle_temp >= temp_fault` 且节点上报 `SPINDLE_TEMP_HIGH` |
| 刀具/砂轮磨损 | `tool_wear_level >= tool_wear_warning` 或节点上报 `TOOL_WEAR_WARNING` |
| 良品率漂移 | `defect_rate` 或 `defect_quantity / finished_quantity` 高于阈值，或节点上报 `QUALITY_DRIFT` |
| 振动异常 | 节点上报 `VIBRATION_HIGH`，后续可增加振动 RMS 指标 |
| 冷却液流量偏低 | 节点上报 `COOLANT_FLOW_LOW`，后续可增加流量值 |
| 同步积压 | `sync.pending_records > 0` |

## 7. 处置效果契约

任何问题处理后必须出现三个效果：

1. 报警从主报警队列消失，或进入 `observing` 并明确显示观察期。
2. 相关节点状态发生合理变化，例如恢复 `running`、进入 `maintenance`、或标记 `isolated`。
3. 日志管理出现归档事件。

示例归档：

```json
{
  "actor": "车间主管",
  "role": "车间主管",
  "permission": "人工高风险审批",
  "subject": "milling-workshop-01-SPINDLE_TEMP_HIGH",
  "action": "批准停机检修",
  "result": "节点进入 maintenance，报警关闭，工单转移待计算",
  "status": "resolved",
  "node_code": "milling-workshop-01",
  "issue_id": "milling-workshop-01-SPINDLE_TEMP_HIGH",
  "severity": "高",
  "source": "central-api"
}
```

## 8. 科学性约束

1. 损耗类指标应随产量缓慢增长，不得在普通模式下几秒内达到故障。
2. 高危故障必须有物理解释，例如温度、振动、冷却、磨损。
3. 质量问题不应总是由温度触发，可由刀补、夹具、磨损或批次差异解释。
4. 网络/同步问题不应改变设备物理状态，只影响数据传输和日志补传。
5. AI 只解释和建议，不能编造不存在的传感器值。

## 9. v2.2.0 验收

1. 已列出当前真实仿真能力。
2. 已定义仿真时间、场景、生产指标。
3. 已明确多类报警，不再只围绕温度。
4. 已定义处置后前端和日志必须看到的效果。
