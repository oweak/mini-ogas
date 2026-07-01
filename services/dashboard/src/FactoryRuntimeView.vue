<script setup lang="ts">
import { computed } from 'vue'
import type { AiRuleExplanation, LogEvent, MachineState, PartQueueSnapshot, RuleConclusion, SnapshotSummary, Workshop } from './types'

type ControlServiceRow = {
  code: string
  name: string
  role: string
  status: 'online' | 'degraded' | string
  metric: string
  boundary: string
}

type NodeRuntimeRow = {
  node_code: string
  machine_code: string
  status: string
  deployment_mode: string
  simulation_mode: string
  host: string
  pid: number | string
  heartbeat_sec: number | string
  run_id: string
  scenario_id: string
  simulation_time: string
  simulation_speed: number | string
  simulation_engine: string
  runtime_source: string
  last_seen_sec?: number
  sync_records: number
}

type AiSmokeTruth = {
  status: string
  detail: string
  source: string
  isLiveApi: boolean
}

type AuthRuntime = {
  provider: string
  model: string
  vault_unlocked: boolean
}

const props = defineProps<{
  controlServiceRows: ControlServiceRow[]
  liveWorkshops: Workshop[]
  statusLabel: Record<MachineState, string>
  syncLabel: Record<'online' | 'delayed' | 'offline', string>
  aiSmokeTruth: AiSmokeTruth
  authRuntime: AuthRuntime | null
  hostConnectedNodeCount: number
  hostNodeCount: number
  nodeRuntimeRows: NodeRuntimeRow[]
  runtimeEvents: LogEvent[]
  snapshotSummary: SnapshotSummary | null
  partQueue: PartQueueSnapshot | null
  ruleConclusions: RuleConclusion[]
  aiRuleExplanation: AiRuleExplanation | null
  aiRuleExplanationLoading: boolean
}>()

const emit = defineEmits<{
  refreshRuleExplanation: []
}>()

const nodeConnectivity = computed(() => {
  const connected = props.hostConnectedNodeCount
  const total = props.hostNodeCount
  if (total <= 0) {
    return {
      className: 'warning',
      label: '未收到子节点心跳',
      detail: 'central-api 尚未接收到任何车间子节点上报'
    }
  }
  if (connected === total) {
    return {
      className: 'running',
      label: '父子节点已连接',
      detail: `${connected}/${total} 个车间子节点在线`
    }
  }
  if (connected > 0) {
    return {
      className: 'warning',
      label: '部分子节点离线',
      detail: `${connected}/${total} 个车间子节点在线`
    }
  }
  return {
    className: 'warning',
    label: '子节点全部离线',
    detail: `${connected}/${total} 个车间子节点在线`
  }
})

const visibleRuleConclusions = computed(() => props.ruleConclusions.slice(0, 4))
const visiblePartQueueItems = computed(() => (props.partQueue?.items ?? []).slice(-6).reverse())
const partQueueCounts = computed(() => ({
  ready: props.partQueue?.counts.ready ?? 0,
  claimed: props.partQueue?.counts.claimed ?? 0,
  completed: props.partQueue?.counts.completed ?? 0
}))
const partStatusLabel: Record<string, string> = {
  ready: '待加工',
  claimed: '加工中',
  completed: '已归档',
  interrupted: '已中断'
}
const aiExplanationStatusLabel = computed(() => {
  const explanation = props.aiRuleExplanation
  if (!explanation) return '未请求'
  if (explanation.used_live_ai) return '真实模型解释'
  if (explanation.status === 'steady') return '稳定态监测'
  return '规则回退解释'
})
</script>

