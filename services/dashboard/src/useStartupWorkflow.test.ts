import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { apiFetch } from './apiClient'
import { useStartupWorkflow } from './useStartupWorkflow'

vi.mock('./apiClient', () => ({
  apiFetch: vi.fn()
}))

const apiFetchMock = vi.mocked(apiFetch)

function jsonResponse(body: unknown, ok = true) {
  return new Response(JSON.stringify(body), {
    status: ok ? 200 : 400,
    headers: { 'Content-Type': 'application/json' }
  })
}

function createWorkflow() {
  const apiAvailable = ref(false)
  const liveLogs = ref<string[]>([])
  const soundArmed = ref(false)
  const playSound = vi.fn()
  const ensureAudioContext = vi.fn(() => null)
  const loadDashboardState = vi.fn(async () => {})
  const workflow = useStartupWorkflow({
    apiAvailable,
    liveLogs,
    soundArmed,
    currentTime: () => '10:30:00',
    playSound,
    ensureAudioContext,
    loadDashboardState,
    preflightDurationMs: 0,
    preflightStepMs: 5,
    loginTransitionMs: 0
  })
  return {
    workflow,
    apiAvailable,
    liveLogs,
    soundArmed,
    playSound,
    ensureAudioContext,
    loadDashboardState
  }
}

describe('useStartupWorkflow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads preflight checks and marks the API available', async () => {
    const preflight = {
      ok: true,
      status: 'ok',
      checks: [
        { id: 'central-api', label: '父节点 central-api', status: 'ok', detail: 'ready' },
        { id: 'ai-runtime', label: 'AI 运行环境', status: 'locked', detail: 'vault loaded' }
      ],
      nodes: [],
      ai_runtime: {
        status: 'locked',
        provider: 'deepseek',
        model: 'deepseek-v4-pro',
        source: 'api',
        vault_present: true,
        vault_unlocked: false
      }
    }
    apiFetchMock.mockResolvedValue(jsonResponse(preflight))
    const { workflow, apiAvailable } = createWorkflow()

    await workflow.runPreflight()
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(apiFetchMock).toHaveBeenCalledWith('/api/system/preflight')
    expect(workflow.preflight.value).toEqual(preflight)
    expect(workflow.authRuntime.value?.provider).toBe('deepseek')
    expect(apiAvailable.value).toBe(true)
    expect(workflow.gatePhase.value).toBe('login')
  })

  it('unlocks the system and records live AI smoke proof after login', async () => {
    apiFetchMock.mockResolvedValue(jsonResponse({
      ok: true,
      access_token: 'runtime-token',
      runtime: {
        status: 'connected',
        provider: 'deepseek',
        model: 'deepseek-v4-pro',
        source: 'api',
        vault_present: true,
        vault_unlocked: true
      },
      ai_smoke: {
        ok: true,
        source: 'api',
        status: 'connected',
        provider: 'deepseek',
        model: 'deepseek-v4-pro'
      }
    }))
    const { workflow, liveLogs, soundArmed, playSound, ensureAudioContext, loadDashboardState } = createWorkflow()
    workflow.loginPassword.value = 'miniogas'

    await workflow.loginAdmin()

    expect(apiFetchMock).toHaveBeenCalledWith('/api/auth/login', expect.objectContaining({ method: 'POST' }))
    expect(workflow.systemUnlocked.value).toBe(true)
    expect(soundArmed.value).toBe(true)
    expect(workflow.loginPassword.value).toBe('')
    expect(workflow.aiSmokeTruth.value.isLiveApi).toBe(true)
    expect(workflow.aiRuntimeLabel.value).toBe('deepseek / deepseek-v4-pro 真实 API 已验证')
    expect(liveLogs.value[0]).toContain('AI 接口已验证')
    expect(playSound).toHaveBeenCalledWith('success')
    expect(ensureAudioContext).toHaveBeenCalled()
    expect(loadDashboardState).toHaveBeenCalled()
  })

  it('keeps unlocked AI visibly marked as fallback when smoke proof fails', async () => {
    apiFetchMock.mockResolvedValue(jsonResponse({
      ok: true,
      access_token: 'runtime-token',
      runtime: {
        status: 'connected',
        provider: 'deepseek',
        model: 'deepseek-v4-pro',
        source: 'api',
        vault_present: true,
        vault_unlocked: true
      },
      ai_smoke: {
        ok: false,
        source: 'rule_fallback',
        status: 'api_error',
        provider: 'deepseek',
        model: 'deepseek-v4-pro',
        error: 'timeout'
      }
    }))
    const { workflow, liveLogs } = createWorkflow()
    workflow.loginPassword.value = 'miniogas'

    await workflow.loginAdmin()

    expect(workflow.systemUnlocked.value).toBe(true)
    expect(workflow.aiSmokeTruth.value.isLiveApi).toBe(false)
    expect(workflow.aiRuntimeLabel.value).toBe('deepseek / deepseek-v4-pro 调用未通过，规则回退')
    expect(workflow.loginFeedback.value).toContain('AI 实时调用未确认成功')
    expect(liveLogs.value[0]).toContain('AI 实时调用未验证')
  })

  it('keeps the system locked when administrator verification fails', async () => {
    apiFetchMock.mockResolvedValue(jsonResponse({ ok: false, error: '密码不正确' }, false))
    const { workflow, playSound } = createWorkflow()
    workflow.loginPassword.value = 'bad-password'

    await workflow.loginAdmin()

    expect(workflow.systemUnlocked.value).toBe(false)
    expect(workflow.loginFeedback.value).toBe('密码不正确')
    expect(playSound).toHaveBeenCalledWith('error')
  })
})
