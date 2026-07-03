<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getReplayRun, listReplayRuns } from './replayApi'
import type { ReplayRunDetail, ReplayRunSummary, ReplayTimelineItem } from './types'

const runs = ref<ReplayRunSummary[]>([])
const selectedRunId = ref('')
const detail = ref<ReplayRunDetail | null>(null)
const runsLoading = ref(false)
const detailLoading = ref(false)
const error = ref('')
const detailError = ref('')

const selectedRun = computed(() => runs.value.find((run) => run.run_id === selectedRunId.value) ?? null)
const timeline = computed(() => detail.value?.timeline ?? [])
const latestEvents = computed(() => timeline.value.slice(-120).reverse())
const hasRuns = computed(() => runs.value.length > 0)

function formatTime(value?: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString()
}

function kindLabel(kind: string) {
  const labels: Record<string, string> = {
    heartbeat: '心跳',
    command: '命令',
    part_queue: '工件流',
    audit: '审计',
    alert: '报警',
    ai_diagnosis: 'AI 诊断'
  }
  return labels[kind] ?? kind
}

function eventSummary(item: ReplayTimelineItem) {
  if (item.kind === 'heartbeat') {
    const detail = item.detail ?? {}
    return `${detail.machine_code ?? item.node_code ?? '-'} / ${detail.active_order ?? '无工单'} / 利用率 ${detail.utilization ?? '-'}`
  }
  if (item.kind === 'command') return String(item.detail?.result_message || item.status || '命令状态已记录')
  if (item.kind === 'part_queue') return `${item.detail?.source_node ?? '-'} -> ${item.detail?.target_node ?? '-'}`
  if (item.kind === 'audit') return String(item.detail?.detail || item.status || '审计事件已归档')
  if (item.kind === 'alert') return String(item.detail?.description || item.status || '报警已记录')
  if (item.kind === 'ai_diagnosis') return String(item.detail?.recommended_action || item.detail?.root_cause || 'AI 诊断已记录')
  return String(item.status || '')
}

async function loadDetail(runId: string) {
  if (!runId) {
    detail.value = null
    return
  }
  detailLoading.value = true
  detailError.value = ''
  try {
    detail.value = await getReplayRun(runId, 500)
  } catch (err) {
    detail.value = null
    detailError.value = err instanceof Error ? err.message : '回放明细不可用'
  } finally {
    detailLoading.value = false
  }
}

async function loadRuns(preferredRunId = selectedRunId.value) {
  runsLoading.value = true
  error.value = ''
  try {
    const response = await listReplayRuns(30)
    if (response.status !== 'ok') throw new Error(response.reason || response.error || response.status)
    runs.value = response.runs
    const nextRunId = preferredRunId && response.runs.some((run) => run.run_id === preferredRunId)
      ? preferredRunId
      : response.runs[0]?.run_id ?? ''
    selectedRunId.value = nextRunId
    await loadDetail(nextRunId)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '回放批次不可用'
    runs.value = []
    detail.value = null
  } finally {
    runsLoading.value = false
  }
}

function selectRun(runId: string) {
  selectedRunId.value = runId
  void loadDetail(runId)
}

onMounted(() => {
  void loadRuns()
})
</script>

