<script setup lang="ts">
/**
 * 帖子详情骨架屏（iOS 风格 shimmer）。
 */
</script>

<template>
  <div class="detail-skeleton" aria-hidden="true">
    <!-- 顶部栏 -->
    <div class="sk-header">
      <div class="sk-header-icon sk-shimmer"></div>
      <div class="sk-header-title sk-shimmer"></div>
      <div class="sk-header-icon sk-shimmer"></div>
    </div>
    <div class="sk-container">
      <!-- 作者行 -->
      <div class="sk-author">
        <div class="sk-author-avatar sk-shimmer"></div>
        <div class="sk-author-info">
          <div class="sk-author-name sk-shimmer"></div>
          <div class="sk-author-time sk-shimmer"></div>
        </div>
      </div>
      <!-- 标题 -->
      <div class="sk-title sk-shimmer"></div>
      <div class="sk-title sk-title--short sk-shimmer"></div>
      <!-- 正文 -->
      <div class="sk-body">
        <div class="sk-body-line sk-shimmer"></div>
        <div class="sk-body-line sk-shimmer"></div>
        <div class="sk-body-line sk-shimmer"></div>
        <div class="sk-body-line sk-body-line--short sk-shimmer"></div>
      </div>
      <!-- 互动栏：4 个按钮（点赞/评论/分享/收藏），对齐真实布局 -->
      <div class="sk-actions">
        <div class="sk-action sk-shimmer"></div>
        <div class="sk-action sk-shimmer"></div>
        <div class="sk-action sk-shimmer"></div>
        <div class="sk-action sk-shimmer"></div>
      </div>
      <!-- 评论 -->
      <div class="sk-comments">
        <div class="sk-comment-title sk-shimmer"></div>
        <div class="sk-comment" v-for="i in 3" :key="i">
          <div class="sk-comment-avatar sk-shimmer"></div>
          <div class="sk-comment-body">
            <div class="sk-comment-line sk-shimmer"></div>
            <div class="sk-comment-line sk-comment-line--short sk-shimmer"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail-skeleton { min-height: 100vh; background: var(--bg-100); }
.sk-header {
  position: sticky; top: 0; z-index: 50;
  height: 52px; display: flex; align-items: center; justify-content: space-between;
  padding: 0 16px; padding-top: env(safe-area-inset-top);
  background: rgba(255,255,255,0.95); backdrop-filter: blur(20px); border-bottom: 0.5px solid var(--bg-300);
}
.sk-header-icon { width: 32px; height: 32px; border-radius: 50%; }
.sk-header-title { width: 100px; height: 18px; border-radius: 4px; }
.sk-container { max-width: 720px; margin: 0 auto; padding: 16px; }
.sk-author { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.sk-author-avatar { width: 44px; height: 44px; border-radius: 50%; }
.sk-author-info { flex: 1; display: flex; flex-direction: column; gap: 6px; }
.sk-author-name { width: 100px; height: 16px; border-radius: 4px; }
.sk-author-time { width: 60px; height: 12px; border-radius: 4px; }
.sk-title { height: 22px; border-radius: 4px; margin-bottom: 10px; }
.sk-title--short { width: 60%; }
.sk-body { margin-bottom: 16px; }
.sk-body-line { height: 15px; border-radius: 4px; margin-bottom: 8px; }
.sk-body-line--short { width: 50%; }
.sk-img { width: 100%; aspect-ratio: 4/3; border-radius: var(--radius-md); margin-bottom: 16px; }
.sk-actions { display: flex; gap: 16px; padding: 12px 0; border-top: 1px solid var(--bg-200); border-bottom: 1px solid var(--bg-200); margin-bottom: 20px; }
.sk-action { width: 56px; height: 32px; border-radius: 8px; }
.sk-comments { display: flex; flex-direction: column; gap: 16px; }
.sk-comment-title { width: 100px; height: 18px; border-radius: 4px; margin-bottom: 4px; }
.sk-comment { display: flex; gap: 10px; }
.sk-comment-avatar { width: 36px; height: 36px; border-radius: 50%; flex-shrink: 0; }
.sk-comment-body { flex: 1; display: flex; flex-direction: column; gap: 6px; }
.sk-comment-line { height: 13px; border-radius: 4px; }
.sk-comment-line--short { width: 70%; }
</style>
