# Mini-OGAS System Issues

Report time: 2026-07-13

## Current Result

No open P0/P1 issue remains inside the accepted v2.2/v2.5 local-runtime scope. This statement is backed by automated tests, a clean supervised restart, live PostgreSQL/AI/node verification and browser inspection.

## Defects Found During The Final Audit

| Severity | Finding | Root cause | Fix and proof |
| --- | --- | --- | --- |
| P0 | Top summary showed zero faults while ten old warning popups appeared. | PostgreSQL restored historical `open` alerts, but `Alert` did not retain its SQL `run_id`. | Domain model and operational queries now enforce current-run alerts; browser shows 0 summary / 0 popups. |
| P0 | WIP could be persisted or claimed under a stale target-node run. | SQL had `run_id`, but `PartQueueItem` inferred it dynamically from target heartbeat. | WIP owns immutable run identity and downstream inheritance; replay test and current-run claim filters pass. |
| P1 | Completed-result notifications could cross run boundaries. | Incident events had no domain-level run identity. | Events persist/restore `run_id`; unbound central events inherit current system run; workflow notification check passes. |
| P1 | Log archive card rendered `undefined 条归档`. | Frontend expected an array while `/api/audit/events` returns `{total, events}`. | Response normalization added; malformed response test, build and browser check pass. |
| P1 | Duplicate command-created audit entries. | Route and Store both emitted the event. | Route duplicate removed; Store transaction is the single owner. |
| P1 | Same run could be fed by mismatched scenario/seed data. | Supervisor/node defaults were independently configured. | Shared scenario/seed plus pre-mutation identity rejection tests. |
| P1 | Some AI outputs could expose configured rather than actual provider labels. | Provenance was assembled outside provider result. | Actual provider/model/source now travels with the result; API/fallback tests pass. |
| P1 | Safety checks were inconsistent across high-risk routes. | Policy lived partly in handlers. | Safety Governor now gates all supported high-risk entry points and audits denial codes. |
| P1 | Live AI rule explanation was requested repeatedly as evidence values changed every second. | The frontend refresh signature included volatile evidence values and had no single-flight/cooldown; the server had no semantic cache. | Semantic refresh gate plus server cache added; browser observed one AI request during 12 seconds of continued snapshot polling. |
| P1 | `mogas doctor` printed secret prefixes. | Diagnostic output masked only the suffix instead of redacting the whole value. | Sensitive values now show only `SET (redacted)`; regression test passes. |
| P1 | A later successful command did not retire an older partial command rule. | Rules scanned every historical command in the snapshot. | Rules use the latest result per node/type; history remains in audit/replay. |
| P1 | Local steady-state explanation still named DeepSeek even when no model call occurred. | Provider identity was copied from the configured active backend into local fallback output. | Local output now reports `rule_fallback`; attempted live provider is a separate field only on failure. |
| P1 | Empty DeepSeek responses were recorded as successful live explanations. | Provider success was inferred from a non-exceptional HTTP call, while the response cap could be exhausted by reasoning before final content. | Empty/unusable output is rejected at adapter, registry and explanation boundaries; `AI_CHAT_MAX_TOKENS=4096` restores complete structured output and regression tests cover truthful fallback. |
| P1 | AI could cite a mathematically false rate comparison in a backlog-only bottleneck. | The deterministic rule emitted all candidate evidence, including predicates that did not trigger the conclusion. | Bottleneck output now contains only satisfied predicates and a trigger-specific summary; the live prompt no longer includes the unmatched rate ratio. |

## Verified Non-Issues

- Production availability does not depend on VirtualBox.
- The normal runtime uses PostgreSQL, not SQLite.
- The frontend does receive backend heartbeat, alert, WIP, audit and run facts.
- DeepSeek participation is real when login smoke says `source=api`; fallback is visibly separate.
- Replay is database-backed and read-only.
- Closed/acknowledged items leave live queues and remain in audit/replay.

## Residual Risks

These are accepted boundaries or v3.0 work, not silently completed features:

1. All production processes currently share one physical Windows host.
2. HTTP is the node event transport; NATS is not deployed.
3. PostgreSQL is a single local central instance without HA/SLO claims.
4. DeepSeek availability and response latency depend on an external provider.
5. The prepared Kali VM is not registered; attack scripts must not target public or non-lab systems.
6. `MemoryStore` remains a 4098-line projection/orchestration object, although key persistence, command, safety and preflight logic now have module boundaries.
7. `simulator.py` remains a 1059-line edge runtime and should be split before v3 transport work.
8. Full Ruff style modernization is intentionally deferred; correctness-class `F` rules are now mandatory and pass.

## Verification Commands

```powershell
.\scripts\start-miniogas.ps1 -ReplaceRunning -FactSource postgresql
.\scripts\verify-miniogas.ps1 -RequireAiUnlocked
& '.\services\central-api\.venv\Scripts\python.exe' '.\scripts\check_runtime_workflow.py'
.\scripts\check-runtime-status.ps1
```

See `docs/full-system-audit-and-optimization-2026-07-13.md` for the complete architecture and evidence report.
