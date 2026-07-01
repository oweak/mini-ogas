param(
  [string]$RuntimeRoot = "D:\MiniOGAS-VMs",
  [switch]$ReplaceRunning,
  [switch]$Foreground
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$SupervisorRoot = Join-Path $ProjectRoot "services\supervisor"
$ConfigPath = Join-Path $ProjectRoot "config\supervisor.toml"
$RuntimeBin = Join-Path $ProjectRoot ".runtime\bin"
$RuntimeLogRoot = Join-Path $ProjectRoot ".runtime\logs"
$SupervisorExe = Join-Path $RuntimeBin "miniogas-supervisor.exe"
$GoExe = "C:\Program Files\Go\bin\go.exe"
$TokenPath = Join-Path $RuntimeRoot "miniogas-token.txt"
$PostgresConfigPath = Join-Path $RuntimeRoot "postgres.env"
$AuthConfigPath = Join-Path $RuntimeRoot "auth.env"
$SessionPath = Join-Path $RuntimeRoot "miniogas-session-token.txt"
$Ports = @(8080, 8081, 8082, 8083, 5173, 9099)

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
$postgresDsn = Get-ConfigValue $PostgresConfigPath "POSTGRES_DSN"
$jwtSecret = Get-ConfigValue $AuthConfigPath "JWT_SECRET"
$bootstrapPassword = Get-ConfigValue $AuthConfigPath "AUTH_BOOTSTRAP_PASSWORD"
if (-not $postgresDsn) { throw "POSTGRES_DSN is missing from $PostgresConfigPath" }
if (-not $jwtSecret -or -not $bootstrapPassword) { throw "auth.env is incomplete: $AuthConfigPath" }

$occupied = @($Ports | ForEach-Object { Get-PortProcessIds $_ } | Select-Object -Unique)
if ($occupied.Count -gt 0 -and -not $ReplaceRunning) {
  throw "Mini-OGAS service ports are already occupied. Use start-system.ps1 for the running stack, or pass -ReplaceRunning to transfer ownership to the Go supervisor."
}
if ($ReplaceRunning) {
  foreach ($processId in $occupied) {
    Stop-Process -Id $processId -Force -ErrorAction Stop
  }
  Stop-ExistingSimulatorProcesses
  Start-Sleep -Seconds 2
}

New-Item -ItemType Directory -Force -Path $RuntimeRoot, $RuntimeBin, $RuntimeLogRoot | Out-Null
$env:OGAS_SESSION_TOKEN = [guid]::NewGuid().ToString()
$env:OGAS_API_TOKEN = $token
$env:API_ACCESS_TOKEN = $token
$env:NODE_INGEST_TOKEN = $token
$env:POSTGRES_DSN = $postgresDsn
$env:JWT_SECRET = $jwtSecret
$env:AUTH_BOOTSTRAP_PASSWORD = $bootstrapPassword
$env:OGAS_RUN_ID = "RUN-LOCAL-$(Get-Date -Format yyyyMMdd)-001"
Set-Content -LiteralPath $SessionPath -Value $env:OGAS_SESSION_TOKEN -Encoding ASCII

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
[pscustomobject]@{
  supervisor_pid = $process.Id
  management_url = "http://127.0.0.1:9099/supervisor/status"
  session_file = $SessionPath
  log = $stdout
  ownership = "go-supervisor"
} | ConvertTo-Json
