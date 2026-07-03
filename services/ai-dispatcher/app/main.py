import json
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

logger = logging.getLogger("mini_ogas.ai_dispatcher")


def _load_project_env() -> None:
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_project_env()
PROCESS_ID = os.getpid()
PROCESS_STARTED_AT = datetime.now(timezone.utc).isoformat()
DEFAULT_PROVIDER_CHAIN = "deepseek,ollama,lm_studio,groq"


def _session_token() -> str:
    token = os.environ.get("OGAS_SESSION_TOKEN")
    if not token:
        token = str(uuid.uuid4())
        os.environ["OGAS_SESSION_TOKEN"] = token
    return token


def _provider_chain() -> list[str]:
    raw = os.getenv("AI_PROVIDER_CHAIN", DEFAULT_PROVIDER_CHAIN)
    valid = {"deepseek", "ollama", "lm_studio", "groq"}
    return [name.strip().lower() for name in raw.split(",") if name.strip().lower() in valid]


def _is_live_key(value: str) -> bool:
    return bool(value) and value not in {"replace_me", "replace-with-your-key"}


def _provider_configured(name: str) -> bool:
    if name == "deepseek":
        return _is_live_key(os.getenv("DEEPSEEK_API_KEY", ""))
    if name == "groq":
        return _is_live_key(os.getenv("GROQ_API_KEY", ""))
    if name == "ollama":
        return _ollama_model_available()
    if name == "lm_studio":
        return _lm_studio_available()
    return False


def _ollama_model_available() -> bool:
    model = os.getenv("OLLAMA_MODEL", "llama3")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    try:
        response = httpx.get(base_url + "/api/tags", timeout=2)
        response.raise_for_status()
        models = response.json().get("models", [])
        return any(
            str(item.get("name") or item.get("model") or "") == model
            for item in models
            if isinstance(item, dict)
        )
    except (httpx.HTTPError, ValueError, TypeError):
        return False


def _lm_studio_available() -> bool:
    base_url = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234").rstrip("/")
    try:
        response = httpx.get(base_url + "/v1/models", timeout=2)
        response.raise_for_status()
        return True
    except httpx.HTTPError:
        return False


app = FastAPI(title="Mini-OGAS AI Dispatcher", version="0.2.0")
_token_scheme = APIKeyHeader(name="X-OGAS-Token", auto_error=False)
_expected_token = os.getenv("API_ACCESS_TOKEN", "")


def _verify_token(token: str | None = Depends(_token_scheme)) -> None:
    if not token or not secrets.compare_digest(token, _expected_token):
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
    recent_metrics: list[dict] = Field(default_factory=list)


class DiagnosisResult(BaseModel):
    severity: Severity
    root_cause: str
    recommended_action: str
    need_isolation: bool
    summary: str
    source: str = "local-fallback"
    attempted_providers: list[str] = Field(default_factory=list)
    provider_errors: list[str] = Field(default_factory=list)


def local_fallback(
    req: DiagnosisRequest,
    attempted: list[str] | None = None,
    errors: list[str] | None = None,
) -> DiagnosisResult:
    need_isolation = req.severity in {Severity.high, Severity.critical}
    action = "isolate_node" if need_isolation else "run_script_then_observe"
    return DiagnosisResult(
        severity=req.severity,
        root_cause=f"{req.alert_type} requires rule-based fallback analysis",
        recommended_action=action,
        need_isolation=need_isolation,
        summary=f"{req.node_code} is using the local rules fallback after the configured provider chain was exhausted.",
        source="local-fallback",
        attempted_providers=attempted or [],
        provider_errors=errors or [],
    )


def _prompt(req: DiagnosisRequest) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You diagnose distributed factory incidents. Return one JSON object with "
                "root_cause, recommended_action, need_isolation, and summary. "
                "Do not execute commands."
            ),
        },
        {"role": "user", "content": req.model_dump_json()},
    ]


def _provider_request(name: str, req: DiagnosisRequest) -> tuple[str, dict[str, str], dict]:
    messages = _prompt(req)
    if name == "deepseek":
        return (
            os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/") + "/chat/completions",
            {"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"},
            {"model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"), "messages": messages,
             "response_format": {"type": "json_object"}, "max_tokens": 500},
        )
    if name == "groq":
        return (
            "https://api.groq.com/openai/v1/chat/completions",
            {"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
            {"model": os.getenv("GROQ_MODEL", "mixtral-8x7b-32768"), "messages": messages,
             "response_format": {"type": "json_object"}, "max_tokens": 500},
        )
    if name == "ollama":
        return (
            os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/") + "/v1/chat/completions",
            {},
            {"model": os.getenv("OLLAMA_MODEL", "llama3"), "messages": messages,
             "response_format": {"type": "json_object"}, "max_tokens": 500},
        )
    if name == "lm_studio":
        return (
            os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234").rstrip("/") + "/v1/chat/completions",
            {},
            {"model": os.getenv("LM_STUDIO_MODEL", "local-model"), "messages": messages,
             "response_format": {"type": "json_object"}, "max_tokens": 500},
        )
    raise ValueError(f"unsupported provider: {name}")


def _parse_content(content: str) -> dict[str, object]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("provider response was not a JSON object")
    return parsed


def _as_bool(value: object) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "yes"}


async def _call_provider(client: httpx.AsyncClient, name: str, req: DiagnosisRequest) -> dict[str, object]:
    url, headers, payload = _provider_request(name, req)
    response = await client.post(url, headers=headers, json=payload)
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return _parse_content(str(content))


async def diagnose_with_chain(req: DiagnosisRequest) -> DiagnosisResult:
    attempted: list[str] = []
    errors: list[str] = []
    timeout = min(float(os.getenv("AI_TIMEOUT_SECONDS", "20")), 8.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for provider in _provider_chain():
            attempted.append(provider)
            if not _provider_configured(provider):
                errors.append(f"{provider}: not configured")
                continue
            try:
                parsed = await _call_provider(client, provider, req)
                return DiagnosisResult(
                    severity=req.severity,
                    root_cause=str(parsed.get("root_cause") or "provider did not state a root cause"),
                    recommended_action=str(parsed.get("recommended_action") or "review live metrics and audit events"),
                    need_isolation=_as_bool(parsed.get("need_isolation")),
                    summary=str(parsed.get("summary") or f"{provider} completed the diagnosis."),
                    source=provider,
                    attempted_providers=attempted,
                    provider_errors=errors,
                )
            except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
                logger.warning("provider %s failed for node=%s: %s", provider, req.node_code, exc)
                errors.append(f"{provider}: {str(exc)[:180]}")
    return local_fallback(req, attempted, errors)


@app.get("/health")
def health() -> dict[str, str | int | list[str]]:
    return {
        "status": "ok", "service": "ai-dispatcher", "session_token": _session_token(),
        "process_id": PROCESS_ID, "process_started_at": PROCESS_STARTED_AT,
        "provider_chain": _provider_chain(),
    }


@app.get("/providers")
def providers(_: None = Depends(_verify_token)) -> dict[str, object]:
    chain = _provider_chain()
    return {"chain": chain, "configured": {name: _provider_configured(name) for name in chain}}


@app.post("/diagnose", response_model=DiagnosisResult)
async def diagnose(req: DiagnosisRequest, _: None = Depends(_verify_token)) -> DiagnosisResult:
    return await diagnose_with_chain(req)
