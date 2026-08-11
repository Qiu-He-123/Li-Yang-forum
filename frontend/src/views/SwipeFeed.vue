<script setup lang="ts">
/**
 * 沉浸刷流（抖音式整屏卡片，一刷一帖）
 * - 复用 /posts 分页接口 + 点赞/收藏/评论接口，纯前端零后端改动
 * - 移动端全屏，桌面端居中手机式窄栏；底部导航常驻，卡片内容避让
 * - 顶栏：返回瀑布流 / 模式分段切换 / 推荐·最新
 * - 右侧操作栏：头像、点赞、评论、收藏、分享；点击卡片进详情
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { Icon, Segmented, toast } from '../components/native'
import EmptyState from '../components/common/EmptyState.vue'
import BadgeIcon from '../components/common/BadgeIcon.vue'
import { listPosts, sharePost, viewPost } from '../api/post'
import { likeTarget, unlikeTarget, favoritePost, unfavoritePost } from '../api/interaction'
import { useSessionStore } from '../stores/session'
import { useInteractionStore } from '../stores/interaction'
import { useUIStore } from '../stores/ui'
import { formatRelative } from '../utils/time'
import { getCircleMeta, resolveCircleSlug } from '../utils/circleStyle'
import type { Post } from '../types/api'

// keep-alive 需要 name，与 App.vue 的 cachedViewNames 对应
defineOptions({ name: 'SwipeFeedView' })

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const interactionStore = useInteractionStore()
const uiStore = useUIStore()

const PAGE_SIZE = 10

const modeOptions = [
  { label: '瀑布流', value: 'waterfall' },
  { label: '沉浸刷', value: 'swipe' },
]

// 内容视图：hot=推荐 / latest=最新（与首页 Tab 一致）
const feedView = ref<'hot' | 'latest'>(route.query.view === 'latest' ? 'latest' : 'hot')

const posts = ref<Post[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const error = ref('')
const loadMoreLoading = ref(false)
const likeLoading = ref(false)
const favLoading = ref(false)

const scrollEl = ref<HTMLElement | null>(null)
const activeIndex = ref(0)
const viewReported = ref<Set<number>>(new Set())

const hasMore = computed(() => page.value * PAGE_SIZE < total.value)
const currentPost = computed(() => posts.value[activeIndex.value] || null)

function formatCount(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, '') + 'w'
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k'
  return String(n)
}

function firstLine(post: Post): string {
  const raw = post.content || ''
  const line = raw.split('\n').find((l) => l.trim()) || ''
  return line.length > 48 ? line.slice(0, 48) + '…' : line
}

function initial(post: Post): string {
  return (post.author || '?').trim().charAt(0).toUpperCase()
}

function isLiked(post: Post): boolean {
  return interactionStore.likedPostIds.has(post.id)
}

function isFavorited(post: Post): boolean {
  return interactionStore.favoritedPostIds.has(post.id)
}

/** 纯文字帖背景：圈子主题色渐变 */
function textBg(post: Post): string {
  const meta = getCircleMeta(resolveCircleSlug(post))
  return `linear-gradient(165deg, ${meta.cardBg} 0%, ${meta.pillBg} 100%)`
}

function watermarkColor(post: Post): string {
  return getCircleMeta(resolveCircleSlug(post)).pillColor
}

function scrollToTop() {
  if (scrollEl.value) scrollEl.value.scrollTop = 0
}

async function loadFeed() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await listPosts(
      { view: feedView.value, page: 1, page_size: PAGE_SIZE },
      { showGlobalLoading: false, showGlobalError: false },
    )
    const payload = data.data as unknown as { items: Post[]; total: number; page: number; page_size: number }
    posts.value = payload.items
    total.value = payload.total
    page.value = payload.page
    activeIndex.value = 0
    viewReported.value = new Set()
    scrollToTop()
  } catch (err) {
    error.value = (err as Error).message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  if (!hasMore.value || loadMoreLoading.value || loading.value) return
  loadMoreLoading.value = true
  try {
    const nextPage = page.value + 1
    const { data } = await listPosts(
      { view: feedView.value, page: nextPage, page_size: PAGE_SIZE },
      { showGlobalLoading: false, showGlobalError: false },
    )
    const payload = data.data as unknown as { items: Post[]; total: number; page: number; page_size: number }
    // 去重：探索位帖子可能跨页重复
    const existingIds = new Set(posts.value.map((p) => p.id))
    posts.value = [...posts.value, ...payload.items.filter((p) => !existingIds.has(p.id))]
    total.value = payload.total
    page.value = payload.page
  } catch {
    // 触底加载失败静默，滚动再次触发即可
  } finally {
    loadMoreLoading.value = false
  }
}

