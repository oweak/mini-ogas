$env:VBOX_USER_HOME = "D:\VBoxVMs\.VirtualBox"
$vb = "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"

Write-Host "=== Creating disk ==="
& $vb createmedium disk `
    --filename "D:\VBoxVMs\ogas-central\ogas-central.vdi" `
    --size 25600 --format VDI --variant Standard 2>&1

Write-Host "=== Adding SATA controller ==="
& $vb storagectl "ogas-central" `
    --name "SATA" --add sata --controller IntelAhci --portcount 2 2>&1

Write-Host "=== Attaching disk ==="
& $vb storageattach "ogas-central" `
    --storagectl "SATA" --port 0 --device 0 `
    --type hdd --medium "D:\VBoxVMs\ogas-central\ogas-central.vdi" 2>&1

Write-Host "=== Attaching ISO ==="
& $vb storageattach "ogas-central" `
    --storagectl "SATA" --port 1 --device 0 `
    --type dvddrive --medium "C:\Users\hq362\Downloads\ubuntu-24.04.3-live-server-amd64.iso" 2>&1

Write-Host "=== STORAGE DONE ==="
