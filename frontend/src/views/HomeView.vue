<script setup lang="ts">
/**
 * 首页（独立于圈子页）
 * 严格对齐设计稿：发现页.html 的 Feed 部分（去掉热门圈子入口）
 * - 顶部固定栏：标题「首页」居中 + 右侧搜索图标
 * - 帖子动态：Tab 切换（推荐 / 最新）+ 双列瀑布流
 * - 底部 TabBar：浮动药丸（首页 active）
 */
import { computed, onActivated, onMounted, onUnmounted, ref, watch } from 'vue'
import { useFadeUpdate } from '../composables/useFadeUpdate'
// keep-alive 需要 name，与 App.vue 的 cachedViewNames 对应
defineOptions({ name: 'HomeView' })

// SWR 刷新渐变：数据变化时递增 key 触发 CSS 淡入动画
const { fadeActive, triggerFade } = useFadeUpdate()
/** 首页/广场卡片宠物体积：与桌面漂浮宠(PET_SIZE=120)一致 */
const CARD_PET_SIZE = 120
import { useRoute, useRouter } from 'vue-router'

import EmptyState from '../components/common/EmptyState.vue'
import AiStatusBadge from '../components/common/AiStatusBadge.vue'
import BadgeIcon from '../components/common/BadgeIcon.vue'
import PostListSkeleton from '../components/post/PostListSkeleton.vue'
import PostPetBox from '../components/post/PostPetBox.vue'
import InfiniteScrollFooter from '../components/common/InfiniteScrollFooter.vue'
import DownloadAppButton from '../components/DownloadAppButton.vue'
import { useInfiniteScroll } from '../composables/useInfiniteScroll'
import { usePetAiTracker } from '../composables/usePetAiTracker'
import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import TodayGuessHero from '../components/home/TodayGuessHero.vue'
import { useSessionStore } from '../stores/session'
import { useUserStore } from '../stores/user'
import { useUIStore } from '../stores/ui'
import { usePostStore } from '../stores/post'
import { useCircleStore } from '../stores/circle'
import { useAnnouncementStore } from '../stores/announcement'
import { useInteractionStore } from '../stores/interaction'
import { getCircleMeta, resolveCircleSlug } from '../utils/circleStyle'
import { viewPost } from '../api/post'
import { fetchHomeStats } from '../api/announcement'
import { fetchPublicSettings } from '../api/settings'
import { formatRelative } from '../utils/time'
import type { Circle, Post } from '../types/api'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const userStore = useUserStore()
const uiStore = useUIStore()
const postStore = usePostStore()
const circleStore = useCircleStore()
const announcementStore = useAnnouncementStore()
const interactionStore = useInteractionStore()

// 游客引导卡片：首次以游客身份浏览时提示注册价值（只弹一次）
const guestGuideVisible = ref(false)
const GUEST_GUIDE_KEY = 'ly:guest-guide-shown'

function maybeShowGuestGuide() {
  if (session.userId) return
  if (localStorage.getItem(GUEST_GUIDE_KEY)) return
  // 延迟出现，避免打扰首屏
  setTimeout(() => {
    guestGuideVisible.value = true
  }, 900)
}

function dismissGuestGuide() {
  guestGuideVisible.value = false
  localStorage.setItem(GUEST_GUIDE_KEY, '1')
}

watch(
  () => session.userId,
  (id) => {
    if (id) {
      guestGuideVisible.value = false
      localStorage.setItem(GUEST_GUIDE_KEY, '1')
    }
  },
)

const { loading: loadMoreLoading, error: loadMoreError, retry: retryLoadMore } = useInfiniteScroll({
  hasMore: computed(() => feedHasMore.value),
  onLoadMore: () => feedLoadMore(),
  containerSelector: '.page-home',
})

// 首页透明统计：在线人数 / 今日发帖 / 注册人数
const homeStats = ref({ online_count: 0, logged_in_count: 0, visitor_count: 0, today_post_count: 0, total_users: 0 })
let homeStatsTimer: ReturnType<typeof setInterval> | null = null

// 首页顶部滚动字幕（后台「其他设置」配置；为空则不显示）
const marqueeItems = ref<string[]>([])
const marqueeChunks = computed(() => {
  if (!marqueeItems.value.length) return []
  const joined = marqueeItems.value.join('　·　')
  // 内容复制一份，配合 translateX(-50%) 实现无缝循环
  return [joined, joined]
})

async function loadMarquee() {
  try {
    const { data } = await fetchPublicSettings()
    marqueeItems.value = data.data.marquee_items || []
  } catch {
    marqueeItems.value = []
  }
}

async function loadHomeStats() {
  try {
    const { data } = await fetchHomeStats({
      showGlobalLoading: false,
      showGlobalError: false,
    })
    homeStats.value = data.data
  } catch {
    // 静默失败：不影响首页浏览
  }
}

function formatStatsNum(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, '') + 'w'
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k'
  return String(n)
}

// 首页 Tab：关注 / 推荐 / 各圈子（与广场一致，默认推荐）
// · 关注    → 关注流   view=following
// · 推荐    → 热门推荐 view=hot（加圈子筛选=空）
// · 圈子slug → 该圈子全部 view=all + category=slug
// 首页展示老版瀑布流帖子，不再内嵌组局（组局已迁至广场页）。
const sortedCircles = computed(() =>
  [...circleStore.circles]
    .filter((c) => c.slug !== 'default')
    .sort((a, b) => (a.sort_order ?? 99) - (b.sort_order ?? 99)),
)
type FeedTabKey = 'follow' | (string & {})
const feedTabs = computed<{ key: FeedTabKey; label: string }[]>(() => {
  const tabs: { key: FeedTabKey; label: string }[] = [
    { key: 'follow', label: '关注' },
    { key: 'newest', label: '最新' },
    { key: 'recommend', label: '推荐' },
  ]
  for (const c of sortedCircles.value) tabs.push({ key: c.slug as FeedTabKey, label: c.name })
  return tabs
})
const tabKeys = computed(() => new Set(feedTabs.value.map((t) => t.key)))
const activeTab = computed<FeedTabKey>(() => {
  const v = String(route.query.tab ?? 'recommend')
  return tabKeys.value.has(v) ? (v as FeedTabKey) : 'recommend'
})

