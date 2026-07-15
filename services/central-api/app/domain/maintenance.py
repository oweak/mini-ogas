from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .master_data import CODE_PATTERN, Code


class MaintenanceError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str, **context: Any):
        super().__init__(message)
        self.status_code = status_code
        self.detail = {"code": code, "message": message, **context}


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _require_zoned(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return value


class AssetIn(StrictInput):
    asset_code: Code = Field(pattern=CODE_PATTERN)
    equipment_code: Code = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=160)
    parent_asset_code: Code | None = Field(default=None, pattern=CODE_PATTERN)
    criticality: Literal["low", "medium", "high", "critical"]


class MaintenanceCodeIn(StrictInput):
    code: Code = Field(pattern=CODE_PATTERN)
    code_type: Literal["failure", "cause", "remedy"]
    description: str = Field(min_length=1, max_length=512)


class ChecklistItemIn(StrictInput):
    sequence: int = Field(ge=1, le=10000)
    instruction: str = Field(min_length=1, max_length=1024)
    required: bool = True


class ChecklistIn(StrictInput):
    checklist_code: Code = Field(pattern=CODE_PATTERN)
    revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=160)
    items: list[ChecklistItemIn] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_items(self) -> ChecklistIn:
        sequences = [item.sequence for item in self.items]
        if len(sequences) != len(set(sequences)):
            raise ValueError("checklist item sequences must be unique")
        return self


class MaintenanceActionIn(StrictInput):
    evidence_reference: str = Field(min_length=1, max_length=240)


class MaintenanceRequestIn(StrictInput):
    request_code: Code = Field(pattern=CODE_PATTERN)
    asset_code: Code = Field(pattern=CODE_PATTERN)
    source_type: Literal["alarm", "manual", "inspection", "preventive"]
    source_reference: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=2048)
    priority: Literal["low", "medium", "high", "critical"]
    observed_at: datetime

    @model_validator(mode="after")
    def validate_observed_at(self) -> MaintenanceRequestIn:
        _require_zoned(self.observed_at, "observed_at")
        return self


class MaintenanceOrderIn(StrictInput):
    order_code: Code = Field(pattern=CODE_PATTERN)
    request_code: Code = Field(pattern=CODE_PATTERN)
    asset_code: Code = Field(pattern=CODE_PATTERN)
    order_type: Literal["corrective", "preventive", "calibration", "tooling"]
    priority: Literal["low", "medium", "high", "critical"]
    assigned_personnel_code: Code = Field(pattern=CODE_PATTERN)
    checklist_code: Code = Field(pattern=CODE_PATTERN)
    checklist_revision: int = Field(ge=1)
    operation_task_id: int | None = Field(default=None, ge=1)
    operation_downtime_id: int | None = Field(default=None, ge=1)
    production_impact: Literal["none", "reduced_capacity", "equipment_unavailable"]
    planned_start_at: datetime
    planned_end_at: datetime

    @model_validator(mode="after")
    def validate_order(self) -> MaintenanceOrderIn:
        _require_zoned(self.planned_start_at, "planned_start_at")
        _require_zoned(self.planned_end_at, "planned_end_at")
        if self.planned_end_at <= self.planned_start_at:
            raise ValueError("planned_end_at must be after planned_start_at")
        if self.operation_downtime_id is not None and self.operation_task_id is None:
            raise ValueError("operation_downtime_id requires operation_task_id")
        return self


class ChecklistResultIn(StrictInput):
    item_sequence: int = Field(ge=1, le=10000)
    result: Literal["pass", "fail", "not_applicable"]
    evidence_reference: str = Field(min_length=1, max_length=240)


class WorkCompleteIn(StrictInput):
    failure_code: Code = Field(pattern=CODE_PATTERN)
    cause_code: Code = Field(pattern=CODE_PATTERN)
    remedy_code: Code = Field(pattern=CODE_PATTERN)
    work_evidence_reference: str = Field(min_length=1, max_length=240)


class MaintenanceVerifyIn(StrictInput):
    verification_reference: str = Field(min_length=1, max_length=240)
    verification_result: Literal["restored", "degraded", "not_restored"]


class ToolIn(StrictInput):
    tool_code: Code = Field(pattern=CODE_PATTERN)
    asset_code: Code = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=160)
    tool_type: str = Field(min_length=1, max_length=80)
    life_limit: float = Field(gt=0)
    life_used: float = Field(ge=0)
    life_uom: str = Field(min_length=1, max_length=40)
    calibration_required: bool = False
    calibration_due_at: datetime | None = None

    @model_validator(mode="after")
    def validate_tool(self) -> ToolIn:
        if self.calibration_required and self.calibration_due_at is None:
            raise ValueError("calibration_required tool requires calibration_due_at")
        if self.calibration_due_at is not None:
            _require_zoned(self.calibration_due_at, "calibration_due_at")
        return self


class ToolAssignmentIn(StrictInput):
    operation_task_id: int = Field(ge=1)
    evidence_reference: str = Field(min_length=1, max_length=240)


class ToolLifeEventIn(StrictInput):
    event_id: Code = Field(pattern=CODE_PATTERN)
    usage_delta: float = Field(gt=0)
    operation_task_id: int | None = Field(default=None, ge=1)
    occurred_at: datetime
    evidence_reference: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def validate_occurred_at(self) -> ToolLifeEventIn:
        _require_zoned(self.occurred_at, "occurred_at")
        return self


class CalibrationIn(StrictInput):
    calibration_code: Code = Field(pattern=CODE_PATTERN)
    result: Literal["pass", "fail"]
    valid_from: datetime
    valid_to: datetime
    performed_by_personnel_code: Code = Field(pattern=CODE_PATTERN)
    evidence_reference: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def validate_period(self) -> CalibrationIn:
        _require_zoned(self.valid_from, "valid_from")
        _require_zoned(self.valid_to, "valid_to")
        if self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be after valid_from")
        return self


class PreventivePlanIn(StrictInput):
    plan_code: Code = Field(pattern=CODE_PATTERN)
    asset_code: Code = Field(pattern=CODE_PATTERN)
    checklist_code: Code = Field(pattern=CODE_PATTERN)
    checklist_revision: int = Field(ge=1)
    interval_hours: int = Field(ge=1, le=87600)
    next_due_at: datetime
    production_impact: Literal["none", "reduced_capacity", "equipment_unavailable"]

    @model_validator(mode="after")
    def validate_due_at(self) -> PreventivePlanIn:
        _require_zoned(self.next_due_at, "next_due_at")
        return self


class PreventiveGenerateIn(StrictInput):
    request_code: Code = Field(pattern=CODE_PATTERN)
    order_code: Code = Field(pattern=CODE_PATTERN)
    assigned_personnel_code: Code = Field(pattern=CODE_PATTERN)
    planned_start_at: datetime
    planned_end_at: datetime

    @model_validator(mode="after")
    def validate_period(self) -> PreventiveGenerateIn:
        _require_zoned(self.planned_start_at, "planned_start_at")
        _require_zoned(self.planned_end_at, "planned_end_at")
        if self.planned_end_at <= self.planned_start_at:
            raise ValueError("planned_end_at must be after planned_start_at")
        return self


class SpareUseIn(StrictInput):
    usage_id: Code = Field(pattern=CODE_PATTERN)
    movement_id: Code = Field(pattern=CODE_PATTERN)
    evidence_reference: str = Field(min_length=1, max_length=240)
