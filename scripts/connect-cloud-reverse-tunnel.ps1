param(
    [string]$ServerIp = "82.156.217.166",
    [string]$User = "ubuntu",
    [string]$KeyPath = "",
    [int]$LocalCentralApiPort = 8080,
    [int]$RemoteForwardPort = 18080
)

$ErrorActionPreference = "Stop"

$sshTarget = "$User@$ServerIp"
$sshArgs = @("-N", "-R", "127.0.0.1:${RemoteForwardPort}:127.0.0.1:${LocalCentralApiPort}")
if ($KeyPath -ne "") {
    $sshArgs = @("-i", $KeyPath) + $sshArgs
}

Write-Host "Opening reverse tunnel:"
Write-Host "  cloud 127.0.0.1:$RemoteForwardPort -> local 127.0.0.1:$LocalCentralApiPort"
Write-Host "Keep this terminal open while the cloud node should report to the laptop."
ssh @sshArgs $sshTarget
