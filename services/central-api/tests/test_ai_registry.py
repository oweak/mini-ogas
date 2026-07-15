from __future__ import annotations

from app.core.ai.providers.rule_fallback import RuleFallbackProvider
from app.core.ai.registry import ProviderRegistry


class EmptyProvider:
    name = "empty-provider"

    def is_available(self) -> bool:
        return True

    def chat(self, _messages, timeout=None) -> str:
        return ""


def test_chat_chain_rejects_empty_provider_output() -> None:
    registry = ProviderRegistry.__new__(ProviderRegistry)
    registry._providers = [EmptyProvider(), RuleFallbackProvider()]
    registry._verified_provider = None

    answer, provider, errors = registry.chat_with_provenance(
        [{"role": "user", "content": "diagnose"}]
    )

    assert answer
    assert provider == "rule_fallback"
    assert registry.verified_provider() is None
    assert errors == ["empty-provider: provider returned an empty chat response"]
