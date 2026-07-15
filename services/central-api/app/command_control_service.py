from __future__ import annotations

import json

from fastapi import HTTPException

from .core.config import settings
from .core.security import ActorInfo, actor_identity
from .models import NodeCommand
from .safety_governor import SafetyDecision, safety_governor
from .store import MemoryStore, store


class CommandControlService:
    """Canonical authorization, safety, lifecycle, and audit boundary for commands."""

    def __init__(self, state: MemoryStore) -> None:
        self.state = state

    def issue_target_rate(
        self,
        *,
        node_code: str,
        target_rate: float,
        actor: ActorInfo,
    ) -> NodeCommand:
        self._require_control_enabled()
        self._require_node(node_code)
        physical_limit = self.state.reported_physical_rate_limit_per_minute(node_code)
        if physical_limit is not None and target_rate > physical_limit + 1e-9:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "target_exceeds_physical_capacity",
                    "message": "target_rate exceeds the latest node-reported physical capacity",
                    "requested_rate": target_rate,
                    "maximum_rate": round(physical_limit, 3),
                    "rate_unit": "parts_per_minute",
                    "node_code": node_code,
                },
            )

        decision = safety_governor.review_control_action(
            action="set_target_rate",
            target_node=node_code,
            risk_level="low",
            actor_role=actor.role,
            actor_id=actor_identity(actor),
            known_nodes=set(self.state.nodes),
        )
        self.state.record_safety_decision(decision)
        self._require_allowed(decision)
        command = self.state.add_command(
            node_code,
            "set_target_rate",
            "low",
            "pending",
            actor_identity(actor),
            parameters={"target_rate": target_rate},
        )
        self.state.add_audit_log(
            actor_identity(actor),
            "command:issue",
            "command",
            str(command.id),
            command.status,
            self._detail(command, decision),
        )
        return command

    def approve(
        self,
        command_id: int,
        *,
        actor: ActorInfo,
        confirmation_code: str = "",
    ) -> dict[str, object]:
        command = self._command(command_id)
        decision = safety_governor.review_control_action(
            action=command.command_type,
            target_node=command.node_code,
            risk_level=command.risk_level,
            actor_role=actor.role,
            actor_id=actor_identity(actor),
            known_nodes=set(self.state.nodes),
            confirmation_code=confirmation_code,
        )
        self.state.record_safety_decision(decision)
        if not decision.allow:
            return self._blocked(decision, command_id)
        result = self.state.approve_command(command_id, actor_identity(actor))
        self.state.add_audit_log(
            actor_identity(actor),
            "command:approve",
            "command",
            str(command_id),
            str(result["status"]),
            self._detail(command, decision),
        )
        return {**result, "safety": decision.model_dump(mode="json")}

    def reject(self, command_id: int, *, actor: ActorInfo, reason: str = "") -> dict[str, object]:
        command = self._command(command_id)
        decision = self._review_lifecycle_action("reject_command", command, actor)
        result = self.state.reject_command(command_id, actor_identity(actor), reason)
        self.state.add_audit_log(
            actor_identity(actor),
            "command:reject",
            "command",
            str(command_id),
            str(result["status"]),
            self._detail(command, decision, reason=reason),
        )
        return {**result, "safety": decision.model_dump(mode="json")}

    def cancel(self, command_id: int, *, actor: ActorInfo, reason: str = "") -> NodeCommand:
        command = self._command(command_id)
        self._review_lifecycle_action("cancel_command", command, actor)
        return self.state.cancel_command(command_id, actor_identity(actor), reason)

    def retry(
        self,
        command_id: int,
        *,
        actor: ActorInfo,
        confirmation_code: str = "",
    ) -> NodeCommand | dict[str, object]:
        command = self._command(command_id)
        decision = safety_governor.review_control_action(
            action=f"retry_{command.command_type}",
            target_node=command.node_code,
            risk_level=command.risk_level,
            actor_role=actor.role,
            actor_id=actor_identity(actor),
            known_nodes=set(self.state.nodes),
            confirmation_code=confirmation_code,
        )
        self.state.record_safety_decision(decision)
        if not decision.allow:
            return self._blocked(decision, command_id)
        return self.state.retry_command(command_id, actor_identity(actor))

    def _review_lifecycle_action(
        self,
        action: str,
        command: NodeCommand,
        actor: ActorInfo,
    ) -> SafetyDecision:
        decision = safety_governor.review_manual_approval(
            action=action,
            actor_role=actor.role,
            actor_id=actor_identity(actor),
            confirmation_code="",
            target_node=command.node_code,
            risk_level="low",
        )
        self.state.record_safety_decision(decision)
        self._require_allowed(decision)
        return decision

    def _command(self, command_id: int) -> NodeCommand:
        command = next((item for item in self.state.commands if item.id == command_id), None)
        if command is None:
            raise HTTPException(status_code=404, detail="command not found")
        return command

    def _require_node(self, node_code: str) -> None:
        if node_code not in self.state.nodes:
            raise HTTPException(status_code=404, detail="node not found")

    @staticmethod
    def _require_control_enabled() -> None:
        if settings.control_mode == "read_only":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "control_mode_read_only",
                    "message": "The configured CONTROL_MODE does not permit control actions.",
                },
            )

    @staticmethod
    def _require_allowed(decision: SafetyDecision) -> None:
        if not decision.allow:
            raise HTTPException(
                status_code=409,
                detail={"error": decision.reason_code, "safety": decision.model_dump(mode="json")},
            )

    @staticmethod
    def _blocked(decision: SafetyDecision, command_id: int) -> dict[str, object]:
        return {
            "accepted": False,
            "command_id": command_id,
            "status": "blocked",
            "safety": decision.model_dump(mode="json"),
        }

    @staticmethod
    def _detail(
        command: NodeCommand,
        decision: SafetyDecision,
        *,
        reason: str = "",
    ) -> str:
        return json.dumps(
            {
                "node_code": command.node_code,
                "command_type": command.command_type,
                "risk_level": command.risk_level,
                "safety_reason": decision.reason_code,
                "reason": reason,
            },
            ensure_ascii=False,
            sort_keys=True,
        )


command_control_service = CommandControlService(store)
