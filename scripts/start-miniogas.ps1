param(
  [string]$RuntimeRoot = "D:\MiniOGAS-VMs",
  [switch]$ReplaceRunning,
  [switch]$Foreground,
  [switch]$DisableNats,
  [switch]$UseScriptLauncher,
  [switch]$CheckOnly,
  [switch]$RequireAiApi,
  [switch]$StartKali,
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

if ($UseScriptLauncher -or $CheckOnly -or $StartKali) {
  $args = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $ProjectRoot "scripts\start-system.ps1"),
    "-RuntimeRoot", $RuntimeRoot
  )
  $args += @("-FactSource", $FactSource)
  $args += @(
    "-AppEnv", $AppEnv, "-DataSource", $DataSource, "-ControlMode", $ControlMode,
    "-TenantId", $TenantId, "-SiteId", $SiteId
  )
  if ($CheckOnly) { $args += "-CheckOnly" }
  if ($RequireAiApi) { $args += "-RequireAiApi" }
  if ($StartKali) { $args += "-StartKali" }
  & powershell.exe @args
  exit $LASTEXITCODE
}

$supervisorArgs = @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-File", (Join-Path $ProjectRoot "scripts\start-supervisor.ps1"),
  "-RuntimeRoot", $RuntimeRoot
)
$supervisorArgs += @("-FactSource", $FactSource)
$supervisorArgs += @(
  "-AppEnv", $AppEnv, "-DataSource", $DataSource, "-ControlMode", $ControlMode,
  "-TenantId", $TenantId, "-SiteId", $SiteId
)
if ($ReplaceRunning) { $supervisorArgs += "-ReplaceRunning" }
if ($Foreground) { $supervisorArgs += "-Foreground" }
if ($DisableNats) { $supervisorArgs += "-DisableNats" }

& powershell.exe @supervisorArgs
exit $LASTEXITCODE
