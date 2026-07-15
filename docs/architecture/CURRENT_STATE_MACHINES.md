# Current State Of Machines And Processes

## Audit Snapshot

| Field | Observation |
|---|---|
| Audit date | 2026-07-14 |
| Active deployment | One Windows host, native processes |
| Workshop deployment | `NODE_DEPLOYMENT_MODE=process` |
| Workshop engine | SimPy |
| Expected production nodes | turning, milling, grinding |
| Active production nodes | 3/3 during runtime check |
| Active virtual machines | None; five VMs are registered in the default VirtualBox profile but powered off |
| Physical machines connected | None |

## Host

| Item | Observed value |
|---|---|
| OS | Windows 11 Home (Chinese), version family `10.0.26200` |
| CPU | Intel Core i7-13700H |
| RAM | Approximately 15.8 GB |
| Python | 3.13.6 authoritative PATH runtime |
| Go | 1.26.4 |
| Node.js | 24.13.0 |
| npm | 11.6.2 |
| VirtualBox | Installed |
| Windows Time | Stopped/manual at audit time |
| WLAN | `192.168.1.6/24` observed |
| Host-only adapter | `169.254.173.15/16` APIPA observed; not a validated lab subnet |

## Active Process Topology

The Go supervisor reported 9/9 configured process definitions healthy. The canonical runtime included:

| Process/service | Endpoint | Role | Reality boundary |
|---|---|---|---|
| `central-api` | `127.0.0.1:8080` | REST, orchestration, state/audit | Local API, not HA |
| `ai-dispatcher` | `127.0.0.1:8081` | Provider dispatch | External DeepSeek after unlock; proposal only |
| `market-simulator` | `127.0.0.1:8082` | Moving market input | Random simulation |
| `production-planner` | `127.0.0.1:8083` | Rule-based planning | Prototype planner, not APS |
| `dashboard` | `127.0.0.1:5173` | Operator UI | Simulated/seeded projection |
| `turning-simpy-node` | outbound heartbeat | Turning model | Local Python simulation |
| `milling-simpy-node` | outbound heartbeat | Milling model | Local Python simulation |
| `grinding-simpy-node` | outbound heartbeat | Grinding model | Local Python simulation |
| Go supervisor | `127.0.0.1:9099` | Process ownership/health | Development supervision only |

Infrastructure listeners:

| Service | Listener | Observation |
|---|---|---|
| NATS | `127.0.0.1:4222` | Loopback only, shadow mode |
| NATS monitoring | `127.0.0.1:8222` | Loopback only |
| PostgreSQL | `listen_addresses=*`, port 5432, SSL off | `pg_hba.conf` permits only localhost/loopback SCRAM; still bind/firewall explicitly before multi-host work |

PostgreSQL should be bound/firewalled consistently with its intended zone before any multi-host pilot.

## VirtualBox Inventory

| VM | Guest/profile | CPU/RAM | Network | State during audit | Current role |
|---|---|---:|---|---|---|
| `ogas-central` | Ubuntu | 2 CPU / 4096 MB | Bridged + host-only | Powered off | Planned central host; not active |
| `miniogas-turning` | Ubuntu | 1 CPU / 1024 MB | NAT, SSH forward 2221 | Powered off | Planned edge lab node; not active |
| `miniogas-milling` | Ubuntu | 1 CPU / 1024 MB | NAT, SSH forward 2222 | Powered off | Planned edge lab node; not active |
| `miniogas-grinding` | Ubuntu | 1 CPU / 1024 MB | NAT, SSH forward 2223 | Powered off | Planned edge lab node; not active |
| `miniogas-kali-redteam` | Debian/Kali | 2 CPU / 4096 MB | NAT + host-only, SSH forward 2224 | Powered off in default profile | Security lab only; not active |

The active UI/API must not report these VMs as connected workshop nodes. VM existence is inventory, not runtime health. The authoritative startup profile uses a separate VirtualBox home and currently reports the Kali VM as not registered there even though the default profile lists it. That profile split must be reconciled before any lab workflow is claimed runnable.

## Workshop Profiles

Current SimPy tests encode these model profiles:

| Workshop | Model machine count | Process time | Approx. nominal capacity |
|---|---:|---:|---:|
| Turning | 3 | 135 s | 80 parts/hour |
| Milling | 2 | 144 s | 50 parts/hour |
| Grinding | 2 | 111 s | 65 parts/hour |

These are simulation configuration facts. They are not measured specifications for a real machine and require calibration/OT approval before use in planning or control.

## Operational Findings

1. The current runtime is single-failure-domain despite process names suggesting distributed nodes.
2. The host-only adapter has an APIPA address, so the intended VM lab network is not proven usable.
3. Host clock service is not governed for multi-host event ordering.
4. PostgreSQL, NATS and all application processes share one host.
5. The local `.venv` and PATH Python differ in installed dependencies.
6. No process/device connector reports an actual PLC/CNC serial, endpoint, certificate or tag map.
7. No physical emergency stop, network isolation or maintenance dispatch integration exists.
8. Windows Time remains `Stopped/Manual`; `w32tm` cannot report synchronization while the service is stopped.
9. A real DeepSeek provider smoke call passed after administrator unlock, but AI remains proposal/explanation only.
10. PostgreSQL event sequence writes now serialize/rebase overlapping Central writers; this fixes a local consistency incident but is not multi-host HA evidence.

## Evidence Commands

The snapshot was established with the repository status/startup scripts, Windows process/port inspection, VirtualBox `VBoxManage list vms`/`showvminfo`, runtime APIs and PostgreSQL queries. Re-run those checks before relying on this file; it is a dated snapshot, not dynamic discovery.
