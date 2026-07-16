param(
  [string]$RuntimeRoot = "D:\MiniOGAS-VMs",
  [switch]$ReplaceRunning,
  [switch]$Foreground,
  [switch]$DisableNats,
  [ValidateSet("development", "test", "digital_twin", "staging", "pilot", "production")]
  [string]$AppEnv = "digital_twin",
  [ValidateSet("simulated", "replay", "shadow", "live")]
  [string]$DataSource = "simulated",
  [ValidateSet("read_only", "operator_assisted", "controlled_write")]
  [string]$ControlMode = "operator_assisted",
  [string]$TenantId = "tenant-local",
  [string]$SiteId = "site-digital-twin",
  [ValidateSet("postgresql", "memory")]
  [string]$FactSource = "postgresql"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$SupervisorRoot = Join-Path $ProjectRoot "services\supervisor"
$DashboardRoot = Join-Path $ProjectRoot "services\dashboard"
$ConfigPath = Join-Path $ProjectRoot "config\supervisor.toml"
$RuntimeBin = Join-Path $ProjectRoot ".runtime\bin"
$RuntimeLogRoot = Join-Path $ProjectRoot ".runtime\logs"
$SupervisorExe = Join-Path $RuntimeBin "miniogas-supervisor.exe"
$GoExe = "C:\Program Files\Go\bin\go.exe"
$TokenPath = Join-Path $RuntimeRoot "miniogas-token.txt"
$PostgresConfigPath = Join-Path $RuntimeRoot "postgres.env"
$AuthConfigPath = Join-Path $RuntimeRoot "auth.env"
$NatsConfigPath = Join-Path $ProjectRoot "config\nats-server.conf"
$NatsRuntimeRoot = Join-Path $RuntimeRoot "nats"
$NatsBinary = Join-Path $NatsRuntimeRoot "bin\nats-server.exe"
$NatsStorePath = Join-Path $NatsRuntimeRoot "jetstream"
$NatsEnvPath = Join-Path $NatsRuntimeRoot "nats.env"
$DataPlatformRoot = Join-Path $RuntimeRoot "data-platform"
$RedisRuntimeRoot = Join-Path $DataPlatformRoot "redis"
$RedisDataPath = Join-Path $RedisRuntimeRoot "data"
$RedisEnvPath = Join-Path $RedisRuntimeRoot "redis.env"
$RedisConfigPath = Join-Path $RedisRuntimeRoot "memurai.conf"
$RedisBinary = Join-Path $RuntimeRoot "memurai-portable\Memurai\memurai.exe"
$RedisCli = Join-Path $RuntimeRoot "memurai-portable\Memurai\memurai-cli.exe"
$MinioRuntimeRoot = Join-Path $DataPlatformRoot "minio"
$MinioDataPath = Join-Path $MinioRuntimeRoot "data"
$MinioEnvPath = Join-Path $MinioRuntimeRoot "minio.env"
$CentralApiPython = Join-Path $ProjectRoot "services\central-api\.venv\Scripts\python.exe"
$SessionPath = Join-Path $RuntimeRoot "miniogas-session-token.txt"
$Ports = @(4222, 8222, 6379, 9000, 9001, 8080, 8081, 8082, 8083, 8084, 5173, 9099)

function Get-ConfigValue {
  param([string]$Path, [string]$Name)
  if (-not (Test-Path -LiteralPath $Path)) { return "" }
  $line = Get-Content -LiteralPath $Path | Where-Object { $_ -match "^$Name=" } | Select-Object -First 1
  if (-not $line) { return "" }
  return $line.Substring($Name.Length + 1).Trim()
}

function Get-PortProcessIds {
  param([int]$Port)
  return @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    Where-Object { $_ -and $_ -gt 0 })
}

function New-RandomHexToken {
  $bytes = New-Object byte[] 32
  $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
  return ([System.BitConverter]::ToString($bytes)).Replace("-", "").ToLowerInvariant()
}

function Stop-ExistingSimulatorProcesses {
  $simulators = @(Get-CimInstance Win32_Process |
    Where-Object {
      $_.ProcessId -ne $PID -and
      $_.CommandLine -and
      $_.CommandLine -match "simulator\.py"
    })
  foreach ($simulator in $simulators) {
    Stop-Process -Id $simulator.ProcessId -Force -ErrorAction SilentlyContinue
  }
}