type FeedMode = 'posts' | 'gatherings' | 'rank'
function feedModeOf(_key: FeedTabKey): FeedMode {
  return 'posts' // 首页统一展示帖子瀑布流
}
function tabToView(key: FeedTabKey): 'all' | 'hot' | 'following' {
  if (key === 'follow') return 'following'
  if (key === 'recommend') return 'hot'
  return 'all'
}
function tabToCategory(key: FeedTabKey): string {
  if (key === 'follow' || key === 'newest' || key === 'recommend') return ''
  return key // 圈子 slug
}
function applyHomeView(key: FeedTabKey) {
  postStore.setView(tabToView(key))
  postStore.setCategory(tabToCategory(key))
  postStore.setPage(1)
}

const feedMode = computed(() => feedModeOf(activeTab.value))
const feedLoading = computed(() => postStore.loading)
const feedError = computed(() => postStore.error)
const feedHasMore = computed(() => postStore.hasMore)
const feedItems = computed<Post[]>(() => postStore.posts)
async function feedLoadMore() {
  await postStore.loadMore()
}

function switchTab(key: FeedTabKey) {
  router.replace({ query: { tab: key } })
}

watch(
  activeTab,
  async (key) => {
    applyHomeView(key)
    await postStore.loadPosts()
  },
)

// ====== 精选入口（2x2 等大网格，同级权重，Apple 风格） ======
interface QuickEntry {
  key: string
  slug: string
  name: string
  desc: string
  icon: string
}

const quickEntries: QuickEntry[] = [
  { key: 'make-friends', slug: 'bottle', name: '交朋友', desc: '随机匹配 · 60秒开聊', icon: 'heart' },
  { key: 'activity-center', slug: 'activities', name: '活动中心', desc: '每日福利', icon: 'gift' },
  { key: 'hot-games', slug: 'match', name: '热门玩法', desc: '宠物小游戏', icon: 'gamepad' },
  { key: 'pet-market', slug: 'pet', name: '宠物市集', desc: '云养萌宠', icon: 'shopping-bag' },
]

function formatCount(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, '') + 'w'
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k'
  return String(n)
}

function circleOf(post: Post): Circle | undefined {
  const slug = post.category || ''
  return circleStore.circles.find((c) => c.slug === slug || c.name === post.category)
}

onMounted(async () => {
  // 性能优化：validateSession 后台并行，不阻塞第一波加载
  // 基于 localStorage 中的 session.userId 决定第二波请求
  const valid = await session.validateSession()
  // 第一波：公告 + 圈子列表 + 首页统计（与 session 校验并行）
  await Promise.all([
    announcementStore.loadAnnouncements(),
    circleStore.loadCircles(),
    loadHomeStats(),
    loadMarquee(),
  ])
  // 在线人数定时刷新（30s），让首页统计实时反映在线状态
  homeStatsTimer = setInterval(loadHomeStats, 60_000)
  // 初始化：应用首页 feed 视图（关注/推荐/圈子）
  const firstKey = activeTab.value
  applyHomeView(firstKey)

  const hasUserId = !!session.userId
  maybeShowGuestGuide()
  async function loadInitialFeed() {
    await postStore.loadPosts()
  }
  if (hasUserId) {
    await Promise.all([
      userStore.loadProfile(),
      interactionStore.loadAll(),
      loadInitialFeed(),
    ])
  } else {
    if (valid) {
      await Promise.all([
        userStore.loadProfile(),
        interactionStore.loadAll(),
        loadInitialFeed(),
      ])
    } else {
      await loadInitialFeed()
    }
  }
})

/** Feed 首次加载失败后的手动重试（帖子模式） */
async function retryFeed() {
  applyHomeView(activeTab.value)
  postStore.setPage(1)
  await postStore.loadPosts()
}

/**
 * keep-alive 重新激活时：恢复首页 view + 从缓存即时展示 + SWR 后台刷新。
 *
 * 关键：KeepAlive 首次挂载时 onMounted 和 onActivated 都会触发！
 * onMounted 是 async，第一波 await 让出执行权时 onActivated 触发，
 * 此时 loading 还是 false → 会和 onMounted 的 loadPosts 并发，导致
 * "参数错误" + 重复加载变慢。用 skipFirstActivated 跳过首次触发。
 */
let skipFirstActivated = true
onActivated(() => {
  if (skipFirstActivated) {
    skipFirstActivated = false
    return
  }
  const key = activeTab.value
  const expectedView = tabToView(key)
  const expectedCat = tabToCategory(key)
  if (postStore.activeView !== expectedView) {
    postStore.setView(expectedView)
  }
  postStore.setCategory(expectedCat)
  if (postStore.restoreFromCache()) {
    postStore.ensureFresh().then((changed) => { if (changed) triggerFade() })
  } else {
    postStore.loadPosts()
  }
})

async function onJoinCircle(e: Event, slug: string) {
  e.stopPropagation()
  e.preventDefault()
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  const circle = circleStore.circles.find((c) => c.slug === slug)
  if (!circle) return
  try {
    const joined = await circleStore.toggleJoin(circle)
    toast.success(joined ? '已加入' : '已退出')
  } catch (err) {
    toast.error((err as Error).message)
  }
}

async function openPost(post: Post) {
  // 游客可查看帖子详情；仅登录用户记录浏览数
  if (session.userId) {
    try {
      await viewPost(post.id)
    } catch {
      /* ignore */
    }
  }
  router.push(`/post/${post.id}`)
}

function openSearch() {
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  router.push('/search')
}

function openCreatePost() {
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  router.push('/publish')
}

function openFeature(slug: string) {
  // 未登录：先弹登录框
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  if (slug === 'bottle') {
    router.push('/bottle')
    return
  }
  if (slug === 'activities') {
    router.push('/activities')
    return
  }
  if (slug === 'match') {
    // 热门玩法 = 宠物小游戏中心（原误跳到 /match 配对页，改为游乐场）
    router.push('/pet-play')
    return
  }
  if (slug === 'pet') {
    router.push('/pet-shop')
    return
  }
  router.push(`/circle/${slug}`)
}

/** 接单 / 放单大厅：未登录先弹登录框，已登录进入接单大厅 tab */
function openOrders() {
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  router.push('/orders?tab=hall')
}

/** 统计入口：未登录先弹登录框，已登录才进列表页 */
function onStatsClick(path: string) {
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  router.push(path)
}

function isJoined(slug: string): boolean {
  const c = circleStore.circles.find((x) => x.slug === slug)
  return !!c?.is_joined
}

// AI 审核轮询（仅登录用户）
let auditPollTimer: ReturnType<typeof setInterval> | null = null
const AUDIT_POLL_INTERVAL = 6000

function stopAuditPolling() {
  if (auditPollTimer) {
    clearInterval(auditPollTimer)
    auditPollTimer = null
  }
}

