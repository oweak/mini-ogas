# Mini-OGAS IP Allocation

## Host Machine
- Wi-Fi (bridged): 192.168.1.4/24
- Host-Only: 192.168.56.1/24

## Central VM: ogas-central
- Bridged (enp0s3): 192.168.1.5/24 (DHCP from router)
- Host-Only (enp0s8): 192.168.56.10/24 (static)

## Future Workshop VMs (planned)
- turning-workshop: 192.168.56.11 (Host-Only static)
- milling-workshop: 192.168.56.12 (Host-Only static)
- grinding-workshop: 192.168.56.13 (Host-Only static)
