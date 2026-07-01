param(
  [string]$RuntimeRoot = "D:\MiniOGAS-VMs",
  [string]$ApiUrl = "http://127.0.0.1:8080",
  [string]$SupervisorUrl = "http://127.0.0.1:9099/supervisor/status",
  [int]$TimeoutSeconds = 90,
  [switch]$SkipRestart
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$AuthConfigPath = Join-Path $RuntimeRoot "auth.env"

function Get-AuthValue {
  param([string]$Name)
  if (-not (Test-Path -LiteralPath $AuthConfigPath)) {
    throw "auth.env not found: $AuthConfigPath"
  }
  $line = Get-Content -LiteralPath $AuthConfigPath | Where-Object { $_ -match "^$Name=" } | Select-Object -First 1
  if (-not $line) { return "" }
  return $line.Substring($Name.Length + 1).Trim().Trim('"').Trim("'")
}

function Get-AuthHeaders {
  $operator = Get-AuthValue "AUTH_BOOTSTRAP_USERNAME"
  if ([string]::IsNullOrWhiteSpace($operator)) { $operator = "admin" }
  $password = Get-AuthValue "AUTH_BOOTSTRAP_PASSWORD"
  if ([string]::IsNullOrWhiteSpace($password)) {
    throw "AUTH_BOOTSTRAP_PASSWORD is missing from $AuthConfigPath"
  }
  $body = @{ operator = $operator; password = $password } | ConvertTo-Json
  $login = Invoke-RestMethod -Method Post -Uri "$ApiUrl/api/auth/login" -ContentType "application/json" -Body $body -TimeoutSec 60
  if ([string]::IsNullOrWhiteSpace([string]$login.access_token)) {
    throw "Login succeeded without an access token."
  }
  return @{ Authorization = "Bearer $($login.access_token)" }
}

function Get-PersistenceStatus {
  param([hashtable]$Headers)
  return Invoke-RestMethod -Uri "$ApiUrl/api/persistence/status" -Headers $Headers -TimeoutSec 30
}

function Assert-ReplayReady {
  param([object]$Status, [string]$Label)
  if ($Status.backend -ne "postgresql") {
    throw "$Label persistence backend is '$($Status.backend)', expected 'postgresql'."
  }
  if ($Status.status -ne "ok") {
    throw "$Label persistence status is '$($Status.status)', expected 'ok'."
  }
  if ($Status.replay_readiness.status -ne "ok") {
    throw "$Label replay readiness is '$($Status.replay_readiness.status)', expected 'ok'."
  }
}

function Get-ShadowCounts {
  param([object]$Status)
  return [ordered]@{
    heartbeat_shadow = [int]$Status.counts.heartbeat_shadow
    part_queue_shadow = [int]$Status.counts.part_queue_shadow
    command_shadow = [int]$Status.counts.command_shadow
    audit_logs = [int]$Status.counts.audit_logs
    commands = [int]$Status.counts.commands
  }
}

function Wait-SupervisorHealthy {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    try {
      $status = Invoke-RestMethod -Uri $SupervisorUrl -TimeoutSec 5
      $processes = @($status.processes)
      if ($processes.Count -gt 0 -and (@($processes | Where-Object { $_.state -ne "healthy" }).Count -eq 0)) {
        return $status
      }
    } catch {
      Start-Sleep -Seconds 2
    }
    Start-Sleep -Seconds 2
  } while ((Get-Date) -lt $deadline)
  throw "Supervisor did not report all processes healthy within $TimeoutSeconds seconds."
}

$headers = Get-AuthHeaders
$before = Get-PersistenceStatus $headers
Assert-ReplayReady $before "before restart"
$beforeCounts = Get-ShadowCounts $before

$supervisorStatus = Invoke-RestMethod -Uri $SupervisorUrl -TimeoutSec 5
if (-not $SkipRestart) {
  $launcherOut = Join-Path $ProjectRoot ".runtime\logs\replay-drill-start.out.log"
  $launcherErr = Join-Path $ProjectRoot ".runtime\logs\replay-drill-start.err.log"
  $launcherScript = '"' + (Join-Path $ProjectRoot "scripts\start-miniogas.ps1") + '"'
  $quotedRuntimeRoot = '"' + $RuntimeRoot + '"'
  $launcherArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $launcherScript,
    "-RuntimeRoot", $quotedRuntimeRoot,
    "-ReplaceRunning"
  )
  $launcher = Start-Process -FilePath "powershell.exe" `
    -ArgumentList $launcherArgs `
    -WorkingDirectory $ProjectRoot `
    -RedirectStandardOutput $launcherOut `
    -RedirectStandardError $launcherErr `
    -PassThru `
    -WindowStyle Hidden
  if (-not $launcher.WaitForExit($TimeoutSeconds * 1000)) {
    Stop-Process -Id $launcher.Id -Force -ErrorAction SilentlyContinue
    throw "start-miniogas.ps1 -ReplaceRunning did not exit within $TimeoutSeconds seconds."
  }
  $launcher.Refresh()
  $exitCode = $launcher.ExitCode
  if ($null -eq $exitCode) {
    $launcherOutput = ""
    if (Test-Path -LiteralPath $launcherOut) {
      $launcherOutput = (Get-Content -LiteralPath $launcherOut -Raw).Trim()
    }
    if ($launcherOutput -match '"ownership"\s*:\s*"go-supervisor"') {
      $exitCode = 0
    }
  }
  if ($exitCode -ne 0) {
    $err = ""
    if (Test-Path -LiteralPath $launcherErr) {
      $err = (Get-Content -LiteralPath $launcherErr -Raw).Trim()
    }
    throw "start-miniogas.ps1 -ReplaceRunning failed with exit code $exitCode. $err"
  }
  $supervisorStatus = Wait-SupervisorHealthy
}

$headers = Get-AuthHeaders
$after = Get-PersistenceStatus $headers
Assert-ReplayReady $after "after restart"
$afterCounts = Get-ShadowCounts $after

$regressions = @()
foreach ($key in $beforeCounts.Keys) {
  if ($afterCounts[$key] -lt $beforeCounts[$key]) {
    $regressions += "$key decreased from $($beforeCounts[$key]) to $($afterCounts[$key])"
  }
}
if ($regressions.Count -gt 0) {
  throw "PostgreSQL replay drill failed: $($regressions -join '; ')"
}

$result = [pscustomobject]@{
  ok = $true
  checked_at = (Get-Date).ToUniversalTime().ToString("o")
  restarted = -not $SkipRestart
  supervisor_session = $supervisorStatus.session_id
  process_count = @($supervisorStatus.processes).Count
  before = [pscustomobject]@{
    status = $before.status
    backend = $before.backend
    replay_status = $before.replay_readiness.status
    counts = $beforeCounts
  }
  after = [pscustomobject]@{
    status = $after.status
    backend = $after.backend
    replay_status = $after.replay_readiness.status
    counts = $afterCounts
    replay_shadow = $after.replay_readiness.shadow
  }
}

$json = $result | ConvertTo-Json -Depth 8
$resultPath = Join-Path $ProjectRoot ".runtime\logs\postgres-replay-drill-last.json"
Set-Content -LiteralPath $resultPath -Value $json -Encoding UTF8
Write-Output $json
