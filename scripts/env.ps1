$ErrorActionPreference = "Stop"

$script:Root = Split-Path -Parent $PSScriptRoot
$script:RuntimeDir = Join-Path $script:Root ".runtime"
$script:ToolsDir = Join-Path $script:RuntimeDir "tools"
$script:GoRoot = Join-Path $script:ToolsDir "go"
$script:GoCacheRoot = Join-Path $script:RuntimeDir "go"
$script:BinDir = Join-Path $script:RuntimeDir "bin"
$script:NpmCache = Join-Path $script:RuntimeDir "npm-cache"

New-Item -ItemType Directory -Force -Path $script:RuntimeDir, $script:ToolsDir, $script:BinDir, $script:NpmCache | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $script:GoCacheRoot "pkg\mod"), (Join-Path $script:GoCacheRoot "build-cache") | Out-Null

if (Test-Path (Join-Path $script:GoRoot "bin\go.exe")) {
    $env:GOROOT = $script:GoRoot
    $env:GOMODCACHE = Join-Path $script:GoCacheRoot "pkg\mod"
    $env:GOCACHE = Join-Path $script:GoCacheRoot "build-cache"
    $env:PATH = "$script:GoRoot\bin;$env:PATH"
}

$env:npm_config_cache = $script:NpmCache

function Get-ServicePython {
    param([Parameter(Mandatory = $true)][string]$ServiceName)
    return Join-Path $script:Root "services\$ServiceName\.venv\Scripts\python.exe"
}
