param(
  [string]$ApiUrl = "http://127.0.0.1:8080",
  [int]$DashboardPort = 5173,
  [string]$RuntimeRoot = "D:\MiniOGAS-VMs",
  [string]$TokenPath = "",
  [string]$AdminPassword = $env:MINIOGAS_ADMIN_PASSWORD,
  [string]$SessionToken = "",
  [switch]$CheckOnly,
  [switch]$RequireAiApi,
  [switch]$StartKali,
  [ValidateSet("development", "test", "digital_twin", "staging", "pilot", "production")]
  [string]$AppEnv = "digital_twin",
  [ValidateSet("simulated", "replay", "shadow", "live")]
  [string]$DataSource = "simulated",
  [ValidateSet("read_only", "operator_assisted", "controlled_write")]
  [string]$ControlMode = "operator_assisted",
  [string]$TenantId = "tenant-local",
  [string]$SiteId = "site-digital-twin",
  [ValidateSet("postgresql", "memory")]
  [string]$FactSource = "postgresql"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$ApiPort = [int]([uri]$ApiUrl).Port
if ($ApiPort -le 0) { $ApiPort = 8080 }
if (-not $TokenPath) { $TokenPath = Join-Path $RuntimeRoot "miniogas-token.txt" }
$PostgresConfigPath = Join-Path $RuntimeRoot "postgres.env"
$SessionTokenPath = Join-Path $RuntimeRoot "miniogas-session-token.txt"
$AuthConfigPath = Join-Path $RuntimeRoot "auth.env"
$RedisEnvPath = Join-Path $RuntimeRoot "data-platform\redis\redis.env"
$RedisCliPath = Join-Path $RuntimeRoot "memurai-portable\Memurai\memurai-cli.exe"
$MinioHealthUrl = "http://127.0.0.1:9000/minio/health/live"
$RuntimeLogRoot = Join-Path $ProjectRoot ".runtime\logs"
New-Item -ItemType Directory -Force -Path $RuntimeLogRoot | Out-Null

function Get-ServicePython {
  param([Parameter(Mandatory = $true)][string]$ServiceName)
  $python = Join-Path $ProjectRoot "services\$ServiceName\.venv\Scripts\python.exe"
  if (-not (Test-Path -LiteralPath $python)) {
    throw "$ServiceName virtual environment is missing: $python"
  }
  return $python
}

function Get-PostgresDsn {
  if (-not (Test-Path -LiteralPath $PostgresConfigPath)) {
    throw "PostgreSQL runtime configuration is missing: $PostgresConfigPath"
  }
  $line = Get-Content -LiteralPath $PostgresConfigPath | Where-Object { $_ -match '^POSTGRES_DSN=' } | Select-Object -First 1
  if (-not $line) {
    throw "POSTGRES_DSN is missing from $PostgresConfigPath"
  }
  $dsn = $line.Substring('POSTGRES_DSN='.Length).Trim()
  if (-not $dsn.StartsWith('postgresql://')) {
    throw "POSTGRES_DSN must use a postgresql:// URI."
  }
  return $dsn
}

function Get-AuthValue {
  param([string]$Name)
  if (-not (Test-Path -LiteralPath $AuthConfigPath)) { return "" }
  $line = Get-Content -LiteralPath $AuthConfigPath | Where-Object { $_ -match "^$Name=" } | Select-Object -First 1
  if (-not $line) { return "" }
  return $line.Substring($Name.Length + 1).Trim()
}

function Initialize-AuthConfig {
  New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
  $jwtSecret = Get-AuthValue "JWT_SECRET"
  $bootstrapPassword = Get-AuthValue "AUTH_BOOTSTRAP_PASSWORD"
  if (-not $jwtSecret) {
    $bytes = New-Object byte[] 48
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $jwtSecret = [Convert]::ToBase64String($bytes)
  }
  if (-not $bootstrapPassword) {
    # Preserve the previous local login secret on the one-time RBAC migration.
    $bootstrapPassword = if ($AdminPassword) { $AdminPassword } else { $token }
  }
  Set-Content -LiteralPath $AuthConfigPath -Value @(
    "JWT_SECRET=$jwtSecret",
    "AUTH_BOOTSTRAP_PASSWORD=$bootstrapPassword"
  ) -Encoding ASCII
  return @{ jwt_secret = $jwtSecret; bootstrap_password = $bootstrapPassword }
}

$PostgresDsn = Get-PostgresDsn
if ($CheckOnly -and (Test-Path -LiteralPath $SessionTokenPath)) {
  $LaunchSessionToken = (Get-Content -LiteralPath $SessionTokenPath -Raw).Trim()
} elseif ($SessionToken) {
  New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
  $LaunchSessionToken = $SessionToken
  Set-Content -LiteralPath $SessionTokenPath -Value $LaunchSessionToken -Encoding ASCII
} else {
  New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
  $LaunchSessionToken = [guid]::NewGuid().ToString()
  Set-Content -LiteralPath $SessionTokenPath -Value $LaunchSessionToken -Encoding ASCII
}
$env:OGAS_SESSION_TOKEN = $LaunchSessionToken
$env:CENTRAL_FACT_SOURCE = $FactSource
$env:APP_ENV = $AppEnv
$env:DATA_SOURCE = $DataSource
$env:CONTROL_MODE = $ControlMode
$env:DEMO_SEED_ENABLED = if (
  $AppEnv -in @("development", "test", "digital_twin") -and $DataSource -eq "simulated"
) { "true" } else { "false" }
$env:INDUSTRIAL_CONNECTOR_ENABLED = "false"
$env:PHYSICAL_WRITE_ENABLED = "false"
$env:TENANT_ID = $TenantId
$env:SITE_ID = $SiteId

function Test-PortListening {
  param([int]$Port)
  $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  return [bool]$listener
}

function Get-PortProcessIds {
  param([int]$Port)
  @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    Where-Object { $_ -and $_ -gt 0 })
}

