# Mini-OGAS v2.2 Test Matrix

日期：2026-06-13
阶段：`v2.2.0 契约冻结与债务登记`

## 1. 目的

本文定义 v2.2 每个小阶段必须通过的测试。v2.2 的测试重点不是追求大而全，而是防止再次出现这些问题：

1. 前端没有根据后端状态运行。
2. 所有报警都变成温度过高。
3. AI 看起来像问答机器，没有真实参与系统。
4. 人工审批没有入口或没有效果。
5. 问题解决后仍保留在报警队列。
6. 已处理问题没有进入日志管理。
7. Dashboard 把假数据当成 live。

## 2. 测试分层

| 层级 | 工具 | 覆盖对象 |
| --- | --- | --- |
| Python 单元测试 | `pytest` | `central-api`、规则、AI、调度、处置、运行状态 |
| Node 单元测试 | `vitest` | Dashboard 状态转换、轮询、音效策略、工作流 |
| API 契约测试 | Python 脚本/pytest | 心跳、snapshot、登录、自检、AI 状态 |
| 运行冒烟测试 | PowerShell + Python | 启动 central-api、dashboard、node-agent |
| 浏览器验证 | Playwright 或人工截图 | 登录门禁、报警处置、日志归档、调度审批 |

## 3. v2.2.0 文档阶段测试

| 编号 | 测试 | 验收 |
| --- | --- | --- |
| DOC-001 | 检查五份文档存在 | `contracts-v2.2.md`、`api-compatibility-plan.md`、`simulation-contract.md`、`test-matrix-v2.2.md`、`architecture-debt.md` |
| DOC-002 | 检查每个 schema 有 JSON 示例 | heartbeat、snapshot、rule conclusion、LLM explanation、command |
| DOC-003 | 检查退出条件 | 每个临时兼容层都有明确退出条件 |
| DOC-004 | 检查未修改运行代码 | `services` 与 `scripts` 不因 v2.2.0 改动 |

## 4. v2.2.1 Heartbeat v2 测试

### 后端测试

| 编号 | 输入 | 期望 |
| --- | --- | --- |
| HB-API-001 | v1 heartbeat，无 v2 字段 | 接收成功，节点状态更新 |
| HB-API-002 | v2 heartbeat，包含 `run_id` / `scenario_id` / `simulation_time` | 接收成功，字段可在状态中读取 |
| HB-API-003 | v2 heartbeat，包含 WIP/速率/利用率 | `dashboard-state` 或 snapshot 可透出 |
| HB-API-004 | heartbeat 缺少 `metrics` | 不崩溃 |
| HB-API-005 | heartbeat 缺少 `production` | 不崩溃但节点显示 unknown |
| HB-API-006 | 旧节点和新节点混合 | 三节点均可显示 |

### node-agent 测试

| 编号 | 场景 | 期望 |
| --- | --- | --- |
| HB-AGENT-001 | normal 模式 | 前 30 个心跳不应产生大量报警 |
| HB-AGENT-002 | demo_stress 模式 | 不同节点产生不同异常 |
| HB-AGENT-003 | milling | 可产生冷却、同步、温度相关压力 |
| HB-AGENT-004 | turning | 可产生质量漂移、主轴温度 |
| HB-AGENT-005 | grinding | 可产生磨损、振动 |

## 5. v2.2.2 Dashboard 显示测试

| 编号 | 输入状态 | 期望 UI |
| --- | --- | --- |
| UI-RUN-001 | API 返回 `simulation_time` | 页面显示仿真时间 |
| UI-RUN-002 | API 返回 `run_id` / `scenario_id` | 页面显示运行批次和场景 |
| UI-RUN-003 | `data_source=live` | 页面显示实时来源 |
| UI-RUN-004 | `data_source=fixture` | 页面明确显示测试/夹具来源 |
| UI-RUN-005 | API 缺 v2 字段 | 页面显示未上报，不伪造 live |
| UI-RUN-006 | 节点返回 `target_rate` / `actual_rate` / `utilization` | 节点卡片显示真实后端数据 |

## 6. v2.2.3 Snapshot Adapter 测试

| 编号 | 测试 | 期望 |
| --- | --- | --- |
| SNAP-001 | `GET /api/dashboard/snapshot` | 返回 200 |
| SNAP-002 | schema version | 返回 `schema_version=2.2` |
| SNAP-003 | data source | 返回 `data_source` |
| SNAP-004 | nodes | 三节点结构稳定 |
| SNAP-005 | work orders | 工单字段可供调度页使用 |
| SNAP-006 | alerts | 已关闭问题不出现 |
| SNAP-007 | legacy parity | 与 `dashboard-state` 关键事实一致 |

## 7. v2.2.4 到 v2.2.5 仿真测试

