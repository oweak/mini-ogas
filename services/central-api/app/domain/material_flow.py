from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .master_data import CODE_PATTERN, Code


class MaterialFlowError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str, **context: Any):
        super().__init__(message)
        self.status_code = status_code
        self.detail = {"code": code, "message": message, **context}


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WarehouseIn(StrictInput):
    warehouse_code: Code = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=160)
    warehouse_type: Literal["raw", "wip", "finished", "quarantine", "scrap", "shipping"]


class LocationIn(StrictInput):
    location_code: Code = Field(pattern=CODE_PATTERN)
    warehouse_code: Code = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1, max_length=160)
    location_type: Literal["storage", "staging", "wip", "quarantine", "scrap", "shipping"]


class ContainerIn(StrictInput):
    container_code: Code = Field(pattern=CODE_PATTERN)
    container_type: str = Field(min_length=1, max_length=80)
    location_code: Code = Field(pattern=CODE_PATTERN)


class LotIn(StrictInput):
    lot_code: Code = Field(pattern=CODE_PATTERN)
    material_code: Code = Field(pattern=CODE_PATTERN)
    tracking_kind: Literal["lot", "serial"]
    evidence_reference: str = Field(min_length=1, max_length=240)


class MovementIn(StrictInput):
    movement_id: Code = Field(pattern=CODE_PATTERN)
    movement_type: Literal[
        "receipt", "issue", "consume", "produce", "return", "transfer", "scrap", "rework"
    ]
    lot_code: Code = Field(pattern=CODE_PATTERN)
    quantity: float = Field(gt=0)
    from_location_code: Code | None = Field(default=None, pattern=CODE_PATTERN)
    to_location_code: Code | None = Field(default=None, pattern=CODE_PATTERN)
    from_container_code: Code | None = Field(default=None, pattern=CODE_PATTERN)
    to_container_code: Code | None = Field(default=None, pattern=CODE_PATTERN)
    operation_task_id: int | None = Field(default=None, ge=1)
    maintenance_order_code: Code | None = Field(default=None, pattern=CODE_PATTERN)
    source: Literal["manual", "execution", "erp_simulated", "wms_simulated"]
    reason: str = Field(min_length=1, max_length=1024)
    evidence_reference: str = Field(min_length=1, max_length=240)
    occurred_at: datetime

    @model_validator(mode="after")
    def validate_direction(self) -> MovementIn:
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        inbound = self.movement_type in {"receipt", "produce"}
        outbound = self.movement_type == "consume"
        bidirectional = self.movement_type in {"issue", "return", "transfer", "scrap", "rework"}
        if inbound and (self.from_location_code is not None or self.to_location_code is None):
            raise ValueError(f"{self.movement_type} requires only a destination location")
        if outbound and (self.from_location_code is None or self.to_location_code is not None):
            raise ValueError("consume requires only a source location")
        if bidirectional and (self.from_location_code is None or self.to_location_code is None):
            raise ValueError(f"{self.movement_type} requires source and destination locations")
        if self.from_container_code and not self.from_location_code:
            raise ValueError("from_container_code requires from_location_code")
        if self.to_container_code and not self.to_location_code:
            raise ValueError("to_container_code requires to_location_code")
        if (
            self.from_location_code,
            self.from_container_code or "",
        ) == (self.to_location_code, self.to_container_code or ""):
            raise ValueError("movement source and destination must differ")
        if self.movement_type == "consume":
            authorities = sum(
                value is not None for value in (self.operation_task_id, self.maintenance_order_code)
            )
            if authorities != 1:
                raise ValueError(
                    "consume requires exactly one of operation_task_id or maintenance_order_code"
                )
            expected_source = "execution" if self.operation_task_id is not None else "manual"
            if self.source != expected_source:
                raise ValueError(
                    f"consume bound to this authority must use source={expected_source}"
                )
        elif self.movement_type in {"produce", "rework"}:
            if self.operation_task_id is None:
                raise ValueError(f"{self.movement_type} requires operation_task_id")
            if self.source != "execution":
                raise ValueError(f"{self.movement_type} must use source=execution")
        elif self.maintenance_order_code is not None:
            raise ValueError("maintenance_order_code is only valid for consume movements")
        return self


class TransformationLegIn(StrictInput):
    lot_code: Code = Field(pattern=CODE_PATTERN)
    quantity: float = Field(gt=0)
    location_code: Code = Field(pattern=CODE_PATTERN)
    container_code: Code | None = Field(default=None, pattern=CODE_PATTERN)


class TransformationIn(StrictInput):
    transformation_id: Code = Field(pattern=CODE_PATTERN)
    transformation_type: Literal["split", "merge", "consume_produce", "rework"]
    inputs: list[TransformationLegIn] = Field(min_length=1, max_length=100)
    outputs: list[TransformationLegIn] = Field(min_length=1, max_length=100)
    operation_task_id: int | None = Field(default=None, ge=1)
    reason: str = Field(min_length=1, max_length=1024)
    evidence_reference: str = Field(min_length=1, max_length=240)
    conversion_evidence_reference: str = Field(default="", max_length=240)
    occurred_at: datetime

    @model_validator(mode="after")
    def validate_shape(self) -> TransformationIn:
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        if self.transformation_type == "split" and not (
            len(self.inputs) == 1 and len(self.outputs) >= 2
        ):
            raise ValueError("split requires one input and at least two outputs")
        if self.transformation_type == "merge" and not (
            len(self.inputs) >= 2 and len(self.outputs) == 1
        ):
            raise ValueError("merge requires at least two inputs and one output")
        if self.transformation_type == "rework" and not (
            len(self.inputs) == 1 and len(self.outputs) == 1
        ):
            raise ValueError("rework requires one input and one output")
        if self.transformation_type in {"consume_produce", "rework"}:
            if self.operation_task_id is None:
                raise ValueError(f"{self.transformation_type} requires operation_task_id")
        input_keys = [
            (item.lot_code, item.location_code, item.container_code or "") for item in self.inputs
        ]
        output_keys = [
            (item.lot_code, item.location_code, item.container_code or "") for item in self.outputs
        ]
        if len(input_keys) != len(set(input_keys)):
            raise ValueError("transformation inputs must be unique")
        if len(output_keys) != len(set(output_keys)):
            raise ValueError("transformation outputs must be unique")
        return self


class ExternalSnapshotItemIn(StrictInput):
    lot_code: Code = Field(pattern=CODE_PATTERN)
    location_code: Code = Field(pattern=CODE_PATTERN)
    container_code: Code | None = Field(default=None, pattern=CODE_PATTERN)
    observed_quantity: float = Field(ge=0)


class ExternalSnapshotIn(StrictInput):
    import_id: Code = Field(pattern=CODE_PATTERN)
    provider: Literal["erp_simulator", "wms_simulator"]
    contract_version: Literal["1.0"]
    observed_at: datetime
    evidence_reference: str = Field(min_length=1, max_length=240)
    items: list[ExternalSnapshotItemIn] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_snapshot(self) -> ExternalSnapshotIn:
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must include a timezone")
        keys = [
            (item.lot_code, item.location_code, item.container_code or "") for item in self.items
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("external snapshot items must be unique")
        return self


class ReconciliationAdjustmentIn(StrictInput):
    movement_id: Code = Field(pattern=CODE_PATTERN)
    reason: str = Field(min_length=1, max_length=1024)
    evidence_reference: str = Field(min_length=1, max_length=240)
