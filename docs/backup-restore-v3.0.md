# Mini-OGAS v3.0 Backup and Restore Contract

> Contract version: 3.0.0
> Durable central source: PostgreSQL
> Durable edge source: node SQLite plus outbox

## 1. Objectives

This contract protects central historical facts, edge-local execution state, replayable outboxes, configuration, and evidence required to prove a restore. A file copy is not a successful backup until its checksum, metadata, and restore drill pass.

| Data class | RPO | RTO | Authority |
|---|---:|---:|---|
| PostgreSQL central facts | 24 hours in v3.0 lab; 15 minutes before production release | 60 minutes | PostgreSQL |
| edge SQLite/outbox | 24 hours plus unsent outbox retained locally | 30 minutes per node | owning edge |
| JetStream shadow data | best effort in v3.0.1; rebuild/replay from accepted facts | 30 minutes | transport only |
| Redis projection | zero backup requirement | 30 minutes to rebuild | cache only |
| configuration and manifests | after every approved change | 30 minutes | Git plus restricted deployment bundle |

## 2. Storage layout

All backup artifacts use D-backed storage. C drive is prohibited because only approximately 2.3 GiB was free during the baseline audit.

```text
D:\MiniOGAS-VMs\backups\
  postgres\YYYY\MM\DD\
  edges\{node_code}\YYYY\MM\DD\
  config\YYYY\MM\DD\
  restore-drills\YYYY\MM\DD-HHMMSS\
  manifests\
```

Each backup set contains:

- the data artifact;
- `manifest.json` with type, source identity, start/end time, tool version, schema version, run ID where applicable, byte size, and SHA-256;
- `verify.txt` with non-secret command results;
- an immutable audit row recording the backup ID and result.

Backup directories grant access only to the backup service account and administrators. AI keys, JWT secrets, edge tokens, and private CA keys are not included in database or SQLite archives.

## 3. PostgreSQL backup policy

### 3.1 Lab baseline

The v3.0 lab MUST create:

- one nightly custom-format logical backup with `pg_dump -Fc`;
- one backup immediately before every schema migration or v3 phase change;
- retention of 7 daily, 4 weekly, and 3 monthly verified backups;
- a SHA-256 manifest generated after `pg_restore --list` succeeds;
- one restore drill every month and before a release gate.

The PostgreSQL 16 tools are installed at `C:\Program Files\PostgreSQL\16\bin`, but output MUST be written to D.

Example PowerShell procedure:

```powershell
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$target = "D:\MiniOGAS-VMs\backups\postgres\$stamp"
New-Item -ItemType Directory -Force -Path $target | Out-Null

# POSTGRES_DSN is loaded from the restricted runtime secret file and never printed.
& 'C:\Program Files\PostgreSQL\16\bin\pg_dump.exe' `
  --dbname $env:POSTGRES_DSN `
  --format custom `
  --no-owner `
  --no-privileges `
  --file "$target\mini_ogas.dump"

if ($LASTEXITCODE -ne 0) { throw 'pg_dump failed' }
& 'C:\Program Files\PostgreSQL\16\bin\pg_restore.exe' `
  --list "$target\mini_ogas.dump" | Set-Content "$target\catalog.txt"
if ($LASTEXITCODE -ne 0) { throw 'pg_restore catalog verification failed' }
Get-FileHash "$target\mini_ogas.dump" -Algorithm SHA256
```

The operational script added in a later phase MUST avoid putting the DSN on a process command line where possible. A protected PostgreSQL password file or service definition is preferred.

### 3.2 Production release target

Before a production claim, add weekly physical base backup plus continuous WAL archiving with a 15-minute maximum archive gap. The release gate must demonstrate point-in-time recovery into a separate PostgreSQL instance. Until that evidence exists, the documented RPO remains 24 hours.

### 3.3 Consistency rules

- Backup runs against PostgreSQL, never against a copied live data directory.
- Schema and data are captured in the same logical dump.
- `event_store`, `audit_logs`, `heartbeat_shadow`, `command_shadow`, `runs`, and `scenarios` MUST be present in the backup catalog.
- A backup is rejected if table count or required-table checks fail.
- A migration backup is retained until that migration has passed a restore drill.

## 4. Edge SQLite backup policy

Canonical edge paths:

```text
/var/lib/mini-ogas/node.db
/var/lib/mini-ogas/outbox/
```

The current process-mode equivalents are:

```text
D:\MiniOGAS-VMs\vm-turning-workshop-01\node.db
D:\MiniOGAS-VMs\vm-milling-workshop-01\node.db
D:\MiniOGAS-VMs\vm-grinding-workshop-01\node.db
```

Each edge MUST create a nightly online backup using the SQLite backup API, not a blind copy of an active database. Before backup:

1. stop accepting a new command claim for at most 30 seconds;
2. finish or persist the current transaction;
3. run `PRAGMA wal_checkpoint(TRUNCATE)`;
4. execute `.backup` to a temporary file;
5. run `PRAGMA integrity_check` against the temporary file;
6. atomically rename it to the final backup name;
7. hash the database and copy the outbox manifest;
8. resume command claims.

Linux example:

