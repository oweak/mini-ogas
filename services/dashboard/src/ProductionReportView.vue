<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { apiFetch } from './apiClient'

type ProductionReport = {
  generated_at: string
  report_type: string
  factory_overview: {
    node_count: number
    online_count: number
    isolated_count: number
    active_alert_count: number
    critical_alert_count: number
    data_source: string
  }
  production_statistics: {
    finished_quantity: number
    defect_quantity: number
    defect_rate: number
    average_utilization: number
    average_target_rate: number
    average_actual_rate: number
  }
  dispatch_summary: {
    task_count: number
    active_task_count: number
    blocked_task_count: number
    completed_task_count: number
    scheduled_quantity: number
    completion_rate: number
  }
  market_summary: {
    signal_count: number
    average_demand_index: number
    average_inventory_pressure: number
  }
  rule_engine: {
    conclusion_count: number
    conclusions: Array<{
      conclusion_id: string
      node_code: string
      machine_code: string
      risk_level: string
      title: string
      summary: string
    }>
  }
  ai_summary: {
    status: string
    provider: string
    model: string
    message: string
  } | null
  persistence: {
    backend?: string
    status?: string
  }
  nodes: Array<{
    node_code: string
    node_name: string
    workshop_type: string
    status: string
    machine_code: string
    active_order: string
    finished_quantity: number
    defect_quantity: number
    target_rate?: number
    actual_rate?: number
    utilization?: number
  }>
}

type ExportFormat = 'markdown' | 'csv'

const report = ref<ProductionReport | null>(null)
const loading = ref(false)
const error = ref('')
const exporting = ref('')
const exportError = ref('')

function percent(value: number | undefined) {
  return `${Math.round((value ?? 0) * 100)}%`
}

function numberValue(value: number | undefined, digits = 2) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-'
  return value.toFixed(digits)
}

async function loadReport() {
  loading.value = true
  error.value = ''
  try {
    const response = await apiFetch('/api/reports/production')
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    report.value = await response.json()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'report unavailable'
  } finally {
    loading.value = false
  }
}

function exportFilename(disposition: string | null, fallback: string) {
  const match = disposition?.match(/filename="([^"]+)"/)
  return match?.[1] ?? fallback
}

async function exportReport(format: ExportFormat) {
  exporting.value = format
  exportError.value = ''
  try {
    const response = await apiFetch(`/api/reports/production/export?format=${format}`)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const blob = await response.blob()
    const suffix = format === 'csv' ? 'csv' : 'md'
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = exportFilename(response.headers.get('Content-Disposition'), `mini-ogas-production-report.${suffix}`)
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  } catch (err) {
    exportError.value = err instanceof Error ? err.message : 'export unavailable'
  } finally {
    exporting.value = ''
  }
}

onMounted(loadReport)
</script>

<template>
  <section class="content-grid report-layout">
    <div class="panel report-main">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">生产报告</p>
          <h2>{{ report ? `运行报告 / ${report.factory_overview.data_source}` : '运行报告' }}</h2>
        </div>
        <div class="report-actions">
          <button class="secondary-action" type="button" :disabled="loading" @click="loadReport">
            {{ loading ? '生成中...' : '重新生成报告' }}
          </button>
          <button
            class="secondary-action"
            type="button"
            :disabled="!report || exporting === 'markdown'"
            @click="exportReport('markdown')"
          >
            {{ exporting === 'markdown' ? '导出中...' : '导出 Markdown' }}
          </button>
          <button
            class="secondary-action"
            type="button"
            :disabled="!report || exporting === 'csv'"
            @click="exportReport('csv')"
          >
            {{ exporting === 'csv' ? '导出中...' : '导出 CSV' }}
          </button>
        </div>
      </div>

      <p v-if="error" class="alarm-feedback error">报告生成失败：{{ error }}</p>
      <p v-if="exportError" class="alarm-feedback error">报告导出失败：{{ exportError }}</p>

      <div v-if="report" class="report-metrics">
        <article>
          <span>在线节点</span>
          <strong>{{ report.factory_overview.online_count }}/{{ report.factory_overview.node_count }}</strong>
        </article>
        <article>
          <span>完成产量</span>
          <strong>{{ report.production_statistics.finished_quantity }}</strong>
        </article>
        <article>
          <span>不良率</span>
          <strong>{{ percent(report.production_statistics.defect_rate) }}</strong>
        </article>
        <article>
          <span>平均利用率</span>
          <strong>{{ percent(report.production_statistics.average_utilization) }}</strong>
        </article>
        <article>
          <span>调度任务</span>
          <strong>{{ report.dispatch_summary.task_count }}</strong>
        </article>
        <article>
          <span>规则结论</span>
          <strong>{{ report.rule_engine.conclusion_count }}</strong>
        </article>
      </div>

      <div v-if="report" class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>节点</th>
              <th>设备</th>
              <th>状态</th>
              <th>工单</th>
              <th>产量</th>
              <th>不良</th>
              <th>目标速率</th>
              <th>实际速率</th>
              <th>利用率</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="node in report.nodes" :key="node.node_code">
              <td>
                <strong>{{ node.node_code }}</strong>
                <small>{{ node.node_name }}</small>
              </td>
              <td>{{ node.machine_code || '-' }}</td>
              <td><span class="state-pill" :class="node.status">{{ node.status }}</span></td>
              <td>{{ node.active_order || '-' }}</td>
              <td>{{ node.finished_quantity ?? 0 }}</td>
              <td>{{ node.defect_quantity ?? 0 }}</td>
              <td>{{ numberValue(node.target_rate) }}</td>
              <td>{{ numberValue(node.actual_rate) }}</td>
              <td>{{ percent(node.utilization) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <aside v-if="report" class="panel report-side">
      <p class="eyebrow">报告摘要</p>
      <dl class="report-facts">
        <div>
          <dt>生成时间</dt>
          <dd>{{ new Date(report.generated_at).toLocaleString() }}</dd>
        </div>
        <div>
          <dt>持久化</dt>
          <dd>{{ report.persistence.backend || '-' }} / {{ report.persistence.status || '-' }}</dd>
        </div>
        <div>
          <dt>AI 运行</dt>
          <dd>{{ report.ai_summary?.provider || '-' }} / {{ report.ai_summary?.status || '-' }}</dd>
        </div>
        <div>
          <dt>市场信号</dt>
          <dd>{{ report.market_summary.signal_count }} / 需求 {{ numberValue(report.market_summary.average_demand_index) }}</dd>
        </div>
        <div>
          <dt>库存压力</dt>
          <dd>{{ numberValue(report.market_summary.average_inventory_pressure) }}</dd>
        </div>
        <div>
          <dt>调度阻塞</dt>
          <dd>{{ report.dispatch_summary.blocked_task_count }}</dd>
        </div>
      </dl>

      <div class="report-rule-list">
        <h3>规则引擎</h3>
        <p v-if="!report.rule_engine.conclusions.length" class="empty-hint">
          当前未发现瓶颈或输入饥饿结论。
        </p>
        <article v-for="item in report.rule_engine.conclusions.slice(0, 4)" :key="item.conclusion_id">
          <strong>{{ item.machine_code }} / {{ item.risk_level }}</strong>
          <span>{{ item.title }}</span>
          <small>{{ item.summary }}</small>
        </article>
      </div>
    </aside>
  </section>
</template>
