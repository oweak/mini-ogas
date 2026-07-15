# Mini-OGAS v3.0 Deployment Contract

> Contract version: 3.0.0
> Status: frozen for phased implementation
> Scope: VM roles, resource limits, ports, credentials, time, certificates, failure states, and preflight gates

## 1. Contract language

The words **MUST**, **MUST NOT**, **SHOULD**, and **MAY** are normative. A phase may not report completion when a MUST item is missing. Current-process simulation and future VM deployment must remain visibly distinguishable.

## 2. Deployment invariants

1. PostgreSQL owns central historical facts.
2. Edge SQLite stores edge-local state and a replayable outbox only; it is not a central substitute.
3. NATS transports schema-valid events. It does not own business truth.
4. Redis, when introduced, is a rebuildable current-state projection only.
5. REST remains available throughout v3.0.1 and later migration phases until a separately approved removal gate exists.
6. SimPy and edge agents create production facts; the dashboard never creates operational facts.
7. LLM output is explanation or proposal, never a direct state mutation.
8. Every state-changing command follows Safety Governor, approval where required, Command Manager, idempotent edge execution, result reporting, and verifier observation.
9. A powered-off VM, a local process, a fallback payload, and a live edge VM MUST have different `data_source` and deployment-state labels.
10. Runtime secrets MUST reside outside Git and MUST NOT appear in logs, reports, command output, or NATS payloads.

## 3. VM inventory and roles

The canonical v3 names below are stable logical names. Existing VirtualBox names may be mapped during migration, but API and certificate identities MUST use the canonical names.

| Canonical VM | Role | vCPU | RAM | System disk | Data disk | Required services |
|---|---|---:|---:|---:|---:|---|
| `ogas-central` | coordination and durable central facts | 2 | 4 GiB | 32 GiB | 40 GiB | Central API, PostgreSQL, NATS JetStream, supervisor, dashboard, AI dispatcher, planner, market simulator |
| `ogas-turning-edge` | turning operation and local execution | 1 | 1 GiB | 16 GiB | 8 GiB | edge agent, SimPy turning runtime, SQLite outbox |
| `ogas-milling-edge` | milling operation and local execution | 1 | 1 GiB | 16 GiB | 8 GiB | edge agent, SimPy milling runtime, SQLite outbox |
| `ogas-grinding-edge` | grinding operation and local execution | 1 | 1 GiB | 16 GiB | 8 GiB | edge agent, SimPy grinding runtime, SQLite outbox |

Optional lab guest:

| Canonical VM | Role | vCPU | RAM | Disk | Constraint |
|---|---|---:|---:|---:|---|
| `ogas-kali-redteam` | authorized local attack-lab controller | 2 | 4 GiB | 40 GiB | powered off outside a declared lab window; no direct PostgreSQL, Redis, or administrative credential |

Resource rules:

- Memory is a hard allocation, not a ballooning target.
- Central PostgreSQL and JetStream data MUST use the D-backed virtual data disk.
- JetStream storage MUST be a local filesystem, not an SMB/NFS/network share.
- The current 16 GiB host MUST NOT start all five guests together while the eight-process host runtime is active. Allowed profiles are `host-process`, `four-vm-production`, and `attack-lab`; only one profile may own service ports at a time.
- Swap MAY absorb a short spike but MUST NOT be used to claim that an undersized VM meets the contract.

## 4. Network interfaces

### 4.1 Production VM interfaces

| VM | NIC 1 | NIC 2 | Bridged NIC |
|---|---|---|---|
| `ogas-central` | NAT, outbound updates/NTP/AI API | Host-Only `ogas-mgmt`, `192.168.56.10/24` | prohibited by default |
| `ogas-turning-edge` | NAT, outbound updates/NTP | Host-Only `ogas-mgmt`, `192.168.56.11/24` | prohibited |
| `ogas-milling-edge` | NAT, outbound updates/NTP | Host-Only `ogas-mgmt`, `192.168.56.12/24` | prohibited |
| `ogas-grinding-edge` | NAT, outbound updates/NTP | Host-Only `ogas-mgmt`, `192.168.56.13/24` | prohibited |

`ogas-kali-redteam` uses NAT plus a dedicated Internal Network named `ogas-attack-lab`. A production edge receives a temporary third NIC on that Internal Network only during an approved, logged test. The central VM MUST NOT attach to `ogas-attack-lab`.

### 4.2 Port ownership

