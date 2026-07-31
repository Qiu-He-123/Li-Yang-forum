<script setup lang="ts">
/**
 * 全部圈子列表页（路由：/circles/all）
 * - 顶部固定栏：返回 + 标题「全部圈子」
 * - 排序 Tab：热度排行 / 人数排行 / 名称排序
 * - 圈子列表（列表形式，非网格）：圆形图标 + 名称 + 简介 + 成员数 + 加入/已加入按钮
 * - 数据来自 circleStore，客户端排序，无服务端分页
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import EmptyState from '../components/common/EmptyState.vue'
import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import { useSessionStore } from '../stores/session'
import { useCircleStore } from '../stores/circle'
import type { Circle } from '../types/api'

const router = useRouter()
const session = useSessionStore()
const circleStore = useCircleStore()

type SortKey = 'heat' | 'members' | 'name'

const sortTabs: { key: SortKey; label: string }[] = [
  { key: 'heat', label: '热度排行' },
  { key: 'members', label: '人数排行' },
  { key: 'name', label: '名称排序' },
]

const sortKey = ref<SortKey>('heat')
const loading = ref(false)
const joiningSlug = ref<string | null>(null)

// 圈子图标与色调映射（与 CircleDiscover.vue 保持一致）
const circleMeta: Record<string, { icon: string; gradient: string }> = {
  confess: { icon: 'heart', gradient: 'linear-gradient(135deg, #ff6b9d, #af52de)' },
  lost: { icon: 'circle-question', gradient: 'linear-gradient(135deg, #66abff, #0064d6)' },
  market: { icon: 'tag', gradient: 'linear-gradient(135deg, #ff9500, #ff6b35)' },
  study: { icon: 'file', gradient: 'linear-gradient(135deg, #34c759, #007aff)' },
  food: { icon: 'map-pin', gradient: 'linear-gradient(135deg, #ffb347, #ff9500)' },
  game: { icon: 'star', gradient: 'linear-gradient(135deg, #5856d6, #af52de)' },
  photo: { icon: 'camera', gradient: 'linear-gradient(135deg, #34c759, #00c7be)' },
  club: { icon: 'star', gradient: 'linear-gradient(135deg, #af52de, #ff6b9d)' },
  sport: { icon: 'flame', gradient: 'linear-gradient(135deg, #007aff, #34c759)' },
  match: { icon: 'shuffle', gradient: 'linear-gradient(135deg, #ff9500, #ff6b35)' },
  treehole: { icon: 'lock', gradient: 'linear-gradient(135deg, #8e8e93, #48484a)' },
  qa: { icon: 'circle-question', gradient: 'linear-gradient(135deg, #66abff, #0064d6)' },
  flea: { icon: 'tag', gradient: 'linear-gradient(135deg, #34c759, #00c7be)' },
}

function getCircleMeta(slug: string) {
  return (
    circleMeta[slug] || {
      icon: 'sparkles',
      gradient: 'linear-gradient(135deg, #66abff, #007aff)',
    }
  )
}

function formatCount(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, '') + 'w'
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k'
  return String(n)
}

// 排序后的圈子列表
const sortedCircles = computed<Circle[]>(() => {
  const list = [...circleStore.circles]
  if (sortKey.value === 'name') {
    list.sort((a, b) => a.name.localeCompare(b.name, 'zh-Hans-CN'))
  } else {
    // heat 与 members 均按成员数降序
    list.sort((a, b) => b.member_count - a.member_count)
  }
  return list
})

function onSortChange(key: SortKey) {
  if (sortKey.value === key) return
  sortKey.value = key
}

function onBack() {
  if (window.history.length > 1) router.back()
  else router.push('/circles')
}

function openCircle(slug: string) {
  if (!slug) return
  router.push(`/circle/${slug}`)
}

async function onJoinCircle(e: Event, circle: Circle) {
  e.stopPropagation()
  e.preventDefault()
  if (!session.userId) {
    toast.info('请先登录')
    return
  }
  joiningSlug.value = circle.slug
  try {
    const joined = await circleStore.toggleJoin(circle)
    toast.success(joined ? '已加入' : '已退出')
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    joiningSlug.value = null
  }
}

onMounted(async () => {
  loading.value = true
  try {
    await circleStore.loadCircles(true)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main class="page-all-circles">
    <!-- ====== 顶部固定栏：返回 + 标题「全部圈子」 ====== -->
    <header class="site-header" role="banner">
      <div class="header-inner">
        <div class="header-side header-side--left">
          <button class="icon-btn" type="button" aria-label="返回" @click="onBack">
            <Icon name="arrow-left" :size="20" />
          </button>
        </div>
        <h1 class="header-title">全部圈子</h1>
        <div class="header-side header-side--right" aria-hidden="true"></div>
      </div>
    </header>

    <!-- ====== 主内容 ====== -->
    <div class="page-container">
      <!-- 排序 Tab -->
      <div class="sort-tabs" role="tablist" aria-label="圈子排序">
        <button
          v-for="tab in sortTabs"
          :key="tab.key"
          class="sort-tab"
          type="button"
          :class="{ 'is-active': sortKey === tab.key }"
          role="tab"
          :aria-selected="sortKey === tab.key"
          @click="onSortChange(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>

      <!-- 加载中 -->
      <div v-if="loading" class="state-tip">
        <Icon name="refresh" :size="20" />
        <span>加载中…</span>
      </div>

      <!-- 圈子列表 -->
      <div v-else-if="sortedCircles.length" class="circle-list">
        <article
          v-for="circle in sortedCircles"
          :key="'ac-' + circle.id"
          class="circle-row"
          @click="openCircle(circle.slug)"
        >
          <span
            class="circle-icon"
            :style="{ background: getCircleMeta(circle.slug).gradient }"
            aria-hidden="true"
          >
            <Icon :name="getCircleMeta(circle.slug).icon" :size="28" color="#fff" />
          </span>
          <div class="circle-info">
            <div class="circle-row-name">{{ circle.name }}</div>
            <p class="circle-row-desc">{{ circle.description || '暂无简介' }}</p>
            <div class="circle-row-meta">
              <span class="meta-item">
                <Icon name="users" :size="12" color="var(--text-400)" />
                {{ formatCount(circle.member_count) }} 成员
              </span>
              <span class="meta-item">
                <Icon name="file-text" :size="12" color="var(--text-400)" />
                {{ formatCount(circle.post_count) }} 帖子
              </span>
            </div>
          </div>
          <button
            class="join-btn"
            :class="{ 'is-joined': circle.is_joined }"
            type="button"
            :disabled="joiningSlug === circle.slug"
            @click="(e) => onJoinCircle(e, circle)"
          >
            {{ circle.is_joined ? '已加入' : '加入' }}
          </button>
        </article>
      </div>

      <!-- 空状态 -->
      <EmptyState v-else text="暂无圈子" />
    </div>
  </main>
</template>

<style scoped>
*, *::before, *::after { box-sizing: border-box; }

.page-all-circles {
  min-height: 100vh;
  background: var(--bg-100);
  padding-top: 56px;
  padding-bottom: calc(56px + env(safe-area-inset-bottom));
  color: var(--text-800);
  font-family: var(--font-sans, inherit);
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* ====== Header ====== */
.site-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  height: 56px;
  background: var(--bg-50);
  border-bottom: 0.5px solid var(--bg-300);
}
.header-inner {
  max-width: 1200px;
  margin: 0 auto;
  height: 100%;
  padding: 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.header-side {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
}
.header-side--left { justify-content: flex-start; }
.header-side--right { justify-content: flex-end; }
.header-title {
  flex: 0 0 auto;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-800);
  letter-spacing: -0.01em;
  text-align: center;
  white-space: nowrap;
  margin: 0;
}
.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  color: var(--text-600);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: background 150ms cubic-bezier(0.32, 0.72, 0, 1),
              color 150ms cubic-bezier(0.32, 0.72, 0, 1);
  flex-shrink: 0;
}
.icon-btn:hover {
  background: var(--bg-100);
  color: var(--text-800);
}

