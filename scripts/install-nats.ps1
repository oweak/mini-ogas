param(
  [string]$RuntimeRoot = "D:\MiniOGAS-VMs",
  [string]$Version = "2.14.3",
  [switch]$Force
)

$ErrorActionPreference = "Stop"
$NatsRoot = Join-Path $RuntimeRoot "nats"
$BinRoot = Join-Path $NatsRoot "bin"
$NatsBinary = Join-Path $BinRoot "nats-server.exe"
$ArchiveName = "nats-server-v$Version-windows-amd64.zip"
$ReleaseRoot = "https://github.com/nats-io/nats-server/releases/download/v$Version"
$ArchiveUrl = "$ReleaseRoot/$ArchiveName"
$ChecksumsUrl = "$ReleaseRoot/SHA256SUMS"
$DownloadRoot = Join-Path $NatsRoot "downloads"
$ArchivePath = Join-Path $DownloadRoot $ArchiveName
$ChecksumsPath = Join-Path $DownloadRoot "SHA256SUMS-v$Version"
$ExtractRoot = Join-Path $DownloadRoot "extract-v$Version"

if ((Test-Path -LiteralPath $NatsBinary) -and -not $Force) {
  $current = (& $NatsBinary --version 2>&1 | Out-String).Trim()
  if ($current -match "v$([regex]::Escape($Version))\b") {
    [pscustomobject]@{
      status = "already-installed"
      version = $current
      binary = $NatsBinary
    } | ConvertTo-Json
    exit 0
  }
  throw "A different NATS Server is installed at $NatsBinary. Pass -Force to replace it."
}

New-Item -ItemType Directory -Force -Path $BinRoot, $DownloadRoot | Out-Null
Invoke-WebRequest -Uri $ArchiveUrl -OutFile $ArchivePath -UseBasicParsing
Invoke-WebRequest -Uri $ChecksumsUrl -OutFile $ChecksumsPath -UseBasicParsing

$checksumLine = Get-Content -LiteralPath $ChecksumsPath |
  Where-Object { $_ -match "\s+$([regex]::Escape($ArchiveName))$" } |
  Select-Object -First 1
if (-not $checksumLine) {
  throw "Official SHA256SUMS does not contain $ArchiveName"
}
$expectedHash = ($checksumLine -split "\s+")[0].ToLowerInvariant()
$actualHash = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $expectedHash) {
  throw "NATS archive checksum mismatch: expected $expectedHash, received $actualHash"
}

$resolvedNatsRoot = [System.IO.Path]::GetFullPath($NatsRoot).TrimEnd('\') + '\'
$resolvedExtractRoot = [System.IO.Path]::GetFullPath($ExtractRoot)
if (-not $resolvedExtractRoot.StartsWith($resolvedNatsRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Refusing to replace extraction directory outside the NATS runtime root: $resolvedExtractRoot"
}
if (Test-Path -LiteralPath $resolvedExtractRoot) {
  Remove-Item -LiteralPath $resolvedExtractRoot -Recurse -Force
}
Expand-Archive -LiteralPath $ArchivePath -DestinationPath $resolvedExtractRoot -Force
$extractedBinary = Get-ChildItem -LiteralPath $resolvedExtractRoot -Recurse -File -Filter "nats-server.exe" |
  Select-Object -First 1
if (-not $extractedBinary) {
  throw "The verified archive did not contain nats-server.exe"
}
Copy-Item -LiteralPath $extractedBinary.FullName -Destination $NatsBinary -Force
$installedVersion = (& $NatsBinary --version 2>&1 | Out-String).Trim()
if ($installedVersion -notmatch "v$([regex]::Escape($Version))\b") {
  throw "Installed NATS Server version does not match v${Version}: $installedVersion"
}

[pscustomobject]@{
  status = "installed"
  version = $installedVersion
  binary = $NatsBinary
  archive_sha256 = $actualHash
  checksum_source = $ChecksumsUrl
} | ConvertTo-Json
