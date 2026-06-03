$ErrorActionPreference = "Stop"
. "$PSScriptRoot\env.ps1"

function Ensure-Go {
    $goExe = Join-Path $script:GoRoot "bin\go.exe"
    if (Test-Path $goExe) {
        & $goExe version
        return
    }

    $metadata = Invoke-RestMethod -Uri "https://go.dev/dl/?mode=json" -UseBasicParsing
    $stable = $metadata | Where-Object { $_.stable -eq $true } | Select-Object -First 1
    $file = $stable.files | Where-Object { $_.os -eq "windows" -and $_.arch -eq "amd64" -and $_.kind -eq "archive" } | Select-Object -First 1
    if (-not $file) {
        throw "Cannot find official Go windows/amd64 archive metadata."
    }

    $zip = Join-Path $script:ToolsDir $file.filename
    Invoke-WebRequest -Uri "https://go.dev/dl/$($file.filename)" -OutFile $zip -UseBasicParsing
    if (Test-Path $script:GoRoot) {
        Remove-Item -LiteralPath $script:GoRoot -Recurse -Force
    }
    Expand-Archive -LiteralPath $zip -DestinationPath $script:ToolsDir -Force
    . "$PSScriptRoot\env.ps1"
    & (Join-Path $script:GoRoot "bin\go.exe") version
}

function Ensure-PythonService {
    param([Parameter(Mandatory = $true)][string]$ServiceName)
    $serviceDir = Join-Path $script:Root "services\$ServiceName"
    $python = Join-Path $serviceDir ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        python -m venv (Join-Path $serviceDir ".venv")
    }
    & $python -m pip install --upgrade pip setuptools wheel
    & $python -m pip install -r (Join-Path $serviceDir "requirements.txt") ruff pytest httpx
}

Ensure-Go

& "$PSScriptRoot\setup-editor.ps1"

foreach ($service in @("central-api", "ai-dispatcher", "market-simulator", "production-planner")) {
    Ensure-PythonService $service
}

Push-Location (Join-Path $script:Root "services\dashboard")
if (Test-Path "package-lock.json") {
    npm ci
} else {
    npm install
}
Pop-Location

Push-Location (Join-Path $script:Root "services\node-agent")
go mod download
Pop-Location

Write-Host "Mini-OGAS development environment is ready under $script:Root"
