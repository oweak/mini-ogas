from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import NodeCommand, utc_now


TERMINAL_VERIFICATION_STATUSES = {"effective", "partial", "failed", "inconclusive"}
DOWNSTREAM_NODE = {
    "turning-workshop-01": "milling-workshop-01",
    "milling-workshop-01": "grinding-workshop-01",
}


def _number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _backlog(production: dict[str, Any] | None) -> float | None:
    if not production:
        return None
    incoming = _number(production.get("wip_input"))
    outgoing = _number(production.get("wip_output"))
    if incoming is None or outgoing is None:
        return None
    return incoming - outgoing


@dataclass(frozen=True)
class VerificationResult:
    status: str
    message: str
    evidence: dict[str, Any]
    terminal: bool


class CommandVerifier:
    """Classify command effect from post-command production observations."""

    def __init__(self, *, min_observations: int = 3, max_observations: int = 5) -> None:
        if min_observations < 1 or max_observations < min_observations:
            raise ValueError("invalid verification observation window")
        self.min_observations = min_observations
        self.max_observations = max_observations

    def observe(
        self,
        command: NodeCommand,
        system_production: dict[str, dict[str, Any]],
    ) -> VerificationResult:
        if command.verification_status in TERMINAL_VERIFICATION_STATUSES:
            return VerificationResult(
                command.verification_status,
                command.result_message,
                command.verification_evidence,
                True,
            )
        if command.command_type != "set_target_rate" or command.status not in {"applied", "executed"}:
            return VerificationResult("not_started", "command is not ready for verification", {}, False)

        expected_target = _number(command.parameters.get("target_rate"))
        target = system_production.get(command.node_code) or {}
        observed_target = _number(target.get("target_rate"))
        downstream_code = DOWNSTREAM_NODE.get(command.node_code, "")
        downstream = system_production.get(downstream_code) if downstream_code else None
        sink = system_production.get("grinding-workshop-01") or {}
        baseline = command.verification_baseline
        baseline_target = baseline.get(command.node_code) or {}
        baseline_downstream = baseline.get(downstream_code) if downstream_code else None
        baseline_sink = baseline.get("grinding-workshop-01") or {}

        observations = list(command.verification_evidence.get("observations") or [])
        observations.append({
            "observed_at": utc_now().isoformat(),
            "target_rate": observed_target,
            "actual_rate": _number(target.get("actual_rate")),
            "downstream_node": downstream_code,
            "downstream_backlog": _backlog(downstream),
            "downstream_wip_input": _number((downstream or {}).get("wip_input")),
            "downstream_utilization": _number((downstream or {}).get("utilization")),
            "sink_actual_rate": _number(sink.get("actual_rate")),
        })
        observations = observations[-self.max_observations :]

        target_applied = (
            expected_target is not None
            and observed_target is not None
            and abs(observed_target - expected_target) <= 0.001
        )
        backlog_values = [
            float(item["downstream_backlog"])
            for item in observations
            if item.get("downstream_backlog") is not None
        ]
        baseline_downstream_backlog = _backlog(baseline_downstream)
        post_command_backlog_delta = (
            backlog_values[-1] - backlog_values[0]
            if len(backlog_values) >= 2
            else None
        )
        backlog_delta = (
            backlog_values[-1] - baseline_downstream_backlog
            if backlog_values and baseline_downstream_backlog is not None
            else post_command_backlog_delta
        )
        flow_improved = backlog_delta is not None and backlog_delta <= -0.5

        current_downstream_wip = _number((downstream or {}).get("wip_input"))
        current_downstream_utilization = _number((downstream or {}).get("utilization"))
        severe_starvation = (
            current_downstream_wip is not None
            and current_downstream_utilization is not None
            and current_downstream_wip <= 2
            and current_downstream_utilization <= 0.45
        )
        baseline_sink_rate = _number(baseline_sink.get("actual_rate"))
        current_sink_rate = _number(sink.get("actual_rate"))
        baseline_requested = _number(baseline_target.get("target_rate"))
        sink_expected_rate: float | None = None
        if (
            command.node_code == "grinding-workshop-01"
            and expected_target is not None
            and baseline_requested is not None
            and baseline_requested > 0
            and baseline_sink_rate is not None
        ):
            sink_expected_rate = baseline_sink_rate * expected_target / baseline_requested
        throughput_floor_rate = (
            sink_expected_rate * 0.9
            if sink_expected_rate is not None
            else (baseline_sink_rate * 0.7 if baseline_sink_rate is not None else None)
        )
        throughput_floor_ok = (
            baseline_sink_rate is None
            or baseline_sink_rate <= 0
            or (
                current_sink_rate is not None
                and throughput_floor_rate is not None
                and current_sink_rate >= throughput_floor_rate
            )
        )
        baseline_actual = _number(baseline_target.get("actual_rate"))
        current_actual = _number(target.get("actual_rate"))
        rate_direction = "unchanged"
        if expected_target is not None and baseline_requested is not None:
            if expected_target < baseline_requested - 0.001:
                rate_direction = "decrease"
            elif expected_target > baseline_requested + 0.001:
                rate_direction = "increase"
        own_rate_moved = False
        if expected_target is not None and baseline_actual is not None and current_actual is not None:
            if baseline_requested is not None and expected_target < baseline_requested:
                own_rate_moved = current_actual <= baseline_actual - 0.02
            elif baseline_requested is not None and expected_target > baseline_requested:
                own_rate_moved = current_actual >= baseline_actual + 0.02

        evidence = {
            "expected_target_rate": expected_target,
            "observed_target_rate": observed_target,
            "target_applied": target_applied,
            "observation_count": len(observations),
            "min_observations": self.min_observations,
            "max_observations": self.max_observations,
            "downstream_node": downstream_code,
            "baseline_downstream_backlog": baseline_downstream_backlog,
            "downstream_backlog_delta": backlog_delta,
            "post_command_backlog_delta": post_command_backlog_delta,
            "flow_improved": flow_improved,
            "rate_direction": rate_direction,
            "own_rate_moved": own_rate_moved,
            "severe_starvation": severe_starvation,
            "sink_expected_rate": sink_expected_rate,
            "throughput_floor_rate": throughput_floor_rate,
            "throughput_floor_ok": throughput_floor_ok,
            "observations": observations,
        }
        command.verification_evidence = evidence
        command.verification_status = "observing"
        command.updated_at = utc_now()

        if len(observations) < self.min_observations:
            return VerificationResult("observing", "waiting for more production observations", evidence, False)

        if not target_applied:
            if len(observations) < self.max_observations:
                return VerificationResult("observing", "target rate has not appeared in heartbeat yet", evidence, False)
            return self._finish(command, "failed", "target rate was not applied within the verification window", evidence)

        if severe_starvation or not throughput_floor_ok:
            return self._finish(command, "failed", "command caused an unacceptable downstream production effect", evidence)

        if rate_direction == "increase":
            effect_proven = own_rate_moved
        elif rate_direction == "unchanged":
            effect_proven = target_applied
        else:
            effect_proven = flow_improved if downstream_code else own_rate_moved
        if effect_proven:
            if rate_direction == "increase":
                message = "target applied and observed node production rate increased"
            elif rate_direction == "unchanged":
                message = "requested target was already applied"
            else:
                message = (
                    "target applied and observed downstream flow improved"
                    if downstream_code
                    else "target applied and observed node production rate decreased"
                )
            return self._finish(command, "effective", message, evidence)

        if len(observations) < self.max_observations:
            return VerificationResult("observing", "target applied; waiting for downstream trend", evidence, False)

        if downstream_code and downstream is None:
            return self._finish(command, "inconclusive", "downstream observations were unavailable", evidence)
        return self._finish(command, "partial", "target applied but downstream flow did not improve", evidence)

    @staticmethod
    def _finish(
        command: NodeCommand,
        status: str,
        message: str,
        evidence: dict[str, Any],
    ) -> VerificationResult:
        now = utc_now()
        command.verification_status = status
        command.verification_evidence = evidence
        command.verified_at = now
        command.updated_at = now
        command.result_message = message
        if status in {"effective", "partial"}:
            command.status = "verified"
        elif status == "failed":
            command.status = "failed"
        else:
            command.status = "applied"
        return VerificationResult(status, message, evidence, True)
