$ErrorActionPreference = "Stop"
. "$PSScriptRoot\env.ps1"

Write-Host "== Runtime versions =="
& (Get-ServicePython "central-api") --version
node --version
npm --version
go version

Write-Host "== Python compile checks =="
foreach ($service in @("central-api", "ai-dispatcher", "market-simulator", "production-planner")) {
    $python = Get-ServicePython $service
    Push-Location (Join-Path $script:Root "services\$service")
    & $python -m compileall app
    Pop-Location
}

Write-Host "== Dashboard build =="
Push-Location (Join-Path $script:Root "services\dashboard")
npm run build
Pop-Location

Write-Host "== Go node-agent build =="
Push-Location (Join-Path $script:Root "services\node-agent")
go build -o (Join-Path $script:BinDir "node-agent.exe") ./cmd/node-agent
Pop-Location

Write-Host "All compile checks passed."

Write-Host ""
Write-Host "== Runtime health checks =="
$services = @(
    @{Name="central-api";        Port=8080; HasHealth=$true},
    @{Name="ai-dispatcher";      Port=8081; HasHealth=$true},
    @{Name="market-simulator";   Port=8082; HasHealth=$true},
    @{Name="production-planner"; Port=8083; HasHealth=$true},
    @{Name="dashboard";          Port=5173; HasHealth=$false}
)
$allRunning = $true
foreach ($svc in $services) {
    $url = "http://127.0.0.1:$($svc.Port)/health"
    try {
        if ($svc.HasHealth) {
            $response = Invoke-WebRequest -Uri $url -TimeoutSec 3 -UseBasicParsing
            $body = $response.Content | ConvertFrom-Json
            $statusText = $body.status
            Write-Host "  [PASS] $($svc.Name) :$($svc.Port) - $statusText" -ForegroundColor Green
        } else {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$($svc.Port)" -TimeoutSec 3 -UseBasicParsing
            Write-Host "  [PASS] $($svc.Name) :$($svc.Port) - HTTP $($response.StatusCode)" -ForegroundColor Green
        }
    } catch {
        $allRunning = $false
        Write-Host "  [FAIL] $($svc.Name) :$($svc.Port) - not reachable" -ForegroundColor Red
    }
}

if (-not $allRunning) {
    Write-Host ""
    Write-Host "Some services are NOT running. Start them with:" -ForegroundColor Yellow
    Write-Host "  .\scripts\start-all.ps1" -ForegroundColor Yellow
    exit 1
}
Write-Host "All runtime health checks passed."
