import json
import secrets
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..command_control_service import command_control_service
from ..core.ai.base import DiagnosisResult
from ..core.ai.dispatcher import DispatcherError, dispatcher_client
from ..core.config import settings
from ..core.principals import ensure_ai_dispatcher_principal
from ..core.security import (
    PERM_AI_DIAGNOSE,
    PERM_AI_SUGGEST,
    ActorInfo,
    actor_identity,
    require_permission,
)
from ..models import AiChatRequest, AiChatResponse, AiDiagnoseRequest, AiStatus, Severity
from ..repositories.ai_suggestions import ai_suggestion_repository
from ..rule_explanation import (
    RuleExplanationCache,
    explain_rule_conclusions,
    rule_explanation_cache_key,
)
from ..store import store

router = APIRouter(tags=["ai"])
rule_explanation_cache = RuleExplanationCache(settings.ai_rule_explanation_cache_seconds)


class AiSuggestionIn(BaseModel):
    node_code: str = Field(min_length=2, max_length=64)
    risk_level: Literal["low", "medium", "high", "critical"]
    recommendation: str = Field(min_length=8, max_length=2_000)
    evidence: dict[str, Any] = Field(default_factory=dict)


@router.get("/ai-diagnoses", operation_id="list_ai_diagnoses_legacy")
@router.get("/ai/diagnoses", operation_id="list_ai_diagnoses")
def list_ai_diagnoses():
    return store.ai_diagnoses


@router.get("/ai/status", response_model=AiStatus)
def ai_status() -> AiStatus:
    runtime = dispatcher_client.status()
    configured = bool(runtime.get("configured"))
    reachable = bool(runtime.get("reachable"))
    providers = []
    for item in runtime.get("providers", []):
        if not isinstance(item, dict):
            continue
        providers.append(
            {
                "name": str(item.get("name") or ""),
                "available": bool(item.get("configured")),
                "in_chain": bool(item.get("in_chain")),
                "fallback": bool(item.get("fallback")),
            }
        )
    tip = ""
    if not reachable:
        tip = "AI Dispatcher 不可达；系统只保留确定性规则回退。"
    elif not configured:
        tip = "AI Dispatcher 尚未解锁或未配置可用 Provider。"
    return AiStatus(
        enabled=settings.ai_enabled,
        configured=configured,
        active_provider=str(runtime.get("provider") or "rule_fallback"),
        model=str(runtime.get("model") or "deterministic-rules"),
        base_url=settings.ai_dispatcher_url,
        mode="dispatcher" if reachable else "rule-fallback",
        providers=providers,
        tip=tip,
    )


@router.get("/ai/shortcuts")
def list_ai_shortcuts():
    return store.ai_shortcuts


@router.post("/ai/suggestions", status_code=201)
def submit_ai_suggestion(
    payload: AiSuggestionIn,
    actor: ActorInfo = Depends(require_permission(PERM_AI_SUGGEST)),
):
    if actor.principal_type != "ai_agent":
        raise HTTPException(status_code=403, detail="only an AI Agent principal may submit suggestions")
    if payload.node_code not in store.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    return _persist_ai_suggestion(
        actor=actor,
        node_code=payload.node_code,
        risk_level=payload.risk_level,
        recommendation=payload.recommendation,
        evidence=payload.evidence,
    )


@router.get("/ai/rule-explanation")
def rule_explanation(
    mode: str = "normal",
    use_live: bool = True,
    refresh: bool = False,
    actor: ActorInfo = Depends(require_permission(PERM_AI_DIAGNOSE)),
):
    from .demo import _build_dashboard_snapshot

    snapshot = _build_dashboard_snapshot(mode)
    runtime = dispatcher_client.status()
    use_live_ai = bool(use_live and runtime.get("configured") and runtime.get("reachable"))
    provider = str(runtime.get("provider") or "rule_fallback")
    model = str(runtime.get("model") or "deterministic-rules")

    def chat_fn(messages: list[dict[str, str]]) -> str:
        result = dispatcher_client.infer(
            messages,
            task_type="rule_explanation",
            response_format="json_object",
            max_tokens=min(settings.ai_chat_max_tokens, 1_500),
        )
        if not result.live:
            raise DispatcherError("dispatcher_rule_fallback")
        return result.content

    cache_key = rule_explanation_cache_key(
        snapshot,
        provider=provider,
        model=model,
        use_live_ai=use_live_ai,
    )
    return rule_explanation_cache.get_or_compute(
        cache_key,
        lambda: explain_rule_conclusions(
            snapshot,
            use_live_ai=use_live_ai,
            chat_fn=chat_fn if use_live_ai else None,
            provider=provider,
            model=model,
        ),
        bypass=refresh,
    )


