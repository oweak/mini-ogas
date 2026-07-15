from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CENTRAL_API_ROOT = PROJECT_ROOT / "services" / "central-api"
OUTPUTS = {
    "openapi": PROJECT_ROOT / "contracts" / "openapi" / "mini-ogas-openapi-v1.json",
    "asyncapi": PROJECT_ROOT / "contracts" / "asyncapi" / "mini-ogas-shadow-v3.json",
    "events": PROJECT_ROOT / "contracts" / "events" / "transport-envelope-v3.schema.json",
}
MANIFEST = PROJECT_ROOT / "contracts" / "manifest.json"


def _configure_safe_export_environment() -> None:
    values = {
        "APP_ENV": "test",
        "DATA_SOURCE": "simulated",
        "CONTROL_MODE": "read_only",
        "DEMO_SEED_ENABLED": "false",
        "TENANT_ID": "tenant-contract",
        "SITE_ID": "site-contract",
        "PERSIST_ENABLED": "false",
        "PERSIST_BACKEND": "sqlite",
        "MICROSERVICES_ENABLED": "false",
        "NATS_ENABLED": "false",
        "AI_ENABLED": "false",
        "ALLOW_LEGACY_API_TOKEN_AUTH": "false",
        "JWT_SECRET": "contract-export-only-jwt-secret",
        "NODE_INGEST_TOKEN": "contract-export-only-node-token",
        "AUTH_BOOTSTRAP_PASSWORD": "contract-export-only-password",
    }
    os.environ.update(values)


def _rewrite_schema_refs(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                item.replace("#/$defs/", "#/components/schemas/")
                if key == "$ref" and isinstance(item, str)
                else _rewrite_schema_refs(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_rewrite_schema_refs(item) for item in value]
    return value


def _asyncapi_document(transport_schema: dict[str, Any]) -> dict[str, Any]:
    definitions = transport_schema.pop("$defs", {})
    transport_schema = _rewrite_schema_refs(transport_schema)
    schemas = {
        name: _rewrite_schema_refs(schema)
        for name, schema in sorted(definitions.items())
    }
    schemas["TransportEnvelope"] = transport_schema

    def message(name: str, message_type: str, status: str) -> dict[str, Any]:
        return {
            "name": name,
            "title": f"Mini-OGAS {message_type} envelope",
            "x-mini-ogas-implementation-status": status,
            "payload": {
                "allOf": [
                    {"$ref": "#/components/schemas/TransportEnvelope"},
                    {
                        "type": "object",
                        "properties": {"message_type": {"const": message_type}},
                        "required": ["message_type"],
                    },
                ]
            },
        }

    return {
        "asyncapi": "3.0.0",
        "info": {
            "title": "Mini-OGAS NATS shadow contract",
            "version": "3.0.0",
            "description": (
                "Contract for the current loopback NATS shadow path. Heartbeat publish and "
                "projection are wired; event, command and audit envelopes are defined but "
                "are not yet connected to all business transactions."
            ),
        },
        "defaultContentType": "application/json",
        "servers": {
            "localShadow": {
                "host": "127.0.0.1:4222",
                "protocol": "nats",
                "description": "Current loopback-only development broker",
            }
        },
        "channels": {
            "heartbeats": {
                "address": "ogas.heartbeats.{node_code}",
                "parameters": {
                    "node_code": {"description": "Validated edge node code"},
                },
                "messages": {"heartbeat": {"$ref": "#/components/messages/Heartbeat"}},
            },
            "events": {
                "address": "ogas.events.{event_type}.{node_code}",
                "parameters": {
                    "event_type": {"description": "Validated domain event token"},
                    "node_code": {"description": "Validated source node code"},
                },
                "messages": {"event": {"$ref": "#/components/messages/Event"}},
            },
            "commands": {
                "address": "ogas.commands.{node_code}",
                "parameters": {
                    "node_code": {"description": "Validated target node code"},
                },
                "messages": {"command": {"$ref": "#/components/messages/Command"}},
            },
            "audit": {
                "address": "ogas.audit.{resource_type}",
                "parameters": {
                    "resource_type": {"description": "Validated audited resource token"},
                },
                "messages": {"audit": {"$ref": "#/components/messages/Audit"}},
            },
        },
        "operations": {
            "publishHeartbeat": {
                "action": "send",
                "channel": {"$ref": "#/channels/heartbeats"},
                "summary": "Central API publishes a transactionally recorded heartbeat envelope",
            },
            "projectHeartbeat": {
                "action": "receive",
                "channel": {"$ref": "#/channels/heartbeats"},
                "summary": "The current in-process projection worker consumes and persists receipts",
            },
        },
        "components": {
            "messages": {
                "Heartbeat": message("Heartbeat", "heartbeat", "wired-shadow"),
                "Event": message("Event", "event", "contract-defined-not-transactionally-wired"),
                "Command": message("Command", "command", "contract-defined-not-transactionally-wired"),
                "Audit": message("Audit", "audit", "contract-defined-not-transactionally-wired"),
            },
            "schemas": schemas,
        },
        "x-mini-ogas-boundary": {
            "dataSource": "shadow",
            "physicalDeviceWrite": False,
            "productionClaim": False,
        },
    }


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def build_outputs() -> dict[Path, bytes]:
    _configure_safe_export_environment()
    sys.path.insert(0, str(CENTRAL_API_ROOT))
    from app.core.nats_contracts import TransportEnvelope
    from app.main import app

    event_schema = TransportEnvelope.model_json_schema(mode="validation")
    payloads = {
        OUTPUTS["openapi"]: _json_bytes(app.openapi()),
        OUTPUTS["events"]: _json_bytes(event_schema),
        OUTPUTS["asyncapi"]: _json_bytes(_asyncapi_document(dict(event_schema))),
    }
    manifest = {
        "contract_set": "mini-ogas-phase1",
        "generator": "tools/export_contracts.py",
        "files": {
            path.relative_to(PROJECT_ROOT).as_posix(): hashlib.sha256(content).hexdigest()
            for path, content in sorted(payloads.items(), key=lambda item: str(item[0]))
        },
    }
    payloads[MANIFEST] = _json_bytes(manifest)
    return payloads


def main() -> int:
    parser = argparse.ArgumentParser(description="Export deterministic Mini-OGAS interface contracts")
    parser.add_argument("--check", action="store_true", help="fail when committed contracts are stale")
    args = parser.parse_args()
    payloads = build_outputs()

    stale = []
    for path, content in payloads.items():
        if args.check:
            if not path.exists() or path.read_bytes() != content:
                stale.append(path.relative_to(PROJECT_ROOT).as_posix())
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    if stale:
        print("stale contracts: " + ", ".join(stale), file=sys.stderr)
        return 1
    print("contract check passed" if args.check else "contracts exported")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
