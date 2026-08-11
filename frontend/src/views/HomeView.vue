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
import { useRoute, useRouter } from 'vue-router'

import EmptyState from '../components/common/EmptyState.vue'
import AiStatusBadge from '../components/common/AiStatusBadge.vue'
import BadgeIcon from '../components/common/BadgeIcon.vue'
import PostListSkeleton from '../components/post/PostListSkeleton.vue'
import InfiniteScrollFooter from '../components/common/InfiniteScrollFooter.vue'
import { Dialog as NativeDialog } from '../components/native'
import { useInfiniteScroll } from '../composables/useInfiniteScroll'
import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
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
  hasMore: computed(() => postStore.hasMore),
  onLoadMore: () => postStore.loadMore(),
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

// 首页 Tab：推荐 / 最新（后端 view=hot/latest，匿名也可访问）
const feedView = computed<'hot' | 'latest'>(() => (route.query.view === 'latest' ? 'latest' : 'hot'))

// 首页特色入口
// - 随机交友：独占一行（大卡片），跳转独立漂流瓶页面（不再是帖子流）
// - 表白墙 / 匿名树洞：并列小卡片
// 图标线性化，避免渐变/毛玻璃等过时效果
const featureMain = {
  slug: 'bottle',
  name: '随机交友',
  icon: 'shuffle',
  desc: '投瓶子 / 在线匹配',
}

const featureSub = [
  {
    slug: 'confess',
    name: '表白墙',
    icon: 'heart',
    desc: '勇敢表达心意',
  },
  {
    slug: 'treehole',
    name: '匿名树洞',
    icon: 'lock',
    desc: '匿名倾诉心事',
  },
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
  homeStatsTimer = setInterval(loadHomeStats, 30_000)
  postStore.setView(feedView.value)
  // 用 localStorage 的 userId 立即判断（validateSession 结果回填到 store）
  const hasUserId = !!session.userId
  maybeShowGuestGuide()
  if (hasUserId) {
    // 第二波：登录用户的互动数据 + 帖子 feed（全部并行）
    await Promise.all([
      userStore.loadProfile(),
      interactionStore.loadAll(),
      postStore.loadPosts(),
    ])
  } else {
    // 匿名用户：等 validateSession 结果确认是否真的未登录
    if (valid) {
      await Promise.all([
        userStore.loadProfile(),
        interactionStore.loadAll(),
        postStore.loadPosts(),
      ])
    } else {
      // 匿名用户也能看首页 feed
      await postStore.loadPosts()
    }
  }
})

async function onViewChange(view: 'hot' | 'latest') {
  postStore.setView(view)
  postStore.setPage(1)
  await postStore.loadPosts()
}

/** Feed 首次加载失败后的手动重试 */
async function retryFeed() {
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
    return // 首次由 onMounted 处理，不重复加载
  }
  // 恢复首页 view（可能被圈子页改成 'all'）
  if (postStore.activeView !== feedView.value) {
    postStore.setView(feedView.value)
  }
  // SWR：有缓存先展示旧数据，后台刷新；无缓存则正常加载
  if (postStore.restoreFromCache()) {
    // 数据变化时触发渐变动画（先不变 → 拉回后渐变过渡）
    postStore.ensureFresh().then((changed) => { if (changed) triggerFade() })
  } else {
    postStore.loadPosts()
  }
})

// 监听路由 query.view 变化（从发帖页跳转过来时自动加载对应视图）
watch(
  () => route.query.view,
  async (newView) => {
    const v = newView === 'latest' ? 'latest' : 'hot'
    if (v !== postStore.activeView) {
      postStore.setView(v)
      postStore.setPage(1)
      await postStore.loadPosts()
    }
  },
)

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

/** 进入沉浸刷流前先弹确认框（内测阶段提示文案） */
const swipeConfirmVisible = ref(false)

function goSwipe() {
  swipeConfirmVisible.value = true
}

function confirmSwipe() {
  swipeConfirmVisible.value = false
  router.push({ path: '/swipe', query: { view: feedView.value } })
}

