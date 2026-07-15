from datetime import timedelta

from app.command_verifier import CommandVerifier
from app.models import NodeCommand, utc_now


def _command() -> NodeCommand:
    return NodeCommand(
        id=41,
        node_code="turning-workshop-01",
        command_type="set_target_rate",
        risk_level="medium",
        status="applied",
        operator="pytest",
        parameters={"target_rate": 0.9},
        verification_baseline={
            "turning-workshop-01": {
                "target_rate": 1.333,
                "actual_rate": 1.1,
                "wip_input": 8,
                "wip_output": 5,
                "utilization": 0.85,
            },
            "milling-workshop-01": {
                "target_rate": 0.833,
                "actual_rate": 0.68,
                "wip_input": 18,
                "wip_output": 6,
                "utilization": 0.9,
            },
            "grinding-workshop-01": {
                "target_rate": 1.081,
                "actual_rate": 0.75,
                "wip_input": 7,
                "wip_output": 5,
                "utilization": 0.7,
            },
        },
        applied_at=utc_now(),
    )


def _system(milling_backlog: float, *, target: float = 0.9, grinding_actual: float = 0.72):
    return {
        "turning-workshop-01": {
            "target_rate": target,
            "actual_rate": 0.82,
            "wip_input": 8,
            "wip_output": 5,
            "utilization": 0.7,
        },
        "milling-workshop-01": {
            "target_rate": 0.833,
            "actual_rate": 0.68,
            "wip_input": 6 + milling_backlog,
            "wip_output": 6,
            "utilization": 0.86,
        },
        "grinding-workshop-01": {
            "target_rate": 1.081,
            "actual_rate": grinding_actual,
            "wip_input": 6,
            "wip_output": 5,
            "utilization": 0.68,
        },
    }


def test_verifier_marks_rate_change_effective_from_observed_flow() -> None:
    verifier = CommandVerifier(min_observations=3, max_observations=5)
    command = _command()

    assert verifier.observe(command, _system(11)).status == "observing"
    assert verifier.observe(command, _system(9)).status == "observing"
    result = verifier.observe(command, _system(7))

    assert result.status == "effective"
    assert command.status == "verified"
    assert command.verification_status == "effective"
    assert command.verified_at is not None
    assert result.evidence["target_applied"] is True
    assert result.evidence["downstream_backlog_delta"] < 0
    assert result.evidence["throughput_floor_ok"] is True


def test_verifier_compares_post_command_backlog_with_creation_baseline() -> None:
    verifier = CommandVerifier(min_observations=3, max_observations=5)
    command = _command()

    assert verifier.observe(command, _system(2)).status == "observing"
    assert verifier.observe(command, _system(2)).status == "observing"
    result = verifier.observe(command, _system(2))

    assert result.status == "effective"
    assert result.evidence["baseline_downstream_backlog"] == 12
    assert result.evidence["downstream_backlog_delta"] == -10


def test_verifier_fails_when_agent_never_applies_target() -> None:
    verifier = CommandVerifier(min_observations=2, max_observations=3)
    command = _command()

    verifier.observe(command, _system(12, target=1.333))
    verifier.observe(command, _system(12, target=1.333))
    result = verifier.observe(command, _system(12, target=1.333))

    assert result.status == "failed"
    assert command.status == "failed"
    assert command.verification_status == "failed"
    assert result.evidence["target_applied"] is False


def test_verifier_reports_partial_when_target_applies_without_flow_improvement() -> None:
    verifier = CommandVerifier(min_observations=2, max_observations=3)
    command = _command()

    verifier.observe(command, _system(12))
    verifier.observe(command, _system(12))
    result = verifier.observe(command, _system(12))

    assert result.status == "partial"
    assert command.status == "verified"
    assert command.verification_status == "partial"
    assert result.evidence["target_applied"] is True
    assert result.evidence["flow_improved"] is False


def test_verifier_uses_own_rate_for_a_target_increase() -> None:
    verifier = CommandVerifier(min_observations=2, max_observations=3)
    command = _command()
    command.parameters = {"target_rate": 1.333}
    command.verification_baseline["turning-workshop-01"]["target_rate"] = 0.5
    command.verification_baseline["turning-workshop-01"]["actual_rate"] = 0.28
    system = _system(12, target=1.333)
    system["turning-workshop-01"]["actual_rate"] = 0.72

    assert verifier.observe(command, system).status == "observing"
    result = verifier.observe(command, system)

    assert result.status == "effective"
    assert result.evidence["rate_direction"] == "increase"
    assert result.evidence["own_rate_moved"] is True


def test_command_metadata_has_version_expiry_and_lifecycle_timestamps() -> None:
    now = utc_now()
    command = NodeCommand(
        id=99,
        node_code="milling-workshop-01",
        command_type="set_target_rate",
        risk_level="low",
        status="pending",
        operator="pytest",
        parameters={"target_rate": 0.72, "idempotency_key": "verify-99"},
        expires_at=now + timedelta(minutes=5),
    )

    assert command.version == 1
    assert command.expires_at > now
    assert command.attempt_count == 0
    assert command.verification_status == "not_started"
    assert command.verification_evidence == {}