/** 当前卡片成为主视口时上报浏览量（仅登录用户，每帖一次） */
function reportViewIfNeeded() {
  const post = currentPost.value
  if (!post || !session.userId || viewReported.value.has(post.id)) return
  viewReported.value.add(post.id)
  viewPost(post.id).catch(() => {})
}

let ticking = false
function onScroll() {
  if (ticking) return
  ticking = true
  requestAnimationFrame(() => {
    ticking = false
    const el = scrollEl.value
    if (!el) return
    const h = el.clientHeight || 1
    const idx = Math.round(el.scrollTop / h)
    const next = Math.max(0, Math.min(idx, posts.value.length - 1))
    if (next !== activeIndex.value) {
      activeIndex.value = next
      reportViewIfNeeded()
    }
    // 快到底部时预加载下一页
    if (activeIndex.value >= posts.value.length - 3) {
      loadMore()
    }
  })
}

function switchView(v: 'hot' | 'latest') {
  const changed = v !== feedView.value
  feedView.value = v
  router.replace({ path: '/swipe', query: { view: v } })
  // 点击当前激活项也重新拉取，当作手动刷新
  loadFeed()
  if (!changed) return
}

function onModeChange(v: string | number) {
  if (v === 'waterfall') goWaterfall()
}

function goWaterfall() {
  router.push({ path: '/', query: { view: feedView.value } })
}

function openPost(post: Post) {
  if (post.is_viewable === false) {
    toast.info(post.content || '审核中，暂无法查看原文')
    return
  }
  // 游客也可查看详情
  router.push(`/post/${post.id}`)
}

function goProfile(post: Post) {
  if (post.is_anonymous || !post.author_id) return
  router.push(`/user/${post.author_id}`)
}

async function toggleLike(post: Post) {
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  likeLoading.value = true
  try {
    if (isLiked(post)) {
      const { data } = await unlikeTarget('post', post.id)
      post.like_count = data.data.like_count
      interactionStore.toggleLikedPost(post.id, false)
    } else {
      const { data } = await likeTarget('post', post.id)
      post.like_count = data.data.like_count
      interactionStore.toggleLikedPost(post.id, true)
    }
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    likeLoading.value = false
  }
}

async function toggleFavorite(post: Post) {
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  favLoading.value = true
  try {
    if (isFavorited(post)) {
      await unfavoritePost(post.id)
      interactionStore.toggleFavoritedPost(post.id, false)
      toast.success('已取消收藏')
    } else {
      await favoritePost(post.id)
      interactionStore.toggleFavoritedPost(post.id, true)
      toast.success('已收藏')
    }
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    favLoading.value = false
  }
}

async function onShare(post: Post) {
  const url = `${window.location.origin}/post/${post.id}`
  const title = post.title || firstLine(post)
  let shared = false
  try {
    if (typeof navigator.share === 'function') {
      await navigator.share({ title: '立洋社区', text: title, url })
      shared = true
    } else {
      await navigator.clipboard.writeText(url)
      shared = true
      toast.success('链接已复制，快去分享吧')
    }
  } catch {
    // 用户取消分享或剪贴板不可用：静默
  }
  if (shared) {
    post.share_count = (post.share_count || 0) + 1
    sharePost(post.id).catch(() => {})
  }
}

onMounted(async () => {
  if (session.userId) {
    await interactionStore.loadAll()
  }
  await loadFeed()
  window.addEventListener('resize', onScroll)
})

onUnmounted(() => {
  window.removeEventListener('resize', onScroll)
})

// 从其他入口带 view 参数进入时同步切换
watch(
  () => route.query.view,
  (v) => {
    const next = v === 'latest' ? 'latest' : 'hot'
    if (next !== feedView.value) {
      feedView.value = next
      loadFeed()
    }
  },
)
</script>

