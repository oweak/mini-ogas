# Identity, Time And Error Standard

## Identity

New externally visible request IDs use `req_<32 lowercase hexadecimal characters>` and are generated with UUIDv4 entropy. A valid upstream `X-Request-ID` is accepted only when it matches a bounded safe character set; otherwise the API replaces it. The same value is emitted in the response header, structured error body and request log.

Transport message IDs remain deterministic UUIDv5 values over canonical payload content. This supports idempotent NATS redelivery and Outbox reconciliation. Existing numeric command, audit and legacy event IDs remain compatibility identifiers; they must not be silently reinterpreted as globally unique IDs. Their transport identity is the envelope `message_id`.

The canonical helper for new random resource IDs is `core.identity.new_id(prefix)`. Prefixes are lowercase bounded tokens. Later domain migrations may preserve a legacy ID as an alternate key while adding a canonical ID.

## Time

- Persisted and externally visible new timestamps are timezone-aware UTC.
- API problem timestamps use RFC 3339 UTC with a `Z` suffix and millisecond precision.
- NATS envelopes carry both `occurred_at` and `published_at`.
- Simulation time is never substituted for wall-clock time; both remain separate runtime fields.
- Naive input timestamps are treated as UTC only at a declared compatibility boundary. New code must not create naive timestamps.
- Database production timestamps use PostgreSQL `TIMESTAMPTZ`; SQLite remains an explicit local/test fallback.

## Error Contract

All framework, authentication, validation and unhandled API errors use `application/problem+json` with:

| Field | Meaning |
|---|---|
| `type` | Stable Mini-OGAS URN |
| `title` | HTTP error class |
| `status` | HTTP status code |
| `code` | Stable machine-readable code |
| `detail` | Legacy-compatible human or structured detail |
| `instance` | Request path |
| `request_id` | Correlation identifier |
| `timestamp` | UTC response time |

Production, pilot, staging, digital-twin and test modes hide unhandled exception details. Only explicit `development` mode may expose the exception string. Secrets must never be placed in an exception message intentionally.
