<script setup lang="ts">
/**
 * 我创建的吧（申请记录列表）
 * 路由：/my/circles-applied
 *
 * 功能：
 * - 拉取当前用户申请过的吧列表
 * - 按状态分组展示：待审核 / 已通过 / 已拒绝
 * - 已拒绝的显示拒绝原因
 * - 已通过的卡片可点击进入圈子详情
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import EmptyState from '../components/common/EmptyState.vue'
import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import { listMyApplies } from '../api/circleApply'
import { useSessionStore } from '../stores/session'
import type { CircleApply } from '../types/api'

const router = useRouter()
const session = useSessionStore()

const applies = ref<CircleApply[]>([])
const loading = ref(false)

// 按状态分组
const pendingList = computed(() => applies.value.filter((a) => a.status === 'pending'))
const approvedList = computed(() => applies.value.filter((a) => a.status === 'approved'))
const rejectedList = computed(() => applies.value.filter((a) => a.status === 'rejected'))

function avatarGradient(id?: number | null) {
  const palettes = [
    'linear-gradient(135deg, #66abff, #007aff)',
    'linear-gradient(135deg, #34c759, #2e8dff)',
    'linear-gradient(135deg, #ff9500, #007aff)',
    'linear-gradient(135deg, #5856d6, #af52de)',
    'linear-gradient(135deg, #d1d1d6, #8e8e93)',
  ]
  if (id == null) return palettes[4]
  return palettes[id % 5]
}

function fmtTime(t: string | null): string {
  if (!t) return ''
  const d = new Date(t)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`
}

function formatCount(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, '') + 'w'
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k'
  return String(n)
}

async function load() {
  loading.value = true
  try {
    const { data } = await listMyApplies()
    applies.value = data.data || []
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

function openCircle(item: CircleApply) {
  if (item.status !== 'approved') return
  router.push(`/circle/${item.slug}`)
}

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/')
}

onMounted(() => {
  if (!session.userId) {
    toast.info('请先登录')
    router.push('/')
    return
  }
  load()
})
</script>

<template>
  <main class="page-applies">
    <!-- 顶部固定栏 -->
    <header class="site-header" role="banner">
      <div class="header-inner">
        <div class="header-side header-side--left">
          <button class="icon-btn" type="button" aria-label="返回" @click="goBack">
            <Icon name="arrow-left" :size="20" />
          </button>
        </div>
        <h1 class="header-title">我创建的吧</h1>
        <div class="header-side header-side--right"></div>
      </div>
    </header>

    <!-- 主内容 -->
    <div class="page-container">
      <div v-if="loading" class="loading-tip">
        <Icon name="refresh" :size="20" />
        <span>加载中…</span>
      </div>

      <template v-else-if="applies.length">
        <!-- 待审核 -->
        <section v-if="pendingList.length" class="group-section">
          <h2 class="group-title">
            <span class="group-dot group-dot--pending" aria-hidden="true"></span>
            待审核
            <span class="group-count">{{ pendingList.length }}</span>
          </h2>
          <div class="card-list">
            <div
              v-for="item in pendingList"
              :key="item.id"
              class="apply-card"
            >
              <span
                class="apply-ic"
                :style="{ background: item.color || 'var(--brand-500)' }"
                aria-hidden="true"
              >
                <Icon :name="item.icon || 'sparkles'" :size="20" color="#fff" />
              </span>
              <div class="apply-info">
                <div class="apply-name">{{ item.name }}</div>
                <div class="apply-slug">/{{ item.slug }}</div>
                <p v-if="item.description" class="apply-desc">{{ item.description }}</p>
                <div class="apply-meta">
                  <span class="status-pill status-pending">审核中</span>
                  <span class="apply-time">申请于 {{ fmtTime(item.created_at) }}</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- 已通过 -->
        <section v-if="approvedList.length" class="group-section">
          <h2 class="group-title">
            <span class="group-dot group-dot--approved" aria-hidden="true"></span>
            已通过
            <span class="group-count">{{ approvedList.length }}</span>
          </h2>
          <div class="card-list">
            <button
              v-for="item in approvedList"
              :key="item.id"
              class="apply-card apply-card--clickable"
              type="button"
              @click="openCircle(item)"
            >
              <span
                class="apply-ic"
                :style="{ background: item.color || 'var(--brand-500)' }"
                aria-hidden="true"
              >
                <Icon :name="item.icon || 'sparkles'" :size="20" color="#fff" />
              </span>
              <div class="apply-info">
                <div class="apply-name">{{ item.name }}</div>
                <div class="apply-slug">/{{ item.slug }}</div>
                <p v-if="item.description" class="apply-desc">{{ item.description }}</p>
                <div class="apply-meta">
                  <span class="status-pill status-approved">已上线</span>
                  <span class="apply-time">{{ formatCount(item.member_count) }} 成员 · {{ formatCount(item.post_count) }} 帖子</span>
                </div>
              </div>
              <Icon name="chevron-right" :size="18" color="#c7c7cc" class="apply-arrow" />
            </button>
          </div>
        </section>

        <!-- 已拒绝 -->
        <section v-if="rejectedList.length" class="group-section">
          <h2 class="group-title">
            <span class="group-dot group-dot--rejected" aria-hidden="true"></span>
            已拒绝
            <span class="group-count">{{ rejectedList.length }}</span>
          </h2>
          <div class="card-list">
            <div
              v-for="item in rejectedList"
              :key="item.id"
              class="apply-card apply-card--rejected"
            >
              <span
                class="apply-ic"
                :style="{ background: avatarGradient(item.id) }"
                aria-hidden="true"
              >
                <Icon name="x" :size="20" color="#fff" />
              </span>
              <div class="apply-info">
                <div class="apply-name">{{ item.name }}</div>
                <div class="apply-slug">/{{ item.slug }}</div>
                <div class="apply-meta">
                  <span class="status-pill status-rejected">已拒绝</span>
                  <span class="apply-time">申请于 {{ fmtTime(item.created_at) }}</span>
                </div>
                <div v-if="item.reject_reason" class="reject-reason">
                  <Icon name="circle-alert" :size="13" />
                  <span>{{ item.reject_reason }}</span>
                </div>
              </div>
            </div>
          </div>
        </section>
      </template>

      <EmptyState v-else text="还没有创建过吧，去圈子页点击右上角 + 申请创建吧" />
    </div>
  </main>
</template>

<style scoped>
.page-applies {
  min-height: 100vh;
  background: var(--bg-100);
  padding-top: 56px;
  padding-bottom: calc(56px + env(safe-area-inset-bottom));
  color: var(--text-800);
}

/* 顶部固定栏 */
.site-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  height: 56px;
  background: color-mix(in srgb, var(--bg-50) 88%, transparent);
  -webkit-backdrop-filter: blur(20px);
  backdrop-filter: blur(20px);
  border-bottom: 0.5px solid var(--bg-300);
}
.header-inner {
  max-width: 720px;
  margin: 0 auto;
  height: 100%;
  padding: 0 12px;
  display: flex;
  align-items: center;
  gap: 8px;
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
  flex: 0 1 auto;
  min-width: 0;
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  color: var(--text-800);
  letter-spacing: -0.01em;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  color: var(--text-700, var(--text-600));
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 0;
  transition: background 150ms var(--ease-apple), color 150ms var(--ease-apple);
  flex-shrink: 0;
}
.icon-btn:hover {
  background: var(--bg-100);
  color: var(--text-800);
}

