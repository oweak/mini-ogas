param(
  [string]$RuntimeRoot = "D:\MiniOGAS-VMs",
  [Parameter(Mandatory = $true)][string]$BearerToken
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$NodeAgentDir = Join-Path $ProjectRoot "services\node-agent"

. (Join-Path $PSScriptRoot "node-credentials.ps1")
$nodeCredentialState = Get-MiniOgasNodeCredentialState -RuntimeRoot $RuntimeRoot
$sessionToken = $env:OGAS_SESSION_TOKEN
$runId = "RUN-LOCAL-$(Get-Date -Format yyyyMMdd-HHmmss)"

python -m pip show simpy *> $null
if ($LASTEXITCODE -ne 0) {
  python -m pip install simpy==4.1.1 | Out-Host
}

$nodes = @(
    @{ Path = (Join-Path $RuntimeRoot "vm-turning-workshop-01"); Node = "turning-workshop-01"; Type = "turning"; Engine = "simpy"; Seed = "20260713"; Scenario = "SCN-NORMAL-SIMPY-FLOW-001" },
    @{ Path = (Join-Path $RuntimeRoot "vm-milling-workshop-01"); Node = "milling-workshop-01"; Type = "milling"; Engine = "simpy"; Seed = "20260713"; Scenario = "SCN-NORMAL-SIMPY-FLOW-001" },
    @{ Path = (Join-Path $RuntimeRoot "vm-grinding-workshop-01"); Node = "grinding-workshop-01"; Type = "grinding"; Engine = "simpy"; Seed = "20260713"; Scenario = "SCN-NORMAL-SIMPY-FLOW-001" }
)

Get-CimInstance Win32_Process -Filter "name='python.exe'" |
  Where-Object { $_.CommandLine -match 'simulator.py' } |
  ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force
  }

Start-Sleep -Seconds 1

foreach ($node in $nodes) {
  $path = $node.Path
  New-Item -ItemType Directory -Force -Path $path | Out-Null
  foreach ($sourceName in @("simulator.py", "event_publishers.py", "runtime_adapters.py")) {
    Copy-Item -LiteralPath (Join-Path $NodeAgentDir $sourceName) -Destination (Join-Path $path $sourceName) -Force
  }
  $nodeToken = $nodeCredentialState.Credentials[$node.Node]
  $command = @"
`$env:NODE_CODE='$($node.Node)'
`$env:WORKSHOP_TYPE='$($node.Type)'
`$env:CENTRAL_API_URL='http://127.0.0.1:8080'
`$env:OGAS_API_TOKEN='$nodeToken'
`$env:OGAS_SESSION_TOKEN='$sessionToken'
`$env:LOCAL_DB_PATH='$path\node.db'
`$env:HEARTBEAT_SEC='5'
`$env:EMERGENCY_AFTER_TICKS='18'
`$env:SIMULATION_MODE='normal'
`$env:SIMULATION_ENGINE='$($node.Engine)'
`$env:SIMULATION_SPEED='1'
`$env:SIMULATION_RANDOM_SEED='$($node.Seed)'
`$env:OGAS_RUN_ID='$runId'
`$env:OGAS_SCENARIO_ID='$($node.Scenario)'
`$env:NODE_DEPLOYMENT_MODE='process'
Set-Location -LiteralPath '$path'
python simulator.py *> node-agent.log
"@

  Start-Process `
    -FilePath "C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe" `
    -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command `
    -WorkingDirectory $path `
    -WindowStyle Hidden
}

Start-Sleep -Seconds 8

$reportedNodes = Invoke-RestMethod `
  -Uri "http://127.0.0.1:8080/nodes" `
  -Headers @{ "Authorization" = "Bearer $BearerToken" } `
  -TimeoutSec 20

$expectedCodes = @($nodes | ForEach-Object { $_.Node })
$activeNodes = @($reportedNodes | Where-Object { $_.node_code -in $expectedCodes })
[pscustomobject]@{
  nodes_connected = @($activeNodes | Where-Object { $_.status -in @('online', 'running', 'warning') }).Count
  nodes_expected = $expectedCodes.Count
  nodes = @($activeNodes | ForEach-Object {
    "$($_.node_code):$($_.status):$($_.last_heartbeat)"
  })
} | ConvertTo-Json
