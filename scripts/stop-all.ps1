param(
  [int]$TimeoutSeconds = 20
)

$ErrorActionPreference = "Stop"

function Get-PortProcessIds {
  param([Parameter(Mandatory = $true)][int]$Port)
  $ids = @()
  foreach ($line in @(& netstat -ano -p tcp 2>$null)) {
    if ($line -notmatch "LISTENING") { continue }
    $parts = @($line.Trim() -split "\s+")
    if ($parts.Count -lt 5 -or $parts[1] -notmatch ":$Port$") { continue }
    $candidate = $parts[-1]
    if ($candidate -match "^\d+$" -and $candidate -ne "0") {
      $ids += [int]$candidate
    }
  }
  return @($ids | Select-Object -Unique)
}

$managedPorts = @(9099, 8080, 8081, 8082, 8083, 8084, 5173, 4222, 6379, 9000)
$gracefulRequested = $false

if (@(Get-PortProcessIds -Port 9099).Count -gt 0) {
  try {
    Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:9099/supervisor/stopall" -TimeoutSec 5 | Out-Null
    $gracefulRequested = $true
  } catch {
    Write-Warning "Supervisor stop request failed; guarded process cleanup will be used."
  }
}

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
do {
  $remaining = @()
  foreach ($port in $managedPorts) {
    if (@(Get-PortProcessIds -Port $port).Count -gt 0) { $remaining += $port }
  }
  if ($remaining.Count -eq 0) { break }
  Start-Sleep -Milliseconds 250
} while ((Get-Date) -lt $deadline)

$forcedPids = @()
foreach ($port in $managedPorts) {
  foreach ($processId in @(Get-PortProcessIds -Port $port)) {
    if ($forcedPids -contains $processId) { continue }
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    $forcedPids += $processId
  }
}

Start-Sleep -Milliseconds 500
$stillListening = @()
foreach ($port in $managedPorts) {
  if (@(Get-PortProcessIds -Port $port).Count -gt 0) { $stillListening += $port }
}
if ($stillListening.Count -gt 0) {
  throw "Mini-OGAS shutdown incomplete; listening ports: $($stillListening -join ', ')"
}

[pscustomobject]@{
  status = "stopped"
  supervisor_stop_requested = $gracefulRequested
  forced_process_count = $forcedPids.Count
  checked_ports = $managedPorts
} | ConvertTo-Json
