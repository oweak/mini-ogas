Write-Host "=== Scanning Host-Only (192.168.56.x) ==="
for ($i = 100; $i -le 115; $i++) {
    $ip = "192.168.56.$i"
    $result = ping -n 1 -w 500 $ip 2>&1 | Out-String
    if ($result -match "TTL=") {
        Write-Host "ALIVE: $ip"
    }
}

Write-Host "=== Scanning Bridged (192.168.1.x) ==="
for ($i = 2; $i -le 20; $i++) {
    $ip = "192.168.1.$i"
    $result = ping -n 1 -w 500 $ip 2>&1 | Out-String
    if ($result -match "TTL=") {
        Write-Host "ALIVE: $ip"
    }
}
