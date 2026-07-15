param(
  [switch]$CheckOnly,
  [string]$RuntimeRoot = "D:\MiniOGAS-VMs"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
  Write-Output '{"ok":true,"status":"not_applicable","reason":"Windows ACL check"}'
  exit 0
}

$currentIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$allowedSids = @(
  $currentIdentity.User.Value,
  "S-1-5-18",
  "S-1-5-32-544"
)
$targets = New-Object System.Collections.Generic.List[object]

$envPath = Join-Path $ProjectRoot ".env"
if (Test-Path -LiteralPath $envPath -PathType Leaf) {
  $targets.Add([pscustomobject]@{ Path = $envPath; IsDirectory = $false })
}

$secretsPath = Join-Path $ProjectRoot "services\central-api\secrets"
if (Test-Path -LiteralPath $secretsPath -PathType Container) {
  $targets.Add([pscustomobject]@{ Path = $secretsPath; IsDirectory = $true })
  Get-ChildItem -LiteralPath $secretsPath -File | ForEach-Object {
    $targets.Add([pscustomobject]@{ Path = $_.FullName; IsDirectory = $false })
  }
}

$runtimeSecretPaths = @(
  (Join-Path $RuntimeRoot "miniogas-token.txt"),
  (Join-Path $RuntimeRoot "postgres.env"),
  (Join-Path $RuntimeRoot "auth.env"),
  (Join-Path $RuntimeRoot "miniogas-session-token.txt"),
  (Join-Path $RuntimeRoot "node-credentials.json"),
  (Join-Path $RuntimeRoot "nats\nats.env"),
  (Join-Path $RuntimeRoot "data-platform\redis\redis.env"),
  (Join-Path $RuntimeRoot "data-platform\redis\memurai.conf"),
  (Join-Path $RuntimeRoot "data-platform\minio\minio.env")
)
foreach ($runtimeSecretPath in $runtimeSecretPaths) {
  if (Test-Path -LiteralPath $runtimeSecretPath -PathType Leaf) {
    $targets.Add([pscustomobject]@{ Path = $runtimeSecretPath; IsDirectory = $false })
  }
}

function Convert-ToSid {
  param([System.Security.Principal.IdentityReference]$Identity)
  return $Identity.Translate([System.Security.Principal.SecurityIdentifier]).Value
}

function Test-RestrictedAcl {
  param([string]$Path)
  $acl = Get-Acl -LiteralPath $Path
  if (-not $acl.AreAccessRulesProtected) { return $false }
  foreach ($rule in $acl.Access) {
    if ($rule.AccessControlType -ne [System.Security.AccessControl.AccessControlType]::Allow) {
      continue
    }
    $sid = Convert-ToSid $rule.IdentityReference
    if ($allowedSids -notcontains $sid) { return $false }
  }
  return $true
}

function Set-RestrictedAcl {
  param([string]$Path, [bool]$IsDirectory)
  $acl = Get-Acl -LiteralPath $Path
  $acl.SetOwner($currentIdentity.User)
  $acl.SetAccessRuleProtection($true, $false)
  foreach ($rule in @($acl.Access)) {
    [void]$acl.RemoveAccessRuleSpecific($rule)
  }

  foreach ($sidValue in $allowedSids) {
    $sid = New-Object System.Security.Principal.SecurityIdentifier($sidValue)
    if ($IsDirectory) {
      $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $sid,
        [System.Security.AccessControl.FileSystemRights]::FullControl,
        [System.Security.AccessControl.InheritanceFlags]"ContainerInherit, ObjectInherit",
        [System.Security.AccessControl.PropagationFlags]::None,
        [System.Security.AccessControl.AccessControlType]::Allow
      )
    } else {
      $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $sid,
        [System.Security.AccessControl.FileSystemRights]::FullControl,
        [System.Security.AccessControl.AccessControlType]::Allow
      )
    }
    $acl.SetAccessRule($rule)
  }
  Set-Acl -LiteralPath $Path -AclObject $acl
}

$failures = New-Object System.Collections.Generic.List[string]
foreach ($target in $targets) {
  $isRestricted = Test-RestrictedAcl -Path $target.Path
  if (-not $CheckOnly -and -not $isRestricted) {
    Set-RestrictedAcl -Path $target.Path -IsDirectory $target.IsDirectory
    $isRestricted = Test-RestrictedAcl -Path $target.Path
  }
  if (-not $isRestricted) {
    $failures.Add((Resolve-Path -Relative -LiteralPath $target.Path))
  }
}

$result = [ordered]@{
  ok = ($failures.Count -eq 0)
  mode = $(if ($CheckOnly) { "check" } else { "protect" })
  target_count = $targets.Count
  allowed_principals = @("current_user", "SYSTEM", "Administrators")
  failures = @($failures)
}
$result | ConvertTo-Json -Compress
if ($failures.Count -gt 0) { exit 1 }
