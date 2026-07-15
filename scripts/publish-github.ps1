param(
    [string]$RepoName = "mini-ogas",
    [ValidateSet("private", "public", "internal")]
    [string]$Visibility = "private",
    [string]$RemoteName = "origin"
)

$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $Command $($Arguments -join ' ')"
    }
}

$repoRoot = git rev-parse --show-toplevel
if ($LASTEXITCODE -ne 0 -or -not $repoRoot) {
    throw "This script must run inside a Git repository."
}
Set-Location $repoRoot

$status = git status --porcelain
if ($status) {
    throw "Working tree is not clean. Commit or stash changes before publishing."
}

gh auth status | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "GitHub CLI is not logged in. Run 'gh auth login' first, then rerun this script."
}

$remoteExists = (git remote) -contains $RemoteName
if (-not $remoteExists) {
    $visibilityFlag = "--$Visibility"
    Invoke-Checked "gh" @(
        "repo",
        "create",
        $RepoName,
        $visibilityFlag,
        "--source",
        ".",
        "--remote",
        $RemoteName
    )
} else {
    $remoteUrl = git remote get-url $RemoteName
    Write-Host "Using existing remote $RemoteName -> $remoteUrl"
}

$branch = git rev-parse --abbrev-ref HEAD
if ($LASTEXITCODE -ne 0 -or -not $branch) {
    throw "Unable to detect current Git branch."
}

Invoke-Checked "git" @("push", "-u", $RemoteName, $branch)
Write-Host "Published $RepoName on branch $branch."