<template>
  <main class="swipe-page">
    <div class="swipe-stage">
      <!-- ====== 顶栏：返回 / 模式切换 / 推荐·最新 ====== -->
      <header class="swipe-header">
        <button
          class="hd-btn"
          type="button"
          aria-label="返回瀑布流"
          title="返回瀑布流"
          @click="goWaterfall"
        >
          <Icon name="arrow-left" :size="20" />
        </button>
        <Segmented
          class="hd-mode"
          :model-value="'swipe'"
          :options="modeOptions"
          @change="onModeChange"
        />
        <div class="hd-view" role="tablist" aria-label="内容来源">
          <button
            class="hd-view-btn"
            :class="{ 'is-active': feedView === 'hot' }"
            type="button"
            role="tab"
            :aria-selected="feedView === 'hot'"
            @click="switchView('hot')"
          >
            推荐
          </button>
          <button
            class="hd-view-btn"
            :class="{ 'is-active': feedView === 'latest' }"
            type="button"
            role="tab"
            :aria-selected="feedView === 'latest'"
            @click="switchView('latest')"
          >
            最新
          </button>
        </div>
      </header>

      <!-- ====== 骨架屏 ====== -->
      <div v-if="loading" class="swipe-scroll">
        <div v-for="i in 3" :key="i" class="swipe-card skeleton-card" />
      </div>

      <!-- ====== 加载失败 ====== -->
      <div v-else-if="error && !posts.length" class="swipe-status">
        <Icon name="triangle-alert" :size="40" />
        <p class="status-text">{{ error }}</p>
        <button class="retry-btn" type="button" @click="loadFeed">重新加载</button>
      </div>

      <!-- ====== 空状态 ====== -->
      <EmptyState v-else-if="!posts.length" text="还没有内容，去首页发布第一条吧" icon="file" />

      <!-- ====== 沉浸卡片流 ====== -->
      <div
        v-else
        ref="scrollEl"
        class="swipe-scroll"
        @scroll="onScroll"
      >
        <article
          v-for="post in posts"
          :key="post.id"
          class="swipe-card"
          :class="post.image_urls.length ? 'swipe-card--img' : 'swipe-card--text'"
        >
          <!-- 背景：图片 / 圈子主题色 -->
          <img
            v-if="post.image_urls.length"
            class="card-bg"
            :src="post.image_urls[0]"
            :alt="post.title || post.content.slice(0, 30)"
            draggable="false"
          />
          <div
            v-else
            class="card-bg card-bg--text"
            :style="{ background: textBg(post) }"
            :class="{ 'has-avatar': post.author_avatar_url && !post.is_anonymous }"
          >
            <img
              v-if="post.author_avatar_url && !post.is_anonymous"
              class="text-bg-avatar"
              :src="post.author_avatar_url"
              alt=""
              draggable="false"
            />
            <span class="text-watermark" aria-hidden="true">
              <Icon :name="getCircleMeta(resolveCircleSlug(post)).icon" :size="150" :color="watermarkColor(post)" />
            </span>
          </div>

          <!-- 图片渐变遮罩 -->
          <div v-if="post.image_urls.length" class="card-shade" />

          <!-- 顶部角标 -->
          <span v-if="post.image_urls.length > 1" class="chip chip--count">
            <Icon name="image" :size="12" />
            {{ post.image_urls.length }}图
          </span>
          <span v-if="post.is_public === false" class="chip chip--private">
            <Icon name="lock" :size="11" />
            私密
          </span>

          <!-- ====== 右侧操作栏 ====== -->
          <aside class="rail" @click.stop>
            <button
              class="rail-avatar"
              type="button"
              :disabled="post.is_anonymous || !post.author_id"
              :title="post.is_anonymous ? '匿名用户' : '查看主页'"
              @click="goProfile(post)"
            >
              <img
                v-if="post.author_avatar_url && !post.is_anonymous"
                :src="post.author_avatar_url"
                alt=""
              />
              <span v-else>{{ post.is_anonymous ? '匿' : initial(post) }}</span>
              <BadgeIcon
                v-if="!post.is_anonymous"
                class="rail-avatar-badge"
                :badge="post.author_badge"
                :size="15"
              />
            </button>

            <div class="rail-item">
              <button
                class="rail-btn"
                :class="{ 'is-active': isLiked(post) }"
                type="button"
                :disabled="likeLoading"
                aria-label="点赞"
                @click="toggleLike(post)"
              >
                <Icon :name="isLiked(post) ? 'heart-filled' : 'heart'" :size="30" />
              </button>
              <span class="rail-count">{{ formatCount(post.like_count) }}</span>
            </div>

            <div class="rail-item">
              <button class="rail-btn" type="button" aria-label="评论" @click="openPost(post)">
                <Icon name="message-circle" :size="28" />
              </button>
              <span class="rail-count">{{ formatCount(post.comment_count) }}</span>
            </div>

            <div class="rail-item">
              <button
                class="rail-btn"
                :class="{ 'is-active': isFavorited(post) }"
                type="button"
                :disabled="favLoading"
                aria-label="收藏"
                @click="toggleFavorite(post)"
              >
                <Icon :name="isFavorited(post) ? 'star-filled' : 'star'" :size="28" />
              </button>
              <span class="rail-count">收藏</span>
            </div>

            <div class="rail-item">
              <button class="rail-btn" type="button" aria-label="分享" @click="onShare(post)">
                <Icon name="share" :size="26" />
              </button>
              <span class="rail-count">{{ post.share_count ? formatCount(post.share_count) : '分享' }}</span>
            </div>
          </aside>

          <!-- ====== 底部信息 ====== -->
          <div
            class="card-info"
            :class="post.image_urls.length ? 'card-info--img' : 'card-info--text'"
          >
            <div class="info-panel">
              <div class="info-top">
                <span
                  class="circle-pill"
                  :style="{
                    color: getCircleMeta(resolveCircleSlug(post)).pillColor,
                    background: getCircleMeta(resolveCircleSlug(post)).pillBg,
                  }"
                >
                  {{ post.category || '校园' }}
                </span>
                <span v-if="post.explored" class="chip chip--explore">探索</span>
              </div>
              <h2 class="info-title">{{ post.title || firstLine(post) }}</h2>
              <p class="info-desc">{{ post.content }}</p>
              <div class="info-meta">
                <span class="info-author">
                  {{ post.is_anonymous ? '匿名同学' : post.author }}
                  <BadgeIcon v-if="!post.is_anonymous" :badge="post.author_badge" :size="14" />
                </span>
                <span class="info-time">{{ formatRelative(post.created_at) }} · {{ post.school }}</span>
              </div>
              <button class="enter-btn" type="button" @click.stop="openPost(post)">
                <span>进入帖子</span>
                <Icon name="arrow-right" :size="16" />
              </button>
            </div>
          </div>
        </article>

        <!-- 触底加载中 -->
        <div v-if="loadMoreLoading" class="load-more-hint">
          <span class="load-more-spinner" aria-hidden="true"></span>
          加载更多…
        </div>
        <div v-else-if="!hasMore" class="load-more-hint">已经刷到底啦</div>
      </div>
    </div>
  </main>
