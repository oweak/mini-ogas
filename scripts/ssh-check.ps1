$plink = "C:\Program Files\PuTTY\plink.exe"
if (-not (Test-Path $plink)) {
    Write-Host "plink not found"
    exit 1
}
$env:PATH = $env:PATH + ";C:\Program Files\PuTTY"

Write-Host "=== VM Hostnamectl ==="
echo y | & $plink -pw 12345678 root@192.168.1.5 "hostnamectl" 2>&1

Write-Host "=== IP Addresses ==="
echo y | & $plink -pw 12345678 root@192.168.1.5 "ip -4 addr show | grep inet" 2>&1

Write-Host "=== Disk Usage ==="
echo y | & $plink -pw 12345678 root@192.168.1.5 "df -h /" 2>&1