@router.post("/ai/shortcuts/{shortcut_id}/run", response_model=AiChatResponse)
def run_ai_shortcut(
    shortcut_id: str,
    actor: ActorInfo = Depends(require_permission(PERM_AI_DIAGNOSE)),
) -> AiChatResponse:
    shortcut = next((item for item in store.ai_shortcuts if item.id == shortcut_id), None)
    if shortcut is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="shortcut not found")

    snapshot = store.management_snapshot()
    context = (
        f"节点数={len(snapshot['nodes'])}, "
        f"排产任务数={len(snapshot['dispatch_tasks'])}, "
        f"告警数={len(snapshot['alerts'])}, "
        f"摘要={snapshot['summary']}"
    )
    messages = [
        {
            "role": "system",
            "content": "你是 Mini-OGAS 分布式机械厂的 AI 运维助手。回答必须短、具体、便于前端展示和复试讲解，不要直接执行高危动作。",
        },
        {"role": "user", "content": f"{shortcut.prompt}\n当前系统上下文：{context}"},
    ]
    try:
        result = dispatcher_client.infer(
            messages,
            task_type="chat",
            max_tokens=settings.ai_chat_max_tokens,
        )
        provider = result.provider
        return AiChatResponse(
            accepted=True,
            used_deepseek=provider == "deepseek",
            status="api" if result.live else "rule-fallback",
            model=result.model,
            answer=result.content,
            provider=provider,
            source=result.source,
            provenance=result.provenance,
        )
    except DispatcherError as exc:
        return AiChatResponse(
            accepted=True, used_deepseek=False, status="local-fallback", model="local-fallback",
            answer=f"{shortcut.label}：AI 后端暂不可用，已使用本地兜底。建议先查看 /api/ai/status。原因：{exc}",
            provider="rule_fallback", source="rule_fallback",
        )


@router.post("/ai/diagnose")
def diagnose(payload: AiDiagnoseRequest, actor: ActorInfo = Depends(require_permission(PERM_AI_DIAGNOSE))):
    if payload.provider not in {"auto", "rule_fallback"}:
        raise HTTPException(
            status_code=422,
            detail="Provider selection is owned by AI Dispatcher; use auto or rule_fallback.",
        )
    latest = store.latest_metrics().get(payload.node_code)
    alert = next(
        (
            item for item in reversed(store.alerts)
            if item.id == payload.alert_id and store.alert_in_current_run(item)
        ),
        None,
    )
    if alert is None:
        alert = next((item for item in reversed(store.alerts)
                      if item.node_code == payload.node_code and store.alert_in_current_run(item)), None)
    if alert is None:
        alert = store.create_alert(
            payload.node_code, "manual_ai_diagnosis", Severity.medium,
            "人工触发 AI 诊断测试。", "ai",
        )

    service_result = diagnose_via_dispatcher(
        payload,
        alert.description,
        alert.severity.value,
        latest,
    )
    if service_result is None:
        result = _rule_diagnosis(payload.node_code, "AI Dispatcher unavailable")
        provider_name = "rule_fallback"
        model_name = "rule_fallback/deterministic-rules"
        provenance: dict[str, Any] = {}
    else:
        result = DiagnosisResult(
            root_cause=str(service_result["root_cause"]),
            recommended_action=str(service_result["recommended_action"]),
            confidence=float(service_result.get("confidence") or 0.5),
            need_isolation=bool(service_result["need_isolation"]),
            raw_text="",
        )
        provenance = dict(service_result["provenance"])
        provider_name = str(provenance.get("provider") or "rule_fallback")
        model_name = str(
            provenance.get("provider_model") or "rule_fallback/deterministic-rules"
        )

    diagnosis = store.add_ai_diagnosis(
        alert_id=alert.id, node_code=payload.node_code,
        root_cause=result.root_cause, recommended_action=result.recommended_action,
        confidence=result.confidence, need_isolation=result.need_isolation,
        model_name=model_name,
        raw_response=json.dumps(provenance, ensure_ascii=False, sort_keys=True),
    )
    ensure_ai_dispatcher_principal()
    suggestion = _persist_ai_suggestion(
        actor=_dispatcher_actor(),
        node_code=payload.node_code,
        risk_level=(
            "high"
            if diagnosis.need_isolation and diagnosis.confidence >= 0.70
            else "medium"
        ),
        recommendation=diagnosis.recommended_action,
        evidence={
            "diagnosis_id": diagnosis.id,
            "alert_id": alert.id,
            "root_cause": diagnosis.root_cause,
            "confidence": diagnosis.confidence,
            "need_isolation": diagnosis.need_isolation,
            "provider": provider_name,
            "model": model_name,
            "provenance": provenance,
        },
        require_human_review=True,
    )
    return _flatten_diagnosis_response(
        diagnosis,
        provider=provider_name,
        status="api" if provider_name != "rule_fallback" else "local-fallback",
        provenance=provenance,
        suggestion=suggestion,
    )


