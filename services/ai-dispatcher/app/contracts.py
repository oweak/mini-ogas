from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskType(StrEnum):
    connectivity_probe = "connectivity_probe"
    chat = "chat"
    diagnosis = "diagnosis"
    rule_explanation = "rule_explanation"
    command_planning = "command_planning"
    incident_briefing = "incident_briefing"


class Severity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=40_000)


class InferenceRequest(BaseModel):
    task_type: TaskType
    messages: list[ChatMessage] = Field(min_length=1, max_length=24)
    response_format: Literal["text", "json_object"] = "text"
    max_tokens: int = Field(default=1_000, ge=1, le=32_768)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    correlation_id: str = Field(default="", max_length=128)


class ProviderAttempt(BaseModel):
    provider: str
    model: str
    provider_model: str
    attempt: int = Field(ge=0)
    status: Literal["skipped", "failed", "succeeded"]
    latency_ms: int = Field(ge=0)
    error_class: str = ""
    error_code: str = ""
    detail: str = ""
    egress_origin: str = ""


class TokenUsage(BaseModel):
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class CostRecord(BaseModel):
    currency: Literal["USD"] = "USD"
    estimated: bool = False
    amount: float | None = Field(default=None, ge=0)
    pricing_source: str = "unconfigured"


class RedactionReport(BaseModel):
    applied: bool = False
    replacement_count: int = Field(default=0, ge=0)
    categories: list[str] = Field(default_factory=list)


class InferenceProvenance(BaseModel):
    request_id: str
    correlation_id: str = ""
    task_type: TaskType
    provider: str
    model: str
    provider_model: str
    source: Literal["api", "rule_fallback"]
    fallback_used: bool
    latency_ms: int = Field(ge=0)
    timeout_seconds: float = Field(gt=0)
    max_tokens: int = Field(gt=0)
    attempts: list[ProviderAttempt] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    cost: CostRecord = Field(default_factory=CostRecord)
    redaction: RedactionReport = Field(default_factory=RedactionReport)
    egress_origin: str = ""
    completed_at: str


class InferenceResponse(BaseModel):
    content: str
    structured_output: dict[str, Any] | None = None
    provenance: InferenceProvenance


class DiagnosisRequest(BaseModel):
    node_code: str = Field(min_length=2, max_length=64)
    alert_type: str = Field(min_length=2, max_length=128)
    severity: Severity
    description: str = Field(min_length=1, max_length=8_000)
    recent_metrics: list[dict[str, Any]] = Field(default_factory=list, max_length=64)
    correlation_id: str = Field(default="", max_length=128)


class DiagnosisResult(BaseModel):
    severity: Severity
    root_cause: str
    recommended_action: str
    need_isolation: bool
    summary: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str
    provider: str
    model: str
    attempted_providers: list[str] = Field(default_factory=list)
    provider_errors: list[str] = Field(default_factory=list)
    provenance: InferenceProvenance


class UnlockRequest(BaseModel):
    password: str = Field(min_length=1, max_length=1_024)
