from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class GateFailure(RuntimeError):
    pass


class ApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.token = ""

    def call(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        expected: tuple[int, ...] = (200, 201),
    ) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=90) as response:
                result = json.loads(response.read().decode("utf-8") or "{}")
                if response.status not in expected:
                    raise GateFailure(
                        f"{method} {path} returned {response.status}, expected {expected}"
                    )
                return result
        except HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(response_body)
            except json.JSONDecodeError:
                detail = {"body": response_body}
            if exc.code in expected:
                return detail
            raise GateFailure(f"{method} {path} returned {exc.code}: {detail}") from exc

    def post(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        expected: tuple[int, ...] = (200, 201),
    ) -> dict[str, Any]:
        return self.call("POST", path, payload or {}, expected=expected)

    def get(self, path: str) -> dict[str, Any]:
        return self.call("GET", path, expected=(200,))


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        raise GateFailure(f"runtime authentication file is missing: {path}")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _expect_problem(
    client: ApiClient,
    path: str,
    payload: dict[str, Any],
    expected_code: str,
) -> None:
    problem = client.post(path, payload, expected=(409,))
    detail = problem.get("detail") or {}
    if detail.get("code") != expected_code:
        raise GateFailure(
            f"{path} returned the wrong stable error code: "
            f"expected {expected_code}, got {detail.get('code')}"
        )


def _seed_master_data(client: ApiClient, prefix: str) -> dict[str, Any]:
    now = datetime.now(UTC)
    parent: str | None = None
    for suffix, name, unit_type in (
        ("ENT", "Enterprise", "enterprise"),
        ("SITE", "Site", "site"),
        ("AREA", "Area", "area"),
        ("LINE", "Line", "line"),
        ("CELL", "Cell", "cell"),
    ):
        code = f"{prefix}-{suffix}"
        payload = {"unit_code": code, "name": f"{prefix} {name}", "unit_type": unit_type}
        if parent:
            payload["parent_code"] = parent
        client.post("/master-data/organization-units", payload, expected=(201,))
        parent = code

    each = f"{prefix}-EA"
    kilogram = f"{prefix}-KG"
    raw_material = f"{prefix}-RAW"
    product = f"{prefix}-PART"
    client.post(
        "/master-data/uoms",
        {"uom_code": each, "name": "Each", "dimension": "count", "scale": 1},
        expected=(201,),
    )
    client.post(
        "/master-data/uoms",
        {
            "uom_code": kilogram,
            "name": "Kilogram",
            "dimension": "mass",
            "scale": 1,
        },
        expected=(201,),
    )
    client.post(
        "/master-data/materials",
        {
            "material_code": raw_material,
            "name": "Validation steel",
            "material_type": "raw",
            "base_uom_code": kilogram,
        },
        expected=(201,),
    )
    client.post(
        "/master-data/materials",
        {
            "material_code": product,
            "name": "Validation part",
            "material_type": "finished",
            "base_uom_code": each,
        },
        expected=(201,),
    )
    client.post(
        "/master-data/products",
        {
            "product_code": product,
            "name": "Validation governed part",
            "material_code": product,
        },
        expected=(201,),
    )

    equipment = f"{prefix}-EQ"
    capability = f"{prefix}-CAP"
    skill = f"{prefix}-SKILL"
    personnel = f"{prefix}-OP"
    client.post(
        "/master-data/equipment",
        {
            "equipment_code": equipment,
            "name": "Validation machine",
            "equipment_type": "lathe",
            "organization_unit_code": parent,
        },
        expected=(201,),
    )
    client.post(
        f"/master-data/equipment/{equipment}/capabilities",
        {"capability_code": capability, "name": "Validation turning"},
        expected=(201,),
    )
    client.post(
        "/master-data/skills",
        {"skill_code": skill, "name": "Validation skill", "level_min": 2},
        expected=(201,),
    )
    client.post(
        "/master-data/personnel",
        {"personnel_code": personnel, "display_name": "Validation operator"},
        expected=(201,),
    )
    client.post(
        "/master-data/qualifications",
        {
            "personnel_code": personnel,
            "skill_code": skill,
            "level": 2,
            "valid_from": (now - timedelta(days=1)).isoformat(),
            "valid_to": (now + timedelta(days=30)).isoformat(),
            "evidence_reference": f"{prefix}-CERT",
        },
        expected=(201,),
    )

    calendar = f"{prefix}-CAL"
    shift = f"{prefix}-DAY"
    client.post(
        "/master-data/calendars",
        {
            "calendar_code": calendar,
            "name": "Validation calendar",
            "timezone": "Asia/Shanghai",
        },
        expected=(201,),
    )
    client.post(
        f"/master-data/calendars/{calendar}/shifts",
        {
            "shift_code": shift,
            "name": "Day",
            "start_time": "08:00",
            "end_time": "16:00",
        },
        expected=(201,),
    )

    document = f"{prefix}-WI"
    client.post(
        "/master-data/documents",
        {
            "document_code": document,
            "title": "Validation instruction",
            "document_type": "work_instruction",
        },
        expected=(201,),
    )
    document_revision = client.post(
        f"/master-data/documents/{document}/revisions",
        {"revision": "A", "content": "Validated setup instruction."},
        expected=(201,),
    )
    client.post(
        f"/master-data/document-revisions/{document_revision['id']}/approve",
        expected=(200,),
    )
    client.post(
        f"/master-data/document-revisions/{document_revision['id']}/effective",
        expected=(200,),
    )

    bom = f"{prefix}-BOM"
    client.post(
        "/master-data/boms",
        {"bom_code": bom, "product_code": product, "name": "Validation BOM"},
        expected=(201,),
    )
    bom_revision = client.post(
        f"/master-data/boms/{bom}/revisions",
        {
            "revision": 1,
            "items": [
                {"material_code": raw_material, "quantity": 2.5, "uom_code": kilogram}
            ],
        },
        expected=(201,),
    )
    client.post(
        f"/master-data/bom-revisions/{bom_revision['id']}/approve", expected=(200,)
    )
    client.post(
        f"/master-data/bom-revisions/{bom_revision['id']}/effective", expected=(200,)
    )

    routing = f"{prefix}-RT"
    operation = f"{prefix}-OP10"
    client.post(
        "/master-data/routings",
        {"routing_code": routing, "product_code": product, "name": "Validation routing"},
        expected=(201,),
    )
    routing_revision = client.post(
        f"/master-data/routings/{routing}/revisions",
        {
            "revision": 1,
            "operations": [
                {
                    "sequence": 10,
                    "operation_code": operation,
                    "name": "Validation turn",
                    "capability_code": capability,
                    "required_skill_code": skill,
                    "required_skill_level": 2,
                    "document_code": document,
                    "standard_time_seconds": 60,
                }
            ],
        },
        expected=(201,),
    )
    client.post(
        f"/master-data/routing-revisions/{routing_revision['id']}/approve",
        expected=(200,),
    )
    client.post(
        f"/master-data/routing-revisions/{routing_revision['id']}/effective",
        expected=(200,),
    )
    return {
        "raw_material": raw_material,
        "product": product,
        "each_uom": each,
        "kilogram_uom": kilogram,
        "equipment": equipment,
        "personnel": personnel,
        "calendar": calendar,
        "shift": shift,
        "document_revision_id": document_revision["id"],
        "bom_revision_id": bom_revision["id"],
        "routing_revision_id": routing_revision["id"],
    }


