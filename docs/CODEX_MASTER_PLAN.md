# Mini-OGAS Codex Master Plan

Updated: 2026-07-13

## Acceptance Rule

Progress is evidence-based. `A` means code and current runtime evidence exist;
`B` means implementation exists but runtime evidence is missing; `C` means only
an interface/shell exists; `D` means documentation only; `E` means the current
implementation contradicts the requirement or is broken.

## Current Truth

The repository has a verified local multi-process baseline using FastAPI, Vue,
Python SimPy workshop processes, Go supervisor, PostgreSQL, authenticated HTTP,
and a DeepSeek-compatible provider chain. v3.0.0 contracts are frozen and a
loopback NATS/JetStream v3.0.1 shadow path is live beside authoritative REST.
It does not currently have Redis or production workshop VMs. The local trusted loop now proves physical
rate control, later heartbeat facts, downstream observations, verifier outcome,
rule retirement, PostgreSQL projection and Dashboard display.

## Ordered Phases

| Phase | Objective | Entry gate | Exit gate | Status |
| --- | --- | --- | --- | --- |
| 0 | Repository fact audit | Cleanly identify repo and user changes | Code map, A-E classification, environment and docs complete | Complete |
| 1 | Reproducible baseline | Phase 0 facts recorded | Build/tests/startup/one node/offline-reconnect/security pass | Complete |
| 2 | v2.2 trusted causal loop | Stable baseline | SimPy -> facts -> rules -> explanation -> safety -> command -> observed effect passes | Complete for local process runtime |
| 3 | v2.5 debt cleanup | All v2.2 scenarios pass | Event schema, PostgreSQL event store, current projection, replay and compatibility exits pass | Complete for local process runtime |
| 4 | v3.0 distribution | Stable event/control contracts | NATS/Redis shadow, independent VMs, offline replay/dedupe/ACK and trace pass | v3.0.0 and v3.0.1 complete; v3.0.2 pending |
| 5 | Demonstration and thesis evidence | Architecture acceptance | Reproducible scenarios, diagrams, evidence bundles and operator docs pass | Local evidence complete; v3 evidence pending |

## Immediate Work Queue

1. Implement v3.0.2 Redis only as a rebuildable current-state projection, with
   PostgreSQL remaining the historical fact source.
2. Split the 4098-line central projection store into bounded repositories and
   application services without changing the v2.2 snapshot contract.
3. Split the 1059-line Python edge runtime into simulation, command, outbox and
   transport modules while preserving deterministic tests.
4. Resolve the recorded network, clock, CA and per-node credential gates before
   deploying the first independent workshop host/VM.
5. Keep `NATSPublisher` in shadow mode and HTTP authoritative until the
   independent-edge acceptance gate passes.
6. Register Kali in an isolated private lab and run a guarded attack/recovery proof.
7. Execute and record PostgreSQL backup/restore RPO/RTO acceptance on a disposable restore target.

## Non-Negotiable Causal Proof

```text
SimPy physical change
-> Edge event/heartbeat
-> Central persisted fact
-> Dashboard snapshot
-> deterministic rule evidence
-> LLM explanation of supplied evidence
-> Safety Governor decision
-> versioned/idempotent command
-> Agent applies command
-> later production facts change
-> Verifier classifies effective/partial/failed/inconclusive
```

## v3.0 Target Topology

`ogas-router`, `ogas-central`, `ogas-turning-edge`, `ogas-milling-edge`,
`ogas-grinding-edge`, `ogas-model`, and optional powered-off `ogas-kali`.
Each edge must have an independent process/VM, local durable outbox, failure
boundary, identity, command ACK, and network-only part/event transfer.
