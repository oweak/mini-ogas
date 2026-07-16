param(
  [string]$AdminPassword = $env:MINIOGAS_ADMIN_PASSWORD,
  [switch]$CheckOnly,
  [switch]$RequireAiApi,
  [switch]$StartKali
)

$ErrorActionPreference = "Stop"
if ($CheckOnly) {
  $checkArgs = @{ CheckOnly = $true }
  if ($AdminPassword) { $checkArgs["AdminPassword"] = $AdminPassword }
  if ($RequireAiApi) { $checkArgs["RequireAiApi"] = $true }
  if ($StartKali) { $checkArgs["StartKali"] = $true }
  & (Join-Path $PSScriptRoot "start-system.ps1") @checkArgs
  exit $LASTEXITCODE
}

& (Join-Path $PSScriptRoot "start-miniogas.ps1")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ($RequireAiApi -or $StartKali) {
  $checkArgs = @{ CheckOnly = $true }
  if ($AdminPassword) { $checkArgs["AdminPassword"] = $AdminPassword }
  if ($RequireAiApi) { $checkArgs["RequireAiApi"] = $true }
  if ($StartKali) { $checkArgs["StartKali"] = $true }
  & (Join-Path $PSScriptRoot "start-system.ps1") @checkArgs
}
exit $LASTEXITCODE