<template>
  <section class="content-grid factory-layout">
    <div class="panel factory-map">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">工厂结构</p>
          <h2>中央控制到车间节点</h2>
        </div>
        <span class="badge">REST 心跳 + 本地缓存同步</span>
      </div>

      <div class="central-node">
        <span class="status-dot running" aria-hidden="true"></span>
        <div>
          <strong>中央控制</strong>
          <small>FastAPI / 权限策略 / 调度状态 / 审计追踪</small>
        </div>
      </div>

      <div v-if="props.snapshotSummary" class="snapshot-strip" aria-label="Dashboard snapshot runtime">
        <div>
          <span>数据源</span>
          <strong>{{ props.snapshotSummary.dataSource }}</strong>
        </div>
        <div>
          <span>仿真引擎</span>
          <strong>{{ props.snapshotSummary.simulationEngine }}</strong>
        </div>
        <div>
          <span>运行批次</span>
          <strong>{{ props.snapshotSummary.runId }}</strong>
        </div>
        <div>
          <span>场景</span>
          <strong>{{ props.snapshotSummary.scenarioId }}</strong>
        </div>
        <div>
          <span>仿真时间</span>
          <strong>{{ props.snapshotSummary.simulationTime || props.snapshotSummary.generatedAt }}</strong>
        </div>
      </div>

      <div class="service-rail" aria-label="中央服务节点">
        <article
          v-for="service in props.controlServiceRows"
          :key="service.code"
          class="service-node"
          :class="{ degraded: service.status === 'degraded' }"
        >
          <div class="service-head">
            <span
              class="status-dot"
              :class="service.status === 'degraded' ? 'warning' : 'running'"
              aria-hidden="true"
            ></span>
            <div>
              <strong>{{ service.name }}</strong>
              <small>{{ service.code }}</small>
            </div>
          </div>
          <p>{{ service.role }}</p>
          <dl>
            <div>
              <dt>当前负载</dt>
              <dd>{{ service.metric }}</dd>
            </div>
            <div>
              <dt>控制边界</dt>
              <dd>{{ service.boundary }}</dd>
            </div>
          </dl>
        </article>
      </div>

      <div class="workshop-list">
        <article v-for="workshop in props.liveWorkshops" :key="workshop.code" class="workshop-block">
          <header>
            <div>
              <span class="status-dot" :class="workshop.status" aria-hidden="true"></span>
              <strong>{{ workshop.name }}</strong>
              <small>{{ workshop.node }}</small>
            </div>
            <span class="load-meter">{{ workshop.load }}% 负载</span>
          </header>

          <div class="machine-grid">
            <article
              v-for="machine in workshop.machines"
              :key="machine.code"
              class="machine-card"
              :class="machine.state"
            >
              <div class="machine-head">
                <div>
                  <strong>{{ machine.code }}</strong>
                  <span>{{ machine.type }}</span>
                </div>
                <span class="state-pill" :class="machine.state">{{ props.statusLabel[machine.state] }}</span>
              </div>
              <dl class="machine-metrics">
                <div>
                  <dt>工单</dt>
                  <dd>{{ machine.workOrder }}</dd>
                </div>
                <div>
                  <dt>工序</dt>
                  <dd>{{ machine.process }}</dd>
                </div>
                <div>
                  <dt>产量</dt>
                  <dd>{{ machine.output }}/{{ machine.target }}</dd>
                </div>
                <div>
                  <dt>良品率</dt>
                  <dd>{{ machine.yieldRate }}%</dd>
                </div>
                <div>
                  <dt>刀具磨损</dt>
                  <dd>{{ machine.toolWear }}%</dd>
                </div>
                <div>
                  <dt>产速</dt>
                  <dd>{{ machine.actualRate ?? '未上报' }}/{{ machine.targetRate ?? '未上报' }}</dd>
                </div>
                <div>
                  <dt>利用率</dt>
                  <dd>{{ machine.utilization !== undefined ? `${Math.round(machine.utilization * 100)}%` : '未上报' }}</dd>
                </div>
                <div>
                  <dt>同步状态</dt>
                  <dd>{{ props.syncLabel[machine.sync] }}</dd>
                </div>
              </dl>
              <p v-if="machine.lastAlarm" class="machine-alarm">{{ machine.lastAlarm }}</p>
            </article>
          </div>
        </article>
      </div>
    </div>

    <aside class="right-stack" aria-label="节点运行证据与操作追踪">
      <section class="panel ai-panel">
        <div class="panel-heading compact">
          <div>
            <p class="eyebrow">运行证据</p>
            <h2>父子节点状态</h2>
          </div>
          <span class="state-pill" :class="nodeConnectivity.className">
            {{ nodeConnectivity.label }}
          </span>
        </div>

        <div class="ai-node-summary">
          <div>
            <span>AI 接口</span>
            <strong>{{ props.aiSmokeTruth.status }}</strong>
          </div>
          <div>
            <span>子节点</span>
            <strong>{{ props.hostConnectedNodeCount }}/{{ props.hostNodeCount }} 在线</strong>
          </div>
        </div>
        <p class="runtime-truth">{{ nodeConnectivity.detail }}</p>

        <div class="ai-section part-transfer-section">
          <h3>WIP 转移队列</h3>
          <div class="part-flow-metrics" aria-label="零件转移队列统计">
            <div>
              <span>待领料</span>
              <strong>{{ partQueueCounts.ready }}</strong>
            </div>
            <div>
              <span>加工中</span>
              <strong>{{ partQueueCounts.claimed }}</strong>
            </div>
            <div>
              <span>已归档</span>
              <strong>{{ partQueueCounts.completed }}</strong>
            </div>
          </div>
          <ol v-if="visiblePartQueueItems.length" class="part-flow-list">
            <li
              v-for="part in visiblePartQueueItems"
              :key="part.part_id"
              :class="part.status"
            >
              <span class="part-flow-track" aria-hidden="true"></span>
              <div>
                <strong>{{ part.part_id }} / {{ partStatusLabel[part.status] ?? part.status }}</strong>
                <small>{{ part.source_node }} → {{ part.target_node }}</small>
                <small>{{ part.order_id }} / {{ part.current_step }} / {{ part.claimed_by || '未领取' }}</small>
              </div>
            </li>
          </ol>
          <article v-else class="ai-case part-flow-empty">
            <div>
              <strong>尚无转移零件</strong>
              <span>等待上游工序完成后写入下一工序队列</span>
            </div>
          </article>
        </div>

        <div class="ai-section">
          <h3>AI 调用证明</h3>
          <div class="ai-truth-indicator" :class="props.aiSmokeTruth.isLiveApi ? 'live' : props.authRuntime?.vault_unlocked ? 'unlocked' : 'locked'">
            <span class="ai-truth-dot" aria-hidden="true"></span>
            <span class="ai-truth-label">{{ props.aiSmokeTruth.isLiveApi ? '真实模型' : props.authRuntime?.vault_unlocked ? '已解锁 / 待验证' : '规则回退' }}</span>
          </div>
          <article class="ai-case">
            <div>
              <strong>{{ props.aiSmokeTruth.isLiveApi ? '真实模型已接入' : '未证明真实模型调用' }}</strong>
              <span>{{ props.authRuntime?.provider || 'unknown' }} / {{ props.authRuntime?.model || 'unknown' }}</span>
            </div>
            <small>来源：{{ props.aiSmokeTruth.source }} / vault：{{ props.authRuntime?.vault_unlocked ? '已解锁' : '未解锁' }}</small>
            <small>{{ props.aiSmokeTruth.detail }}</small>
          </article>
        </div>

        <div class="ai-section">
          <div class="section-action-head">
            <h3>AI 规则解释</h3>
            <button class="secondary-action compact-action" type="button" :disabled="props.aiRuleExplanationLoading" @click="emit('refreshRuleExplanation')">
              {{ props.aiRuleExplanationLoading ? '分析中' : '刷新解释' }}
            </button>
          </div>
          <article class="ai-case rule-ai-case" :class="props.aiRuleExplanation?.used_live_ai ? 'live' : props.aiRuleExplanation?.status || 'idle'">
            <div>
              <strong>{{ aiExplanationStatusLabel }}</strong>
              <span>{{ props.aiRuleExplanation?.provider || props.authRuntime?.provider || 'unknown' }}</span>
            </div>
            <small>{{ props.aiRuleExplanation?.summary || '等待 dashboard snapshot 与规则结论同步后生成解释。' }}</small>
            <small v-if="props.aiRuleExplanation">
              digest：{{ props.aiRuleExplanation.prompt_digest }} / 规则数：{{ props.aiRuleExplanation.rule_count }} / 来源：{{ props.aiRuleExplanation.source }}
            </small>
            <ul v-if="props.aiRuleExplanation?.reasoning?.length" class="rule-evidence-list">
              <li v-for="item in props.aiRuleExplanation.reasoning.slice(0, 3)" :key="`ai-reason-${item}`">{{ item }}</li>
            </ul>
            <ol v-if="props.aiRuleExplanation?.recommended_actions?.length" class="rule-action-list">
              <li v-for="action in props.aiRuleExplanation.recommended_actions.slice(0, 3)" :key="`ai-action-${action}`">{{ action }}</li>
            </ol>
          </article>
        </div>

        <div class="ai-section">
          <h3>心跳来源</h3>
          <article v-for="item in props.nodeRuntimeRows" :key="item.node_code" class="ai-case">
            <div>
              <strong>{{ item.node_code }}</strong>
              <span>{{ item.machine_code }} / {{ item.status }}</span>
            </div>
            <small>运行批次：{{ item.run_id || '未上报' }} / 场景：{{ item.scenario_id || '未上报' }}</small>
            <small>仿真时间：{{ item.simulation_time || '未上报' }} / 倍率：{{ item.simulation_speed || '未上报' }} / 来源：{{ item.runtime_source }}</small>
            <small>运行模式：{{ item.deployment_mode }} / 模拟：{{ item.simulation_mode }} / 引擎：{{ item.simulation_engine || '未上报' }}</small>
            <small>主机：{{ item.host || '-' }} / pid：{{ item.pid || '-' }} / 心跳：{{ item.heartbeat_sec || '-' }} 秒 / 最近：{{ item.last_seen_sec ?? '-' }} 秒前 / 待同步：{{ item.sync_records }}</small>
          </article>
        </div>

        <div class="ai-section">
          <h3>规则结论</h3>
          <article
            v-for="conclusion in visibleRuleConclusions"
            :key="conclusion.conclusion_id"
            class="ai-case rule-case"
            :class="conclusion.severity"
          >
            <div>
              <strong>{{ conclusion.machine_code }} / {{ conclusion.risk_level }}</strong>
              <span>{{ conclusion.rule_id }}</span>
            </div>
            <small>{{ conclusion.title }}</small>
            <small>{{ conclusion.summary }}</small>
            <ul class="rule-evidence-list">
              <li v-for="item in conclusion.evidence.slice(0, 3)" :key="`${conclusion.conclusion_id}-${item.field}`">
                {{ item.field }} {{ item.operator }} {{ item.threshold }}，当前 {{ item.value }}
              </li>
            </ul>
            <ol class="rule-action-list">
              <li v-for="action in conclusion.recommended_actions.slice(0, 2)" :key="`${conclusion.conclusion_id}-${action}`">
                {{ action }}
              </li>
            </ol>
          </article>
          <article v-if="visibleRuleConclusions.length === 0" class="ai-case rule-case empty">
            <div>
              <strong>未触发瓶颈或饥饿规则</strong>
              <span>只读判断</span>
            </div>
            <small>当前 snapshot 未发现需要上报的流程瓶颈；规则引擎保持监测，不创建命令。</small>
          </article>
        </div>

        <div class="ai-section">
          <h3>管理边界</h3>
          <ul class="approval-list">
            <li>前端状态必须来自 central-api，不再用静态报警冒充运行结果</li>
            <li>生产节点健康以子节点心跳为准，Kali/虚拟机仅作为攻防实验环境</li>
            <li>问题解决后必须从队列消失并进入日志管理</li>
          </ul>
        </div>
      </section>

      <section class="panel event-panel">
        <div class="panel-heading compact">
          <div>
            <p class="eyebrow">追踪</p>
            <h2>最近操作</h2>
          </div>
        </div>
        <ol class="event-list">
          <li
            v-for="event in props.runtimeEvents"
            :key="`${event.time}-${event.source}-${event.message}`"
            :class="event.level"
          >
            <time>{{ event.time }}</time>
            <strong>{{ event.source }}</strong>
            <span>{{ event.message }}</span>
          </li>
        </ol>
      </section>
    </aside>
  </section>
</template>
