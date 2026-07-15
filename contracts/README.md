# Mini-OGAS Contract Set

This directory contains generated, executable Phase 1 contracts. It is not a declaration that every defined message is wired to industrial equipment.

## Files

- `openapi/mini-ogas-openapi-v1.json`: current FastAPI routes generated from the running application model.
- `asyncapi/mini-ogas-shadow-v3.json`: current loopback NATS shadow subjects and message status.
- `events/transport-envelope-v3.schema.json`: Pydantic-derived transport envelope JSON Schema.
- `manifest.json`: SHA-256 checksums for generated artifacts.

Heartbeat publication and projection are wired to the present REST-to-NATS-to-PostgreSQL shadow path. Event, command, and audit message definitions are explicitly marked `contract-defined-not-transactionally-wired` until their business transactions use the Outbox.

Regenerate with:

```powershell
python .\tools\export_contracts.py
```

Verify without modifying files:

```powershell
python .\tools\export_contracts.py --check
```

The verification suite fails when generated artifacts drift from code.
