$ErrorActionPreference = "Stop"
. "$PSScriptRoot\env.ps1"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
$CentralDir    = Join-Path $script:Root "services\central-api"
$AiDispatcherDir = Join-Path $script:Root "services\ai-dispatcher"
$MarketDir     = Join-Path $script:Root "services\market-simulator"
$PlannerDir    = Join-Path $script:Root "services\production-planner"
$AgentScript   = Join-Path $script:Root "services\node-agent\agent.py"

$CentralPython    = Get-ServicePython "central-api"
$AiDispatcherPy   = Get-ServicePython "ai-dispatcher"
$MarketPy         = Get-ServicePython "market-simulator"
$PlannerPy        = Get-ServicePython "production-planner"

$ApiToken     = $env:API_ACCESS_TOKEN
if (-not $ApiToken) { $ApiToken = "mini-ogas-dev-token" }

$Ports = @(
    @{Name="central-api";         Port=8080; Dir=$CentralDir;    Exe=$CentralPython;    Args="-m uvicorn app.main:app --host 127.0.0.1 --port 8080 --log-level warning"; Role="core"},
    @{Name="ai-dispatcher";       Port=8081; Dir=$AiDispatcherDir; Exe=$AiDispatcherPy;  Args="-m uvicorn app.main:app --host 127.0.0.1 --port 8081 --log-level warning"; Role="microservice"},
    @{Name="market-simulator";    Port=8082; Dir=$MarketDir;     Exe=$MarketPy;         Args="-m uvicorn app.main:app --host 127.0.0.1 --port 8082 --log-level warning"; Role="microservice"},
    @{Name="production-planner";  Port=8083; Dir=$PlannerDir;    Exe=$PlannerPy;        Args="-m uvicorn app.main:app --host 127.0.0.1 --port 8083 --log-level warning"; Role="microservice"}
)

$NodeAgents = @(
    @{Code="turning-workshop-01";  Type="turning"},
    @{Code="milling-workshop-01";  Type="milling"},
    @{Code="grinding-workshop-01"; Type="grinding"},
    @{Code="cloud-workshop-01";    Type="cloud"},
    @{Code="cloud-db-01";          Type="database"}
)

$PidDir = Join-Path $script:RuntimeDir "pids"
New-Item -ItemType Directory -Force -Path $PidDir | Out-Null

# ---------------------------------------------------------------------------
# Phase 0 — Kill any process holding our ports
# ---------------------------------------------------------------------------
# Generate a session token so every child process can prove it belongs to this launch
$env:OGAS_SESSION_TOKEN = [guid]::NewGuid().ToString()
Write-Host "Session token: $env:OGAS_SESSION_TOKEN" -ForegroundColor DarkGray

# Set BEFORE starting central-api so it probes microservices
$env:MICROSERVICES_ENABLED = "true"
$env:RATE_LIMIT_PER_MINUTE = "600"

Write-Host "=== Phase 0: Killing stale processes ===" -ForegroundColor Cyan

function Kill-Port {
    param([int]$Port)
    $line = netstat -ano 2>$null | Select-String ":$Port " | Select-String "LISTENING" | Select-Object -First 1
    if (-not $line) { return }
    $parts = -split $line
    $pidVal = $parts[-1]
    if ($pidVal -and $pidVal -match '^\d+$' -and $pidVal -ne '0') {
        taskkill /F /PID $pidVal 2>$null | Out-Null
        Write-Host "  Killed PID $pidVal on port $Port"
        Start-Sleep -Milliseconds 500
    }
}

foreach ($svc in $Ports) { Kill-Port -Port $svc.Port }
# Also kill any lingering agent.py processes
Get-Process -Name "python" -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_.MainWindowTitle -match "agent" -or $_.CommandLine -match "agent\.py") {
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""

# ---------------------------------------------------------------------------
# Phase 1 — Start central-api first (everything depends on it)
# ---------------------------------------------------------------------------
Write-Host "=== Phase 1: Starting central-api ===" -ForegroundColor Cyan

$proc = Start-Process -FilePath $CentralPython -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8080","--log-level","warning" -WorkingDirectory $CentralDir -PassThru -WindowStyle Hidden
Set-Content -Path (Join-Path $PidDir "central-api.pid") -Value $proc.Id
Write-Host "  central-api starting (PID $($proc.Id))..."

# Wait for health
$ok = $false
for ($i = 0; $i -lt 15; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8080/preflight" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $ok = $true; break }
    } catch { }
    Start-Sleep 1
}
if ($ok) { Write-Host "  central-api: OK" -ForegroundColor Green }
else      { Write-Host "  central-api: FAILED TO START" -ForegroundColor Red; exit 1 }

Write-Host ""

# ---------------------------------------------------------------------------
# Phase 2 — Microservices
# ---------------------------------------------------------------------------
Write-Host "=== Phase 2: Starting microservices ===" -ForegroundColor Cyan

foreach ($svc in $Ports | Where-Object { $_.Role -eq "microservice" }) {
    $proc = Start-Process -FilePath $svc.Exe -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","$($svc.Port)","--log-level","warning" -WorkingDirectory $svc.Dir -PassThru -WindowStyle Hidden
    Set-Content -Path (Join-Path $PidDir "$($svc.Name).pid") -Value $proc.Id
    Write-Host "  $($svc.Name) starting (PID $($proc.Id))..."
}

