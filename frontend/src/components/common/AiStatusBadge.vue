<script setup lang="ts">
import { computed } from 'vue'
import type { AiStatus } from '../../types/api'

/**
 * AI 审核状态徽标。
 * 在帖子标题旁/评论旁显示当前 AI 审核状态：
 * - pending: AI审核中（黄色）
 * - approved: 已通过（绿色，默认不显示避免噪音）
 * - rejected: 未通过（红色，鼠标悬停显示原因）
 * - manual_review: 人工复核中（橙色）
 */
const props = defineProps<{
  status?: AiStatus
  /** 是否在 approved 时也显示（默认不显示，避免列表噪音） */
  showApproved?: boolean
  /** 审核未通过原因（rejected 时显示） */
  rejectReason?: string | null
}>()

const visible = computed(() => {
  if (!props.status) return false
  if (props.status === 'approved') return props.showApproved ?? false
  return true
})

const config = computed(() => {
  switch (props.status) {
    case 'pending':
      return { text: '审核中', cls: 'bg-amber-50 text-amber-700 border-amber-200' }
    case 'rejected':
      return { text: '未通过', cls: 'bg-red-50 text-red-700 border-red-200' }
    case 'manual_review':
      return { text: '人工复核中', cls: 'bg-orange-50 text-orange-700 border-orange-200' }
    case 'approved':
      return { text: '已通过', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' }
    default:
      return { text: '', cls: '' }
  }
})

const tooltip = computed(() => {
  if (props.status === 'rejected' && props.rejectReason) {
    return `未通过原因：${props.rejectReason}（详情请看消息通知）`
  }
  if (props.status === 'pending') {
    return '内容审核中，其他人暂时看不到，审核通过后将正常显示'
  }
  return ''
})
</script>

<template>
  <span
    v-if="visible"
    class="inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-semibold leading-none cursor-help"
    :class="config.cls"
    :title="tooltip"
  >
    {{ config.text }}
  </span>
</template>
