<template>
  <div class="circle-detail-skeleton" aria-hidden="true">
    <!-- 顶部栏 -->
    <header class="sk-header">
      <div class="sk-header-btn sk-shimmer"></div>
      <div class="sk-header-title sk-shimmer"></div>
      <div class="sk-header-btn sk-shimmer"></div>
    </header>

    <div class="sk-container">
      <!-- 圈子信息卡骨架 -->
      <section class="sk-bar-card">
        <div class="sk-bar-head">
          <div class="sk-bar-avatar sk-shimmer"></div>
          <div class="sk-bar-info">
            <div class="sk-bar-name sk-shimmer"></div>
            <div class="sk-bar-desc sk-shimmer"></div>
            <div class="sk-bar-desc sk-shimmer sk-bar-desc--short"></div>
          </div>
          <div class="sk-follow-btn sk-shimmer"></div>
        </div>
        <div class="sk-bar-stats">
          <div v-for="i in 3" :key="'stat-' + i" class="sk-bar-stat">
            <div class="sk-stat-icon sk-shimmer"></div>
            <div class="sk-stat-text">
              <div class="sk-stat-label sk-shimmer"></div>
              <div class="sk-stat-value sk-shimmer"></div>
            </div>
          </div>
        </div>
      </section>

      <!-- 分类 Tab 骨架 -->
      <div class="sk-cat-tabs">
        <div v-for="i in 4" :key="'tab-' + i" class="sk-cat-tab sk-shimmer"></div>
      </div>

      <!-- 帖子列表骨架 -->
      <div class="sk-post-list">
        <div v-for="i in 4" :key="'post-' + i" class="sk-post-item">
          <div class="sk-post-author-row">
            <div class="sk-avatar sk-shimmer"></div>
            <div class="sk-author-name sk-shimmer"></div>
            <div class="sk-post-time sk-shimmer"></div>
          </div>
          <div class="sk-post-title sk-shimmer"></div>
          <div class="sk-post-body sk-shimmer"></div>
          <div class="sk-post-body sk-shimmer sk-post-body--short"></div>
          <div class="sk-post-meta">
            <div class="sk-meta-item sk-shimmer"></div>
            <div class="sk-meta-item sk-shimmer"></div>
            <div class="sk-meta-item sk-shimmer"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.circle-detail-skeleton {
  min-height: 100vh;
  background: var(--background-100, #f5f5f7);
}

.sk-header {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--background-0, #ffffff);
  border-bottom: 1px solid var(--separator, #e5e5ea);
}
.sk-header-btn { width: 32px; height: 32px; border-radius: 50%; }
.sk-header-title { width: 120px; height: 18px; border-radius: 4px; }

.sk-container {
  max-width: 640px;
  margin: 0 auto;
  padding: 12px 16px;
}

/* 圈子信息卡 */
.sk-bar-card {
  background: var(--background-0, #ffffff);
  border-radius: 16px;
  padding: 20px 16px;
  margin-bottom: 12px;
}
.sk-bar-head {
  display: flex;
  align-items: center;
  gap: 12px;
}
.sk-bar-avatar { width: 56px; height: 56px; border-radius: 50%; flex-shrink: 0; }
.sk-bar-info { flex: 1; min-width: 0; }
.sk-bar-name { width: 140px; height: 20px; border-radius: 4px; margin-bottom: 8px; }
.sk-bar-desc { width: 100%; height: 14px; border-radius: 4px; margin-bottom: 6px; }
.sk-bar-desc--short { width: 60%; }
.sk-follow-btn { width: 72px; height: 32px; border-radius: 16px; flex-shrink: 0; }

.sk-bar-stats {
  display: flex;
  gap: 24px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--separator, #e5e5ea);
}
.sk-bar-stat { display: flex; align-items: center; gap: 6px; }
.sk-stat-icon { width: 16px; height: 16px; border-radius: 50%; }
.sk-stat-text { display: flex; flex-direction: column; gap: 4px; }
.sk-stat-label { width: 28px; height: 10px; border-radius: 3px; }
.sk-stat-value { width: 36px; height: 14px; border-radius: 3px; }

/* 分类 Tab */
.sk-cat-tabs {
  display: flex;
  gap: 8px;
  padding: 8px 0 12px;
}
.sk-cat-tab { width: 56px; height: 32px; border-radius: 8px; }

/* 帖子列表 */
.sk-post-list { display: flex; flex-direction: column; gap: 12px; }
.sk-post-item {
  background: var(--background-0, #ffffff);
  border-radius: 12px;
  padding: 16px;
}
.sk-post-author-row { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.sk-avatar { width: 24px; height: 24px; border-radius: 50%; }
.sk-author-name { width: 80px; height: 14px; border-radius: 3px; }
.sk-post-time { width: 40px; height: 12px; border-radius: 3px; }
.sk-post-title { width: 80%; height: 18px; border-radius: 4px; margin-bottom: 10px; }
.sk-post-body { width: 100%; height: 14px; border-radius: 3px; margin-bottom: 6px; }
.sk-post-body--short { width: 55%; }
.sk-post-meta { display: flex; gap: 16px; margin-top: 12px; }
.sk-meta-item { width: 48px; height: 24px; border-radius: 8px; }
</style>
