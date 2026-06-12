# Mini-OGAS VM 分布式 + SimPy 实时仿真 + AI 工厂大脑 设计文档

> 版本: 1.0 | 日期: 2026-06-12 | 状态: 待审核

---

## 1. 目标

将 Mini-OGAS 从单机静态模拟改造为**虚拟机分布式实时仿真系统**，AI 从被动诊断工具升级为**主动管理的工厂大脑**，Dashboard 面向非技术管理者提供直观的健康监控。

核心目标：
- 3 台 Ubuntu VM 分布式部署，1 台 Kali 攻击测试
- SimPy RealtimeEnvironment 驱动 3 工序产线实时仿真
- AI 三大角色持续监控、决策、执行，闭环验证
- Dashboard 面向工厂主管：健康分、可视化产线、通知弹窗、待办/已办

---

## 2. VM 拓扑与网络设计

### 2.1 虚拟机清单

| VM 名称 | vCPU | RAM | 磁盘 | OS | 用途 |
|---------|------|-----|------|-----|------|
| ogas-central | 4 | 3 GB | 25 GB | Ubuntu Server 24.04 | 全部后端服务 + DB |
| ogas-edge | 2 | 1 GB | 15 GB | Ubuntu Server 24.04 | 3 个 node-agent + SimPy |
| ogas-router | 1 | 256 MB | 5 GB | Alpine Linux 3.20 | iptables 路由 + 审计 |
| ogas-kali | 2 | 2 GB | 30 GB | Kali Linux 2024 | 攻击测试（非持续运行） |

### 2.2 网络分区

| 网络 | 类型 | 网段 | 接入 VM |
|------|------|------|---------|
| Host-Only | VirtualBox 管理 | 192.168.56.0/24 | 宿主机 + ogas-router |
| ogas-svc | Internal Network | 10.0.1.0/24 | ogas-central, ogas-edge, ogas-router |
| ogas-atk | Internal Network | 10.0.99.0/24 | ogas-kali, ogas-router |

路由器 iptables 规则：
- 默认允许 ogas-atk → ogas-svc 转发（所有攻击流量经过审计）
- tcpdump 镜像端口记录全部攻击包
- 可随时执行 `iptables -I FORWARD -j DROP` 切断攻击

### 2.3 资源预算

| 场景 | VM 内存 | 宿主机 | 总计 |
|------|---------|--------|------|
| 日常运行（3 VM） | 4.25 GB | ~5 GB | ~9 GB / 16 GB |
| 攻击测试（4 VM） | 6.25 GB | ~5 GB | ~11 GB / 16 GB |

---

## 3. 软件栈

### 3.1 ogas-central (3 GB, Ubuntu Server 24.04)

Docker Compose 管理全部服务：

| 容器 | 端口 | 说明 |
|------|------|------|
| postgres:16-alpine | 5432 | 持久化：节点、告警、时序指标、事件日志、AI 操作记录 |
| redis:7-alpine | 6379 | 缓存 + 消息队列 |
| nats:2-alpine | 4222 | 节点实时通信 |
| central-api | 8080 | FastAPI 主网关 |
| ai-dispatcher | 8081 | AI 决策循环（3 角色并行） |
| market-simulator | 8082 | 原料价格/供应/需求信号 |
| production-planner | 8083 | 工单调度 + 产线编排 |
| dashboard | 5173 | Vue 前端 |

### 3.2 ogas-edge (1 GB, Ubuntu Server 24.04)

裸 Python 进程（无容器），systemd 守护：

| 进程 | 说明 |
|------|------|
| turning-agent | SimPy 车削仿真 + 心跳上报 |
| milling-agent | SimPy 铣削仿真 + 心跳上报 |
| grinding-agent | SimPy 磨削仿真 + 心跳上报 |

每个 agent 内嵌 SimPy RealtimeEnvironment(factor=1.0)，独立进程。

### 3.3 ogas-router (256 MB, Alpine Linux 3.20)

- iptables 三区转发规则
- tcpdump 攻击流量审计
- 定时输出审计日志到 central-api（只读挂载）

### 3.4 ogas-kali (2 GB, Kali Linux 2024)

- 预装工具：nmap, Metasploit, Burp Suite Community, Wireshark, Hydra, sqlmap
- 仅攻击测试时启动

---

## 4. 产线模型：3 工序实时仿真

### 4.1 产线 DAG

```
原材料 (market-sim) → [Turning 车削] → 半成品A → [Milling 铣削] → 半成品B → [Grinding 磨削] → 成品
     产能: 80/h              产能: 60/h              产能: 50/h
     3 台车床                2 台铣床                2 台磨床
```

