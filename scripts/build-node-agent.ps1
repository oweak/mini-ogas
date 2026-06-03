$ErrorActionPreference = "Stop"
. "$PSScriptRoot\env.ps1"

$output = Join-Path $script:BinDir "node-agent.exe"
Push-Location (Join-Path $script:Root "services\node-agent")
go build -o $output ./cmd/node-agent
Pop-Location

Write-Host "Built $output"
