import { computed, ref, type Ref } from 'vue'
import { apiFetch } from './apiClient'
import type { AiSmokeState, AuthRuntime, PreflightCheck, PreflightState } from './types'
import type { SoundKind } from './soundPolicy'

type GatePhase = 'preflight' | 'login'

type StartupWorkflowOptions = {
  apiAvailable: Ref<boolean>
  liveLogs: Ref<string[]>
  soundArmed: Ref<boolean>
  currentTime: () => string
  playSound: (kind: SoundKind) => void
  ensureAudioContext: () => AudioContext | null
  loadDashboardState: () => Promise<void>
  preflightDurationMs?: number
  preflightStepMs?: number
  loginTransitionMs?: number
}

type LoginResponse = {
  ok?: boolean
  error?: string
  access_token?: string
  runtime?: AuthRuntime
  preflight?: PreflightState
  ai_smoke?: AiSmokeState
}

const fallbackAiRuntime: AuthRuntime = {
  status: 'not_configured',
  provider: '',
  model: '',
  source: 'rule_fallback',
  vault_present: false,
  vault_unlocked: false
}

function wait(ms: number) {
  return new Promise((resolve) => globalThis.setTimeout(resolve, ms))
}

function startupFallbackChecks(preflightLoading: boolean): PreflightCheck[] {
  return [
    { id: 'central-api', label: '父节点 central-api', status: preflightLoading ? 'checking' : 'waiting', detail: '等待连接主控 API。' },
    { id: 'edge-nodes', label: '父子节点连接', status: preflightLoading ? 'checking' : 'waiting', detail: '等待检查车间子节点心跳。' },
    { id: 'ai-runtime', label: 'AI 运行环境', status: 'locked', detail: '等待管理员密码解锁并调用模型接口。' },
    { id: 'rules', label: '系统自检', status: preflightLoading ? 'checking' : 'waiting', detail: '等待检查规则引擎、调度和日志模块。' }
  ]
}

function failedPreflight(authRuntime: AuthRuntime | null): PreflightState {
  return {
    ok: false,
    status: 'error',
    checks: [
      { id: 'central-api', label: '父节点 central-api', status: 'error', detail: '无法连接 central-api，请先启动后端服务。' },
      { id: 'edge-nodes', label: '父子节点连接', status: 'waiting', detail: '父节点不可用，暂未检查子节点。' },
      { id: 'ai-runtime', label: 'AI 运行环境', status: 'waiting', detail: '父节点不可用，暂未解锁 AI。' },
      { id: 'rules', label: '系统自检', status: 'waiting', detail: '父节点不可用，暂未执行自检。' }
    ],
    nodes: [],
    ai_runtime: authRuntime ?? fallbackAiRuntime
  }
}

function safeStoreToken(token?: string) {
  if (!token) return
  try {
    window.localStorage.setItem('miniogas_access_token', token)
  } catch {
    // Local storage can be unavailable in privacy modes; the current session can continue with in-memory auth state.
  }
}

