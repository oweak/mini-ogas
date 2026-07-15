$script:MiniOgasProductionNodeCodes = @(
  "turning-workshop-01",
  "milling-workshop-01",
  "grinding-workshop-01"
)

function New-MiniOgasNodeToken {
  $bytes = New-Object byte[] 32
  $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
  return ([System.BitConverter]::ToString($bytes)).Replace("-", "").ToLowerInvariant()
}

function Get-MiniOgasNodeCredentialState {
  param(
    [Parameter(Mandatory = $true)][string]$RuntimeRoot,
    [switch]$CreateIfMissing
  )

  $path = Join-Path $RuntimeRoot "node-credentials.json"
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
    if (-not $CreateIfMissing) {
      throw "Node credential file is missing: $path"
    }
    New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
    $created = [ordered]@{}
    foreach ($nodeCode in $script:MiniOgasProductionNodeCodes) {
      $created[$nodeCode] = New-MiniOgasNodeToken
    }
    Set-Content -LiteralPath $path -Value ($created | ConvertTo-Json -Compress) -Encoding UTF8
  }

  $parsed = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
  $credentials = [ordered]@{}
  foreach ($nodeCode in $script:MiniOgasProductionNodeCodes) {
    $property = $parsed.PSObject.Properties[$nodeCode]
    $token = if ($property) { [string]$property.Value } else { "" }
    if ($token.Length -lt 32) {
      throw "Credential for $nodeCode is missing or shorter than 32 characters in $path"
    }
    $credentials[$nodeCode] = $token
  }
  $unique = @($credentials.Values | Select-Object -Unique)
  if ($unique.Count -ne $credentials.Count) {
    throw "Every production node must have a distinct credential in $path"
  }

  return [pscustomobject]@{
    Path = $path
    Credentials = $credentials
    Json = ($credentials | ConvertTo-Json -Compress)
  }
}
