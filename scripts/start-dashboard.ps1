$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$ServiceDir = Join-Path $Root "services\dashboard"

Push-Location $ServiceDir
if (-not (Test-Path "node_modules")) {
    npm install
}
npm run dev
Pop-Location

