from __future__ import annotations

import json

from fastapi import HTTPException

from .core.config import settings
from .core.security import ActorInfo, actor_identity
from .models import NodeCommand
from .repositories.ai_suggestions import ai_suggestion_repository
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
        return self._issue_target_rate(
            node_code=node_code,
            target_rate=target_rate,
            actor=actor,
            risk_level="low",
            status="pending",
            parameters={},
            audit_action="command:issue",
        )

    def issue_dispatch_target_rate(
        self,
        *,
        node_code: str,
        target_rate: float,
        actor: ActorInfo,
        order_id: str,
        product_code: str,
        plan_target_quantity: int,
        dispatch_task_ids: list[int],
        planning_horizon_minutes: int,
        physical_limit: float,
    ) -> NodeCommand:
        return self._issue_target_rate(
            node_code=node_code,
            target_rate=target_rate,
            actor=actor,
            risk_level="high",
            status="waiting_approval",
            parameters={
                "workflow_kind": "dispatch_target_rate",
                "node_executable": True,
                "source_order_id": order_id,
                "product_code": product_code,
                "plan_target_quantity": plan_target_quantity,
                "dispatch_task_ids": dispatch_task_ids,
                "planning_horizon_minutes": planning_horizon_minutes,
                "physical_limit": round(physical_limit, 3),
                "rate_unit": "parts_per_minute",
                "idempotency_key": (
                    f"dispatch:{order_id}:{node_code}:{plan_target_quantity}:"
                    f"{planning_horizon_minutes}"
                ),
                "ttl_seconds": 1800,
            },
            audit_action="dispatch:target-rate-proposed",
            allow_confirmation_pending=True,
        )

    def _issue_target_rate(
        self,
        *,
        node_code: str,
        target_rate: float,
        actor: ActorInfo,
        risk_level: str,
        status: str,
        parameters: dict[str, object],
        audit_action: str,
        allow_confirmation_pending: bool = False,
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
            risk_level=risk_level,
            actor_role=actor.role,
            actor_id=actor_identity(actor),
            known_nodes=set(self.state.nodes),
        )
        self.state.record_safety_decision(decision)
        if not decision.allow and not (
            allow_confirmation_pending
            and decision.reason_code == "confirmation_code_required"
        ):
            self._require_allowed(decision)
        command = self.state.add_command(
            node_code,
            "set_target_rate",
            risk_level,
            status,
            actor_identity(actor),
            parameters={"target_rate": target_rate, **parameters},
        )
        self.state.add_audit_log(
            actor_identity(actor),
            audit_action,
            "command",
            str(command.id),
            command.status,
            self._detail(command, decision),
        )
        return command

    def issue_ai_review(
        self,
        *,
        suggestion_id: str,
        node_code: str,
        risk_level: str,
        recommendation: str,
        evidence: dict[str, object],
        actor: ActorInfo,
    ) -> NodeCommand:
        self._require_control_enabled()
        self._require_node(node_code)
        if actor.principal_type != "ai_agent":
            raise HTTPException(status_code=403, detail="AI review requires an AI Agent principal")
        decision = safety_governor.review_control_action(
            action="review_ai_recommendation",
            target_node=node_code,
            risk_level=risk_level,
            actor_role=actor.role,
            actor_id=actor_identity(actor),
            known_nodes=set(self.state.nodes),
        )
        self.state.record_safety_decision(decision)
        if not decision.allow and decision.reason_code != "confirmation_code_required":
            self._require_allowed(decision)
        command = self.state.add_command(
            node_code,
            "review_ai_recommendation",
            risk_level,
            "waiting_approval",
            actor_identity(actor),
            parameters={
                "workflow_kind": "ai_suggestion_review",
                "node_executable": False,
                "suggestion_id": suggestion_id,
                "recommendation": recommendation,
                "evidence": evidence,
                "idempotency_key": f"ai-suggestion:{suggestion_id}",
                "ttl_seconds": 86_400,
            },
        )
        self.state.add_audit_log(
            actor_identity(actor),
            "ai:suggestion:command-created",
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
        if self._is_ai_suggestion_review(command):
            result = self.state.approve_human_review_command(
                command_id,
                actor_identity(actor),
            )
            suggestion_id = ai_suggestion_repository.set_status_for_command(
                command_id,
                "accepted",
            )
            if suggestion_id:
                result["suggestion_id"] = suggestion_id
                result["suggestion_status"] = "accepted"
        else:
            result = self.state.approve_command(command_id, actor_identity(actor))
            if self._is_dispatch_target_rate(command):
                self.state.update_dispatch_control_status(command, "approved")
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
        if self._is_ai_suggestion_review(command):
            suggestion_id = ai_suggestion_repository.set_status_for_command(
                command_id,
                "rejected",
            )
            if suggestion_id:
                result["suggestion_id"] = suggestion_id
                result["suggestion_status"] = "rejected"
        if self._is_dispatch_target_rate(command):
            self.state.update_dispatch_control_status(command, "rejected")
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
        cancelled = self.state.cancel_command(command_id, actor_identity(actor), reason)
        if self._is_ai_suggestion_review(command):
            ai_suggestion_repository.set_status_for_command(command_id, "rejected")
        if self._is_dispatch_target_rate(command):
            self.state.update_dispatch_control_status(command, "cancelled")
        return cancelled

    def retry(
        self,
        command_id: int,
        *,
        actor: ActorInfo,
        confirmation_code: str = "",
    ) -> NodeCommand | dict[str, object]:
        command = self._command(command_id)
        if self._is_ai_suggestion_review(command):
            raise HTTPException(
                status_code=409,
                detail="AI suggestion review commands cannot be retried as node commands",
            )
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
    def _is_ai_suggestion_review(command: NodeCommand) -> bool:
        return command.parameters.get("workflow_kind") == "ai_suggestion_review"

    @staticmethod
    def _is_dispatch_target_rate(command: NodeCommand) -> bool:
        return command.parameters.get("workflow_kind") == "dispatch_target_rate"

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
