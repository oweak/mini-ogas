from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .models import NodeCommand, utc_now


CLAIMABLE_STATUSES = {"pending", "queued"}
APPROVAL_STATUS = "waiting_approval"
RESULT_STATUSES = {"executed", "failed"}
TERMINAL_STATUSES = {"failed", "verified", "rejected", "expired", "superseded", "cancelled"}
RETRYABLE_STATUSES = {"failed", "rejected", "expired", "cancelled"}


@dataclass(frozen=True)
class CommandTransition:
    command: NodeCommand
    stage: str
    message: str


class CommandManager:
    """Owns node-command lifecycle transitions.

    The store keeps persistence and audit side effects; this manager keeps
    state-change rules deterministic and testable.
    """

    def create_command(
        self,
        commands: list[NodeCommand],
        *,
        node_code: str,
        command_type: str,
        risk_level: str,
        status: str,
        operator: str,
        parameters: dict[str, object] | None = None,
        verification_baseline: dict[str, dict[str, object]] | None = None,
        now: datetime | None = None,
    ) -> tuple[NodeCommand, list[CommandTransition], bool]:
        now = now or utc_now()
        normalized_parameters = dict(parameters or {})
        idempotency_key = str(normalized_parameters.get("idempotency_key") or "")
        if idempotency_key:
            for command in commands:
                if (
                    command.node_code == node_code
                    and command.command_type == command_type
                    and command.parameters.get("idempotency_key") == idempotency_key
                ):
                    return command, [], False

        next_id = max((item.id for item in commands), default=0) + 1
        normalized_parameters.setdefault("idempotency_key", f"command-{next_id}")
        ttl_seconds = int(normalized_parameters.get("ttl_seconds") or 300)
        command = NodeCommand(
            id=next_id,
            node_code=node_code,
            command_type=command_type,
            risk_level=risk_level,
            status=status,
            operator=operator,
            parameters=normalized_parameters,
            expires_at=now + timedelta(seconds=max(1, ttl_seconds)),
            verification_baseline=verification_baseline or {},
            created_at=now,
            updated_at=now,
        )
        transitions = self.supersede_pending(
            commands,
            node_code=node_code,
            command_type=command_type,
            replacement_id=command.id,
            now=now,
        )
        commands.append(command)
        del commands[:-100]
        return command, transitions, True

    def pending_for_node(self, commands: list[NodeCommand], node_code: str) -> list[NodeCommand]:
        return [c for c in commands if c.node_code == node_code and c.status in CLAIMABLE_STATUSES]

    def claim_for_node(
        self,
        commands: list[NodeCommand],
        *,
        node_code: str,
        agent_id: str = "",
        now: datetime | None = None,
    ) -> list[NodeCommand]:
        now = now or utc_now()
        claimed: list[NodeCommand] = []
        for command in commands:
            if command.node_code != node_code or command.status not in CLAIMABLE_STATUSES:
                continue
            command.status = "claimed"
            command.claimed_by = agent_id or node_code
            command.dispatched_at = command.dispatched_at or now
            command.received_at = now
            command.attempt_count += 1
            command.updated_at = now
            claimed.append(command)
        return claimed

    def record_result(
        self,
        commands: list[NodeCommand],
        *,
        node_code: str,
        command_id: int,
        status: str,
        message: str,
        now: datetime | None = None,
    ) -> tuple[NodeCommand, bool]:
        now = now or utc_now()
        command = self._find_for_node(commands, node_code, command_id)
        if status not in RESULT_STATUSES | {"applied"}:
            raise ValueError(f"unsupported command result status: {status}")
        normalized_status = "applied" if status in {"executed", "applied"} else status

        if command.status == "verified":
            return command, False
        if command.status == normalized_status and command.result_message == message:
            return command, False
        if command.status in {"expired", "superseded", "rejected", "cancelled"}:
            raise ValueError(f"command {command_id} is not executable (current: {command.status})")
        if command.status not in {"claimed", "pending", "queued", "executed", "applied", "failed"}:
            raise ValueError(f"command {command_id} cannot accept result from status {command.status}")

        command.status = normalized_status
        command.result_message = message
        if command.status == "applied":
            command.applied_at = now
            command.verification_status = "observing"
        command.updated_at = now
        return command, True

    def pending_approvals(self, commands: list[NodeCommand]) -> list[NodeCommand]:
        return [c for c in commands if c.status == APPROVAL_STATUS]

    def approve(
        self,
        commands: list[NodeCommand],
        *,
        command_id: int,
        actor: str,
        now: datetime | None = None,
    ) -> NodeCommand:
        now = now or utc_now()
        command = self._find(commands, command_id)
        if command.status != APPROVAL_STATUS:
            raise ValueError(f"command {command_id} is not waiting approval (current: {command.status})")
        command.status = "pending"
        command.operator = actor
        command.updated_at = now
        return command

    def reject(
        self,
        commands: list[NodeCommand],
        *,
        command_id: int,
        actor: str,
        now: datetime | None = None,
    ) -> NodeCommand:
        now = now or utc_now()
        command = self._find(commands, command_id)
        if command.status != APPROVAL_STATUS:
            raise ValueError(f"command {command_id} is not waiting approval (current: {command.status})")
        command.status = "rejected"
        command.operator = actor
        command.updated_at = now
        return command

    def cancel(
        self,
        commands: list[NodeCommand],
        *,
        command_id: int,
        actor: str,
        reason: str = "",
        now: datetime | None = None,
    ) -> tuple[NodeCommand, bool]:
        now = now or utc_now()
        command = self._find(commands, command_id)
        if command.status == "cancelled":
            return command, False
        if command.status in TERMINAL_STATUSES or command.status == "executed":
            raise ValueError(f"command {command_id} cannot be cancelled from status {command.status}")
        command.status = "cancelled"
        command.operator = actor
        command.result_message = f"cancelled by {actor}: {reason or 'no reason provided'}"
        command.updated_at = now
        return command, True

    def retry(
        self,
        commands: list[NodeCommand],
        *,
        command_id: int,
        actor: str,
        now: datetime | None = None,
    ) -> tuple[NodeCommand, list[CommandTransition]]:
        now = now or utc_now()
        source = self._find(commands, command_id)
        if source.status not in RETRYABLE_STATUSES:
            raise ValueError(f"command {command_id} cannot be retried from status {source.status}")
        parameters = dict(source.parameters)
        parameters.pop("idempotency_key", None)
        parameters["retry_of"] = source.id
        command, transitions, _ = self.create_command(
            commands,
            node_code=source.node_code,
            command_type=source.command_type,
            risk_level=source.risk_level,
            status="pending",
            operator=actor,
            parameters=parameters,
            now=now,
        )
        return command, transitions

    def expire_stale_claims(
        self,
        commands: list[NodeCommand],
        *,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> list[CommandTransition]:
        now = now or utc_now()
        cutoff = now - timedelta(seconds=ttl_seconds)
        expired: list[CommandTransition] = []
        for command in commands:
            if command.status != "claimed" or command.updated_at >= cutoff:
                continue
            command.status = "expired"
            command.result_message = f"claim timed out after {ttl_seconds}s without result"
            command.updated_at = now
            expired.append(CommandTransition(
                command=command,
                stage="command-expired",
                message=f"command_id={command.id} expired after agent claim timeout.",
            ))
        return expired

    def supersede_pending(
        self,
        commands: list[NodeCommand],
        *,
        node_code: str,
        command_type: str,
        replacement_id: int,
        now: datetime | None = None,
    ) -> list[CommandTransition]:
        now = now or utc_now()
        transitions: list[CommandTransition] = []
        for command in commands:
            if (
                command.node_code == node_code
                and command.command_type == command_type
                and command.status in {APPROVAL_STATUS, "pending", "queued"}
            ):
                command.status = "superseded"
                command.result_message = f"superseded by command_id={replacement_id}"
                command.updated_at = now
                transitions.append(CommandTransition(
                    command=command,
                    stage="command-superseded",
                    message=f"command_id={command.id} superseded by command_id={replacement_id}.",
                ))
        return transitions

    def verify_target_rate(
        self,
        commands: list[NodeCommand],
        *,
        node_code: str,
        target_rate: float,
        now: datetime | None = None,
    ) -> list[CommandTransition]:
        now = now or utc_now()
        transitions: list[CommandTransition] = []
        for command in commands:
            if (
                command.node_code != node_code
                or command.command_type != "set_target_rate"
                or command.status not in {"executed", "applied"}
            ):
                continue
            try:
                expected = float(command.parameters.get("target_rate"))
            except (TypeError, ValueError):
                continue
            if abs(target_rate - expected) <= 0.001:
                command.status = "verified"
                command.result_message = f"heartbeat target_rate={target_rate} verified"
                command.updated_at = now
                transitions.append(CommandTransition(
                    command=command,
                    stage="command-verified",
                    message=f"command_id={command.id} set_target_rate verified by heartbeat.",
                ))
        return transitions

    def _find(self, commands: list[NodeCommand], command_id: int) -> NodeCommand:
        command = next((c for c in commands if c.id == command_id), None)
        if command is None:
            raise ValueError(f"command {command_id} not found")
        return command

    def _find_for_node(self, commands: list[NodeCommand], node_code: str, command_id: int) -> NodeCommand:
        command = next((c for c in commands if c.id == command_id and c.node_code == node_code), None)
        if command is None:
            raise ValueError(f"command {command_id} not found for node {node_code}")
        return command
