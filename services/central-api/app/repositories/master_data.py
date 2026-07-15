from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from ..core.config import settings
from ..core.database import get_db
from ..core.nats_contracts import build_audit_envelope
from ..core.outbox import outbox_repository
from ..domain.data_platform import DataPlatformError
from ..domain.master_data import (
    BomIn,
    BomRevisionIn,
    CalendarIn,
    DocumentIn,
    DocumentRevisionIn,
    EquipmentCapabilityIn,
    EquipmentIn,
    MasterDataError,
    MaterialIn,
    OrganizationUnitIn,
    PersonnelIn,
    ProductIn,
    QualificationIn,
    RoutingIn,
    RoutingRevisionIn,
    ShiftIn,
    SkillIn,
    UomIn,
    WorkOrderIn,
)
from .data_platform import data_platform_repository


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode_json(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row)


def _database_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class MasterDataRepository:
    def _scope(self) -> tuple[str, str]:
        return settings.tenant_id, settings.site_id

    def _require_by_code(
        self,
        db: Any,
        table: str,
        code_column: str,
        code: str,
        resource: str,
    ) -> dict[str, Any]:
        row = db.execute(
            f"SELECT * FROM {table} "
            f"WHERE tenant_id=? AND site_id=? AND {code_column}=?",
            (*self._scope(), code),
        ).fetchone()
        if row is None:
            raise MasterDataError(
                409,
                "REFERENCE_NOT_FOUND",
                f"referenced {resource} does not exist in the active tenant/site",
                resource_type=resource,
                resource_code=code,
            )
        return _row_dict(row)

    def _require_by_id(
        self,
        db: Any,
        table: str,
        identifier: int,
        resource: str,
    ) -> dict[str, Any]:
        row = db.execute(
            f"SELECT * FROM {table} WHERE tenant_id=? AND site_id=? AND id=?",
            (*self._scope(), identifier),
        ).fetchone()
        if row is None:
            raise MasterDataError(
                409,
                "REFERENCE_NOT_FOUND",
                f"referenced {resource} does not exist in the active tenant/site",
                resource_type=resource,
                resource_id=identifier,
            )
        return _row_dict(row)

    def _insert_id(
        self,
        db: Any,
        sql: str,
        params: tuple[Any, ...],
        resource: str,
        resource_code: str,
    ) -> int:
        try:
            row = db.execute(f"{sql} RETURNING id", params).fetchone()
        except Exception as exc:
            message = str(exc).lower()
            if any(token in message for token in ("unique", "duplicate", "constraint failed")):
                raise MasterDataError(
                    409,
                    "DUPLICATE_MASTER_DATA",
                    f"{resource} already exists",
                    resource_type=resource,
                    resource_code=resource_code,
                ) from exc
            raise
        if row is None:
            raise RuntimeError(f"database did not return an id for {resource}")
        data = _row_dict(row) if hasattr(row, "keys") else {"id": row[0]}
        return int(data["id"])

    def _audit(
        self,
        db: Any,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str,
        detail: dict[str, Any],
    ) -> None:
        created_at = datetime.now(UTC).isoformat()
        row = db.execute(
            """INSERT INTO audit_logs (
                   tenant_id, site_id, run_id, actor, action, resource_type,
                   resource_id, result, detail, created_at
               ) VALUES (?, ?, 'master-data', ?, ?, ?, ?, 'success', ?, ?)
               RETURNING id""",
            (
                *self._scope(),
                actor,
                action,
                resource_type,
                resource_id,
                _canonical_json(detail),
                created_at,
            ),
        ).fetchone()
        audit_id = int(_row_dict(row)["id"] if hasattr(row, "keys") else row[0])
        envelope = build_audit_envelope(
            {
                "id": audit_id,
                "run_id": "master-data",
                "actor": actor,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "result": "success",
                "detail": _canonical_json(detail),
                "created_at": created_at,
            },
            run_id="master-data",
        )
        if not outbox_repository.enqueue_in_transaction(db, envelope):
            raise RuntimeError("failed to enqueue the master-data audit envelope")

    def _created_response(self, db: Any, table: str, identifier: int) -> dict[str, Any]:
        return self._require_by_id(db, table, identifier, table)

    def create_organization_unit(
        self, payload: OrganizationUnitIn, actor: str
    ) -> dict[str, Any]:
        expected_parent = {
            "enterprise": None,
            "site": "enterprise",
            "area": "site",
            "line": "area",
            "cell": "line",
        }
        with get_db() as db:
            parent_id: int | None = None
            required_type = expected_parent[payload.unit_type]
            if required_type is None:
                if payload.parent_code is not None:
                    raise MasterDataError(
                        409,
                        "INVALID_ORGANIZATION_HIERARCHY",
                        "enterprise units cannot have a parent",
                    )
            else:
                if payload.parent_code is None:
                    raise MasterDataError(
                        409,
                        "INVALID_ORGANIZATION_HIERARCHY",
                        f"{payload.unit_type} units require a {required_type} parent",
                    )
                parent = self._require_by_code(
                    db,
                    "organization_units",
                    "unit_code",
                    payload.parent_code,
                    "organization_unit",
                )
                if parent["unit_type"] != required_type:
                    raise MasterDataError(
                        409,
                        "INVALID_ORGANIZATION_HIERARCHY",
                        f"{payload.unit_type} parent must be {required_type}",
                        parent_code=payload.parent_code,
                        parent_type=parent["unit_type"],
                    )
                parent_id = int(parent["id"])
            identifier = self._insert_id(
                db,
                """INSERT INTO organization_units (
                       tenant_id, site_id, unit_code, name, unit_type, parent_id, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (*self._scope(), payload.unit_code, payload.name, payload.unit_type, parent_id, actor),
                "organization_unit",
                payload.unit_code,
            )
            self._audit(
                db,
                actor,
                "master-data:organization-unit-created",
                "organization_unit",
                payload.unit_code,
                payload.model_dump(mode="json"),
            )
            result = self._created_response(db, "organization_units", identifier)
            result["parent_code"] = payload.parent_code
            return result

    def create_uom(self, payload: UomIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            identifier = self._insert_id(
                db,
                """INSERT INTO uoms (
                       tenant_id, site_id, uom_code, name, dimension, scale, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (*self._scope(), payload.uom_code, payload.name, payload.dimension, payload.scale, actor),
                "uom",
                payload.uom_code,
            )
            self._audit(db, actor, "master-data:uom-created", "uom", payload.uom_code, payload.model_dump())
            return self._created_response(db, "uoms", identifier)

    def create_material(self, payload: MaterialIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            uom = self._require_by_code(db, "uoms", "uom_code", payload.base_uom_code, "uom")
            identifier = self._insert_id(
                db,
                """INSERT INTO materials (
                       tenant_id, site_id, material_code, name, material_type, base_uom_id, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.material_code,
                    payload.name,
                    payload.material_type,
                    int(uom["id"]),
                    actor,
                ),
                "material",
                payload.material_code,
            )
            self._audit(
                db, actor, "master-data:material-created", "material", payload.material_code, payload.model_dump()
            )
            result = self._created_response(db, "materials", identifier)
            result["base_uom_code"] = payload.base_uom_code
            return result

    def create_product(self, payload: ProductIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            material = self._require_by_code(
                db, "materials", "material_code", payload.material_code, "material"
            )
            if material["material_type"] != "finished":
                raise MasterDataError(
                    409,
                    "INVALID_PRODUCT_MATERIAL",
                    "a product must reference a finished material",
                    material_code=payload.material_code,
                )
            identifier = self._insert_id(
                db,
                """INSERT INTO products (
                       tenant_id, site_id, product_code, name, material_id, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (*self._scope(), payload.product_code, payload.name, int(material["id"]), actor),
                "product",
                payload.product_code,
            )
            self._audit(
                db, actor, "master-data:product-created", "product", payload.product_code, payload.model_dump()
            )
            result = self._created_response(db, "products", identifier)
            result["material_code"] = payload.material_code
            return result

    def create_equipment(self, payload: EquipmentIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            unit = self._require_by_code(
                db,
                "organization_units",
                "unit_code",
                payload.organization_unit_code,
                "organization_unit",
            )
            if unit["unit_type"] != "cell":
                raise MasterDataError(
                    409,
                    "INVALID_EQUIPMENT_LOCATION",
                    "equipment must belong to a cell organization unit",
                    organization_unit_code=payload.organization_unit_code,
                )
            identifier = self._insert_id(
                db,
                """INSERT INTO equipment (
                       tenant_id, site_id, equipment_code, name, equipment_type,
                       organization_unit_id, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.equipment_code,
                    payload.name,
                    payload.equipment_type,
                    int(unit["id"]),
                    actor,
                ),
                "equipment",
                payload.equipment_code,
            )
            self._audit(
                db, actor, "master-data:equipment-created", "equipment", payload.equipment_code, payload.model_dump()
            )
            result = self._created_response(db, "equipment", identifier)
            result["organization_unit_code"] = payload.organization_unit_code
            return result

    def create_equipment_capability(
        self, equipment_code: str, payload: EquipmentCapabilityIn, actor: str
    ) -> dict[str, Any]:
        with get_db() as db:
            equipment = self._require_by_code(
                db, "equipment", "equipment_code", equipment_code, "equipment"
            )
            identifier = self._insert_id(
                db,
                """INSERT INTO equipment_capabilities (
                       tenant_id, site_id, equipment_id, capability_code, name, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    int(equipment["id"]),
                    payload.capability_code,
                    payload.name,
                    actor,
                ),
                "equipment_capability",
                f"{equipment_code}:{payload.capability_code}",
            )
            detail = {**payload.model_dump(), "equipment_code": equipment_code}
            self._audit(
                db,
                actor,
                "master-data:equipment-capability-created",
                "equipment_capability",
                f"{equipment_code}:{payload.capability_code}",
                detail,
            )
            result = self._created_response(db, "equipment_capabilities", identifier)
            result["equipment_code"] = equipment_code
            return result

    def create_skill(self, payload: SkillIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            identifier = self._insert_id(
                db,
                """INSERT INTO skills (
                       tenant_id, site_id, skill_code, name, level_min, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (*self._scope(), payload.skill_code, payload.name, payload.level_min, actor),
                "skill",
                payload.skill_code,
            )
            self._audit(db, actor, "master-data:skill-created", "skill", payload.skill_code, payload.model_dump())
            return self._created_response(db, "skills", identifier)

    def create_personnel(self, payload: PersonnelIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            if payload.linked_username:
                user = db.execute(
                    """SELECT username, active FROM users
                       WHERE tenant_id=? AND site_id=? AND username=?""",
                    (*self._scope(), payload.linked_username),
                ).fetchone()
                if user is None or not bool(_row_dict(user)["active"]):
                    raise MasterDataError(
                        409,
                        "ACCOUNT_NOT_FOUND",
                        "linked account does not exist or is inactive",
                        linked_username=payload.linked_username,
                    )
            identifier = self._insert_id(
                db,
                """INSERT INTO personnel (
                       tenant_id, site_id, personnel_code, display_name, linked_username, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.personnel_code,
                    payload.display_name,
                    payload.linked_username,
                    actor,
                ),
                "personnel",
                payload.personnel_code,
            )
            self._audit(
                db, actor, "master-data:personnel-created", "personnel", payload.personnel_code, payload.model_dump()
            )
            return self._created_response(db, "personnel", identifier)

    def create_qualification(self, payload: QualificationIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            personnel = self._require_by_code(
                db, "personnel", "personnel_code", payload.personnel_code, "personnel"
            )
            skill = self._require_by_code(db, "skills", "skill_code", payload.skill_code, "skill")
            if payload.level < int(skill["level_min"]):
                raise MasterDataError(
                    409,
                    "QUALIFICATION_LEVEL_INVALID",
                    "qualification level is below the skill minimum",
                    skill_code=payload.skill_code,
                    level_min=int(skill["level_min"]),
                )
            identifier = self._insert_id(
                db,
                """INSERT INTO personnel_qualifications (
                       tenant_id, site_id, personnel_id, skill_id, level, valid_from,
                       valid_to, evidence_reference, issued_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    int(personnel["id"]),
                    int(skill["id"]),
                    payload.level,
                    payload.valid_from.isoformat(),
                    payload.valid_to.isoformat(),
                    payload.evidence_reference,
                    actor,
                ),
                "personnel_qualification",
                f"{payload.personnel_code}:{payload.skill_code}:{payload.valid_from.isoformat()}",
            )
            detail = payload.model_dump(mode="json")
            self._audit(
                db,
                actor,
                "master-data:qualification-issued",
                "personnel_qualification",
                str(identifier),
                detail,
            )
            result = self._created_response(db, "personnel_qualifications", identifier)
            result.update(
                personnel_code=payload.personnel_code,
                skill_code=payload.skill_code,
            )
            return result

    def create_calendar(self, payload: CalendarIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            identifier = self._insert_id(
                db,
                """INSERT INTO calendars (
                       tenant_id, site_id, calendar_code, name, timezone, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (*self._scope(), payload.calendar_code, payload.name, payload.timezone, actor),
                "calendar",
                payload.calendar_code,
            )
            self._audit(
                db, actor, "master-data:calendar-created", "calendar", payload.calendar_code, payload.model_dump()
            )
            return self._created_response(db, "calendars", identifier)

    def create_shift(
        self, calendar_code: str, payload: ShiftIn, actor: str
    ) -> dict[str, Any]:
        with get_db() as db:
            calendar = self._require_by_code(
                db, "calendars", "calendar_code", calendar_code, "calendar"
            )
            identifier = self._insert_id(
                db,
                """INSERT INTO calendar_shifts (
                       tenant_id, site_id, calendar_id, shift_code, name,
                       start_time, end_time, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    int(calendar["id"]),
                    payload.shift_code,
                    payload.name,
                    payload.start_time,
                    payload.end_time,
                    actor,
                ),
                "calendar_shift",
                f"{calendar_code}:{payload.shift_code}",
            )
            detail = {**payload.model_dump(), "calendar_code": calendar_code}
            self._audit(
                db,
                actor,
                "master-data:calendar-shift-created",
                "calendar_shift",
                f"{calendar_code}:{payload.shift_code}",
                detail,
            )
            result = self._created_response(db, "calendar_shifts", identifier)
            result["calendar_code"] = calendar_code
            return result

    def create_document(self, payload: DocumentIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            identifier = self._insert_id(
                db,
                """INSERT INTO controlled_documents (
                       tenant_id, site_id, document_code, title, document_type, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.document_code,
                    payload.title,
                    payload.document_type,
                    actor,
                ),
                "controlled_document",
                payload.document_code,
            )
            self._audit(
                db,
                actor,
                "master-data:document-created",
                "controlled_document",
                payload.document_code,
                payload.model_dump(),
            )
            return self._created_response(db, "controlled_documents", identifier)

    def create_document_revision(
        self, document_code: str, payload: DocumentRevisionIn, actor: str
    ) -> dict[str, Any]:
        with get_db() as db:
            document = self._require_by_code(
                db,
                "controlled_documents",
                "document_code",
                document_code,
                "controlled_document",
            )
            if payload.content is not None:
                content_json = _canonical_json({"content": payload.content})
                encoded = content_json.encode("utf-8")
                content_sha256 = hashlib.sha256(encoded).hexdigest()
                content_length = len(encoded)
                object_id = None
            else:
                try:
                    stored_object = data_platform_repository.require_available_object(
                        int(payload.object_id or 0)
                    )
                except DataPlatformError as exc:
                    raise MasterDataError(
                        exc.status_code,
                        exc.code,
                        exc.message,
                        **exc.context,
                    ) from exc
                object_id = int(stored_object["id"])
                content_sha256 = str(stored_object["content_sha256"])
                content_length = int(stored_object["byte_length"])
                content_json = _canonical_json(
                    {
                        "object_id": object_id,
                        "content_sha256": content_sha256,
                        "content_length": content_length,
                    }
                )
            identifier = self._insert_id(
                db,
                """INSERT INTO document_revisions (
                       tenant_id, site_id, document_id, revision, content_json,
                       content_sha256, content_length, object_id, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    int(document["id"]),
                    payload.revision,
                    content_json,
                    content_sha256,
                    content_length,
                    object_id,
                    actor,
                ),
                "document_revision",
                f"{document_code}:{payload.revision}",
            )
            self._audit(
                db,
                actor,
                "master-data:revision-created",
                "document_revision",
                str(identifier),
                {
                    "document_code": document_code,
                    "revision": payload.revision,
                    "content_sha256": content_sha256,
                    "content_length": content_length,
                    "object_id": object_id,
                },
            )
            return self._format_revision(
                "document", self._require_by_id(db, "document_revisions", identifier, "document_revision")
            )

    def create_bom(self, payload: BomIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            product = self._require_by_code(
                db, "products", "product_code", payload.product_code, "product"
            )
            identifier = self._insert_id(
                db,
                """INSERT INTO boms (
                       tenant_id, site_id, bom_code, product_id, name, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (*self._scope(), payload.bom_code, int(product["id"]), payload.name, actor),
                "bom",
                payload.bom_code,
            )
            self._audit(db, actor, "master-data:bom-created", "bom", payload.bom_code, payload.model_dump())
            result = self._created_response(db, "boms", identifier)
            result["product_code"] = payload.product_code
            return result

    def create_bom_revision(
        self, bom_code: str, payload: BomRevisionIn, actor: str
    ) -> dict[str, Any]:
        with get_db() as db:
            bom = self._require_by_code(db, "boms", "bom_code", bom_code, "bom")
            items = payload.model_dump(mode="json")["items"]
            for item in items:
                material = self._require_by_code(
                    db, "materials", "material_code", item["material_code"], "material"
                )
                uom = self._require_by_code(db, "uoms", "uom_code", item["uom_code"], "uom")
                base_uom = self._require_by_id(
                    db, "uoms", int(material["base_uom_id"]), "material_base_uom"
                )
                if uom["dimension"] != base_uom["dimension"]:
                    raise MasterDataError(
                        409,
                        "UOM_DIMENSION_MISMATCH",
                        "BOM item UOM dimension does not match the material base UOM",
                        material_code=item["material_code"],
                        uom_code=item["uom_code"],
                    )
            identifier = self._insert_id(
                db,
                """INSERT INTO bom_revisions (
                       tenant_id, site_id, bom_id, revision, content_json, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    int(bom["id"]),
                    payload.revision,
                    _canonical_json({"items": items}),
                    actor,
                ),
                "bom_revision",
                f"{bom_code}:{payload.revision}",
            )
            self._audit(
                db,
                actor,
                "master-data:revision-created",
                "bom_revision",
                str(identifier),
                {"bom_code": bom_code, "revision": payload.revision},
            )
            return self._format_revision(
                "bom", self._require_by_id(db, "bom_revisions", identifier, "bom_revision")
            )

    def create_routing(self, payload: RoutingIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            product = self._require_by_code(
                db, "products", "product_code", payload.product_code, "product"
            )
            identifier = self._insert_id(
                db,
                """INSERT INTO routings (
                       tenant_id, site_id, routing_code, product_id, name, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (*self._scope(), payload.routing_code, int(product["id"]), payload.name, actor),
                "routing",
                payload.routing_code,
            )
            self._audit(
                db, actor, "master-data:routing-created", "routing", payload.routing_code, payload.model_dump()
            )
            result = self._created_response(db, "routings", identifier)
            result["product_code"] = payload.product_code
            return result

    def create_routing_revision(
        self, routing_code: str, payload: RoutingRevisionIn, actor: str
    ) -> dict[str, Any]:
        with get_db() as db:
            routing = self._require_by_code(
                db, "routings", "routing_code", routing_code, "routing"
            )
            operations = payload.model_dump(mode="json")["operations"]
            for operation in operations:
                capability = db.execute(
                    """SELECT id FROM equipment_capabilities
                       WHERE tenant_id=? AND site_id=? AND capability_code=? LIMIT 1""",
                    (*self._scope(), operation["capability_code"]),
                ).fetchone()
                if capability is None:
                    raise MasterDataError(
                        409,
                        "REFERENCE_NOT_FOUND",
                        "routing capability is not provided by any registered equipment",
                        resource_type="equipment_capability",
                        resource_code=operation["capability_code"],
                    )
                skill = self._require_by_code(
                    db, "skills", "skill_code", operation["required_skill_code"], "skill"
                )
                if int(operation["required_skill_level"]) < int(skill["level_min"]):
                    raise MasterDataError(
                        409,
                        "ROUTING_SKILL_LEVEL_INVALID",
                        "routing required skill level is below the skill minimum",
                        skill_code=operation["required_skill_code"],
                    )
                self._require_by_code(
                    db,
                    "controlled_documents",
                    "document_code",
                    operation["document_code"],
                    "controlled_document",
                )
            identifier = self._insert_id(
                db,
                """INSERT INTO routing_revisions (
                       tenant_id, site_id, routing_id, revision, content_json, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    int(routing["id"]),
                    payload.revision,
                    _canonical_json({"operations": operations}),
                    actor,
                ),
                "routing_revision",
                f"{routing_code}:{payload.revision}",
            )
            self._audit(
                db,
                actor,
                "master-data:revision-created",
                "routing_revision",
                str(identifier),
                {"routing_code": routing_code, "revision": payload.revision},
            )
            return self._format_revision(
                "routing",
                self._require_by_id(db, "routing_revisions", identifier, "routing_revision"),
            )

    def _format_revision(self, kind: str, row: dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        content = _decode_json(result.pop("content_json", "{}"), {})
        if kind == "document":
            result["content"] = content.get("content", "")
            if content.get("object_id") is not None:
                result["object_id"] = content["object_id"]
        elif kind == "bom":
            result["items"] = content.get("items", [])
        elif kind == "routing":
            result["operations"] = content.get("operations", [])
        return result

    def transition_revision(
        self, kind: str, revision_id: int, transition: str, actor: str
    ) -> dict[str, Any]:
        definitions = {
            "document": ("document_revisions", "document_id"),
            "bom": ("bom_revisions", "bom_id"),
            "routing": ("routing_revisions", "routing_id"),
        }
        table, parent_column = definitions[kind]
        with get_db() as db:
            revision = self._require_by_id(db, table, revision_id, f"{kind}_revision")
            current_status = str(revision["status"])
            if transition == "approve":
                if current_status == "approved":
                    return self._format_revision(kind, revision)
                if current_status != "draft":
                    raise MasterDataError(
                        409,
                        "INVALID_REVISION_TRANSITION",
                        f"cannot approve a revision in status {current_status}",
                        revision_id=revision_id,
                    )
                db.execute(
                    f"""UPDATE {table}
                        SET status='approved', approved_by=?, approved_at=?
                        WHERE tenant_id=? AND site_id=? AND id=? AND status='draft'""",
                    (actor, datetime.now(UTC).isoformat(), *self._scope(), revision_id),
                )
                action = "master-data:revision-approved"
            elif transition == "effective":
                if current_status == "effective":
                    return self._format_revision(kind, revision)
                if current_status != "approved":
                    raise MasterDataError(
                        409,
                        "INVALID_REVISION_TRANSITION",
                        f"cannot make a revision effective from status {current_status}",
                        revision_id=revision_id,
                    )
                db.execute(
                    f"""UPDATE {table} SET status='superseded'
                        WHERE tenant_id=? AND site_id=? AND {parent_column}=?
                          AND status='effective' AND id!=?""",
                    (*self._scope(), int(revision[parent_column]), revision_id),
                )
                db.execute(
                    f"""UPDATE {table}
                        SET status='effective', effective_by=?, effective_at=?
                        WHERE tenant_id=? AND site_id=? AND id=? AND status='approved'""",
                    (actor, datetime.now(UTC).isoformat(), *self._scope(), revision_id),
                )
                action = "master-data:revision-effective"
            else:
                raise ValueError(f"unsupported revision transition: {transition}")
            self._audit(
                db,
                actor,
                action,
                f"{kind}_revision",
                str(revision_id),
                {"revision_id": revision_id, "transition": transition},
            )
            updated = self._require_by_id(db, table, revision_id, f"{kind}_revision")
            return self._format_revision(kind, updated)

    def list_bom_revisions(self, bom_code: str) -> list[dict[str, Any]]:
        with get_db() as db:
            bom = self._require_by_code(db, "boms", "bom_code", bom_code, "bom")
            rows = db.execute(
                """SELECT * FROM bom_revisions
                   WHERE tenant_id=? AND site_id=? AND bom_id=?
                   ORDER BY revision ASC""",
                (*self._scope(), int(bom["id"])),
            ).fetchall()
            return [self._format_revision("bom", _row_dict(row)) for row in rows]

    def create_work_order(self, payload: WorkOrderIn, actor: str) -> dict[str, Any]:
        with get_db() as db:
            product = self._require_by_code(
                db, "products", "product_code", payload.product_code, "product"
            )
            bom_revision = self._require_by_id(
                db, "bom_revisions", payload.bom_revision_id, "bom_revision"
            )
            routing_revision = self._require_by_id(
                db, "routing_revisions", payload.routing_revision_id, "routing_revision"
            )
            bom = self._require_by_id(db, "boms", int(bom_revision["bom_id"]), "bom")
            routing = self._require_by_id(
                db, "routings", int(routing_revision["routing_id"]), "routing"
            )
            if int(bom["product_id"]) != int(product["id"]) or int(routing["product_id"]) != int(
                product["id"]
            ):
                raise MasterDataError(
                    409,
                    "WORK_ORDER_PRODUCT_MISMATCH",
                    "BOM and routing revisions must belong to the work-order product",
                    product_code=payload.product_code,
                )
            for document_id in payload.document_revision_ids:
                self._require_by_id(db, "document_revisions", document_id, "document_revision")
            calendar = self._require_by_code(
                db, "calendars", "calendar_code", payload.calendar_code, "calendar"
            )
            shift = db.execute(
                """SELECT * FROM calendar_shifts
                   WHERE tenant_id=? AND site_id=? AND calendar_id=? AND shift_code=?""",
                (*self._scope(), int(calendar["id"]), payload.shift_code),
            ).fetchone()
            if shift is None:
                raise MasterDataError(
                    409,
                    "SHIFT_NOT_FOUND",
                    "shift does not belong to the selected calendar",
                    calendar_code=payload.calendar_code,
                    shift_code=payload.shift_code,
                )
            for assignment in payload.operation_assignments:
                self._require_by_code(
                    db, "equipment", "equipment_code", assignment.equipment_code, "equipment"
                )
                self._require_by_code(
                    db, "personnel", "personnel_code", assignment.personnel_code, "personnel"
                )
            identifier = self._insert_id(
                db,
                """INSERT INTO work_orders (
                       tenant_id, site_id, work_order_code, product_id, quantity,
                       bom_revision_id, routing_revision_id, document_revision_ids_json,
                       calendar_id, shift_id, operation_assignments_json, created_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    *self._scope(),
                    payload.work_order_code,
                    int(product["id"]),
                    payload.quantity,
                    payload.bom_revision_id,
                    payload.routing_revision_id,
                    _canonical_json(payload.document_revision_ids),
                    int(calendar["id"]),
                    int(_row_dict(shift)["id"]),
                    _canonical_json(payload.model_dump(mode="json")["operation_assignments"]),
                    actor,
                ),
                "work_order",
                payload.work_order_code,
            )
            self._audit(
                db,
                actor,
                "master-data:work-order-created",
                "work_order",
                payload.work_order_code,
                payload.model_dump(mode="json"),
            )
            return self._format_work_order(db, identifier)

    def _format_work_order(self, db: Any, identifier: int) -> dict[str, Any]:
        row = db.execute(
            """SELECT wo.*, p.product_code, c.calendar_code, s.shift_code
               FROM work_orders wo
               JOIN products p ON p.id=wo.product_id
               JOIN calendars c ON c.id=wo.calendar_id
               JOIN calendar_shifts s ON s.id=wo.shift_id
               WHERE wo.tenant_id=? AND wo.site_id=? AND wo.id=?""",
            (*self._scope(), identifier),
        ).fetchone()
        if row is None:
            raise MasterDataError(404, "WORK_ORDER_NOT_FOUND", "work order was not found")
        result = _row_dict(row)
        result["document_revision_ids"] = _decode_json(
            result.pop("document_revision_ids_json", "[]"), []
        )
        result["operation_assignments"] = _decode_json(
            result.pop("operation_assignments_json", "[]"), []
        )
        return result

    def _require_effective_revision(
        self, row: dict[str, Any], resource: str, identifier: int
    ) -> None:
        if row["status"] != "effective":
            raise MasterDataError(
                409,
                "REVISION_NOT_EFFECTIVE",
                f"bound {resource} revision is not effective",
                resource_type=resource,
                revision_id=identifier,
                status=row["status"],
            )

    def _validate_qualification(
        self,
        db: Any,
        personnel: dict[str, Any],
        skill_code: str,
        required_level: int,
        now: datetime,
    ) -> None:
        rows = db.execute(
            """SELECT q.level, q.valid_from, q.valid_to
               FROM personnel_qualifications q
               JOIN skills s ON s.id=q.skill_id
               WHERE q.tenant_id=? AND q.site_id=? AND q.personnel_id=?
                 AND s.skill_code=? AND q.level>=?""",
            (*self._scope(), int(personnel["id"]), skill_code, required_level),
        ).fetchall()
        qualified = any(
            _database_datetime(_row_dict(row)["valid_from"])
            <= now
            <= _database_datetime(_row_dict(row)["valid_to"])
            for row in rows
        )
        if not qualified:
            raise MasterDataError(
                409,
                "QUALIFICATION_MISSING",
                "assigned personnel lacks a current qualification for the operation",
                personnel_code=personnel["personnel_code"],
                skill_code=skill_code,
                required_level=required_level,
            )

    def release_work_order(self, work_order_code: str, actor: str) -> dict[str, Any]:
        with get_db() as db:
            row = self._require_by_code(
                db, "work_orders", "work_order_code", work_order_code, "work_order"
            )
            if row["status"] == "released":
                return self._format_work_order(db, int(row["id"]))
            if row["status"] != "draft":
                raise MasterDataError(
                    409,
                    "WORK_ORDER_NOT_RELEASABLE",
                    f"work order cannot be released from status {row['status']}",
                    work_order_code=work_order_code,
                )
            bom_revision = self._require_by_id(
                db, "bom_revisions", int(row["bom_revision_id"]), "bom_revision"
            )
            routing_revision = self._require_by_id(
                db, "routing_revisions", int(row["routing_revision_id"]), "routing_revision"
            )
            self._require_effective_revision(
                bom_revision, "bom_revision", int(row["bom_revision_id"])
            )
            self._require_effective_revision(
                routing_revision, "routing_revision", int(row["routing_revision_id"])
            )

            document_ids = _decode_json(row["document_revision_ids_json"], [])
            selected_documents: dict[str, dict[str, Any]] = {}
            for document_id in document_ids:
                revision_row = db.execute(
                    """SELECT dr.*, d.document_code
                       FROM document_revisions dr
                       JOIN controlled_documents d ON d.id=dr.document_id
                       WHERE dr.tenant_id=? AND dr.site_id=? AND dr.id=?""",
                    (*self._scope(), int(document_id)),
                ).fetchone()
                if revision_row is None:
                    raise MasterDataError(
                        409,
                        "REFERENCE_NOT_FOUND",
                        "bound document revision does not exist",
                        revision_id=document_id,
                    )
                document = _row_dict(revision_row)
                self._require_effective_revision(document, "document_revision", int(document_id))
                selected_documents[str(document["document_code"])] = document

            routing_content = _decode_json(routing_revision["content_json"], {})
            operations = routing_content.get("operations", [])
            assignments = _decode_json(row["operation_assignments_json"], [])
            assignment_by_sequence = {
                int(assignment["sequence"]): assignment for assignment in assignments
            }
            required_sequences = {int(operation["sequence"]) for operation in operations}
            if required_sequences != set(assignment_by_sequence):
                raise MasterDataError(
                    409,
                    "OPERATION_ASSIGNMENT_INCOMPLETE",
                    "operation assignments must exactly cover the bound routing revision",
                    required_sequences=sorted(required_sequences),
                    assigned_sequences=sorted(assignment_by_sequence),
                )

            now = datetime.now(UTC)
            for operation in operations:
                sequence = int(operation["sequence"])
                assignment = assignment_by_sequence[sequence]
                equipment = self._require_by_code(
                    db,
                    "equipment",
                    "equipment_code",
                    str(assignment["equipment_code"]),
                    "equipment",
                )
                if not bool(equipment["active"]):
                    raise MasterDataError(
                        409,
                        "EQUIPMENT_INACTIVE",
                        "assigned equipment is inactive",
                        equipment_code=equipment["equipment_code"],
                    )
                capability = db.execute(
                    """SELECT id FROM equipment_capabilities
                       WHERE tenant_id=? AND site_id=? AND equipment_id=? AND capability_code=?""",
                    (
                        *self._scope(),
                        int(equipment["id"]),
                        str(operation["capability_code"]),
                    ),
                ).fetchone()
                if capability is None:
                    raise MasterDataError(
                        409,
                        "EQUIPMENT_CAPABILITY_MISSING",
                        "assigned equipment lacks the routing-required capability",
                        equipment_code=equipment["equipment_code"],
                        capability_code=operation["capability_code"],
                    )
                personnel = self._require_by_code(
                    db,
                    "personnel",
                    "personnel_code",
                    str(assignment["personnel_code"]),
                    "personnel",
                )
                if not bool(personnel["active"]):
                    raise MasterDataError(
                        409,
                        "PERSONNEL_INACTIVE",
                        "assigned personnel is inactive",
                        personnel_code=personnel["personnel_code"],
                    )
                self._validate_qualification(
                    db,
                    personnel,
                    str(operation["required_skill_code"]),
                    int(operation["required_skill_level"]),
                    now,
                )
                required_document = str(operation["document_code"])
                if required_document not in selected_documents:
                    raise MasterDataError(
                        409,
                        "REQUIRED_DOCUMENT_MISSING",
                        "work order does not bind the routing-required effective document",
                        document_code=required_document,
                        operation_sequence=sequence,
                    )

            updated = db.execute(
                """UPDATE work_orders
                   SET status='released', released_by=?, released_at=?
                   WHERE tenant_id=? AND site_id=? AND id=? AND status='draft'""",
                (actor, now.isoformat(), *self._scope(), int(row["id"])),
            )
            if int(getattr(updated, "rowcount", 0) or 0) != 1:
                raise MasterDataError(
                    409,
                    "WORK_ORDER_RELEASE_CONFLICT",
                    "work order changed while release validation was in progress",
                    work_order_code=work_order_code,
                )
            self._audit(
                db,
                actor,
                "master-data:work-order-released",
                "work_order",
                work_order_code,
                {
                    "bom_revision_id": int(row["bom_revision_id"]),
                    "routing_revision_id": int(row["routing_revision_id"]),
                    "document_revision_ids": document_ids,
                    "operation_assignments": assignments,
                },
            )
            return self._format_work_order(db, int(row["id"]))


master_data_repository = MasterDataRepository()
