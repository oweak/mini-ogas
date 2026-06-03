from fastapi import APIRouter, Depends

from ..core.ai.base import DiagnosisResult
from ..core.ai.registry import registry
from ..core.config import settings
from ..core.security import PERM_AI_DIAGNOSE, ActorInfo, require_permission
from ..core.service_client import post_json
from ..models import AiChatRequest, AiChatResponse, AiDiagnoseRequest, AiStatus, Severity
from ..store import store

router = APIRouter(tags=["ai"])


@router.get("/ai-diagnoses")
@router.get("/ai/diagnoses")
def list_ai_diagnoses():
    return store.ai_diagnoses


@router.get("/ai/status", response_model=AiStatus)
def ai_status() -> AiStatus:
    active = registry.first_available()
    configured = registry.is_any_live_provider()
    tip = ""
    if not configured:
        tip = (
            "未配置任何 AI 后端。请设置 DEEPSEEK_API_KEY、OLLAMA_BASE_URL、"
            "LM_STUDIO_BASE_URL 或 GROQ_API_KEY 之一。详见 .env.example。"
        )
    return AiStatus(
        enabled=settings.ai_enabled,
        configured=configured,
        active_provider=active.name if active else "rule_fallback",
        model=getattr(active, "_model", "") if active and hasattr(active, "_model") else "",
        base_url=settings.deepseek_base_url,
        mode="multi-backend" if configured else "rule-fallback",
        providers=registry.status_list(),
        tip=tip,
    )


@router.get("/ai/shortcuts")
def list_ai_shortcuts():
    return store.ai_shortcuts


@router.post("/ai/shortcuts/{shortcut_id}/run", response_model=AiChatResponse)
def run_ai_shortcut(shortcut_id: str) -> AiChatResponse:
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
    used_ai = registry.is_any_live_provider()
    try:
        answer = registry.chat(messages)
        return AiChatResponse(accepted=True, used_deepseek=used_ai, status="multi-backend" if used_ai else "rule-fallback",
                              model=settings.deepseek_model, answer=answer)
    except Exception as exc:
        return AiChatResponse(
            accepted=True, used_deepseek=False, status="local-fallback", model="local-fallback",
            answer=f"{shortcut.label}：AI 后端暂不可用，已使用本地兜底。建议先查看 /api/ai/status。原因：{exc}",
        )


