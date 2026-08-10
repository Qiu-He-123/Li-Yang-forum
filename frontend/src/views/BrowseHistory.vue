<script setup lang="ts">
/**
 * 浏览历史页
 *
 * 功能：
 * - 列表展示用户浏览过的帖子（按浏览时间倒序）
 * - 单条删除 + 清空全部
 * - 点击跳转到帖子详情
 * - 分页加载更多
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import EmptyState from '../components/common/EmptyState.vue'
import MarkdownText from '../components/common/MarkdownText.vue'
import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import { clearHistory, deleteHistoryItem, listHistory, type HistoryItem } from '../api/history'

const router = useRouter()

const items = ref<HistoryItem[]>([])
const loading = ref(false)
const deleting = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)
const hasMore = computed(() => items.value.length < total.value)

async function loadList(reset = false) {
  if (reset) {
    page.value = 1
    items.value = []
  }
  if (loading.value) return
  loading.value = true
  try {
    const { data } = await listHistory(page.value, pageSize)
    const next = data.data.items || []
    items.value = reset ? next : [...items.value, ...next]
    total.value = data.data.total || 0
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

async function onLoadMore() {
  if (loading.value || !hasMore.value) return
  page.value += 1
  await loadList(false)
}

async function onDeleteItem(item: HistoryItem, idx: number) {
  if (deleting.value) return
  deleting.value = true
  try {
    await deleteHistoryItem(item.history_id)
    items.value.splice(idx, 1)
    total.value = Math.max(0, total.value - 1)
    toast.success('已删除')
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    deleting.value = false
  }
}

async function onClearAll() {
  if (deleting.value || !items.value.length) return
  if (!window.confirm('确定要清空全部浏览历史吗？此操作不可恢复。')) return
  deleting.value = true
  try {
    await clearHistory()
    items.value = []
    total.value = 0
    toast.success('已清空浏览历史')
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    deleting.value = false
  }
}

function openPost(item: HistoryItem) {
  router.push(`/post/${item.post_id}`)
}

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/')
}

function timeAgo(dateStr?: string | null): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const now = new Date()
  const diff = (now.getTime() - d.getTime()) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  if (diff < 604800) return `${Math.floor(diff / 86400)}天前`
  return d.toLocaleDateString()
}

function avatarGradient(id: number | null | undefined): string {
  const idx = (id ?? 0) % 5
  const grads = [
    'linear-gradient(135deg, #66abff, #007aff)',
    'linear-gradient(135deg, #34c759, #2e8dff)',
    'linear-gradient(135deg, #ff9500, #007aff)',
    'linear-gradient(135deg, #5856d6, #0064d6)',
    'linear-gradient(135deg, #d1d1d6, #8e8e93)',
  ]
  return grads[idx]
}

const isEmpty = computed(() => !loading.value && items.value.length === 0)

onMounted(() => {
  loadList(true)
})
</script>

<template>
  <main class="page-history">
    <!-- 顶部栏 -->
    <header class="page-header">
      <button class="icon-btn" type="button" aria-label="返回" @click="goBack">
        <Icon name="arrow-left" :size="20" />
      </button>
      <h1 class="page-title">浏览历史</h1>
      <button
        v-if="items.length"
        class="clear-btn"
        type="button"
        :disabled="deleting"
        @click="onClearAll"
      >
        清空
      </button>
      <span v-else class="icon-btn-placeholder" />
    </header>

    <div class="page-container">
      <!-- 统计条 -->
      <div v-if="items.length" class="stat-bar">
        <Icon name="history" :size="14" />
        <span>共 {{ total }} 条浏览记录</span>
      </div>

      <!-- 加载中（首次） -->
      <div v-if="loading && !items.length" class="loading-tip">
        <Icon name="refresh" :size="20" />
        <span>加载中…</span>
      </div>

      <!-- 历史列表 -->
      <div v-else-if="items.length" class="history-list">
        <article
          v-for="(item, idx) in items"
          :key="item.history_id"
          class="history-item"
        >
          <div class="item-main" @click="openPost(item)">
            <div class="item-body">
              <h3 class="item-title">{{ item.title || item.content.slice(0, 40) || '无标题' }}</h3>
              <MarkdownText v-if="item.title && item.content" :content="item.content" class="item-excerpt" :clamp="2" />
              <div class="item-meta">
                <span class="meta-cat">#{{ item.category || '校园' }}</span>
                <span class="meta-dot">·</span>
                <span class="meta-stat">
                  <Icon name="heart" :size="12" />
                  {{ item.like_count }}
                </span>
                <span class="meta-dot">·</span>
                <span class="meta-stat">
                  <Icon name="message-square" :size="12" />
                  {{ item.comment_count }}
                </span>
              </div>
            </div>
            <img
              v-if="item.image_urls?.length"
              class="item-thumb"
              :src="item.image_urls[0]"
              :alt="item.title || ''"
            />
          </div>
          <div class="item-footer">
            <div class="author-info">
              <div
                class="author-avatar"
                :style="
                  item.author_avatar_url
                    ? { backgroundImage: `url(${item.author_avatar_url})` }
                    : { background: avatarGradient(item.author_id) }
                "
              >
                <span v-if="!item.author_avatar_url">
                  {{ item.author_nickname?.charAt(0).toUpperCase() || 'U' }}
                </span>
              </div>
              <span class="author-name">{{ item.author_nickname || '匿名用户' }}</span>
              <span class="viewed-time">{{ timeAgo(item.viewed_at) }}看过</span>
            </div>
            <button
              class="del-btn"
              type="button"
              :disabled="deleting"
              aria-label="删除"
              @click.stop="onDeleteItem(item, idx)"
            >
              <Icon name="trash" :size="16" />
            </button>
          </div>
        </article>

        <!-- 加载更多 -->
        <div v-if="hasMore" class="load-more">
          <button
            class="load-more-btn"
            type="button"
            :disabled="loading"
            @click="onLoadMore"
          >
            <Icon v-if="loading" name="refresh" :size="14" />
            {{ loading ? '加载中…' : '加载更多' }}
          </button>
        </div>
        <div v-else class="list-end">
          <span>没有更多了</span>
        </div>
      </div>

      <!-- 空状态 -->
      <EmptyState v-else-if="isEmpty" icon="history" text="还没有浏览历史，去看看精彩内容吧" />
    </div>
  </main>
</template>

<style scoped>
.page-history {
  min-height: 100vh;
  background: var(--bg-100);
  padding-bottom: calc(80px + env(safe-area-inset-bottom));
}

/* 顶部 */
.page-header {
  position: sticky;
  top: 0;
  z-index: 50;
  background: rgba(255, 255, 255, 0.95);
  -webkit-backdrop-filter: blur(20px);
  backdrop-filter: blur(20px);
  border-bottom: 0.5px solid var(--bg-300);
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  padding-top: env(safe-area-inset-top);
}
.page-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-800);
  margin: 0;
  flex: 1;
  text-align: center;
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
  color: var(--text-600);
  transition: background 0.15s;
}
.icon-btn:hover {
  background: var(--bg-100);
}
.icon-btn-placeholder {
  width: 36px;
  height: 36px;
  display: inline-block;
}
.clear-btn {
  font-size: 14px;
  color: #ff3b30;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 8px;
  font-weight: 500;
  transition: background 0.15s;
}
.clear-btn:hover:not(:disabled) {
  background: rgba(255, 59, 48, 0.08);
}
.clear-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 内容区 */
.page-container {
  max-width: 720px;
  margin: 0 auto;
  padding: 8px 16px 0;
}

