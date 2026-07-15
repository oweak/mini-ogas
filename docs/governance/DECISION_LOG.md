# Decision Log

| Date | Decision | Record | Status |
|---|---|---|---|
| 2026-07-13 | Treat PostgreSQL as primary durable business store and NATS as loopback shadow transport during Phase 1 | `PHASE1_GATE.md` and existing Phase 1 implementation record | Accepted for current engineering stage |
| 2026-07-14 | Keep simulation, replay, fixture, fallback, and live facts explicitly separated | `architecture/SIMULATION_PRODUCTION_BOUNDARY.md` | Active |
| 2026-07-14 | Implement Phase 2 inside the modular central API, with PostgreSQL authority and immutable revisions, instead of extending `MemoryStore` or splitting a new service | `adr/ADR-0002-phase2-versioned-master-data.md` | Accepted for Phase 2 |
| 2026-07-14 | Make PostgreSQL the sole Phase 3 execution authority with strict state, evidence, quantity, audit and replay guards | `adr/ADR-0003-phase3-production-execution-authority.md` | Accepted for Phase 3 |
| 2026-07-14 | Make PostgreSQL movements/balances/genealogy the Phase 4 material authority and treat external snapshots as observations requiring reconciliation | `adr/ADR-0004-phase4-material-flow-authority.md` | Accepted for Phase 4 |
| 2026-07-14 | Make PostgreSQL inspection/measurement/Hold/disposition the Phase 5 quality authority and deny AI release | `adr/ADR-0005-phase5-quality-authority.md` | Accepted for Phase 5 |
| 2026-07-14 | Make PostgreSQL Maintenance Order/verification and Tool event records the Phase 6 authority; alarms and AI remain non-authoritative | `adr/ADR-0006-phase6-maintenance-authority.md` | Accepted for Phase 6 |

This log is an index. Security, data, migration, rollback, consequences, and evidence
remain in the linked gate/ADR records.
