<script setup lang="ts">
import type { DispatchPlan, DisplayedWorkOrder } from './types'

defineProps<{
  orders: DisplayedWorkOrder[]
  dispatchPlan: DispatchPlan | null
  dispatchPanelTitle: string
  dispatchApprovalLabel: string
  dispatchAwaitingApproval: boolean
  dispatchConfirmCode: string
  dispatchFeedback: string
  dispatchFeedbackKind: 'info' | 'success' | 'error'
  dispatchLoading: 'recalculate' | 'approve' | null
  workOrderStatusLabel: Record<DisplayedWorkOrder['status'], string>
}>()

defineEmits<{
  recalculate: []
  approve: []
  updateConfirmCode: [value: string]
}>()
</script>

<template>
  <section class="content-grid order-layout">
    <div class="panel">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">调度队列</p>
          <h2>工单与工艺路线</h2>
        </div>
        <button class="secondary-action" type="button" :disabled="dispatchLoading !== null" @click="$emit('recalculate')">
          {{ dispatchLoading === 'recalculate' ? '计算中...' : '重新计算计划' }}
        </button>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>工单</th>
              <th>产品</th>
              <th>工艺路线</th>
              <th>优先级</th>
              <th>进度</th>
              <th>截止</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="order in orders" :key="order.id">
              <td>{{ order.id }}</td>
              <td>{{ order.product }}</td>
              <td>
                <span class="route">{{ order.route.join(' -> ') }}</span>
              </td>
              <td>
                <span class="priority">{{ order.priority }}</span>
              </td>
              <td>
                <div class="progress-cell">
                  <span>{{ order.completed === null ? '未上报' : `${order.completed}/${order.quantity}` }}</span>
                  <meter v-if="order.completed !== null" :value="order.completed" :max="order.quantity"></meter>
                </div>
              </td>
              <td>{{ order.due }}</td>
              <td>
                <span class="state-pill" :class="order.status">
                  {{ workOrderStatusLabel[order.status] }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <aside class="panel dispatch-panel">
      <p class="eyebrow">建议动作</p>
      <h2>{{ dispatchPanelTitle }}</h2>
      <p>{{ dispatchPlan?.summary ?? '尚未评估调度状态。点击重新计算计划后，系统会根据受阻工单、节点状态和可用产能生成建议。' }}</p>
      <div class="decision-stack">
        <span>状态：{{ dispatchPlan?.status ?? '待重新计算' }}</span>
        <span>约束：{{ dispatchPlan?.risk ?? '等待调度引擎评估节点心跳与工单状态' }}</span>
        <span v-if="dispatchPlan?.command_id">命令：#{{ dispatchPlan.command_id }}</span>
        <span v-if="dispatchPlan?.target_rate !== undefined">
          目标速率：{{ dispatchPlan.target_rate }} {{ dispatchPlan.rate_unit ?? 'parts_per_minute' }}
        </span>
        <span v-if="dispatchPlan?.verification_status">验证：{{ dispatchPlan.verification_status }}</span>
        <span>{{ dispatchApprovalLabel }}</span>
      </div>
      <ol v-if="dispatchPlan?.steps?.length" class="dispatch-steps">
        <li v-for="step in dispatchPlan.steps" :key="step">{{ step }}</li>
      </ol>
      <div v-if="dispatchAwaitingApproval" class="confirmation-box">
        <label>
          <span>确认码</span>
          <input
            :value="dispatchConfirmCode"
            :placeholder="dispatchPlan?.confirmation_code_hint ?? 'CONFIRM'"
            @input="$emit('updateConfirmCode', ($event.target as HTMLInputElement).value)"
          />
        </label>
      </div>
      <p v-if="dispatchFeedback" class="alarm-feedback" :class="{ error: dispatchFeedbackKind === 'error' }">
        {{ dispatchFeedback }}
      </p>
      <button
        v-if="dispatchAwaitingApproval"
        class="primary-action"
        type="button"
        :disabled="dispatchLoading !== null"
        @click="$emit('approve')"
      >
        {{ dispatchLoading === 'approve' ? '批准中...' : '批准调度变更' }}
      </button>
    </aside>
  </section>
</template>