**瓶颈设计**：产能梯度 80→60→50，milling 天然成为瓶颈，WIP 自动堆积。

### 4.2 SimPy 仿真参数（每工位）

| 参数 | turning | milling | grinding |
|------|---------|---------|----------|
| 机床数 | 3 | 2 | 2 |
| 加工时间 (s) | 0.5–2.0 | 1.0–4.0 | 0.8–3.0 |
| 缺陷率 | 2% | 3% | 1.5% |
| 返工率 | 30% | 20% | 40% |
| 故障频率 | 1/200 件 | 1/150 件 | 1/250 件 |
| 换型时间 (s) | 30 | 45 | 20 |

### 4.3 仿真组件（SimPy 原语）

| 模型组件 | SimPy 原语 | 说明 |
|----------|-----------|------|
| 机床池 | `simpy.Resource(capacity=N)` | N 台机床排队争用 |
| 工件流 | `simpy.Process` | 泊松分布到达 |
| 原料库存 | `simpy.Container` | 实时库存水位 |
| 在制品队列 | `simpy.Store` | WIP 缓冲 |
| 成品输出 | `simpy.Store` | 完成品计数 |
| 刀具磨损 | 自定义累加器 | 每件 +0.002~0.005 |
| 故障注入 | `simpy.Interrupt` | 随机主轴过热/断刀 |

### 4.4 实时仿真循环

```
while True:
    env.run(until=env.now + 3)    # 3 秒步进，墙钟同步
    push_metrics_to_central()     # 上报产速/WIP/缺陷率/磨损/CPU/内存
    check_incoming_orders()       # 接收新工单/参数变更
```

### 4.5 瓶颈传播机制

production-planner 每 10 秒检测：
- 读取各工位产速 + WIP 水位
- 判断：上游产出 > 下游产能 → WIP 堆积 → 触发告警
- 判断：下游 WIP < 下限 → 饥饿告警
- 数据写入 `bottleneck_events` 表

---

## 5. AI 架构：工厂大脑

### 5.1 AI 三大角色

| 角色 | 触发条件 | 自治级别 | 决策循环周期 |
|------|---------|----------|-------------|
| AI 调度员 | WIP 变化率 > 阈值 | 建议-执行 | 每 10 秒 |
| AI 应急指挥官 | 缺陷率飙升 / 告警触发 | 半自动 | 事件驱动 |
| AI 预测维护 | 刀具磨损 > 0.6 或趋势上升 | 建议 | 每 30 秒 |

### 5.2 AI 决策循环（5 步）

```
1. 数据流入 → agent 每 3s 推送指标到 central-api
2. 异常检测 → ai-dispatcher 轮询快照，检测触发条件
3. LLM 推理 → 构造结构化 Prompt → DeepSeek/Ollama → 返回结构化决策
4. 执行动作 → 调用 central-api 写接口，实际改变系统状态
5. 闭环验证 → 下个循环检查效果，无效则升级诊断
```

### 5.3 AI 执行通道（写权限接口）

| AI 决策类型 | API 接口 | 效果 |
|------------|---------|------|
| 调整产速 | `PATCH /api/node/{code}/params` | agent 收到新 target_rate，30s 平滑过渡 |
| 暂停工位 | `POST /api/node/{code}/pause` | agent 完成当前件后待命 |
| 创建维护工单 | `POST /api/work-orders` | 维护工单排程，agent 定时停机 |
| 隔离节点 | `POST /api/node/{code}/isolate` | 节点从调度中移除 |
| 重排工单优先级 | `PATCH /api/dispatch/reorder` | 工单队列重新排序 |
| 创建质量召回 | `POST /api/quality/recall` | 标记缺陷批次，触发返工 |
| 调整工艺参数 | `PATCH /api/node/{code}/recipe` | 修改进给速度/切削深度等 |

### 5.4 AI 提供商链式回退

```
deepseek → ollama (本地, ogas-central:11434) → groq → local-fallback
```

- Ollama 部署在 ogas-central，模型推荐 `llama3:8b` 或 `qwen2.5:7b`
- local-fallback：硬编码规则引擎，兜底保证系统不崩溃

### 5.5 AI 操作日志

每条记录写入 `ai_actions` 表：

