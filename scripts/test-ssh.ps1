param([string]$HostIP = "192.168.1.5")

Write-Host "Testing SSH to $HostIP..."
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $result = $tcp.BeginConnect($HostIP, 22, $null, $null)
    if ($result.AsyncWaitHandle.WaitOne(3000)) {
        Write-Host "SSH on $HostIP` port 22: OPEN"
        $tcp.EndConnect($result)
    } else {
        Write-Host "SSH on $HostIP` port 22: CLOSED / TIMEOUT"
    }
    $tcp.Close()
} catch {
    Write-Host "SSH: FAILED - $_"
}
