from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class PublishResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["disabled", "published", "degraded", "rejected"]
    message_id: str = ""
    subject: str = ""
    error_category: str = ""


class EventPublisher(ABC):
    @abstractmethod
    async def publish_event(self, event: Any) -> PublishResult:
        raise NotImplementedError

    @abstractmethod
    async def publish_heartbeat(self, heartbeat: dict[str, object]) -> PublishResult:
        raise NotImplementedError

    @abstractmethod
    async def publish_command(self, command: Any) -> PublishResult:
        raise NotImplementedError

    @abstractmethod
    async def publish_audit(self, audit: Any, *, run_id: str = "") -> PublishResult:
        raise NotImplementedError
