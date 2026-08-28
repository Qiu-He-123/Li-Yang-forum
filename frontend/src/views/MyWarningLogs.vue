<script setup lang="ts">
/**
 * 我的警告值变动记录页
 *
 * - 顶部展示当前警告值状态（与个人主页卡片保持一致）
 * - 下方分页展示所有警告值变动记录（违规/签到/发帖/评论/管理员调整等）
 * - 封号用户也可访问本页（无 requiresAuth 限制？实际需要登录态，但允许 ban 用户访问）
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import AppHeader from '../components/header/AppHeader.vue'
import EmptyState from '../components/common/EmptyState.vue'
import Pagination from '../components/common/Pagination.vue'
import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import {
  fetchMyWarningLogs,
  fetchMyWarningStatus,
  type WarningLogItem,
  type WarningStatus,
} from '../api/user'

const router = useRouter()

const status = ref<WarningStatus | null>(null)
const logs = ref<WarningLogItem[]>([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

const warningPercent = computed(() => {
  if (!status.value) return 0
  const { score, perm_ban_threshold } = status.value
  return Math.min(100, Math.round((score / perm_ban_threshold) * 100))
})

const warningLevelMeta = computed(() => {
  if (!status.value) return null
  const level = status.value.level
  const map = {
    normal: { text: '状态良好', color: '#34c759', bg: '#e8f9ee', icon: 'check-circle' },
    warn: { text: '已警告', color: '#ff9500', bg: '#fff4e0', icon: 'triangle-alert' },
    ban: { text: '已封号', color: '#ff3b30', bg: '#ffe5e3', icon: 'circle-alert' },
    danger: { text: '危险', color: '#ff3b30', bg: '#ffe5e3', icon: 'circle-alert' },
  } as const
  return map[level] || map.normal
})

const sourceMeta: Record<string, { text: string; color: string; bg: string; icon: string }> = {
  violation: { text: '内容违规', color: '#ff3b30', bg: '#ffe5e3', icon: 'triangle-alert' },
  checkin: { text: '每日签到', color: '#34c759', bg: '#e8f9ee', icon: 'gift' },
  post: { text: '帖子审核通过', color: '#34c759', bg: '#e8f9ee', icon: 'check-circle' },
  comment: { text: '评论审核通过', color: '#34c759', bg: '#e8f9ee', icon: 'check-circle' },
  admin_adjust: { text: '管理员调整', color: '#ff9500', bg: '#fff4e0', icon: 'shield' },
  system: { text: '系统', color: '#8e8e93', bg: '#f0f0f0', icon: 'circle-alert' },
}

function getSourceMeta(source: string) {
  return sourceMeta[source] || sourceMeta.system
}

function fmtTime(t: string | null): string {
  if (!t) return ''
  return t.replace('T', ' ').slice(0, 19)
}

function fmtDelta(delta: number): string {
  if (delta > 0) return `+${delta}`
  return `${delta}`
}

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/')
}

async function loadStatus() {
  try {
    const { data } = await fetchMyWarningStatus()
    status.value = data.data
  } catch (err) {
    toast.error((err as Error).message)
  }
}

async function loadLogs() {
  loading.value = true
  try {
    const { data } = await fetchMyWarningLogs({ page: page.value, page_size: pageSize.value })
    logs.value = data.data.items || []
    total.value = data.data.total || 0
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

function onPageChange(p: number) {
  page.value = p
  loadLogs()
}

onMounted(() => {
  loadStatus()
  loadLogs()
})
</script>

<template>
  <main class="page-warning-logs">
    <AppHeader />

    <div class="container">
      <!-- 返回按钮 + 标题 -->
      <div class="page-head">
        <button class="icon-btn" type="button" @click="goBack">
          <Icon name="arrow-left" :size="18" />
        </button>
        <h1 class="page-title">警告值变动记录</h1>
        <span class="icon-placeholder" />
      </div>

      <!-- 当前警告值状态卡片 -->
      <section v-if="status" class="status-card" :style="{ background: warningLevelMeta?.bg }">
        <div class="status-head">
          <div class="status-title-wrap">
            <span class="status-ic" :style="{ color: warningLevelMeta?.color }">
              <Icon :name="warningLevelMeta?.icon || 'check-circle'" :size="18" />
            </span>
            <span class="status-title">当前警告值</span>
            <span
              class="status-level-pill"
              :style="{
                color: warningLevelMeta?.color,
                background: '#fff',
                border: `1px solid ${warningLevelMeta?.color}`,
              }"
            >
              {{ warningLevelMeta?.text }}
            </span>
          </div>
        </div>

        <div class="status-score-row">
          <div class="status-score-num" :style="{ color: warningLevelMeta?.color }">
            {{ status.score }}
          </div>
          <div class="status-score-divider">/</div>
          <div class="status-score-max">{{ status.perm_ban_threshold }}</div>
        </div>

        <div class="status-progress">
          <div
            class="status-progress-bar"
            :style="{ width: `${warningPercent}%`, background: warningLevelMeta?.color }"
          />
        </div>

        <div v-if="status.score < status.perm_ban_threshold" class="status-hint">
          <Icon name="triangle-alert" :size="13" :color="warningLevelMeta?.color" />
          <span>
            达到 <b>{{ status.next_threshold }}</b> 将触发：<b>{{ status.next_action }}</b>
          </span>
        </div>

        <div class="status-reduce-tip">
          <Icon name="sparkles" :size="13" color="#34c759" />
          <span>{{ status.reduce_hint }}</span>
        </div>
      </section>

      <!-- 记录列表 -->
      <section class="logs-section">
        <div class="logs-section-head">
          <h2 class="logs-section-title">变动记录</h2>
          <span class="logs-section-count">共 {{ total }} 条</span>
        </div>

        <div v-if="loading" class="loading-tip">
          <Icon name="refresh" :size="20" />
          <span>加载中…</span>
        </div>

        <div v-else-if="logs.length" class="logs-list">
          <article v-for="log in logs" :key="log.id" class="log-item">
            <div class="log-left">
              <span
                class="log-source-pill"
                :style="{
                  color: getSourceMeta(log.source).color,
                  background: getSourceMeta(log.source).bg,
                }"
              >
                <Icon :name="getSourceMeta(log.source).icon" :size="12" />
                {{ getSourceMeta(log.source).text }}
              </span>
            </div>
            <div class="log-body">
              <p class="log-reason">{{ log.reason }}</p>
              <div class="log-meta">
                <span class="log-time">{{ fmtTime(log.created_at) }}</span>
                <span v-if="log.related_type" class="log-related">
                  · 关联{{ log.related_type === 'post' ? '帖子' : '评论' }} #{{ log.related_id }}
                </span>
              </div>
            </div>
            <div class="log-right">
              <div
                class="log-delta"
                :class="log.delta > 0 ? 'is-up' : 'is-down'"
              >
                {{ fmtDelta(log.delta) }}
              </div>
              <div class="log-after">→ {{ log.score_after }}</div>
            </div>
          </article>
        </div>

        <EmptyState v-else text="暂无警告值变动记录，保持良好社区行为" />

        <Pagination
          :total="total"
          :page="page"
          :page-size="pageSize"
          @change="onPageChange"
        />
      </section>
    </div>
  </main>
</template>

<style scoped>
.page-warning-logs {
  min-height: 100vh;
  background: var(--bg-100);
  padding-bottom: calc(80px + env(safe-area-inset-bottom));
}

.container {
  max-width: 640px;
  margin: 0 auto;
  padding: 16px;
}

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.page-title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  color: var(--text-800);
}
.icon-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: transparent;
  cursor: pointer;
  display: grid;
  place-items: center;
  color: var(--text-700);
  transition: background 0.15s;
}
.icon-btn:hover {
  background: var(--bg-200);
}
.icon-placeholder {
  width: 36px;
  height: 36px;
  display: inline-block;
}

/* 状态卡片 */
.status-card {
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  padding: 18px 16px;
  margin-bottom: 20px;
}
.status-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.status-title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}
.status-ic {
  display: grid;
  place-items: center;
}
.status-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-800);
}
.status-level-pill {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
}
.status-score-row {
  display: flex;
  align-items: baseline;
  gap: 4px;
  margin-bottom: 12px;
}
.status-score-num {
  font-size: 36px;
  font-weight: 800;
  line-height: 1;
  letter-spacing: -0.02em;
}
.status-score-divider {
  font-size: 20px;
  color: var(--text-400);
  font-weight: 600;
}
.status-score-max {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-600);
}
.status-progress {
  width: 100%;
  height: 8px;
  background: rgba(255, 255, 255, 0.6);
  border-radius: 999px;
  margin-bottom: 12px;
  overflow: hidden;
}
.status-progress-bar {
  height: 100%;
  border-radius: 999px;
  transition: width 0.3s ease;
}
.status-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-700);
  margin-bottom: 6px;
}
.status-hint b {
  color: var(--text-800);
  font-weight: 700;
}
.status-reduce-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-500);
}

