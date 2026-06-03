$ErrorActionPreference = "Stop"
. "$PSScriptRoot\env.ps1"

$packageRoot = Join-Path $script:RuntimeDir "cloud-node-package"
$distRoot = Join-Path $script:RuntimeDir "dist"
$archive = Join-Path $distRoot "mini-ogas-cloud-node.tar.gz"

if (Test-Path $packageRoot) {
    Remove-Item -LiteralPath $packageRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $packageRoot, $distRoot | Out-Null

Push-Location (Join-Path $script:Root "services\node-agent")
$oldGoos = $env:GOOS
$oldGoarch = $env:GOARCH
$env:GOOS = "linux"
$env:GOARCH = "amd64"
go build -o (Join-Path $packageRoot "node-agent") ./cmd/node-agent
$env:GOOS = $oldGoos
$env:GOARCH = $oldGoarch
Pop-Location

Copy-Item -LiteralPath (Join-Path $script:Root "deploy\cloud-node\install-node-agent.sh") -Destination $packageRoot
Copy-Item -LiteralPath (Join-Path $script:Root "deploy\cloud-node\mini-ogas-node-agent.service") -Destination $packageRoot
Copy-Item -LiteralPath (Join-Path $script:Root "deploy\env.cloud-node.example") -Destination (Join-Path $packageRoot "node-agent.env.example")
Copy-Item -LiteralPath (Join-Path $script:Root "scripts") -Destination (Join-Path $packageRoot "scripts") -Recurse

if (Test-Path $archive) {
    Remove-Item -LiteralPath $archive -Force
}

Push-Location $packageRoot
tar -czf $archive .
Pop-Location

Write-Host "Cloud node package created: $archive"