if (-not (Test-Path -LiteralPath $TokenPath)) {
  throw "Node API token file is missing: $TokenPath"
}
$token = (Get-Content -LiteralPath $TokenPath -Raw).Trim()
. (Join-Path $PSScriptRoot "node-credentials.ps1")
$nodeCredentialState = Get-MiniOgasNodeCredentialState -RuntimeRoot $RuntimeRoot -CreateIfMissing
$postgresDsn = Get-ConfigValue $PostgresConfigPath "POSTGRES_DSN"
$jwtSecret = Get-ConfigValue $AuthConfigPath "JWT_SECRET"
$bootstrapPassword = Get-ConfigValue $AuthConfigPath "AUTH_BOOTSTRAP_PASSWORD"
if (-not $postgresDsn) { throw "POSTGRES_DSN is missing from $PostgresConfigPath" }
if (-not $jwtSecret -or -not $bootstrapPassword) { throw "auth.env is incomplete: $AuthConfigPath" }
if (-not (Test-Path -LiteralPath $NatsBinary)) { throw "NATS Server is missing: $NatsBinary" }
if (-not (Test-Path -LiteralPath $NatsConfigPath)) { throw "NATS configuration is missing: $NatsConfigPath" }
if (-not (Test-Path -LiteralPath $RedisBinary)) { throw "Memurai runtime is missing: $RedisBinary" }
if (-not (Test-Path -LiteralPath $RedisCli)) { throw "Memurai CLI is missing: $RedisCli" }
if (-not (Test-Path -LiteralPath $CentralApiPython)) {
  throw "Central API virtual environment is missing: $CentralApiPython"
}
$MinioBinary = Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages") -Recurse -Filter "minio.exe" -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -match "MinIO\.Server" } |
  Select-Object -First 1 -ExpandProperty FullName
if (-not $MinioBinary -or -not (Test-Path -LiteralPath $MinioBinary)) {
  throw "MinIO Server installed binary was not found under the WinGet package root."
}

$occupied = @($Ports | ForEach-Object { Get-PortProcessIds $_ } | Select-Object -Unique)
if ($occupied.Count -gt 0 -and -not $ReplaceRunning) {
  throw "Mini-OGAS service ports are already occupied. Inspect the active runtime or pass -ReplaceRunning to transfer ownership to the Go supervisor."
}
if ($ReplaceRunning) {
  # Stop the old supervisor first so it cannot restart children while their
  # occupied ports are being transferred to the new supervisor session.
  foreach ($supervisorPid in @(Get-PortProcessIds 9099)) {
    Stop-Process -Id $supervisorPid -Force -ErrorAction SilentlyContinue
  }
  $occupied = @($Ports | ForEach-Object { Get-PortProcessIds $_ } | Select-Object -Unique)
  foreach ($processId in $occupied) {
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
  }
  Stop-ExistingSimulatorProcesses
  Start-Sleep -Seconds 2
}

