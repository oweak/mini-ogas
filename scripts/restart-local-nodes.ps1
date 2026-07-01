$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$NodeAgentDir = Join-Path $ProjectRoot "services\node-agent"

$tokenPath = "D:\MiniOGAS-VMs\miniogas-token.txt"
$token = (Get-Content -LiteralPath $tokenPath -Raw).Trim()
$sessionToken = $env:OGAS_SESSION_TOKEN

python -m pip show simpy *> $null
if ($LASTEXITCODE -ne 0) {
  python -m pip install simpy==4.1.1 | Out-Host
}

$nodes = @(
  @{ Path = "D:\MiniOGAS-VMs\vm-turning-workshop-01"; Node = "turning-workshop-01"; Type = "turning"; Engine = "simpy"; Seed = "20260611"; Scenario = "SCN-TURNING-SIMPY-FLOW-001" },
  @{ Path = "D:\MiniOGAS-VMs\vm-milling-workshop-01"; Node = "milling-workshop-01"; Type = "milling"; Engine = "simpy"; Seed = "20260613"; Scenario = "SCN-MILLING-SIMPY-SINGLE-001" },
  @{ Path = "D:\MiniOGAS-VMs\vm-grinding-workshop-01"; Node = "grinding-workshop-01"; Type = "grinding"; Engine = "simpy"; Seed = "20260615"; Scenario = "SCN-GRINDING-SIMPY-FLOW-001" }
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
  Copy-Item -LiteralPath (Join-Path $NodeAgentDir "simulator.py") -Destination (Join-Path $path "simulator.py") -Force
  $command = @"
`$env:NODE_CODE='$($node.Node)'
`$env:WORKSHOP_TYPE='$($node.Type)'
`$env:CENTRAL_API_URL='http://127.0.0.1:8080'
`$env:OGAS_API_TOKEN='$token'
`$env:OGAS_SESSION_TOKEN='$sessionToken'
`$env:LOCAL_DB_PATH='$path\node.db'
`$env:HEARTBEAT_SEC='5'
`$env:EMERGENCY_AFTER_TICKS='18'
`$env:SIMULATION_MODE='normal'
`$env:SIMULATION_ENGINE='$($node.Engine)'
`$env:SIMULATION_SPEED='1'
`$env:SIMULATION_RANDOM_SEED='$($node.Seed)'
`$env:OGAS_RUN_ID='RUN-LOCAL-$(Get-Date -Format yyyyMMdd)-001'
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
  -Headers @{ "X-OGAS-Token" = $token } `
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
