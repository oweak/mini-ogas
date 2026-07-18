# Stage H Governed Production Closed-Loop Evidence

Date: 2026-07-18

Implementation commit: `51eba35cfd8790830ed61b7bdc6ed05f61d4fc28`

## Gate Scope

Stage H proves one automated industrial-control path from a real order fact through
planning, governed command execution, SimPy physical behavior, durable facts,
Dashboard projection, effect verification and audit history. An HTTP 200 response is
not acceptance evidence.

The accepted path is:

```text
allocation order change
  -> order-aware production plan and dispatch tasks
  -> high-risk target-rate proposal
  -> JWT permission, Safety Governor and CONFIRM approval
  -> bound node claim and local durable execution
  -> SimPy target, actual rate and output/WIP change
  -> PostgreSQL order/plan/task/command/heartbeat facts
  -> Dashboard command and dispatch projection
  -> CommandVerifier effective decision
  -> audit log and event-store lifecycle
```

This gate does not claim a mature MES/MOM, high availability, independent factory
hosts, real-factory validation or authoritative NATS edge transport.

## Reproduced Defects And Root Causes

1. Allocation orders were accepted but did not affect the production-planner request,
   plan quantity or node target rate. The UI approval path could report execution even
   though no node command existed.
2. A governed command could be approved, but the Dashboard immediately wrote a local
   "executed" effect before the node claimed it or the Verifier observed production.
3. The command Verifier applied a fixed 70 percent baseline throughput floor to the
   grinding sink. A scientifically proportional target decrease was therefore marked
   failed even when actual rate followed the approved target exactly.
4. The AI connectivity probe gave a reasoning-capable model only 16 output tokens.
   DeepSeek could consume that budget in reasoning and return no final content, causing
   a false fallback result despite a valid Vault key and reachable provider.
5. The first Stage H verifier expected a nonexistent `last_seen_sec` snapshot field and
   misclassified a fresh timestamped heartbeat as stale.

## Implemented Control Path

- `DispatchControlService` selects an accepted order and its current production plan,
  requires a dispatch task on a fresh capacity-reporting node, derives parts/minute
  from quantity and deadline, and rejects targets above reported physical capacity.
- `CommandControlService` creates `set_target_rate` as a high-risk,
  `waiting_approval` command with order, product, plan, task, capacity, TTL and
  idempotency provenance. The command remains absent from the node claim queue before
  approval.
- Wrong or missing confirmation is rejected by Safety Governor. A permitted
  administrator using `CONFIRM` moves the command to `pending`; the bound node alone
  can claim it.
- Node execution changes the SimPy physical rate controller, persists the local command
  lifecycle and reports subsequent Heartbeat v2 observations.
- `CommandVerifier` requires three observations, target application, direction-aware
  own-rate movement and a dynamic sink throughput floor. For a sink target change, the
  floor is based on expected throughput at the approved target with a 10 percent
  safety allowance; a severely underperforming sink still fails.
- Verified command results project the allocation order and dispatch task to
  `in_progress`. Failed, inconclusive, rejected or cancelled results remain explicit.
- Dashboard dispatch state uses the canonical command lifecycle. Approval displays
  `approved_executing`; only `verified/effective` displays `approved_executed` and can
  be treated as resolved.

## Planning Causality

The fallback planner and the independent Production Planner service both receive active
allocation orders. For each product they:

- retain market and inventory pressure;
- sum committed active-order quantity;
- use the greater of market demand and committed quantity;
- preserve the highest order priority;
- include accepted order IDs and committed quantity in the plan reason;
- plan an order-only product even when no market signal exists.

This makes the order-to-plan relationship queryable in both the API response and the
PostgreSQL plan projection.

## Automated Gate

`scripts/check_stage_h_closed_loop.py` is included in the official verifier. It performs
all of the following without mock heartbeats or direct database repair:

1. proves an unauthenticated proposal receives HTTP 401;
2. logs in as the administrator and checks JWT execution/issue/approve permissions;
3. requires 3/3 fresh SimPy production nodes;
4. creates a P3 allocation order and proves plan quantity and order-ID causality;
5. proves a grinding dispatch task exists;
6. creates exactly one high-risk target-rate command in `waiting_approval`;
7. proves the command is visible in the approval queue but not claimable by the node;
8. rejects an incorrect confirmation code without changing command state;
9. approves with `CONFIRM` and observes node claim, apply and result;
10. waits for `verified/effective`, an applied target and output/WIP/quality change;
11. checks Dashboard command identity, target and effective result;
12. queries PostgreSQL under tenant/site scope for every durable fact and audit stage.