function startAuditPollingIfNeeded() {
  if (!session.userId || !postStore.hasPendingAudit) {
    stopAuditPolling()
    return
  }
  if (auditPollTimer) return
  auditPollTimer = setInterval(async () => {
    if (postStore.hasPendingAudit) await postStore.silentRefresh()
    else stopAuditPolling()
  }, AUDIT_POLL_INTERVAL)
}

watch(
  () => postStore.hasPendingAudit,
  (has) => {
    if (has) startAuditPollingIfNeeded()
    else stopAuditPolling()
  },
)

onUnmounted(() => {
  stopAuditPolling()
  if (homeStatsTimer) {
    clearInterval(homeStatsTimer)
    homeStatsTimer = null
  }
})
</script>

<template>
  <main class="page-home">
    <!-- ====== 顶部固定栏：标题「首页」居中 + 右侧搜索图标 ====== -->
<header class="site-header" role="banner">
<DownloadAppButton />
<div class="header-inner">
        <div class="header-side header-side--left" aria-hidden="true"></div>
        <h1 class="header-title">同伴圈·首页</h1>
        <div class="header-side header-side--right">
          <button class="icon-btn" type="button" aria-label="搜索" @click="openSearch">
            <Icon name="search" :size="20" />
          </button>
        </div>
      </div>
    </header>

    <!-- ====== 主内容 ====== -->
    <div class="page-container">
      <!-- ====== 滚动字幕：后台「其他设置」配置，空则不显示 ====== -->
      <div v-if="marqueeChunks.length" class="home-marquee" role="marquee" aria-label="滚动公告">
        <span class="marquee-icon" aria-hidden="true">
          <Icon name="megaphone" :size="15" />
        </span>
        <div class="marquee-viewport">
          <div class="marquee-track">
            <span v-for="(chunk, i) in marqueeChunks" :key="i" class="marquee-chunk">{{ chunk }}</span>
          </div>
        </div>
      </div>

      <!-- ====== 今日竞猜焦点区 ====== -->
      <TodayGuessHero />

      <!-- ====== 精选入口：左大卡 + 右三小卡，不对称布局 ====== -->
      <section class="quick-entry" aria-label="精选入口">
        <button
          v-for="f in quickEntries"
          :key="f.key"
          class="qe-card"
          type="button"
          @click="openFeature(f.slug)"
        >
          <span class="qe-card__icon">
            <Icon :name="f.icon" :size="22" />
          </span>
          <div class="qe-card__body">
            <h3 class="qe-card__title">{{ f.name }}</h3>
            <p class="qe-card__desc">{{ f.desc }}</p>
          </div>
        </button>
      </section>

      <!-- ====== 接单 / 放单大厅：竞猜式渐变 Hero 卡片 ====== -->
      <button
        type="button"
        class="orders-hero"
        @click="openOrders"
        :aria-label="'进入接单大厅'"
      >
        <span class="orders-hero__decor orders-hero__decor--1" aria-hidden="true"></span>
        <span class="orders-hero__decor orders-hero__decor--2" aria-hidden="true"></span>
        <div class="orders-hero__left">
          <span class="orders-hero__tag">
            <span class="orders-hero__dot" aria-hidden="true"></span>
            接单 · 放单
          </span>
          <h3 class="orders-hero__title">接单大厅</h3>
          <p class="orders-hero__desc">校园互助 · 找活赚钱 · 免费发布悬赏</p>
          <div class="orders-hero__stats">
            <span class="orders-hero__stat">
              <b>0 抽成</b>
              <i>平台免费</i>
            </span>
            <span class="orders-hero__sep" aria-hidden="true"></span>
            <span class="orders-hero__stat">
              <b>全品类</b>
              <i>代买代送 · 助教跑腿</i>
            </span>
          </div>
        </div>
        <span class="orders-hero__cta">
          去接单
          <Icon name="chevron-right" :size="14" />
        </span>
      </button>

      <!-- ====== 透明统计：在线人数 / 今日发帖 / 注册人数 ====== -->
      <section class="home-stats" aria-label="站点统计">
        <div class="stats-item stats-item--link" title="查看在线用户" @click="onStatsClick('/stats/online')">
          <span class="stats-top">
            <span class="stats-dot stats-dot--green" aria-hidden="true"></span>
            <span class="stats-num">{{ formatStatsNum(homeStats.logged_in_count) }}</span>
          </span>
          <span class="stats-label">在线中</span>
        </div>
        <div class="stats-item stats-item--link" title="查看在线游客" @click="onStatsClick('/stats/guests')">
          <span class="stats-top">
            <Icon name="user" :size="14" />
            <span class="stats-num">{{ formatStatsNum(homeStats.visitor_count) }}</span>
          </span>
          <span class="stats-label">游客在线</span>
        </div>
        <div class="stats-item stats-item--link" title="查看今日发布" @click="onStatsClick('/stats/today-posts')">
          <span class="stats-top">
            <Icon name="file" :size="14" />
            <span class="stats-num">{{ formatStatsNum(homeStats.today_post_count) }}</span>
          </span>
          <span class="stats-label">今日发布</span>
        </div>
        <div class="stats-item stats-item--link" title="查看注册用户" @click="onStatsClick('/stats/users')">
          <span class="stats-top">
            <Icon name="users" :size="14" />
            <span class="stats-num">{{ formatStatsNum(homeStats.total_users) }}</span>
          </span>
          <span class="stats-label">注册人数</span>
        </div>
      </section>

      <!-- ====== 帖子动态 Feed（Tab 切换 + 瀑布流）====== -->
      <section class="feed-section" aria-label="帖子动态">
        <div class="feed-tabs" role="tablist" aria-label="帖子分类">
          <button
            v-for="t in feedTabs"
            :key="t.key"
            class="feed-tab"
            type="button"
            :class="{ 'is-active': activeTab === t.key }"
            role="tab"
            :aria-selected="activeTab === t.key"
            @click="switchTab(t.key)"
          >
            {{ t.label }}
          </button>
        </div>

        <PostListSkeleton v-if="feedLoading" :count="5" />

        <!-- ===== 帖子瀑布流（关注/推荐/圈子 全走此分支） ===== -->
        <template v-else-if="feedModeOf(activeTab) === 'posts'">
          <div v-if="postStore.posts.length" :class="{ 'swr-updated': fadeActive }" class="feed">
            <article
              v-for="post in postStore.posts"
              :key="post.id"
              class="card"
              :class="post.image_urls?.length || post.video_urls?.length ? 'card--image' : 'card--text'"
              :style="
                !post.image_urls?.length && !post.video_urls?.length && post.category
                  ? { background: getCircleMeta(resolveCircleSlug(post)).cardBg }
                  : {}
              "
              @click="openPost(post)"
            >
              <img
                v-if="post.image_urls?.length"
                class="card-img"
                :src="post.image_urls[0]"
                :alt="post.title || post.content.slice(0, 30)"
                loading="lazy"
              />
              <video
                v-else-if="post.video_urls?.length"
                class="card-img card-video"
                :src="post.video_urls[0]"
                preload="metadata"
                muted
                playsinline
              ></video>
              <div class="card-body">
                <div class="card-top">
                  <span
                    class="circle-pill"
                    :style="{
                      color: getCircleMeta(resolveCircleSlug(post)).pillColor,
                      background: getCircleMeta(resolveCircleSlug(post)).pillBg,
                    }"
                    >#{{ circleOf(post)?.name || post.category || '校园' }}</span
                  >
                  <AiStatusBadge
                    :status="post.ai_status"
                    :reject-reason="post.reject_reason"
                  />
                </div>
                <h3 class="card-title" :class="{ 'card-title--text': !post.image_urls?.length }">
                  <template v-if="!post.image_urls?.length">
                    <Icon
                      :name="getCircleMeta(resolveCircleSlug(post)).icon"
                      :size="14"
                      :color="getCircleMeta(resolveCircleSlug(post)).iconColor"
                      class="title-icon"
                    />
                  </template>
                  <span v-if="post.is_public === false" class="private-badge">
                    <Icon name="lock" :size="12" />
                    已私密
                  </span>
                  <span class="title-text">{{ post.title || post.content }}</span>
                </h3>
                <div class="card-meta">
                  <div class="card-author">
                    <img
                      v-if="post.author_avatar_url && !post.is_anonymous"
                      :src="post.author_avatar_url"
                      :alt="post.author"
                      class="avatar avatar-sm avatar-img"
                    />
                    <span
                      v-else
                      class="avatar avatar-sm"
                      :class="`av-${(post.author_id || 0) % 5 + 1}`"
                      aria-hidden="true"
                    >{{ post.is_anonymous ? '匿' : (post.author || 'U').charAt(0).toUpperCase() }}</span>
                    <BadgeIcon v-if="!post.is_anonymous" :badge="post.author_badge" :size="13" />
                    <span class="author-name">{{ post.is_anonymous ? '匿名同学' : post.author }}</span>
                  </div>
                  <div class="card-stats">
                    <span class="post-time">{{ formatRelative(post.created_at) }}</span>
                    <div class="card-likes">
                      <Icon name="heart" :size="14" />
                      <span class="like-count">{{ formatCount(post.like_count) }}</span>
                    </div>
                  </div>
                </div>
              </div>
              <!-- 发帖人的宠物：浮在卡片内右下角留白处，可拖动可移动、随机动作、不挡文字；
                   自己帖子默认隐藏卡片内宠物，由桌面漂浮宠自动飞入 -->
              <PostPetBox
                v-if="!post.is_anonymous && post.author_id"
                :user-id="post.author_id"
                :size="CARD_PET_SIZE"
                :self="post.author_id === session.userId"
                :author-name="post.author"
              />
            </article>
          </div>

          <div v-else-if="postStore.error" class="feed-error">
            <p class="feed-error-text">加载失败，请检查网络后重试</p>
            <button class="feed-error-btn" type="button" @click="retryFeed">重新加载</button>
          </div>
          <EmptyState v-else text="暂无帖子，发布第一条校园动态。" />
        </template>

        <!-- 底部状态：放在瀑布流容器之外，避免多列布局把它排到帖子右边 -->
        <InfiniteScrollFooter
          :loading="loadMoreLoading"
          :error="loadMoreError"
          :has-more="feedHasMore"
          :has-items="feedItems.length > 0"
          @retry="retryLoadMore"
        />
      </section>
    </div>

    <!-- 游客引导卡片：登录后解锁互动 -->
    <Transition name="guide">
      <div v-if="!session.userId && guestGuideVisible" class="guest-guide">
        <div class="guest-guide-body">
          <div class="guest-guide-title">
            <Icon name="log-in" :size="16" />
            登录同伴圈，解锁全部功能
          </div>
          <div class="guest-guide-desc">
            点赞 / 评论 / 收藏 / 发帖 / 徽章 / 签到 / 漂流瓶，注册只需 30 秒
          </div>
          <div class="guest-guide-actions">
            <button class="guide-btn guide-btn--ghost" type="button" @click="dismissGuestGuide">先逛逛</button>
            <button class="guide-btn guide-btn--primary" type="button" @click="uiStore.openAuthDialog()">
              立即登录 / 注册
            </button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- 右下角发帖 FAB -->
    <button class="home-fab" type="button" aria-label="发布动态" @click="openCreatePost">
      <Icon name="plus" :size="26" color="#fff" />
    </button>
  </main>
