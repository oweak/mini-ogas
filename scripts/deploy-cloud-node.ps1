param(
    [string]$ServerIp = "82.156.217.166",
    [string]$User = "ubuntu",
    [string]$KeyPath = "",
    [string]$NodeCode = "cloud-workshop-01",
    [string]$WorkshopType = "milling",
    [string]$CentralApiUrl = "http://127.0.0.1:18080"
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\env.ps1"

& "$PSScriptRoot\package-cloud-node.ps1"

$archive = Join-Path $script:RuntimeDir "dist\mini-ogas-cloud-node.tar.gz"
$remoteDir = "~/mini-ogas-cloud-node"
$sshTarget = "$User@$ServerIp"
$sshArgs = @()
if ($KeyPath -ne "") {
    $sshArgs += @("-i", $KeyPath)
}

$remoteEnv = @"
NODE_CODE=$NodeCode
WORKSHOP_TYPE=$WorkshopType
CENTRAL_API_URL=$CentralApiUrl
COLLECT_INTERVAL_SECONDS=5
LOCAL_DB_PATH=/var/lib/mini-ogas/node.db
SCRIPT_DIR=/opt/mini-ogas/scripts
"@

ssh @sshArgs $sshTarget "rm -rf $remoteDir && mkdir -p $remoteDir"
scp @sshArgs $archive "${sshTarget}:$remoteDir/mini-ogas-cloud-node.tar.gz"
ssh @sshArgs $sshTarget "cd $remoteDir && tar -xzf mini-ogas-cloud-node.tar.gz && cat > node-agent.env.example <<'EOF'
$remoteEnv
EOF
chmod +x install-node-agent.sh && sudo ./install-node-agent.sh && sudo systemctl status mini-ogas-node-agent --no-pager"

Write-Host "Cloud node deployed to $sshTarget"