.page-container {
  max-width: 720px;
  margin: 0 auto;
  padding: 16px 16px 24px;
}

.loading-tip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 16px;
  color: var(--text-500);
  font-size: 14px;
}
.loading-tip :deep(svg) {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0); }
  to { transform: rotate(360deg); }
}

/* 分组 */
.group-section {
  margin-bottom: 24px;
}
.group-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 12px;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-800);
  letter-spacing: -0.01em;
}
.group-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.group-dot--pending { background: #ff9500; }
.group-dot--approved { background: #34c759; }
.group-dot--rejected { background: #ff3b30; }
.group-count {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-400);
  background: var(--bg-200);
  padding: 1px 7px;
  border-radius: 999px;
}

.card-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* 申请卡片 */
.apply-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px;
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  border: none;
  text-align: left;
  width: 100%;
  font-family: inherit;
}
.apply-card--clickable {
  cursor: pointer;
  transition: box-shadow 150ms var(--ease-apple), transform 150ms var(--ease-apple);
}
.apply-card--clickable:hover {
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}
.apply-card--clickable:active {
  transform: translateY(0);
}
.apply-card--rejected {
  opacity: 0.85;
}

.apply-ic {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.apply-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.apply-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-800);
  line-height: 1.2;
}
.apply-slug {
  font-size: 12px;
  color: var(--text-400);
  line-height: 1.2;
}
.apply-desc {
  margin: 2px 0 0;
  font-size: 12.5px;
  color: var(--text-500);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}
.apply-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  flex-wrap: wrap;
}
.status-pill {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
}
.status-pending {
  color: #ff9500;
  background: rgba(255, 149, 0, 0.12);
}
.status-approved {
  color: #34c759;
  background: rgba(52, 199, 89, 0.12);
}
.status-rejected {
  color: #ff3b30;
  background: rgba(255, 59, 48, 0.12);
}
.apply-time {
  font-size: 11.5px;
  color: var(--text-400);
}

.reject-reason {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 6px;
  padding: 8px 10px;
  font-size: 12px;
  color: #ff3b30;
  background: rgba(255, 59, 48, 0.08);
  border-radius: 8px;
  line-height: 1.4;
}
.reject-reason :deep(svg) {
  flex-shrink: 0;
  margin-top: 2px;
}

.apply-arrow {
  flex-shrink: 0;
  align-self: center;
}

/* 响应式 — Mobile */
@media (max-width: 768px) {
  .page-applies {
    padding-top: 48px;
    padding-bottom: calc(52px + env(safe-area-inset-bottom));
  }
  .site-header { height: 48px; }
  .header-inner { padding: 0 10px; gap: 6px; }
  .header-title { font-size: 16px; }
  .icon-btn { width: 34px; height: 34px; }
  .page-container { padding: 12px 12px 20px; }
  .group-section { margin-bottom: 18px; }
  .group-title { font-size: 14px; margin-bottom: 10px; }
  .apply-card { padding: 12px; gap: 10px; }
  .apply-ic { width: 40px; height: 40px; border-radius: 10px; }
  .apply-name { font-size: 14px; }
  .apply-slug { font-size: 11.5px; }
  .apply-desc { font-size: 12px; }
}
</style>
