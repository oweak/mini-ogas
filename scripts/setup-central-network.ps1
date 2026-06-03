$env:VBOX_USER_HOME = "D:\VBoxVMs\.VirtualBox"
$vb = "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"

Write-Host "=== NIC 1: Bridged (Wi-Fi) ==="
& $vb modifyvm "ogas-central" `
    --nic1 bridged `
    --bridgeadapter1 "Intel(R) Wi-Fi 6E AX211 160MHz" `
    --nictype1 82540EM `
    --cableconnected1 on 2>&1

Write-Host "=== NIC 2: Host-Only ==="
& $vb modifyvm "ogas-central" `
    --nic2 hostonly `
    --hostonlyadapter2 "VirtualBox Host-Only Ethernet Adapter" `
    --nictype2 82540EM `
    --cableconnected2 on 2>&1

Write-Host "=== NETWORK DONE ==="
