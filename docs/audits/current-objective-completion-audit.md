# Current A-H Objective Completion Audit

Date: 2026-07-18

Branch: `codex/current-stage-hardening`

Stage H implementation commit: `51eba35cfd8790830ed61b7bdc6ed05f61d4fc28`

## Audit Method

Completion is evaluated against all 16 explicit requirements in the current Codex
objective. A requirement is accepted only when the current source defines the boundary
and an executable test, live runtime gate or clean-container gate proves it. Historical
plans and HTTP success responses are not sufficient evidence.

The canonical local command is:

```powershell
.\scripts\verify-miniogas.ps1 -RequireAiUnlocked
```

The clean Linux deployment command is the GitHub `Container Gate`, which executes
`scripts/container-smoke.sh` from a fresh checkout.

## Requirement-By-Requirement Decision

| No. | Required state | Authoritative evidence inspected | Decision |
| ---: | --- | --- | --- |
| 1 | All known P0 blockers are closed. | `docs/audits/current-stage-baseline.md` preserves the B1-B8 reproduction/root-cause evidence; the canonical verifier reruns the corrected authorization, encoding, dependency, image-input, environment and controlled-clock gates. | Satisfied |
| 2 | Central, Node, AI, Dashboard and Go tests all pass. | Canonical result: Central API 330, Python simulator 40, AI Dispatcher 13, Production Planner 2, CLI/workflow 41 plus 9 subtests, Dashboard 74 across 16 files, and both Go modules. | Satisfied |
| 3 | Dashboard completes a production build. | `verify-miniogas.ps1` runs `npm.cmd run build`; the local gate passed and the clean container serves the Nginx production artifact. | Satisfied |
| 4 | Central API and Node Agent images build and start from a clean environment. | GitHub Container Gate `29632887914` ran `docker compose up --build --detach`, reached Central health and observed authenticated SimPy heartbeats from all three node images. | Satisfied |
| 5 | At least one one-command deployment path reproduces the core system. | `scripts/start-miniogas.ps1` is the supported Supervisor entrypoint and reached 12/12 healthy processes. `mogas up` now delegates to that entrypoint, reads its session proof and rejects stale/missing Central health. Compose is the independent clean Linux path. | Satisfied |
| 6 | Node identity is bound to `node_code`; cross-node command access is impossible. | `docs/security/principal-control-matrix.md`, `test_node_ingest_token_cannot_create_cross_node_command`, independent node credentials, path/body binding, rotation and revocation gates. | Satisfied |
| 7 | Every production command uses unified authentication, authorization, safety, approval and audit. | `CommandControlService`, the Principal matrix and Safety Governor own issue/approve/reject/cancel/retry. Node claim/report is credential-bound. Stage H rejects unauthenticated proposals and a wrong `CONFIRM` before the approved command can be claimed. | Satisfied |
| 8 | PostgreSQL is the central source for key business facts. | Command, Node, Production, Quality, Incident/Event and Data Platform repositories persist their facts in PostgreSQL. Phase 1/3/4/5/6/7 gates query the database directly; MemoryStore is retained only as a compatibility/projection facade. | Satisfied |
| 9 | Central restart restores key business state. | `scripts/container-smoke.sh` stops nodes, restarts Central and Background Worker, proves node facts survive, proves the migration ledger is unchanged and then observes heartbeat count growth. Repository recreation/restart tests cover command, node, production, quality and incident facts. | Satisfied |
| 10 | Simulation and periodic work are not duplicated by API workers. | `docs/audits/stage-d-background-worker-evidence.md` and `test_architecture_boundaries.py` prove API lifecycle has no `asyncio.create_task`, Supervisor/Compose declare exactly one `background-worker`, and that worker alone owns simulation and Outbox/NATS tasks. | Satisfied |
| 11 | Outbox has one official publisher and consumers are idempotent. | `docs/audits/stage-e-single-outbox-publisher-evidence.md` proves request-side direct NATS publication was removed. The worker is the sole publisher; deterministic IDs, PostgreSQL receipt uniqueness, duplicate counters and aggregate-order fencing are covered by architecture, migration and NATS publisher tests. | Satisfied |
| 12 | Redis projection can be rebuilt. | `scripts/check_phase7_data_platform.py` performs two rebuilds, requires a new generation and reconciles rebuilt projection data to PostgreSQL authority. The canonical Phase 7 gate passed. | Satisfied |
| 13 | NATS Shadow can reconcile, degrade and roll back. | `docs/audits/stage-e-shadow-reconciliation-evidence.md` and `scripts/check-stage-e-nats-recovery.ps1` prove a 100-message window, receive/duplicate/latency/order/PostgreSQL metrics, degraded REST continuity, controlled stop/recovery and `-DisableNats` rollback. NATS remains Shadow. | Satisfied |
| 14 | Supervisor, Compose, Dockerfiles, startup scripts and README agree. | `docs/deployment/component-truth-table.md`, Stage F evidence and deployment architecture tests compare the component set, ports, health, migration owner and production Dashboard. `mogas up` no longer calls retired `start-system.ps1`; `start-system.ps1` remains diagnostic-only. | Satisfied |
| 15 | AI calls use one control plane with auditable source and fallback. | `docs/audits/stage-g-unified-ai-plane-evidence.md` proves AI Dispatcher is the sole provider owner and covers provider/model, deadline/retry/token cap, fallback, provenance, latency, cost, redaction, egress and errors. Strict runtime proved live `deepseek-v4-pro`; high-risk advice remains human-only. | Satisfied |
| 16 | The end-to-end production-control loop is proved beyond HTTP 200. | `docs/audits/stage-h-governed-closed-loop-evidence.md` and `scripts/check_stage_h_closed_loop.py` prove order-to-plan causality, governed approval, bound node claim, SimPy rate/output/WIP change, PostgreSQL facts, Dashboard projection, Verifier `effective` and complete audit/event history. Final run: order `AO-006`, command `60`, target `0.592 -> 0.750`, actual `0.432 -> 0.547`, finished `6 -> 7`. | Satisfied |