New-Item -ItemType Directory -Force -Path @(
  $RuntimeRoot,
  $RuntimeBin,
  $RuntimeLogRoot,
  $NatsRuntimeRoot,
  $NatsStorePath,
  $DataPlatformRoot,
  $RedisRuntimeRoot,
  $RedisDataPath,
  $MinioRuntimeRoot,
  $MinioDataPath
) | Out-Null
if (-not (Test-Path -LiteralPath $NatsEnvPath)) {
  Set-Content -LiteralPath $NatsEnvPath -Value "NATS_AUTH_TOKEN=$(New-RandomHexToken)" -Encoding ASCII
}
$natsAuthToken = Get-ConfigValue $NatsEnvPath "NATS_AUTH_TOKEN"
if (-not $natsAuthToken) { throw "NATS_AUTH_TOKEN is missing from $NatsEnvPath" }
if (-not (Test-Path -LiteralPath $RedisEnvPath)) {
  Set-Content -LiteralPath $RedisEnvPath -Value "REDIS_PASSWORD=$(New-RandomHexToken)" -Encoding ASCII
}
$redisPassword = Get-ConfigValue $RedisEnvPath "REDIS_PASSWORD"
if (-not $redisPassword) { throw "REDIS_PASSWORD is missing from $RedisEnvPath" }
@(
  "bind 127.0.0.1",
  "port 6379",
  "protected-mode yes",
  "requirepass $redisPassword",
  "dir $($RedisDataPath.Replace('\', '/'))",
  "appendonly yes",
  "appendfsync everysec",
  "save 900 1",
  "loglevel notice"
) | Set-Content -LiteralPath $RedisConfigPath -Encoding ASCII
if (-not (Test-Path -LiteralPath $MinioEnvPath)) {
  @(
    "MINIO_ROOT_USER=miniogas-admin",
    "MINIO_ROOT_PASSWORD=$(New-RandomHexToken)"
  ) | Set-Content -LiteralPath $MinioEnvPath -Encoding ASCII
}
$minioRootUser = Get-ConfigValue $MinioEnvPath "MINIO_ROOT_USER"
$minioRootPassword = Get-ConfigValue $MinioEnvPath "MINIO_ROOT_PASSWORD"
if (-not $minioRootUser -or -not $minioRootPassword) {
  throw "MinIO credentials are incomplete: $MinioEnvPath"
}
$env:OGAS_SESSION_TOKEN = [guid]::NewGuid().ToString()
$env:APP_ENV = $AppEnv
$env:DATA_SOURCE = $DataSource
$env:CONTROL_MODE = $ControlMode
$env:DEMO_SEED_ENABLED = if (
  $AppEnv -in @("development", "test", "digital_twin") -and $DataSource -eq "simulated"
) { "true" } else { "false" }
$env:INDUSTRIAL_CONNECTOR_ENABLED = "false"
$env:PHYSICAL_WRITE_ENABLED = "false"
$env:TENANT_ID = $TenantId
$env:SITE_ID = $SiteId
$env:OGAS_API_TOKEN = $token
$env:API_ACCESS_TOKEN = $token
$env:NODE_INGEST_TOKEN = $token
$env:NODE_CREDENTIALS_JSON = $nodeCredentialState.Json
$env:ALLOW_LEGACY_NODE_TOKEN_AUTH = "false"
$env:TURNING_NODE_TOKEN = $nodeCredentialState.Credentials["turning-workshop-01"]
$env:MILLING_NODE_TOKEN = $nodeCredentialState.Credentials["milling-workshop-01"]
$env:GRINDING_NODE_TOKEN = $nodeCredentialState.Credentials["grinding-workshop-01"]
$env:POSTGRES_DSN = $postgresDsn
$env:JWT_SECRET = $jwtSecret
$env:AUTH_BOOTSTRAP_PASSWORD = $bootstrapPassword
$env:NATS_SERVER_BIN = $NatsBinary
$env:NATS_CONFIG_PATH = $NatsConfigPath
$env:NATS_STORE_DIR = $NatsStorePath.Replace("\", "/")
$env:NATS_AUTH_TOKEN = $natsAuthToken
$env:NATS_ENABLED = if ($DisableNats) { "false" } else { "true" }
$env:REDIS_SERVER_BIN = $RedisBinary
$env:REDIS_CONFIG_PATH = $RedisConfigPath
$env:REDIS_URL = "redis://:$redisPassword@127.0.0.1:6379/0"
$env:MINIO_SERVER_BIN = $MinioBinary
$env:MINIO_DATA_DIR = $MinioDataPath
$env:MINIO_ROOT_USER = $minioRootUser
$env:MINIO_ROOT_PASSWORD = $minioRootPassword
$env:CENTRAL_API_PYTHON = $CentralApiPython
$env:CENTRAL_FACT_SOURCE = $FactSource
$env:PERSIST_ENABLED = "true"
$env:PERSIST_BACKEND = "postgres"
$env:DATABASE_AUTO_MIGRATE = "false"
$env:OGAS_RUN_ID = "RUN-LOCAL-$(Get-Date -Format yyyyMMdd-HHmmss)"
$env:OGAS_SIMULATION_START_TIME = (Get-Date).ToUniversalTime().ToString("o")
Set-Content -LiteralPath $SessionPath -Value $env:OGAS_SESSION_TOKEN -Encoding ASCII
$protectSecrets = Join-Path $PSScriptRoot "protect-secrets.ps1"
& $protectSecrets -RuntimeRoot $RuntimeRoot
if (-not $?) { throw "Secret ACL provisioning failed." }

Push-Location (Join-Path $ProjectRoot "services\central-api")
try {
  $migrationOutput = @(& $CentralApiPython -m app.migrate 2>&1)
  if ($LASTEXITCODE -ne 0) {
    throw "PostgreSQL migration failed before service startup. No runtime process was started."
  }
  $migrationReport = ($migrationOutput | Select-Object -Last 1) | ConvertFrom-Json
  if ($migrationReport.status -ne "migrated" -or $migrationReport.backend -ne "postgresql") {
    throw "Migration entrypoint returned an invalid deployment report."
  }
  $migrationEvidencePath = Join-Path $RuntimeLogRoot "migration-last.json"
  $migrationReport | ConvertTo-Json | Set-Content -LiteralPath $migrationEvidencePath -Encoding ASCII
} finally {
  Pop-Location
}

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
  throw "npm.cmd is required to build the production Dashboard artifact."
}
Push-Location $DashboardRoot
try {
  & npm.cmd run build
  if ($LASTEXITCODE -ne 0) { throw "Dashboard production build failed." }
} finally {
  Pop-Location
}

