from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .master_data import CODE_PATTERN


class DataPlatformError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str, **context: Any):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.context = context


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SignalDefinitionIn(StrictInput):
    signal_code: str = Field(pattern=CODE_PATTERN)
    display_name: str = Field(min_length=1, max_length=160)
    value_type: Literal["number", "integer", "boolean", "text"]
    unit: str = Field(default="", max_length=40)
    minimum: float | None = None
    maximum: float | None = None
    freshness_threshold_ms: int = Field(gt=0, le=86_400_000)
    allowed_sources: list[Literal["simulated", "replay", "shadow", "live"]] = Field(
        min_length=1,
        max_length=4,
    )
    mapping_version: int = Field(gt=0)

    @field_validator("allowed_sources")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("allowed_sources must not contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_range(self) -> SignalDefinitionIn:
        if self.minimum is not None and self.maximum is not None:
            if self.minimum > self.maximum:
                raise ValueError("minimum cannot exceed maximum")
        if self.value_type in {"boolean", "text"}:
            if self.minimum is not None or self.maximum is not None:
                raise ValueError("boolean and text signals cannot define numeric limits")
        return self


class TelemetrySampleIn(StrictInput):
    sample_id: str = Field(min_length=1, max_length=128)
    signal_code: str = Field(pattern=CODE_PATTERN)
    value: float | int | bool | str
    unit: str = Field(default="", max_length=40)
    mapping_version: int = Field(gt=0)
    sequence_no: int = Field(ge=0)
    source_timestamp: datetime
    simulation_time: datetime | None = None

    @field_validator("source_timestamp", "simulation_time")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("telemetry timestamps must include a timezone")
        return value


class TelemetryBatchIn(StrictInput):
    batch_id: str = Field(min_length=1, max_length=128)
    source: Literal["simulated", "replay", "shadow", "live"]
    source_id: str = Field(min_length=1, max_length=128)
    equipment_code: str = Field(pattern=CODE_PATTERN)
    edge_received_at: datetime
    samples: list[TelemetrySampleIn] = Field(min_length=1, max_length=2_000)

    @field_validator("edge_received_at")
    @classmethod
    def edge_timestamp_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("edge_received_at must include a timezone")
        return value

    @field_validator("samples")
    @classmethod
    def unique_sample_identity(cls, value: list[TelemetrySampleIn]) -> list[TelemetrySampleIn]:
        sample_ids = [item.sample_id for item in value]
        sequences = [(item.signal_code, item.sequence_no) for item in value]
        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError("sample_id values must be unique within a batch")
        if len(sequences) != len(set(sequences)):
            raise ValueError("signal sequence numbers must be unique within a batch")
        return value


class ProjectionRebuildIn(StrictInput):
    reason: str = Field(min_length=3, max_length=240)


class AggregateTelemetryIn(StrictInput):
    from_timestamp: datetime | None = None
    to_timestamp: datetime | None = None

    @model_validator(mode="after")
    def validate_window(self) -> AggregateTelemetryIn:
        for value in (self.from_timestamp, self.to_timestamp):
            if value is not None and value.tzinfo is None:
                raise ValueError("aggregation timestamps must include a timezone")
        if self.from_timestamp and self.to_timestamp:
            if self.to_timestamp <= self.from_timestamp:
                raise ValueError("to_timestamp must be after from_timestamp")
        return self


class RetentionRunIn(StrictInput):
    reason: str = Field(min_length=3, max_length=240)
