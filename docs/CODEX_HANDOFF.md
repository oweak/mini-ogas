# Mini-OGAS Codex Handoff

Updated: 2026-07-13

## Current stage

The engineering master prompt Phase 0 and Phase 1 gates are accepted in addition
to the earlier v2.2/v2.5 and v3.0.0/v3.0.1 work. Phase 2 organization, asset,
personnel and versioned master-data capability is the first unmet gate.
Physical simulation, stable events, deterministic rules, command
verification/outbox, causal part flow, durable offline replay, PostgreSQL facts,
JWT/RBAC and the guarded AI path all have fresh automated and runtime evidence.

## Last known clean baseline

- Repository: `D:\New project\mini-ogas`
- Branch: `master`
- Commit: `f3d8d88 feat: complete v2.5 trusted runtime architecture`
- Worktree was clean before adding the persistent planning documents.

## Current edits

- Added `AGENTS.md`.
- Added `docs/CODEX_MASTER_PLAN.md`.
- Added `docs/CODEX_PROGRESS.md`.
- Added `docs/CODEX_HANDOFF.md`.
- Added `docs/VERIFICATION_MATRIX.md`.
- Renamed the debt register to `docs/ARCHITECTURE_DEBT.md` and will reopen
  newly proven P0/P1 debt there.
- Added the five v3.0.0 audit/contract documents and the v3.0.1 implementation
  report.
- Added strict NATS contracts, publisher, JetStream worker, PostgreSQL receipt
  storage, supervisor process/configuration and checksum-verified installer.
- Added the nine Phase 0 required records, Phase 1 environment/source/control
  guards, forced-RLS scope migration, heartbeat Outbox, generated contracts,
  problem errors and local secret ACL governance.

## Actual evidence

- Canonical verification: central-api 196, Python simulator 35, Dashboard 69
  plus production build, AI dispatcher 4, CLI/workflow 31 plus 9 subtests, and
  both Go modules passed.
- Ruff correctness rules (`F`) pass across `services`, `scripts` and `tools`.
- Strict local runtime: 9/9 processes, 3/3 fresh SimPy nodes, PostgreSQL primary,
  live DeepSeek, zero active issues and one supervisor session.
- NATS v2.14.3 is a live loopback shadow path: JetStream publisher and durable
  worker are live, PostgreSQL receipts are idempotent and the observed worker
  failure/invalid counts are zero after the timeout correction.
- An independent Central process with unreachable NATS reported degraded while
  accepting and applying the authoritative REST heartbeat.
- Live command 54 proved physical throttling: raw SimPy output advanced while
  command-constrained output did not. Command 55 restored 1.333 parts/minute and
  reached `verified/effective` from three later heartbeat observations.
- Browser audit: one AI explanation request in 12 seconds while snapshots kept
  polling, no overlapping request storm, and no new warning/error in the clean run.
- Phase 1 database gate: application role `mini_ogas` is non-superuser and cannot
  bypass RLS; 18/18 tables are forced scoped, alternate scope reads return zero,
  audit had 7,843 scoped rows and heartbeat Outbox had 112 published rows.
- Secret/content/contract gates pass; 9 sensitive repository/runtime paths have
  protected ACLs and generated OpenAPI/AsyncAPI artifacts match current code.

## Highest-priority blockers

1. `MemoryStore` remains a 4098-line projection/orchestration object.
2. `simulator.py` remains a 1059-line edge runtime with mixed responsibilities.
3. Redis and independent VMs remain future distributed work; NATS is only a
   loopback shadow and is not yet the authoritative edge transport.
4. The Kali disk is prepared but the VM is not registered or running.
5. PostgreSQL is local and single-instance; HA and recovery SLOs are not defined.

## Exact next actions

1. Audit Phase 2 current master-data facts and reuse only real implemented models.
2. Add versioned organization/asset/material/BOM/routing/document records under
   tenant/site RLS with immutable revisions and effective approval transitions.
3. Separate account roles from personnel skills/qualifications and enforce the
   distinction when binding work to an operation/equipment capability.
4. Bind work orders to explicit BOM, routing and document revisions with audit
   evidence and backward-compatible adapters.
5. Do not begin Phase 3 execution-state expansion until all four Phase 2 gates pass.

## Most recent command

`scripts\verify-miniogas.ps1 -RequireAiUnlocked` passed all canonical gates on
2026-07-13, including 196 central tests, 35 simulator tests, 69 Dashboard tests,
both Go modules, strict runtime, real DeepSeek, Ruff, contract drift, secret ACL,
and the live PostgreSQL Phase 1 gate.

## Do not repeat

- Do not re-audit VirtualBox UI residue; it was removed from the production path.
- Do not claim Redis or workshop VMs from architecture diagrams. Describe NATS
  only as loopback shadow transport until an edge migration gate passes.
- Do not treat agent `executed` as operational effectiveness.
- Do not replace PostgreSQL central facts with SQLite.

## External blockers

Docker and VBoxManage are not currently discoverable on PATH. The production VM
network is still NAT-only, the host-only adapter is not on the contracted subnet,
Windows Time is not running, and no v3 CA/certificates exist. These are hard
gates before v3.0.3 edge migration, not blockers for loopback v3.0.1.