# Wait for all microservice health checks
foreach ($svc in $Ports | Where-Object { $_.Role -eq "microservice" }) {
    $ok = $false
    for ($i = 0; $i -lt 10; $i++) {
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$($svc.Port)/health" -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -eq 200) { $ok = $true; break }
        } catch { }
        Start-Sleep 1
    }
    if ($ok) { Write-Host "  $($svc.Name): OK" -ForegroundColor Green }
    else      { Write-Host "  $($svc.Name): FAILED" -ForegroundColor Red }
}
Write-Host ""

# ---------------------------------------------------------------------------
# Phase 3 — Node agents (real psutil processes)
# ---------------------------------------------------------------------------
Write-Host "=== Phase 3: Starting node agents ===" -ForegroundColor Cyan

$script:AgentRestartCommands = @{}
foreach ($agent in $NodeAgents) {
    $agentArgs = @(
        "-u", $AgentScript,
        "--node-code", $agent.Code,
        "--workshop-type", $agent.Type,
        "--interval", "3",
        "--api-url", "http://127.0.0.1:8080",
        "--token", $ApiToken
    )
    $proc = Start-Process -FilePath $CentralPython -ArgumentList $agentArgs -WindowStyle Hidden -PassThru
    Set-Content -Path (Join-Path $PidDir "$($agent.Code).pid") -Value $proc.Id
    $script:AgentRestartCommands[$agent.Code] = @{Exe=$CentralPython; Args=$agentArgs}
    Write-Host "  $($agent.Code) agent (PID $($proc.Id))"
}
Write-Host ""

# ---------------------------------------------------------------------------
# Phase 4 — Final verification
# ---------------------------------------------------------------------------
Write-Host "=== Phase 4: Final verification ===" -ForegroundColor Cyan
Start-Sleep 3

# Check nodes
try {
    $nodes = Invoke-RestMethod -Uri "http://127.0.0.1:8080/nodes" -Headers @{"X-OGAS-Token"=$ApiToken} -TimeoutSec 5
    $online = ($nodes | Where-Object { $_.status -eq "online" }).Count
    Write-Host "  Nodes online: $online / $($nodes.Count)" -ForegroundColor $(if ($online -ge 5) { "Green" } else { "Yellow" })
} catch {
    Write-Host "  Node check failed: $_" -ForegroundColor Red
}

# Check integrations
try {
    $snapshot = Invoke-RestMethod -Uri "http://127.0.0.1:8080/management/snapshot" -Headers @{"X-OGAS-Token"=$ApiToken} -TimeoutSec 5
    foreach ($integ in $snapshot.integrations) {
        $color = if ($integ.status -eq "online") { "Green" } else { "Red" }
        Write-Host "  $($integ.service): $($integ.status)" -ForegroundColor $color
    }
} catch {
    Write-Host "  Integration check failed: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== All services started ===" -ForegroundColor Green
Write-Host "  Dashboard : http://127.0.0.1:8080"
Write-Host "  API docs  : http://127.0.0.1:8080/docs"
Write-Host ""
Write-Host "  Stop all  : powershell -File scripts\stop-all.ps1"

# ---------------------------------------------------------------------------
# Phase 5 — Supervised mode: delegate to Go supervisor if available,
#            otherwise fall back to legacy watchdog
# ---------------------------------------------------------------------------
Write-Host ""
$SupervisorExe = Join-Path $script:Root ".runtime\bin\supervisor.exe"
$SupervisorCfg = Join-Path $script:Root "config\supervisor.toml"

if (Test-Path $SupervisorExe) {
    Write-Host "=== Phase 5: Supervisor mode ===" -ForegroundColor Cyan
    Write-Host "  Delegating to Go supervisor (PID monitoring, auto-restart, health checks)"
    $SupervisorProc = Start-Process -FilePath $SupervisorExe -ArgumentList @("--config", $SupervisorCfg) -NoNewWindow -PassThru
    # The supervisor blocks until Ctrl+C; when it exits, all processes are shut down
    $SupervisorProc.WaitForExit()
    Write-Host "Supervisor exited."
} else {
    Write-Host "=== Phase 5: Watchdog (legacy, build supervisor.exe for production) ===" -ForegroundColor Cyan
    Write-Host "  Agent processes are monitored every 5 seconds." -ForegroundColor Yellow
    Write-Host "  Crashed agents will be auto-restarted." -ForegroundColor Yellow

    while ($true) {
        Start-Sleep -Seconds 5
        foreach ($agent in $NodeAgents) {
            $pidFile = Join-Path $PidDir "$($agent.Code).pid"
            if (-not (Test-Path $pidFile)) { continue }
            $pidVal = Get-Content $pidFile -ErrorAction SilentlyContinue
            if (-not $pidVal -or $pidVal -notmatch '^\d+$') { continue }

            $proc = Get-Process -Id $pidVal -ErrorAction SilentlyContinue
            if (-not $proc) {
                $cmd = $script:AgentRestartCommands[$agent.Code]
                if (-not $cmd) { continue }
                Write-Host "$(Get-Date -Format 'HH:mm:ss') Watchdog: $($agent.Code) (PID $pidVal) crashed, restarting..." -ForegroundColor Red
                $newProc = Start-Process -FilePath $cmd.Exe -ArgumentList $cmd.Args -WindowStyle Hidden -PassThru
                Set-Content -Path $pidFile -Value $newProc.Id
                Write-Host "$(Get-Date -Format 'HH:mm:ss') Watchdog: $($agent.Code) restarted (new PID $($newProc.Id))" -ForegroundColor Green
            }
        }
    }
}
