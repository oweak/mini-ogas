param(
    [string]$ServiceName = "mini-ogas-simulator"
)

[ordered]@{
    success = $true
    action = "restart_simulator"
    service = $ServiceName
    message = "restart command simulated for safe demo"
} | ConvertTo-Json -Compress

