param(
  [string]$RuntimeRoot = "D:\MiniOGAS-VMs",
  [switch]$ReplaceRunning,
  [switch]$Foreground,
  [switch]$UseScriptLauncher,
  [switch]$CheckOnly,
  [switch]$RequireAiApi,
  [switch]$StartKali,
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
if ($ReplaceRunning) { $supervisorArgs += "-ReplaceRunning" }
if ($Foreground) { $supervisorArgs += "-Foreground" }

& powershell.exe @supervisorArgs
exit $LASTEXITCODE
