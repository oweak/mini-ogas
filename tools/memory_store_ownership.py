from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CENTRAL_ROOT = PROJECT_ROOT / "services" / "central-api"
STORE_PATH = CENTRAL_ROOT / "app" / "store.py"
OUTPUT_PATH = PROJECT_ROOT / "docs" / "audits" / "memory-store-ownership-map.md"


@dataclass(frozen=True)
class FieldOwnership:
    domain: str
    target_owner: str
    durable_tables: str


def _fields(
    names: str,
    domain: str,
    target_owner: str,
    durable_tables: str,
) -> dict[str, FieldOwnership]:
    return {
        name: FieldOwnership(domain, target_owner, durable_tables)
        for name in names.split()
    }


FIELD_OWNERSHIP: dict[str, FieldOwnership] = {
    **_fields("_lock", "infrastructure", "RuntimeStateCoordinator", "runtime only"),
    **_fields("rng", "simulation", "RuntimeSimulationState", "runs, scenarios"),
    **_fields(
        "nodes metrics runtime_metrics machines node_db_size_bytes node_db_size_sources "
        "node_heartbeats_v2 node_record_sync_ids",
        "node and telemetry",
        "NodeRepository / NodeService",
        "heartbeat_shadow, metrics, node_record_receipts, telemetry_*",
    ),
    **_fields(
        "market_signals market_forecast inventory production_plans dispatch_tasks "
        "allocation_orders dispatch_seq order_seq",
        "planning and dispatch",
        "PlanningRepository / PlanningService",
        "production_plan_shadow, dispatch_task_shadow, allocation_order_shadow, inventory_*",
    ),
    **_fields(
        "part_queue part_seq part_completion_watermark",
        "material flow",
        "PartQueueRepository / MaterialFlowService",
        "part_queue_shadow, material_*",
    ),
    **_fields(
        "command_repository command_manager command_verifier",
        "command and control",
        "CommandRepository / CommandService",
        "commands, command_shadow, event_store, audit_logs",
    ),
    **_fields(
        "alerts audit_logs incident_events _incident_event_seq _node_event_sequences "
        "_shadow_event_count ai_diagnoses",
        "incident, audit and AI evidence",
        "IncidentRepository / AuditRepository / AiEvidenceRepository",
        "alerts, audit_logs, event_store, ai_diagnosis",
    ),
    **_fields(
        "topology_edges ai_shortcuts authority_matrix cloud_roles",
        "topology and governance",
        "TopologyRepository / GovernanceService",
        "no durable legacy table",
    ),
    **_fields(
        "simulation_running simulation_tick simulation_speed simulation_anomaly_rate "
        "simulation_last_tick_at simulation_generated_orders simulation_generated_events",
        "simulation",
        "RuntimeSimulationState",
        "runs, scenarios; volatile counters remain rebuildable",
    ),
    **_fields(
        "_suspend_persist _primary_projection_refreshed_at _primary_projection_last_error "
        "_primary_projection_refresh_lock _primary_projection_in_progress "
        "_persistence_write_failures",
        "persistence infrastructure",
        "PersistenceCoordinator / PersistenceHealth",
        "schema_migrations and runtime-only health state",
    ),
}


DOMAIN_TARGETS = {
    "infrastructure": "RuntimeStateCoordinator",
    "command and control": "CommandRepository / CommandService",
    "node and telemetry": "NodeRepository / NodeService",
    "material flow": "PartQueueRepository / MaterialFlowService",
    "planning and dispatch": "PlanningRepository / PlanningService",
    "incident, audit and AI evidence": (
        "IncidentRepository / AuditRepository / AiEvidenceRepository"
    ),
    "topology and governance": "TopologyRepository / GovernanceService",
    "simulation": "RuntimeSimulationState / simulation worker",
    "runtime coordination": "RunContextService",
    "query and replay": "QueryService / ReplayService",
    "persistence infrastructure": "PersistenceCoordinator / adapters",
    "compatibility facade": "MemoryStore facade only",
}


