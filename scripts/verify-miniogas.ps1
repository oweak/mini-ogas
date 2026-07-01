param(
  [switch]$SkipRuntime,
  [switch]$RequireAiUnlocked
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")

function Invoke-Step {
  param([string]$Name, [scriptblock]$Action)
  Write-Host "==> $Name"
  & $Action
  if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE" }
}

Push-Location $ProjectRoot
try {
  Invoke-Step "API contract check" { python .\scripts\check_api_contract.py }
  Invoke-Step "dashboard gate check" { python .\scripts\check_dashboard_gate.py }
  Invoke-Step "secret scan" { python .\scripts\check_secrets.py }
  Invoke-Step "secret scan tests" { python .\scripts\test_check_secrets.py }
  Invoke-Step "central-api tests" {
    Push-Location .\services\central-api
    try { python -m pytest -q } finally { Pop-Location }
  }
  Invoke-Step "node-agent tests" {
    Push-Location .\services\node-agent
    try { python .\test_simulator.py } finally { Pop-Location }
  }
  Invoke-Step "dashboard tests and build" {
    Push-Location .\services\dashboard
    try { npm.cmd run test -- --run; npm.cmd run build } finally { Pop-Location }
  }
  if (-not $SkipRuntime) {
    $runtimeArgs = @("-File", (Join-Path $ProjectRoot "scripts\start-system.ps1"), "-CheckOnly")
    if ($RequireAiUnlocked) { $runtimeArgs += "-RequireAiApi" }
    Invoke-Step "strict runtime check" { & powershell.exe -NoProfile -ExecutionPolicy Bypass @runtimeArgs }
  }
} finally {
  Pop-Location
}

Write-Host "Mini-OGAS verification complete."