@router.post("/ai/diagnose")
def diagnose(payload: AiDiagnoseRequest, actor: ActorInfo = Depends(require_permission(PERM_AI_DIAGNOSE))):
    latest = store.latest_metrics().get(payload.node_code)
    alert = next((item for item in reversed(store.alerts) if item.id == payload.alert_id), None)
    if alert is None:
        alert = next((item for item in reversed(store.alerts)
                      if item.node_code == payload.node_code), None)
    if alert is None:
        alert = store.create_alert(
            payload.node_code, "manual_ai_diagnosis", Severity.medium,
            "人工触发 AI 诊断测试。", "ai",
        )

    service_result = diagnose_via_dispatcher(payload, alert.description, alert.severity.value, latest)
    if service_result is not None:
        sev_conf = {"high": 0.85, "critical": 0.90, "medium": 0.70, "low": 0.55}
        confidence = sev_conf.get(alert.severity.value, 0.70)
        diagnosis = store.add_ai_diagnosis(
            alert_id=alert.id, node_code=payload.node_code,
            root_cause=service_result["root_cause"],
            recommended_action=service_result["recommended_action"],
            confidence=confidence,
            need_isolation=bool(service_result["need_isolation"]),
            model_name=f"ai-dispatcher/{service_result['source']}",
            raw_response="",
        )
        return _flatten_diagnosis_response(diagnosis, service_result["source"] == "deepseek",
                                           f"ai-dispatcher-{service_result['source']}")

    prompt = build_prompt(payload, alert.description, latest)
    used_ai = False
    try:
        if payload.provider == "auto":
            result = registry.diagnose(prompt)
            used_ai = registry.is_any_live_provider()
        elif payload.provider == "rule_fallback":
            result = _rule_diagnosis(payload.node_code)
        else:
            # Specific provider requested — find it and use it directly
            provider = _find_provider(payload.provider)
            if provider is None or not provider.is_available():
                result = _rule_diagnosis(payload.node_code, f"Provider {payload.provider} 不可用")
            else:
                try:
                    result = provider.diagnose(prompt)
                    used_ai = True
                except Exception as exc:
                    result = _rule_diagnosis(payload.node_code, str(exc))
    except Exception as exc:
        result = _rule_diagnosis(payload.node_code, str(exc))

    # Determine model name
    if used_ai:
        active = registry.first_available()
        model_name = active.name if active else "multi-backend"
    else:
        model_name = "local-fallback"

    diagnosis = store.add_ai_diagnosis(
        alert_id=alert.id, node_code=payload.node_code,
        root_cause=result.root_cause, recommended_action=result.recommended_action,
        confidence=result.confidence, need_isolation=result.need_isolation,
        model_name=model_name,
        raw_response=result.raw_text,
    )
    if diagnosis.need_isolation and diagnosis.confidence >= 0.70:
        store.add_command(payload.node_code, "review_ai_isolation", "high",
                          "waiting_approval", "ai-policy")
    elif diagnosis.need_isolation:
        store.add_command(payload.node_code, "review_ai_recommendation", "low",
                          "waiting_approval", "ai-policy-low-confidence")
    else:
        store.add_command(payload.node_code, "review_ai_recommendation", "medium",
                          "waiting_approval", "ai-policy")
    return _flatten_diagnosis_response(diagnosis, used_ai,
                                       "multi-backend" if used_ai else "local-fallback")


def _find_provider(name: str):
    for p in registry.providers():
        if p.name == name:
            return p
    return None


def diagnose_via_dispatcher(payload: AiDiagnoseRequest, description: str, severity: str,
                            latest) -> dict | None:
    if not settings.microservices_enabled:
        store.update_integration_edge("ai-dispatcher", False)
        return None
    if payload.provider == "rule_fallback":
        return None
    recent_metrics = [latest.model_dump(mode="json")] if latest else []
    ok, data = post_json(
        f"{settings.ai_dispatcher_url}/diagnose",
        {
            "node_code": payload.node_code, "alert_type": "manual_ai_diagnosis",
            "severity": severity, "description": description,
            "recent_metrics": recent_metrics,
        },
        timeout=settings.ai_timeout_seconds,
    )
    store.update_integration_edge("ai-dispatcher", ok)
    if not ok or not isinstance(data, dict):
        return None
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
    used_ai = registry.is_any_live_provider()
    try:
        answer = registry.chat(messages)
        return AiChatResponse(
            accepted=True, used_deepseek=used_ai, status="multi-backend" if used_ai else "rule-fallback",
            model=settings.deepseek_model, answer=answer,
        )
    except Exception as exc:
        return AiChatResponse(
            accepted=True, used_deepseek=False, status="local-fallback", model="local-fallback",
            answer=(
                "AI 后端当前未能实时调用，已进入本地兜底模式。"
                f"原因：{exc}。你可以先检查 /api/ai/status、API Key 和网络连通性。"
                "支持的后端：DeepSeek、Ollama、LM Studio、Groq。"
            ),
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


def _flatten_diagnosis_response(diagnosis, used_deepseek: bool, status: str) -> dict:
    return {
        "accepted": True,
        "used_deepseek": used_deepseek,
        "status": status,
        "diagnosis": diagnosis,
        "root_cause": diagnosis.root_cause,
        "recommended_action": diagnosis.recommended_action,
        "confidence": diagnosis.confidence,
        "need_isolation": diagnosis.need_isolation,
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