</template>

<style scoped>
*, *::before, *::after { box-sizing: border-box; }

.page-home {
  /* 首页背景加深一档（原 #F7F8FB → 规范 #F2F3F7），清爽不刺眼 */
  --home-bg-100: #F2F3F7;
  /* 未选中次级文字加深，避免发飘 */
  --home-desc-500: #555566;
  --home-tab-unselected: #606474;
  /* 顶部图标/搜索颜色加深到 #222 */
  --home-icon-deep: #222222;

  min-height: 100vh;
  background: var(--home-bg-100);
  padding-top: 56px;
  padding-bottom: calc(56px + 28px + env(safe-area-inset-bottom));
  color: var(--text-800);
  font-family: var(--font-sans, inherit);
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* SITE HEADER */
.site-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  height: 56px;
  background: #ffffff;
  border-bottom: 0.5px solid #e9e7ef;
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
.header-side--right { justify-content: flex-end; gap: 6px; }
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
  color: var(--home-icon-deep);  /* 铃铛/搜索图标 #222，不再浅灰发虚 */
  background: transparent;
  border: none;
  cursor: pointer;
  transition: background 150ms cubic-bezier(0.32, 0.72, 0, 1),
              color 150ms cubic-bezier(0.32, 0.72, 0, 1);
  flex-shrink: 0;
}
.icon-btn:hover {
  background: rgba(0,0,0,0.05);
  color: #000;
}

/* PAGE CONTAINER */
.page-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px 20px calc(56px + env(safe-area-inset-bottom));
}