## Deployment And Runtime Cross-Check

The converged core component set is PostgreSQL, authenticated Redis, authenticated NATS
JetStream Shadow, MinIO, one-shot migration, Central API, Background Worker, AI
Dispatcher, market simulator, Production Planner, production Dashboard and three SimPy
nodes. Supervisor runs the process-hosted equivalents; Compose runs the containerized
equivalents. The local accepted runtime reported 12/12 managed processes healthy.

The clean Ubuntu Container Gate
[29632887914](https://github.com/oweak/mini-ogas/actions/runs/29632887914)
passed implementation commit `51eba35` and proved image builds, one-shot PostgreSQL
migration, infrastructure health, production Dashboard serving, three node heartbeats
and PostgreSQL recovery across service restart.

## Non-Negotiable Boundary Check

- No failed test was removed or skipped to obtain acceptance.
- The controlled calibration clock remains strict; no validity window was widened.
- Stage H uses live SimPy heartbeats and PostgreSQL queries, not fixtures or mock
  production state.
- Production command routes remain authenticated and converge on the canonical command
  service and Safety Governor.
- PostgreSQL is authoritative; Redis is rebuildable and NATS remains Shadow.
- AI remains advisory and cannot autonomously issue a node-executable high-risk command.

## Acceptance Boundary

All 16 requirements of the current A-H objective are satisfied. The supported
description is a repeatably deployable industrial digital-twin/MOM engineering
prototype with a trusted control boundary, durable key facts, event Shadow validation
and controlled AI assistance.

This audit does not claim a mature MES/MOM, industrial high availability, independent
multi-factory deployment, real-factory production validation, authoritative NATS edge
transport or autonomous AI equipment control.
