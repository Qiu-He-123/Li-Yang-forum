<script setup lang="ts">
/**
 * 首页统计列表页（在线中 / 游客在线 / 今日发布 / 注册人数）。
 * 下拉触底加载下一页，与首页瀑布流一致。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { Icon } from '../components/native'
import EmptyState from '../components/common/EmptyState.vue'
import BadgeIcon from '../components/common/BadgeIcon.vue'
import InfiniteScrollFooter from '../components/common/InfiniteScrollFooter.vue'
import { toast } from '../components/native/Toast'
import { useInfiniteScroll } from '../composables/useInfiniteScroll'
import {
  fetchOnlineGuests,
  fetchOnlineUsers,
  type OnlineGuestItem,
  type OnlineUserItem,
} from '../api/stats'
import { fetchRecentUsers, type RecentUserItem } from '../api/user'
import { listPosts } from '../api/post'
import type { Badge, Post } from '../types/api'

const route = useRoute()
const router = useRouter()

type ListType = 'online' | 'guests' | 'today-posts' | 'users'
const type = computed<ListType>(
  () => (route.path.split('/').pop() as ListType) || 'online',
)

const metaMap: Record<ListType, { title: string; desc: string }> = {
  online: { title: '在线用户', desc: '当前在线的登录用户' },
  guests: { title: '游客在线', desc: '当前在线的游客（匿名会话）' },
  'today-posts': { title: '今日发布', desc: '今天发布的新帖' },
  users: { title: '注册用户', desc: '按注册时间倒序' },
}
const meta = computed(() => metaMap[type.value] || metaMap.online)

interface Row {
  key: string
  avatar: string | null
  name: string
  badge: Badge | null
  school: string | null
  time: string | null
  post?: Post
}

const rows = ref<Row[]>([])
const loading = ref(false)
const page = ref(1)
const total = ref(0)
const pageSize = 20
const keyword = ref('')

// 搜索结果：在线/注册用户已由后端按 q 过滤，这里再做一次客户端兜底（游客页无后端搜索）
const displayRows = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return rows.value
  return rows.value.filter((r) => r.name.toLowerCase().includes(kw))
})

function fmtTime(t?: string | null): string {
  if (!t) return '—'
  return t.replace('T', ' ').slice(0, 16)
}

async function load(reset = false) {
  if (reset) {
    page.value = 1
    rows.value = []
    total.value = 0
  }
  loading.value = true
  try {
    let items: Row[] = []
    let t = 0
    if (type.value === 'online') {
      const { data } = await fetchOnlineUsers(page.value, pageSize, keyword.value.trim())
      items = data.data.items.map((u: OnlineUserItem) => ({
        key: String(u.id),
        avatar: u.avatar_url,
        name: u.nickname,
        badge: u.badge,
        school: u.school,
        time: u.connected_at,
      }))
      t = data.data.total
    } else if (type.value === 'guests') {
      const { data } = await fetchOnlineGuests(page.value, pageSize)
      items = data.data.items.map((g: OnlineGuestItem) => ({
        key: g.id,
        avatar: null,
        name: g.nickname,
        badge: null,
        school: null,
        time: g.connected_at,
      }))
      t = data.data.total
    } else if (type.value === 'users') {
      const { data } = await fetchRecentUsers(page.value, pageSize, keyword.value.trim())
      items = data.data.items.map((u: RecentUserItem) => ({
        key: String(u.id),
        avatar: u.avatar_url,
        name: u.nickname,
        badge: u.badge,
        school: u.school,
        time: u.created_at,
      }))
      t = data.data.total
    } else {
      const { data } = await listPosts({
        view: 'today',
        page: page.value,
        page_size: pageSize,
      })
      const payload = data.data as unknown as { items: Post[]; total: number }
      items = (payload.items || []).map((p: Post) => ({
        key: String(p.id),
        avatar: p.author_avatar_url ?? null,
        name: p.author ?? '匿名',
        badge: null,
        school: null,
        time: p.created_at ?? null,
        post: p,
      }))
      t = payload.total || 0
    }
    const seen = new Set<string>()
    const merged = [...(reset ? [] : rows.value), ...items].filter((r) =>
      seen.has(r.key) ? false : (seen.add(r.key), true),
    )
    rows.value = merged
    total.value = t
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

const hasMore = computed(() => rows.value.length < total.value)

async function loadMore() {
  if (!hasMore.value || loading.value) return
  page.value += 1
  await load()
}

const {
  loading: scrollLoading,
  error: scrollError,
  retry: scrollRetry,
} = useInfiniteScroll({
  hasMore,
  onLoadMore: loadMore,
  containerSelector: '.page-stats',
})

watch(type, () => load(true))
onMounted(() => load(true))

function openRow(row: Row) {
  if (type.value === 'today-posts' && row.post) {
    router.push(`/post/${row.post.id}`)
    return
  }
  if (type.value !== 'guests') {
    router.push(`/user/${row.key}`)
  }
}

function onSearch() {
  load(true)
}

function clearSearch() {
  keyword.value = ''
  load(true)
}
</script>

<template>
  <main class="page-stats">
    <header class="stats-header">
      <button class="icon-btn" type="button" aria-label="返回" @click="router.back()">
        <Icon name="arrow-left" :size="20" />
      </button>
      <div class="stats-header-text">
        <h1 class="stats-header-title">{{ meta.title }}</h1>
        <span class="stats-header-desc">{{ meta.desc }}</span>
      </div>
      <span class="icon-btn-placeholder" />
    </header>

    <!-- 搜索：在线中 / 游客在线 / 注册用户 -->
    <div v-if="type !== 'today-posts'" class="stats-search">
      <span class="stats-search-icon" role="button" aria-label="搜索" @click="onSearch">
        <Icon name="search" :size="16" />
      </span>
      <input
        v-model="keyword"
        type="text"
        placeholder="搜索昵称…"
        @keyup.enter="onSearch"
      />
      <button
        v-if="keyword"
        class="stats-search-clear"
        type="button"
        aria-label="清空"
        @click="clearSearch"
      >
        <Icon name="x" :size="14" />
      </button>
    </div>

    <div class="stats-list-wrap">
      <div v-if="loading && !rows.length" class="loading-tip">
        <Icon name="refresh" :size="20" />
        <span>加载中…</span>
      </div>

      <div v-else-if="displayRows.length" class="stats-list">
        <!-- 今日发布：帖子样式 -->
        <button
          v-if="type === 'today-posts'"
          v-for="row in displayRows"
          :key="row.key"
          class="stats-row stats-row--post"
          type="button"
          @click="openRow(row)"
        >
          <img v-if="row.post?.image_urls?.length" class="row-thumb" :src="row.post.image_urls[0]" alt="" />
          <div class="row-main">
            <h3 class="row-title">{{ row.post?.title || row.post?.content?.slice(0, 50) }}</h3>
            <p v-if="row.post?.content" class="row-excerpt">{{ row.post.content.slice(0, 60) }}</p>
            <div class="row-meta">
              <span class="row-cat">#{{ row.post?.category || '校园' }}</span>
              <span class="dot">·</span>
              <span class="row-stat">
                <Icon name="heart" :size="11" />
                {{ row.post?.like_count ?? 0 }}
              </span>
              <span class="dot">·</span>
              <span class="row-stat">
                <Icon name="message-square" :size="11" />
                {{ row.post?.comment_count ?? 0 }}
              </span>
              <span class="dot">·</span>
              <span class="row-time">{{ fmtTime(row.time) }}</span>
            </div>
          </div>
        </button>

        <!-- 用户/游客：头像列表样式 -->
        <button
          v-else
          v-for="row in displayRows"
          :key="row.key"
          class="stats-row"
          type="button"
          :class="{ 'is-guest': type === 'guests' }"
          @click="openRow(row)"
        >
          <span
            class="row-avatar"
            :style="row.avatar ? { backgroundImage: `url(${row.avatar})` } : {}"
          >
            <Icon v-if="type === 'guests'" name="user" :size="18" />
            <span v-else>{{ row.name.charAt(0).toUpperCase() }}</span>
          </span>
          <span class="row-main">
            <span class="row-name">
              <BadgeIcon :badge="row.badge" :size="14" />
              {{ row.name }}
            </span>
            <span class="row-sub">{{ row.school || (type === 'guests' ? '匿名浏览中' : '—') }}</span>
          </span>
          <span class="row-right">
            <span class="row-online-dot" aria-hidden="true"></span>
            <span class="row-time">
              {{ type === 'users' ? '注册于' : '上线于' }} {{ fmtTime(row.time) }}
            </span>
          </span>
        </button>

        <InfiniteScrollFooter
          :loading="scrollLoading"
          :error="scrollError"
          :has-more="hasMore"
          :has-items="displayRows.length > 0"
          @retry="scrollRetry"
        />
      </div>

      <EmptyState v-else :text="keyword ? '没有找到相关用户' : '暂时没有数据'" />
    </div>
  </main>
</template>

<style scoped>
.page-stats {
  height: 100dvh;
  overflow-y: auto;
  background: var(--bg-100);
  color: var(--text-800);
  -webkit-overflow-scrolling: touch;
}
.stats-header {
  position: sticky;
  top: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  background: var(--bg-50);
  border-bottom: 0.5px solid var(--bg-300);
}
.stats-search {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 16px 12px;
  padding: 0 14px;
  height: 40px;
  border-radius: 999px;
  border: 1px solid var(--bg-300);
  background: var(--bg-50);
  color: var(--text-400);
}
.stats-search-icon {
  display: inline-flex;
  align-items: center;
  cursor: pointer;
}
.stats-search input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  font-size: 14px;
  color: var(--text-800);
}
.stats-search input::placeholder {
  color: var(--text-400);
}
.stats-search-clear {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 50%;
  background: var(--bg-200);
  color: var(--text-500);
  cursor: pointer;
}
.stats-header-text {
  flex: 1;
  min-width: 0;
}
.stats-header-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
}
.stats-header-desc {
  font-size: 11px;
  color: var(--text-400);
}
.icon-btn-placeholder {
  width: 36px;
}
.loading-tip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 0;
  color: var(--text-400);
  font-size: 13px;
}
.stats-list-wrap {
  padding: 12px 16px 24px;
}
.stats-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.stats-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 14px;
  border: 1px solid var(--bg-300);
  border-radius: 14px;
  background: var(--bg-50);
  cursor: pointer;
  text-align: left;
  transition: all 0.15s ease;
}
.stats-row:hover {
  border-color: var(--brand-300);
  box-shadow: 0 6px 20px -8px rgba(0, 0, 0, 0.1);
}
.stats-row:active {
  transform: scale(0.99);
}
.row-avatar {
  flex: none;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, #66abff, #007aff);
  color: #fff;
  font-size: 15px;
  font-weight: 700;
  background-size: cover;
  background-position: center;
  overflow: hidden;
}
.row-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.row-name {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 15px;
  font-weight: 700;
}
.row-sub {
  font-size: 12px;
  color: var(--text-400);
}
.row-right {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-400);
}
.row-online-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #34c759;
}
.row-time {
  font-size: 11px;
  color: var(--text-400);
}
/* 帖子行 */
.stats-row--post {
  align-items: flex-start;
}
.row-thumb {
  flex: none;
  width: 72px;
  height: 72px;
  border-radius: 10px;
  object-fit: cover;
  background: var(--bg-200);
}
.row-title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.row-excerpt {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--text-500);
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.row-meta {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 4px;
  font-size: 11px;
  color: var(--text-400);
}
.row-cat {
  color: var(--brand-500);
}
.dot {
  color: var(--text-300);
}
.row-stat {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
</style>
