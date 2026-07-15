# Phase 7 Data Platform Contract

## Boundary

This contract applies to the local engineering data platform. PostgreSQL business
tables remain authoritative for accepted MOM transactions. Telemetry, Redis keys, and
object bytes cannot mutate those facts without a later governed interpreter or
application command.

## Telemetry Signal Definition

Required fields:

| Field | Rule |
|---|---|
| `signal_code` | Stable scoped code; never a display label |
| `display_name` | Operator-facing name |
| `value_type` | `number`, `integer`, `boolean`, or `text` |
| `unit` | Canonical engineering unit; empty only for dimensionless/text |
| `minimum` / `maximum` | Optional numeric inclusive range |
| `freshness_threshold_ms` | Positive threshold used for stale/missing decisions |
| `allowed_sources` | Non-empty subset of `simulated`, `replay`, `shadow`, `live`, `manual` |
| `mapping_version` | Positive version; mismatch is bad quality |

Definitions are governed PostgreSQL facts. Updating policy creates a new mapping
version; it never rewrites prior samples.

## Telemetry Batch

`POST /telemetry/batches` accepts a strict batch:

```json
{
  "batch_id": "01J...",
  "source": "simulated",
  "source_id": "turning-workshop-01",
  "equipment_code": "LATHE-01",
  "edge_received_at": "2026-07-14T06:30:00Z",
  "samples": [
    {
      "sample_id": "01J...",
      "signal_code": "spindle_temperature",
      "value": 61.5,
      "unit": "Cel",
      "mapping_version": 1,
      "sequence_no": 501,
      "source_timestamp": "2026-07-14T06:29:59.950Z",
      "simulation_time": "2026-07-14T06:29:59.950Z"
    }
  ]
}
```

Tenant, site, central ingest time, processed time, and actor are server-derived. Node
credentials cannot submit `manual`, corrected, or physical `live` measurements.

The response contains counts by quality, duplicate count, Historian checkpoint, and
Redis projection status. HTTP success means the immutable PostgreSQL batch committed;
it does not mean the signal is good or a business action occurred.

## Quality Codes

| Quality | Meaning | Projection behavior |
|---|---|---|
| `good` | Contract, range, mapping, order, and freshness checks pass | Current observed and usable projection |
| `uncertain` | Accepted evidence is stale or otherwise usable only with warning | Current observed projection, visibly uncertain |
| `bad` | Unit, mapping, range, sequence, timestamp, or source contract failed | Visible observed/quality evidence; never usable for business interpretation |

Machine-readable reasons include `stale`, `future_timestamp`, `unit_mismatch`,
`range_violation`, `mapping_version_mismatch`, `out_of_order`, `sequence_conflict`,
`source_not_allowed`, and `missing`.

## Query And Retention

- `GET /telemetry/latest` returns one latest observed sample per
  `source_id`/active-definition stream. A definition that has never been observed is
  retained as an explicit missing entry instead of hiding the catalog gap.
- `GET /telemetry/measurements` requires a bounded time range and limit.
- `GET /telemetry/quality/summary` exposes counts, lag, source, and reasons for
  configured production sources. Auxiliary validation streams remain queryable from
  `/telemetry/latest` but are excluded from operator quality counts and reported by
  `excluded_auxiliary_streams`.
- `POST /telemetry/aggregations/hourly` materializes deterministic hourly aggregates.
- `POST /telemetry/retention/run` deletes eligible raw partitions/rows only after
  aggregate coverage and records a retention run.

Initial engineering policy keeps 7 days raw and 90 days hourly aggregates. These are
configuration facts, not hard-coded business facts.

## Redis Projection

Key namespace:

```text
miniogas:{tenant_id}:{site_id}:telemetry:{generation}:latest:{source_id}:{signal_code}
miniogas:{tenant_id}:{site_id}:telemetry:active_generation
```

`POST /telemetry/projection/rebuild` creates a new generation from PostgreSQL,
verifies expected key count and max measurement ID, atomically swaps the active
generation pointer, and records a PostgreSQL checkpoint. `GET
/telemetry/projection/status` reports provider, availability, active generation,
checkpoint, row/key counts, and lag without credentials.

## Document Object Contract

`PUT /document-objects/{object_name}` accepts raw bytes with:

- `Content-Type`;
- `X-Content-SHA256` containing lowercase SHA-256 hex;
- optional original filename header.

The server computes SHA-256 before upload, rejects mismatch, stores to the
content-addressed key, reads it back, and finalizes the PostgreSQL manifest only after
checksum and length match. `GET /document-objects/{object_id}` verifies the checksum
again before returning bytes.

Every `document_revisions` row has immutable `content_sha256` and `content_length`.
An object-backed revision additionally references exactly one available object
manifest. Existing inline revisions are migrated with a checksum of their canonical
stored `content_json` bytes.

## Non-Claims

This contract does not prove a physical sensor, PLC/CNC source, calibrated device,
plant Historian, production Redis cluster, object-store HA, backup restore, or
industrial load. Those claims require later connector, deployment, and pilot gates.