/* ====== Container ====== */
.page-container {
  max-width: 720px;
  margin: 0 auto;
  padding: 16px 16px calc(56px + env(safe-area-inset-bottom));
}

/* ====== Sort Tabs ====== */
.sort-tabs {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  padding: 0 2px;
  flex-wrap: wrap;
}
.sort-tab {
  padding: 6px 16px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-500);
  background: transparent;
  border: none;
  cursor: pointer;
  font-family: inherit;
  transition: color 150ms cubic-bezier(0.32, 0.72, 0, 1),
              background 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.sort-tab:hover { color: var(--text-800); }
.sort-tab.is-active {
  color: var(--brand-600);
  background: var(--brand-50);
  font-weight: 600;
}

/* ====== State tip ====== */
.state-tip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 0;
  color: var(--text-500);
  font-size: 13px;
}
.state-tip :deep(svg) {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0); }
  to { transform: rotate(360deg); }
}

/* ====== Circle List ====== */
.circle-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.circle-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  cursor: pointer;
  transition: transform 150ms cubic-bezier(0.32, 0.72, 0, 1),
              box-shadow 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.circle-row:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}
.circle-row:active {
  transform: scale(0.99);
}
.circle-icon {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-sm);
  flex-shrink: 0;
}
.circle-info {
  flex: 1;
  min-width: 0;
}
.circle-row-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-800);
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.circle-row-desc {
  margin: 2px 0 4px;
  font-size: 12.5px;
  color: var(--text-500);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}
.circle-row-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 11.5px;
  color: var(--text-400);
}
.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

/* ====== Join Button ====== */
.join-btn {
  flex-shrink: 0;
  padding: 6px 14px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  color: var(--bg-50);
  background: var(--brand-500);
  border: none;
  cursor: pointer;
  font-family: inherit;
  transition: background 150ms cubic-bezier(0.32, 0.72, 0, 1),
              color 150ms cubic-bezier(0.32, 0.72, 0, 1),
              transform 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.join-btn:hover:not(:disabled) { background: var(--brand-600); }
.join-btn:active:not(:disabled) { transform: scale(0.94); }
.join-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.join-btn.is-joined {
  background: var(--bg-200);
  color: var(--text-400);
}
.join-btn.is-joined:hover:not(:disabled) {
  background: var(--bg-300);
  color: var(--text-500);
}

/* ====== Responsive ====== */
@media (max-width: 768px) {
  .page-all-circles {
    padding-top: 48px;
    padding-bottom: calc(52px + env(safe-area-inset-bottom));
  }
  .site-header { height: 48px; }
  .header-inner { padding: 0 12px; gap: 8px; }
  .header-title { font-size: 17px; }
  .icon-btn { width: 34px; height: 34px; }
  .icon-btn :deep(svg) { width: 19px; height: 19px; }

  .page-container { padding: 12px 12px 24px; }

  .sort-tab { padding: 5px 13px; font-size: 12.5px; }

  .circle-row { padding: 12px; gap: 10px; }
  .circle-icon { width: 46px; height: 46px; }
  .circle-row-name { font-size: 14px; }
  .circle-row-desc { font-size: 12px; }
  .circle-row-meta { font-size: 11px; gap: 10px; }
  .join-btn { padding: 5px 12px; font-size: 11px; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
  }
}
</style>
