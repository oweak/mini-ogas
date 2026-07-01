param(
  [string]$ApiUrl = "http://127.0.0.1:8080",
  [string]$RuntimeRoot = "D:\MiniOGAS-VMs",
  [string]$Operator = "",
  [string]$Password = $env:MINIOGAS_ADMIN_PASSWORD
)

$ErrorActionPreference = "Stop"

$AuthConfigPath = Join-Path $RuntimeRoot "auth.env"

function Get-AuthValue {
  param([string]$Name)
  if (-not (Test-Path -LiteralPath $AuthConfigPath)) { return "" }
  $line = Get-Content -LiteralPath $AuthConfigPath | Where-Object { $_ -match "^$Name=" } | Select-Object -First 1
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

$health = Invoke-RestMethod -Uri "$ApiUrl/health" -TimeoutSec 20

function Invoke-JsonWithRetry {
  param(
    [string]$Uri,
    [int]$TimeoutSec = 70,
    [int]$Attempts = 2
  )
  $lastError = $null
  for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
    try {
      return Invoke-RestMethod -Uri $Uri -TimeoutSec $TimeoutSec
    } catch {
      $lastError = $_
      if ($attempt -lt $Attempts) { Start-Sleep -Seconds 2 }
    }
  }
  throw $lastError
}

$preflight = Invoke-JsonWithRetry "$ApiUrl/api/system/preflight" 70 2

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

$auth = $null
if ([string]::IsNullOrWhiteSpace($Password)) {
  $auth = [pscustomobject]@{
    ok = $false
    error = "Administrator password not configured; set MINIOGAS_ADMIN_PASSWORD or AUTH_BOOTSTRAP_PASSWORD in auth.env."
  }
} else {
  try {
    $body = New-LoginJsonBody $Operator $Password
    $auth = Invoke-RestMethod -Uri "$ApiUrl/api/auth/login" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 60
    $tokenPresent = -not [string]::IsNullOrWhiteSpace([string]$auth.access_token)
    if ($auth.PSObject.Properties.Name -contains "access_token") {
      $auth.PSObject.Properties.Remove("access_token")
    }
    $auth | Add-Member -NotePropertyName "access_token_present" -NotePropertyValue $tokenPresent -Force
  } catch {
    $auth = [pscustomobject]@{
      ok = $false
      error = $_.Exception.Message
    }
  }
}

[pscustomobject]@{
  health = $health
  preflight = $preflight
  login_probe = $auth
} | ConvertTo-Json -Depth 10