function Stop-PortProcesses {
  param([int]$Port)
  foreach ($pidValue in Get-PortProcessIds $Port) {
    Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
  }
}

function Start-HiddenPowerShell {
  param(
    [string]$Name,
    [string]$Command,
    [string]$WorkingDirectory
  )
  Start-Process `
    -FilePath "C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe" `
    -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $Command `
    -WorkingDirectory $WorkingDirectory `
    -WindowStyle Hidden | Out-Null
  Write-Host "started $Name"
}

function Wait-JsonEndpoint {
  param(
    [string]$Name,
    [string]$Uri,
    [hashtable]$Headers = @{},
    [int]$TimeoutSec = 30
  )
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  $lastError = ""
  while ((Get-Date) -lt $deadline) {
    try {
      return Invoke-RestMethod -Uri $Uri -Headers $Headers -Method Get -TimeoutSec 5
    } catch {
      $lastError = $_.Exception.Message
      Start-Sleep -Seconds 1
    }
  }
  throw "$Name did not become ready at $Uri. Last error: $lastError"
}

function Test-HealthProof {
  param([string]$Uri)
  try {
    $health = Invoke-RestMethod -Uri "$Uri/health" -Method Get -TimeoutSec 5
    $startedAt = [DateTimeOffset]::Parse([string]$health.process_started_at)
    return [string]$health.session_token -eq [string]$LaunchSessionToken -and [int]$health.process_id -gt 0 -and $startedAt -le [DateTimeOffset]::UtcNow
  } catch {
    return $false
  }
}

function Test-CentralApiFresh {
  param([string]$Uri)
  return Test-HealthProof $Uri
}

function Test-ServiceFresh {
  param([string]$Uri)
  return Test-HealthProof $Uri
}

function New-CheckResult {
  param($Name, $Ok, $Detail, $Data = $null)
  [pscustomobject]@{
    name = $Name
    ok = [bool]$Ok
    detail = $Detail
    data = $Data
  }
}