<template>
  <section class="content-grid replay-layout">
    <aside class="panel replay-runs-panel">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">运行证据</p>
          <h2>数据库回放批次</h2>
        </div>
        <button class="secondary-action" type="button" :disabled="runsLoading" @click="loadRuns()">
          {{ runsLoading ? '刷新中...' : '刷新' }}
        </button>
      </div>

      <p v-if="error" class="alarm-feedback error" role="alert">回放批次读取失败：{{ error }}</p>
      <div v-if="runsLoading && !runs.length" class="replay-skeleton" aria-label="正在读取运行批次">
        <span></span>
        <span></span>
        <span></span>
      </div>
      <p v-else-if="!hasRuns" class="empty-hint">
        暂无可回放的 run_id。等待节点上报 heartbeat v2 后，PostgreSQL 会自动形成运行批次。
      </p>

      <div v-else class="replay-run-list" role="list" aria-label="运行批次">
        <button
          v-for="run in runs"
          :key="run.run_id"
          class="replay-run-button"
          :class="{ active: selectedRunId === run.run_id }"
          type="button"
          role="listitem"
          @click="selectRun(run.run_id)"
        >
          <strong>{{ run.run_id }}</strong>
          <span>{{ run.node_count }} 个节点 / {{ run.heartbeat_count }} 条心跳</span>
          <small>{{ formatTime(run.ended_at) }}</small>
        </button>
      </div>
    </aside>

    <div class="replay-detail-column">
      <section class="panel replay-hero-panel">
        <div class="panel-heading">
          <div>
            <p class="eyebrow">运行回放</p>
            <h2>{{ selectedRun ? selectedRun.run_id : '等待选择运行批次' }}</h2>
          </div>
          <span class="state-pill" :class="detail?.status === 'ok' ? 'running' : 'warning'">
            {{ detail?.status || (detailLoading ? 'loading' : 'idle') }}
          </span>
        </div>

        <p v-if="detailError" class="alarm-feedback error" role="alert">回放明细读取失败：{{ detailError }}</p>
        <div v-if="detailLoading" class="replay-skeleton detail" aria-label="正在读取回放明细">
          <span></span>
          <span></span>
        </div>

        <div v-if="detail" class="replay-facts">
          <article>
            <span>节点</span>
            <strong>{{ detail.node_codes.length }}</strong>
          </article>
          <article>
            <span>心跳</span>
            <strong>{{ detail.counts.heartbeats }}</strong>
          </article>
          <article>
            <span>命令</span>
            <strong>{{ detail.counts.commands }}</strong>
          </article>
          <article>
            <span>审计</span>
            <strong>{{ detail.counts.audit_events }}</strong>
          </article>
          <article>
            <span>AI 诊断</span>
            <strong>{{ detail.counts.ai_diagnoses }}</strong>
          </article>
          <article>
            <span>时间线</span>
            <strong>{{ detail.counts.timeline }}</strong>
          </article>
        </div>

        <dl v-if="detail" class="replay-meta">
          <div>
            <dt>场景</dt>
            <dd>{{ detail.scenario_ids.join(', ') || '-' }}</dd>
          </div>
          <div>
            <dt>开始</dt>
            <dd>{{ formatTime(detail.started_at) }}</dd>
          </div>
          <div>
            <dt>结束</dt>
            <dd>{{ formatTime(detail.ended_at) }}</dd>
          </div>
          <div>
            <dt>持久化</dt>
            <dd>{{ detail.backend || '-' }}</dd>
          </div>
        </dl>
      </section>

      <section class="panel replay-timeline-panel">
        <div class="panel-heading compact">
          <div>
            <p class="eyebrow">事件链</p>
            <h2>按数据库时间重建的运行过程</h2>
          </div>
          <span v-if="detail" class="badge">{{ latestEvents.length }}/{{ detail.counts.timeline }}</span>
        </div>

        <p v-if="detail && !latestEvents.length" class="empty-hint">该运行批次暂无可显示事件。</p>
        <ol v-else class="replay-timeline">
          <li v-for="item in latestEvents" :key="`${item.kind}-${item.time}-${item.title}`" :class="item.kind">
            <time>{{ formatTime(item.time) }}</time>
            <div>
              <strong>{{ kindLabel(item.kind) }} / {{ item.title || item.node_code || '-' }}</strong>
              <span>{{ item.node_code || 'central-api' }} / {{ item.status || 'recorded' }}</span>
              <small>{{ eventSummary(item) }}</small>
            </div>
          </li>
        </ol>
      </section>
    </div>
  </section>
</template>
