<script setup lang="ts">
import type { Alarm } from './types'

type AiDecisionOption = {
  label: string
  rationale?: string
  risk?: string
  automation?: boolean
}

type ApiDiagnosis = {
  id: number
  alert_id: number | string
  issue_id?: string
  node_code: string
  root_cause: string
  recommended_action: string
  confidence: number
  need_isolation: boolean
  model_name: string
  source?: string
  provider?: string
  status?: string
  generated_at?: string
  risk_assessment?: string
  requires_human?: boolean
  automation_allowed?: boolean
  evidence?: string[]
  options?: AiDecisionOption[]
}

type EscalationItem = {
  id?: number
  node_code: string
  issue_type: string
  description: string
  status: string
}

type AlarmActions = {
  confirm: boolean
  diagnose: boolean
  isolate: boolean
  observe: boolean
  ignore: boolean
  escalate: boolean
  close: boolean
}

defineProps<{
  alarms: Alarm[]
  selectedAlarm?: Alarm
  selectedAlarmId: string
  alarmStatusLabel: Record<Alarm['status'], string>
  severityLabel: Record<Alarm['severity'], string>
  alarmActions: AlarmActions
  diagnosisForSelected: ApiDiagnosis[]
  latestDiagnosisForSelected?: ApiDiagnosis
  aiRuntimeTruthLabel: string
  aiDiagnosisResult: string | null
  alarmFeedback: string
  alarmActionLoading: string | null
  escalationQueue: EscalationItem[]
  escalationConfirmCodes: Record<number, string>
  resolvedEffects: string[]
}>()

const emit = defineEmits<{
  refresh: []
  selectAlarm: [id: string]
  updateEscalationCode: [id: number, code: string]
  confirmAlarm: [alarm: Alarm]
  runAiDiagnose: [alarm: Alarm]
  isolateNode: [alarm: Alarm]
  observeAlarm: [alarm: Alarm]
  ignoreAlarm: [alarm: Alarm]
  escalateToHuman: [alarm: Alarm]
  closeAlarm: [alarm: Alarm]
  decideEscalation: [item: EscalationItem, decision: 'approve' | 'reject']
}>()

function feedbackIsError(value: string) {
  return value.includes('失败') || value.includes('错误') || value.includes('无法')
}
</script>

