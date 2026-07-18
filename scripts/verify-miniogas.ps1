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
  $env:GOMODCACHE = Join-Path $ProjectRoot ".runtime\go-mod-cache"
  $env:GOCACHE = Join-Path $ProjectRoot ".runtime\go-build-cache"
  New-Item -ItemType Directory -Force -Path $env:GOMODCACHE, $env:GOCACHE | Out-Null
  $centralPython = Get-ServicePython "central-api"
  $aiDispatcherPython = Get-ServicePython "ai-dispatcher"
  if (-not (Test-Path -LiteralPath $centralPython)) {
    throw "central-api virtual environment is missing: $centralPython"
  }
  if (-not (Test-Path -LiteralPath $aiDispatcherPython)) {
    throw "ai-dispatcher virtual environment is missing: $aiDispatcherPython"
  }
  Invoke-Step "API contract check" { python .\scripts\check_api_contract.py }
  Invoke-Step "generated OpenAPI and AsyncAPI contract check" { & $centralPython .\tools\export_contracts.py --check }
  Invoke-Step "dashboard gate check" { python .\scripts\check_dashboard_gate.py }
  Invoke-Step "secret scan" { python .\scripts\check_secrets.py }
  Invoke-Step "secret scan tests" { python .\scripts\test_check_secrets.py }
  if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
    Invoke-Step "secret ACL check" { & .\scripts\protect-secrets.ps1 -CheckOnly }
  }
  Invoke-Step "central-api tests" {
    Push-Location .\services\central-api
    try { & $centralPython -m pytest -q } finally { Pop-Location }
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
    try { & $aiDispatcherPython -m pytest .\tests -q } finally { Pop-Location }
  }
  Invoke-Step "Production planner tests" {
    Push-Location .\services\production-planner
    try { & $centralPython -m pytest .\tests -q } finally { Pop-Location }
  }
  Invoke-Step "CLI and workflow tests" {
    python -m pytest .\tools\mogas\tests .\scripts\test_check_secrets.py .\scripts\test_kali_redteam_workflow.py .\scripts\test_runtime_workflow_auth.py .\scripts\test_stage_h_closed_loop.py -q
  }
  Invoke-Step "dashboard tests and build" {
    Push-Location .\services\dashboard
    try { npm.cmd run test -- --run; npm.cmd run build } finally { Pop-Location }
  }
  $ruffExe = Join-Path $ProjectRoot "services\central-api\.venv\Scripts\ruff.exe"
  if (Test-Path -LiteralPath $ruffExe) {
    Invoke-Step "Python correctness lint" { & $ruffExe check .\services .\scripts .\tools --select F }
  } else {
    Write-Host "==> Python correctness lint skipped: run scripts\setup-dev.ps1 to install Ruff"
  }
  if (-not $SkipRuntime) {
    $runtimeArgs = @("-File", (Join-Path $ProjectRoot "scripts\start-system.ps1"), "-CheckOnly")
    if ($RequireAiUnlocked) { $runtimeArgs += "-RequireAiApi" }
    Invoke-Step "strict runtime check" { & powershell.exe -NoProfile -ExecutionPolicy Bypass @runtimeArgs }
    Invoke-Step "Phase 1 PostgreSQL scope, migration, audit and Outbox gate" {
      & $centralPython .\scripts\check_phase1_database.py
    }
    Invoke-Step "Phase 3 durable production-execution gate" {
      & $centralPython .\scripts\check_phase3_execution.py
    }
    Invoke-Step "Phase 4 material-flow, genealogy and reconciliation gate" {
      & $centralPython .\scripts\check_phase4_material_flow.py
    }
    Invoke-Step "Phase 5 quality, hold, disposition and release gate" {
      & $centralPython .\scripts\check_phase5_quality.py
    }
    Invoke-Step "Phase 6 maintenance, tooling, downtime and verification gate" {
      & $centralPython .\scripts\check_phase6_maintenance.py
    }
    Invoke-Step "Phase 7 Historian, projection, object integrity and retention gate" {
      & $centralPython .\scripts\check_phase7_data_platform.py
    }
    Invoke-Step "Stage H governed production closed-loop gate" {
      & $centralPython .\scripts\check_stage_h_closed_loop.py
    }
  }
} finally {
  Pop-Location
}

Write-Host "Mini-OGAS verification complete."
