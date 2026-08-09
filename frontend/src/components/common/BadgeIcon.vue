<script setup lang="ts">
/**
 * 徽章图标（勋章展示）
 *
 * - 图标字段为 emoji（如 🏅）时直接渲染文字
 * - 图标字段为 http(s) 图片 URL 时渲染 img（后台上传的压缩图标）
 * - 鼠标悬浮显示徽章名称
 */
import { computed } from 'vue'
import type { Badge } from '../../types/api'

const props = withDefaults(
  defineProps<{
    badge?: Badge | { icon: string; name?: string } | null
    /** 图标显示尺寸（px），默认 16 */
    size?: number
  }>(),
  { badge: null, size: 16 },
)

const icon = computed(() => props.badge?.icon || '')
const name = computed(() => props.badge?.name || '')
const isImage = computed(() => /^https?:\/\//i.test(icon.value))
</script>

<template>
  <span
    v-if="badge && icon"
    class="badge-icon"
    :title="name || '徽章'"
    :style="{ width: `${size}px`, height: `${size}px`, fontSize: `${size}px` }"
  >
    <img v-if="isImage" :src="icon" :alt="name || '徽章'" :style="{ width: `${size}px`, height: `${size}px` }" />
    <template v-else>{{ icon }}</template>
  </span>
</template>

<style scoped>
.badge-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  vertical-align: -0.15em;
  line-height: 1;
}
.badge-icon img {
  border-radius: 50%;
  object-fit: contain;
  display: block;
}
</style>
