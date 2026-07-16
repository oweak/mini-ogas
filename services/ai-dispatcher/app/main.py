from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import APIKeyHeader

logger = logging.getLogger("mini_ogas.ai_dispatcher")


def _project_root(module_path: Path) -> Path | None:
    for parent in module_path.resolve().parents:
        if (parent / ".git").exists() or (parent / "docker-compose.yml").exists():
            return parent
    return None


def _load_project_env(module_path: Path | None = None) -> None:
    explicit_path = os.getenv("OGAS_ENV_FILE", "").strip()
    if explicit_path:
        env_path = Path(explicit_path).expanduser()
    else:
        project_root = _project_root(module_path or Path(__file__))
        if project_root is None:
            return
        env_path = project_root / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_project_env()

from .contracts import (  # noqa: E402
    DiagnosisRequest,
    DiagnosisResult,
    InferenceRequest,
    InferenceResponse,
    TaskType,
    UnlockRequest,
)
from .runtime import runtime  # noqa: E402

PROCESS_ID = os.getpid()
PROCESS_STARTED_AT = datetime.now(UTC).isoformat()
app = FastAPI(title="Mini-OGAS AI Dispatcher", version="1.0.0")
_token_scheme = APIKeyHeader(name="X-OGAS-Token", auto_error=False)


def _session_token() -> str:
    token = os.environ.get("OGAS_SESSION_TOKEN")
    if not token:
        token = str(uuid.uuid4())
        os.environ["OGAS_SESSION_TOKEN"] = token
    return token


def _verify_token(token: str | None = Depends(_token_scheme)) -> None:
    expected_token = os.getenv("AI_DISPATCHER_TOKEN", os.getenv("API_ACCESS_TOKEN", ""))
    if not token or not expected_token or not secrets.compare_digest(token, expected_token):
        raise HTTPException(status_code=401, detail="missing or invalid X-OGAS-Token")


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "ai-dispatcher",
        "session_token": _session_token(),
        "process_id": PROCESS_ID,
        "process_started_at": PROCESS_STARTED_AT,
        "provider_chain": runtime.provider_chain(),
    }


@app.get("/providers")
def providers(_: None = Depends(_verify_token)) -> dict[str, object]:
    return {"chain": runtime.provider_chain(), "providers": runtime.provider_statuses()}


@app.get("/runtime/status")
def runtime_status(_: None = Depends(_verify_token)) -> dict[str, object]:
    return runtime.status()


@app.post("/runtime/unlock")
def unlock(payload: UnlockRequest, _: None = Depends(_verify_token)) -> dict[str, object]:
    try:
        result = runtime.unlock(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
    return {"ok": True, **result, "runtime": runtime.status()}


@app.post("/v1/inference", response_model=InferenceResponse)
async def inference(
    payload: InferenceRequest,
    _: None = Depends(_verify_token),
) -> InferenceResponse:
    return await runtime.infer(payload)


def _diagnosis_messages(payload: DiagnosisRequest) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You diagnose distributed factory incidents. Return one JSON object with "
                "root_cause, recommended_action, need_isolation, summary, and confidence. "
                "Do not execute commands or claim an action was completed."
            ),
        },
        {"role": "user", "content": payload.model_dump_json()},
    ]


@app.post("/diagnose", response_model=DiagnosisResult)
async def diagnose(
    payload: DiagnosisRequest,
    _: None = Depends(_verify_token),
) -> DiagnosisResult:
    response = await runtime.infer(
        InferenceRequest(
            task_type=TaskType.diagnosis,
            messages=_diagnosis_messages(payload),
            response_format="json_object",
            max_tokens=800,
            correlation_id=payload.correlation_id,
        )
    )
    parsed = response.structured_output or {}
    fallback = response.provenance.source == "rule_fallback"
    default_isolation = payload.severity.value in {"high", "critical"}
    attempted = list(dict.fromkeys(item.provider for item in response.provenance.attempts))
    errors = [
        f"{item.provider}:{item.error_class}:{item.error_code}"
        for item in response.provenance.attempts
        if item.status == "failed"
    ]
    return DiagnosisResult(
        severity=payload.severity,
        root_cause=str(parsed.get("root_cause") or "Deterministic incident review required."),
        recommended_action=str(
            parsed.get("recommended_action")
            or ("isolate_node_for_human_review" if default_isolation else "run_script_then_observe")
        ),
        need_isolation=_as_bool(parsed.get("need_isolation"), default=default_isolation),
        summary=str(
            parsed.get("summary")
            or f"{payload.node_code} used deterministic fallback after model providers failed."
        ),
        confidence=_as_float(parsed.get("confidence"), default=0.5),
        source="local-fallback" if fallback else response.provenance.provider,
        provider=response.provenance.provider,
        model=response.provenance.model,
        attempted_providers=attempted,
        provider_errors=errors,
        provenance=response.provenance,
    )


def _as_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    return value is True or str(value).strip().lower() in {"true", "1", "yes"}


def _as_float(value: object, *, default: float) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return default