</template>

<style scoped>
*, *::before, *::after { box-sizing: border-box; }

/* ====== 页面骨架：桌面端深色背景 + 居中手机式窄栏 ====== */
.swipe-page {
  min-height: 100vh;
  min-height: 100dvh;
  background:
    radial-gradient(1100px 700px at 50% -10%, #26262a 0%, #101012 55%, #0b0b0d 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-family: var(--font-sans, inherit);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.swipe-stage {
  position: relative;
  width: 100%;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
  background: #000;
}

@media (min-width: 769px) {
  .swipe-stage {
    max-width: 480px;
    height: calc(100dvh - 44px);
    border-radius: 28px;
    border: 1px solid rgba(255, 255, 255, 0.08);
    box-shadow: 0 24px 80px -20px rgba(0, 0, 0, 0.75);
  }
}

/* ====== 顶栏 ====== */
.swipe-header {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: calc(env(safe-area-inset-top) + 10px) 12px 12px;
  background: linear-gradient(180deg, rgba(0, 0, 0, 0.55), transparent);
}

.hd-btn {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.35);
  color: #fff;
  cursor: pointer;
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
  transition: background 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.hd-btn:hover {
  background: rgba(0, 0, 0, 0.55);
}

.hd-mode {
  flex: 1;
  min-width: 0;
}

.hd-view {
  flex: none;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.35);
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
}
.hd-view-btn {
  padding: 5px 11px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: rgba(255, 255, 255, 0.75);
  font-family: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 150ms cubic-bezier(0.32, 0.72, 0, 1), color 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.hd-view-btn.is-active {
  background: rgba(255, 255, 255, 0.92);
  color: #111;
}

/* ====== 滚动容器 ====== */
.swipe-scroll {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
  scroll-snap-type: y mandatory;
  scroll-behavior: smooth;
}

.swipe-card {
  position: relative;
  flex: none;
  width: 100%;
  height: 100%;
  scroll-snap-align: start;
  scroll-snap-stop: always;
  overflow: hidden;
  background: #000;
  user-select: none;
  -webkit-user-select: none;
}

.card-bg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  pointer-events: none;
}
.card-bg--text {
  position: relative;
}
.text-bg-avatar {
  position: absolute;
  inset: -48px;
  width: calc(100% + 96px);
  height: calc(100% + 96px);
  object-fit: cover;
  filter: blur(38px) saturate(1.15);
  transform: scale(1.12);
  opacity: 0.92;
  pointer-events: none;
}
.card-bg--text.has-avatar::after {
  content: '';
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.28);
  pointer-events: none;
}
.text-watermark {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -52%);
  opacity: 0.16;
  pointer-events: none;
}

