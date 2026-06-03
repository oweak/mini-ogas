import logging
import os
import uuid
from enum import Enum

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

logger = logging.getLogger("mini_ogas.ai_dispatcher")


def _session_token() -> str:
    token = os.environ.get("OGAS_SESSION_TOKEN")
    if not token:
        token = str(uuid.uuid4())
        os.environ["OGAS_SESSION_TOKEN"] = token
    return token


app = FastAPI(title="Mini-OGAS AI Dispatcher", version="0.1.0")

_token_scheme = APIKeyHeader(name="X-OGAS-Token", auto_error=False)
_expected_token = os.getenv("API_ACCESS_TOKEN", "mini-ogas-dev-token")


def _verify_token(token: str | None = Depends(_token_scheme)) -> None:
    if not token or token != _expected_token:
        raise HTTPException(status_code=401, detail="missing or invalid X-OGAS-Token")


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class DiagnosisRequest(BaseModel):
    node_code: str
    alert_type: str
    severity: Severity
    description: str
    recent_metrics: list[dict] = []


class DiagnosisResult(BaseModel):
    severity: Severity
    root_cause: str
    recommended_action: str
    need_isolation: bool
    summary: str
    source: str = "deepseek"


def local_fallback(req: DiagnosisRequest) -> DiagnosisResult:
    need_isolation = req.severity in {Severity.high, Severity.critical}
    action = "isolate_node" if need_isolation else "run_script_then_observe"
    return DiagnosisResult(
        severity=req.severity,
        root_cause=f"{req.alert_type} requires rule-based fallback analysis",
        recommended_action=action,
        need_isolation=need_isolation,
        summary=f"{req.node_code} 出现 {req.alert_type}，当前使用本地兜底诊断。",
        source="local-fallback",
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ai-dispatcher", "session_token": _session_token()}


@app.post("/diagnose", response_model=DiagnosisResult)
async def diagnose(req: DiagnosisRequest, _: None = Depends(_verify_token)) -> DiagnosisResult:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key or api_key in {"replace_me", "replace-with-your-key"}:
        return local_fallback(req)

    prompt = (
        "You are diagnosing a small distributed factory operations system. "
        "Return JSON fields: severity, root_cause, recommended_action, "
        "need_isolation, summary. "
        f"Event: {req.model_dump_json()}"
    )
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    timeout = float(os.getenv("AI_TIMEOUT_SECONDS", "20"))
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "max_tokens": 500,
            },
        )
        if response.status_code >= 400:
            logger.warning("DeepSeek HTTP %d for node=%s alert=%s", response.status_code, req.node_code, req.alert_type)
            return local_fallback(req)
        try:
            content = response.json()["choices"][0]["message"]["content"]
            result = DiagnosisResult.model_validate_json(content)
            return result.model_copy(update={"source": "deepseek"})
        except (KeyError, IndexError, ValueError, TypeError):
            logger.exception("DeepSeek response parse failure for node=%s", req.node_code)
            return local_fallback(req)