function openFeature(slug: string) {
  // 随机交友入口跳转独立的漂流瓶页面（不再是圈子帖子流）
  if (slug === 'bottle') {
    if (!session.userId) {
      uiStore.openAuthDialog()
      return
    }
    router.push('/bottle')
    return
  }
  router.push(`/circle/${slug}`)
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
      <div class="header-inner">
        <div class="header-side header-side--left" aria-hidden="true"></div>
        <h1 class="header-title">立洋社区·首页</h1>
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

      <!-- ====== 特色入口：随机交友（独占一行）+ 表白墙/匿名树洞（并列）====== -->
      <section class="feature-entry" aria-label="特色功能">
        <!-- 随机交友：主卡片，独占一行 -->
        <button
          class="feature-card feature-card--main"
          type="button"
          @click="openFeature(featureMain.slug)"
        >
          <span class="feature-ic feature-ic--line" aria-hidden="true">
            <Icon :name="featureMain.icon" :size="26" />
          </span>
          <span class="feature-text">
            <span class="feature-name">{{ featureMain.name }}</span>
            <span class="feature-desc">{{ featureMain.desc }}</span>
          </span>
          <span class="feature-arrow" aria-hidden="true">
            <Icon name="arrow-right" :size="18" />
          </span>
        </button>

        <!-- 表白墙 / 匿名树洞：并列小卡片 -->
        <div class="feature-row">
          <button
            v-for="item in featureSub"
            :key="item.slug"
            class="feature-card feature-card--sub"
            type="button"
            @click="openFeature(item.slug)"
          >
            <span class="feature-ic feature-ic--line" aria-hidden="true">
              <Icon :name="item.icon" :size="20" />
            </span>
            <span class="feature-text">
              <span class="feature-name">{{ item.name }}</span>
              <span class="feature-desc">{{ item.desc }}</span>
            </span>
          </button>
        </div>
      </section>

      <!-- ====== 透明统计：在线人数 / 今日发帖 / 注册人数 ====== -->
      <section class="home-stats" aria-label="站点统计">
        <div class="stats-item">
          <span class="stats-dot stats-dot--green" aria-hidden="true"></span>
          <span class="stats-num">{{ formatStatsNum(homeStats.online_count) }}</span>
          <span class="stats-label">在线中</span>
        </div>
        <span class="stats-divider" aria-hidden="true"></span>
        <div class="stats-item" title="未登录的游客人数">
          <Icon name="user" :size="14" />
          <span class="stats-num">{{ formatStatsNum(homeStats.visitor_count) }}</span>
          <span class="stats-label">游客在线</span>
        </div>
        <span class="stats-divider" aria-hidden="true"></span>
        <div class="stats-item">
          <Icon name="file" :size="14" />
          <span class="stats-num">{{ formatStatsNum(homeStats.today_post_count) }}</span>
          <span class="stats-label">今日发布</span>
        </div>
        <span class="stats-divider" aria-hidden="true"></span>
        <div class="stats-item">
          <Icon name="users" :size="14" />
          <span class="stats-num">{{ formatStatsNum(homeStats.total_users) }}</span>
          <span class="stats-label">注册人数</span>
        </div>
      </section>

      <!-- ====== 帖子动态 Feed（Tab 切换 + 瀑布流）====== -->
      <section class="feed-section" aria-label="帖子动态">
        <div class="feed-tabs" role="tablist" aria-label="帖子来源">
          <button
            class="feed-tab"
            type="button"
            :class="{ 'is-active': feedView === 'hot' }"
            role="tab"
            :aria-selected="feedView === 'hot'"
            @click="router.replace({ query: { view: 'hot' } }); onViewChange('hot')"
          >
            推荐
          </button>
          <button
            class="feed-tab"
            type="button"
            :class="{ 'is-active': feedView === 'latest' }"
            role="tab"
            :aria-selected="feedView === 'latest'"
            @click="router.replace({ query: { view: 'latest' } }); onViewChange('latest')"
          >
            最新
          </button>
          <button
            class="feed-tab feed-tab--mode"
            type="button"
            @click="goSwipe"
          >
            <Icon name="play" :size="13" />
            刷一刷
          </button>
        </div>

        <PostListSkeleton v-if="postStore.loading" :count="5" />

        <!-- :class swr-updated：SWR 刷新数据变化时渐变过渡（文字逐字淡变+图片滑动），不销毁 DOM 保持滚动 -->
        <div v-else-if="postStore.posts.length" :class="{ 'swr-updated': fadeActive }" class="feed">
          <article
            v-for="post in postStore.posts"
            :key="post.id"
            class="card"
            :class="post.image_urls?.length ? 'card--image' : 'card--text'"
            :style="
              !post.image_urls?.length && post.category
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
          </article>
        </div>

        <div v-else-if="postStore.error" class="feed-error">
          <p class="feed-error-text">加载失败，请检查网络后重试</p>
          <button class="feed-error-btn" type="button" @click="retryFeed">重新加载</button>
        </div>
        <EmptyState v-else text="暂无帖子，发布第一条校园动态。" />

        <!-- 底部状态：放在瀑布流容器之外，避免多列布局把它排到帖子右边 -->
        <InfiniteScrollFooter
          :loading="loadMoreLoading"
          :error="loadMoreError"
          :has-more="postStore.hasMore"
          :has-items="postStore.posts.length > 0"
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
            登录立洋社区，解锁全部功能
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

    <!-- 刷一刷进入确认 -->
    <NativeDialog
      v-model="swipeConfirmVisible"
      title="进入刷一刷"
      width="360px"
      :close-on-overlay="true"
    >
      <p class="swipe-confirm-text">我们正在持续完成此项目，目前非常的烂，真的要进入吗？</p>
      <template #footer>
        <button class="btn btn-outline" type="button" @click="swipeConfirmVisible = false">否</button>
        <button class="btn btn-primary" type="button" @click="confirmSwipe">进入</button>
      </template>
    </NativeDialog>
  </main>
</template>

<style scoped>
*, *::before, *::after { box-sizing: border-box; }

.page-home {
  min-height: 100vh;
  background: var(--bg-100);
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
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 14px;
  margin-bottom: 18px;
  background: var(--bg-50);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-xs);
  font-size: 12px;
}
.stats-item {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--text-500);
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
  font-weight: 700;
  color: var(--text-800);
  font-size: 13px;
}
.stats-label {
  color: var(--text-400);
  font-size: 12px;
}
.stats-divider {
  width: 1px;
  height: 14px;
  background: var(--bg-300);
}

