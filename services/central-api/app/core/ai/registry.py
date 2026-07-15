"""Provider registry — auto-detection, chained fallback, status reporting."""

from __future__ import annotations

import logging
from typing import Optional

from ..config import settings
from .base import AIProvider, DiagnosisResult
from .providers.deepseek import DeepSeekProvider
from .providers.groq import GroqProvider
from .providers.lm_studio import LMStudioProvider
from .providers.ollama import OllamaProvider
from .providers.rule_fallback import RuleFallbackProvider

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Holds an ordered list of providers. Diagnose/chat fall through the chain
    until one succeeds. The last provider is always RuleFallbackProvider."""

    def __init__(self) -> None:
        self._providers: list[AIProvider] = []
        self._verified_provider: str | None = None
        self._build_chain()

    # ------------------------------------------------------------------
    # Chain construction
    # ------------------------------------------------------------------

    def _build_chain(self) -> None:
        chain_names = settings.ai_provider_chain
        for name in chain_names:
            provider = self._create_provider(name)
            if provider is not None:
                self._providers.append(provider)
        # Rule fallback is always the absolute last resort
        self._providers.append(RuleFallbackProvider())

    def reload(self) -> None:
        """Rebuild providers after runtime config changes, such as vault unlock."""
        self._providers = []
        self._verified_provider = None
        self._build_chain()

    def _create_provider(self, name: str) -> Optional[AIProvider]:
        if name == "deepseek":
            return DeepSeekProvider(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                model=settings.deepseek_model,
                timeout=settings.ai_timeout_seconds,
                chat_max_tokens=settings.ai_chat_max_tokens,
            )
        if name == "ollama":
            return OllamaProvider(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
                timeout=settings.ai_timeout_seconds,
            )
        if name == "lm_studio":
            return LMStudioProvider(
                base_url=settings.lm_studio_base_url,
                timeout=settings.ai_timeout_seconds,
            )
        if name == "groq":
            return GroqProvider(
                api_key=settings.groq_api_key,
                model=settings.groq_model,
                timeout=settings.ai_timeout_seconds,
            )
        logger.warning("Unknown AI provider in chain: %s", name)
        return None

    # ------------------------------------------------------------------
    # Fallback diagnose / chat
    # ------------------------------------------------------------------

    def diagnose(self, prompt: str, timeout: float | None = None) -> DiagnosisResult:
        result, _, _ = self.diagnose_with_provenance(prompt, timeout=timeout)
        return result

    def diagnose_with_provenance(
        self,
        prompt: str,
        timeout: float | None = None,
    ) -> tuple[DiagnosisResult, str, list[str]]:
        """Return the diagnosis, actual serving provider, and bounded failures."""
        errors: list[str] = []
        for provider in self._providers:
            if not provider.is_available():
                errors.append(f"{provider.name}: not available")
                continue
            try:
                result = provider.diagnose(prompt, timeout=timeout)
                logger.debug("AI diagnose served by %s (confidence=%.2f)", provider.name, result.confidence)
                self._verified_provider = provider.name if provider.name != "rule_fallback" else None
                return result, provider.name, errors[-8:]
            except Exception as exc:
                errors.append(f"{provider.name}: {exc}")
                logger.warning("AI provider %s failed: %s", provider.name, exc)
        self._verified_provider = None
        logger.error("All providers exhausted. Errors: %s", "; ".join(errors))
        result = DiagnosisResult(
            root_cause="所有 AI 后端均不可用，请检查配置。",
            recommended_action="检查 /api/ai/status 了解各 Provider 状态。",
            confidence=0.0,
            raw_text="total failure",
        )
        return result, "rule_fallback", errors[-8:]

    def chat_with_provenance(
        self, messages: list[dict[str, str]], timeout: float | None = None
    ) -> tuple[str, str, list[str]]:
        """Return chat output with the provider that actually served it."""
        errors: list[str] = []
        for provider in self._providers:
            if provider.name == "rule_fallback" or not provider.is_available():
                continue
            try:
                answer = provider.chat(messages, timeout=timeout)
                if not isinstance(answer, str) or not answer.strip():
                    raise RuntimeError("provider returned an empty chat response")
                self._verified_provider = provider.name
                return answer, provider.name, errors
            except Exception as exc:
                errors.append(f"{provider.name}: {exc}")
                logger.warning("AI chat provider %s failed: %s", provider.name, exc)
        self._verified_provider = None
        fallback = next(provider for provider in self._providers if provider.name == "rule_fallback")
        return fallback.chat(messages, timeout=timeout), "rule_fallback", errors

    def chat(self, messages: list[dict[str, str]], timeout: float | None = None) -> str:
        """Try each provider in chain order; return the resulting answer."""
        answer, _, _ = self.chat_with_provenance(messages, timeout=timeout)
        return answer
    # ------------------------------------------------------------------
    # Status / introspection
    # ------------------------------------------------------------------

    def providers(self) -> list[AIProvider]:
        return list(self._providers)

    def first_available(self) -> Optional[AIProvider]:
        for p in self._providers:
            if p.is_available():
                return p
        return None

    def verified_provider(self) -> Optional[str]:
        return self._verified_provider

    def model_for(self, provider_name: str) -> str:
        provider = next((item for item in self._providers if item.name == provider_name), None)
        if provider is None:
            return ""
        return str(getattr(provider, "_model", ""))

    def status_list(self) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for p in self._providers:
            result.append({
                "name": p.name,
                "available": p.is_available(),
                "in_chain": p.name != "rule_fallback",
                "fallback": p.name == "rule_fallback",
            })
        return result

    def is_any_live_provider(self) -> bool:
        """True if at least one non-fallback provider is available."""
        for p in self._providers:
            if p.name != "rule_fallback" and p.is_available():
                return True
        return False


# ------------------------------------------------------------------
# Module-level singleton (same lifetime as `store`)
# ------------------------------------------------------------------

registry = ProviderRegistry()