if (-not (Test-Path -LiteralPath $GoExe)) { throw "Go toolchain was not found: $GoExe" }
$env:GOMODCACHE = Join-Path $ProjectRoot ".runtime\go\modcache"
$env:GOCACHE = Join-Path $ProjectRoot ".runtime\go\buildcache"
Push-Location $SupervisorRoot
try {
  & $GoExe build -o $SupervisorExe .
  if ($LASTEXITCODE -ne 0) { throw "Go supervisor build failed." }
} finally {
  Pop-Location
}

if ($Foreground) {
  Push-Location $ProjectRoot
  try { & $SupervisorExe -config $ConfigPath } finally { Pop-Location }
  exit $LASTEXITCODE
}

$stdout = Join-Path $RuntimeLogRoot "supervisor.out.log"
$stderr = Join-Path $RuntimeLogRoot "supervisor.err.log"
$quotedConfigPath = '"' + $ConfigPath + '"'
$process = Start-Process -FilePath $SupervisorExe -ArgumentList @("-config", $quotedConfigPath) -WorkingDirectory $ProjectRoot -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru -WindowStyle Hidden
$expectedProcessCount = @(Select-String -LiteralPath $ConfigPath -Pattern '^\[\[process\]\]$').Count
$deadline = (Get-Date).AddSeconds(60)
$lastStates = @()
while ((Get-Date) -lt $deadline) {
  $process.Refresh()
  if ($process.HasExited) {
    throw "Go supervisor exited before readiness. See $stderr"
  }
  try {
    $status = Invoke-RestMethod -Uri "http://127.0.0.1:9099/supervisor/status" -TimeoutSec 3
    $lastStates = @($status.processes | ForEach-Object { "$($_.name)=$($_.state)" })
    $healthy = @($status.processes | Where-Object { $_.state -eq "healthy" })
    if (
      $status.session_id -eq $env:OGAS_SESSION_TOKEN -and
      $status.processes.Count -eq $expectedProcessCount -and
      $healthy.Count -eq $expectedProcessCount
    ) {
      break
    }
  } catch {
    $lastStates = @("management API not ready: $($_.Exception.Message)")
  }
  Start-Sleep -Milliseconds 500
}
if ((Get-Date) -ge $deadline) {
  throw "Go supervisor readiness timed out: $($lastStates -join ', ')"
}
$previousRedisCliAuth = $env:REDISCLI_AUTH
$env:REDISCLI_AUTH = $redisPassword
try {
  $redisPing = (& $RedisCli -h 127.0.0.1 -p 6379 ping 2>$null | Select-Object -Last 1).Trim()
} finally {
  $env:REDISCLI_AUTH = $previousRedisCliAuth
}
if ($redisPing -ne "PONG") {
  throw "Redis authenticated PING failed after supervisor readiness."
}
$minioHealth = Invoke-WebRequest -Uri "http://127.0.0.1:9000/minio/health/live" -UseBasicParsing -TimeoutSec 5
if ($minioHealth.StatusCode -ne 200) {
  throw "MinIO liveness endpoint returned HTTP $($minioHealth.StatusCode)."
}
[pscustomobject]@{
  supervisor_pid = $process.Id
  management_url = "http://127.0.0.1:9099/supervisor/status"
  session_file = $SessionPath
  log = $stdout
  ownership = "go-supervisor"
  healthy_processes = $expectedProcessCount
  migration_evidence = $migrationEvidencePath
  dashboard_serving = "production-dist"
  redis_authenticated = $true
  minio_live = $true
} | ConvertTo-Json
