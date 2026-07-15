from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .master_data import CODE_PATTERN, Code


class QualityError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str, **context: Any):
        super().__init__(message)
        self.status_code = status_code
        self.detail = {"code": code, "message": message, **context}


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GaugeIn(StrictInput):
    gauge_code: Code = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=160)
    gauge_type: str = Field(min_length=1, max_length=80)
    calibration_status: Literal["valid", "expired", "out_of_calibration", "retired"]
    valid_from: datetime
    valid_to: datetime
    evidence_reference: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def validate_calibration_period(self) -> GaugeIn:
        if self.valid_from.tzinfo is None or self.valid_to.tzinfo is None:
            raise ValueError("gauge calibration timestamps must include a timezone")
        if self.valid_to <= self.valid_from:
            raise ValueError("gauge valid_to must be after valid_from")
        return self


class CharacteristicIn(StrictInput):
    characteristic_code: Code = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=160)
    value_type: Literal["numeric", "boolean", "text"]
    uom_code: Code | None = Field(default=None, pattern=CODE_PATTERN)
    target_value: float | None = None
    lower_spec_limit: float | None = None
    upper_spec_limit: float | None = None
    expected_boolean: bool | None = None
    expected_text: str | None = Field(default=None, max_length=240)
    method: str = Field(min_length=1, max_length=160)
    sample_size: int = Field(ge=1, le=1000)
    gauge_type: str = Field(min_length=1, max_length=80)
    required_skill_code: Code = Field(pattern=CODE_PATTERN)
    required_skill_level: int = Field(ge=1, le=10)

    @model_validator(mode="after")
    def validate_specification(self) -> CharacteristicIn:
        if self.value_type == "numeric":
            if not self.uom_code:
                raise ValueError("numeric characteristic requires uom_code")
            if self.lower_spec_limit is None and self.upper_spec_limit is None:
                raise ValueError("numeric characteristic requires a specification limit")
            if (
                self.lower_spec_limit is not None
                and self.upper_spec_limit is not None
                and self.lower_spec_limit > self.upper_spec_limit
            ):
                raise ValueError("lower_spec_limit cannot exceed upper_spec_limit")
        elif self.value_type == "boolean" and self.expected_boolean is None:
            raise ValueError("boolean characteristic requires expected_boolean")
        elif self.value_type == "text" and not self.expected_text:
            raise ValueError("text characteristic requires expected_text")
        return self


class InspectionPlanIn(StrictInput):
    plan_code: Code = Field(pattern=CODE_PATTERN)
    revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=160)
    material_code: Code = Field(pattern=CODE_PATTERN)
    stage: Literal["receiving", "in_process", "final"]
    operation_code: Code | None = Field(default=None, pattern=CODE_PATTERN)
    characteristics: list[CharacteristicIn] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_characteristics(self) -> InspectionPlanIn:
        codes = [item.characteristic_code for item in self.characteristics]
        if len(codes) != len(set(codes)):
            raise ValueError("inspection-plan characteristic codes must be unique")
        if self.stage == "in_process" and not self.operation_code:
            raise ValueError("in_process plan requires operation_code")
        return self


class QualityActionIn(StrictInput):
    evidence_reference: str = Field(min_length=1, max_length=240)


class InspectionLotIn(StrictInput):
    inspection_lot_code: Code = Field(pattern=CODE_PATTERN)
    plan_code: Code = Field(pattern=CODE_PATTERN)
    plan_revision: int = Field(ge=1)
    lot_code: Code = Field(pattern=CODE_PATTERN)
    location_code: Code = Field(pattern=CODE_PATTERN)
    operation_task_id: int | None = Field(default=None, ge=1)
    quantity: float = Field(gt=0)
    evidence_reference: str = Field(min_length=1, max_length=240)


class MeasurementIn(StrictInput):
    measurement_id: Code = Field(pattern=CODE_PATTERN)
    characteristic_code: Code = Field(pattern=CODE_PATTERN)
    sample_index: int = Field(ge=1)
    numeric_value: float | None = None
    boolean_value: bool | None = None
    text_value: str | None = Field(default=None, max_length=1024)
    uom_code: Code | None = Field(default=None, pattern=CODE_PATTERN)
    method: str = Field(min_length=1, max_length=160)
    gauge_code: Code = Field(pattern=CODE_PATTERN)
    personnel_code: Code = Field(pattern=CODE_PATTERN)
    occurred_at: datetime
    evidence_reference: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def validate_value(self) -> MeasurementIn:
        if self.occurred_at.tzinfo is None:
            raise ValueError("measurement occurred_at must include a timezone")
        present = sum(
            value is not None for value in (self.numeric_value, self.boolean_value, self.text_value)
        )
        if present != 1:
            raise ValueError("measurement requires exactly one typed value")
        return self


class DispositionIn(StrictInput):
    disposition_code: Code = Field(pattern=CODE_PATTERN)
    disposition_type: Literal["use_as_is", "rework", "scrap", "return_to_supplier"]
    reason: str = Field(min_length=1, max_length=1024)
    evidence_reference: str = Field(min_length=1, max_length=240)


class AuthorizationIn(StrictInput):
    authorization_reference: str = Field(min_length=1, max_length=240)


class CapaIn(StrictInput):
    capa_code: Code = Field(pattern=CODE_PATTERN)
    problem_statement: str = Field(min_length=1, max_length=2048)
    root_cause: str = Field(min_length=1, max_length=2048)
    action_plan: str = Field(min_length=1, max_length=4096)
    due_at: datetime
    evidence_reference: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def validate_due_at(self) -> CapaIn:
        if self.due_at.tzinfo is None:
            raise ValueError("CAPA due_at must include a timezone")
        return self


class CapaCompleteIn(StrictInput):
    verification_reference: str = Field(min_length=1, max_length=240)
    effectiveness_result: str = Field(min_length=1, max_length=2048)
