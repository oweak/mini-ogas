<script setup lang="ts">
type StartupCheck = {
  id: string
  label: string
  status: string
  detail: string
  visualStatus?: string
}

type PreflightState = {
  nodes?: unknown[]
}

defineProps<{
  gatePhase: 'preflight' | 'login'
  checks: StartupCheck[]
  startupChecks: StartupCheck[]
  bootProgress: number
  preflightLoading: boolean
  preflight: PreflightState | null
  loginOperator: string
  loginPassword: string
  loginFeedback: string
  loginLoading: boolean
}>()

const emit = defineEmits<{
  'update:loginOperator': [value: string]
  'update:loginPassword': [value: string]
  'run-preflight': []
  login: []
}>()

function checkCode(status?: string) {
  if (status === 'ok') return 'OK'
  if (status === 'warning') return 'WARN'
  if (status === 'error') return 'FAIL'
  if (status === 'locked') return 'LOCK'
  if (status === 'checking') return 'SCAN'
  return 'WAIT'
}

function checkLabel(status: string) {
  if (status === 'ok') return '通过'
  if (status === 'locked') return '等待解锁'
  return status
}
</script>

<template>
  <section class="login-overlay" aria-label="管理员验证">
    <div v-if="gatePhase === 'preflight'" class="boot-card" aria-label="系统启动自检">
      <div class="boot-header">
        <span class="brand-mark" aria-hidden="true"></span>
        <div>
          <strong>Mini-OGAS</strong>
          <small>Power-on self test</small>
        </div>
      </div>
      <h2>系统启动自检</h2>
      <div class="boot-screen">
        <article
          v-for="check in checks"
          :key="check.id"
          class="boot-line"
          :class="check.visualStatus"
        >
          <span>{{ checkCode(check.visualStatus) }}</span>
          <strong>{{ check.label }}</strong>
          <small>{{ check.detail }}</small>
        </article>
      </div>
      <div class="boot-progress" aria-label="自检进度">
        <span :style="{ width: `${bootProgress}%` }"></span>
      </div>
      <p>{{ preflightLoading ? '正在检查父子节点、调度表、规则引擎与密钥库...' : '自检完成，正在进入管理员登录。' }}</p>
    </div>

    <form v-else class="login-card" @submit.prevent="emit('login')">
      <p class="eyebrow">管理员验证</p>
      <h2>进入 Mini-OGAS 控制台</h2>
      <p>系统自检已完成。请输入管理员密码，解锁接口配置并进入控制台。</p>
      <div v-if="preflight?.nodes?.length" class="startup-nodes">
        <strong>自检结果</strong>
        <span v-for="check in startupChecks" :key="check.id">
          {{ check.label }} / {{ checkLabel(check.status) }}
        </span>
      </div>
      <label>
        <span>管理员账号</span>
        <input
          :value="loginOperator"
          type="text"
          autocomplete="username"
          placeholder="admin"
          @input="emit('update:loginOperator', ($event.target as HTMLInputElement).value)"
        />
      </label>
      <label>
        <span>管理员密码</span>
        <input
          :value="loginPassword"
          type="password"
          autocomplete="new-password"
          placeholder="请输入管理员密码"
          @input="emit('update:loginPassword', ($event.target as HTMLInputElement).value)"
        />
      </label>
      <p
        v-if="loginFeedback"
        class="alarm-feedback"
        :class="{ error: loginFeedback.includes('失败') || loginFeedback.includes('无法') || loginFeedback.includes('不正确') }"
      >
        {{ loginFeedback }}
      </p>
      <div class="login-actions">
        <button class="secondary-action" type="button" :disabled="preflightLoading || loginLoading" @click="emit('run-preflight')">
          重新自检
        </button>
        <button class="primary-action" type="submit" :disabled="loginLoading || !loginPassword">
          {{ loginLoading ? '验证与调用中...' : '登录并进入系统' }}
        </button>
      </div>
      <small class="startup-note">登录后才会调用外部模型；若模型超时，系统会明确显示规则回退状态。</small>
    </form>
  </section>
</template>
