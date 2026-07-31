<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppHeader from '../components/header/AppHeader.vue'
import EmptyState from '../components/common/EmptyState.vue'
import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import { listPosts } from '../api/post'
import { hotTopics, searchTopics, type Topic } from '../api/topic'
import { useSessionStore } from '../stores/session'
import { useSearchStore } from '../stores/search'
import type { Post } from '../types/api'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const searchStore = useSearchStore()

const keyword = ref<string>(String(route.query.q ?? ''))
const tagFilter = ref<string>(String(route.query.tag ?? ''))
const posts = ref<Post[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const hasSearched = ref(false)

// 话题相关
const hotTopicList = ref<Topic[]>([])
const topicSuggestList = ref<Topic[]>([])
const topicSuggestLoading = ref(false)
let topicSuggestTimer: ReturnType<typeof setTimeout> | null = null

const showClearBtn = computed(() => keyword.value.length > 0)

/** 输入时实时搜索话题联想 */
watch(keyword, (val) => {
  if (topicSuggestTimer) clearTimeout(topicSuggestTimer)
  const q = val.trim()
  if (!q) {
    topicSuggestList.value = []
    return
  }
  topicSuggestLoading.value = true
  topicSuggestTimer = setTimeout(async () => {
    try {
      const { data } = await searchTopics(q, {
        showGlobalLoading: false,
        showGlobalError: false,
      })
      topicSuggestList.value = (data.data || []).slice(0, 5)
    } catch {
      topicSuggestList.value = []
    } finally {
      topicSuggestLoading.value = false
    }
  }, 250)
})

function rankColor(idx: number): string {
  if (idx === 0) return 'linear-gradient(135deg, #ff3b30, #ff9500)'
  if (idx === 1) return '#ff9500'
  if (idx === 2) return '#007aff'
  return '#8e8e93'
}

function hotTag(count: number): { label: string; bg: string; color: string } | null {
  if (count >= 1000) return { label: '沸', bg: 'linear-gradient(135deg, #ff3b30, #ff9500)', color: '#fff' }
  if (count >= 200) return { label: '热', bg: '#ffecea', color: '#ff3b30' }
  return null
}

function formatCount(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, '') + 'w'
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k'
  return String(n)
}

