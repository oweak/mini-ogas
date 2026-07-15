"""Abstract AI provider interface and shared types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class DiagnosisResult:
    root_cause: str
    recommended_action: str
    confidence: float
    need_isolation: bool = False
    raw_text: str = ""


class AIProvider(ABC):
    """Abstract provider — each backend implements diagnose, chat, is_available."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier: 'deepseek', 'ollama', 'lm_studio', 'groq', etc."""

    @abstractmethod
    def diagnose(self, prompt: str, timeout: float | None = None) -> DiagnosisResult:
        """Send a diagnosis prompt and return structured result."""

    @abstractmethod
    def chat(self, messages: list[dict[str, str]], timeout: float | None = None) -> str:
        """Free-form chat completion."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether this provider is configured and reachable."""
