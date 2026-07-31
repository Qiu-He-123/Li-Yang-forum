<script setup lang="ts">
/**
 * 话题详情页（阶段二：简化版）
 *
 * 路由：/topic/:id
 * - 顶部固定栏：返回 + 话题名 + 关注/已关注
 * - 话题信息卡：#话题名 + 描述 + 帖子数 + 关注按钮
 * - 帖子列表：单列贴吧风格，作者行 + 标题 + 摘要 + 元数据 + 可选缩略图
 * - 滚动加载更多
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import EmptyState from '../components/common/EmptyState.vue'
import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import { followTopic, getTopicDetail, listTopicPosts, type Topic } from '../api/topic'
import { useSessionStore } from '../stores/session'
import type { Post } from '../types/api'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()

const topicId = computed(() => Number(route.params.id))
const topic = ref<Topic | null>(null)
const posts = ref<Post[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const loadingMore = ref(false)
const followLoading = ref(false)

const hasMore = computed(() => posts.value.length < total.value)

// 头像渐变（与社区其他页面对齐）
function avatarGradient(id?: number): string {
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

function formatCount(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, '') + 'w'
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k'
  return String(n)
}

function timeAgo(iso?: string | null): string {
  if (!iso) return ''
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const diff = Date.now() - then
  const min = Math.floor(diff / 60000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min}分钟前`
  const hour = Math.floor(min / 60)
  if (hour < 24) return `${hour}小时前`
  const day = Math.floor(hour / 24)
  if (day < 7) return `${day}天前`
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

async function loadTopic() {
  if (!topicId.value) return
  try {
    const { data } = await getTopicDetail(topicId.value)
    topic.value = data.data
  } catch (err) {
    toast.error((err as Error).message)
    topic.value = null
  }
}

async function loadPosts(reset = false) {
  if (!topicId.value) return
  if (reset) {
    page.value = 1
    loading.value = true
  } else {
    loadingMore.value = true
  }
  try {
    const { data } = await listTopicPosts(topicId.value, page.value, pageSize)
    const payload = data.data
    if (reset) {
      posts.value = payload.items || []
    } else {
      // 追加并按 id 去重，避免重复
      const existIds = new Set(posts.value.map((p) => p.id))
      const fresh = (payload.items || []).filter((p) => !existIds.has(p.id))
      posts.value = [...posts.value, ...fresh]
    }
    total.value = payload.total || 0
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

async function onLoadMore() {
  if (loadingMore.value || !hasMore.value) return
  page.value += 1
  await loadPosts(false)
}

async function onToggleFollow() {
  if (!topic.value) return
  if (!session.userId) {
    toast.info('请先登录')
    return
  }
  followLoading.value = true
  try {
    const { data } = await followTopic(topic.value.id)
    topic.value.is_followed = data.data.is_followed
    toast.success(data.data.is_followed ? '已关注话题' : '已取消关注')
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    followLoading.value = false
  }
}

function openPost(p: Post) {
  router.push(`/post/${p.id}`)
}

function openAuthor(p: Post) {
  if (p.author_id && !p.is_anonymous) {
    router.push(`/user/${p.author_id}`)
  }
}

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/')
}

onMounted(async () => {
  await session.validateSession()
  await loadTopic()
  await loadPosts(true)
})

// 路由参数变化时重新加载
watch(topicId, async () => {
  topic.value = null
  posts.value = []
  await loadTopic()
  await loadPosts(true)
})
</script>

<template>
  <main class="page-topic">
    <!-- 顶部固定栏 -->
    <header class="topic-header">
      <div class="header-inner">
        <button class="icon-btn" type="button" aria-label="返回" @click="goBack">
          <Icon name="arrow-left" :size="20" />
        </button>
        <h1 class="header-title">话题详情</h1>
        <button
          v-if="topic"
          class="follow-btn"
          type="button"
          :class="{ 'is-followed': topic.is_followed }"
          :disabled="followLoading"
          @click="onToggleFollow"
        >
          {{ topic.is_followed ? '已关注' : '关注' }}
        </button>
        <span v-else class="icon-btn-placeholder" />
      </div>
    </header>

    <div class="page-container">
      <!-- 加载中 -->
      <div v-if="loading && !topic" class="loading-tip">
        <Icon name="refresh" :size="22" />
        <span>加载中…</span>
      </div>

      <template v-else-if="topic">
        <!-- 话题信息卡 -->
        <section class="topic-info-card">
          <div class="topic-info-head">
            <div class="topic-icon">
              <Icon name="tag" :size="22" color="#fff" />
            </div>
            <div class="topic-info-meta">
              <h2 class="topic-name">#{{ topic.name }}</h2>
              <div class="topic-stats">
                <span>{{ formatCount(topic.post_count) }} 帖子</span>
              </div>
            </div>
            <button
              class="follow-btn follow-btn--lg"
              type="button"
              :class="{ 'is-followed': topic.is_followed }"
              :disabled="followLoading"
              @click="onToggleFollow"
            >
              <Icon :name="topic.is_followed ? 'check' : 'plus'" :size="14" />
              {{ topic.is_followed ? '已关注' : '关注话题' }}
            </button>
          </div>
          <p v-if="topic.description" class="topic-desc">{{ topic.description }}</p>
        </section>

        <!-- 帖子列表标题 -->
        <div class="section-title">
          <span>话题下的帖子</span>
          <span class="section-count">{{ total }}</span>
        </div>

        <!-- 帖子列表 -->
        <div v-if="loading && !posts.length" class="loading-tip">
          <Icon name="refresh" :size="20" />
          <span>加载中…</span>
        </div>

        <div v-else-if="posts.length" class="post-list">
          <article
            v-for="p in posts"
            :key="p.id"
            class="post-item"
            @click="openPost(p)"
          >
            <header class="post-author-row">
              <button
                class="post-avatar"
                :style="(p.author_avatar_url && !p.is_anonymous) ? {} : { background: avatarGradient(p.author_id) }"
                @click.stop="openAuthor(p)"
              >
                <img v-if="p.author_avatar_url && !p.is_anonymous" :src="p.author_avatar_url" :alt="p.author" />
                <span v-else-if="!p.is_anonymous">{{ (p.author || 'U').charAt(0).toUpperCase() }}</span>
                <Icon v-else name="user" :size="14" color="#fff" />
              </button>
              <div class="post-author-meta">
                <div class="post-author-name">
                  {{ p.is_anonymous ? '匿名同学' : p.author }}
                  <span v-if="p.is_anonymous" class="anon-badge">匿名</span>
                  <span v-if="p.is_public === false" class="private-badge">
                    <Icon name="lock" :size="11" />
                    已私密
                  </span>
                </div>
                <div class="post-author-time">
                  {{ timeAgo(p.created_at) }}
                  <span class="dot">·</span>
                  <span class="cat-pill">#{{ p.category || '校园' }}</span>
                </div>
              </div>
            </header>

            <h3 v-if="p.title" class="post-title">{{ p.title }}</h3>
            <p class="post-excerpt">{{ p.content }}</p>

            <div v-if="p.image_urls?.length" class="post-images">
              <img
                v-for="(url, idx) in p.image_urls.slice(0, 3)"
                :key="idx"
                :src="url"
                :alt="`图片${idx + 1}`"
                class="post-thumb"
                loading="lazy"
              />
              <span v-if="p.image_urls.length > 3" class="img-more">+{{ p.image_urls.length - 3 }}</span>
            </div>

            <footer class="post-foot">
              <span class="foot-meta">
                <Icon name="heart" :size="13" />
                {{ formatCount(p.like_count) }}
              </span>
              <span class="foot-meta">
                <Icon name="message-square" :size="13" />
                {{ formatCount(p.comment_count) }}
              </span>
              <span v-if="p.location" class="foot-meta">
                <Icon name="map-pin" :size="13" />
                {{ p.location }}
              </span>
            </footer>
          </article>

          <!-- 加载更多 -->
          <div v-if="hasMore" class="load-more">
            <button
              class="load-more-btn"
              type="button"
              :disabled="loadingMore"
              @click="onLoadMore"
            >
              <Icon v-if="loadingMore" name="refresh" :size="14" />
              <span>{{ loadingMore ? '加载中…' : '加载更多' }}</span>
            </button>
          </div>
          <div v-else class="list-end">没有更多了</div>
        </div>

        <EmptyState v-else icon="tag" text="该话题下还没有帖子" />
      </template>

      <EmptyState v-else icon="tag" text="话题不存在或已被删除" />
    </div>
  </main>
</template>

<style scoped>
.page-topic {
  min-height: 100vh;
  background: var(--bg-100);
  padding-bottom: calc(80px + env(safe-area-inset-bottom));
}

/* 顶部固定栏 */
.topic-header {
  position: sticky;
  top: 0;
  z-index: 50;
  background: rgba(255, 255, 255, 0.95);
  -webkit-backdrop-filter: blur(20px);
  backdrop-filter: blur(20px);
  border-bottom: 0.5px solid var(--bg-300);
  height: 56px;
}
.header-inner {
  max-width: 720px;
  margin: 0 auto;
  height: 100%;
  padding: 0 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.header-title {
  flex: 1;
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  color: var(--text-800);
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  transition: background 0.15s var(--ease-apple);
}
.icon-btn:hover {
  background: var(--bg-200);
}
.icon-btn-placeholder {
  width: 36px;
  height: 36px;
  display: inline-block;
}
.follow-btn {
  height: 30px;
  padding: 0 14px;
  border-radius: 999px;
  border: none;
  background: var(--brand-500);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: all 0.15s var(--ease-apple);
  flex-shrink: 0;
}
.follow-btn:hover:not(:disabled) {
  background: var(--brand-600);
}
.follow-btn.is-followed {
  background: var(--brand-50);
  color: var(--brand-600);
}
.follow-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.follow-btn--lg {
  height: 34px;
  padding: 0 16px;
  font-size: 13px;
}

/* 容器 */
.page-container {
  max-width: 720px;
  margin: 0 auto;
  padding: 16px 16px 24px;
}

/* 加载状态 */
.loading-tip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 0;
  color: var(--text-500);
  font-size: 14px;
}
.loading-tip :deep(svg) {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 话题信息卡 */
.topic-info-card {
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  padding: 20px;
  margin-bottom: 16px;
}
.topic-info-head {
  display: flex;
  align-items: center;
  gap: 14px;
}
.topic-icon {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  background: linear-gradient(135deg, var(--brand-400), var(--brand-600));
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.topic-info-meta {
  flex: 1;
  min-width: 0;
}
.topic-name {
  margin: 0 0 4px;
  font-size: 19px;
  font-weight: 700;
  color: var(--text-800);
  word-break: break-word;
}
.topic-stats {
  font-size: 13px;
  color: var(--text-500);
}
.topic-desc {
  margin: 14px 0 0;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-700);
  word-break: break-word;
}

/* 分区标题 */
.section-title {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding: 8px 4px 12px;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-800);
}
.section-count {
  font-size: 13px;
  color: var(--text-400);
  font-weight: 600;
}

