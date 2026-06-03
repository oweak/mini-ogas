# Mini-OGAS 系统自检测试日志 v1.0

**日期**: 2026-06-02 01:45:53 UTC
**环境**: Windows 11 / Python 3.x / Node.js (Vue 3 + Vite)
**测试范围**: 全系统端到端自检

---

## 1. 健康检查 ✅

| 测试项 | 端点 | 结果 | 详情 |
|--------|------|------|------|
| 服务状态 | `GET /health` | 200 | `{"status":"ok","service":"central-api"}` |
| 系统自检 | `GET /api/preflight` | all_pass=True | 4/4 步骤通过：微服务连通性 ✓ / 父子节点激活 (5) ✓ / AI Key 验证 (deepseek-chat) ✓ / 虚拟试运行 (置信度 85%) ✓ |

## 2. 认证模块 ✅

| 测试项 | 端点 | 结果 | 详情 |
|--------|------|------|------|
| 正确密码 | `POST /api/auth/verify` | 200 ok | role=system_admin |
| 错误密码 | `POST /api/auth/verify` | 401 | 密码错误 |
| 无 token 访问受保护接口 | `GET /api/ai/status` | 401 | 拒绝访问 |
| 无 token 访问受保护接口 | `GET /events` | 401 | 拒绝访问 |

## 3. 静态资源（免认证）✅

| 测试项 | 端点 | 结果 |
|--------|------|------|
| 首页 | `GET /` | 200 (index.html) |
| JavaScript | `GET /assets/index-*.js` | 200 |
| CSS | `GET /assets/index-*.css` | 200 |
| 公开 API | `GET /api/preflight` | 200 |

## 4. AI 模块 ✅

| 测试项 | 端点 | 结果 | 详情 |
|--------|------|------|------|
| AI 状态 | `GET /api/ai/status` | 200 | enabled=true, model=deepseek-chat, mode=deepseek-live |
| AI 快捷指令 | `GET /api/ai/shortcuts` | 200 | 4 条快捷指令 |
| AI 诊断列表 | `GET /api/diagnoses` | 200 | 0 条（当前无报警触发） |
| 干运行诊断 | preflight 内嵌 | pass | 根因+建议+置信度 85% |

## 5. 审计与日志模块 ✅

| 测试项 | 端点 | 结果 | 详情 |
|--------|------|------|------|
| 统一事件流 | `GET /events?limit=5` | 200 | total=12, returned=5 |
| 按来源过滤 | `GET /events?source_type=alert` | 200 | total=1 |
| 按严重度过滤 | `GET /events?severity=high,critical` | 200 | total=5 |
| 报警列表 | `GET /api/alerts` | 200 | 1 条 |
| 升级队列 | `GET /api/ops/escalations` | 200 | 0 条 |

## 6. 管理与调度 ✅

| 测试项 | 端点 | 结果 | 详情 |
|--------|------|------|------|
| 系统快照 | `GET /api/management/snapshot` | 200 | 21 keys, has_topology=True, has_auth=True, has_events=True |
| 排产重算 | `POST /api/dispatch/rebuild` | 200 | total=16, dispatched=16 |
| 节点列表 | `GET /api/nodes` | 200 | 5 节点 |

## 7. 前端构建 ✅

| 测试项 | 命令 | 结果 |
|--------|------|------|
| TypeScript 类型检查 | `vue-tsc --noEmit` | 0 错误 ✓ |
| Vite 生产构建 | `vite build` | 0 错误, 601ms ✓ |
| 产物大小 | — | HTML 0.48 kB, CSS 30.77 kB, JS 126.49 kB |

## 8. 后端单元测试 ✅

| 测试项 | 命令 | 结果 |
|--------|------|------|
| pytest 全量 | `python -m pytest tests/ -q` | **26 passed**, 1 warning, 0.59s |

---

## 汇总

| 模块 | 测试项数 | 通过 | 失败 |
|------|----------|------|------|
| 健康检查 | 2 | 2 | 0 |
| 认证模块 | 4 | 4 | 0 |
| 静态资源 | 4 | 4 | 0 |
| AI 模块 | 4 | 4 | 0 |
| 审计与日志 | 5 | 5 | 0 |
| 管理与调度 | 3 | 3 | 0 |
| 前端构建 | 2 | 2 | 0 |
| 后端单元测试 | 1 (26 cases) | 26 | 0 |
| **合计** | **25** | **50** | **0** |

**结论**: 系统全部模块通过自检，状态就绪。