```sql
CREATE TABLE ai_actions (
    id UUID PRIMARY KEY,
    role VARCHAR(32),          -- scheduler / commander / maintenance
    triggered_by VARCHAR(256), -- 触发条件
    analysis TEXT,             -- LLM 推理原文
    actions JSONB,             -- 执行的动作列表
    executed_at TIMESTAMPTZ,
    verified_at TIMESTAMPTZ,   -- 闭环验证时间
    result VARCHAR(32)         -- effective / partial / failed
);
```

---

## 6. API 接口设计（含安全）

### 6.1 安全模型

所有接口统一认证：

```
Header: X-OGAS-Token: <token>
Header: X-OGAS-Session-Token: <session_token>
```

三级权限：
- **admin**：管理面板 + AI 手动干预
- **service**：服务间调用（agent ↔ central, AI → central）
- **readonly**：Dashboard 只读

Token 通过 `.env` 注入，VM 间通信使用 Internal Network 隔离。

### 6.2 新增接口清单

#### 节点控制（admin / service）

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| PATCH | `/api/node/{code}/params` | 修改产速/工艺参数 | service token |
| POST | `/api/node/{code}/pause` | 暂停工位 | admin |
| POST | `/api/node/{code}/resume` | 恢复工位 | admin |
| POST | `/api/node/{code}/isolate` | 隔离节点 | admin |
| POST | `/api/node/{code}/reinstate` | 恢复节点 | admin |
| PATCH | `/api/node/{code}/recipe` | 修改工艺配方 | service token |

#### 调度控制（admin / service）

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| PATCH | `/api/dispatch/reorder` | 重排工单优先级 | service token |
| POST | `/api/dispatch/override` | 手动创建调度指令 | admin |

#### 工单管理

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/work-orders` | 创建工单 | admin / service token |
| GET | `/api/work-orders` | 工单列表 | readonly+ |
| PATCH | `/api/work-orders/{id}` | 更新工单状态 | admin |
| GET | `/api/work-orders/queue` | 待办工单队列 | readonly+ |

#### 质量管理

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/quality/recall` | 创建产品召回 | admin |
| GET | `/api/quality/defect-trend` | 缺陷率趋势数据 | readonly+ |

#### AI 操作记录

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/ai/actions` | AI 操作日志列表 | readonly+ |
| GET | `/api/ai/actions/{id}` | AI 操作详情（含推理链） | readonly+ |
| GET | `/api/ai/status` | AI 三大角色运行状态 | readonly+ |
| POST | `/api/ai/toggle/{role}` | 开关 AI 角色 | admin |

#### 时序数据

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/metrics/history/{node}` | 节点指标历史（图表用） | readonly+ |
| GET | `/api/metrics/snapshot` | 全量实时快照 | readonly+ |
| GET | `/api/events/timeline` | 事件时间线 | readonly+ |

