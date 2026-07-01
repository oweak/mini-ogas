import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { useProtectedPolling } from './protectedPolling'

describe('useProtectedPolling', () => {
  it('does not refresh protected data while the system is locked', async () => {
    const systemUnlocked = ref(false)
    const runtimeTick = ref(0)
    const loadDashboardState = vi.fn()
    const fetchAlarmData = vi.fn()
    const fetchAuditEvents = vi.fn()

    const polling = useProtectedPolling({
      systemUnlocked,
      runtimeTick,
      loadDashboardState,
      fetchAlarmData,
      fetchAuditEvents,
      appendHeartbeatLog: vi.fn(),
    })

    await polling.refreshProtectedData()

    expect(loadDashboardState).not.toHaveBeenCalled()
    expect(fetchAlarmData).not.toHaveBeenCalled()
    expect(fetchAuditEvents).not.toHaveBeenCalled()
  })

  it('refreshes protected data after the system is unlocked', async () => {
    const systemUnlocked = ref(true)
    const runtimeTick = ref(0)
    const loadDashboardState = vi.fn()
    const fetchAlarmData = vi.fn()
    const fetchAuditEvents = vi.fn()

    const polling = useProtectedPolling({
      systemUnlocked,
      runtimeTick,
      loadDashboardState,
      fetchAlarmData,
      fetchAuditEvents,
      appendHeartbeatLog: vi.fn(),
    })

    await polling.refreshProtectedData()

    expect(loadDashboardState).toHaveBeenCalledOnce()
    expect(fetchAlarmData).toHaveBeenCalledOnce()
    expect(fetchAuditEvents).toHaveBeenCalledOnce()
  })

  it('starts polling only once and stops cleanly', () => {
    vi.useFakeTimers()
    const systemUnlocked = ref(true)
    const runtimeTick = ref(0)
    const loadDashboardState = vi.fn()
    const fetchAlarmData = vi.fn()
    const fetchAuditEvents = vi.fn()
    const appendHeartbeatLog = vi.fn()
    const polling = useProtectedPolling({
      systemUnlocked,
      runtimeTick,
      loadDashboardState,
      fetchAlarmData,
      fetchAuditEvents,
      appendHeartbeatLog,
      setIntervalFn: setInterval,
      clearIntervalFn: clearInterval,
    })

    polling.startRuntimePolling()
    polling.startRuntimePolling()
    vi.advanceTimersByTime(5000)
    polling.stopRuntimePolling()
    vi.advanceTimersByTime(5000)
    vi.useRealTimers()

    expect(runtimeTick.value).toBe(5)
    expect(loadDashboardState).toHaveBeenCalledTimes(5)
    expect(fetchAlarmData).not.toHaveBeenCalled()
    expect(fetchAuditEvents).not.toHaveBeenCalled()
    expect(appendHeartbeatLog).toHaveBeenCalledOnce()
  })
})