def diagnose_via_dispatcher(payload: AiDiagnoseRequest, description: str, severity: str,
                            latest) -> dict | None:
    if payload.provider == "rule_fallback":
        return None
    recent_metrics = [latest.model_dump(mode="json")] if latest else []
    try:
        data = dispatcher_client.diagnose(
            node_code=payload.node_code,
            alert_type=payload.alert_type or "manual_ai_diagnosis",
            severity=severity,
            description=description,
            recent_metrics=recent_metrics,
            correlation_id=f"alert:{payload.alert_id}" if payload.alert_id is not None else "",
            timeout=settings.ai_timeout_seconds,
        )
    except DispatcherError:
        store.update_integration_edge("ai-dispatcher", False)
        return None
    store.update_integration_edge("ai-dispatcher", True)
    required = {"root_cause", "recommended_action", "need_isolation", "source"}
    if not required.issubset(data):
        return None
    return data


@router.post("/ai/chat", response_model=AiChatResponse)
def chat(payload: AiChatRequest, actor: ActorInfo = Depends(require_permission(PERM_AI_DIAGNOSE))) -> AiChatResponse:
    latest = store.latest_metrics().get(payload.node_code)
    context = ""
    if payload.use_context and latest:
        context = (
            f"当前车间节点 {payload.node_code} 指标："
            f"CPU {latest.cpu_usage:.1f}%，内存 {latest.memory_usage:.1f}%，磁盘 {latest.disk_usage:.1f}%，"
            f"入站 {latest.network_in}，出站 {latest.network_out}，"
            f"DB {latest.db_latency_ms}ms，API {latest.api_latency_ms}ms。"
        )
    system_message = {
        "role": "system",
        "content": (
            "你是 Mini-OGAS 分布式机械厂的运维助手。"
            "请用中文回答，重点解释车间节点管理、生产调度、指标监控、异常处理、AI 诊断策略。"
            "回答要具体、可用于复试展示。" + context
        ),
    }
    messages = [system_message, *[item.model_dump() for item in payload.messages[-12:]]]
    try:
        result = dispatcher_client.infer(
            messages,
            task_type="chat",
            max_tokens=settings.ai_chat_max_tokens,
        )
        provider = result.provider
        return AiChatResponse(
            accepted=True,
            used_deepseek=provider == "deepseek",
            status="api" if result.live else "rule-fallback",
            model=result.model,
            answer=result.content,
            provider=provider,
            source=result.source,
            provenance=result.provenance,
        )
    except DispatcherError as exc:
        return AiChatResponse(
            accepted=True, used_deepseek=False, status="local-fallback", model="local-fallback",
            answer=(
                "AI 后端当前未能实时调用，已进入本地兜底模式。"
                f"原因：{exc}。你可以先检查 /api/ai/status、API Key 和网络连通性。"
                "Provider 与 fallback 由 AI Dispatcher 统一管理。"
            ),
            provider="rule_fallback",
            source="rule_fallback",
        )


