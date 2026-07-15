# Schema Version Register

| Version/Migration | Domain | Compatibility | Verification | Status |
|---|---|---|---|---|
| `2026.07.13-phase1-scope-outbox` | Platform data scope and Outbox | Additive | Checksum ledger, forced RLS, live runtime | Active |
| `2026.07.14-phase2-master-data` | Organization, resource, engineering revision, work-order release | Additive | Fresh/repeat init, 18/18 live forced RLS, trigger/index probes | Active |
| `2026.07.14-phase2-revision-delete-guard` | Controlled history | Additive | Live delete rejection and ledger singleton | Active |
| `2026.07.14-phase3-production-execution` | Production/work-order/operation execution | Additive | 11/11 forced RLS, history/quantity guards, live workflow | Active |
| `2026.07.14-phase3-execution-invariant-guards` | State, evidence and quantity invariants | Additive | SQLite/PostgreSQL direct bypass rejection | Active |
| `2026.07.14-phase4-material-flow` | Warehouse/location, lot/serial, container, movement, balance, genealogy and reconciliation | Additive | 10/10 forced RLS; live governed material workflow | Active |
| `2026.07.14-phase4-balance-invariant-guards` | Global Serial quantity invariant | Additive | SQLite tests and PostgreSQL second-location rejection | Active |
| `2026.07.14-phase5-quality-operations` | Inspection plans, gauges, lots, holds, measurements, NC, disposition, CAPA and history | Additive | 10/10 forced RLS; live governed quality workflow | Active |
| `2026.07.14-phase5-quality-invariant-guards` | Held movement, deterministic result and authorized release invariants | Additive | SQLite/PostgreSQL direct bypass rejection | Active |
| `2026.07.14-phase6-maintenance-operations` | Assets, maintenance requests/orders, PM plans, checklists, spares, tools, life, calibration and history | Additive | 14/14 forced RLS; live governed workflow | Active |
| `2026.07.14-phase6-maintenance-invariant-guards` | Checklist/work, independent verification, tool/calibration and task interlocks | Additive | SQLite/PostgreSQL direct bypass rejection | Active |
| `2026.07.14-phase6-mro-movement-binding` | Maintenance authority on Phase 4 Consume movements | Additive nullable FK/index/guard | Bound live spare and unbound direct insert rejection | Active |
| `2026.07.14-phase6-maintenance-lifecycle-guards` | Legal Maintenance Order lifecycle and immutable accepted evidence | Additive | Same-actor transition and verified-evidence rewrite rejection | Active |
| OpenAPI v1 generated artifact | HTTP | Additive `/master-data/*`, `/execution/*`, `/material-flow/*`, `/quality/*`, and `/maintenance/*` operations | `python tools/export_contracts.py --check` | Current |
| NATS schema 3.0 | Shadow audit transport | Existing `audit` envelope reused | Strict envelope and Outbox tests | Current shadow only |

Migration checksums are immutable after application. A checksum mismatch fails startup;
new behavior requires a new migration ID.
