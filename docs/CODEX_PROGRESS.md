# Mini-OGAS Codex Progress

Current status: local v2.2/v2.5 acceptance is complete. The latest canonical
gate passed 162 central tests, 35 simulator tests, 69 Dashboard tests plus
build, all remaining service suites, Ruff correctness lint and strict live
PostgreSQL/DeepSeek/3-node checks. Entries below are chronological checkpoints.

## 2026-07-13 - Long-cycle directive restart

### Completed audit actions

- Confirmed repository `D:\New project\mini-ogas`, branch `master`, clean
  baseline at `f3d8d88` before this work unit.
- Confirmed Python, Node.js, npm and Go are available. Docker and VBoxManage are
  not available on PATH, so VM/distributed claims are blocked pending local
  installation discovery or provisioning.
- Read the current README, architecture, debt, first-stage plan, progress, code
  entry points, simulator, rules, command manager, storage schema, Python edge
  runtime, and Go node-agent paths.
- Added the required persistent engineering documents and repository rules.

### Verified facts carried from the immediately preceding work unit

- Commit `f3d8d88` passed central-api 133 tests, simulator 26 tests, Dashboard
  63 tests plus production build, AI dispatcher 4 tests, CLI/workflow 30 tests
  plus 9 subtests, and both Go modules.
- The strict local runtime reported 8/8 supervised processes, 3/3 SimPy nodes,
  PostgreSQL primary facts, and a live DeepSeek API response.
- A local fault-to-archive workflow and desktop/mobile browser checks passed.

These are local multi-process v2.5 baseline facts, not VM-distributed evidence.

### Newly confirmed gaps

- P0: SimPy profiles use 45/60/75 second cycles (80/60/48 per hour per machine),
  which conflicts with the required 80/50/65 per-hour line model and the stated
  135/144/111 second processing assumptions.
- P0: `verify_target_rate` only checks that the next heartbeat echoes the target
  value. It does not verify WIP trend, starvation, throughput, alert state, or a
  verification window.
- P0: no stable event envelope with local/global sequence, correlation, event
  and ingest times, schema version, and payload exists.
- P1: deterministic rules only implement bottleneck and starvation; heartbeat
  loss/stale data, overproduction WIP growth, defect rise, wear, network anomaly,
  and ineffective-command rules are absent.
- P1: part records lack batch, next operation, quality status, scenario identity,
  and event sequence.
- P1: the Python edge has a SQLite heartbeat buffer and resync path, but ordered
  event dedupe/no-loss behavior has not been proven against the new contract.
- P2: the Go agent and Python SimPy edge overlap in purpose and expose different
  heartbeat/command contracts.
- P2: NATS, Redis and independent production VMs are not implemented.

### Checkpoint task at that time

Implement the physical simulation contract and the observation-based command
Verifier first, with focused tests, then introduce the stable event envelope.

### Work unit 1 - Physical simulation contract

- Added explicit machine counts and physical processing times: Turning 3 x 135s,
  Milling 2 x 144s, Grinding 2 x 111s.
- SimPy now runs parallel machine resources with steady-state phase offsets;
  one simulated hour yields approximately 80/50/65 parts without inventing a
  faster physical capacity.
- Added `nominal_capacity_per_hour`, per-hour target/actual rates, machine count,
  process time and rate-unit metadata while retaining the v2.2 per-minute fields.
- Fixed simulation time to advance from one process/run epoch and added explicit
  wall-clock and simulation-start timestamps.
- Supervisor now supplies one shared UTC simulation start to all three nodes.
- Actual test: `python -m unittest test_simulator.py` -> 30 tests passed.
- Next blocker: observation-window command Verifier.

### Work unit 2 - Observation-based Command Verifier

- Added a deterministic `CommandVerifier` that stores the pre-command system
  baseline and evaluates multiple post-command production observations.
- Verification now checks target application, downstream backlog trend, severe
  starvation, sink-throughput floor and observation-window completeness.
- Added explicit `effective`, `partial`, `failed`, `inconclusive` and
  `observing` results. Agent `executed` is normalized to command `applied`; only
  observed evidence can advance it to `verified`.
- Added command version, expiry, dispatch/receive/apply/verify timestamps,
  attempt count, baseline and evidence fields.
- Added SQLite and PostgreSQL-compatible schema migrations, durable upsert, and
  restart restoration for all verification metadata.
- Focused Verifier tests: 4 passed. Store/database tests: 63 passed. Full
  central-api suite: 137 passed.
- Next blocker: stable ordered event envelope and event-store persistence.

### Work unit 3 - Stable ordered event envelope

- Extended operational events with event ID/type, schema version, source node,
  event/ingest time, node-local and system-global sequences, correlation ID,
  run/scenario identity and structured payload.
- Added an idempotent `event_store` to SQLite and PostgreSQL schemas. The
  source/run/local sequence tuple is unique and the global sequence is unique.
