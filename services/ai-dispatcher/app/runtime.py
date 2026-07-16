from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import Any

import httpx

from .contracts import (
    CostRecord,
    InferenceProvenance,
    InferenceRequest,
    InferenceResponse,
    ProviderAttempt,
    RedactionReport,
    TaskType,
    TokenUsage,
)
from .policy import (
    EgressPolicyError,
    bounded_float,
    bounded_int,
    estimate_cost,
    redact_payload,
    require_allowed_egress,
)
from .vault import load_vault_payload, valid_api_key, vault_present

logger = logging.getLogger("mini_ogas.ai_dispatcher.runtime")
DEFAULT_PROVIDER_CHAIN = "deepseek,ollama,lm_studio,groq"
SUPPORTED_PROVIDERS = frozenset({"deepseek", "ollama", "lm_studio", "groq"})
RETRIABLE_ERROR_CLASSES = frozenset({"timeout", "transport", "rate_limit", "upstream"})


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    model: str
    base_url: str
    api_key: str = ""

    @property
    def provider_model(self) -> str:
        return f"{self.name}/{self.model}"

    @property
    def endpoint(self) -> str:
        suffix = "/chat/completions" if self.name == "deepseek" else "/v1/chat/completions"
        if self.name == "groq":
            suffix = "/chat/completions"
        base = self.base_url.rstrip("/")
        return base if base.endswith("/chat/completions") else base + suffix

    @property
    def configured(self) -> bool:
        if self.name in {"deepseek", "groq"}:
            return valid_api_key(self.api_key)
        return bool(self.base_url and self.model)


