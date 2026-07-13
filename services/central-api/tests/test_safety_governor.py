from app.safety_governor import safety_governor


KNOWN_NODES = {
    "turning-workshop-01",
    "milling-workshop-01",
    "grinding-workshop-01",
    "cloud-workshop-01",
    "cloud-db-01",
}


def test_high_risk_action_requires_confirmation_code() -> None:
    decision = safety_governor.review_control_action(
        action="isolate_node",
        target_node="milling-workshop-01",
        risk_level="high",
        actor_role="operator",
        known_nodes=KNOWN_NODES,
        confirmation_code=None,
    )

    assert decision.allow is False
    assert decision.confirmation_required is True
    assert decision.reason_code == "confirmation_code_required"


def test_control_plane_node_cannot_be_isolated_by_production_command() -> None:
    decision = safety_governor.review_control_action(
        action="isolate_node",
        target_node="cloud-workshop-01",
        risk_level="high",
        actor_role="system_admin",
        known_nodes=KNOWN_NODES,
        confirmation_code="CONFIRM",
    )

    assert decision.allow is False
    assert decision.confirmation_required is False
    assert decision.reason_code == "control_plane_isolation_blocked"


def test_unknown_target_node_is_denied_before_execution() -> None:
    decision = safety_governor.review_control_action(
        action="restore_node",
        target_node="missing-node",
        risk_level="medium",
        actor_role="operator",
        known_nodes=KNOWN_NODES,
    )

    assert decision.allow is False
    assert decision.reason_code == "target_node_not_found"


def test_dispatch_approval_with_confirmation_is_allowed() -> None:
    decision = safety_governor.review_manual_approval(
        action="dispatch_plan_approve",
        actor_role="system_admin",
        confirmation_code="CONFIRM",
    )

    assert decision.allow is True
    assert decision.requires_human is True
    assert decision.reason_code == "allowed"


def test_operator_cannot_execute_high_risk_action_even_with_confirmation() -> None:
    decision = safety_governor.review_control_action(
        action="isolate_node",
        target_node="milling-workshop-01",
        risk_level="high",
        actor_role="operator",
        known_nodes=KNOWN_NODES,
        confirmation_code="CONFIRM",
    )

    assert decision.allow is False
    assert decision.reason_code == "insufficient_role"


def test_emergency_containment_policy_can_auto_isolate_production_node() -> None:
    decision = safety_governor.review_control_action(
        action="isolate_node",
        target_node="milling-workshop-01",
        risk_level="high",
        actor_role="safety_automation",
        known_nodes=KNOWN_NODES,
        run_mode="emergency_containment",
    )

    assert decision.allow is True
    assert decision.requires_human is False
    assert decision.reason_code == "emergency_containment_allowed"
    assert decision.run_mode == "emergency_containment"