| Port | Bind address on central | Owner | Allowed source | Purpose |
|---:|---|---|---|---|
| 22/tcp | `192.168.56.10` | SSH | host `192.168.56.1` only | administration |
| 5173/tcp | `192.168.56.10` | dashboard | host only | development dashboard; production may be served by 8080 |
| 8080/tcp | `192.168.56.10` | Central API | host and three edges | REST control and compatibility path |
| 8081-8083/tcp | `127.0.0.1` | internal services | central only | AI, market, planner |
| 9099/tcp | `127.0.0.1` | supervisor | central only | local process control |
| 4222/tcp | `192.168.56.10` | NATS client | host and three edges with mTLS | event transport |
| 6222/tcp | closed | reserved | none in single-node phase | future NATS cluster route |
| 8222/tcp | `127.0.0.1` | NATS monitor | central only | monitoring; no Internet exposure |
| 5432/tcp | `127.0.0.1` | PostgreSQL | central only | central durable facts |
| 6379/tcp | `127.0.0.1` | Redis, future | central only | rebuildable projection |

Edges expose only SSH on the management NIC. Agents initiate connections to Central; no edge application listener is required.

## 5. Agent Protocol transport

The normative payload schemas are in `docs/contracts-v3.0.md`.

### 5.1 REST compatibility paths

| Function | Canonical path | Rule |
|---|---|---|
| Heartbeat | `POST /agents/{node_code}/heartbeat` | authoritative during v3.0.1 shadow mode |
| Command claim | `GET /agents/{node_code}/commands/pending` | retained until a later gated migration |
| Command result | `POST /commands/{command_id}/result` | retained |
| Offline replay | `POST /node-records/sync` | retained and idempotent |

`POST /node-heartbeats` remains a deprecated wrapper only. It MUST emit deprecation metadata and MUST NOT acquire new features.

### 5.2 NATS subjects

| Subject | Producer | Consumer | Persistence |
|---|---|---|---|
| `ogas.events.{event_type}.{node_code}` | central or authorized edge | durable event worker | JetStream |
| `ogas.heartbeats.{node_code}` | central shadow publisher, later edge | durable heartbeat worker | JetStream |
| `ogas.commands.{node_code}` | central only | node-specific durable consumer, later phase | JetStream |
| `ogas.audit.{resource_type}` | central only | durable audit worker | JetStream |

Subject tokens MUST be lower-case ASCII and match `[a-z0-9][a-z0-9_-]{0,63}`. User-provided strings MUST NOT be interpolated before validation. Wildcard characters, whitespace, path separators, and empty tokens are forbidden.

## 6. Credential scopes

Credentials are identities, not shared environment aliases.

### 6.1 `edge-token`

Each edge receives a unique credential bound to exactly one `node_code`.

Allowed:

- REST heartbeat and offline replay for its own node;
- claim and report its own commands;
- NATS publish to its own heartbeat and approved event subjects;
- NATS subscribe to `ogas.commands.{own_node_code}` only.

Forbidden:

- another node's subjects or REST path;
- audit publication;
- PostgreSQL, Redis, supervisor, AI-provider, or dashboard administration;
- creating or approving commands;
- reading another node's state.

### 6.2 `central-token`

The central service identity may publish all four normative subject families, create durable consumers, query NATS account state, and invoke internal service routes. It MUST NOT be embedded in a dashboard bundle or copied to an edge.

### 6.3 `attack-lab-token`

The attack-lab identity is disabled by default and has an expiry of at most two hours. It may invoke only explicitly enabled lab-control routes and publish only under `ogas.lab.attack.>` if that subject family is introduced. It cannot publish production heartbeat, command, event, or audit subjects and cannot subscribe to commands or business data.

### 6.4 Rotation and storage

- Runtime credentials MUST be stored under a restricted D-drive secret directory or the guest's root-only secret store.
- Edge credentials MUST be different from dashboard JWT secrets and AI API keys.
- Rotate at least every 90 days and immediately after a suspected compromise.
- Support overlap of old/new credentials for no more than 15 minutes.
- Logs record credential identity/fingerprint, never the credential value.

The current single shared node secret is a known pre-v3 condition and MUST be removed before non-loopback edge publishing.

## 7. Time synchronization