.card-shade {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 58%;
  background: linear-gradient(180deg, transparent, rgba(0, 0, 0, 0.18) 38%, rgba(0, 0, 0, 0.72) 82%, rgba(0, 0, 0, 0.86));
  pointer-events: none;
}

/* ====== 角标 ====== */
.chip {
  position: absolute;
  top: calc(env(safe-area-inset-top) + 62px);
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.4;
  background: rgba(0, 0, 0, 0.45);
  color: #fff;
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  pointer-events: none;
}
.chip--count {
  right: 14px;
}
.chip--private {
  left: 14px;
  color: #fbbf24;
}

/* ====== 右侧操作栏 ====== */
.rail {
  position: absolute;
  right: 12px;
  bottom: calc(100px + env(safe-area-inset-bottom));
  z-index: 20;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 18px;
}

.rail-avatar {
  position: relative;
  width: 46px;
  height: 46px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.9);
  background: linear-gradient(135deg, #66abff, #007aff);
  color: #fff;
  font-size: 16px;
  font-weight: 700;
  display: grid;
  place-items: center;
  overflow: visible;
  padding: 0;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
}
.rail-avatar:disabled {
  cursor: default;
  opacity: 0.95;
}
.rail-avatar img {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  object-fit: cover;
  display: block;
}
.rail-avatar-badge {
  position: absolute;
  right: -7px;
  bottom: -5px;
  background: rgba(0, 0, 0, 0.5);
  border-radius: 50%;
  padding: 1px;
}

.rail-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
}
.rail-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: #fff;
  cursor: pointer;
  transition: transform 120ms cubic-bezier(0.32, 0.72, 0, 1);
}
.rail-btn:active {
  transform: scale(0.86);
}
.rail-btn:disabled {
  opacity: 0.5;
}
.rail-btn.is-active {
  color: #ff4d6d;
}
.rail-count {
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.6);
  font-variant-numeric: tabular-nums;
}

/* ====== 底部信息 ====== */
.card-info {
  position: absolute;
  z-index: 10;
}
.card-info--img {
  left: 0;
  right: 64px;
  bottom: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 0 16px calc(92px + env(safe-area-inset-bottom));
}
.card-info--text {
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 22px calc(84px + env(safe-area-inset-bottom));
}
.info-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 100%;
}
.card-info--text .info-panel {
  align-items: center;
  text-align: center;
  width: 100%;
  max-width: 420px;
  padding: 26px 22px 22px;
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.52);
  -webkit-backdrop-filter: blur(22px);
  backdrop-filter: blur(22px);
  border: 0.5px solid rgba(255, 255, 255, 0.65);
  box-shadow: 0 14px 44px rgba(0, 0, 0, 0.14);
}

