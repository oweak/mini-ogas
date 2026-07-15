# Interface Contract Governance

## Scope

Phase 1 establishes contracts for interfaces that exist now. It does not use a schema to imply a connector, device write, autonomous AI action or completed message workflow.

## OpenAPI

`contracts/openapi/mini-ogas-openapi-v1.json` is generated from the FastAPI application. Compatibility routes remain visible. Duplicate operation IDs are forbidden; the legacy `/ai-diagnoses` route and canonical `/ai/diagnoses` route have separate identifiers.

## AsyncAPI

`contracts/asyncapi/mini-ogas-shadow-v3.json` documents four existing envelope types and NATS subjects:

| Message | Subject | Implementation status |
|---|---|---|
| Heartbeat | `ogas.heartbeats.{node_code}` | REST ingestion, transactional Outbox, publish and projection wired in shadow mode |
| Event | `ogas.events.{event_type}.{node_code}` | Schema/publisher defined; not transactionally wired to every event mutation |
| Command | `ogas.commands.{node_code}` | Schema/publisher defined; not transactionally wired to command creation |
| Audit | `ogas.audit.{resource_type}` | Schema/publisher defined; not transactionally wired to audit creation |

Only heartbeat send/receive operations are declared in AsyncAPI operations. The other channels carry an explicit non-wired extension marker. This is deliberate evidence against interface-shell inflation.

## Compatibility And Drift

`tools/export_contracts.py` runs in a network-disabled, persistence-disabled test configuration. It writes deterministic JSON and a SHA-256 manifest. `python tools/export_contracts.py --check` is part of `verify-miniogas.ps1` and tests. A route/model change must regenerate the artifacts and pass existing endpoint tests.

Breaking contract changes require a new schema or API version and a recorded compatibility plan. Renaming a subject, removing a field, tightening an enum or changing units is breaking unless an adapter and observation period are provided.
