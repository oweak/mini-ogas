$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$ServiceDir = Join-Path $Root "services\central-api"
$Python = Join-Path $ServiceDir ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Push-Location $ServiceDir
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    Pop-Location
}

Push-Location $ServiceDir
& $Python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
Pop-Location

