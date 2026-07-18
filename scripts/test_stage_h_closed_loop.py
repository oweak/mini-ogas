from datetime import UTC, datetime

from check_stage_h_closed_loop import (
    changed_physical_metrics,
    derive_observable_target,
    event_mentions_command,
    heartbeat_age_seconds,
)


def test_event_mentions_command_across_lifecycle_message_formats() -> None:
    command_id = 42
    cases = [
        ("command-created", "command_id=42 created with status=waiting_approval."),
        ("command-approved", "operator admin approved command #42 (set_target_rate)."),
        ("command-claimed", "agent claimed 1 command(s): 42"),
        ("command-result", "command_id=42 status=executed: applied"),
        ("command-verification-effective", "command 42 verification effective."),
    ]
    for event_type, message in cases:
        assert event_mentions_command(event_type, {"message": message}, command_id)

    assert not event_mentions_command("command-created", {"message": "command_id=420"}, command_id)
    assert not event_mentions_command("unrelated-event", {"message": "command 42"}, command_id)


def test_changed_physical_metrics_requires_output_wip_or_quality_evidence() -> None:
    baseline = {
        "finished_quantity": 10,
        "wip_input": 4,
        "wip_output": 2,
        "defect_quantity": 0,
        "actual_rate": 1.0,
    }
    rate_only = {**baseline, "actual_rate": 0.7}
    assert changed_physical_metrics(baseline, rate_only) == []

    changed = {**rate_only, "finished_quantity": 11, "wip_output": 3}
    assert changed_physical_metrics(baseline, changed) == [
        "finished_quantity",
        "wip_output",
    ]


def test_heartbeat_age_uses_snapshot_timestamp_with_timezone() -> None:
    node = {"received_at": "2026-07-18T13:27:22+08:00"}
    now = datetime(2026, 7, 18, 5, 27, 30, tzinfo=UTC)

    assert heartbeat_age_seconds(node, now=now) == 8.0


def test_observable_target_toggles_between_safe_capacity_points() -> None:
    quantity, rate, direction = derive_observable_target(
        baseline_target=0.45,
        physical_rate=1.082,
        horizon_minutes=120,
    )
    assert (quantity, rate, direction) == (90, 0.75, "increase")

    quantity, rate, direction = derive_observable_target(
        baseline_target=0.75,
        physical_rate=1.082,
        horizon_minutes=120,
    )
    assert (quantity, rate, direction) == (71, 0.592, "decrease")
