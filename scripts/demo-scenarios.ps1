$ErrorActionPreference = "Stop"

param(
    [ValidateSet("normal", "common_fault", "complex_fault", "hostile_attack", "market_shift")]
    [string]$Scenario = "normal"
)

$Body = @{ scenario = $Scenario } | ConvertTo-Json
Invoke-RestMethod `
    -Uri "http://127.0.0.1:8080/demo/scenario" `
    -Method Post `
    -ContentType "application/json" `
    -Body $Body

