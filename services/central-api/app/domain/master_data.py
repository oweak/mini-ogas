from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Code = str
CODE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$"
TIME_PATTERN = r"^(?:[01]\d|2[0-3]):[0-5]\d$"


class MasterDataError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str, **context: Any):
        super().__init__(message)
        self.status_code = status_code
        self.detail = {"code": code, "message": message, **context}


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OrganizationUnitIn(StrictInput):
    unit_code: Code = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=160)
    unit_type: Literal["enterprise", "site", "area", "line", "cell"]
    parent_code: Code | None = Field(default=None, pattern=CODE_PATTERN)


class UomIn(StrictInput):
    uom_code: Code = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=80)
    dimension: str = Field(min_length=1, max_length=40)
    scale: float = Field(gt=0)


class MaterialIn(StrictInput):
    material_code: Code = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=160)
    material_type: Literal["raw", "intermediate", "finished", "consumable"]
    base_uom_code: Code = Field(pattern=CODE_PATTERN)


class ProductIn(StrictInput):
    product_code: Code = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=160)
    material_code: Code = Field(pattern=CODE_PATTERN)


class EquipmentIn(StrictInput):
    equipment_code: Code = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=160)
    equipment_type: str = Field(min_length=1, max_length=80)
    organization_unit_code: Code = Field(pattern=CODE_PATTERN)


class EquipmentCapabilityIn(StrictInput):
    capability_code: Code = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=160)


class SkillIn(StrictInput):
    skill_code: Code = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=160)
    level_min: int = Field(ge=1, le=10)


class PersonnelIn(StrictInput):
    personnel_code: Code = Field(pattern=CODE_PATTERN)
    display_name: str = Field(min_length=1, max_length=160)
    linked_username: str | None = Field(default=None, min_length=1, max_length=100)


class QualificationIn(StrictInput):
    personnel_code: Code = Field(pattern=CODE_PATTERN)
    skill_code: Code = Field(pattern=CODE_PATTERN)
    level: int = Field(ge=1, le=10)
    valid_from: datetime
    valid_to: datetime
    evidence_reference: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def validate_period(self) -> QualificationIn:
        if self.valid_from.tzinfo is None or self.valid_to.tzinfo is None:
            raise ValueError("qualification validity timestamps must include a timezone")
        if self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be later than valid_from")
        return self


class CalendarIn(StrictInput):
    calendar_code: Code = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=160)
    timezone: str = Field(min_length=1, max_length=80)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("unknown IANA timezone") from exc
        return value


class ShiftIn(StrictInput):
    shift_code: Code = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=160)
    start_time: str = Field(pattern=TIME_PATTERN)
    end_time: str = Field(pattern=TIME_PATTERN)

    @model_validator(mode="after")
    def validate_window(self) -> ShiftIn:
        if self.start_time == self.end_time:
            raise ValueError("shift start_time and end_time must differ")
        return self


class DocumentIn(StrictInput):
    document_code: Code = Field(pattern=CODE_PATTERN)
    title: str = Field(min_length=1, max_length=240)
    document_type: str = Field(min_length=1, max_length=80)


class DocumentRevisionIn(StrictInput):
    revision: str = Field(min_length=1, max_length=32)
    content: str | None = Field(default=None, min_length=1, max_length=100_000)
    object_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def require_one_content_source(self) -> DocumentRevisionIn:
        if (self.content is None) == (self.object_id is None):
            raise ValueError("exactly one of content or object_id is required")
        return self


class BomIn(StrictInput):
    bom_code: Code = Field(pattern=CODE_PATTERN)
    product_code: Code = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=160)


class BomItemIn(StrictInput):
    material_code: Code = Field(pattern=CODE_PATTERN)
    quantity: float = Field(gt=0)
    uom_code: Code = Field(pattern=CODE_PATTERN)


class BomRevisionIn(StrictInput):
    revision: int = Field(ge=1)
    items: list[BomItemIn] = Field(min_length=1, max_length=1000)

    @field_validator("items")
    @classmethod
    def unique_materials(cls, items: list[BomItemIn]) -> list[BomItemIn]:
        keys = [(item.material_code, item.uom_code) for item in items]
        if len(keys) != len(set(keys)):
            raise ValueError("BOM items must be unique by material and UOM")
        return items


class RoutingIn(StrictInput):
    routing_code: Code = Field(pattern=CODE_PATTERN)
    product_code: Code = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=160)


class RoutingOperationIn(StrictInput):
    sequence: int = Field(ge=1)
    operation_code: Code = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=160)
    capability_code: Code = Field(pattern=CODE_PATTERN)
    required_skill_code: Code = Field(pattern=CODE_PATTERN)
    required_skill_level: int = Field(ge=1, le=10)
    document_code: Code = Field(pattern=CODE_PATTERN)
    standard_time_seconds: float = Field(gt=0)


class RoutingRevisionIn(StrictInput):
    revision: int = Field(ge=1)
    operations: list[RoutingOperationIn] = Field(min_length=1, max_length=500)

    @field_validator("operations")
    @classmethod
    def unique_sequences(cls, operations: list[RoutingOperationIn]) -> list[RoutingOperationIn]:
        sequences = [operation.sequence for operation in operations]
        codes = [operation.operation_code for operation in operations]
        if len(sequences) != len(set(sequences)):
            raise ValueError("routing operation sequences must be unique")
        if len(codes) != len(set(codes)):
            raise ValueError("routing operation codes must be unique")
        return sorted(operations, key=lambda operation: operation.sequence)


class OperationAssignmentIn(StrictInput):
    sequence: int = Field(ge=1)
    equipment_code: Code = Field(pattern=CODE_PATTERN)
    personnel_code: Code = Field(pattern=CODE_PATTERN)


class WorkOrderIn(StrictInput):
    work_order_code: Code = Field(pattern=CODE_PATTERN)
    product_code: Code = Field(pattern=CODE_PATTERN)
    quantity: float = Field(gt=0)
    bom_revision_id: int = Field(ge=1)
    routing_revision_id: int = Field(ge=1)
    document_revision_ids: list[int] = Field(min_length=1, max_length=100)
    calendar_code: Code = Field(pattern=CODE_PATTERN)
    shift_code: Code = Field(pattern=CODE_PATTERN)
    operation_assignments: list[OperationAssignmentIn] = Field(min_length=1, max_length=500)

    @field_validator("document_revision_ids")
    @classmethod
    def unique_document_revisions(cls, values: list[int]) -> list[int]:
        if len(values) != len(set(values)):
            raise ValueError("document_revision_ids must be unique")
        return values

    @field_validator("operation_assignments")
    @classmethod
    def unique_assignment_sequences(
        cls, assignments: list[OperationAssignmentIn]
    ) -> list[OperationAssignmentIn]:
        sequences = [assignment.sequence for assignment in assignments]
        if len(sequences) != len(set(sequences)):
            raise ValueError("operation assignment sequences must be unique")
        return sorted(assignments, key=lambda assignment: assignment.sequence)