def build_prompt(payload: AiDiagnoseRequest, alert_description: str, latest) -> str:
    metric_text = "no latest metric"
    if latest:
        metric_text = (
            f"cpu={latest.cpu_usage:.1f}%, memory={latest.memory_usage:.1f}%, "
            f"disk={latest.disk_usage:.1f}%, network_in={latest.network_in}, "
            f"db_latency={latest.db_latency_ms}ms, api_latency={latest.api_latency_ms}ms, "
            f"finished_quantity={latest.finished_quantity}, defect_quantity={latest.defect_quantity}"
        )
    return (
        f"车间节点: {payload.node_code}\n"
        f"告警: {alert_description}\n"
        f"最新指标: {metric_text}\n"
        f"用户补充: {payload.question or '无'}\n"
        "请判断根因、建议动作、置信度，以及是否需要隔离该车间节点。"
    )


def _flatten_diagnosis_response(
    diagnosis,
    provider: str,
    status: str,
    provenance: dict[str, Any] | None = None,
    suggestion: dict[str, Any] | None = None,
) -> dict:
    used_live_provider = provider not in {"", "local-fallback", "rule_fallback"}
    return {
        "accepted": True,
        "used_deepseek": provider == "deepseek",
        "used_live_provider": used_live_provider,
        "provider": provider,
        "source": "api" if used_live_provider else "rule_fallback",
        "status": status,
        "diagnosis": diagnosis,
        "root_cause": diagnosis.root_cause,
        "recommended_action": diagnosis.recommended_action,
        "confidence": diagnosis.confidence,
        "need_isolation": diagnosis.need_isolation,
        "provenance": provenance or {},
        "suggestion": suggestion or {},
    }


def _dispatcher_actor() -> ActorInfo:
    return ActorInfo(
        principal_id="ai:dispatcher",
        principal_type="ai_agent",
        username="ai-dispatcher",
        display_name="AI Dispatcher",
        role="ai_agent",
        roles=["ai_agent"],
        permissions={PERM_AI_SUGGEST},
    )


def _persist_ai_suggestion(
    *,
    actor: ActorInfo,
    node_code: str,
    risk_level: str,
    recommendation: str,
    evidence: dict[str, Any],
    require_human_review: bool = False,
) -> dict[str, Any]:
    suggestion_id = "ais_" + secrets.token_urlsafe(16)
    needs_review = require_human_review or risk_level in {"high", "critical"}
    suggestion_status = "pending_human_review" if needs_review else "submitted"
    command = None
    if needs_review:
        command = command_control_service.issue_ai_review(
            suggestion_id=suggestion_id,
            node_code=node_code,
            risk_level=risk_level,
            recommendation=recommendation,
            evidence=evidence,
            actor=actor,
        )
    try:
        ai_suggestion_repository.create(
            suggestion_id=suggestion_id,
            tenant_id=settings.tenant_id,
            site_id=settings.site_id,
            principal_id=actor.principal_id,
            node_code=node_code,
            risk_level=risk_level,
            recommendation=recommendation,
            evidence=evidence,
            status=suggestion_status,
            command_id=command.id if command is not None else None,
        )
    except Exception:
        if command is not None:
            store.cancel_command(
                command.id,
                actor_identity(actor),
                "AI suggestion persistence failed",
            )
        raise
    store.add_audit_log(
        actor_identity(actor),
        "ai:suggestion:submit",
        "node",
        node_code,
        suggestion_status,
        json.dumps(
            {"suggestion_id": suggestion_id, "command_id": command.id if command else None},
            ensure_ascii=False,
            sort_keys=True,
        ),
    )
    return {
        "suggestion_id": suggestion_id,
        "principal_id": actor.principal_id,
        "node_code": node_code,
        "risk_level": risk_level,
        "status": suggestion_status,
        "command_id": command.id if command is not None else None,
        "approval_url": f"/ops/approve/{command.id}" if command is not None else None,
    }


def _rule_diagnosis(node_code: str, reason: str | None = None) -> DiagnosisResult:
    suffix = f"。AI 未实时调用原因：{reason}" if reason else ""
    return DiagnosisResult(
        root_cause=f"{node_code} 需要人工复核资源指标和加工队列状态{suffix}",
        recommended_action="先刷新车间节点状态和最新指标；若 CPU/延迟持续升高，限制新任务下发并检查 node-agent 日志。",
        confidence=0.58,
        need_isolation=False,
        raw_text="local fallback",
    )