/* 记录区 */
.logs-section {
  background: transparent;
}
.logs-section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 12px;
}
.logs-section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-800);
}
.logs-section-count {
  font-size: 12px;
  color: var(--text-500);
}

.loading-tip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 0;
  color: var(--text-500);
  font-size: 13px;
}

.logs-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.log-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  background: var(--bg-50);
  border-radius: var(--radius-md);
  padding: 12px 14px;
  box-shadow: var(--shadow-xs);
}
.log-left {
  flex-shrink: 0;
  padding-top: 2px;
}
.log-source-pill {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 999px;
  white-space: nowrap;
}
.log-body {
  flex: 1;
  min-width: 0;
}
.log-reason {
  margin: 0 0 4px;
  font-size: 13px;
  color: var(--text-800);
  line-height: 1.5;
  word-break: break-word;
}
.log-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  font-size: 11px;
  color: var(--text-400);
}
.log-related {
  color: var(--text-400);
}
.log-right {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}
.log-delta {
  font-size: 16px;
  font-weight: 800;
  line-height: 1;
}
.log-delta.is-up {
  color: #ff3b30;
}
.log-delta.is-down {
  color: #34c759;
}
.log-after {
  font-size: 11px;
  color: var(--text-500);
}

@media (max-width: 480px) {
  .container {
    padding: 12px;
  }
  .log-item {
    padding: 10px 12px;
  }
  .log-left {
    width: 90px;
  }
}
</style>