.info-top {
  display: flex;
  align-items: center;
  gap: 8px;
}
.circle-pill {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 999px;
  letter-spacing: 0.01em;
  white-space: nowrap;
  flex-shrink: 0;
}
.chip--explore {
  position: static;
  background: linear-gradient(135deg, #34c759, #2e8dff);
  color: #fff;
}

.info-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  line-height: 1.4;
  color: #fff;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
  text-shadow: 0 1px 6px rgba(0, 0, 0, 0.45);
}

.info-desc {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.55;
  color: rgba(255, 255, 255, 0.92);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
  text-shadow: 0 1px 5px rgba(0, 0, 0, 0.45);
}

.info-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.85);
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.5);
}
.info-author {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.info-time {
  white-space: nowrap;
  opacity: 0.85;
}

/* 纯文字帖：深色文字，覆盖圈子的浅色背景 */
.card-info--text .info-title {
  font-size: 26px;
  font-weight: 800;
  -webkit-line-clamp: 3;
}
.card-info--text .info-desc {
  font-size: 16px;
  line-height: 1.6;
  -webkit-line-clamp: 6;
  max-width: 100%;
}
.card-info--text .info-title,
.card-info--text .info-desc,
.card-info--text .info-meta {
  color: var(--text-800);
  text-shadow: none;
}
.card-info--text .info-meta {
  color: var(--text-500);
}

/* 「进入帖子」按钮：不点卡片直达，需要显式点击进入 */
.enter-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  padding: 10px 22px;
  border: none;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.94);
  color: #111;
  font-family: inherit;
  font-size: 13.5px;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.28);
  transition: transform 120ms cubic-bezier(0.32, 0.72, 0, 1),
              background 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.enter-btn:hover {
  background: #fff;
}
.enter-btn:active {
  transform: scale(0.95);
}

/* ====== 骨架屏 ====== */
.skeleton-card {
  background: #1c1c1f;
}
.skeleton-card::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(100deg, transparent 30%, rgba(255, 255, 255, 0.06) 50%, transparent 70%);
  background-size: 220% 100%;
  animation: skeleton-shimmer 1.4s linear infinite;
}
@keyframes skeleton-shimmer {
  from { background-position: 140% 0; }
  to { background-position: -80% 0; }
}

/* ====== 状态 ====== */
.swipe-status {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: rgba(255, 255, 255, 0.6);
  padding: 0 32px;
}
.status-text {
  margin: 0;
  font-size: 13px;
  text-align: center;
  color: rgba(255, 255, 255, 0.55);
}
.retry-btn {
  padding: 9px 26px;
  border: none;
  border-radius: 999px;
  background: var(--brand-500);
  color: #fff;
  font-family: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.retry-btn:hover {
  background: var(--brand-600);
}

.load-more-hint {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 64px;
  color: rgba(255, 255, 255, 0.55);
  font-size: 12px;
  background: #0e0e10;
}
.load-more-spinner {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.2);
  border-top-color: #fff;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 空状态在深色页面上换浅色文字 */
.swipe-page :deep(.empty-text) {
  color: rgba(255, 255, 255, 0.55);
}
.swipe-page :deep(.empty-icon) {
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.4);
}

/* 短屏（iPhone SE / 小屏安卓）：压缩间距与字号，避免信息被底部导航遮挡 */
@media (max-height: 700px) {
  .card-info--img {
    padding-bottom: calc(78px + env(safe-area-inset-bottom));
  }
  .rail {
    bottom: calc(84px + env(safe-area-inset-bottom));
    gap: 14px;
  }
  .card-info--text .info-panel {
    padding: 18px 16px 16px;
    border-radius: 22px;
  }
  .card-info--text .info-title {
    font-size: 22px;
  }
  .card-info--text .info-desc {
    font-size: 14.5px;
    -webkit-line-clamp: 4;
  }
  .enter-btn {
    margin-top: 6px;
    padding: 8px 18px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .swipe-scroll {
    scroll-behavior: auto;
  }
  .skeleton-card::after {
    animation: none;
  }
}
</style>
