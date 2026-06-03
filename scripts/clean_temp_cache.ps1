param(
    [string]$TargetPath = "$env:TEMP"
)

$result = [ordered]@{
    success = $true
    action = "clean_temp_cache"
    target = $TargetPath
    message = "scan completed"
}

try {
    if (Test-Path $TargetPath) {
        $result.message = "temporary cache path exists; cleanup can be enabled for demo"
    } else {
        $result.success = $false
        $result.message = "target path not found"
    }
} catch {
    $result.success = $false
    $result.message = $_.Exception.Message
}

$result | ConvertTo-Json -Compress

