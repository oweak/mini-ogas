# Stage G Unified AI Plane Evidence

Date: 2026-07-16

## Gate Scope

Stage G makes AI Dispatcher the sole model-call owner and turns AI output into
advice with explicit provenance. It standardizes provider policy, retry and timeout
budgets, token ceilings, deterministic fallback, cost records, latency, error
classification, redaction and egress policy. High-risk advice must enter the same
human command-approval boundary as other sensitive operations.

This gate does not grant an AI principal direct node-control authority and does not
accept the Stage H market-to-audit production loop.

## Single Model-Call Owner

- Provider implementations, cloud/local model URLs, provider keys, chain ordering,
  retries and fallbacks now exist only in `services/ai-dispatcher`.
- Central API uses `DispatcherClient` for inference, diagnosis, status, vault unlock
  and connectivity probes; the former Central provider registry and runtime were
  removed.
- A production-source architecture test rejects provider endpoint strings, provider
  environment keys and `ProviderRegistry` under the Central application package.
- Supervisor, Compose and launch scripts inject provider settings only into AI
  Dispatcher. Central receives only its internal Dispatcher URL and service token.

## Unified Runtime Contract

Every inference response includes:

- request/correlation/task identity;
- provider, model and `provider_model`;
- live API or deterministic fallback source;
- total latency, timeout budget and effective token ceiling;
- ordered attempts with latency, status, error class and error code;
- provider token usage and configurable estimated USD cost, or an explicit
  unconfigured cost record;
- redaction count/categories and the approved egress origin.

The runtime enforces one overall deadline, one per-provider timeout, bounded retry
count and exponential delay, and a Dispatcher-owned maximum token limit. Error
classes distinguish configuration, policy denial, authentication, rate limiting,
transport, timeout, upstream, invalid response and internal failure.

## Data and Secret Boundary

- Message payloads are recursively redacted for sensitive field names, bearer tokens
  and API-key patterns before a provider call.
- Provider URLs are reduced to origins and denied unless present in
  `AI_EGRESS_ALLOWLIST`; credentials embedded in URLs are rejected.
- The encrypted AI vault and its decryption code moved to AI Dispatcher. Central can
  only request unlock through the authenticated internal API.
- `AI_DISPATCHER_TOKEN` is distinct from `API_ACCESS_TOKEN`. Production configuration
  rejects short or reused tokens, the local Supervisor generates and ACL-protects the
  dedicated token, and the container gate generates an independent value.
- `mogas setup` no longer writes a cloud model key to plaintext `.env`; the supported
  operator path is `deploy/reset-ai-vault.ps1`.

## AI Advice Approval Boundary

High/critical external AI Agent suggestions and diagnosis-generated review advice now:

1. persist as an `ai_suggestions` fact with principal, evidence and provenance;
2. create one `review_ai_recommendation` command in `waiting_approval`;
3. carry `workflow_kind=ai_suggestion_review` and `node_executable=false`;
4. remain absent from node claim queues;
5. require the canonical permission and Safety Governor path;
6. become terminal `verified/accepted` or `rejected/rejected` together;
7. record the decision timestamp and audit/event evidence;
8. reject command retry, preventing advice from becoming a node instruction.

Low/medium external suggestions remain advisory unless a diagnosis policy explicitly
requires human review. The Stage G migration adds a unique nullable `command_id` and
`decided_at` to the suggestion ledger and is idempotent through the migration ledger.

## Automated Acceptance

The official verifier passed on the Stage G working tree:

- Central API: 326 tests;
- Python SimPy/node simulator: 40 tests;
- AI Dispatcher: 12 tests;
- Dashboard: 16 files and 73 tests plus production build;
- CLI/workflow: 36 tests plus 9 subtests;
- Go node-agent and Go Supervisor suites;
- API/generated contract checks, secret scan, ACL check and Ruff correctness;
- strict Supervisor runtime and PostgreSQL Phase 1/3/4/5/6/7 gates.

Focused Stage G tests prove provider fallback/retry/deadline policy, pre-egress
redaction, denied egress, token caps, cost calculation, vault secrecy, dedicated
service authentication, Central ownership exclusion, migration idempotence, unique
suggestion-command linkage, approval, rejection and node-claim exclusion.

## Live Runtime Evidence

The Windows Supervisor was replaced from the Stage G working tree and reported 12
healthy processes. Strict runtime verification observed:

- AI runtime `source=api`, `status=live`, provider `deepseek`, model
  `deepseek-v4-pro`, vault present and unlocked;
- 3/3 fresh SimPy production nodes with zero active issues;
- PostgreSQL authority, authenticated Redis projection, NATS Shadow and MinIO healthy;
- all PostgreSQL Phase 1/3/4/5/6/7 gates passed.

A direct authenticated Central chat request returned through AI Dispatcher with
`source=api`, one successful DeepSeek attempt, approved egress origin
`https://api.deepseek.com`, complete provenance and an explicit unconfigured cost
record. AI Dispatcher rejected the external API token with HTTP 401 and accepted only
the dedicated internal token.

## Independent Container Gate

GitHub Container Gate
[29493157247](https://github.com/oweak/mini-ogas/actions/runs/29493157247)
passed on commit `4807f9d` in 1 minute 16 seconds. The clean Ubuntu runner built every
image, supplied a distinct required Dispatcher token, ran the one-shot PostgreSQL
migration, started the complete stack, accepted all three SimPy heartbeats and proved
Central restart persistence.

## Acceptance Decision

Stage G is accepted. AI Dispatcher is the sole model-call owner, the unified inference
contract is executable in local Supervisor and clean Compose modes, and high-risk AI
advice is bound to the canonical human approval chain. This decision does not grant AI
direct control authority and does not accept Stage H.
