param(
  [string]$SupervisorUrl = "http://127.0.0.1:9099",
  [string]$CentralApiUrl = "http://127.0.0.1:8080",
  [string]$WorkerUrl = "http://127.0.0.1:8084",
  [int]$OutageSeconds = 18,
  [int]$RecoveryTimeoutSeconds = 90,
  [int]$ThresholdTimeoutSeconds = 300
)

$ErrorActionPreference = "Stop"

function Get-WorkerHealth {
  Invoke-RestMethod -Uri "$WorkerUrl/health" -TimeoutSec 5
}

function Get-CentralHealth {
  Invoke-RestMethod -Uri "$CentralApiUrl/health" -TimeoutSec 5
}

function Get-ProcessState {
  param([string]$Name)
  $status = Invoke-RestMethod -Uri "$SupervisorUrl/supervisor/status" -TimeoutSec 5
  return @($status.processes | Where-Object name -eq $Name | Select-Object -First 1)
}

function Wait-Until {
  param(
    [scriptblock]$Condition,
    [int]$TimeoutSeconds,
    [string]$FailureMessage
  )
  $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
  do {
    if (& $Condition) { return }
    Start-Sleep -Milliseconds 500
  } while ([DateTimeOffset]::UtcNow -lt $deadline)
  throw $FailureMessage
}

if ($OutageSeconds -lt 16) {
  throw "OutageSeconds must be at least 16 so the 15-second reconciliation grace expires."
}

$baseline = Get-WorkerHealth
if ($baseline.nats.status -ne "live") {
  throw "NATS must be live before the recovery gate starts."
}
$baselineMatched = [int]$baseline.nats.reconciliation.counts.matched_receipts
$baselinePublished = [int]$baseline.nats.publisher.published_count
$stopped = $false

try {
  Invoke-RestMethod -Method Post -Uri "$SupervisorUrl/supervisor/stop/nats-server" -TimeoutSec 5 | Out-Null
  $stopped = $true
  Wait-Until -TimeoutSeconds 15 -FailureMessage "NATS did not enter stopped/degraded state." -Condition {
    $process = Get-ProcessState "nats-server"
    $worker = Get-WorkerHealth
    $process.state -eq "stopped" -and $worker.nats.status -eq "degraded"
  }

  Start-Sleep -Seconds $OutageSeconds
  $duringCentral = Get-CentralHealth
  $duringWorker = Get-WorkerHealth
  $duringCounts = $duringWorker.nats.reconciliation.counts
  if ($duringCentral.status -ne "ok" -or $duringCentral.overall_status -ne "degraded") {
    throw "Central did not preserve liveness with explicit degraded readiness."
  }
  if ($duringWorker.nats.reconciliation.status -ne "degraded") {
    throw "Shadow reconciliation did not degrade after the grace period."
  }
  if ([int]$duringCounts.stale_pending -lt 1) {
    throw "No durable stale Outbox backlog was observed during the NATS outage."
  }

  Invoke-RestMethod -Method Post -Uri "$SupervisorUrl/supervisor/start/nats-server" -TimeoutSec 5 | Out-Null
  $stopped = $false
  Wait-Until -TimeoutSeconds $RecoveryTimeoutSeconds -FailureMessage "NATS did not recover and reconcile." -Condition {
    $process = Get-ProcessState "nats-server"
    $worker = Get-WorkerHealth
    $reconciliation = $worker.nats.reconciliation
    $counts = $reconciliation.counts
    $process.state -eq "healthy" -and
      $worker.nats.status -eq "live" -and
      [int]$counts.fresh_pending -eq 0 -and
      [int]$counts.stale_pending -eq 0 -and
      [int]$counts.fresh_unmatched -eq 0 -and
      [int]$counts.stale_unmatched -eq 0
  }

  Wait-Until -TimeoutSeconds $ThresholdTimeoutSeconds -FailureMessage "NATS steady-state thresholds did not converge." -Condition {
    $worker = Get-WorkerHealth
    $worker.nats.status -eq "live" -and
      $worker.nats.reconciliation.status -eq "ready" -and
      [bool]$worker.nats.reconciliation.thresholds_met
  }

  $recoveredCentral = Get-CentralHealth
  $recoveredWorker = Get-WorkerHealth
  $recovered = $recoveredWorker.nats.reconciliation
  if ($recoveredCentral.overall_status -ne "ready") {
    throw "Central readiness did not recover."
  }
  if ([int]$recoveredWorker.nats.publisher.published_count -le $baselinePublished) {
    throw "Publisher count did not advance across the outage."
  }
  if ([double]$recovered.rates.receive_rate -ne 1.0) {
    throw "Recovered receive rate is not 100 percent."
  }
  if ([int]$recovered.ordering.divergences -ne 0) {
    throw "Recovered stream contains an order divergence."
  }

  [ordered]@{
    status = "PASS"
    baseline_matched = $baselineMatched
    baseline_published = $baselinePublished
    outage_stale_pending = [int]$duringCounts.stale_pending
    recovered_matched = [int]$recovered.counts.matched_receipts
    recovered_published = [int]$recoveredWorker.nats.publisher.published_count
    receive_rate = [double]$recovered.rates.receive_rate
    duplicate_rate = [double]$recovered.rates.duplicate_rate
    p95_latency_ms = [double]$recovered.latency_ms.p95
    order_divergences = [int]$recovered.ordering.divergences
    central_liveness_during_outage = $duringCentral.status
    central_readiness_during_outage = $duringCentral.overall_status
    central_readiness_after_recovery = $recoveredCentral.overall_status
  } | ConvertTo-Json
} finally {
  if ($stopped) {
    try {
      Invoke-RestMethod -Method Post -Uri "$SupervisorUrl/supervisor/start/nats-server" -TimeoutSec 5 | Out-Null
    } catch {
      Write-Warning "Failed to restore nats-server automatically: $($_.Exception.Message)"
    }
  }
}