/* MARQUEE（滚动字幕：顶部公告条，细长不遮挡主内容） */
.home-marquee {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  margin: 0 0 16px;
  padding: 0 10px 0 8px;
  background: linear-gradient(90deg, var(--brand-50), #eef6ff 55%, var(--bg-50));
  border: 0.5px solid rgba(0, 122, 255, 0.14);
  border-radius: 12px;
  overflow: hidden;
}
.marquee-icon {
  flex: none;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 8px;
  background: var(--bg-50);
  color: var(--brand-500);
  box-shadow: var(--shadow-2xs);
}
.marquee-viewport {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 6%, #000 94%, transparent);
  mask-image: linear-gradient(90deg, transparent, #000 6%, #000 94%, transparent);
}
.marquee-track {
  display: inline-flex;
  white-space: nowrap;
  will-change: transform;
  animation: marquee-scroll 24s linear infinite;
}
.marquee-chunk {
  padding-right: 32px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-600);
  letter-spacing: 0.01em;
}
.home-marquee:hover .marquee-track {
  animation-play-state: paused;
}
@keyframes marquee-scroll {
  from { transform: translateX(0); }
  to { transform: translateX(-50%); }
}
@media (prefers-reduced-motion: reduce) {
  .marquee-track { animation: none; }
}

/* FEATURE ENTRY (随机交友主卡 + 表白墙/匿名树洞并列) */
.feature-entry {
  margin-bottom: 24px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.feature-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 18px;
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  border: none;
  cursor: pointer;
  text-align: left;
  transition: transform 150ms cubic-bezier(0.32, 0.72, 0, 1),
              box-shadow 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.feature-card:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}
/* 随机交友主卡：图标/标题/小文字垂直居中 */
.feature-card--main {
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  padding: 20px 18px;
  gap: 8px;
}
.feature-card--main .feature-text {
  align-items: center;
}
.feature-card--main .feature-arrow {
  display: none;
}

/* 线性图标：无渐变、无毛玻璃，纯描边圆框 */
.feature-ic--line {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-50);
  border: 1.5px solid var(--brand-500);
  color: var(--brand-500);
  flex-shrink: 0;
}
.feature-card--main .feature-ic--line {
  width: 48px;
  height: 48px;
  border-color: var(--brand-500);
}
.feature-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.feature-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-800);
  line-height: 1.2;
}
.feature-card--sub .feature-name {
  font-size: 14px;
}
.feature-desc {
  font-size: 12px;
  color: var(--text-400);
  line-height: 1.2;
}
.feature-arrow {
  color: var(--text-400);
  flex-shrink: 0;
}
.feature-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}
.feature-card--sub {
  padding: 14px 14px;
}

/* 透明统计条 */
.home-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0;
  padding: 12px 8px;
  margin-bottom: 18px;
  background: var(--bg-50);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-xs);
}
.stats-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  min-width: 0;
  padding: 2px 4px;
  color: var(--text-500);
}
.stats-item + .stats-item {
  border-left: 0.5px solid var(--bg-300);
}
.stats-top {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  min-width: 0;
}
.stats-item--link {
  cursor: pointer;
  user-select: none;
}
.stats-item--link:hover {
  opacity: 0.8;
}
.stats-item--link:active {
  transform: scale(0.97);
}
.stats-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
}
.stats-dot--green {
  background: #34c759;
  box-shadow: 0 0 0 3px rgba(52, 199, 89, 0.18);
  animation: pulse-online 1.6s ease-in-out infinite;
}
@keyframes pulse-online {
  0%, 100% { box-shadow: 0 0 0 3px rgba(52, 199, 89, 0.18); }
  50% { box-shadow: 0 0 0 5px rgba(52, 199, 89, 0.08); }
}
.stats-num {
  max-width: 100%;
  font-weight: 700;
  color: var(--text-800);
  font-size: clamp(12px, 4.2vw, 15px);
  line-height: 1.2;
  white-space: nowrap;
}
.stats-label {
  max-width: 100%;
  color: var(--text-400);
  font-size: clamp(10px, 3vw, 12px);
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.stats-divider {
  width: 1px;
  height: 14px;
  background: var(--bg-300);
}

/* FEED TABS（全部 / 为你推荐 / 游戏组局 / 现实组局）
   改造：未选中 #606474；选中 加粗、字色主色、2px 下划线；去原来的胶囊底色。 */
.feed-tabs {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 14px;
  padding: 0 2px;
  border-bottom: 0.5px solid rgba(0,0,0,0.06);
  overflow-x: auto;
  white-space: nowrap;
  scrollbar-width: none;
}
.feed-tabs::-webkit-scrollbar { display: none; }
.feed-tab {
  position: relative;
  padding: 8px 2px 10px;
  font-size: 15px;
  font-weight: 400;
  color: var(--home-tab-unselected);   /* 未选中 #606474，不再太淡 */
  background: transparent;
  flex: 0 0 auto;
  border: none;
  cursor: pointer;
  transition: color 150ms cubic-bezier(0.32, 0.72, 0, 1),
              font-weight 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.feed-tab::after {
  /* 下划线 2px：宽度跟随文字（不写死）*/
  content: '';
  position: absolute;
  left: 50%;
  bottom: 2px;
  width: 60%;
  height: 2px;
  border-radius: 2px;
  background: transparent;
  transform: translateX(-50%) scaleX(0);
  transform-origin: center;
  transition: background 150ms ease, transform 180ms cubic-bezier(0.32, 0.72, 0, 1);
}
.feed-tab:hover { color: var(--brand-600); }
.feed-tab.is-active {
  color: var(--brand-600);
  font-weight: 700;   /* 选中态加粗 */
}
.feed-tab.is-active::after {
  background: var(--brand-500);
  transform: translateX(-50%) scaleX(1);
  /* 选中下划线颜色饱和度提高：用偏深的主色 */
  background: #0a6cff;
}

.feed-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 0;
  color: var(--text-500);
  font-size: 13px;
}
.feed-loading :deep(svg) {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0); }
  to { transform: rotate(360deg); }
}

/* FEED masonry
   一屏最多 5 张：卡片按比例放大（桌面 2 列大卡片），
   图片高度按 4 张一组、文字卡高度按 3 张一组略有差异，
   形成错落又整齐的瀑布流。 */
.feed {
  column-count: 2;
  column-gap: 14px;
  column-fill: balance;
}

