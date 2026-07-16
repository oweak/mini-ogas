param(
  [string]$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path,
  [string]$Provider = "deepseek",
  [string]$Model = "deepseek-v4-pro",
  [string]$BaseUrl = "https://api.deepseek.com/v1",
  [string]$VaultPath = "",
  [switch]$UseEnvironment
)

$ErrorActionPreference = "Stop"

$dispatcherDir = Join-Path $ProjectRoot "services\ai-dispatcher"
if (-not $VaultPath) {
  $VaultPath = Join-Path $dispatcherDir "secrets\ai-vault.json"
}

function ConvertFrom-SecureStringPlainText([securestring]$Secure) {
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
  try {
    [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
  } finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
  }
}

if ($UseEnvironment) {
  $apiKey = $env:MINIOGAS_AI_API_KEY
  $password = $env:MINIOGAS_VAULT_PASSWORD
  if ([string]::IsNullOrWhiteSpace($apiKey) -or [string]::IsNullOrWhiteSpace($password)) {
    throw "UseEnvironment requires MINIOGAS_AI_API_KEY and MINIOGAS_VAULT_PASSWORD."
  }
} else {
  $apiKey = ConvertFrom-SecureStringPlainText (Read-Host "AI API key" -AsSecureString)
  $password = ConvertFrom-SecureStringPlainText (Read-Host "Vault password" -AsSecureString)
}

if ([string]::IsNullOrWhiteSpace($apiKey) -or $apiKey.Length -lt 12) {
  throw "AI API key is empty or too short."
}
if ([string]::IsNullOrWhiteSpace($password)) {
  throw "Vault password is empty."
}

$env:MINIOGAS_AI_API_KEY = $apiKey
$env:MINIOGAS_VAULT_PASSWORD = $password
$env:MINIOGAS_AI_PROVIDER = $Provider
$env:MINIOGAS_AI_MODEL = $Model
$env:MINIOGAS_AI_BASE_URL = $BaseUrl
$env:MINIOGAS_AI_VAULT_PATH = $VaultPath

Push-Location $dispatcherDir
try {
  python .\create_ai_vault.py | Out-Host
  if ($LASTEXITCODE -ne 0) {
    throw "create_ai_vault.py failed"
  }

  $checkScript = @'
import json
import os
from pathlib import Path
from app.vault import decrypt_vault_payload

vault_path = Path(os.environ["MINIOGAS_AI_VAULT_PATH"])
payload = decrypt_vault_payload(json.loads(vault_path.read_text(encoding="utf-8")), os.environ["MINIOGAS_VAULT_PASSWORD"])
print(json.dumps({
    "ok": True,
    "provider": payload.get("provider"),
    "model": payload.get("model"),
    "base_url": payload.get("base_url"),
    "key_present": bool(payload.get("api_key")),
}, ensure_ascii=False))
'@
  $checkScript | python -
  if ($LASTEXITCODE -ne 0) {
    throw "AI vault verification failed"
  }
} finally {
  Pop-Location
  Remove-Item Env:\MINIOGAS_AI_API_KEY -ErrorAction SilentlyContinue
  Remove-Item Env:\MINIOGAS_VAULT_PASSWORD -ErrorAction SilentlyContinue
  Remove-Item Env:\MINIOGAS_AI_PROVIDER -ErrorAction SilentlyContinue
  Remove-Item Env:\MINIOGAS_AI_MODEL -ErrorAction SilentlyContinue
  Remove-Item Env:\MINIOGAS_AI_BASE_URL -ErrorAction SilentlyContinue
  Remove-Item Env:\MINIOGAS_AI_VAULT_PATH -ErrorAction SilentlyContinue
}

Write-Host "AI vault reset complete: $VaultPath"
Write-Host "Restart ai-dispatcher, then log in with the vault password to unlock the model runtime."
