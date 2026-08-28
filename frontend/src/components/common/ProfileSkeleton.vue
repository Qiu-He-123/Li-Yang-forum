<script setup lang="ts">
/**
 * 个人主页骨架屏（iOS 风格 shimmer）。
 * 用于 UserHome 和 UserPostsList 首次加载。
 */
</script>

<template>
  <div class="profile-skeleton" aria-hidden="true">
    <!-- Hero 区 -->
    <div class="sk-hero">
      <div class="sk-hero-bar">
        <div class="sk-icon sk-shimmer"></div>
        <div class="sk-hero-name sk-shimmer"></div>
        <div class="sk-icon sk-shimmer"></div>
      </div>
      <div class="sk-hero-body">
        <div class="sk-avatar sk-shimmer"></div>
        <div class="sk-name sk-shimmer"></div>
        <div class="sk-bio sk-shimmer"></div>
        <div class="sk-bio sk-bio--short sk-shimmer"></div>
        <div class="sk-stats">
          <div class="sk-stat sk-shimmer"></div>
          <div class="sk-stat sk-shimmer"></div>
          <div class="sk-stat sk-shimmer"></div>
        </div>
      </div>
    </div>
    <!-- 功能区 -->
    <div class="sk-funcs">
      <div v-for="i in 6" :key="i" class="sk-func-item">
        <div class="sk-func-icon sk-shimmer"></div>
        <div class="sk-func-label sk-shimmer"></div>
      </div>
    </div>
    <!-- Tab 区 -->
    <div class="sk-tabs">
      <div class="sk-tab sk-shimmer"></div>
      <div class="sk-tab sk-shimmer"></div>
      <div class="sk-tab sk-shimmer"></div>
    </div>
    <!-- 帖子列表 -->
    <div class="sk-posts">
      <div v-for="i in 4" :key="i" class="sk-post-card">
        <div v-if="i % 2" class="sk-post-img sk-shimmer"></div>
        <div class="sk-post-body">
          <div class="sk-post-line sk-shimmer"></div>
          <div class="sk-post-line sk-post-line--short sk-shimmer"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.profile-skeleton { min-height: 100vh; background: var(--bg-100); }

.sk-hero { background: var(--bg-50); }
.sk-hero-bar {
  height: 52px; display: flex; align-items: center; justify-content: space-between;
  padding: 0 16px; padding-top: env(safe-area-inset-top);
}
.sk-icon { width: 32px; height: 32px; border-radius: 50%; }
.sk-hero-name { width: 80px; height: 18px; border-radius: 4px; }
.sk-hero-body { padding: 8px 20px 24px; display: flex; flex-direction: column; align-items: center; gap: 10px; }
.sk-avatar { width: 72px; height: 72px; border-radius: 50%; }
.sk-name { width: 120px; height: 20px; border-radius: 4px; }
.sk-bio { width: 80%; height: 14px; border-radius: 4px; }
.sk-bio--short { width: 50%; }
.sk-stats { display: flex; gap: 32px; margin-top: 8px; }
.sk-stat { width: 56px; height: 32px; border-radius: 6px; }

.sk-funcs {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px;
  background: var(--bg-200); margin: 10px 0;
}
.sk-func-item { background: var(--bg-50); padding: 18px 0; display: flex; flex-direction: column; align-items: center; gap: 8px; }
.sk-func-icon { width: 36px; height: 36px; border-radius: 10px; }
.sk-func-label { width: 52px; height: 12px; border-radius: 4px; }

.sk-tabs { display: flex; gap: 0; background: var(--bg-50); padding: 0 16px; border-bottom: 1px solid var(--bg-200); }
.sk-tab { width: 80px; height: 36px; margin-right: 20px; border-radius: 4px; }

.sk-posts { padding: 10px 12px; display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.sk-post-card { background: var(--bg-50); border-radius: var(--radius-md); overflow: hidden; }
.sk-post-img { width: 100%; aspect-ratio: 1; }
.sk-post-body { padding: 10px; }
.sk-post-line { height: 14px; border-radius: 4px; margin-bottom: 6px; }
.sk-post-line--short { width: 60%; }

@media (max-width: 768px) {
  .sk-hero-body { padding: 8px 16px 20px; }
  .sk-avatar { width: 60px; height: 60px; }
  .sk-posts { grid-template-columns: 1fr 1fr; gap: 8px; }
}
</style>