/* Feed 加载失败提示 */
.feed-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 40px 16px;
  color: var(--text-500);
  font-size: 13px;
}
.feed-error-btn {
  padding: 8px 22px;
  border-radius: 999px;
  border: none;
  background: var(--brand-500);
  color: #fff;
  font-family: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.feed-error-btn:hover {
  background: var(--brand-600);
}
.feed-error-btn:active {
  transform: scale(0.96);
}

/* 骨架屏与 2 列大卡片保持一致，避免加载完成时布局跳动 */
.feed-section :deep(.skeleton-feed) {
  column-count: 2;
  column-gap: 14px;
}

/* POST CARDS */
.card {
  position: relative;
  display: block;
  width: 100%;
  max-width: 100%;
  break-inside: avoid;
  margin-bottom: 16px;
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: 0 3px 14px rgba(23, 32, 64, 0.12);
  border: 1px solid rgba(23, 32, 64, 0.09);
  cursor: pointer;
  text-align: left;
  /* 防止内容撑开卡片宽度 */
  min-width: 0;
  word-break: break-word;
  overflow-wrap: anywhere;
  transition: box-shadow 150ms cubic-bezier(0.32, 0.72, 0, 1),
              transform 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.card:hover {
  box-shadow: 0 8px 22px rgba(23, 32, 64, 0.18);
  transform: translateY(-1px);
}
.card-img {
  width: 100%;
  height: 240px;
  display: block;
  object-fit: cover;
}
/* 视频帖封面帧：不拦截点击（点卡片进详情播放），高度跟随视频实际比例 */
.card-video {
  background: #000;
  pointer-events: none;
  height: auto !important;
  max-height: 420px;
  object-fit: contain;
}
.card:nth-of-type(4n+1) .card-img { height: 280px; }
.card:nth-of-type(4n+2) .card-img { height: 205px; }
.card:nth-of-type(4n+3) .card-img { height: 255px; }
.card:nth-of-type(4n)   .card-img { height: 215px; }

/* ===== 首页房间卡片（图1样式：单列圆角卡片，TT语音风格） ===== */
.room-feed {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 0 0 8px;
}

.room-card {
  position: relative;
  display: flex;
  flex-direction: column;
  background: #FFFFFF;
  border-radius: 22px;
  padding: 16px 18px 16px;
  cursor: pointer;
  text-align: left;
  border: 1px solid #D9DDE8;
  box-shadow: 0 3px 14px rgba(23, 32, 64, 0.12);
  transition: transform 150ms ease, box-shadow 150ms ease;
  overflow: hidden;
}
.room-card:hover {
  box-shadow: 0 8px 22px rgba(23, 32, 64, 0.18);
  transform: translateY(-1px);
}
.room-card:active {
  transform: scale(0.985);
}

/* 顶部：标签 + 更多 */
.room-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 16px;
}
.room-card__tags {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  min-width: 0;
}
.room-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.4;
  white-space: nowrap;
}
.room-tag__emoji {
  font-size: 15px;
  line-height: 1;
}
.room-tag--category {
  background: #F2F3F8;
  color: #333;
}
.room-tag--host {
  background: linear-gradient(135deg, #5DD9C1, #38C9B0);
  color: #fff;
}

.room-card__more {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: transparent;
  border: none;
  color: #B0B4C0;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 150ms ease, color 150ms ease;
  padding: 0;
}
.room-card__more:hover {
  background: rgba(0,0,0,0.05);
  color: #666;
}
.room-card__more :deep(svg) {
  width: 20px;
  height: 20px;
}

/* 中部：头像 + 信息 */
.room-card__body {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 0;
  flex: 1;
}
.room-card__avatar-wrap {
  position: relative;
  flex-shrink: 0;
}
.room-card__avatar {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  object-fit: cover;
  display: inline-block;
  background: #E5E5EA;
  border: 2.5px solid #fff;
  box-shadow: 0 2px 6px rgba(0,0,0,0.08);
}
.room-card__avatar--ph {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: 700;
  color: #fff;
}
.room-card__avatar-badge {
  position: absolute;
  right: -1px;
  bottom: -1px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #FF4D8D;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  color: #fff;
  border: 2px solid #FFFFFF;
  line-height: 1;
  font-weight: 500;
}

.room-card__info {
  flex: 1;
  min-width: 0;
  padding-top: 2px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.room-card__title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: #1A1A2E;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.room-card__hostname {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin: 2px 0 2px;
  font-size: 12px;
  font-weight: 600;
  color: #6a6a7a;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.room-card__hostname :deep(svg) {
  width: 12px;
  height: 12px;
}
.room-card__subtitle {
  margin: 0;
  font-size: 14px;
  color: #8E8E9E;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: flex;
  align-items: center;
  gap: 4px;
}
.room-card__sub-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: #A0A4B4;
}
.room-card__sub-icon :deep(svg) {
  width: 14px;
  height: 14px;
}
.room-card__rank {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #999;
  line-height: 1.3;
}

/* 底部：右下角统计 */
.room-card__foot {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 20px;
  margin-top: 8px;
  padding-top: 0;
}
.room-card__stat {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 15px;
  color: #8E8E9E;
  font-weight: 500;
}
.room-card__stat :deep(svg) {
  width: 20px;
  height: 20px;
  color: #9BA0B0;
}

/* Mobile adjustments */
@media (max-width: 768px) {
  .room-feed {
    gap: 10px;
  }
  .room-card {
    padding: 14px 14px 14px;
    border-radius: 18px;
  }
  .room-card__avatar {
    width: 52px;
    height: 52px;
  }
  .room-card__avatar--ph {
    font-size: 20px;
  }
  .room-card__title {
    font-size: 19px;
  }
  .room-card__subtitle {
    font-size: 13px;
  }
  .room-tag {
    font-size: 12px;
    padding: 3px 10px;
  }
  .room-card__foot {
    gap: 16px;
  }
  .room-card__stat {
    font-size: 14px;
  }
  .room-card__stat :deep(svg) {
    width: 18px;
    height: 18px;
  }
}

/* 纯文字卡：给基准最小高度 + 轻微高度节奏，与图片卡保持接近的体量 */
.card--text {
  display: flex;
  flex-direction: column;
  /* text card height ~ half of image card; max-height caps long text */
  min-height: 176px;
  max-height: 208px;
}
.card--text:nth-of-type(3n+1) { min-height: 192px; }
.card--text:nth-of-type(3n)   { min-height: 168px; }
.card--text .card-body {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  flex: 1;
  overflow: hidden;
}
.card-body {
  padding: 16px 18px 18px;
}