The test target alternates between 70 and 55 percent of reported physical capacity.
This proves both increase and decrease behavior without repeatedly multiplying the
running target toward zero.

## Live Runtime Evidence

The Windows Go Supervisor reported the complete 12-process runtime healthy, including
PostgreSQL-backed Central API, dedicated Background Worker, authenticated Redis,
NATS Shadow, MinIO, AI Dispatcher, market simulator, Production Planner, production
Dashboard and three fresh SimPy workshop processes.

Four live Stage H runs supplied complementary evidence:

| Command | Direction | Target before/after | Actual before/after | Physical change | Result |
| --- | --- | ---: | ---: | --- | --- |
| `57` | decrease | `0.700 -> 0.450` | `0.434 -> 0.284` | WIP input | effective |
| `58` | increase | `0.450 -> 0.750` | `0.288 -> 0.480` | WIP input | effective |
| `59` | decrease | `0.750 -> 0.592` | `0.473 -> 0.379` | finished `0 -> 1`, WIP input/output | effective |
| `60` | increase | `0.592 -> 0.750` | `0.432 -> 0.547` | finished `6 -> 7` | effective |

The final official run used order `AO-006`, plan target quantity `509`, dispatch task
`58` and command `60`. PostgreSQL showed:

- allocation order `in_progress`;
- P3 plan covering the order and retaining its ID in the reason;
- grinding dispatch task `in_progress`;
- command `verified/effective`, claimed by `grinding-workshop-01`, attempt count one;
- latest Heartbeat v2 from `simulation_engine=simpy`, target `0.750`, actual `0.547`,
  finished quantity `7`;
- audit actions `allocation-order:create`, `dispatch:target-rate-proposed`,
  `dispatch:propose` and `command:approve`;
- event stages `command-created`, `command-approved`, `command-claimed`,
  `command-result` and `command-verification-effective`.

## AI Runtime Correction

The strict gate initially failed truthfully because the connectivity probe fell back.
Direct Dispatcher provenance isolated DeepSeek as `invalid_response`. An authenticated
Vault probe then proved `deepseek-v4-pro` returned a live API response when given a
128-token budget: one successful DeepSeek attempt, 45 total tokens, no fallback.

The connection probe now reserves 128 bounded tokens, and provider parsing rejects
`content=null` instead of converting it to the literal string `None`. The final strict
runtime reported `source=api`, `status=live`, provider `deepseek`, model
`deepseek-v4-pro`, Vault present and unlocked.

## Full Verification Result

The canonical command was:

```powershell
.\scripts\verify-miniogas.ps1 -RequireAiUnlocked
```

It passed with:

- Central API: 330 tests;
- Python node simulator: 40 tests;
- AI Dispatcher: 13 tests;
- Production Planner: 2 tests;
- CLI/workflow: 41 tests plus 9 subtests;
- Dashboard: 16 files, 74 tests and production build;
- Go node-agent and Go Supervisor suites;
- API/generated contracts, secret scan, secret ACL and Ruff correctness;
- strict live runtime with DeepSeek API and 3/3 SimPy nodes;
- PostgreSQL Phase 1, Production Phase 3, Material Phase 4, Quality Phase 5,
  Maintenance Phase 6, Data Platform Phase 7 and Stage H closed-loop gates.

## Independent Container Gate

GitHub Container Gate
[29632887914](https://github.com/oweak/mini-ogas/actions/runs/29632887914)
passed implementation commit `51eba35` in 1 minute 30 seconds. A clean Ubuntu runner
built the images, ran the one-shot migration, started the complete Compose stack,
observed all three SimPy nodes and proved PostgreSQL recovery after service restart.

## Acceptance Decision

Stage H is accepted. The current A-H hardening objective is satisfied by executable
local and clean-container evidence. The accepted description remains an industrial
digital-twin/MOM engineering prototype with governed control and durable facts; it is
not a mature industrial MES/MOM or a proven multi-host production deployment.
