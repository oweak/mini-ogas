from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from .master_data import CODE_PATTERN, Code


class ExecutionError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str, **context: Any):
        super().__init__(message)
        self.status_code = status_code
        self.detail = {"code": code, "message": message, **context}


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProductionOrderIn(StrictInput):
    production_order_code: Code = Field(pattern=CODE_PATTERN)
    product_code: Code = Field(pattern=CODE_PATTERN)
    quantity: float = Field(gt=0)
    priority: int = Field(ge=1, le=10)
    due_at: datetime

    @model_validator(mode="after")
    def require_zoned_due_at(self) -> ProductionOrderIn:
        if self.due_at.tzinfo is None:
            raise ValueError("due_at must include a timezone")
        return self


class ExecutionActionIn(StrictInput):
    idempotency_key: str = Field(min_length=1, max_length=128)
    reason: str = Field(default="", max_length=1024)


class HoldActionIn(ExecutionActionIn):
    reason: str = Field(min_length=1, max_length=1024)


class SetupCompleteIn(StrictInput):
    idempotency_key: str = Field(min_length=1, max_length=128)
    evidence_reference: str = Field(min_length=1, max_length=240)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)


class CompleteTaskIn(StrictInput):
    idempotency_key: str = Field(min_length=1, max_length=128)
    evidence_reference: str = Field(default="", max_length=240)


class QuantityReportIn(StrictInput):
    report_id: Code = Field(pattern=CODE_PATTERN)
    good_quantity: float = Field(ge=0)
    scrap_quantity: float = Field(ge=0)
    rework_quantity: float = Field(ge=0)
    evidence_reference: str = Field(min_length=1, max_length=240)
    occurred_at: datetime

    @model_validator(mode="after")
    def validate_report(self) -> QuantityReportIn:
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        if self.good_quantity + self.scrap_quantity + self.rework_quantity <= 0:
            raise ValueError("a quantity report must account for a positive quantity")
        return self


class DowntimeStartIn(StrictInput):
    downtime_code: Code = Field(pattern=CODE_PATTERN)
    idempotency_key: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=1024)
    evidence_reference: str = Field(min_length=1, max_length=240)


class DowntimeEndIn(StrictInput):
    idempotency_key: str = Field(min_length=1, max_length=128)
    evidence_reference: str = Field(min_length=1, max_length=240)