/* 桌面端：2 列大卡片，一屏最多 5 张 */
@media (min-width: 769px) {
  .feed {
    column-count: 2;
    column-gap: 20px;
  }
  .feed-section :deep(.skeleton-feed) {
    column-gap: 20px;
  }
  .card-img {
    height: 360px;
  }
  .card:nth-of-type(4n+1) .card-img { height: 440px; }
  .card:nth-of-type(4n+2) .card-img { height: 340px; }
  .card:nth-of-type(4n+3) .card-img { height: 390px; }
  .card:nth-of-type(4n)   .card-img { height: 355px; }
  .card--text {
    min-height: 248px;
    max-height: 296px;
  }
  .card--text:nth-of-type(3n+1) { min-height: 268px; }
  .card--text:nth-of-type(3n)   { min-height: 232px; }
}
.card-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.circle-pill {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 999px;
  letter-spacing: 0.01em;
  white-space: nowrap;
  flex-shrink: 0;
}
.join-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  flex-shrink: 0;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  color: var(--bg-50);
  background: var(--brand-500);
  border: none;
  cursor: pointer;
  transition: background 150ms cubic-bezier(0.32, 0.72, 0, 1),
              color 150ms cubic-bezier(0.32, 0.72, 0, 1),
              transform 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.join-btn:hover { background: var(--brand-600); }
