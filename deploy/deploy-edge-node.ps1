param(
  [Parameter(Mandatory = $true)]
  [string]$ServerHost,

  [Parameter(Mandatory = $true)]
  [string]$ServerUser,

  [int]$ServerPort = 22,

  [string]$IdentityFile = "",

  [Parameter(Mandatory = $true)]
  [string]$CentralApiUrl,

  [string]$NodeCode = "milling-workshop-01",
  [string]$WorkshopType = "milling",
  [ValidateSet("simple", "simpy")]
  [string]$SimulationEngine = "simpy",
  [string]$SimulationSeed = "20260613",
  [string]$ScenarioId = "SCN-MILLING-SIMPY-SINGLE-001",
  [string]$RunId = "RUN-EDGE-$(Get-Date -Format yyyyMMdd)-001",
  [string]$OgasApiToken = $env:OGAS_API_TOKEN
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($OgasApiToken)) {
  throw "OGAS_API_TOKEN is required. Pass -OgasApiToken or set the OGAS_API_TOKEN environment variable from the central deployment token."
}

$projectRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$remoteRoot = "~/mini-ogas-edge"
$sshTarget = "${ServerUser}@${ServerHost}"

$sshBase = @("-p", "$ServerPort")
$scpBase = @("-P", "$ServerPort")
if ($IdentityFile -ne "") {
  $sshBase += @("-i", $IdentityFile)
  $scpBase += @("-i", $IdentityFile)
}

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("mini-ogas-edge-" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmp | Out-Null
New-Item -ItemType Directory -Path (Join-Path $tmp "deploy") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $tmp "services\node-agent") | Out-Null

Copy-Item -LiteralPath (Join-Path $projectRoot "deploy\docker-compose.edge.yml") -Destination (Join-Path $tmp "deploy\docker-compose.edge.yml")
Copy-Item -LiteralPath (Join-Path $projectRoot "services\node-agent\Dockerfile") -Destination (Join-Path $tmp "services\node-agent\Dockerfile")
Copy-Item -LiteralPath (Join-Path $projectRoot "services\node-agent\.dockerignore") -Destination (Join-Path $tmp "services\node-agent\.dockerignore")
Copy-Item -LiteralPath (Join-Path $projectRoot "services\node-agent\simulator.py") -Destination (Join-Path $tmp "services\node-agent\simulator.py")

@"
NODE_CODE=$NodeCode
WORKSHOP_TYPE=$WorkshopType
CENTRAL_API_URL=$CentralApiUrl
OGAS_API_TOKEN=$OgasApiToken
LOCAL_DB_PATH=/data/node.db
HEARTBEAT_SEC=5
EMERGENCY_AFTER_TICKS=18
SIMULATION_MODE=normal
SIMULATION_ENGINE=$SimulationEngine
SIMULATION_SPEED=1
SIMULATION_RANDOM_SEED=$SimulationSeed
OGAS_RUN_ID=$RunId
OGAS_SCENARIO_ID=$ScenarioId
NODE_DEPLOYMENT_MODE=cloud
"@ | Set-Content -LiteralPath (Join-Path $tmp "deploy\.env.edge") -Encoding UTF8

& ssh @sshBase $sshTarget "mkdir -p $remoteRoot/deploy $remoteRoot/services/node-agent"
& scp @scpBase (Join-Path $tmp "deploy\docker-compose.edge.yml") "${sshTarget}:$remoteRoot/deploy/docker-compose.edge.yml"
& scp @scpBase (Join-Path $tmp "deploy\.env.edge") "${sshTarget}:$remoteRoot/deploy/.env.edge"
& scp @scpBase (Join-Path $tmp "services\node-agent\Dockerfile") "${sshTarget}:$remoteRoot/services/node-agent/Dockerfile"
& scp @scpBase (Join-Path $tmp "services\node-agent\.dockerignore") "${sshTarget}:$remoteRoot/services/node-agent/.dockerignore"
& scp @scpBase (Join-Path $tmp "services\node-agent\simulator.py") "${sshTarget}:$remoteRoot/services/node-agent/simulator.py"

& ssh @sshBase $sshTarget "cd $remoteRoot/deploy && docker compose -f docker-compose.edge.yml up -d --build"
& ssh @sshBase $sshTarget "cd $remoteRoot/deploy && docker compose -f docker-compose.edge.yml ps"

Remove-Item -LiteralPath $tmp -Recurse -Force

Write-Host "Deployed Mini-OGAS edge node $NodeCode to $ServerHost"
