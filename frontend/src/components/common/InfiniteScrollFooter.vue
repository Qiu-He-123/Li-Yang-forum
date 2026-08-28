<script setup lang="ts">
/**
 * 无限滚动底部状态组件
 *
 * 三种状态：
 * - loading: 转圈 + "加载中..."
 * - error: "加载失败，点击重试"
 * - noMore: "—— 已显示全部内容 ——"
 * - hidden: 无内容时不显示
 */
defineProps<{
  loading: boolean
  error: boolean
  hasMore: boolean
  /** 列表是否为空（空列表时不显示底部状态） */
  hasItems: boolean
}>()

const emit = defineEmits<{
  retry: []
}>()
</script>

<template>
  <div v-if="hasItems" class="infinite-footer">
    <!-- 加载中 -->
    <div v-if="loading" class="infinite-loading">
      <span class="infinite-spinner" aria-hidden="true"></span>
      <span class="infinite-text">加载中...</span>
    </div>
    <!-- 加载失败，点击重试 -->
    <button v-else-if="error" class="infinite-error" type="button" @click="emit('retry')">
      加载失败，点击重试
    </button>
    <!-- 已显示全部 -->
    <div v-else-if="!hasMore" class="infinite-end">
      <span class="infinite-end-line"></span>
      <span class="infinite-end-text">已显示全部内容</span>
      <span class="infinite-end-line"></span>
    </div>
  </div>
</template>

<style scoped>
.infinite-footer {
  padding: 16px 0 8px;
  display: flex;
  justify-content: center;
  align-items: center;
}

.infinite-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-400, #8e8e93);
  font-size: 13px;
}

.infinite-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid var(--bg-200, #e5e5ea);
  border-top-color: var(--brand-500, #007aff);
  border-radius: 50%;
  animation: infinite-spin 0.8s linear infinite;
}

@keyframes infinite-spin {
  to {
    transform: rotate(360deg);
  }
}

.infinite-text {
  line-height: 1;
}

.infinite-error {
  background: none;
  border: none;
  color: var(--brand-500, #007aff);
  font-size: 13px;
  cursor: pointer;
  padding: 8px 16px;
  border-radius: 8px;
  transition: background 150ms ease;
  font-family: inherit;
}

.infinite-error:hover {
  background: var(--bg-100, #f2f2f7);
}

.infinite-end {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  max-width: 240px;
  color: var(--text-400, #8e8e93);
}

.infinite-end-line {
  flex: 1;
  height: 1px;
  background: var(--bg-200, #e5e5ea);
}

.infinite-end-text {
  font-size: 12px;
  white-space: nowrap;
  line-height: 1;
}
</style>
