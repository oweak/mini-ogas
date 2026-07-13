param(
  [switch]$SkipRuntime,
  [switch]$RequireAiUnlocked
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
. (Join-Path $PSScriptRoot "env.ps1")

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
  Invoke-Step "Python simulator tests" {
    Push-Location .\services\node-agent
    try { python -m pytest .\test_simulator.py -q } finally { Pop-Location }
  }
  Invoke-Step "Go node-agent tests" {
    Push-Location .\services\node-agent
    try { go test ./... } finally { Pop-Location }
  }
  Invoke-Step "Go supervisor tests" {
    Push-Location .\services\supervisor
    try { go test ./... } finally { Pop-Location }
  }
  Invoke-Step "AI dispatcher tests" {
    Push-Location .\services\ai-dispatcher
    try { python -m pytest .\tests -q } finally { Pop-Location }
  }
  Invoke-Step "CLI and workflow tests" {
    python -m pytest .\tools\mogas\tests .\scripts\test_check_secrets.py .\scripts\test_kali_redteam_workflow.py -q
  }
  Invoke-Step "dashboard tests and build" {
    Push-Location .\services\dashboard
    try { npm.cmd run test -- --run; npm.cmd run build } finally { Pop-Location }
  }
  if (Get-Command ruff -ErrorAction SilentlyContinue) {
    Invoke-Step "Python lint" { ruff check .\services .\scripts .\tools }
  } else {
    Write-Host "==> Python lint skipped: install ruff to enable the optional local lint gate"
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
