from __future__ import annotations

import time
from typing import Protocol

from .core.ai.vault import runtime_status
from .core.config import settings
from .core.service_client import get_json
from .core.session import get_session_token
from .core.supervisor import supervisor_health
from .models import PreflightResult, PreflightStep
from .rules import evaluate_snapshot_rules


class PreflightStore(Protocol):
    def production_node_readiness(self) -> dict[str, object]: ...

    def persistence_status(self) -> dict[str, object]: ...


def _step(key: str, label: str) -> tuple[PreflightStep, float]:
    return PreflightStep(key=key, label=label, status="running"), time.monotonic()


def _finish(step: PreflightStep, started_at: float) -> PreflightStep:
    step.elapsed_ms = int((time.monotonic() - started_at) * 1000)
    return step


def _supervisor_step() -> PreflightStep:
    step, started_at = _step("supervisor", "运行所有权")
    supervisor = supervisor_health(get_session_token())
    status = str(supervisor.get("status") or "offline")
    healthy = int(supervisor.get("healthy_processes") or 0)
    expected = supervisor.get("expected_processes") or []
    expected_count = len(expected) if isinstance(expected, list) else 0
    missing = supervisor.get("missing_processes") or []
    unhealthy = supervisor.get("unhealthy_processes") or []
    if status == "ok":
        step.status = "pass"
        step.detail = f"Go supervisor 接管运行，session 一致，{healthy}/{expected_count} 个进程健康。"
    elif status == "session_mismatch":
        step.status = "fail"
        step.detail = "Go supervisor 在线，但 session 与 central-api 不一致，可能存在旧进程残留。"
    elif status == "degraded":
        step.status = "fail"
        step.detail = f"Go supervisor 在线但进程异常：missing={len(missing)}，unhealthy={len(unhealthy)}。"
    else:
        step.status = "fail"
        step.detail = "Go supervisor 未响应，无法确认系统运行所有权。"
    return _finish(step, started_at)


def _services_step() -> PreflightStep:
    step, started_at = _step("services", "微服务连通性")
    if not settings.microservices_enabled:
        step.status = "pass"
        step.detail = "独立模式已启用，外部微服务不作为启动前置条件。"
        return _finish(step, started_at)

    session_token = get_session_token()
    parts: list[str] = []
    all_ok = True
    services = (
        ("AI 调度器", settings.ai_dispatcher_url),
        ("市场模拟器", settings.market_simulator_url),
        ("排产规划器", settings.production_planner_url),
    )
    for name, base_url in services:
        try:
            ok, data = get_json(
                f"{base_url}/health",
                timeout=settings.service_probe_timeout_seconds,
            )
        except Exception:
            ok, data = False, None
        if ok and isinstance(data, dict):
            service_token = str(data.get("session_token") or "")
            if service_token and service_token != session_token:
                parts.append(f"{name} x(session_mismatch)")
                all_ok = False
                continue
            parts.append(f"{name} ok")
            continue
        parts.append(f"{name} x")
        all_ok = False
    step.status = "pass" if all_ok else "fail"
    step.detail = "; ".join(parts)
    return _finish(step, started_at)


def _nodes_step(store: PreflightStore) -> PreflightStep:
    step, started_at = _step("nodes", "父子节点激活")
    readiness = store.production_node_readiness()
    expected = readiness.get("expected") or []
    healthy = readiness.get("healthy") or []
    missing = readiness.get("missing") or []
    stale = readiness.get("stale") or []
    unavailable = readiness.get("unavailable") or []
    expected_count = len(expected) if isinstance(expected, list) else 0
    healthy_count = len(healthy) if isinstance(healthy, list) else 0
    if expected_count > 0 and healthy_count == expected_count:
        step.status = "pass"
        step.detail = f"生产节点 {healthy_count}/{expected_count} 在线且心跳新鲜：{', '.join(healthy)}"
    else:
        step.status = "fail"
        details: list[str] = [f"生产节点 {healthy_count}/{expected_count} 就绪"]
        if missing:
            details.append(f"未注册: {', '.join(missing)}")
        if stale:
            details.append(f"心跳过期: {', '.join(stale)}")
        if unavailable:
            details.append(f"不可用: {', '.join(unavailable)}")
        step.detail = "; ".join(details)
    return _finish(step, started_at)


def _ai_environment_step() -> PreflightStep:
    step, started_at = _step("ai-runtime", "AI 运行环境")
    if not settings.ai_enabled:
        step.status = "pass"
        step.detail = "AI 已禁用；系统仅使用规则引擎。"
    else:
        runtime = runtime_status()
        reachable = bool(runtime.get("reachable"))
        configured = bool(runtime.get("configured"))
        vault = bool(runtime.get("vault_present"))
        if reachable:
            step.status = "pass"
            mode = "已配置" if configured else "等待密钥库解锁" if vault else "规则回退"
            step.detail = f"AI Dispatcher 控制面可达，运行模式：{mode}。"
        else:
            step.status = "fail"
            step.detail = "AI Dispatcher 控制面不可达；Central API 不会直接调用模型。"
    return _finish(step, started_at)


def _rule_dry_run_step() -> PreflightStep:
    step, started_at = _step("dry_run", "规则引擎试运行")
    snapshot = {
        "schema_version": "2.2",
        "data_source": "self-check",
        "run": {"run_id": "preflight-local-rule"},
        "nodes": [
            {
                "node_code": "preflight-check",
                "machine_code": "PREFLIGHT-MILL",
                "workshop_type": "milling",
                "production": {
                    "wip_input": 20,
                    "wip_output": 4,
                    "target_rate": 1.0,
                    "actual_rate": 0.45,
                    "utilization": 0.94,
                },
            }
        ],
    }
    conclusions = evaluate_snapshot_rules(snapshot)
    if conclusions and all(item.get("read_only") is True for item in conclusions):
        step.status = "pass"
        step.detail = f"本地只读规则试运行通过，生成 {len(conclusions)} 条可追溯结论；未写入运行状态。"
    else:
        step.status = "fail"
        step.detail = "本地规则试运行未生成预期的只读结论。"
    return _finish(step, started_at)


def _persistence_step(store: PreflightStore) -> PreflightStep:
    step, started_at = _step("persistence", "中心持久化检查")
    persistence = store.persistence_status()
    status = str(persistence.get("status") or "degraded")
    if status == "degraded":
        step.status = "fail"
        step.detail = (
            f"{persistence.get('backend')} 持久化异常: "
            f"{persistence.get('last_error') or persistence.get('tables')}"
        )
    elif status == "disabled":
        step.status = "pass"
        step.detail = "PERSIST_ENABLED=false，当前为显式内存测试模式。"
    else:
        counts = persistence.get("counts") or {}
        parts = counts.get("part_queue_shadow", 0) if isinstance(counts, dict) else 0
        commands = counts.get("command_shadow", 0) if isinstance(counts, dict) else 0
        step.status = "pass"
        step.detail = (
            f"{persistence.get('backend')} 持久化正常，"
            f"part_queue={parts}，commands={commands}。"
        )
    return _finish(step, started_at)


def run_system_preflight(store: PreflightStore) -> PreflightResult:
    steps = [
        _supervisor_step(),
        _services_step(),
        _nodes_step(store),
        _ai_environment_step(),
        _rule_dry_run_step(),
        _persistence_step(store),
    ]
    all_pass = all(step.status == "pass" for step in steps)
    message = "所有自检通过，系统就绪" if all_pass else "部分自检未通过，请检查后重试"
    return PreflightResult(all_pass=all_pass, steps=steps, message=message)