def method_domain(name: str) -> str:
    normalized = name.lower()
    if name == "__init__":
        return "compatibility facade"
    if "command" in normalized or "safety" in normalized or normalized in {
        "pending_approvals",
        "reported_physical_rate_limit_per_minute",
    }:
        return "command and control"
    if "part" in normalized:
        return "material flow"
    if any(token in normalized for token in ("alert", "audit", "event", "diagnosis")) or (
        "escalat" in normalized or normalized == "add_ai_auto_briefing"
    ):
        return "incident, audit and AI evidence"
    if any(
        token in normalized
        for token in ("market", "production_plan", "dispatch", "allocation", "resource")
    ) or normalized in {"_available_machine_for", "_planner_node_health"}:
        return "planning and dispatch"
    if any(token in normalized for token in ("simulation", "scenario")) or normalized in {
        "seed_demo",
        "_initial_metric",
    }:
        return "simulation"
    if "integration" in normalized:
        return "topology and governance"
    if normalized.startswith("current_run_id"):
        return "runtime coordination"
    if any(
        token in normalized
        for token in ("node", "heartbeat", "metric", "machine", "workshop")
    ) or normalized in {"host_status"}:
        return "node and telemetry"
    if any(token in normalized for token in ("replay", "snapshot", "summary", "preflight")) or (
        normalized == "shadow_consistency_report"
    ):
        return "query and replay"
    if any(token in normalized for token in ("persist", "projection")):
        return "persistence infrastructure"
    raise ValueError(f"MemoryStore method has no ownership domain: {name}")


def _scope_name(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    current: ast.AST | None = node
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
        current = parents.get(current)
    return "<module>"


def _is_external_store_reference(node: ast.Attribute) -> bool:
    if isinstance(node.value, ast.Name):
        return node.value.id in {"store", "state"}
    return (
        isinstance(node.value, ast.Attribute)
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "self"
        and node.value.attr == "state"
    )


def _source_files() -> list[Path]:
    files = list((CENTRAL_ROOT / "app").rglob("*.py"))
    files.extend((CENTRAL_ROOT / "tests").rglob("*.py"))
    return sorted(path for path in files if "__pycache__" not in path.parts)


def _direct_callers(
    members: set[str],
    store_tree: ast.Module,
) -> dict[str, set[str]]:
    callers: dict[str, set[str]] = defaultdict(set)
    store_class = next(
        node
        for node in store_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "MemoryStore"
    )
    for method in store_class.body:
        if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if method.name == "__init__":
            continue
        for node in ast.walk(method):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "self"
                and node.attr in members
                and node.attr != method.name
            ):
                callers[node.attr].add(f"store.py::{method.name}")

    for path in _source_files():
        if path == STORE_PATH:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr in members
                and _is_external_store_reference(node)
            ):
                callers[node.attr].add(f"{relative}::{_scope_name(node, parents)}")
    return callers


SQL_TABLE_PATTERN = re.compile(
    r"(?i)\b(?:FROM|INTO|UPDATE|JOIN|DELETE\s+FROM)\s+([a-z_][a-z0-9_]*)"
)