/* 统计条 */
.stat-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 4px 12px;
  font-size: 12px;
  color: var(--text-500);
}

/* 加载中 */
.loading-tip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 48px 0;
  color: var(--text-500);
  font-size: 13px;
}

/* 列表 */
.history-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.history-item {
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  overflow: hidden;
  transition: box-shadow 0.15s;
}
.history-item:hover {
  box-shadow: var(--shadow-sm);
}
.item-main {
  display: flex;
  gap: 12px;
  padding: 14px 14px 10px;
  cursor: pointer;
}
.item-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.item-title {
  margin: 0;
  padding-right: 4px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-800);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.item-excerpt {
  margin: 0;
  font-size: 13px;
  color: var(--text-500);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.item-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-400);
  margin-top: 2px;
}
.meta-cat {
  color: var(--brand-500);
}
.meta-dot {
  color: var(--bg-300);
}
.meta-stat {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
.item-thumb {
  width: 84px;
  height: 84px;
  border-radius: 10px;
  object-fit: cover;
  flex-shrink: 0;
  background: var(--bg-200);
}

/* 底部 */
.item-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 14px;
  border-top: 0.5px solid var(--bg-200);
}
.author-info {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}
.author-avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background-size: cover;
  background-position: center;
  display: grid;
  place-items: center;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}
.author-name {
  font-size: 12px;
  color: var(--text-600);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex-shrink: 0;
  max-width: 120px;
}
.viewed-time {
  font-size: 11px;
  color: var(--text-400);
  white-space: nowrap;
}
.del-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: none;
  background: transparent;
  cursor: pointer;
  display: grid;
  place-items: center;
  color: var(--text-400);
  transition: all 0.15s;
  flex-shrink: 0;
}
.del-btn:hover:not(:disabled) {
  background: rgba(255, 59, 48, 0.08);
  color: #ff3b30;
}
.del-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 加载更多 */
.load-more {
  display: flex;
  justify-content: center;
  padding: 16px 0 8px;
}
.load-more-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px;
  border: 1px solid var(--bg-300);
  background: var(--bg-50);
  color: var(--text-600);
  font-size: 13px;
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.15s;
}
.load-more-btn:hover:not(:disabled) {
  background: var(--bg-100);
  border-color: var(--brand-400);
  color: var(--brand-500);
}
.load-more-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.list-end {
  text-align: center;
  padding: 16px 12px 18px;
  font-size: 12px;
  color: var(--text-300);
}

@media (max-width: 768px) {
  .page-header {
    height: 48px;
    padding: 0 12px;
    padding-top: env(safe-area-inset-top);
  }
  .page-container {
    padding: 8px 12px 0;
  }
  .item-thumb {
    width: 72px;
    height: 72px;
  }
}
</style>
