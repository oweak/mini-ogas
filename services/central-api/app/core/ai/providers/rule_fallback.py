"""Rule fallback provider — always available, returns deterministic diagnoses."""

from __future__ import annotations

from ..base import AIProvider, DiagnosisResult


class RuleFallbackProvider(AIProvider):
    name = "rule_fallback"

    def is_available(self) -> bool:
        return True

    def diagnose(self, prompt: str, timeout: float | None = None) -> DiagnosisResult:
        return DiagnosisResult(
            root_cause="当前无可用的 AI 后端，基于规则引擎进行本地诊断。建议检查 AI Provider 配置。",
            recommended_action="请确认至少一个 AI Provider 可用（检查 /api/ai/status），或配置 DEEPSEEK_API_KEY / Ollama / LM Studio。",
            confidence=0.3,
            need_isolation=False,
            raw_text="rule_fallback",
        )

    def chat(self, messages: list[dict[str, str]], timeout: float | None = None) -> str:
        return "所有 AI 后端当前不可用，已进入规则回退模式。请检查 /api/ai/status 了解详情。"