```bash
set -euo pipefail
src=/var/lib/mini-ogas/node.db
dst=/var/backups/mini-ogas/node-$(date -u +%Y%m%dT%H%M%SZ).db
sqlite3 "$src" 'PRAGMA wal_checkpoint(TRUNCATE);'
sqlite3 "$src" ".backup '$dst.tmp'"
test "$(sqlite3 "$dst.tmp" 'PRAGMA integrity_check;')" = "ok"
mv "$dst.tmp" "$dst"
sha256sum "$dst" > "$dst.sha256"
```

Retain 7 daily and 4 weekly edge backups. A node MUST NOT delete unsynchronized outbox rows merely because a backup succeeded.

## 5. Configuration backup

The following non-secret artifacts belong in Git and the deployment evidence bundle:

- frozen v3 contracts;
- NATS server configuration with credential references, not values;
- supervisor configuration;
- PostgreSQL migration identifiers;
- VM resource and NIC export;
- firewall rules;
- software versions.

Restricted secret material is backed up separately using encrypted administrator-controlled storage. It MUST NOT share the ordinary backup manifest or repository.

## 6. PostgreSQL restore procedure

Restore is always performed into a new empty database first.

1. Select the newest backup whose SHA-256 and catalog checks pass.
2. Record the incident/change ID and stop Central writers.
3. Create a new database such as `mini_ogas_restore_YYYYMMDD`.
4. Restore with `--clean --if-exists --no-owner --no-privileges` only against that new database.
5. Run schema, constraint, row-count, and semantic verification.
6. Start a temporary Central API against the restored database on a non-production port.
7. Verify health, snapshot, event replay order, command state, and audit retrieval.
8. Promote by changing the protected DSN and restarting Central under the supervisor.
9. Keep the old database read-only until the observation window ends.

Example:

```powershell
& 'C:\Program Files\PostgreSQL\16\bin\createdb.exe' `
  --maintenance-db $env:POSTGRES_ADMIN_DSN mini_ogas_restore_20260713

& 'C:\Program Files\PostgreSQL\16\bin\pg_restore.exe' `
  --dbname $env:POSTGRES_RESTORE_DSN `
  --clean --if-exists --no-owner --no-privileges `
  'D:\MiniOGAS-VMs\backups\postgres\<backup-id>\mini_ogas.dump'
```

Never restore directly over the only live database.

## 7. Edge SQLite restore procedure

1. Isolate the node from new dispatches.
2. Stop the edge agent and preserve the failed database, WAL, SHM, and outbox as an incident bundle.
3. Verify the selected backup checksum and `PRAGMA integrity_check`.
4. Restore it to a new path and apply owner/mode restrictions.
5. Start the edge agent in `recovery` mode with command execution disabled.
6. Confirm node identity, local schema version, last acknowledged command, and outbox sequence.
7. Replay unsent records through `POST /node-records/sync` using original idempotency keys.
8. Confirm Central accepts duplicates without creating duplicate facts.
9. Re-enable command claims and require three healthy heartbeats before `online`.

An edge restore MUST NOT reset a command ID, outbox local sequence, `run_id`, or original request ID.

## 8. Restore verification

### 8.1 PostgreSQL checks

Required checks:

- database connection and server version;
- expected migration version;
- required tables and indexes;
- no duplicate `event_id`;
- no duplicate `(source_node, run_id, local_sequence)`;
- monotonic global sequence within each accepted replay policy;
- command status and verifier evidence preserved;
- latest run/scenario references valid;
- dashboard snapshot reports `data_source=live` only when reading the restored PostgreSQL instance.

Example invariant queries:

```sql
SELECT event_id, count(*) FROM event_store GROUP BY event_id HAVING count(*) > 1;
SELECT source_node, run_id, local_sequence, count(*)
FROM event_store
GROUP BY source_node, run_id, local_sequence
HAVING count(*) > 1;
```

Both queries MUST return zero rows.

### 8.2 SQLite checks

- `PRAGMA integrity_check` returns `ok`;
- required tables and indexes exist;
- outbox sequence never moves backward;
- applied command IDs remain unique;
- node code matches the certificate and runtime configuration;
- a new heartbeat and one harmless test record reach Central.

## 9. Restore drill evidence

A restore drill is complete only when the evidence bundle includes:

| Evidence | Required |
|---|---|
| backup and manifest IDs | yes |
| start/end timestamps and operator | yes |
| tool and server versions | yes |
| checksum verification | yes |
| restore command exit codes | yes |
| invariant query results | yes |
| Central health and snapshot excerpt without secrets | yes |
| edge heartbeat/replay evidence, when applicable | yes |
| achieved RPO/RTO | yes |
| cleanup decision and approval | yes |

## 10. Current baseline status

As of the v3.0.0 audit:

- PostgreSQL 16 backup utilities exist on the host;
- no canonical backup directory exists;
- no scheduled PostgreSQL or SQLite backup is verified;
- no restore-drill evidence exists;
- the three current SQLite databases are on D and can be incorporated into the policy;
- static SQL and live PostgreSQL schema differ, so fresh-database reproducibility is not yet proven.

This document completes the backup/restore **contract**, not the automation. A v3.0 release claim remains blocked until a real backup and restore drill pass.

## 11. Failure and rollback

If a backup fails, retain the previous verified backup, emit one deduplicated alert, and do not delete retention candidates. If a restore verification fails, keep production on the old database or node image, quarantine the failed restore, and attach its evidence to the incident. A failed restore MUST never be promoted because the service merely starts.
