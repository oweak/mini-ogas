<script setup lang="ts">
import type { AuditEvent, NodeSyncRecord } from './types'

defineProps<{
  auditEvents: AuditEvent[]
  nodeSyncRecords: NodeSyncRecord[]
  verificationSummary: (effect?: Record<string, unknown>) => string
}>()

defineEmits<{
  refresh: []
}>()

function countByPermission(events: AuditEvent[], keyword: string) {
  return events.filter((event) => event.permission.includes(keyword)).length
}
</script>

<template>
  <section class="content-grid logs-layout">
    <div class="panel log-archive-panel">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">审计归档</p>
          <h2>已处理问题与调度审批</h2>
        </div>
        <button class="secondary-action" type="button" @click="$emit('refresh')">
          刷新日志
        </button>
      </div>
      <p v-if="!auditEvents.length" class="empty-hint">暂无已归档处理记录</p>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>时间</th>
              <th>处理人</th>
              <th>权限</th>
              <th>处理事宜</th>
              <th>处理结果</th>
              <th>节点</th>
              <th>来源</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="event in auditEvents" :key="event.id">
              <td>{{ event.time }}</td>
              <td>
                <strong>{{ event.actor }}</strong>
                <small>{{ event.role }}</small>
              </td>
              <td>{{ event.permission }}</td>
              <td>
                <strong>{{ event.subject }}</strong>
                <small>{{ event.action }}</small>
              </td>
              <td>
                <span>{{ event.result }}</span>
                <small v-if="verificationSummary(event.effect)" class="verification-line">
                  {{ verificationSummary(event.effect) }}
                </small>
              </td>
              <td>{{ event.node_code || '-' }}</td>
              <td>
                <span class="state-pill" :class="event.status">{{ event.source }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <aside class="panel log-metrics-panel">
      <p class="eyebrow">归档摘要</p>
      <h2>处置闭环</h2>
      <dl class="log-metrics">
        <div>
          <dt>归档总数</dt>
          <dd>{{ auditEvents.length }}</dd>
        </div>
        <div>
          <dt>自动处置</dt>
          <dd>{{ countByPermission(auditEvents, '自动') }}</dd>
        </div>
        <div>
          <dt>人工审批</dt>
          <dd>{{ countByPermission(auditEvents, '人工') + countByPermission(auditEvents, '审批') }}</dd>
        </div>
        <div>
          <dt>节点补传</dt>
          <dd>{{ auditEvents.filter((event) => event.source === 'node-sync').length }}</dd>
        </div>
      </dl>
      <ol class="log-timeline">
        <li v-for="event in auditEvents.slice(0, 5)" :key="`timeline-${event.id}`">
          <time>{{ event.time }}</time>
          <strong>{{ event.action }}</strong>
          <span>{{ event.result }}</span>
        </li>
      </ol>
      <div v-if="nodeSyncRecords.length" class="node-sync-archive">
        <h3>子节点补传归档</h3>
        <article v-for="record in nodeSyncRecords.slice(0, 4)" :key="`${record.node_code}-${record.synced_at}`">
          <strong>{{ record.node_code }}</strong>
          <span>{{ record.record.production?.machine_code || '未标记设备' }} / {{ record.record.status || 'archived' }}</span>
          <small>{{ record.record.production?.active_order || '无工单' }} / 报警 {{ record.record.alarms?.length ?? 0 }} 条</small>
        </article>
      </div>
    </aside>
  </section>
</template>
