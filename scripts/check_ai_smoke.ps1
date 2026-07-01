param(
  [string]$ApiUrl = "http://127.0.0.1:8080",
  [string]$RuntimeRoot = "D:\MiniOGAS-VMs",
  [string]$Operator = "",
  [string]$Password = $env:MINIOGAS_ADMIN_PASSWORD,
  [int]$Attempts = 3,
  [int]$RetryDelaySec = 2
)

$ErrorActionPreference = "Stop"

function New-CheckResult($ok, $detail, $data = $null) {
  [pscustomobject]@{
    ok = [bool]$ok
    detail = $detail
    data = $data
  }
}

function ConvertTo-JsonStringLiteral([string]$Text) {
  $builder = New-Object System.Text.StringBuilder
  foreach ($char in $Text.ToCharArray()) {
    $code = [int][char]$char
    if ($char -eq '"') {
      [void]$builder.Append('\"')
    } elseif ($char -eq '\') {
      [void]$builder.Append('\\')
    } elseif ($code -lt 32 -or $code -gt 126) {
      [void]$builder.Append(('\u{0:x4}' -f $code))
    } else {
      [void]$builder.Append($char)
    }
  }
  return $builder.ToString()
}

function New-LoginJsonBody([string]$OperatorName, [string]$VaultPassword) {
  $operatorJson = ConvertTo-JsonStringLiteral $OperatorName
  $passwordJson = ConvertTo-JsonStringLiteral $VaultPassword
  return "{`"operator`":`"$operatorJson`",`"password`":`"$passwordJson`"}"
}

function Get-AuthValue {
  param([string]$Name)
  $authConfigPath = Join-Path $RuntimeRoot "auth.env"
  if (-not (Test-Path -LiteralPath $authConfigPath)) { return "" }
  $line = Get-Content -LiteralPath $authConfigPath | Where-Object { $_ -match "^$Name=" } | Select-Object -First 1
  if (-not $line) { return "" }
  return $line.Substring($Name.Length + 1).Trim().Trim('"').Trim("'")
}

if ([string]::IsNullOrWhiteSpace($Operator)) {
  $Operator = Get-AuthValue "AUTH_BOOTSTRAP_USERNAME"
  if ([string]::IsNullOrWhiteSpace($Operator)) { $Operator = "admin" }
}
if ([string]::IsNullOrWhiteSpace($Password)) {
  $Password = Get-AuthValue "AUTH_BOOTSTRAP_PASSWORD"
}

if ([string]::IsNullOrWhiteSpace($Password)) {
  $result = New-CheckResult $false "Administrator password is required for strict AI smoke verification." @{
    accepted_sources = @("MINIOGAS_ADMIN_PASSWORD", "D:\MiniOGAS-VMs\auth.env")
  }
  $result | ConvertTo-Json -Depth 6
  exit 1
}

$login = $null
$lastError = $null
$attemptsUsed = 0
for ($attempt = 1; $attempt -le [Math]::Max(1, $Attempts); $attempt++) {
  $attemptsUsed = $attempt
  try {
    $body = New-LoginJsonBody $Operator $Password
    $candidate = Invoke-RestMethod -Uri "$ApiUrl/api/auth/login" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 90
    $login = $candidate
    $candidateOk = [bool]$candidate.ok -and [bool]$candidate.runtime.vault_unlocked -and [bool]$candidate.ai_smoke.ok -and [string]$candidate.ai_smoke.source -eq "api"
    if ($candidateOk) {
      break
    }
    $lastError = $candidate.ai_smoke.error
  } catch {
    $lastError = $_.Exception.Message
  }
  if ($attempt -lt [Math]::Max(1, $Attempts)) {
    Start-Sleep -Seconds $RetryDelaySec
  }
}

if ($null -eq $login) {
  $result = New-CheckResult $false "AI smoke login failed: $lastError" @{
    attempts = $attemptsUsed
  }
  $result | ConvertTo-Json -Depth 6
  exit 1
}

$runtime = $login.runtime
$smoke = $login.ai_smoke
$ok = [bool]$login.ok -and [bool]$runtime.vault_unlocked -and [bool]$smoke.ok -and [string]$smoke.source -eq "api"
$detail = if ($ok) {
  "AI vault unlocked and startup smoke test proved a live API model call."
} elseif (-not [bool]$login.ok) {
  "Administrator login did not succeed."
} elseif (-not [bool]$runtime.vault_unlocked) {
  "AI vault was not unlocked after administrator login."
} elseif (-not [bool]$smoke.ok) {
  "AI startup smoke test failed; runtime must be treated as rule fallback."
} else {
  "AI startup smoke test did not prove source=api."
}

$result = New-CheckResult $ok $detail @{
  login_ok = [bool]$login.ok
  runtime_status = $runtime.status
  provider = $runtime.provider
  model = $runtime.model
  source = $runtime.source
  vault_present = [bool]$runtime.vault_present
  vault_unlocked = [bool]$runtime.vault_unlocked
  smoke_ok = [bool]$smoke.ok
  smoke_source = $smoke.source
  smoke_status = $smoke.status
  smoke_error = $smoke.error
  attempts = $attemptsUsed
}

$result | ConvertTo-Json -Depth 6
if (-not $ok) {
  exit 1
}