#### 系统健康

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/health-score` | 系统健康分 (0-100) + 扣分项 | readonly+ |
| GET | `/api/bottleneck/status` | 瓶颈检测结果 | readonly+ |

### 6.3 安全规范

- Token 长度 ≥ 32 字符随机字符串
- 生产环境禁止 `mini-ogas-dev-token` 默认值
- service token 不暴露给前端，仅后端服务间使用
- 所有写操作记录审计日志（操作者、时间、内容）
- Kali 攻击场景建议：先测试 Token 为空、Token 为默认值、Token 爆破三种场景
- Rate Limit：每个 IP 每分钟 180 请求（可配置）

---

## 7. 前端 Dashboard 设计

### 7.1 布局结构

```
┌──────────────────────────────────────────────────────────────┐
│  顶部栏：系统健康分 (85) │ ⚠ 1 个关注项 │ 🔵 3 工位在线        │
├────────────────────────────────────────────┬─────────────────┤
│                                            │  📋 待办         │
│   产线可视化                                │  · 铣削换刀 (16m) │
│   [车削] → [铣削⚠] → [磨削]                │  · 质量抽检      │
│                                            │                  │
│   🤖 AI 近期操作                            │  ✅ 已办         │
│   14:28 检测到堆积                          │  · 车削降速完成  │
│   14:29 已调整车削速度                      │  · 维护工单#46   │
│   14:29 已创建维护工单                       │                  │
│                                            │                  │
│   📈 今日产量：1,247 件 · 合格率 97.2%        │                  │
├────────────────────────────────────────────┴─────────────────┤
│  底部状态栏：AI 调度员 ●活跃 | AI 指挥官 ○待命 | AI 维护 ●活跃  │
└──────────────────────────────────────────────────────────────┘
```

### 7.2 通知弹窗

触发条件：
- **AI 执行动作**：自动弹出（3 秒后自动收起）——"AI 已降低车削速度：80→65"
- **告警触发**：黄色弹窗，需手动关闭——"铣削在制品堆积超过警戒线"
- **紧急事件**：红色弹窗，需确认——"车削刀具断裂，工位已停机"
- **维护提醒**：蓝色弹窗——"铣削预计 16 分钟后需换刀"

弹窗位置：右上角，不阻挡产线视图。多条通知堆叠显示（最多 3 条）。

### 7.3 右侧面板：待办/已办

**待办列表** 数据来源：
- 未解决的告警（需人工处理）
- AI 创建的维护工单（待执行）
- 系统建议（AI 标记为"建议"的操作）

**已办列表** 数据来源：
- AI 已自动执行的操作
- 已关闭的告警
- 已完成的维护工单

每项显示：时间、来源（AI/系统/手动）、描述、状态。

### 7.4 面向管理者的语言翻译

| 技术指标 | 管理者看到 |
|---------|-----------|
| tool_wear=0.68 | "刀具已使用 68%，预计 29 分钟后需更换" |
| milling.wip=47, change=+20/h | "铣削在制品堆积，每小时增加 20 件" |
| grinding.capacity_util=76% | "磨削产能仅发挥 76%，供料不足" |
| PATCH /node/turning {rate:65} | "AI 已自动降低车削速度以缓解堆积" |
| defect_rate 2%→8% | "铣削缺陷率异常上升，AI 正在诊断" |

### 7.5 颜色编码规范

| 颜色 | 含义 | 管理者行动 |
|------|------|-----------|
| 绿色 | 正常 | 无需关注 |
| 黄色 | 注意（AI 已介入） | 了解情况 |
| 橙色 | 警告（需关注） | 查看详情 |
| 红色 | 紧急（需人工决策） | 立即处理 |

---

## 8. 时间真实性与过渡动画

### 8.1 渐变机制

任何参数变更不瞬间跳变，而是 30 秒内平滑插值：

```
80 → 78 → 75 → 72 → 68 → 65  (每 5 秒更新)
```

实现：agent 收到变更指令 → SimPy 定时更新 target_rate → 前端通过时序数据渲染趋势。

### 8.2 事件时间线

Dashboard 右侧时间线显示完整因果链：

```
14:28:00 ⚠ 铣削 WIP 超过预警阈值（35→47）
14:28:05 🤖 AI调度员 已唤醒，分析产线数据
14:28:12 🤖 AI调度员 定位瓶颈：铣削产能不足（60/h），上游车削过快（80/h）
14:28:15 🔧 AI调度员 执行：降低车削至 65/h，创建维护工单 #47
14:28:20 📊 车削产速开始下降：80→78→75→...
14:28:48 📋 维护工单 #47 已排程（30 分钟后执行）
14:30:00 ✅ AI调度员 闭环确认：车削已稳定 65/h，铣削 WIP 增速放缓
14:35:00 ✅ 瓶颈解除：铣削 WIP 稳定在 42，磨削利用率回升至 89%
```

### 8.3 因果可追溯

每个 Dashboard 数值支持点击追溯：
- 产速变化 → 显示触发条件（AI 决策/手动调整/故障）
- 告警产生 → 显示前 30 分钟的指标趋势
- 工单创建 → 显示关联的 AI 诊断记录

---

## 9. Kali 攻击场景

### 9.1 攻击路径（难度递进）

| 级别 | 场景 | 工具 | 目标 |
|------|------|------|------|
| L1 侦察 | 端口扫描 + 服务发现 | nmap | 发现 10.0.1.10:8080/5173，识别 FastAPI docs |
| L2 Web | API 未授权访问 | Burp Suite, curl | 试探未授权接口，抓包分析 JWT |
| L3 凭证 | Token 爆破 | Hydra | 暴力破解 X-OGAS-Token |
| L4 横向 | 伪造 agent 心跳 | 自定义脚本 | 注入虚假指标，触发误告警 |
| L5 纵深 | 篡改 AI 决策参数 | MitM + 重放 | 中间人攻击篡改 AI 调度指令 |

### 9.2 蓝队检测点

- 路由 VM tcpdump 审计日志
- central-api 异常请求频率告警
- agent 心跳 Token 校验
- AI 异常决策回滚机制

---

## 10. 数据存储

### 10.1 PostgreSQL 核心表（新增/变更）

| 表名 | 用途 | 保留策略 |
|------|------|---------|
| metrics_snapshot | 时序指标（产速/WIP/缺陷率/磨损/CPU/内存） | 10 分钟窗口实时查询，归档 30 天 |
| bottleneck_events | 瓶颈检测事件 | 永久 |
| ai_actions | AI 操作记录（含推理链） | 永久 |
| event_timeline | Dashboard 事件时间线 | 30 天 |
| work_orders | 维护/生产工单 | 永久 |
| quality_records | 质检记录 | 永久 |
| notifications | 弹窗通知记录 | 7 天 |

### 10.2 Agent 本地存储

每个 agent 本地 SQLite：
- 生产日志（加工件数、缺陷数、刀具更换记录）
- 离线缓冲（网络中断时暂存心跳，恢复后补发）

---

## 11. 文件变更清单

### 新建文件

| 文件 | 说明 |
|------|------|
| `deploy/vm/init-central.sh` | ogas-central 初始化脚本 |
| `deploy/vm/init-edge.sh` | ogas-edge 初始化脚本 |
| `deploy/vm/init-router.sh` | ogas-router 初始化脚本 |
| `deploy/vm/Vagrantfile` | Vagrant 编排（可选，替代手动 VBox） |
| `services/node-agent/sim_workshop.py` | SimPy 实时仿真引擎（从 agent.py 拆分） |
| `services/ai-dispatcher/app/scheduler.py` | AI 调度员决策循环 |
| `services/ai-dispatcher/app/commander.py` | AI 应急指挥官 |
| `services/ai-dispatcher/app/maintainer.py` | AI 预测维护 |
| `services/ai-dispatcher/app/llm_client.py` | 多提供商链式回退客户端 |
| `services/central-api/app/routers/nodes.py` | 节点控制接口 |
| `services/central-api/app/routers/dispatch.py` | 调度控制接口 |
| `services/central-api/app/routers/ai.py` | AI 操作记录接口 |
| `services/central-api/app/routers/events.py` | 事件时间线接口 |
| `services/central-api/app/routers/health_score.py` | 健康分接口 |
| `services/central-api/app/routers/work_orders.py` | 工单接口 |
| `services/central-api/app/routers/quality.py` | 质量接口 |
| `database/migrations/002_metrics_schema.sql` | 时序数据表迁移 |
| `database/migrations/003_ai_actions.sql` | AI 操作记录表迁移 |

### 修改文件

| 文件 | 变更内容 |
|------|---------|
| `services/node-agent/agent.py` | 集成 SimPy RealtimeEnvironment，支持平滑过渡、参数变更接收 |
| `services/ai-dispatcher/app/main.py` | 启动 3 个 AI 角色并行决策循环 |
| `services/central-api/app/main.py` | 注册新路由，增加 health score 端点 |
| `services/central-api/app/routers/demo.py` | 替换静态数据生成，对接真实 SimPy 指标 |
| `services/dashboard/src/App.vue` | 新布局：健康分 + 产线可视化 + 事件时间线 + 待办/已办面板 |
| `services/dashboard/src/components/` | 新增：HealthScore, ProductionFlow, AiTimeline, TodoPanel, NotificationToast |
| `scripts/start-all.ps1` | 增加进程新鲜度验证 |
| `.env` | 增加 AI_PROVIDER_CHAIN, OLLAMA 配置, service token |

---

## 12. 实施阶段建议

| 阶段 | 内容 | 预估产出 |
|------|------|---------|
| Phase 1 | SimPy 实时仿真引擎 + agent 改造 | 3 个 agent 跑真实仿真，指标实时上报 |
| Phase 2 | AI 决策循环 + 执行通道 | AI 三大角色上线，可主动调整系统 |
| Phase 3 | Dashboard 改造 | 新布局 + 通知弹窗 + 待办/已办面板 |
| Phase 4 | VM 化部署 | 4 台 VM 初始化脚本 + 网络配置 |
| Phase 5 | Kali 攻击场景 | 攻击路径预配置 + 蓝队检测 |
| Phase 6 | 链式 AI 回退 + Ollama | 本地模型部署 + 多提供商回退 |

---

## 13. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 16 GB 内存不足 | Kali 仅在攻击测试时启动；edge VM 使用 Alpine Linux 可再省 200 MB |
| SimPy 实时仿真 CPU 过载 | 3 个 RealtimeEnvironment 而非 5 个；降低 agent 上报频率到 5s |
| LLM 响应延迟导致决策滞后 | Ollama 本地模型作为首选回退，响应 < 2s |
| AI 错误决策导致生产混乱 | 所有写操作带 `source=ai` 标记，支持一键回滚 |
| 前端过度复杂 | 默认视图极简（健康分+产线），详情按需展开 |