<template>
  <section class="content-grid alarm-layout">
    <div class="panel alarm-list-panel">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">报警队列</p>
          <h2>确认、诊断、处置</h2>
        </div>
        <button class="secondary-action" type="button" :disabled="alarmActionLoading !== null" @click="emit('refresh')">
          {{ alarmActionLoading ? '刷新中...' : '刷新数据' }}
        </button>
      </div>
      <p v-if="!alarms.length" class="empty-hint">暂无报警数据</p>
      <TransitionGroup name="alarm-queue" tag="div" class="alarm-row-stack">
        <button
          v-for="alarm in alarms"
          :key="alarm.id"
          class="alarm-row"
          :class="{ selected: alarm.id === selectedAlarmId }"
          type="button"
          @click="emit('selectAlarm', alarm.id)"
        >
          <span class="severity" :class="alarm.severity">{{ severityLabel[alarm.severity] }}</span>
          <strong>{{ alarm.title }}</strong>
          <small>{{ alarm.machine }} / {{ alarmStatusLabel[alarm.status] }}</small>
        </button>
      </TransitionGroup>
    </div>

    <div class="alarm-detail-stack">
      <article v-if="selectedAlarm" class="panel alarm-detail">
        <div class="panel-heading">
          <div>
            <p class="eyebrow">{{ selectedAlarm.id }} / {{ selectedAlarm.machine }}</p>
            <h2>{{ selectedAlarm.title }}</h2>
          </div>
          <span class="severity" :class="selectedAlarm.severity">
            {{ severityLabel[selectedAlarm.severity] }}
          </span>
        </div>

        <dl class="alarm-facts">
          <div>
            <dt>当前值</dt>
            <dd>{{ selectedAlarm.value }}</dd>
          </div>
          <div>
            <dt>状态</dt>
            <dd>{{ alarmStatusLabel[selectedAlarm.status] }}</dd>
          </div>
          <div>
            <dt>所需审批</dt>
            <dd>{{ selectedAlarm.requiredRole }}</dd>
          </div>
        </dl>

        <section class="diagnosis-box">
          <h3>规则引擎</h3>
          <p>{{ selectedAlarm.rule }}</p>
        </section>

        <section class="diagnosis-box">
          <h3>AI 诊断</h3>
          <p v-if="diagnosisForSelected.length">
            <span v-for="d in diagnosisForSelected" :key="d.id" class="diag-result">
              <strong>{{ d.source === 'api' ? '真实模型 API' : '规则回退' }}</strong>
              / {{ d.provider || 'unknown' }} / {{ d.model_name }}
              ({{ Math.round(d.confidence * 100) }}%):
              {{ d.root_cause }} - {{ d.recommended_action }}
              <span v-if="d.need_isolation" class="tag-isolate">需隔离</span>
            </span>
          </p>
          <p v-else-if="aiDiagnosisResult">{{ aiDiagnosisResult }}</p>
          <p v-else>{{ selectedAlarm.aiSuggestion || '尚未执行 AI 诊断' }}</p>
          <div v-if="latestDiagnosisForSelected" class="ai-provenance">
            <small>运行状态：{{ aiRuntimeTruthLabel }} / {{ latestDiagnosisForSelected.status || 'unknown' }} / {{ latestDiagnosisForSelected.generated_at || '-' }}</small>
            <small>审批边界：{{ latestDiagnosisForSelected.requires_human ? '需要人工决策' : '允许自动/脚本处置' }}；{{ latestDiagnosisForSelected.automation_allowed ? '自动化允许' : '自动化受限' }}</small>
            <p v-if="latestDiagnosisForSelected.risk_assessment">{{ latestDiagnosisForSelected.risk_assessment }}</p>
            <ul v-if="latestDiagnosisForSelected.evidence?.length" class="compact-list">
              <li v-for="evidence in latestDiagnosisForSelected.evidence.slice(0, 4)" :key="evidence">{{ evidence }}</li>
            </ul>
            <div v-if="latestDiagnosisForSelected.options?.length" class="decision-options">
              <span v-for="option in latestDiagnosisForSelected.options.slice(0, 3)" :key="option.label">
                {{ option.label }}{{ option.automation ? ' / 可自动' : ' / 人工确认' }}
              </span>
            </div>
          </div>
        </section>

        <p v-if="alarmFeedback" class="alarm-feedback" :class="{ error: feedbackIsError(alarmFeedback) }">
          {{ alarmFeedback }}
        </p>

        <div class="action-bar" aria-label="报警操作">
          <button v-if="alarmActions.confirm" class="secondary-action" type="button" :disabled="alarmActionLoading === selectedAlarm.id" @click="emit('confirmAlarm', selectedAlarm)">
            {{ alarmActionLoading === selectedAlarm.id ? '处理中...' : '确认报警' }}
          </button>
          <button v-if="alarmActions.diagnose" class="secondary-action" :class="{ 'primary-action': selectedAlarm.status === 'confirmed' }" type="button" :disabled="alarmActionLoading === selectedAlarm.id" @click="emit('runAiDiagnose', selectedAlarm)">
            {{ alarmActionLoading === selectedAlarm.id ? '诊断中...' : 'AI 诊断' }}
          </button>
          <button v-if="alarmActions.isolate" class="danger-action" type="button" :disabled="alarmActionLoading === selectedAlarm.id" @click="emit('isolateNode', selectedAlarm)">
            {{ alarmActionLoading === selectedAlarm.id ? '处理中...' : '隔离节点' }}
          </button>
          <button v-if="alarmActions.observe" class="secondary-action" type="button" :disabled="alarmActionLoading === selectedAlarm.id" @click="emit('observeAlarm', selectedAlarm)">
            {{ alarmActionLoading === selectedAlarm.id ? '提交中...' : '观察并保持运行' }}
          </button>
          <button v-if="alarmActions.ignore" class="secondary-action" type="button" :disabled="alarmActionLoading === selectedAlarm.id" @click="emit('ignoreAlarm', selectedAlarm)">
            {{ alarmActionLoading === selectedAlarm.id ? '归档中...' : '忽略误报并归档' }}
          </button>
          <button v-if="alarmActions.escalate" class="primary-action" type="button" :disabled="alarmActionLoading === selectedAlarm.id" @click="emit('escalateToHuman', selectedAlarm)">
            {{ alarmActionLoading === selectedAlarm.id ? '升级中...' : '升级人工处理' }}
          </button>
          <button v-if="alarmActions.close" class="primary-action" type="button" :disabled="alarmActionLoading === selectedAlarm.id" @click="emit('closeAlarm', selectedAlarm)">
            {{ alarmActionLoading === selectedAlarm.id ? '关闭中...' : '验证关闭并归档' }}
          </button>
        </div>
      </article>

      <article v-if="escalationQueue.length" class="panel escalation-panel">
        <div class="panel-heading compact">
          <div>
            <p class="eyebrow">升级队列</p>
            <h2>待人工决策</h2>
          </div>
        </div>
        <TransitionGroup name="alarm-queue" tag="div" class="escalation-stack">
          <div v-for="item in escalationQueue" :key="item.id ?? item.node_code" class="escalation-row">
            <strong>{{ item.node_code }}</strong>
            <span>{{ item.issue_type }}</span>
            <small>{{ item.status }}</small>
            <p>{{ item.description }}</p>
            <div v-if="item.id" class="escalation-actions">
              <input
                :value="escalationConfirmCodes[item.id] ?? ''"
                placeholder="批准需输入 CONFIRM"
                aria-label="人工决策确认码"
                @input="emit('updateEscalationCode', item.id, ($event.target as HTMLInputElement).value)"
              />
              <button class="primary-action" type="button" :disabled="alarmActionLoading === `escalation-${item.id}`" @click="emit('decideEscalation', item, 'approve')">
                批准执行
              </button>
              <button class="secondary-action" type="button" :disabled="alarmActionLoading === `escalation-${item.id}`" @click="emit('decideEscalation', item, 'reject')">
                驳回关闭
              </button>
            </div>
          </div>
        </TransitionGroup>
      </article>

      <article v-if="resolvedEffects.length" class="panel alarm-archive-panel">
        <p class="eyebrow">处置反馈</p>
        <h2>已归档结果</h2>
        <TransitionGroup name="resolved-list" tag="ol" class="alarm-archive-list">
          <li v-for="effect in resolvedEffects" :key="effect">{{ effect }}</li>
        </TransitionGroup>
      </article>

      <article v-if="!selectedAlarm" class="panel alarm-detail">
        <p class="empty-hint">请在左侧选择一个报警以查看详情并执行处置操作</p>
      </article>
    </div>
  </section>
</template>
