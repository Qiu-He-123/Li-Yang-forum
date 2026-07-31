<script setup lang="ts">
import { Icon } from '../native'

defineProps<{
  text?: string
  icon?: string
}>()
</script>

<template>
  <div class="empty-state">
    <span v-if="icon" class="empty-icon" aria-hidden="true">
      <Icon :name="icon" :size="36" />
    </span>
    <p class="empty-text">{{ text ?? '暂无数据' }}</p>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 40px 16px;
  text-align: center;
}
.empty-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: var(--bg-100);
  color: var(--text-300);
}
.empty-text {
  margin: 0;
  font-size: 14px;
  color: var(--text-400);
  line-height: 1.5;
}
</style>