def _method_tables(method: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    tables: set[str] = set()
    delegates: set[str] = set()
    for node in ast.walk(method):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            tables.update(SQL_TABLE_PATTERN.findall(node.value))
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in {
                "central_fact_repository",
                "outbox_repository",
                "registry",
                "safety_governor",
            }:
                delegates.add(f"{node.value.id}.{node.attr}")
    return sorted(tables) + sorted(delegates)


def _cell(values: set[str] | list[str]) -> str:
    if not values:
        return "-"
    return "<br>".join(sorted(values))


def build_document() -> str:
    source = STORE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(STORE_PATH))
    store_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "MemoryStore"
    )
    init = next(
        node
        for node in store_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    fields: dict[str, int] = {}
    for node in ast.walk(init):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
            ):
                fields[target.attr] = node.lineno

    methods = {
        node.name: node
        for node in store_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    missing_fields = sorted(set(fields) - set(FIELD_OWNERSHIP))
    stale_fields = sorted(set(FIELD_OWNERSHIP) - set(fields))
    if missing_fields or stale_fields:
        raise ValueError(
            f"field ownership drift; missing={missing_fields}, stale={stale_fields}"
        )
    domains = {name: method_domain(name) for name in methods}
    callers = _direct_callers(set(fields) | set(methods), tree)

    domain_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for ownership in FIELD_OWNERSHIP.values():
        domain_counts[ownership.domain][0] += 1
    for domain in domains.values():
        domain_counts[domain][1] += 1

    lines = [
        "# MemoryStore Ownership Map",
        "",
        "Generated by `tools/memory_store_ownership.py` from the current AST. Do not edit",
        "the inventory tables manually; run the generator and commit the result.",
        "",
        "## Scope And Interpretation",
        "",
        f"- Source: `services/central-api/app/store.py` ({len(source.splitlines())} lines).",
        f"- Inventory: {len(fields)} instance fields and {len(methods)} methods.",
        "- Caller evidence is a conservative syntactic map of `self.<member>` inside",
        "  `MemoryStore`, plus direct `store.<member>`, `state.<member>` and",
        "  `self.state.<member>` references in Central API application/tests.",
        "- SQL evidence comes only from SQL string literals in each method; delegated",
        "  repository and control calls are named separately.",
        "- PostgreSQL remains the central fact authority. A target owner describes the",
        "  extraction boundary, not permission to create a second source of truth.",
        "",
        "## Domain Summary",
        "",
        "| Domain | Fields | Methods | Target owner |",
        "| --- | ---: | ---: | --- |",
    ]
    for domain, counts in sorted(domain_counts.items()):
        lines.append(
            f"| {domain} | {counts[0]} | {counts[1]} | {DOMAIN_TARGETS.get(domain, '-')} |"
        )

    lines.extend(
        [
            "",
            "## Field Inventory",
            "",
            "| Field | Line | Domain | Current owner | Target owner | "
            "Durable tables / boundary | Direct callers |",
            "| --- | ---: | --- | --- | --- | --- | --- |",
        ]
    )
    for name, line in sorted(fields.items(), key=lambda item: item[1]):
        ownership = FIELD_OWNERSHIP[name]
        lines.append(
            f"| `{name}` | {line} | {ownership.domain} | `MemoryStore` | "
            f"{ownership.target_owner} | {ownership.durable_tables} | {_cell(callers[name])} |"
        )

    lines.extend(
        [
            "",
            "## Method Inventory",
            "",
            "| Method | Lines | Domain | Target owner | Direct SQL / delegate | Direct callers |",
            "| --- | ---: | --- | --- | --- | --- |",
        ]
    )
    for name, method in sorted(methods.items(), key=lambda item: item[1].lineno):
        domain = domains[name]
        lines.append(
            f"| `{name}` | {method.lineno}-{method.end_lineno} | {domain} | "
            f"{DOMAIN_TARGETS[domain]} | {_cell(_method_tables(method))} | "
            f"{_cell(callers[name])} |"
        )

    lines.extend(
        [
            "",
            "## Extraction Order And Gates",
            "",
            "1. Command and control: move command projection, persistence and lifecycle",
            "   ownership to `CommandRepository`/`CommandService`; keep `MemoryStore` as a",
            "   compatibility facade. Prove atomic command/event writes and restart reload.",
            "2. Node and telemetry: move node identity, heartbeat projection, metric ingest",
            "   and node lifecycle to `NodeRepository`/`NodeService`; preserve `node_code`",
            "   credential binding and fresh-heartbeat semantics.",
            "3. Scheduler and simulation: move periodic work outside API request workers and",
            "   give volatile simulation state one supervised worker owner.",
            "4. Material, planning, incident/audit and topology domains follow one at a time,",
            "   each with transaction, compatibility and restart-recovery tests.",
            "",
            "Every extraction must remove duplicate mutable ownership, preserve API contracts,",
            "keep PostgreSQL authoritative, and pass the full verifier before the next domain",
            "moves. Redis remains rebuildable and NATS remains Shadow during Stage D.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the MemoryStore ownership audit")
    parser.add_argument("--check", action="store_true", help="fail if the committed map is stale")
    args = parser.parse_args()
    document = build_document()
    if args.check:
        if not OUTPUT_PATH.exists() or OUTPUT_PATH.read_text(encoding="utf-8") != document:
            print(f"stale ownership map: {OUTPUT_PATH.relative_to(PROJECT_ROOT)}", file=sys.stderr)
            return 1
        print("MemoryStore ownership map check passed")
        return 0
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(document, encoding="utf-8")
    print(f"wrote {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