class AiRuntime:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._vault_override: dict[str, str] | None = None
        self._verified_provider = ""
        self._verified_model = ""
        self._verified_at = ""

    @staticmethod
    def provider_chain() -> list[str]:
        raw = os.getenv("AI_PROVIDER_CHAIN", DEFAULT_PROVIDER_CHAIN)
        result: list[str] = []
        for value in raw.split(","):
            name = value.strip().lower()
            if name in SUPPORTED_PROVIDERS and name not in result:
                result.append(name)
        return result

    def provider_config(self, name: str) -> ProviderConfig:
        with self._lock:
            override = dict(self._vault_override or {})
        if override.get("provider") == name:
            defaults = self._environment_provider(name)
            return ProviderConfig(
                name=name,
                model=override.get("model") or defaults.model,
                base_url=override.get("base_url") or defaults.base_url,
                api_key=override.get("api_key") or defaults.api_key,
            )
        return self._environment_provider(name)

    @staticmethod
    def _environment_provider(name: str) -> ProviderConfig:
        if name == "deepseek":
            return ProviderConfig(
                name=name,
                model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip() or "deepseek-chat",
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip(),
                api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
            )
        if name == "groq":
            return ProviderConfig(
                name=name,
                model=os.getenv("GROQ_MODEL", "mixtral-8x7b-32768").strip()
                or "mixtral-8x7b-32768",
                base_url=os.getenv(
                    "GROQ_BASE_URL", "https://api.groq.com/openai/v1"
                ).strip(),
                api_key=os.getenv("GROQ_API_KEY", "").strip(),
            )
        if name == "ollama":
            return ProviderConfig(
                name=name,
                model=os.getenv("OLLAMA_MODEL", "llama3").strip() or "llama3",
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip(),
            )
        if name == "lm_studio":
            return ProviderConfig(
                name=name,
                model=os.getenv("LM_STUDIO_MODEL", "local-model").strip() or "local-model",
                base_url=os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234").strip(),
            )
        raise ValueError(f"unsupported provider: {name}")

    def provider_statuses(self) -> list[dict[str, Any]]:
        statuses: list[dict[str, Any]] = []
        for order, name in enumerate(self.provider_chain()):
            config = self.provider_config(name)
            origin = ""
            policy = "allowed"
            try:
                origin = require_allowed_egress(config.endpoint)
            except EgressPolicyError:
                policy = "denied"
            statuses.append(
                {
                    "name": name,
                    "model": config.model,
                    "provider_model": config.provider_model,
                    "configured": config.configured,
                    "in_chain": True,
                    "fallback": False,
                    "order": order,
                    "egress_origin": origin,
                    "egress_policy": policy,
                    "verified": name == self._verified_provider,
                }
            )
        statuses.append(
            {
                "name": "rule_fallback",
                "model": "deterministic-rules",
                "provider_model": "rule_fallback/deterministic-rules",
                "configured": True,
                "in_chain": False,
                "fallback": True,
                "order": len(statuses),
                "egress_origin": "",
                "egress_policy": "not_applicable",
                "verified": False,
            }
        )
        return statuses

    def status(self) -> dict[str, Any]:
        providers = self.provider_statuses()
        configured = next(
            (
                item
                for item in providers
                if item["in_chain"] and item["configured"] and item["egress_policy"] == "allowed"
            ),
            None,
        )
        with self._lock:
            verified_provider = self._verified_provider
            verified_model = self._verified_model
            verified_at = self._verified_at
            vault_unlocked = self._vault_override is not None
        env_secret_configured = any(
            self.provider_config(name).configured for name in ("deepseek", "groq")
        )
        source = "api" if verified_provider else "configured" if configured else "rule_fallback"
        provider = verified_provider or str((configured or {}).get("name") or "rule_fallback")
        model = verified_model or str((configured or {}).get("model") or "deterministic-rules")
        status = "live" if verified_provider else "configured" if configured else "rule_fallback"
        return {
            "status": status,
            "source": source,
            "provider": provider,
            "model": model,
            "provider_model": f"{provider}/{model}",
            "configured": configured is not None,
            "vault_present": vault_present() or env_secret_configured,
            "vault_unlocked": vault_unlocked or env_secret_configured,
            "last_verified_at": verified_at,
            "providers": providers,
        }

    def unlock(self, password: str) -> dict[str, str]:
        payload = load_vault_payload(password)
        candidate = ProviderConfig(
            name=payload["provider"],
            model=payload["model"] or self._environment_provider(payload["provider"]).model,
            base_url=payload["base_url"]
            or self._environment_provider(payload["provider"]).base_url,
            api_key=payload["api_key"],
        )
        origin = require_allowed_egress(candidate.endpoint)
        with self._lock:
            self._vault_override = payload
            self._verified_provider = ""
            self._verified_model = ""
            self._verified_at = ""
        return {
            "provider": candidate.name,
            "model": candidate.model,
            "provider_model": candidate.provider_model,
            "egress_origin": origin,
        }

    async def infer(self, request: InferenceRequest) -> InferenceResponse:
        started = monotonic()
        request_id = str(uuid.uuid4())
        overall_timeout = bounded_float("AI_TIMEOUT_SECONDS", 60.0, 1.0, 300.0)
        provider_timeout = bounded_float("AI_PROVIDER_TIMEOUT_SECONDS", 20.0, 1.0, 120.0)
        retry_count = bounded_int("AI_PROVIDER_RETRIES", 1, 0, 5)
        token_limit = bounded_int("AI_MAX_TOKENS", 4_096, 1, 32_768)
        max_tokens = min(request.max_tokens, token_limit)
        sanitized, redaction = redact_payload(
            [message.model_dump(mode="json") for message in request.messages]
        )
        attempts: list[ProviderAttempt] = []
        deadline = started + overall_timeout

        async with httpx.AsyncClient() as client:
            for provider_name in self.provider_chain():
                config = self.provider_config(provider_name)
                if not config.configured:
                    attempts.append(
                        self._attempt(
                            config,
                            attempt=0,
                            status="skipped",
                            error_class="configuration",
                            error_code="provider_not_configured",
                        )
                    )
                    continue
                try:
                    egress_origin = require_allowed_egress(config.endpoint)
                except EgressPolicyError as exc:
                    attempts.append(
                        self._attempt(
                            config,
                            attempt=0,
                            status="failed",
                            error_class="policy_denied",
                            error_code="egress_not_allowlisted",
                            detail=str(exc),
                        )
                    )
                    continue

                for retry_index in range(retry_count + 1):
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        attempts.append(
                            self._attempt(
                                config,
                                attempt=retry_index + 1,
                                status="failed",
                                error_class="timeout",
                                error_code="overall_deadline_exhausted",
                                egress_origin=egress_origin,
                            )
                        )
                        return self._fallback_response(
                            request,
                            request_id=request_id,
                            started=started,
                            timeout=overall_timeout,
                            max_tokens=max_tokens,
                            attempts=attempts,
                            redaction=redaction,
                        )
                    call_started = monotonic()
                    try:
                        content, structured, usage = await self._call_provider(
                            client,
                            config,
                            messages=sanitized,
                            response_format=request.response_format,
                            temperature=request.temperature,
                            max_tokens=max_tokens,
                            timeout=min(provider_timeout, remaining),
                        )
                        call_latency = self._elapsed_ms(call_started)
                        attempts.append(
                            self._attempt(
                                config,
                                attempt=retry_index + 1,
                                status="succeeded",
                                latency_ms=call_latency,
                                egress_origin=egress_origin,
                            )
                        )
                        with self._lock:
                            self._verified_provider = config.name
                            self._verified_model = config.model
                            self._verified_at = datetime.now(UTC).isoformat()
                        return InferenceResponse(
                            content=content,
                            structured_output=structured,
                            provenance=InferenceProvenance(
                                request_id=request_id,
                                correlation_id=request.correlation_id,
                                task_type=request.task_type,
                                provider=config.name,
                                model=config.model,
                                provider_model=config.provider_model,
                                source="api",
                                fallback_used=self._fallback_used(attempts, config.name),
                                latency_ms=self._elapsed_ms(started),
                                timeout_seconds=overall_timeout,
                                max_tokens=max_tokens,
                                attempts=attempts,
                                usage=usage,
                                cost=estimate_cost(config.provider_model, usage),
                                redaction=redaction,
                                egress_origin=egress_origin,
                                completed_at=datetime.now(UTC).isoformat(),
                            ),
                        )
                    except Exception as exc:
                        error_class, error_code, detail = self._classify_error(exc)
                        attempts.append(
                            self._attempt(
                                config,
                                attempt=retry_index + 1,
                                status="failed",
                                latency_ms=self._elapsed_ms(call_started),
                                error_class=error_class,
                                error_code=error_code,
                                detail=detail,
                                egress_origin=egress_origin,
                            )
                        )
                        logger.warning(
                            "provider call failed request_id=%s provider=%s model=%s "
                            "error_class=%s error_code=%s",
                            request_id,
                            config.name,
                            config.model,
                            error_class,
                            error_code,
                        )
                        if error_class not in RETRIABLE_ERROR_CLASSES:
                            break
                        if retry_index < retry_count:
                            delay = min(
                                0.25 * (2**retry_index),
                                max(0.0, deadline - monotonic()),
                            )
                            await asyncio.sleep(delay)

        return self._fallback_response(
            request,
            request_id=request_id,
            started=started,
            timeout=overall_timeout,
            max_tokens=max_tokens,
            attempts=attempts,
            redaction=redaction,
        )

    @staticmethod
    async def _call_provider(
        client: httpx.AsyncClient,
        config: ProviderConfig,
        *,
        messages: list[dict[str, str]],
        response_format: str,
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> tuple[str, dict[str, Any] | None, TokenUsage]:
        payload: dict[str, Any] = {
            "model": config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format == "json_object":
            payload["response_format"] = {"type": "json_object"}
        headers = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        response = await client.post(
            config.endpoint,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        content = str(data["choices"][0]["message"]["content"])
        if not content.strip():
            raise ValueError("provider returned an empty response")
        structured = _parse_json_object(content) if response_format == "json_object" else None
        usage_data = data.get("usage") if isinstance(data, dict) else None
        usage = TokenUsage(
            prompt_tokens=_optional_int((usage_data or {}).get("prompt_tokens")),
            completion_tokens=_optional_int((usage_data or {}).get("completion_tokens")),
            total_tokens=_optional_int((usage_data or {}).get("total_tokens")),
        )
        return content, structured, usage

    @staticmethod
    def _classify_error(exc: Exception) -> tuple[str, str, str]:
        if isinstance(exc, httpx.TimeoutException):
            return "timeout", exc.__class__.__name__, "provider request timed out"
        if isinstance(exc, httpx.TransportError):
            return "transport", exc.__class__.__name__, "provider transport failed"
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            if status in {401, 403}:
                category = "authentication"
            elif status == 429:
                category = "rate_limit"
            elif status >= 500:
                category = "upstream"
            else:
                category = "provider_error"
            return category, f"http_{status}", f"provider returned HTTP {status}"
        if isinstance(exc, (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError)):
            return "invalid_response", exc.__class__.__name__, "provider response was invalid"
        return "internal", exc.__class__.__name__, "unexpected dispatcher failure"

    @staticmethod
    def _attempt(
        config: ProviderConfig,
        *,
        attempt: int,
        status: str,
        latency_ms: int = 0,
        error_class: str = "",
        error_code: str = "",
        detail: str = "",
        egress_origin: str = "",
    ) -> ProviderAttempt:
        return ProviderAttempt(
            provider=config.name,
            model=config.model,
            provider_model=config.provider_model,
            attempt=attempt,
            status=status,
            latency_ms=latency_ms,
            error_class=error_class,
            error_code=error_code,
            detail=detail[:240],
            egress_origin=egress_origin,
        )

    @staticmethod
    def _fallback_used(attempts: list[ProviderAttempt], provider: str) -> bool:
        first_configured = next(
            (item.provider for item in attempts if item.error_code != "provider_not_configured"),
            provider,
        )
        previous_failed = any(item.status == "failed" for item in attempts[:-1])
        return first_configured != provider or previous_failed

    @staticmethod
    def _fallback_response(
        request: InferenceRequest,
        *,
        request_id: str,
        started: float,
        timeout: float,
        max_tokens: int,
        attempts: list[ProviderAttempt],
        redaction: RedactionReport,
    ) -> InferenceResponse:
        content, structured = _fallback_content(request.task_type)
        return InferenceResponse(
            content=content,
            structured_output=structured,
            provenance=InferenceProvenance(
                request_id=request_id,
                correlation_id=request.correlation_id,
                task_type=request.task_type,
                provider="rule_fallback",
                model="deterministic-rules",
                provider_model="rule_fallback/deterministic-rules",
                source="rule_fallback",
                fallback_used=True,
                latency_ms=AiRuntime._elapsed_ms(started),
                timeout_seconds=timeout,
                max_tokens=max_tokens,
                attempts=attempts,
                usage=TokenUsage(),
                cost=CostRecord(),
                redaction=redaction,
                egress_origin="",
                completed_at=datetime.now(UTC).isoformat(),
            ),
        )

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, round((monotonic() - started) * 1_000))


def _optional_int(value: Any) -> int | None:
    try:
        return max(0, int(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _parse_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("provider response was not a JSON object")
    return parsed


def _fallback_content(task_type: TaskType) -> tuple[str, dict[str, Any] | None]:
    if task_type == TaskType.connectivity_probe:
        return "AI provider unavailable", None
    if task_type == TaskType.diagnosis:
        payload = {
            "root_cause": "No model provider was available; deterministic review is required.",
            "recommended_action": "Review current metrics and apply the approved rule workflow.",
            "need_isolation": False,
            "summary": (
                "The AI Dispatcher exhausted its provider chain and used deterministic fallback."
            ),
            "confidence": 0.5,
        }
        return json.dumps(payload, ensure_ascii=False), payload
    return (
        "No model provider was available. The system retained deterministic rule behavior.",
        None,
    )


runtime = AiRuntime()
