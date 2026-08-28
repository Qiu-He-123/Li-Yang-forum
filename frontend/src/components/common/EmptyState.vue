<script setup lang="ts">
import { Icon } from '../native'

defineProps<{
  text?: string
  icon?: string
}>()
</script>

<template>
  <div class="empty-state">
    <div class="empty-illustration" aria-hidden="true">
      <div class="empty-circle">
        <span v-if="icon" class="empty-icon">
          <Icon :name="icon" :size="40" />
        </span>
      </div>
    </div>
    <p class="empty-text">{{ text ?? '暂无数据' }}</p>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 18px;
  padding: 80px 16px 60px;
  text-align: center;
}
.empty-illustration {
  position: relative;
  width: 120px;
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.empty-circle {
  width: 96px;
  height: 96px;
  border-radius: 50%;
  /* 规范：背景不在整页浅白里"消失"，给轻微底色对比 */
  background: #eaecf2;
  display: flex;
  align-items: center;
  justify-content: center;
  /* 规范：图标颜色 #868A99，不再浅灰 */
  color: #868A99;
}
.empty-illustration::before {
  content: '';
  position: absolute;
  width: 120px;
  height: 120px;
  border-radius: 50%;
  border: 2px dashed #dde0e9;
  animation: spin 25s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.empty-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.empty-text {
  margin: 0;
  font-size: 15px;
  /* 规范：主文字加深到 #505464，不要浅灰 */
  color: #505464;
  line-height: 1.5;
  font-weight: 500;
}
</style>