Push-Location $ProjectRoot
try {
  $checks = New-Object System.Collections.Generic.List[object]
  $token = ""
  if (Test-Path -LiteralPath $TokenPath) {
    $token = (Get-Content -LiteralPath $TokenPath -Raw).Trim()
    $checks.Add((New-CheckResult "api-token" $true "Token file loaded; secret value is not printed." @{ path = $TokenPath }))
  } else {
    $checks.Add((New-CheckResult "api-token" $false "Token file not found: $TokenPath"))
  }
  $headers = if ($token) { @{ "X-OGAS-Token" = $token } } else { @{} }
  $dashboardHeaders = @{}
  $dashboardBearer = ""
  $authConfig = Initialize-AuthConfig
  . (Join-Path $PSScriptRoot "node-credentials.ps1")
  $nodeCredentialState = Get-MiniOgasNodeCredentialState `
    -RuntimeRoot $RuntimeRoot `
    -CreateIfMissing:$(-not $CheckOnly)
  $checks.Add((New-CheckResult "node-credentials" $true "Three distinct node credentials loaded; values are not printed." @{
    path = $nodeCredentialState.Path
    nodes = @($nodeCredentialState.Credentials.Keys)
  }))

  if ($CheckOnly) {
    if (-not (Test-Path -LiteralPath $RedisCliPath)) {
      $checks.Add((New-CheckResult "redis-projection-runtime" $false "Redis-compatible CLI is missing: $RedisCliPath"))
    } elseif (-not (Test-Path -LiteralPath $RedisEnvPath)) {
      $checks.Add((New-CheckResult "redis-projection-runtime" $false "Redis runtime configuration is missing: $RedisEnvPath"))
    } else {
      $redisPasswordLine = Get-Content -LiteralPath $RedisEnvPath | Where-Object { $_ -match '^REDIS_PASSWORD=' } | Select-Object -First 1
      $redisPassword = if ($redisPasswordLine) { $redisPasswordLine.Substring('REDIS_PASSWORD='.Length).Trim() } else { "" }
      if (-not $redisPassword) {
        $checks.Add((New-CheckResult "redis-projection-runtime" $false "REDIS_PASSWORD is missing from the protected runtime configuration."))
      } else {
        $previousRedisCliAuth = $env:REDISCLI_AUTH
        $env:REDISCLI_AUTH = $redisPassword
        try {
          $redisPing = @(& $RedisCliPath -h 127.0.0.1 -p 6379 ping 2>$null | Select-Object -Last 1)
          $appendOnly = @(& $RedisCliPath -h 127.0.0.1 -p 6379 --raw CONFIG GET appendonly 2>$null)
          $redisOk = ($redisPing -join "").Trim() -eq "PONG" -and $appendOnly -contains "yes"
          $checks.Add((New-CheckResult "redis-projection-runtime" $redisOk "Authenticated Redis PING and append-only persistence checked; credentials were not printed." @{
            authenticated = (($redisPing -join "").Trim() -eq "PONG")
            appendonly = ($appendOnly -contains "yes")
          }))
        } catch {
          $checks.Add((New-CheckResult "redis-projection-runtime" $false "Authenticated Redis runtime check failed: $($_.Exception.Message)"))
        } finally {
          $env:REDISCLI_AUTH = $previousRedisCliAuth
        }
      }
    }

    try {
      $minioHealth = Invoke-WebRequest -Uri $MinioHealthUrl -UseBasicParsing -TimeoutSec 5
      $checks.Add((New-CheckResult "minio-object-store" ($minioHealth.StatusCode -eq 200) "MinIO liveness returned HTTP $($minioHealth.StatusCode)." @{
        endpoint = $MinioHealthUrl
      }))
    } catch {
      $checks.Add((New-CheckResult "minio-object-store" $false "MinIO liveness check failed: $($_.Exception.Message)" @{
        endpoint = $MinioHealthUrl
      }))
    }
  }

  if (-not $CheckOnly) {
    $microservices = @(
      @{ name = "ai-dispatcher"; port = 8081; directory = "ai-dispatcher" },
      @{ name = "market-simulator"; port = 8082; directory = "market-simulator" },
      @{ name = "production-planner"; port = 8083; directory = "production-planner" }
    )
    foreach ($service in $microservices) {
      $serviceUrl = "http://127.0.0.1:$($service.port)"
      if ((Test-PortListening $service.port) -and -not (Test-ServiceFresh $serviceUrl)) {
        Stop-PortProcesses $service.port
        Start-Sleep -Seconds 1
      }
      if (-not (Test-PortListening $service.port)) {
        $serviceLog = Join-Path $RuntimeLogRoot "$($service.name).out.log"
        $servicePython = Get-ServicePython $service.directory
        $serviceCommand = @"
`$env:API_ACCESS_TOKEN = '$token'
`$env:OGAS_SESSION_TOKEN = '$LaunchSessionToken'
`$env:DEEPSEEK_API_KEY = '$env:DEEPSEEK_API_KEY'
`$env:DEEPSEEK_BASE_URL = '$env:DEEPSEEK_BASE_URL'
`$env:DEEPSEEK_MODEL = '$env:DEEPSEEK_MODEL'
Set-Location -LiteralPath '$ProjectRoot\services\$($service.directory)'
& '$servicePython' -m uvicorn app.main:app --host 127.0.0.1 --port $($service.port) *> '$serviceLog'
"@
        Start-HiddenPowerShell $service.name $serviceCommand (Join-Path $ProjectRoot "services\$($service.directory)")
      }
      $serviceHealth = Wait-JsonEndpoint "$($service.name) /health" "$serviceUrl/health" @{} 30
      $checks.Add((New-CheckResult $service.name ([string]$serviceHealth.session_token -eq [string]$LaunchSessionToken) "$($service.name) started for this launch session."))
    }
  }

  $apiWasListening = Test-PortListening $ApiPort
  if ($apiWasListening) {
    if (Test-CentralApiFresh $ApiUrl) {
      $checks.Add((New-CheckResult "central-api-process" $true "Port $ApiPort is listening and matches this launch session." @{ session_fresh = $true }))
    } elseif ($CheckOnly) {
      $checks.Add((New-CheckResult "central-api-process" $false "Port $ApiPort is listening, but /health does not match this launch session." @{ session_fresh = $false }))
    } else {
      Stop-PortProcesses $ApiPort
      Start-Sleep -Seconds 2
      $apiWasListening = $false
    }
  }
  if (-not $apiWasListening) {
    if ($CheckOnly) {
      $checks.Add((New-CheckResult "central-api-process" $false "Port $ApiPort is not listening."))
    } else {
      $apiLog = Join-Path $RuntimeLogRoot "central-api.out.log"
      $centralPython = Get-ServicePython "central-api"
$apiCommand = @"
`$env:OGAS_API_TOKEN = '$token'
`$env:API_ACCESS_TOKEN = '$token'
`$env:NODE_INGEST_TOKEN = '$token'
`$env:NODE_CREDENTIALS_JSON = '$($nodeCredentialState.Json)'
`$env:ALLOW_LEGACY_NODE_TOKEN_AUTH = 'false'
`$env:OGAS_SESSION_TOKEN = '$LaunchSessionToken'
`$env:APP_ENV = '$AppEnv'
`$env:DATA_SOURCE = '$DataSource'
`$env:CONTROL_MODE = '$ControlMode'
`$env:DEMO_SEED_ENABLED = '$($env:DEMO_SEED_ENABLED)'
`$env:INDUSTRIAL_CONNECTOR_ENABLED = 'false'
`$env:PHYSICAL_WRITE_ENABLED = 'false'
`$env:TENANT_ID = '$TenantId'
`$env:SITE_ID = '$SiteId'
`$env:PERSIST_ENABLED = 'true'
`$env:PERSIST_BACKEND = 'postgres'
`$env:CENTRAL_FACT_SOURCE = '$FactSource'
`$env:POSTGRES_DSN = '$PostgresDsn'
`$env:MICROSERVICES_ENABLED = 'true'
`$env:JWT_SECRET = '$($authConfig.jwt_secret)'
`$env:AUTH_BOOTSTRAP_PASSWORD = '$($authConfig.bootstrap_password)'
Set-Location -LiteralPath '$ProjectRoot\services\central-api'
& '$centralPython' -m uvicorn app.main:app --host 127.0.0.1 --port $ApiPort *> '$apiLog'
"@
      Start-HiddenPowerShell "central-api" $apiCommand (Join-Path $ProjectRoot "services\central-api")
      $health = Wait-JsonEndpoint "central-api /health" "$ApiUrl/health" @{} 40
      $checks.Add((New-CheckResult "central-api-process" ([string]$health.session_token -eq [string]$LaunchSessionToken) "central-api started for this launch session." @{
        session_fresh = [string]$health.session_token -eq [string]$LaunchSessionToken
      }))
    }
  }

  $apiCanCheck = Test-PortListening $ApiPort
  if ($apiCanCheck) {
    $health = Wait-JsonEndpoint "central-api /health" "$ApiUrl/health" @{} 40
    $checks.Add((New-CheckResult "central-api-health" ($health.status -eq "ok") "central-api returned $($health.status)." @{
      service = $health.service
      session_token_present = [bool]$health.session_token
    }))
    try {
      $dashboardPassword = if ($AdminPassword) { $AdminPassword } else { $authConfig.bootstrap_password }
      $loginBody = @{ operator = "admin"; password = $dashboardPassword } | ConvertTo-Json
      $dashboardLogin = Invoke-RestMethod -Uri "$ApiUrl/api/auth/login" -Method Post -ContentType "application/json" -Body $loginBody -TimeoutSec 70
      $dashboardHeaders = @{ "Authorization" = "Bearer $($dashboardLogin.access_token)" }
      $dashboardBearer = [string]$dashboardLogin.access_token
      $checks.Add((New-CheckResult "dashboard-auth" ([bool]$dashboardLogin.access_token) "Administrator bearer token issued for runtime verification."))
      try {
        $projection = Invoke-RestMethod -Uri "$ApiUrl/api/telemetry/projection/status" -Headers $dashboardHeaders -Method Get -TimeoutSec 10
        $projectionOk = [bool]$projection.available -and [string]$projection.provider -eq "redis" -and [string]$projection.authority -eq "postgresql-historian" -and [bool]$projection.active_generation
        $checks.Add((New-CheckResult "telemetry-projection" $projectionOk "Redis projection status and PostgreSQL Historian authority checked." @{
          provider = $projection.provider
          authority = $projection.authority
          active_generation_present = [bool]$projection.active_generation
        }))
      } catch {
        $checks.Add((New-CheckResult "telemetry-projection" $false "Telemetry projection check failed: $($_.Exception.Message)"))
      }
    } catch {
      $checks.Add((New-CheckResult "dashboard-auth" $false "Dashboard JWT login failed: $($_.Exception.Message)"))
    }
  }

  if (-not $CheckOnly) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "scripts\restart-local-nodes.ps1") `
      -RuntimeRoot $RuntimeRoot `
      -BearerToken $dashboardBearer
  }

  if (-not (Test-PortListening $DashboardPort)) {
    if ($CheckOnly) {
      $checks.Add((New-CheckResult "dashboard-process" $false "Port $DashboardPort is not listening."))
    } else {
      $dashboardLog = Join-Path $RuntimeLogRoot "dashboard.out.log"
      $dashboardCommand = @"
Set-Location -LiteralPath '$ProjectRoot\services\dashboard'
npm.cmd run dev -- --host 127.0.0.1 --port $DashboardPort *> '$dashboardLog'
"@
      Start-HiddenPowerShell "dashboard" $dashboardCommand (Join-Path $ProjectRoot "services\dashboard")
      Start-Sleep -Seconds 3
      $checks.Add((New-CheckResult "dashboard-process" (Test-PortListening $DashboardPort) "Dashboard dev server port $DashboardPort checked."))
    }
  } else {
    $checks.Add((New-CheckResult "dashboard-process" $true "Port $DashboardPort is already listening."))
  }

  if (-not (Test-PortListening $ApiPort)) {
    $checks.Add((New-CheckResult "ai-runtime" $false "Skipped because central-api is not listening."))
  } else {
  try {
    $auth = Wait-JsonEndpoint "AI runtime" "$ApiUrl/api/auth/status" @{} 15
    $runtime = $auth.runtime
    $smoke = $null
    $dashboardPassword = if ($AdminPassword) { $AdminPassword } else { $authConfig.bootstrap_password }
    if ($RequireAiApi -and [string]$runtime.source -ne "api" -and $dashboardPassword) {
      $loginBody = @{
        operator = "admin"
        password = $dashboardPassword
      } | ConvertTo-Json
      $login = Invoke-RestMethod -Uri "$ApiUrl/api/auth/login" -Method Post -ContentType "application/json" -Body $loginBody -TimeoutSec 70
      $smoke = $login.ai_smoke
      $auth = Wait-JsonEndpoint "AI runtime" "$ApiUrl/api/auth/status" @{} 15
      $runtime = $auth.runtime
    }
    $aiOk = if ($RequireAiApi) { [string]$runtime.source -eq "api" } else { [bool]$runtime.vault_present -or [string]$runtime.source -eq "api" }
    $checks.Add((New-CheckResult "ai-runtime" $aiOk "AI runtime source is $($runtime.source), status is $($runtime.status)." @{
      status = $runtime.status
      source = $runtime.source
      provider = $runtime.provider
      model = $runtime.model
      vault_present = $runtime.vault_present
      vault_unlocked = $runtime.vault_unlocked
      require_api = [bool]$RequireAiApi
      login_attempted = [bool]($RequireAiApi -and $dashboardPassword)
      smoke_ok = if ($null -ne $smoke) { [bool]$smoke.ok } else { $null }
    }))
  } catch {
    $checks.Add((New-CheckResult "ai-runtime" $false "AI runtime check failed: $($_.Exception.Message)"))
  }
  }

  if (-not (Test-PortListening $ApiPort)) {
    $checks.Add((New-CheckResult "node-heartbeats" $false "Skipped because central-api is not listening."))
  } else {
  try {
    $snapshot = Wait-JsonEndpoint "dashboard snapshot" "$ApiUrl/api/dashboard/snapshot?mode=normal" $dashboardHeaders 30
    $nodes = @($snapshot.nodes)
    $connected = [int]$snapshot.system.nodes_connected
    $expected = [int]$snapshot.system.nodes_expected
    $checks.Add((New-CheckResult "node-heartbeats" ($connected -eq $expected -and $expected -ge 3) "$connected/$expected production snapshot nodes are connected." @{
      schema_version = $snapshot.schema_version
      data_source = $snapshot.data_source
      simulation_engine = $snapshot.run.simulation_engine
      scenario_id = $snapshot.run.scenario_id
      nodes = @($nodes | ForEach-Object { "$($_.node_code):$($_.status):$($_.runtime.simulation_engine):$($_.runtime.scenario_id)" })
      active_issues = @($snapshot.alerts).Count
      audit_events = @($snapshot.audit.recent_events).Count
    }))
  } catch {
    $checks.Add((New-CheckResult "node-heartbeats" $false "Dashboard snapshot check failed: $($_.Exception.Message)"))
  }
  }

  $vboxManage = "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
  if (Test-Path -LiteralPath $vboxManage) {
    $env:VBOX_USER_HOME = Join-Path $RuntimeRoot "VirtualBoxHome"
    $vboxHomeUsed = $env:VBOX_USER_HOME
    $oldErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $kaliInfo = @(& $vboxManage showvminfo miniogas-kali-redteam --machinereadable 2>$null)
    $kaliExitCode = $LASTEXITCODE
    $ErrorActionPreference = $oldErrorPreference
    if ($kaliExitCode -ne 0) {
      Remove-Item Env:\VBOX_USER_HOME -ErrorAction SilentlyContinue
      $vboxHomeUsed = "default"
      $oldErrorPreference = $ErrorActionPreference
      $ErrorActionPreference = "Continue"
      $kaliInfo = @(& $vboxManage showvminfo miniogas-kali-redteam --machinereadable 2>$null)
      $kaliExitCode = $LASTEXITCODE
      $ErrorActionPreference = $oldErrorPreference
    }
    $kaliVboxPath = Join-Path $RuntimeRoot "kali-redteam\extracted\miniogas-kali-redteam\miniogas-kali-redteam.vbox"
    if ($kaliExitCode -ne 0 -and $StartKali -and -not $CheckOnly -and (Test-Path -LiteralPath $kaliVboxPath)) {
      & $vboxManage registervm $kaliVboxPath | Out-Null
      $vboxHomeUsed = "default"
      $oldErrorPreference = $ErrorActionPreference
      $ErrorActionPreference = "Continue"
      $kaliInfo = @(& $vboxManage showvminfo miniogas-kali-redteam --machinereadable 2>$null)
      $kaliExitCode = $LASTEXITCODE
      $ErrorActionPreference = $oldErrorPreference
    }
    if ($kaliExitCode -ne 0) {
      $kaliOptionalOk = -not [bool]$StartKali -and (Test-Path -LiteralPath $kaliVboxPath)
      $checks.Add((New-CheckResult "kali-redteam-vm" $kaliOptionalOk "Kali red-team VM is not registered; the disk image is present and can be registered with -StartKali." @{
        raw = @($kaliInfo)
        requested_start = [bool]$StartKali
        ssh_port = 2224
        vbox_path = if (Test-Path -LiteralPath $kaliVboxPath) { $kaliVboxPath } else { "" }
      }))
    } else {
      $kaliState = (($kaliInfo | Select-String -Pattern '^VMState=').Line -replace '^VMState=', '').Trim('"')
      if ($StartKali -and $kaliState -ne "running" -and -not $CheckOnly) {
        & $vboxManage startvm miniogas-kali-redteam --type headless | Out-Null
        Start-Sleep -Seconds 5
        $oldErrorPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $kaliInfo = @(& $vboxManage showvminfo miniogas-kali-redteam --machinereadable 2>$null)
        $ErrorActionPreference = $oldErrorPreference
        $kaliState = (($kaliInfo | Select-String -Pattern '^VMState=').Line -replace '^VMState=', '').Trim('"')
      }
      $checks.Add((New-CheckResult "kali-redteam-vm" ($kaliState -eq "running" -or -not $StartKali) "Kali red-team VM state is $kaliState." @{
        state = $kaliState
        requested_start = [bool]$StartKali
        ssh_port = 2224
        vbox_user_home = $vboxHomeUsed
      }))
    }
  } else {
    $checks.Add((New-CheckResult "kali-redteam-vm" $false "VBoxManage.exe was not found."))
  }

  $allOk = -not ($checks | Where-Object { -not $_.ok })
  $report = [pscustomobject]@{
    ok = [bool]$allOk
    checked_at = (Get-Date).ToString("s")
    api_url = $ApiUrl
    dashboard_url = "http://127.0.0.1:$DashboardPort"
    checks = $checks
  }
  $report | ConvertTo-Json -Depth 8
  if (-not $allOk) { exit 1 }
} finally {
  Pop-Location
}