async function doSearch() {
  const q = keyword.value.trim()
  if (!q) {
    toast.info('请输入搜索关键词')
    return
  }
  loading.value = true
  hasSearched.value = true
  try {
    const params: Parameters<typeof listPosts>[0] = {
      page: page.value,
      page_size: pageSize.value,
      q,
    }
    if (tagFilter.value.trim()) params.tag = tagFilter.value
    const { data } = await listPosts(params)
    const payload = data.data as unknown as { items: Post[]; total: number; page: number; page_size: number } | Post[]
    if (Array.isArray(payload)) {
      posts.value = payload
      total.value = payload.length
    } else {
      posts.value = payload.items
      total.value = payload.total
      page.value = payload.page
      pageSize.value = payload.page_size
    }
    searchStore.appendHistoryLocal(q)
    router.replace({ path: '/search', query: { q } })
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

function searchKeyword(kw: string) {
  keyword.value = kw
  doSearch()
}

/** 点击话题跳转到话题详情页 */
function openTopic(topic: Topic) {
  router.push(`/topic/${topic.id}`)
}

async function removeHistory(kw: string, e: Event) {
  e.stopPropagation()
  await searchStore.removeHistory(kw)
}

async function clearAllHistory() {
  await searchStore.clearHistory()
  toast.success('已清空')
}

function clearInput() {
  keyword.value = ''
  hasSearched.value = false
  posts.value = []
}

function goBack() {
  router.back()
}

function openPost(post: Post) {
  router.push(`/post/${post.id}`)
}

watch(
  () => route.query.q,
  (q) => {
    keyword.value = String(q ?? '')
    if (keyword.value) doSearch()
  },
)

onMounted(async () => {
  const valid = await session.validateSession()
  if (!valid) return
  await Promise.all([
    searchStore.loadHistory(),
    searchStore.loadHot(),
    // 加载热门话题
    hotTopics(10).then(({ data }) => {
      hotTopicList.value = data.data || []
    }).catch(() => {
      hotTopicList.value = []
    }),
  ])
  if (keyword.value) doSearch()
})
</script>

<template>
  <main class="page-search">
    <!-- 顶部搜索栏 -->
    <header class="search-header">
      <button class="back-btn" type="button" aria-label="返回" @click="goBack">
        <Icon name="arrow-left" :size="20" />
      </button>
      <form class="search-box" @submit.prevent="doSearch">
        <Icon name="search" :size="18" class="search-ic" />
        <input
          v-model="keyword"
          class="search-input"
          type="text"
          placeholder="搜索帖子、用户、圈子"
          autofocus
        />
        <button
          v-if="showClearBtn"
          class="clear-btn"
          type="button"
          aria-label="清空"
          @click="clearInput"
        >
          <Icon name="x" :size="16" />
        </button>
      </form>
      <button class="search-action" type="button" @click="doSearch">搜索</button>
    </header>

    <div class="search-page">
      <!-- 搜索结果 -->
      <div v-if="hasSearched" class="search-results">
        <div v-if="loading" class="loading-tip">
          <Icon name="refresh" :size="20" />
          <span>搜索中…</span>
        </div>
        <div v-else-if="posts.length" class="result-list">
          <div class="result-count">共找到 {{ total }} 条结果</div>
          <article
            v-for="post in posts"
            :key="post.id"
            class="result-item"
            @click="openPost(post)"
          >
            <h3 class="result-title">
              <span v-if="post.is_public === false" class="private-badge">
                <Icon name="lock" :size="12" />
                已私密
              </span>
              {{ post.title || post.content.slice(0, 50) }}
            </h3>
            <p v-if="post.content && post.title" class="result-excerpt">{{ post.content }}</p>
            <div class="result-meta">
              <span class="result-author">{{ post.is_anonymous ? '匿名' : post.author }}</span>
              <span class="dot">·</span>
              <span class="result-cat">#{{ post.category || '校园' }}</span>
              <span class="dot">·</span>
              <span class="result-likes">
                <Icon name="heart" :size="12" />
                {{ formatCount(post.like_count) }}
              </span>
            </div>
          </article>
        </div>
        <EmptyState v-else text="没有找到相关内容，换个关键词试试" />
      </div>

      <!-- 搜索历史 + 热搜榜（未搜索时） -->
      <template v-else>
        <!-- 话题搜索联想（输入时实时显示） -->
        <section v-if="topicSuggestList.length" class="block topic-suggest-block">
          <div class="block-head">
            <h2 class="block-title">
              <Icon name="hash" :size="14" />
              相关话题
            </h2>
            <span class="block-update">点击进入话题</span>
          </div>
          <div class="topic-suggest-list">
            <div
              v-for="t in topicSuggestList"
              :key="t.id"
              class="topic-suggest-item"
              @click="openTopic(t)"
            >
              <div class="topic-suggest-info">
                <span class="topic-suggest-name">#{{ t.name }}</span>
                <span class="topic-suggest-count">{{ formatCount(t.post_count) }} 帖</span>
              </div>
              <Icon name="chevron-right" :size="14" color="#c7c7cc" />
            </div>
          </div>
        </section>

        <!-- 历史搜索 -->
        <section class="block">
          <div class="block-head">
            <h2 class="block-title">搜索历史</h2>
            <button
              v-if="searchStore.history.length"
              class="block-action"
              type="button"
              @click="clearAllHistory"
            >
              <Icon name="trash" :size="13" />
              清空
            </button>
          </div>
          <div v-if="searchStore.history.length" class="history-chips">
            <button
              v-for="h in searchStore.history"
              :key="h.id"
              class="history-chip"
              type="button"
              @click="searchKeyword(h.keyword)"
            >
              <span class="chip-text">{{ h.keyword }}</span>
              <span class="chip-x" @click="removeHistory(h.keyword, $event)">
                <Icon name="x" :size="11" />
              </span>
            </button>
          </div>
          <div v-else class="empty-state">
            <Icon name="clock" :size="28" color="#aeaeb2" />
            <p>暂无搜索历史</p>
          </div>
        </section>

        <!-- 热门话题 -->
        <section v-if="hotTopicList.length" class="block">
          <div class="block-head">
            <h2 class="block-title">
              <Icon name="hash" :size="16" color="#007aff" />
              热门话题
            </h2>
            <span class="block-update">点击进入话题</span>
          </div>
          <div class="topic-chips">
            <button
              v-for="(t, idx) in hotTopicList"
              :key="t.id"
              class="topic-chip"
              type="button"
              @click="openTopic(t)"
            >
              <span
                v-if="idx < 3"
                class="topic-rank"
                :style="{ color: idx < 3 ? '' : '#8e8e93' }"
              >{{ idx + 1 }}</span>
              <span class="topic-chip-name">#{{ t.name }}</span>
              <span class="topic-chip-count">{{ formatCount(t.post_count) }}</span>
            </button>
          </div>
        </section>

        <!-- 校园热搜 -->
        <section class="block">
          <div class="block-head">
            <h2 class="block-title">
              <Icon name="flame" :size="16" color="#ff3b30" />
              校园热搜
            </h2>
            <span class="block-update">更新于刚刚</span>
          </div>
          <ol v-if="searchStore.hotList.length" class="hot-list">
            <li
              v-for="(item, idx) in searchStore.hotList"
              :key="item.keyword"
              class="hot-item"
              @click="searchKeyword(item.keyword)"
            >
              <span class="hot-rank" :style="{ color: idx < 3 ? '' : '#8e8e93' }">
                <span
                  v-if="idx < 3"
                  class="rank-num"
                  :style="{ background: rankColor(idx) }"
                >{{ idx + 1 }}</span>
                <span v-else class="rank-num rank-num--muted">{{ idx + 1 }}</span>
              </span>
              <div class="hot-content">
                <div class="hot-keyword-row">
                  <span class="hot-keyword">{{ item.keyword }}</span>
                  <span
                    v-if="hotTag(item.count)"
                    class="hot-tag"
                    :style="{
                      background: hotTag(item.count)!.bg,
                      color: hotTag(item.count)!.color,
                    }"
                  >{{ hotTag(item.count)!.label }}</span>
                </div>
                <span class="hot-count">{{ formatCount(item.count) }} 讨论</span>
              </div>
              <Icon name="chevron-right" :size="16" color="#c7c7cc" class="hot-arrow" />
            </li>
          </ol>
          <div v-else class="empty-state">
            <Icon name="flame" :size="28" color="#aeaeb2" />
            <p>暂无热搜数据</p>
          </div>
        </section>
      </template>
    </div>
  </main>
</template>

<style scoped>
.page-search {
  min-height: 100vh;
  background: var(--bg-100);
  padding-bottom: calc(80px + env(safe-area-inset-bottom));
}

/* 顶部搜索栏 */
.search-header {
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
  gap: 10px;
  padding: 0 16px;
}
.back-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: transparent;
  cursor: pointer;
  display: grid;
  place-items: center;
  color: var(--text-600);
  flex-shrink: 0;
}
.back-btn:hover {
  background: var(--bg-100);
}
.search-box {
  flex: 1;
  display: flex;
  align-items: center;
  background: var(--bg-100);
  border: 1px solid transparent;
  border-radius: 999px;
  padding: 0 12px;
  height: 36px;
  transition: all 0.15s cubic-bezier(0.32, 0.72, 0, 1);
}
.search-box:focus-within {
  background: var(--brand-50);
  border-color: var(--brand-500);
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.15);
}
.search-ic {
  color: var(--text-400);
  flex-shrink: 0;
}
.search-input {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 14px;
  color: var(--text-800);
  outline: none;
  margin: 0 8px;
  min-width: 0;
}
.search-input::placeholder {
  color: var(--text-400);
}
.clear-btn {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: none;
  background: var(--bg-300);
  cursor: pointer;
  display: grid;
  place-items: center;
  color: var(--text-500);
  flex-shrink: 0;
}
.search-action {
  font-size: 14px;
  font-weight: 600;
  color: var(--brand-500);
  background: transparent;
  border: none;
  cursor: pointer;
  flex-shrink: 0;
  padding: 0 4px;
}
.search-action:hover {
  color: var(--brand-600);
}

