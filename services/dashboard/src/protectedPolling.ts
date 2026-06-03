import type { Ref } from 'vue'

export type ProtectedPollingOptions = {
  systemUnlocked: Ref<boolean>
  runtimeTick: Ref<number>
  loadDashboardState: () => Promise<void> | void
  fetchAlarmData: () => Promise<void> | void
  fetchAuditEvents: () => Promise<void> | void
  appendHeartbeatLog: () => void
  setIntervalFn?: typeof window.setInterval
  clearIntervalFn?: typeof window.clearInterval
}

export function useProtectedPolling(options: ProtectedPollingOptions) {
  let runtimeTimer: number | undefined

  function defaultSetInterval() {
    return options.setIntervalFn ?? window.setInterval.bind(window)
  }

  function defaultClearInterval() {
    return options.clearIntervalFn ?? window.clearInterval.bind(window)
  }

  async function refreshProtectedData() {
    if (!options.systemUnlocked.value) return
    await options.loadDashboardState()
    await options.fetchAlarmData()
    await options.fetchAuditEvents()
  }

  function stopRuntimePolling() {
    if (runtimeTimer) {
      defaultClearInterval()(runtimeTimer)
      runtimeTimer = undefined
    }
  }

  function startRuntimePolling() {
    if (runtimeTimer) return
    runtimeTimer = defaultSetInterval()(() => {
      options.runtimeTick.value += 1
      if (options.systemUnlocked.value) {
        void options.loadDashboardState()
        if (options.runtimeTick.value % 10 === 0) {
          void options.fetchAlarmData()
          void options.fetchAuditEvents()
        }
      }
      if (options.runtimeTick.value % 5 === 0) {
        options.appendHeartbeatLog()
      }
    }, 1000)
  }

  return {
    refreshProtectedData,
    startRuntimePolling,
    stopRuntimePolling,
  }
}