- Event and audit projections are persisted in one database transaction;
  restart restoration rebuilds sequence watermarks from the durable event log.
- Replay now reads the event store and exposes operational events in sequence.
- Focused event/database tests and the full central-api suite pass.

### Work unit 4 - Deterministic operational rules

- Expanded the rule engine beyond bottleneck/starvation to heartbeat loss,
  stale data, defect-rate rise, tool wear, network anomaly, upstream
  overproduction and ineffective-command evidence.
- Every conclusion now carries trigger data, thresholds, candidate actions,
  result and a calculation summary suitable for UI and AI explanation.
- Offline nodes are excluded from flow calculations to prevent contradictory
  bottleneck/starvation conclusions.
- Focused rule and explanation tests pass.

### Work unit 5 - Edge command safety and part identity

- Python edge commands now validate schema version, expiry, command ID,
  whitelist and safe target range before applying changes.
- Applied-command idempotency is durable in edge SQLite, so a restarted agent
  does not execute the same command twice.
- Parts now carry run/scenario/batch/parent identity, current and next
  operation, quality state and monotonic event sequence across milling and
  grinding.
- SQLite/PostgreSQL migrations, persistence, restart restoration and replay
  projection include the full part identity contract.
- Actual results: node simulator 31 tests passed; focused Store/database 59
  tests passed; full central-api 143 tests passed.

### Checkpoint task at that time

Run fresh cross-service and live-process acceptance for the hardened contracts.
Then close remaining v2.2 runtime gaps before starting NATS/Redis distribution.

### Work unit 6 - Durable edge command-result outbox

- Extended edge SQLite command records with immutable parameters, report state,
  attempts, last error and reported timestamp.
- The agent queues results before network reporting, retries before and after
  polling, and marks completion only after central acceptance.
- Restart restores the last applied target-rate state. A repeated command is
  logged and ignored rather than re-executed.
- Disconnect/restart/reconnect test proves one local command row, two report
  attempts, successful eventual delivery and no target-rate rollback.
- Python node simulator suite: 32 passed.

### Work unit 7 - Causal three-operation WIP flow

- Dashboard, deterministic rules and Command Verifier now consume one central
  WIP projection derived from current-run durable part facts.
- Raw heartbeat WIP remains available as `reported_wip_input/output`; projected
  facts are explicitly marked `wip_source=part_queue`.
- SimPy finished-quantity deltas now advance the durable chain: Turning creates
  parts; Milling and Grinding can complete only available upstream parts.
- Default edge mode is heartbeat-driven flow. The older single-part claim loop
  remains only as explicit `PART_FLOW_MODE=agent_claim` compatibility behavior.
- Fixed run selection to follow the latest received fact and made centrally
  created parts inherit the same run/scenario identity.
- Tests prove output never exceeds input and run transitions do not strand new
  parts as historical WIP.

### Work unit 8 - Durable offline heartbeat replay

- Replaced the in-memory-only sync acknowledgement with transactional
  `node_record_receipts` and archived heartbeat persistence.
- Dedupe identity is `(node_code, run_id, local_id)` with a payload hash;
  conflicting reuse is rejected instead of silently discarded.
- Offline records retain source time and ingest provenance, never mutate the
  live projection, and cannot supersede a newer heartbeat after central restart.
- Full central-api suite: 147 passed. Focused disconnect/replay tests pass.

### Work unit 9 - Physical target-rate control and operator command boundary

- Moved target-rate handling into incremental SimPy output control: raw physical
  completions and command-constrained completions are now separate observable facts.
- Added per-workshop physical-capacity validation at both central operator gateway
  and edge restore/apply boundaries.
- Added JWT-protected `/ops/agents/{node_code}/commands`; the agent claim/result
  channel remains machine-credential-only.
- Live command 54 reduced Turning from 1.333 to 0.5 parts/minute. Raw SimPy output
  advanced while constrained output paused, proving a physical simulation effect.

### Work unit 10 - Verifier correction and nominal restoration

- Corrected downstream backlog comparison to use the command-creation baseline.
- Added direction-aware verification: a target increase is proven by the node's
  observed actual-rate increase; a decrease still requires downstream-flow evidence.
- Deterministic rules now evaluate only the latest command per node/type, so an old
  partial result remains in audit/replay but leaves live rules after a newer effective
  command.
- Live command 55 restored Turning to 1.333 parts/minute and became
  `verified/effective` after three later heartbeats; live rules returned to empty.

### Work unit 11 - AI request control and browser QA

- Replaced per-second evidence-value signatures with semantic rule signatures.
- Added frontend single-flight, retry cooldown, lock-screen reset and manual refresh.
- Added a server-side semantic cache with explicit `hit/miss/bypass` provenance.
- Normalized list-valued model summaries into stable operator text.
- Browser proof: snapshots continued every second, while only one DeepSeek rule
  explanation request occurred in 12 seconds; clean console had no new warnings.
- Desktop and mobile screenshots are in `output/playwright/`.