def run_gate(api_url: str, runtime_root: Path) -> dict[str, Any]:
    auth = _read_env_file(runtime_root / "auth.env")
    password = auth.get("AUTH_BOOTSTRAP_PASSWORD", "")
    if not password:
        raise GateFailure("AUTH_BOOTSTRAP_PASSWORD is missing from runtime auth.env")
    client = ApiClient(api_url)
    login = client.post(
        "/auth/login",
        {"operator": "admin", "password": password},
        expected=(200,),
    )
    client.token = str(login.get("access_token") or "")
    if not client.token:
        raise GateFailure("administrator login did not return a bearer token")

    prefix = f"V3G{datetime.now(UTC):%m%d%H%M%S}{uuid4().hex[:4].upper()}"
    master = _seed_master_data(client, prefix)
    work_order = f"{prefix}-WO"
    production_order = f"{prefix}-PO"
    client.post(
        "/master-data/work-orders",
        {
            "work_order_code": work_order,
            "product_code": master["product"],
            "quantity": 4,
            "bom_revision_id": master["bom_revision_id"],
            "routing_revision_id": master["routing_revision_id"],
            "document_revision_ids": [master["document_revision_id"]],
            "calendar_code": master["calendar"],
            "shift_code": master["shift"],
            "operation_assignments": [
                {
                    "sequence": 10,
                    "equipment_code": master["equipment"],
                    "personnel_code": master["personnel"],
                }
            ],
        },
        expected=(201,),
    )
    client.post(f"/master-data/work-orders/{work_order}/release", expected=(200,))
    client.post(
        "/execution/production-orders",
        {
            "production_order_code": production_order,
            "product_code": master["product"],
            "quantity": 4,
            "priority": 5,
            "due_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        },
        expected=(201,),
    )
    client.post(
        f"/execution/production-orders/{production_order}/work-orders/{work_order}/attach",
        {"idempotency_key": f"{prefix}-ATTACH"},
        expected=(200,),
    )
    client.post(
        f"/execution/production-orders/{production_order}/release",
        {"idempotency_key": f"{prefix}-RELEASE", "reason": "runtime gate"},
        expected=(200,),
    )
    dispatch = client.post(
        f"/execution/work-orders/{work_order}/dispatch",
        {"idempotency_key": f"{prefix}-DISPATCH"},
        expected=(200,),
    )
    task_id = int(dispatch["tasks"][0]["id"])
    _expect_problem(
        client,
        f"/execution/tasks/{task_id}/start",
        {"idempotency_key": f"{prefix}-SKIP-SETUP"},
        "INVALID_OPERATION_TRANSITION",
    )
    client.post(
        f"/execution/tasks/{task_id}/setup/start",
        {"idempotency_key": f"{prefix}-SETUP-START"},
        expected=(200,),
    )
    client.post(
        f"/execution/tasks/{task_id}/setup/complete",
        {
            "idempotency_key": f"{prefix}-SETUP-COMPLETE",
            "evidence_reference": f"{prefix}-SETUP-EVIDENCE",
            "parameters": {"chuck_pressure_bar": 18.5},
        },
        expected=(200,),
    )
    client.post(
        f"/execution/tasks/{task_id}/start",
        {"idempotency_key": f"{prefix}-START"},
        expected=(200,),
    )
    _expect_problem(
        client,
        f"/execution/tasks/{task_id}/complete",
        {
            "idempotency_key": f"{prefix}-PREMATURE-COMPLETE",
            "evidence_reference": f"{prefix}-INSPECTION",
        },
        "QUANTITY_NOT_CONSERVED",
    )
    report_time = datetime.now(UTC).isoformat()
    first_report = {
        "report_id": f"{prefix}-REPORT-1",
        "good_quantity": 3,
        "scrap_quantity": 0,
        "rework_quantity": 0,
        "evidence_reference": f"{prefix}-COUNTER-1",
        "occurred_at": report_time,
    }
    first = client.post(
        f"/execution/tasks/{task_id}/quantity-reports", first_report, expected=(201,)
    )
    repeated = client.post(
        f"/execution/tasks/{task_id}/quantity-reports", first_report, expected=(201,)
    )
    if first.get("id") != repeated.get("id"):
        raise GateFailure("quantity report retry created a duplicate fact")
    _expect_problem(
        client,
        f"/execution/tasks/{task_id}/quantity-reports",
        {
            **first_report,
            "report_id": f"{prefix}-REPORT-OVER",
            "good_quantity": 2,
        },
        "QUANTITY_EXCEEDS_PLAN",
    )
    client.post(
        f"/execution/tasks/{task_id}/quantity-reports",
        {
            "report_id": f"{prefix}-REPORT-2",
            "good_quantity": 0,
            "scrap_quantity": 1,
            "rework_quantity": 0,
            "evidence_reference": f"{prefix}-COUNTER-2",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
        expected=(201,),
    )
    _expect_problem(
        client,
        f"/execution/tasks/{task_id}/complete",
        {"idempotency_key": f"{prefix}-NO-EVIDENCE", "evidence_reference": ""},
        "COMPLETION_EVIDENCE_REQUIRED",
    )
    client.post(
        f"/execution/tasks/{task_id}/complete",
        {
            "idempotency_key": f"{prefix}-COMPLETE",
            "evidence_reference": f"{prefix}-INSPECTION",
        },
        expected=(200,),
    )
    client.post(
        f"/execution/tasks/{task_id}/close",
        {"idempotency_key": f"{prefix}-TASK-CLOSE"},
        expected=(200,),
    )
    work_order_state = client.post(
        f"/execution/work-orders/{work_order}/close",
        {"idempotency_key": f"{prefix}-WO-CLOSE"},
        expected=(200,),
    )
    production_order_state = client.post(
        f"/execution/production-orders/{production_order}/close",
        {"idempotency_key": f"{prefix}-PO-CLOSE"},
        expected=(200,),
    )
    replay = client.get(f"/execution/work-orders/{work_order}/replay")
    statuses = [item["to_status"] for item in replay["status_history"]]
    expected_statuses = ["dispatched", "setup", "ready", "running", "completed", "closed"]
    if statuses != expected_statuses:
        raise GateFailure(f"replay status history mismatch: {statuses}")
    if len(replay["quantity_reports"]) != 2:
        raise GateFailure("replay did not preserve exactly two accepted quantity reports")
    if work_order_state["execution_status"] != "closed":
        raise GateFailure("work-order execution did not reach closed")
    if production_order_state["status"] != "closed":
        raise GateFailure("production order did not reach closed")
    return {
        "status": "PASS",
        "validation_prefix": prefix,
        "work_order_status": work_order_state["execution_status"],
        "production_order_status": production_order_state["status"],
        "task_count": len(replay["tasks"]),
        "history_events": len(replay["status_history"]),
        "quantity_reports": len(replay["quantity_reports"]),
        "ai_smoke_ok": bool((login.get("ai_smoke") or {}).get("ok")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the Phase 3 durable execution loop")
    parser.add_argument("--api-url", default="http://127.0.0.1:8080")
    parser.add_argument("--runtime-root", type=Path, default=Path(r"D:\MiniOGAS-VMs"))
    args = parser.parse_args()
    try:
        result = run_gate(args.api_url, args.runtime_root)
    except GateFailure as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
