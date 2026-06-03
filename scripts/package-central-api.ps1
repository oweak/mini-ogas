<#
.SYNOPSIS
    Package central-api as a portable Windows folder using PyInstaller.
.DESCRIPTION
    Creates a standalone distribution under .runtime/central-api-package/
    that includes the Python application, all dependencies, a .env template,
    and launch scripts.  The output folder can be copied to any machine
    that runs the same Windows version — no Python installation required.
.PARAMETER Clean
    Remove existing package directory before building.
#>

param([switch]$Clean)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\env.ps1"

# --- Paths ---
$packageName   = "central-api-package"
$packageRoot   = Join-Path $script:RuntimeDir $packageName
$distRoot      = Join-Path $script:RuntimeDir "dist"
$archive       = Join-Path $distRoot "mini-ogas-central-api.zip"
$serviceDir    = Join-Path $script:Root "services" "central-api"
$pythonExe     = Get-ServicePython "central-api"

if (-not (Test-Path $pythonExe)) {
    Write-Error "Virtual environment not found at $pythonExe. Run setup-dev.ps1 first."
    exit 1
}

# --- Cleanup ---
if ($Clean -and (Test-Path $packageRoot)) {
    Remove-Item -LiteralPath $packageRoot -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $packageRoot, $distRoot | Out-Null

# --- Build Vue dashboard ---
Write-Host "==> Building Vue dashboard..."
$dashboardDir = Join-Path $script:Root "services" "dashboard"
Push-Location $dashboardDir
& npm run build
if ($LASTEXITCODE -ne 0) {
    Pop-Location
    Write-Error "Dashboard build failed."
    exit 1
}
Pop-Location

# --- Install PyInstaller ---
Write-Host "==> Installing PyInstaller..."
& $pythonExe -m pip install pyinstaller --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install PyInstaller."
    exit 1
}

# --- Build ---
Write-Host "==> Building portable bundle with PyInstaller (onedir)..."
Push-Location $serviceDir
& $pythonExe -m PyInstaller `
    --onedir `
    --name "mini-ogas-central-api" `
    --distpath (Join-Path $packageRoot "dist") `
    --workpath (Join-Path $packageRoot "build") `
    --add-data "main.py;." `
    --add-data "test_main.py;." `
    --add-data "$(Join-Path $script:Root 'services' 'dashboard' 'dist');dashboard-dist" `
    --hidden-import "uvicorn.logging" `
    --hidden-import "uvicorn.protocols.http.auto" `
    --hidden-import "uvicorn.lifespan.on" `
    --hidden-import "uvicorn.lifespan.off" `
    --hidden-import "pydantic" `
    --clean `
    run_portable.py
$buildOk = ($LASTEXITCODE -eq 0)
Pop-Location

if (-not $buildOk) {
    Write-Error "PyInstaller build failed."
    exit 1
}

# --- Post-build: copy extras ---
$exeDir = Join-Path $packageRoot "dist" "mini-ogas-central-api"

# Copy .env.example as a template
$envSrc = Join-Path $serviceDir ".env.example"
if (-not (Test-Path $envSrc)) {
    # Fall back to project-root .env.example
    $envSrc = Join-Path $script:Root ".env.example"
}
if (Test-Path $envSrc) {
    Copy-Item -LiteralPath $envSrc -Destination (Join-Path $exeDir ".env.example")
}

# Create minimal start script
@"
@echo off
REM Mini-OGAS Central API — portable start
REM Copy .env.example to .env and edit settings before first run.
echo Starting Mini-OGAS Central API...
mini-ogas-central-api.exe
pause
"@ | Out-File -FilePath (Join-Path $exeDir "start.bat") -Encoding ascii

# PowerShell launcher
@"
# Mini-OGAS Central API — portable start (PowerShell)
Write-Host "Starting Mini-OGAS Central API..."
& "`$PSScriptRoot\mini-ogas-central-api.exe"
"@ | Out-File -FilePath (Join-Path $exeDir "start.ps1") -Encoding ascii

Write-Host ""
Write-Host "=== Package created ==="
Write-Host "Location: $exeDir"
Write-Host ""
Write-Host "To run on any machine:"
Write-Host "  1. Copy the folder to the target machine"
Write-Host "  2. (Optional) Copy .env.example to .env and edit settings"
Write-Host "  3. Double-click start.bat"
Write-Host ""

# --- Archive ---
if (Test-Path $archive) { Remove-Item -LiteralPath $archive -Force }
Compress-Archive -Path "$exeDir\*" -DestinationPath $archive -CompressionLevel Optimal
Write-Host "Zipped archive: $archive"
