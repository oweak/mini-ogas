import { computed, ref, type Ref } from 'vue'
import { demoScenario } from './data'
import type { SoundKind } from './soundPolicy'

export type DemoMode = 'normal' | 'emergency'

export type EmergencyGuideStage = {
  title: string
  goal: string
  options: string[]
}

type EmergencyDemoWorkflowOptions = {
  runtimeTick: Ref<number>
  liveLogs: Ref<string[]>
  currentTime: () => string
  playSound: (kind: SoundKind) => void
  loadDashboardState: () => Promise<void>
  recoveryDelayMs?: number
}

export const emergencyGuideStages: EmergencyGuideStage[] = [
  {
    title: '确认报警',
    goal: '判断是否进入高等级处置流程。',
    options: ['确认 ALM-0042 高等级报警', '标记为观察并继续采样', '请求车间主管复核']
  },
  {
    title: '控制风险',
    goal: '防止故障设备继续影响生产与数据同步。',
    options: [
      '派遣维修工人到 MILL-02 现场',
      '执行停机并挂牌锁定',
      '保留心跳并限制生产数据写入',
      '执行冷却回路本地检查'
    ]
  },
  {
    title: '重排生产',
    goal: '把受影响工单转移到可用设备。',
    options: [
      '将剩余数量重排到 MILL-01',
      '为 MILL-02 创建主轴与轴承检查工单',
      '降低 GRIND-01 后续进给速度',
      '通知计划节点重新计算产能'
    ]
  },
  {
    title: '恢复与上报',
    goal: '恢复正常运行，并把全过程提交到审计日志。',
    options: ['确认温度回落并解除故障状态', '生成处置报告', '写入审计日志并恢复正常运行']
  }
]

export function useEmergencyDemoWorkflow(options: EmergencyDemoWorkflowOptions) {
  const demoMode = ref<DemoMode>('normal')
  const aiGuideVisible = ref(true)
  const emergencyStep = ref(0)
  const handledActions = ref<string[]>([])
  const dismissedIssues = ref<string[]>([])
  let emergencyTimer: ReturnType<typeof globalThis.setTimeout> | undefined

  const activeDemo = computed(() => demoScenario[demoMode.value])
  const liveOutput = computed(() => (demoMode.value === 'normal' ? 74 + (options.runtimeTick.value % 18) : 39))
  const liveTemp = computed(() =>
    demoMode.value === 'normal' ? 66 + (options.runtimeTick.value % 5) : Math.max(72, 89 - emergencyStep.value * 5)
  )
  const liveWear = computed(() =>
    demoMode.value === 'normal' ? 58 + (options.runtimeTick.value % 3) : Math.max(60, 76 - emergencyStep.value * 4)
  )
  const pendingRecords = computed(() =>
    demoMode.value === 'normal' ? 0 : Math.max(0, 6 - emergencyStep.value * 2)
  )
  const heartbeatStatus = computed(() => {
    if (demoMode.value === 'normal') return 'running'
    return emergencyStep.value >= emergencyGuideStages.length ? 'recovering' : 'fault'
  })

  function clearEmergencyTimer() {
    if (!emergencyTimer) return
    globalThis.clearTimeout(emergencyTimer)
    emergencyTimer = undefined
  }

  function setDemoMode(mode: DemoMode) {
    clearEmergencyTimer()
    demoMode.value = mode
    dismissedIssues.value = []
    if (mode === 'emergency') {
      options.playSound('critical')
      aiGuideVisible.value = true
      emergencyStep.value = 0
      handledActions.value = []
      options.liveLogs.value.unshift(`${options.currentTime()} 触发 SPINDLE_TEMP_HIGH，AI 应急引导已打开`)
    } else {
      emergencyStep.value = 0
      handledActions.value = []
      aiGuideVisible.value = false
      options.playSound('success')
    }
    void options.loadDashboardState()
  }

  function selectTreatment(option: string) {
    handledActions.value.push(option)
    options.liveLogs.value.unshift(`${options.currentTime()} 已执行：${option}`)
    options.playSound('notice')
  }

  function advanceEmergencyStep() {
    if (handledActions.value.length === 0) {
      options.liveLogs.value.unshift(`${options.currentTime()} 等待选择处置动作，流程未推进`)
      options.playSound('error')
      return
    }

    emergencyStep.value = Math.min(emergencyStep.value + 1, emergencyGuideStages.length)
    handledActions.value = []
    options.playSound('step')

    if (emergencyStep.value >= emergencyGuideStages.length) {
      options.liveLogs.value.unshift(`${options.currentTime()} 处置完成：节点恢复正常，报告已提交到审计日志`)
      options.playSound('success')
      emergencyTimer = globalThis.setTimeout(() => {
        demoMode.value = 'normal'
        aiGuideVisible.value = false
        emergencyStep.value = 0
        dismissedIssues.value = []
        options.liveLogs.value.unshift(`${options.currentTime()} 系统恢复正常运行，MILL-02 重新纳入调度`)
        options.playSound('success')
      }, options.recoveryDelayMs ?? 900)
    }
  }

  return {
    demoMode,
    aiGuideVisible,
    emergencyStep,
    handledActions,
    dismissedIssues,
    demoScenario,
    emergencyGuideStages,
    activeDemo,
    liveOutput,
    liveTemp,
    liveWear,
    pendingRecords,
    heartbeatStatus,
    setDemoMode,
    selectTreatment,
    advanceEmergencyStep,
    clearEmergencyTimer
  }
}