/* 主内容区 */
.search-page {
  max-width: 640px;
  margin: 0 auto;
  padding: 16px;
}

/* Block 区块 */
.block {
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  padding: 16px;
  margin-bottom: 14px;
}
.block-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.block-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-800);
  margin: 0;
  letter-spacing: -0.01em;
}
.block-action {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-400);
  background: transparent;
  border: none;
  cursor: pointer;
}
.block-action:hover {
  color: var(--error);
}
.block-update {
  font-size: 11px;
  color: var(--text-400);
}

/* 历史 chips */
.history-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.history-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px 6px 12px;
  background: var(--bg-100);
  border: 1px solid var(--bg-200);
  border-radius: 999px;
  font-size: 13px;
  color: var(--text-600);
  cursor: pointer;
  transition: all 0.15s cubic-bezier(0.32, 0.72, 0, 1);
}
.history-chip:hover {
  background: var(--brand-50);
  border-color: var(--brand-100);
  color: var(--brand-600);
}
.chip-x {
  display: inline-grid;
  place-items: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--bg-300);
  color: var(--text-500);
  transition: all 0.15s;
}
.chip-x:hover {
  background: var(--error);
  color: white;
}

/* 热搜榜 */
.hot-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.hot-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 4px;
  border-bottom: 0.5px solid var(--bg-200);
  cursor: pointer;
  transition: background 0.15s;
}
.hot-item:last-child {
  border-bottom: none;
}
.hot-item:hover {
  background: var(--bg-100);
}
.hot-rank {
  flex-shrink: 0;
  width: 24px;
  display: grid;
  place-items: center;
}
.rank-num {
  display: inline-grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 700;
  color: white;
}
.rank-num--muted {
  background: var(--bg-200);
  color: var(--text-500);
}
.hot-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.hot-keyword-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.hot-keyword {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-800);
}
.hot-tag {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 4px;
  letter-spacing: 0.02em;
}
.hot-count {
  font-size: 11px;
  color: var(--text-400);
}
.hot-arrow {
  flex-shrink: 0;
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px 0;
  color: var(--text-400);
  font-size: 13px;
}
.empty-state p {
  margin: 0;
}