/* 帖子列表 */
.post-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.post-item {
  background: var(--bg-50);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-xs);
  padding: 16px;
  cursor: pointer;
  transition: all 0.15s var(--ease-apple);
}
.post-item:hover {
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}
.post-author-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.post-avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  border: none;
  cursor: pointer;
  display: grid;
  place-items: center;
  color: #fff;
  font-weight: 600;
  font-size: 13px;
  flex-shrink: 0;
  overflow: hidden;
}
.post-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.post-author-meta {
  flex: 1;
  min-width: 0;
}
.post-author-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-800);
  display: flex;
  align-items: center;
  gap: 6px;
}
.anon-badge {
  display: inline-block;
  padding: 1px 6px;
  background: var(--bg-200);
  color: var(--text-500);
  font-size: 10px;
  font-weight: 600;
  border-radius: 4px;
}
.post-author-time {
  font-size: 12px;
  color: var(--text-500);
  margin-top: 2px;
  display: flex;
  align-items: center;
  gap: 4px;
}
.dot {
  opacity: 0.6;
}
.cat-pill {
  color: var(--brand-500);
  font-weight: 500;
}
.post-title {
  margin: 0 0 6px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-800);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.post-excerpt {
  margin: 0;
  font-size: 14px;
  line-height: 1.55;
  color: var(--text-600);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.private-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 6px;
  border-radius: 999px;
  background: rgba(245, 158, 11, 0.12);
  color: #b45309;
  font-size: 11px;
  font-weight: 600;
}
.post-images {
  display: flex;
  gap: 6px;
  margin-top: 10px;
  position: relative;
}
.post-thumb {
  width: 80px;
  height: 80px;
  object-fit: cover;
  border-radius: var(--radius-sm);
  background: var(--bg-100);
}
.img-more {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 80px;
  height: 80px;
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  border-radius: var(--radius-sm);
}
.post-foot {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 0.5px solid var(--bg-200);
}
.foot-meta {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-500);
}

/* 加载更多 */
.load-more {
  text-align: center;
  padding: 16px 0 8px;
}
.load-more-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  border-radius: 999px;
  border: 1px solid var(--bg-300);
  background: var(--bg-50);
  color: var(--text-600);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s var(--ease-apple);
}
.load-more-btn:hover:not(:disabled) {
  border-color: var(--brand-300);
  color: var(--brand-500);
}
.load-more-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.load-more-btn :deep(svg) {
  animation: spin 1s linear infinite;
}
.list-end {
  text-align: center;
  padding: 16px 0 8px;
  font-size: 12px;
  color: var(--text-400);
}

/* 响应式 */
@media (max-width: 560px) {
  .page-container {
    padding: 12px 12px 20px;
  }
  .topic-info-card {
    padding: 16px;
  }
  .topic-icon {
    width: 46px;
    height: 46px;
    border-radius: 12px;
  }
  .topic-name {
    font-size: 17px;
  }
  .post-item {
    padding: 14px;
  }
  .post-thumb {
    width: 72px;
    height: 72px;
  }
  .img-more {
    width: 72px;
    height: 72px;
  }
}
</style>