.join-btn:active { transform: scale(0.94); }
.join-btn.is-joined {
  background: var(--bg-200);
  color: var(--text-400);
}
.join-btn.is-joined:hover {
  background: var(--bg-300);
  color: var(--text-500);
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
.card-title {
  margin: 0 0 12px;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.45;
  color: var(--text-800);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}
.card--text .card-body { padding: 18px; }
.card-title--text {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  -webkit-line-clamp: 3;
  font-size: 15px;
  line-height: 1.5;
}
.title-icon {
  flex-shrink: 0;
  margin-top: 3px;
}
.title-text {
  flex: 1;
  min-width: 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}
.card-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.card-author {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  flex: 1;
}
.avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  flex-shrink: 0;
  overflow: hidden;
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  background: var(--bg-200);
}
.avatar-sm { width: 28px; height: 28px; }
.avatar-img {
  object-fit: cover;
  display: block;
}
.av-1 { background: linear-gradient(135deg, #66abff, #007aff); }
.av-2 { background: linear-gradient(135deg, #34c759, #2e8dff); }
.av-3 { background: linear-gradient(135deg, #ff9500, #007aff); }
.av-4 { background: linear-gradient(135deg, #5856d6, #0064d6); }
.av-5 { background: linear-gradient(135deg, #d1d1d6, #8e8e93); }
.author-name {
  font-size: 13px;
  color: var(--text-500);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.card-likes {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--text-400);
  flex-shrink: 0;
}
.like-count {
  font-size: 13px;
  color: var(--text-400);
}
.card-stats {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}
/* 发帖人宠物小方框：位于作者与统计之间的留白处，不挤占内容 */
.post-pet-inline {
  margin: 0 2px;
  flex-shrink: 0;
}
.post-time {
  font-size: 12px;
  color: var(--text-400);
  white-space: nowrap;
}

/* 游客引导卡片 */
.guest-guide {
  position: fixed;
  left: 16px;
  right: 16px;
  bottom: calc(84px + env(safe-area-inset-bottom));
  z-index: 95;
  max-width: 520px;
  margin: 0 auto;
  background: rgba(255, 255, 255, 0.97);
  -webkit-backdrop-filter: blur(20px);
  backdrop-filter: blur(20px);
  border: 1px solid var(--bg-300);
  border-radius: 18px;
  box-shadow: 0 16px 40px -10px rgba(0, 0, 0, 0.18);
  padding: 14px 16px;
}
.guest-guide-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.guest-guide-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-800);
}
.guest-guide-desc {
  font-size: 12px;
  color: var(--text-500);
  line-height: 1.5;
}
.guest-guide-actions {
  display: flex;
  gap: 8px;
  margin-top: 6px;
}
.guide-btn {
  flex: 1;
  padding: 9px 0;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  font-family: inherit;
  transition: transform 0.15s, opacity 0.15s;
}
.guide-btn:active {
  transform: scale(0.98);
}
.guide-btn--ghost {
  background: var(--bg-100);
  color: var(--text-600);
}
.guide-btn--primary {
  background: var(--brand-500);
  color: #fff;
}

/* 引导卡片动画 */
.guide-enter-active,
.guide-leave-active {
  transition: opacity 0.25s, transform 0.25s;
}
.guide-enter-from,
.guide-leave-to {
  opacity: 0;
  transform: translateY(12px);
}

/* ============ 右下角发帖 FAB ============
   改造：蓝色加深（去掉过亮浅蓝），去掉过重外发光，仅保留轻微阴影。 */
.home-fab {
  position: fixed;
  right: max(16px, calc((100vw - 720px) / 2 + 16px));
  bottom: calc(80px + env(safe-area-inset-bottom));
  width: 56px;
  height: 56px;
  border-radius: 50%;
  border: 1px solid rgba(0,0,0,0.06);
  cursor: pointer;
  /* 蓝加深：偏稳重实色过渡，不爆亮 */
  background: linear-gradient(135deg, #2e6bff 0%, #1e4fe0 60%, #1942c2 100%);
  /* 仅轻微阴影，不做 AI 廉价外发光 */
  box-shadow: 0 8px 18px rgba(30, 79, 224, 0.24), 0 2px 4px rgba(0, 0, 0, 0.08);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  z-index: 60;
  transition: transform 150ms ease, box-shadow 150ms ease, filter 150ms ease;
}
.home-fab:hover { transform: translateY(-2px); filter: brightness(1.04); box-shadow: 0 10px 22px rgba(30, 79, 224, 0.3), 0 3px 6px rgba(0,0,0,0.1); }
.home-fab:active { transform: scale(0.95); filter: brightness(0.98); }

/* RESPONSIVE Mobile */
@media (max-width: 768px) {
  .page-home {
    padding-top: 48px;
    padding-bottom: calc(52px + env(safe-area-inset-bottom));
  }
  .site-header { height: 48px; }
  .header-inner { padding: 0 12px; gap: 8px; }
  .header-title { font-size: 17px; }
  .icon-btn { width: 34px; height: 34px; }
  .icon-btn :deep(svg) { width: 19px; height: 19px; }
  .page-container { padding: 14px 12px 24px; }
  .home-marquee { height: 34px; margin-bottom: 14px; }
  .marquee-chunk { font-size: 12px; }
  .feature-entry { margin-bottom: 18px; gap: 8px; }
  .feature-card { padding: 14px 14px; }
  .feature-card--main { padding: 18px 14px; }
  .feature-card--sub { padding: 12px 12px; }
  .feature-ic--line { width: 40px; height: 40px; }
  .feature-card--main .feature-ic--line { width: 44px; height: 44px; }
  .feature-name { font-size: 14px; }
  .feature-card--sub .feature-name { font-size: 13px; }
  .feature-desc { font-size: 11px; }
  .feature-row { gap: 8px; }
  .feed-tab { padding: 5px 13px; font-size: 12.5px; }
  .feed { column-gap: 10px; }
  .card {
    margin-bottom: 12px;
    border-radius: calc(var(--radius-lg) * 0.8);
  }
  .card-img { border-radius: calc(var(--radius-lg) * 0.8) calc(var(--radius-lg) * 0.8) 0 0; }
  .card-body { padding: 12px 14px 14px; }
  .card-top { margin-bottom: 10px; gap: 6px; }
  .circle-pill { font-size: 11px; padding: 3px 8px; }
  .join-btn { font-size: 10px; padding: 2px 8px; }
  .card-title { font-size: 14px; margin-bottom: 10px; line-height: 1.4; }
  .card--text .card-body { padding: 14px; }
  .avatar-sm { width: 24px; height: 24px; }
  .author-name { font-size: 12px; }
  .like-count { font-size: 12px; }
  .card-likes :deep(svg) { width: 14px; height: 14px; }
  .title-icon { margin-top: 2px; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
  }
}

/* ============ 精选入口（2x2 等大网格，同级权重，Apple 风格） ============
   改造：图标底色饱和度 +15%（不再褪色感），下方文字 desc：#555566。
   每个卡片给一个独立色变量，后续再换色只改 --icon-bg。 */
.quick-entry {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  margin: 0 0 16px;
}
.qe-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 14px 14px 16px;
  background: #ffffff;
  border: 1px solid rgba(0,0,0,0.04);
  border-radius: 14px;
  box-shadow: 0 2px 8px rgba(17,24,39,0.04);
  text-align: left;
  font-family: inherit;
  cursor: pointer;
  transition: transform 0.15s var(--ease-apple), box-shadow 0.15s var(--ease-apple);
}
.qe-card:hover {
  box-shadow: 0 4px 14px rgba(17,24,39,0.08);
}
.qe-card:active {
  transform: scale(0.98);
}

/* —— 接单大厅：竞猜式蓝紫渐变 Hero 卡片 —— */
.orders-hero {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  margin: 4px 0 14px;
  padding: 16px 18px;
  border: none;
  border-radius: 18px;
  color: #fff;
  text-align: left;
  cursor: pointer;
  overflow: hidden;
  isolation: isolate;
  background: linear-gradient(135deg, #5856d6 0%, #007aff 100%);
  box-shadow: 0 6px 16px rgba(88, 86, 214, 0.28);
  transition: box-shadow 0.25s var(--ease-apple), transform 0.15s var(--ease-apple);
}
.orders-hero:hover {
  box-shadow: 0 10px 24px rgba(88, 86, 214, 0.32);
  transform: translateY(-1px);
}
.orders-hero:active {
  transform: scale(0.98);
}
.orders-hero__decor {
  position: absolute;
  border-radius: 50%;
  z-index: -1;
  pointer-events: none;
}
.orders-hero__decor--1 {
  width: 200px;
  height: 200px;
  background: rgba(255, 255, 255, 0.08);
  top: -80px;
  right: -60px;
}
.orders-hero__decor--2 {
  width: 140px;
  height: 140px;
  background: rgba(255, 255, 255, 0.05);
  bottom: -40px;
  left: -30px;
}
.orders-hero__left {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}
.orders-hero__tag {
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  font-weight: 600;
  font-size: 12px;
}
.orders-hero__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #ffd60a;
  animation: ordersPulse 1.6s infinite;
}
@keyframes ordersPulse {
  0%   { box-shadow: 0 0 0 0 rgba(255, 214, 10, 0.6); }
  70%  { box-shadow: 0 0 0 8px rgba(255, 214, 10, 0); }
  100% { box-shadow: 0 0 0 0 rgba(255, 214, 10, 0); }
}
.orders-hero__title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: -0.01em;
}
.orders-hero__desc {
  margin: 0;
  font-size: 13px;
  opacity: 0.9;
}
.orders-hero__stats {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 2px;
}
.orders-hero__stat {
  display: flex;
  flex-direction: column;
  line-height: 1.15;
}
.orders-hero__stat b {
  font-size: 15px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.orders-hero__stat i {
  font-style: normal;
  font-size: 10.5px;
  color: rgba(255, 255, 255, 0.65);
  margin-top: 2px;
}
.orders-hero__sep {
  width: 1px;
  height: 26px;
  background: rgba(255, 255, 255, 0.25);
}
.orders-hero__cta {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
  padding: 10px 20px;
  border-radius: 999px;
  background: #fff;
  color: #5856d6;
  font-weight: 700;
  font-size: 14px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.18);
}
.orders-hero__cta :deep(svg) {
  width: 14px;
  height: 14px;
}

/* —— 每个入口一个独立底色（与名字语义一致，整体饱和度在原蓝紫/粉/绿/橙的基础上 +15%）—— */
.qe-card:nth-of-type(1) .qe-card__icon { /* 交朋友 · 玫红（+15%饱和） */
  background: #ffdfe7;
  color: #D6336C;
}
.qe-card:nth-of-type(2) .qe-card__icon { /* 活动中心 · 橙 */
  background: #ffe7cc;
  color: #E87719;
}
.qe-card:nth-of-type(3) .qe-card__icon { /* 热门玩法 · 蓝紫 */
  background: #e0e0ff;
  color: #6E54E6;
}
.qe-card:nth-of-type(4) .qe-card__icon { /* 宠物市集 · 绿 */
  background: #d7f0de;
  color: #2F9E57;
}

.qe-card__icon {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: var(--brand-50);
  color: var(--brand-500);
  display: flex;
  align-items: center;
  justify-content: center;
}
.qe-card__icon :deep(svg) {
  width: 22px;
  height: 22px;
}
.qe-card__body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}
.qe-card__title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #202028;    /* 标题也略微加深，不飘 */
  line-height: 1.3;
  letter-spacing: -0.01em;
}
.qe-card__desc {
  margin: 0;
  font-size: 12px;
  color: var(--home-desc-500);   /* 规范 #555566：远距离可读 */
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
@media (max-width: 420px) {
  .quick-entry { gap: 8px; }
  .qe-card { padding: 12px 12px 12px 14px; border-radius: 12px; gap: 10px; }
  .qe-card__icon { width: 36px; height: 36px; border-radius: 9px; }
  .qe-card__icon :deep(svg) { width: 20px; height: 20px; }
  .qe-card__title { font-size: 13px; }
  .qe-card__desc { font-size: 11px; }
}
</style>
