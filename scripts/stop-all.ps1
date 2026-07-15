$ErrorActionPreference = "Continue"

. "$PSScriptRoot\env.ps1"

Write-Host "=== Stopping all Mini-OGAS services ===" -ForegroundColor Cyan

# 1. Kill by saved PIDs (if start-all.ps1 was used)
$PidDir = Join-Path $script:RuntimeDir "pids"
if (Test-Path $PidDir) {
    Get-ChildItem $PidDir -Filter "*.pid" | ForEach-Object {
        $pidVal = Get-Content $_.FullName -ErrorAction SilentlyContinue
        if ($pidVal -and $pidVal -match '^\d+$') {
            taskkill /F /PID $pidVal 2>$null | Out-Null
            Write-Host "  Stopped $($_.BaseName) (PID $pidVal)"
        }
        Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
    }
}

# 2. Kill by port (catches anything missed by PID files)
$Ports = @(8080, 8081, 8082, 8083, 8084)
foreach ($port in $Ports) {
    $line = netstat -ano 2>$null | Select-String ":$port " | Select-String "LISTENING"
    if ($line) {
        foreach ($l in $line) {
            $parts = -split $l
            $pidVal = $parts[-1]
            if ($pidVal -and $pidVal -match '^\d+$' -and $pidVal -ne '0') {
                taskkill /F /PID $pidVal 2>$null | Out-Null
                Write-Host "  Killed PID $pidVal on port $port"
            }
        }
    }
}

# 3. Kill any remaining agent.py processes
Get-Process -Name "python" -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $cmd = (Get-WmiObject Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
        if ($cmd -match "agent\.py") {
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
            Write-Host "  Killed agent.py (PID $($_.Id))"
        }
    } catch { }
}

Write-Host "Done." -ForegroundColor Green
