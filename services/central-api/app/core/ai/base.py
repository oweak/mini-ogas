"""Abstract AI provider interface and shared types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiagnosisResult:
    root_cause: str
    recommended_action: str
    confidence: float
    need_isolation: bool = False
    raw_text: str = ""