/* FEED TABS */
.feed-tabs {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  padding: 0 2px;
}
.feed-tab {
  padding: 6px 16px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-500);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: color 150ms cubic-bezier(0.32, 0.72, 0, 1),
              background 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.feed-tab:hover { color: var(--text-800); }
.feed-tab.is-active {
  color: var(--brand-600);
  background: var(--brand-50);
  font-weight: 600;
}
.feed-tab--mode {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
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
  display: block;
  width: 100%;
  max-width: 100%;
  break-inside: avoid;
  margin-bottom: 16px;
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-xs);
  cursor: pointer;
  border: none;
  text-align: left;
  /* 防止内容撑开卡片宽度 */
  min-width: 0;
  word-break: break-word;
  overflow-wrap: anywhere;
  transition: box-shadow 150ms cubic-bezier(0.32, 0.72, 0, 1),
              transform 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}
.card-img {
  width: 100%;
  height: 240px;
  display: block;
  object-fit: cover;
}
.card:nth-of-type(4n+1) .card-img { height: 280px; }
.card:nth-of-type(4n+2) .card-img { height: 205px; }
.card:nth-of-type(4n+3) .card-img { height: 255px; }
.card:nth-of-type(4n)   .card-img { height: 215px; }

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

/* 刷一刷确认弹窗文案 */
.swipe-confirm-text {
  margin: 0;
  font-size: 15px;
  line-height: 1.6;
  color: var(--text-800);
}

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
</style>
