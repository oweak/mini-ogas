param(
  [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$HookPath = Join-Path $ProjectRoot ".githooks\pre-commit"

if (-not (Test-Path -LiteralPath $HookPath -PathType Leaf)) {
  throw "Pre-commit hook is missing: $HookPath"
}

Push-Location $ProjectRoot
try {
  $configured = (@(& git config --local --get core.hooksPath 2>$null) -join "").Trim()
  if ($CheckOnly) {
    if ($configured -ne ".githooks") {
      throw "Git hooks are not enabled. Run scripts\install-git-hooks.ps1."
    }
  } else {
    & git config --local core.hooksPath .githooks
    if ($LASTEXITCODE -ne 0) { throw "Failed to configure core.hooksPath." }
  }

  & python .\scripts\check_secrets.py
  if ($LASTEXITCODE -ne 0) { throw "Secret scan failed." }

  $trackedIgnored = @(& git ls-files -ci --exclude-standard)
  if ($trackedIgnored.Count -gt 0) {
    throw "Tracked files match private/generated ignore rules: $($trackedIgnored -join ', ')"
  }
} finally {
  Pop-Location
}

Write-Host "Mini-OGAS pre-commit protection is enabled and verified."
