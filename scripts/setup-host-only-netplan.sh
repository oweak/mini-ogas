#!/bin/bash
# Configure Host-Only network via netplan on Ubuntu 24.04
cat > /tmp/01-netcfg.yaml << 'EOF'
network:
  version: 2
  renderer: networkd
  ethernets:
    enp0s8:
      dhcp4: true
EOF

echo 12345678 | sudo -S cp /tmp/01-netcfg.yaml /etc/netplan/01-netcfg.yaml
echo 12345678 | sudo -S chmod 600 /etc/netplan/01-netcfg.yaml
echo 12345678 | sudo -S netplan apply
echo "=== Done ==="
ip -4 addr show dev enp0s8
