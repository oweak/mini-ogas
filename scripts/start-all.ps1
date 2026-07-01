param(
  [string]$AdminPassword = $env:MINIOGAS_ADMIN_PASSWORD,
  [switch]$CheckOnly,
  [switch]$RequireAiApi,
  [switch]$StartKali
)

$ErrorActionPreference = "Stop"
$launcher = Join-Path $PSScriptRoot "start-system.ps1"
& $launcher @PSBoundParameters
exit $LASTEXITCODE
