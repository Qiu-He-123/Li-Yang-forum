<script setup lang="ts">
/**
 * 漂流瓶页面骨架屏（iOS 风格 shimmer）。
 */
</script>

<template>
  <div class="bottle-skeleton" aria-hidden="true">
    <div class="sk-header">
      <div class="sk-header-icon sk-shimmer"></div>
      <div class="sk-header-title sk-shimmer"></div>
      <div class="sk-header-icon sk-shimmer"></div>
    </div>
    <div class="sk-stats">
      <div v-for="i in 4" :key="i" class="sk-stat-card">
        <div class="sk-stat-num sk-shimmer"></div>
        <div class="sk-stat-label sk-shimmer"></div>
      </div>
    </div>
    <div class="sk-tab-area">
      <div class="sk-tab sk-shimmer"></div>
      <div class="sk-tab sk-shimmer"></div>
      <div class="sk-tab sk-shimmer"></div>
    </div>
    <div class="sk-content">
      <div class="sk-line sk-shimmer"></div>
      <div class="sk-line sk-shimmer"></div>
      <div class="sk-line sk-line--short sk-shimmer"></div>
      <div class="sk-btn sk-shimmer"></div>
    </div>
  </div>
</template>

<style scoped>
.bottle-skeleton { min-height: 100vh; background: var(--bg-100); }
.sk-header {
  height: 52px; display: flex; align-items: center; justify-content: space-between;
  padding: 0 16px; padding-top: env(safe-area-inset-top);
  background: var(--bg-50); border-bottom: 0.5px solid var(--bg-300);
}
.sk-header-icon { width: 32px; height: 32px; border-radius: 50%; }
.sk-header-title { width: 100px; height: 18px; border-radius: 4px; }
.sk-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; padding: 12px; }
.sk-stat-card { background: var(--bg-50); border-radius: var(--radius-md); padding: 12px 8px; display: flex; flex-direction: column; align-items: center; gap: 6px; }
.sk-stat-num { width: 40px; height: 20px; border-radius: 4px; }
.sk-stat-label { width: 48px; height: 10px; border-radius: 4px; }
.sk-tab-area { display: flex; gap: 0; padding: 0 16px; background: var(--bg-50); border-bottom: 1px solid var(--bg-200); }
.sk-tab { width: 80px; height: 36px; margin-right: 16px; border-radius: 4px; }
.sk-content { padding: 24px 20px; display: flex; flex-direction: column; gap: 12px; }
.sk-line { height: 15px; border-radius: 4px; }
.sk-line--short { width: 60%; }
.sk-btn { width: 160px; height: 44px; border-radius: 22px; margin-top: 12px; align-self: center; }
</style>