- All VMs MUST run `chrony` or `systemd-timesyncd` through the NAT interface.
- All VMs MUST use the same primary upstream and at least one fallback. The deployment default is `time.cloudflare.com` plus the regional NTP pool.
- Windows orchestration host MUST run `W32Time` automatically.
- Normal clock offset: at most 500 ms.
- Hard event-ingest gate: offset greater than 2 seconds marks the node `time_unsynchronized`; events remain durable but are excluded from strict event-time ordering until corrected.
- A node MUST report its measured offset, synchronization source, and last successful sync in runtime metadata.
- Event envelopes carry both producer `event_time` and central `ingest_time`; consumers MUST NOT overwrite either.

## 8. Certificate policy

The project uses a private self-signed CA for the isolated lab deployment.

| Artifact | Lifetime | Location |
|---|---:|---|
| offline root CA | 10 years | encrypted offline directory, not mounted by services |
| intermediate issuing CA | 2 years | central restricted certificate directory |
| server/edge leaf certificate | 90 days | owning VM only |

Requirements:

- mTLS is mandatory for any NATS listener not bound to loopback.
- Central server SANs include `ogas-central`, `192.168.56.10`, and the configured DNS name.
- Edge client certificate subject contains the canonical `node_code`.
- Private keys are non-exportable where supported or mode `0600` on Linux.
- Revocation is implemented through an allowlist of active certificate fingerprints in the initial lab phase.
- v3.0.1 MAY use plaintext only when NATS binds exclusively to `127.0.0.1`; this exception ends before v3.0.3.

## 9. Node liveness state machine

Heartbeat contract cadence is 5 seconds.

| State | Condition | System action |
|---|---|---|
| `online` | last valid heartbeat age `<= 15s` | normal scheduling |
| `stale` | age `> 15s` and `<= 30s` | stop new nonessential dispatch; show degraded state |
| `offline` | age `> 30s` | stop dispatch to node; create one deduplicated incident |
| `isolated` | approved isolation command or security policy | deny commands except restore/diagnostic path |
| `time_unsynchronized` | absolute offset `> 2s` | retain payload, reject strict event-time ordering |

Recovery from `stale` or `offline` requires three consecutive schema-valid heartbeats with increasing sequence numbers. A single heartbeat MUST NOT clear an incident. Flapping is recorded when three state changes occur within five minutes.

## 10. Command guarantees

- `command_id` is globally unique and stable across retries.
- Edge execution is idempotent by `(command_id, version)`.
- Claim lease is 120 seconds unless a command schema states a shorter limit.
- Acknowledgement means received or executed; it is not evidence of physical effect.
- Verifier evidence from subsequent facts determines `effective`, `partial`, `failed`, or `inconclusive`.
- High-risk commands require an authenticated approval and confirmation code.
- Expired commands MUST NOT execute.

## 11. Deployment preflight

Every item below MUST be recorded as `pass`, `fail`, or `not_applicable` with evidence:

- [ ] Host has at least 20 GiB free on D and at least 6 GiB available RAM for the selected run profile.
- [ ] Canonical VM names map to exactly one registered guest each.
- [ ] No conflicting host process owns 5173, 5432, 8080-8083, 9099, 4222, or 8222.
- [ ] `ogas-mgmt` is `192.168.56.0/24`; host is `192.168.56.1`.
- [ ] Central and each edge have the contracted static management address.
- [ ] Bidirectional ICMP and TCP 8080/4222 checks pass where allowed.
- [ ] PostgreSQL reports healthy and accepts a transaction.
- [ ] JetStream store directory is on D-backed local storage and writable by NATS only.
- [ ] Unique edge, central, and attack-lab identities exist; no shared production token remains.
- [ ] NTP is synchronized and absolute offset is at most 500 ms.
- [ ] CA chain, SAN, expiry, and mTLS handshake verify.
- [ ] PostgreSQL and each node SQLite backup exist, have SHA-256 manifests, and have passed the latest restore drill.
- [ ] REST rollback is enabled and tested.
- [ ] Dashboard `data_source` and deployment labels match actual runtime ownership.
- [ ] Canonical tests, `git diff --check`, and strict runtime verification pass.

## 12. Rollback

At any v3 transport phase, set NATS shadow publishing to disabled, stop the NATS worker and server, and leave the REST and PostgreSQL path running. Rollback MUST NOT delete JetStream data, PostgreSQL rows, node SQLite data, or event IDs. A rollback is successful only when a new REST heartbeat is accepted, appears in the live snapshot, and no false `live-nats` label remains.