| 编号 | 场景 | 期望 |
| --- | --- | --- |
| SIM-001 | 单节点 deterministic run | 同一 seed 产生同一结果 |
| SIM-002 | 三工序正常运行 | WIP 和产量按节拍推进 |
| SIM-003 | 工单派发 | 子节点 active_order 来自主机端 |
| SIM-004 | 低速损耗 | 普通模式下磨损不应快速爆表 |
| SIM-005 | 多故障场景 | 至少覆盖冷却、质量、磨损、振动、温度、同步 |
| SIM-006 | 仿真时间 | simulation_time 单调递增 |

## 8. v2.2.6 Rule Engine 测试

| 编号 | 输入 | 期望 |
| --- | --- | --- |
| RULE-001 | `SPINDLE_TEMP_HIGH` | 高风险，人工决策 |
| RULE-002 | `VIBRATION_HIGH` | 高风险，人工决策 |
| RULE-003 | `TOOL_WEAR_WARNING` | 中风险，可自动维护提醒 |
| RULE-004 | `QUALITY_DRIFT` | 中风险，抽检/刀补建议 |
| RULE-005 | `COOLANT_FLOW_LOW` | 中风险，降载/现场检查 |
| RULE-006 | `SYNC-DELAY` | 同步问题，不改变物理设备状态 |
| RULE-007 | 已解决 issue_id | 不再进入报警队列 |

## 9. v2.2.7 AI Explanation 测试

| 编号 | 场景 | 期望 |
| --- | --- | --- |
| AI-001 | vault 解锁且 API 可用 | `source=api`，显示 provider/model |
| AI-002 | API 超时 | `source=fallback` 或 `status=api_error` 可见 |
| AI-003 | 高风险问题 | `requires_human=true` |
| AI-004 | 低风险问题 | 给出自动处置建议但不直接改状态 |
| AI-005 | 诊断结果 | 包含原因、证据、方案、问题追问 |
| AI-006 | AI 决策缓存 | `GET /api/ai/decisions` 可查 |

## 10. v2.2.8 Command Polling 测试

| 编号 | 场景 | 期望 |
| --- | --- | --- |
| CMD-001 | 低风险命令 | 无需人工，但必须归档 |
| CMD-002 | 高风险命令缺 CONFIRM | 拒绝执行 |
| CMD-003 | 高风险命令有 CONFIRM | 执行并归档 |
| CMD-004 | node-agent 拉取命令 | 只执行属于自己的命令 |
| CMD-005 | 命令执行失败 | 返回失败原因，不删除命令 |

## 11. v2.2.9 part_queue 测试

| 编号 | 场景 | 期望 |
| --- | --- | --- |
| PQ-001 | 工单进入第一工序 | part_queue 增加输入 |
| PQ-002 | 工序完成 | part_queue 转入下一工序 |
| PQ-003 | 节点故障 | 未开始件可被调度转移 |
| PQ-004 | 调度审批 | 审批后工单分配改变并归档 |

## 12. v2.2.10 PostgreSQL Shadow Write 测试

| 编号 | 场景 | 期望 |
| --- | --- | --- |
| PG-001 | 写入 heartbeat | 内存状态和 PostgreSQL shadow 均有记录 |
| PG-002 | 写入 audit_event | 可从 shadow 表查询 |
| PG-003 | 数据库不可用 | 主系统继续运行，明确降级 |
| PG-004 | replay 准备 | shadow 数据含 run_id/scenario_id |

## 13. 全链路验收脚本

建议 v2.2 每次完成小阶段后运行：

```powershell
.\scripts\start-system.ps1 -RequireAiApi -AdminPassword miniogas
.\scripts\check-runtime-status.ps1
python -m pytest services\central-api
Set-Location services\dashboard
npm test -- --run
npm run build
```

如不要求真实 AI：

```powershell
.\scripts\start-system.ps1 -AdminPassword miniogas
```

## 14. 人工浏览器验收

每次涉及前端时至少检查：

1. 登录前只看到自检动画，不透出后方系统内容。
2. 登录后能看到 3 个节点真实连接状态。
3. 报警出现时有弹窗、动画、分级音效。
4. 点击确认、诊断、处置后有明显状态变化。
5. 解决后的报警从队列消失并进入日志管理。
6. 调度审批后调度卡片清空或显示无待审批，并进入日志管理。

## 15. v2.2 总体验收

v2.2 完成时必须证明：

1. Dashboard 的运行事实来自后端。
2. 三个子节点能持续产生不同生产状态。
3. AI API 可真实调用，并且 fallback 状态不伪装成 API 成功。
4. 规则引擎只做判断，不越权改状态。
5. 自动处置和人工处置都有可见结果和归档。
6. 系统能在普通模式下长期正常运行，不会启动即满屏报警。
