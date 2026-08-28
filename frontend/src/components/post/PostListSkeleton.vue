<script setup lang="ts">
/**
 * 帖子列表骨架屏（iOS 风格 shimmer 动画）。
 * 替代原"加载中..."文字提示，让用户在等待时看到内容结构，
 * 减少感知上的"卡顿感"（参考大厂 App 列表加载体验）。
 *
 * 用法：<PostListSkeleton :count="6" />
 */
withDefaults(defineProps<{ count?: number }>(), { count: 6 })
</script>

<template>
  <div class="skeleton-feed" aria-hidden="true">
    <div v-for="i in count" :key="i" class="sk-card" :class="{ 'sk-card--text': i % 3 === 0 }">
      <!-- 图片块（仅图片卡显示） -->
      <div v-if="i % 3 !== 0" class="sk-img shimmer"></div>
      <div class="sk-body">
        <!-- 顶部圈子标签 -->
        <div class="sk-row">
          <div class="sk-pill shimmer"></div>
        </div>
        <!-- 标题（2 行） -->
        <div class="sk-title shimmer"></div>
        <div class="sk-title sk-title--short shimmer"></div>
        <!-- 底部作者信息 -->
        <div class="sk-meta">
          <div class="sk-avatar shimmer"></div>
          <div class="sk-line shimmer"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.skeleton-feed {
  column-count: 2;
  column-gap: 14px;
}
@media (min-width: 769px) {
  .skeleton-feed { column-count: 3; column-gap: 16px; }
}
@media (min-width: 1100px) {
  .skeleton-feed { column-count: 4; }
}

.sk-card {
  display: block;
  width: 100%;
  break-inside: avoid;
  margin-bottom: 16px;
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-xs);
  min-width: 0;
}
.sk-card--text .sk-body { padding: 18px; }

.sk-img {
  width: 100%;
  min-height: 180px;
}
.sk-body { padding: 14px 16px 16px; }

.sk-row {
  display: flex;
  margin-bottom: 12px;
}
.sk-pill {
  width: 64px;
  height: 22px;
  border-radius: 999px;
}

.sk-title {
  height: 16px;
  border-radius: 4px;
  margin-bottom: 8px;
}
.sk-title--short {
  width: 60%;
}

.sk-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
}
.sk-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  flex-shrink: 0;
}
.sk-line {
  width: 80px;
  height: 12px;
  border-radius: 4px;
}

/* iOS 风格 shimmer：使用全局 .sk-shimmer 类 */
.shimmer {
  background: linear-gradient(
    90deg,
    var(--bg-200) 0%,
    var(--bg-300) 50%,
    var(--bg-200) 100%
  );
  background-size: 200% 100%;
  animation: sk-shimmer 1.4s ease-in-out infinite;
}
@media (prefers-reduced-motion: reduce) {
  .shimmer { animation: none; }
}

/* 移动端适配 */
@media (max-width: 768px) {
  .skeleton-feed { column-gap: 10px; }
  .sk-card { margin-bottom: 12px; border-radius: calc(var(--radius-lg) * 0.8); }
  .sk-img { min-height: 140px; }
  .sk-body { padding: 12px 14px 14px; }
  .sk-card--text .sk-body { padding: 14px; }
  .sk-avatar { width: 24px; height: 24px; }
}
</style>
