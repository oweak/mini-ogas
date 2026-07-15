<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { apiFetch } from './apiClient'
import {
  freshnessLabel,
  qualityPresentation,
  signalValueLabel,
  type ProjectionStatus,
  type QualitySummary
} from './dataQuality'

const summary = ref<QualitySummary | null>(null)
const projection = ref<ProjectionStatus | null>(null)
const loading = ref(false)
const rebuilding = ref(false)
const errorMessage = ref('')
const projectionMessage = ref('')
const rebuildReason = ref('管理员数据投影恢复')
let refreshTimer: ReturnType<typeof setInterval> | null = null

const kpis = computed(() => {
  const counts = summary.value?.counts ?? {}
  return [
    { key: 'total', label: '监测信号', value: summary.value?.signals.length ?? 0, tone: 'neutral' },
    { key: 'good', label: '质量良好', value: counts.good ?? 0, tone: 'good' },
    { key: 'uncertain', label: '待确认', value: counts.uncertain ?? 0, tone: 'uncertain' },
    { key: 'bad', label: '异常 / 缺失', value: (counts.bad ?? 0) + (counts.missing ?? 0), tone: 'bad' }
  ]
})

const sourceLabels = computed(() => {
  const sources = new Set(
    (summary.value?.signals ?? [])
      .map((signal) => signal.source)
      .filter((source): source is string => Boolean(source))
  )
  return [...sources]
})

function timeLabel(value: string | null | undefined) {
  if (!value) return '未上报'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString('zh-CN', { hour12: false })
}

async function refresh() {
  if (loading.value) return
  loading.value = true
  errorMessage.value = ''
  try {
    const [qualityResponse, projectionResponse] = await Promise.all([
      apiFetch('/api/telemetry/quality/summary'),
      apiFetch('/api/telemetry/projection/status')
    ])
    if (!qualityResponse.ok) {
      throw new Error(`数据质量接口返回 ${qualityResponse.status}`)
    }
    summary.value = await qualityResponse.json() as QualitySummary
    if (projectionResponse.ok) {
      projection.value = await projectionResponse.json() as ProjectionStatus
      projectionMessage.value = ''
    } else {
      projection.value = null
      projectionMessage.value = `Redis 投影状态不可用：${projectionResponse.status}`
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '数据质量接口不可用'
  } finally {
    loading.value = false
  }
}

async function rebuildProjection() {
  const reason = rebuildReason.value.trim()
  if (reason.length < 3 || rebuilding.value) return
  rebuilding.value = true
  projectionMessage.value = ''
  try {
    const response = await apiFetch('/api/telemetry/projection/rebuild', {
      method: 'POST',
      body: JSON.stringify({ reason })
    })
    const result = await response.json()
    if (!response.ok) {
      throw new Error(result?.detail?.message ?? `投影重建失败：${response.status}`)
    }
    projectionMessage.value = `已重建 ${result.projected_key_count} 个最新值索引`
    await refresh()
  } catch (error) {
    projectionMessage.value = error instanceof Error ? error.message : '投影重建失败'
  } finally {
    rebuilding.value = false
  }
}

onMounted(() => {
  void refresh()
  refreshTimer = setInterval(() => void refresh(), 5_000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<template>
  <section class="quality-page" aria-label="数据质量运行状态">
    <header class="quality-header">
      <div>
        <p class="eyebrow">Historian / Redis Projection</p>
        <h2>遥测事实与质量状态</h2>
        <div class="quality-source-line">
          <span class="source-chip authority">事实源 {{ summary?.source_of_truth ?? '未连接' }}</span>
          <span v-for="source in sourceLabels" :key="source" class="source-chip">{{ source }}</span>
          <span class="source-time">数据时间 {{ timeLabel(summary?.generated_at) }}</span>
        </div>
      </div>
      <button class="secondary-button" type="button" :disabled="loading" @click="refresh">
        {{ loading ? '刷新中...' : '刷新数据' }}
      </button>
    </header>

    <p v-if="errorMessage" class="quality-error" role="alert">{{ errorMessage }}</p>

    <section class="quality-kpis" aria-label="质量汇总">
      <article
        v-for="(item, index) in kpis"
        :key="item.key"
        class="quality-kpi"
        :class="`tone-${item.tone}`"
        :style="{ '--entry-delay': `${index * 55}ms` }"
      >
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </article>
    </section>

    <div class="quality-layout">
      <section class="panel quality-table-panel">
        <div class="panel-heading compact-heading">
          <div>
            <p class="eyebrow">Latest Values</p>
            <h3>最新采样</h3>
          </div>
          <span class="live-indicator"><i aria-hidden="true"></i>5 秒刷新</span>
        </div>
        <div class="quality-table-wrap">
          <table class="quality-table">
            <thead>
              <tr>
                <th>信号</th>
                <th>设备</th>
                <th>当前值</th>
                <th>质量</th>
                <th>新鲜度</th>
                <th>来源节点</th>
                <th>采样时间</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(signal, index) in summary?.signals ?? []"
                :key="`${signal.source_id ?? 'missing'}:${signal.signal_code}`"
                :style="{ '--entry-delay': `${index * 45}ms` }"
              >
                <td>
                  <strong>{{ signal.signal_code }}</strong>
                  <small>{{ signal.display_name }}</small>
                </td>
                <td>{{ signal.equipment_code ?? '未映射' }}</td>
                <td class="signal-value">{{ signalValueLabel(signal) }}</td>
                <td>
                  <span
                    class="quality-badge"
                    :class="`tone-${qualityPresentation(signal.quality_code, signal.quality_reason).tone}`"
                  >
                    {{ qualityPresentation(signal.quality_code, signal.quality_reason).label }}
                  </span>
                </td>
                <td>{{ freshnessLabel(signal.freshness_age_ms) }}</td>
                <td>
                  <strong>{{ signal.source_id ?? '未上报' }}</strong>
                  <small>{{ signal.source ?? 'unknown' }}</small>
                </td>
                <td>{{ timeLabel(signal.source_timestamp) }}</td>
              </tr>
              <tr v-if="!loading && !summary?.signals.length">
                <td colspan="7" class="empty-row">当前作用域没有遥测定义</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <aside class="panel projection-panel" aria-label="Redis 投影管理">
        <div class="panel-heading compact-heading">
          <div>
            <p class="eyebrow">Disposable Read Model</p>
            <h3>Redis 最新值投影</h3>
          </div>
          <span class="quality-badge" :class="projection?.available ? 'tone-good' : 'tone-bad'">
            {{ projection?.available ? '可用' : '不可用' }}
          </span>
        </div>
        <dl class="projection-facts">
          <div>
            <dt>提供方</dt>
            <dd>{{ projection?.provider ?? '未连接' }}</dd>
          </div>
          <div>
            <dt>权威来源</dt>
            <dd>{{ projection?.authority ?? 'PostgreSQL Historian' }}</dd>
          </div>
          <div>
            <dt>活动代次</dt>
            <dd class="generation-value">{{ projection?.active_generation ?? '尚未建立' }}</dd>
          </div>
        </dl>
        <label class="projection-reason">
          <span>重建原因</span>
          <input v-model="rebuildReason" maxlength="240" type="text">
        </label>
        <button
          class="primary-button"
          type="button"
          :disabled="rebuilding || rebuildReason.trim().length < 3"
          @click="rebuildProjection"
        >
          {{ rebuilding ? '重建中...' : '从 Historian 重建' }}
        </button>
        <p v-if="projectionMessage" class="projection-message" aria-live="polite">
          {{ projectionMessage }}
        </p>
      </aside>
    </div>
  </section>
</template>