### Work unit 12 - Correctness lint and secret-output hardening

- Installed and ran Ruff. The broad style backlog remains documented, but all
  correctness-class `F` findings were removed across services, scripts and tools.
- `mogas doctor` no longer prints secret prefixes; it displays only
  `SET (redacted)`, covered by a regression test.
- Canonical verification now runs project-local Ruff correctness lint.
- Final canonical result: central 162, simulator 35, Dashboard 69 plus build,
  AI dispatcher 4, CLI/workflow 31 plus 9 subtests, both Go modules and strict
  PostgreSQL/DeepSeek/3-node runtime all pass.

### Work unit 13 - AI empty-response truth boundary

- Reproduced the difference between a successful login probe and an empty complex
  rule explanation from the same live `deepseek-v4-pro` provider.
- Confirmed that reasoning tokens could exhaust short response caps; the final
  configurable 4096-token cap covers the live multi-rule structured response.
- Added adapter, provider-chain and rule-contract validation so empty strings,
  empty JSON and unusable structured output cannot claim live AI success.
- Live verification returned a non-empty summary, two reasoning entries, three
  recommendations and two evidence entries with `provider=deepseek`, while all
  fallback paths retain explicit provenance.

### Work unit 14 - Trigger-grounded AI evidence

- Browser content review caught an AI arithmetic contradiction caused by the rule
  payload exposing a rate predicate that had not actually matched.
- Bottleneck conclusions now emit only satisfied predicates and choose summaries
  from the real trigger path instead of a generic below-target statement.
- Added a backlog-only regression proving a `0.94` actual/target ratio cannot be
  presented as satisfying a `<= 0.75` condition.

### Work unit 15 - v3.0.0 baseline and contract gate

- Audited the real repository, local runtime, PostgreSQL schema, Windows host,
  VirtualBox inventory, network adapters, clock service, storage and secrets
  boundary before changing v3 code.
- Created the five v3.0.0 baseline/contract documents, including executable
  JSON schemas and explicit deferred gates for VM networking, CA material,
  time synchronization and per-node credentials.
- The document gate parsed all three JSON schema blocks and passed with zero
  errors. Decision: `PASS WITH RECORDED DEFERRED GATES` for loopback v3.0.1.

### Work unit 16 - v3.0.1 NATS shadow transport

- Installed checksum-verified NATS Server 2.14.3 and pinned `nats-py==2.15.0`.
- Added strict schema 3.0 contracts, deterministic IDs, four subject families,
  JetStream file persistence, explicit-ACK durable consumption and idempotent
  PostgreSQL shadow receipts.
- Preserved REST as the authoritative path. NATS failure reports degraded while
  Central liveness remains healthy; a background manager retries connection.
- Fixed two live-only defects found during gate execution: normal empty pull
  timeouts no longer mark the worker degraded, and unavailable NATS at process
  startup no longer blocks the FastAPI lifespan.
- Live acceptance proved 9/9 healthy processes, zero crashes, zero NATS worker
  failures, four message types, PostgreSQL consumption and independent-process
  REST fallback with NATS unavailable.
- Canonical result: Central 173, simulator 35, Dashboard 69 plus build, AI 4,
  CLI/workflow 31 plus 9 subtests, both Go modules, Ruff, strict runtime and
  live DeepSeek all passed.

### Work unit 17 - Engineering master prompt Phase 0

- Read the 3,460-line engineering master prompt and audited the current Git,
  runtime, PostgreSQL, NATS, SimPy, source provenance, AI, secret and physical
  safety boundaries before adding Phase 1 capability.
- Corrected simulation provenance and removed frontend-derived OEE, yield,
  due-time and completion facts.
- Created all nine required Phase 0 governance, architecture and security
  records. The current chain remained runnable and no physical write path exists.
- Phase 0 passed the full canonical and strict runtime gates.

### Work unit 18 - Phase 1 engineering foundation

- Added fail-fast `APP_ENV`, `DATA_SOURCE`, `CONTROL_MODE`, Demo isolation and
  explicit tenant/site deployment scope.
- Added checksum migrations, scoped columns, forced PostgreSQL RLS and a
  transactional heartbeat Outbox with lease, retry and dead-letter lifecycle.
- Added deterministic OpenAPI/AsyncAPI/schema exports with drift tests and
  truthful wired/unwired NATS status.
- Added request IDs, UTC helpers, a stable problem response contract, login
  rate limiting, production bootstrap rules and protected Windows secret ACLs.
- Froze module dependency direction with architecture tests while retaining
  seven explicitly recorded legacy router couplings.
- Final gate: Central 196; simulator 35; Dashboard 69 plus build; AI 4;
  CLI/workflow 31 plus 9 subtests; both Go modules and Ruff passed. Live
  PostgreSQL proved 18/18 forced-RLS tables, zero cross-scope rows, 7,843 audit
  rows and 112 published Outbox rows under non-bypass role `mini_ogas`.
