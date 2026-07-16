param(
  [string]$EnvFile = ".env",
  [switch]$NoBuild
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$ComposeFile = Join-Path $ProjectRoot "docker-compose.yml"
$ResolvedEnvFile = if ([System.IO.Path]::IsPathRooted($EnvFile)) {
  $EnvFile
} else {
  Join-Path $ProjectRoot $EnvFile
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker CLI is not installed or not available on PATH."
}
if (-not (Test-Path -LiteralPath $ResolvedEnvFile)) {
  throw "Compose environment file is missing: $ResolvedEnvFile"
}

Push-Location $ProjectRoot
try {
  & docker compose --env-file $ResolvedEnvFile -f $ComposeFile config --quiet
  if ($LASTEXITCODE -ne 0) { throw "Compose configuration validation failed." }

  $arguments = @("compose", "--env-file", $ResolvedEnvFile, "-f", $ComposeFile, "up", "--detach")
  if (-not $NoBuild) { $arguments += "--build" }
  & docker @arguments
  if ($LASTEXITCODE -ne 0) { throw "Compose startup failed." }

  $deadline = (Get-Date).AddMinutes(4)
  do {
    try {
      $health = Invoke-RestMethod -Uri "http://127.0.0.1:8080/health" -TimeoutSec 3
      $dashboard = Invoke-WebRequest -Uri "http://127.0.0.1:5173/" -UseBasicParsing -TimeoutSec 3
      if ($health.overall_status -eq "ready" -and $dashboard.StatusCode -eq 200) { break }
    } catch {
      Start-Sleep -Seconds 2
    }
  } while ((Get-Date) -lt $deadline)

  if ((Get-Date) -ge $deadline) {
    throw "Compose services did not reach Central readiness and Dashboard HTTP 200 in time."
  }

  $migrationId = (& docker compose --env-file $ResolvedEnvFile -f $ComposeFile ps --all --quiet migrate).Trim()
  if (-not $migrationId) { throw "The one-shot migration container was not created." }
  $migrationExit = (& docker inspect --format "{{.State.ExitCode}}" $migrationId).Trim()
  if ($migrationExit -ne "0") { throw "The one-shot migration container failed." }

  [pscustomobject]@{
    status = "ready"
    central_api = "http://127.0.0.1:8080"
    dashboard = "http://127.0.0.1:5173"
    migration = "completed"
    deployment = "docker-compose"
  } | ConvertTo-Json
} finally {
  Pop-Location
}
