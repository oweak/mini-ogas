param(
  [string]$Root = "D:\MiniOGAS-VMs"
)

$ErrorActionPreference = "SilentlyContinue"

Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -and $_.CommandLine -match "simulator.py" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

$owners = Get-NetTCPConnection -LocalPort 8080 -State Listen | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($owner in $owners) {
  Stop-Process -Id $owner -Force
}

Write-Host "Stopped Mini-OGAS Python node-agent and central-api processes."