/* 搜索结果 */
.search-results {
  max-width: 720px;
  margin: 0 auto;
  padding: 16px;
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
.result-count {
  font-size: 12px;
  color: var(--text-400);
  margin-bottom: 12px;
}
.result-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.result-item {
  background: var(--bg-50);
  border-radius: var(--radius-md);
  padding: 14px;
  box-shadow: var(--shadow-xs);
  cursor: pointer;
  transition: box-shadow 0.15s;
}
.result-item:hover {
  box-shadow: var(--shadow-sm);
}
/* 私密徽标 */
.private-badge {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-right: 6px;
  padding: 1px 6px;
  font-size: 11px;
  font-weight: 500;
  line-height: 1.4;
  color: #b45309;
  background: rgba(245, 158, 11, 0.12);
  border-radius: 4px;
  vertical-align: middle;
}
.result-title {
  margin: 0 0 6px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-800);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.result-excerpt {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--text-500);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.result-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-400);
}
.result-author {
  font-weight: 500;
}
.result-cat {
  color: var(--brand-500);
}
.result-likes {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
.dot {
  color: var(--bg-300);
}

/* 话题搜索联想 */
.topic-suggest-block {
  border: 1px solid rgba(0, 122, 255, 0.15);
}
.topic-suggest-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.topic-suggest-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s;
}
.topic-suggest-item:hover {
  background: var(--bg-100);
}
.topic-suggest-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.topic-suggest-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--brand-500);
}
.topic-suggest-count {
  font-size: 11px;
  color: var(--text-400);
}

/* 热门话题 chips */
.topic-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.topic-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: var(--bg-100);
  border: 1px solid var(--bg-200);
  border-radius: 999px;
  font-size: 13px;
  color: var(--text-700);
  cursor: pointer;
  transition: all 0.15s cubic-bezier(0.32, 0.72, 0, 1);
}
.topic-chip:hover {
  background: var(--brand-50);
  border-color: var(--brand-100);
  color: var(--brand-600);
}
.topic-rank {
  display: inline-grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, #ff9500, #ff3b30);
}
.topic-chip-name {
  font-weight: 500;
}
.topic-chip-count {
  font-size: 11px;
  color: var(--text-400);
  padding-left: 4px;
  border-left: 1px solid var(--bg-300);
}

@media (max-width: 768px) {
  .search-header {
    height: 48px;
    padding: 0 12px;
  }
  .search-page {
    padding: 12px;
  }
}
</style>