export function useStartupWorkflow(options: StartupWorkflowOptions) {
  const loginOperator = ref('车间主管')
  const loginPassword = ref('')
  const loginFeedback = ref('')
  const loginLoading = ref(false)
  const systemUnlocked = ref(false)
  const gatePhase = ref<GatePhase>('preflight')
  const authRuntime = ref<AuthRuntime | null>(null)
  const preflightLoading = ref(false)
  const preflightStep = ref(0)
  const preflight = ref<PreflightState | null>(null)
  const aiSmoke = ref<AiSmokeState | null>(null)
  let preflightTimer: ReturnType<typeof globalThis.setInterval> | undefined

  const loginRequired = computed(() => !systemUnlocked.value)
  const startupChecks = computed<PreflightCheck[]>(() => {
    const checks = preflight.value?.checks ?? startupFallbackChecks(preflightLoading.value)
    if (aiSmoke.value) {
      return checks.map((item) => item.id === 'ai-runtime'
        ? {
            ...item,
            status: aiSmoke.value?.ok ? 'ok' : 'warning',
            detail: aiSmoke.value?.ok
              ? `${aiSmoke.value.provider} / ${aiSmoke.value.model} 已完成启动调用。`
              : `AI 已尝试调用，当前为 ${aiSmoke.value?.source}/${aiSmoke.value?.status}，系统将保留规则回退。`
          }
        : item)
    }
    return checks
  })

  const animatedStartupChecks = computed(() =>
    startupChecks.value.map((check, index) => {
      if (!preflightLoading.value) return { ...check, visualStatus: check.status }
      if (index < preflightStep.value) return { ...check, visualStatus: check.status === 'waiting' ? 'ok' : check.status }
      if (index === preflightStep.value) return { ...check, visualStatus: 'checking' }
      return { ...check, visualStatus: 'waiting' }
    })
  )

  const bootProgress = computed(() => {
    const total = Math.max(1, startupChecks.value.length)
    return Math.round((Math.min(preflightStep.value, total) / total) * 100)
  })

  const aiRuntimeLabel = computed(() => {
    if (!authRuntime.value) return '连接 central-api 后显示'
    if (authRuntime.value.vault_unlocked && aiSmoke.value?.ok) {
      return `${authRuntime.value.provider} / ${authRuntime.value.model} 真实 API 已验证`
    }
    if (authRuntime.value.vault_unlocked && aiSmoke.value && !aiSmoke.value.ok) {
      return `${authRuntime.value.provider} / ${authRuntime.value.model} 调用未通过，规则回退`
    }
    if (authRuntime.value.vault_unlocked) return `${authRuntime.value.provider} / ${authRuntime.value.model} 已解锁，待调用验证`
    if (authRuntime.value.vault_present) return '密钥库已加载，等待管理员验证'
    return '未发现密钥库，使用规则回退'
  })

  const aiSmokeTruth = computed(() => {
    if (!aiSmoke.value) {
      return {
        status: authRuntime.value?.vault_unlocked ? '待验证' : '未解锁',
        detail: authRuntime.value?.vault_unlocked
          ? '管理员已解锁密钥库，但尚未记录启动烟测结果。'
          : '登录前不会调用外部模型；当前仅允许规则回退。',
        source: authRuntime.value?.source ?? 'rule_fallback',
        isLiveApi: false
      }
    }
    const isLiveApi = aiSmoke.value.ok && aiSmoke.value.source === 'api'
    return {
      status: isLiveApi ? '真实 API 已验证' : '规则回退/烟测未通过',
      detail: isLiveApi
        ? `${aiSmoke.value.provider} / ${aiSmoke.value.model} 启动烟测成功，诊断可使用真实模型。`
        : `${aiSmoke.value.provider || 'unknown'} / ${aiSmoke.value.model || 'unknown'}：${aiSmoke.value.error || aiSmoke.value.status || '未确认真实模型调用'}，系统会明确标记规则回退。`,
      source: aiSmoke.value.source,
      isLiveApi
    }
  })

  function clearPreflightTimer() {
    if (!preflightTimer) return
    globalThis.clearInterval(preflightTimer)
    preflightTimer = undefined
  }

  async function fetchAuthStatus() {
    try {
      const res = await apiFetch('/api/auth/status')
      if (!res.ok) throw new Error('auth status unavailable')
      const data = await res.json()
      authRuntime.value = data.runtime
      options.apiAvailable.value = true
    } catch {
      authRuntime.value = null
      options.apiAvailable.value = false
    }
  }

  async function runPreflight() {
    gatePhase.value = 'preflight'
    preflightLoading.value = true
    preflightStep.value = 0
    clearPreflightTimer()
    preflightTimer = globalThis.setInterval(() => {
      preflightStep.value = Math.min(preflightStep.value + 1, Math.max(1, startupChecks.value.length - 1))
    }, options.preflightStepMs ?? 420)
    try {
      const [res] = await Promise.all([
        apiFetch('/api/system/preflight'),
        wait(options.preflightDurationMs ?? 4200)
      ])
      if (!res.ok) throw new Error('preflight unavailable')
      const data = await res.json()
      preflight.value = data
      authRuntime.value = data.ai_runtime
      options.apiAvailable.value = true
    } catch {
      preflight.value = failedPreflight(authRuntime.value)
      options.apiAvailable.value = false
    } finally {
      clearPreflightTimer()
      preflightStep.value = startupChecks.value.length
      preflightLoading.value = false
      globalThis.setTimeout(() => {
        if (!systemUnlocked.value) gatePhase.value = 'login'
      }, options.loginTransitionMs ?? 520)
    }
  }

  async function loginAdmin() {
    loginLoading.value = true
    loginFeedback.value = ''
    try {
      const res = await apiFetch('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ operator: loginOperator.value || '车间主管', password: loginPassword.value })
      })
      const data = await res.json() as LoginResponse
      authRuntime.value = data.runtime ?? authRuntime.value
      preflight.value = data.preflight ?? preflight.value
      aiSmoke.value = data.ai_smoke ?? null
      if (!res.ok || !data.ok) {
        loginFeedback.value = data.error ?? '管理员验证失败'
        options.playSound('error')
        return
      }
      safeStoreToken(data.access_token)
      loginPassword.value = ''
      systemUnlocked.value = true
      options.soundArmed.value = true
      options.ensureAudioContext()
      loginFeedback.value = data.ai_smoke?.ok
        ? '管理员验证通过，父子节点、AI 接口与系统自检已完成。'
        : '管理员验证通过；AI 实时调用未确认成功，系统将使用规则回退并保留日志。'
      const aiStatusLog = data.ai_smoke?.ok
        ? `AI 接口已验证：${data.runtime?.provider ?? 'model'} / ${data.runtime?.model ?? 'unknown'}`
        : `AI 实时调用未验证：${data.runtime?.status ?? 'unknown'} / 使用规则回退`
      options.liveLogs.value.unshift(`${options.currentTime()} 管理员验证通过：${loginOperator.value || '车间主管'} / ${aiStatusLog}`)
      options.playSound('success')
      await options.loadDashboardState()
    } catch {
      loginFeedback.value = '无法连接 central-api，请先启动后端服务。'
      options.playSound('error')
    } finally {
      loginLoading.value = false
    }
  }

  function lockSystem(message = '登录已过期，请重新验证管理员密码。') {
    systemUnlocked.value = false
    gatePhase.value = 'login'
    loginPassword.value = ''
    loginFeedback.value = message
  }

  return {
    loginOperator,
    loginPassword,
    loginFeedback,
    loginLoading,
    systemUnlocked,
    gatePhase,
    authRuntime,
    preflightLoading,
    preflightStep,
    preflight,
    aiSmoke,
    loginRequired,
    startupChecks,
    animatedStartupChecks,
    bootProgress,
    aiRuntimeLabel,
    aiSmokeTruth,
    fetchAuthStatus,
    runPreflight,
    loginAdmin,
    lockSystem,
    clearPreflightTimer
  }
}
