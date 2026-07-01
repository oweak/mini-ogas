from __future__ import annotations

from pydantic import BaseModel


CONFIRMATION_CODE = "CONFIRM"
HIGH_RISK_ACTIONS = {
    "isolate_node",
    "simulate_hostile_attack",
    "dispatch_plan_approve",
    "escalation_approve",
}
CONTROL_PLANE_NODES = {"cloud-workshop-01", "cloud-db-01"}


class SafetyDecision(BaseModel):
    allow: bool
    requires_human: bool = False
    confirmation_required: bool = False
    reason_code: str
    message: str
    action: str
    target_node: str = ""
    risk_level: str = "low"
    actor_role: str = ""


class SafetyGovernor:
    """Central approval gate for risky operator and AI-proposed actions."""

    def review_control_action(
        self,
        *,
        action: str,
        target_node: str | None,
        risk_level: str,
        actor_role: str,
        known_nodes: set[str],
        confirmation_code: str | None = None,
    ) -> SafetyDecision:
        target = target_node or ""
        risk = self._normalize_risk(action, risk_level)
        if target and target not in known_nodes:
            return self._deny(
                "target_node_not_found",
                f"目标节点 {target} 未注册，命令已被安全闸门拦截。",
                action,
                target,
                risk,
                actor_role,
            )
        if action == "isolate_node" and target in CONTROL_PLANE_NODES:
            return self._deny(
                "control_plane_isolation_blocked",
                f"{target} 是控制平面逻辑节点，不能通过生产处置命令隔离。",
                action,
                target,
                risk,
                actor_role,
            )
        return self._confirmation_gate(
            action=action,
            target_node=target,
            risk_level=risk,
            actor_role=actor_role,
            confirmation_code=confirmation_code,
        )

    def review_manual_approval(
        self,
        *,
        action: str,
        actor_role: str,
        confirmation_code: str | None,
        target_node: str = "",
        risk_level: str = "high",
    ) -> SafetyDecision:
        risk = self._normalize_risk(action, risk_level)
        return self._confirmation_gate(
            action=action,
            target_node=target_node,
            risk_level=risk,
            actor_role=actor_role,
            confirmation_code=confirmation_code,
        )

    def _confirmation_gate(
        self,
        *,
        action: str,
        target_node: str,
        risk_level: str,
        actor_role: str,
        confirmation_code: str | None,
    ) -> SafetyDecision:
        requires_confirmation = risk_level == "high" or action in HIGH_RISK_ACTIONS
        if requires_confirmation and confirmation_code != CONFIRMATION_CODE:
            return SafetyDecision(
                allow=False,
                requires_human=True,
                confirmation_required=True,
                reason_code="confirmation_code_required",
                message=f"高风险动作 {action} 需要确认码 {CONFIRMATION_CODE}。",
                action=action,
                target_node=target_node,
                risk_level=risk_level,
                actor_role=actor_role,
            )
        return SafetyDecision(
            allow=True,
            requires_human=requires_confirmation,
            confirmation_required=False,
            reason_code="allowed",
            message="安全闸门已批准该动作。",
            action=action,
            target_node=target_node,
            risk_level=risk_level,
            actor_role=actor_role,
        )

    def _normalize_risk(self, action: str, risk_level: str) -> str:
        risk = (risk_level or "low").lower()
        if action in HIGH_RISK_ACTIONS:
            return "high"
        if risk not in {"low", "medium", "high", "critical"}:
            return "low"
        return "high" if risk == "critical" else risk

    def _deny(
        self,
        reason_code: str,
        message: str,
        action: str,
        target_node: str,
        risk_level: str,
        actor_role: str,
    ) -> SafetyDecision:
        return SafetyDecision(
            allow=False,
            requires_human=True,
            confirmation_required=False,
            reason_code=reason_code,
            message=message,
            action=action,
            target_node=target_node,
            risk_level=risk_level,
            actor_role=actor_role,
        )


safety_governor = SafetyGovernor()
