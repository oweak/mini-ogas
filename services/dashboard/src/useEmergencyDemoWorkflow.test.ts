import { ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { emergencyGuideStages, useEmergencyDemoWorkflow } from './useEmergencyDemoWorkflow'

function createWorkflow() {
  const liveLogs = ref<string[]>([])
  const playSound = vi.fn()
  const loadDashboardState = vi.fn(async () => {})
  const workflow = useEmergencyDemoWorkflow({
    runtimeTick: ref(4),
    liveLogs,
    currentTime: () => '10:30:00',
    playSound,
    loadDashboardState,
    recoveryDelayMs: 25
  })
  return { workflow, liveLogs, playSound, loadDashboardState }
}

describe('useEmergencyDemoWorkflow', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('enters emergency mode and opens the AI guide', () => {
    const { workflow, liveLogs, playSound, loadDashboardState } = createWorkflow()

    workflow.setDemoMode('emergency')

    expect(workflow.demoMode.value).toBe('emergency')
    expect(workflow.aiGuideVisible.value).toBe(true)
    expect(workflow.emergencyStep.value).toBe(0)
    expect(workflow.handledActions.value).toEqual([])
    expect(liveLogs.value[0]).toContain('AI 应急引导已打开')
    expect(playSound).toHaveBeenCalledWith('critical')
    expect(loadDashboardState).toHaveBeenCalled()
  })

  it('requires an operator action before advancing emergency stages', () => {
    const { workflow, liveLogs, playSound } = createWorkflow()
    workflow.setDemoMode('emergency')

    workflow.advanceEmergencyStep()

    expect(workflow.emergencyStep.value).toBe(0)
    expect(liveLogs.value[0]).toContain('等待选择处置动作')
    expect(playSound).toHaveBeenCalledWith('error')
  })

  it('advances through all stages and automatically restores normal mode', () => {
    const { workflow, liveLogs, playSound } = createWorkflow()
    workflow.setDemoMode('emergency')

    for (const stage of emergencyGuideStages) {
      workflow.selectTreatment(stage.options[0])
      workflow.advanceEmergencyStep()
    }

    expect(workflow.emergencyStep.value).toBe(emergencyGuideStages.length)
    expect(liveLogs.value[0]).toContain('处置完成')
    expect(playSound).toHaveBeenCalledWith('success')

    vi.advanceTimersByTime(25)

    expect(workflow.demoMode.value).toBe('normal')
    expect(workflow.aiGuideVisible.value).toBe(false)
    expect(workflow.emergencyStep.value).toBe(0)
    expect(liveLogs.value[0]).toContain('系统恢复正常运行')
  })
})
