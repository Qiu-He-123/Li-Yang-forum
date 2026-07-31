<script setup lang="ts">
/**
 * 圈子发现页（路由：/circles）
 * 严格对齐设计稿：发现页.html
 * - 顶部固定栏：标题「圈子」居中 + 右侧搜索图标
 * - 热门圈子：3 x 2 网格入口（点击进入圈子详情）
 * - 圈子动态：Tab 切换（我加入的 / 全部圈子）+ 双列瀑布流
 * - 底部 TabBar：浮动药丸（圈子 active）
 *
 * 功能说明：
 * - 匿名用户可访问，仅显示「全部圈子」Tab
 * - 登录用户额外显示「我加入的」Tab（按已加入圈子的 category 过滤帖子）
 * - 加入/退出圈子按钮实时更新 member_count
 * - 点击帖子进入帖子详情
 */
import { computed, onActivated, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useFadeUpdate } from '../composables/useFadeUpdate'
// keep-alive 需要 name，与 App.vue 的 cachedViewNames 对应
defineOptions({ name: 'CircleDiscoverView' })

// SWR 刷新渐变：数据变化时递增 key 触发 CSS 淡入动画
const { fadeActive, triggerFade } = useFadeUpdate()
import { useRoute, useRouter } from 'vue-router'

import EmptyState from '../components/common/EmptyState.vue'
import AiStatusBadge from '../components/common/AiStatusBadge.vue'
import PostListSkeleton from '../components/post/PostListSkeleton.vue'
import InfiniteScrollFooter from '../components/common/InfiniteScrollFooter.vue'
import { useInfiniteScroll } from '../composables/useInfiniteScroll'
import { Dialog, Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import { useSessionStore } from '../stores/session'
import { useUserStore } from '../stores/user'
import { usePostStore } from '../stores/post'
import { useCircleStore } from '../stores/circle'
import { useAnnouncementStore } from '../stores/announcement'
import { useInteractionStore } from '../stores/interaction'
import { viewPost } from '../api/post'
import { applyCreateCircle } from '../api/circleApply'
import { listViewedCircles } from '../api/circle'
import type { Circle, Post } from '../types/api'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const userStore = useUserStore()
const postStore = usePostStore()
const circleStore = useCircleStore()
const announcementStore = useAnnouncementStore()
const interactionStore = useInteractionStore()

const { loading: loadMoreLoading, error: loadMoreError, retry: retryLoadMore } = useInfiniteScroll({
  hasMore: computed(() => postStore.hasMore),
  onLoadMore: () => postStore.loadMore(),
})

// 圈子 Feed Tab：joined（我加入的）/ all（全部圈子）
const feedTab = computed<'joined' | 'all'>(() => (route.query.tab === 'joined' ? 'joined' : 'all'))

// 当前用户已加入的圈子 name 集合（用于「我加入的」Tab 客户端过滤）
const joinedCircleNames = computed<Set<string>>(() => {
  return new Set(
    circleStore.circles.filter((c) => c.is_joined).map((c) => c.name),
  )
})

// 「我加入的」Tab 下客户端过滤帖子（按 category = 圈子 name 匹配）
const displayedPosts = computed<Post[]>(() => {
  if (feedTab.value === 'all') return postStore.posts
  if (!session.userId) return []
  return postStore.posts.filter((p) => joinedCircleNames.value.has(p.category || ''))
})

// 热门圈子入口：严格对齐设计稿「发现页.html」网格
// 表白墙/匿名树洞/随机交友 已挪至首页特色入口，圈子页不展示
const FEATURE_SLUGS = new Set(['confess', 'treehole', 'match'])
const hotCircles = computed(() =>
  circleStore.circles.filter((c) => c.slug !== 'default' && !FEATURE_SLUGS.has(c.slug)),
)

// 精选圈子：优先展示未加入的圈子；不足 4 个时补充已加入的圈子，确保至少 4 个
const featuredCircles = computed(() => {
  const notJoined = hotCircles.value.filter((c) => !c.is_joined)
  if (notJoined.length >= 4) return notJoined
  // 不足4个，补充已加入的圈子
  const joined = hotCircles.value.filter((c) => c.is_joined)
  return [...notJoined, ...joined].slice(0, Math.max(4, notJoined.length))
})

// 全部圈子模块：按成员数取前 10 个圈子
const topCircles = computed(() => {
  return [...circleStore.circles]
    .sort((a, b) => b.member_count - a.member_count)
    .slice(0, 10)
})

// 圈子图标与色调映射（严格对齐设计稿：发现页.html）
// 设计稿规则：
// - 图片卡（card--image）：白色背景 var(--background-50)，无染色
// - 文本卡（card--text）：按圈子染色，仅 4 种染色：study/lost/game/confess
//   - study   -> background: var(--brand-50)       = #e8f2ff 浅蓝
//   - lost    -> background: var(--state-error-surface) = #ffecea 浅红
//   - game    -> background: #f3f0ff               浅紫
//   - confess -> background: #faf5ff               浅紫粉
// 其他圈子的文本卡保持白底（与图片卡一致）
// pillBg/pillColor: 卡片顶部 #圈子标签的背景/文字色（对齐 .circle-pill--*）
// gradient: 热门圈子入口圆形图标渐变（对齐 .circle-ic--*）
// iconColor: 文本卡标题前导图标颜色（对齐 .card--* .title-icon background-color）
const circleMeta: Record<string, { icon: string; gradient: string; pillBg: string; pillColor: string; cardBg: string; iconColor: string }> = {
  confess: { icon: 'heart', gradient: 'linear-gradient(135deg, #ff6b9d, #af52de)', pillBg: '#f7eaff', pillColor: '#af52de', cardBg: '#faf5ff', iconColor: '#af52de' },
  lost: { icon: 'circle-question', gradient: 'linear-gradient(135deg, #66abff, #0064d6)', pillBg: '#e8f2ff', pillColor: '#0064d6', cardBg: '#ffecea', iconColor: '#ff3b30' },
  market: { icon: 'tag', gradient: 'linear-gradient(135deg, #ff9500, #ff6b35)', pillBg: '#fff3e6', pillColor: '#d26510', cardBg: '#ffffff', iconColor: '#d26510' },
  study: { icon: 'file', gradient: 'linear-gradient(135deg, #34c759, #007aff)', pillBg: '#e8f2ff', pillColor: '#0064d6', cardBg: '#e8f2ff', iconColor: '#007aff' },
  food: { icon: 'map-pin', gradient: 'linear-gradient(135deg, #ffb347, #ff9500)', pillBg: '#fff3e6', pillColor: '#d26510', cardBg: '#ffffff', iconColor: '#d26510' },
  game: { icon: 'star', gradient: 'linear-gradient(135deg, #5856d6, #af52de)', pillBg: '#eeeaff', pillColor: '#5856d6', cardBg: '#f3f0ff', iconColor: '#5856d6' },
  photo: { icon: 'camera', gradient: 'linear-gradient(135deg, #34c759, #00c7be)', pillBg: '#e9f9ee', pillColor: '#34c759', cardBg: '#ffffff', iconColor: '#34c759' },
  club: { icon: 'star', gradient: 'linear-gradient(135deg, #af52de, #ff6b9d)', pillBg: '#f7eaff', pillColor: '#af52de', cardBg: '#ffffff', iconColor: '#af52de' },
  sport: { icon: 'flame', gradient: 'linear-gradient(135deg, #007aff, #34c759)', pillBg: '#e8f2ff', pillColor: '#007aff', cardBg: '#ffffff', iconColor: '#007aff' },
  // 新增 4 个圈子
  match: { icon: 'shuffle', gradient: 'linear-gradient(135deg, #ff9500, #ff6b35)', pillBg: '#fff3e6', pillColor: '#d26510', cardBg: '#ffffff', iconColor: '#ff9500' },
  treehole: { icon: 'lock', gradient: 'linear-gradient(135deg, #8e8e93, #48484a)', pillBg: '#f2f2f7', pillColor: '#48484a', cardBg: '#ffffff', iconColor: '#8e8e93' },
  qa: { icon: 'circle-question', gradient: 'linear-gradient(135deg, #66abff, #0064d6)', pillBg: '#e8f2ff', pillColor: '#0064d6', cardBg: '#e8f2ff', iconColor: '#007aff' },
  flea: { icon: 'tag', gradient: 'linear-gradient(135deg, #34c759, #00c7be)', pillBg: '#e9f9ee', pillColor: '#34c759', cardBg: '#ffffff', iconColor: '#34c759' },
}

function getCircleMeta(slug: string) {
  return (
    circleMeta[slug] || {
      icon: 'sparkles',
      gradient: 'linear-gradient(135deg, #66abff, #007aff)',
      pillBg: '#e8f2ff',
      pillColor: '#0064d6',
      cardBg: '#ffffff',
      iconColor: '#007aff',
    }
  )
}

function formatCount(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, '') + 'w'
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k'
  return String(n)
}

function circleOf(post: Post): Circle | undefined {
  return circleStore.circles.find((c) => c.slug === post.category || c.name === post.category)
}

// 后端 post.category 存的是圈子的 name（如「校园美食」），需映射回 slug（如「food」）以匹配 circleMeta
function resolveCircleSlug(post: Post): string {
  const bySlug = circleStore.circles.find((c) => c.slug === post.category)
  if (bySlug) return bySlug.slug
  const byName = circleStore.circles.find((c) => c.name === post.category)
  if (byName) return byName.slug
  return post.category || 'default'
}

// 我的足迹：从 circleStore 读取（提升到 store 后，CircleDetail 进入时即可即时更新）
// 修复"延迟一步"问题：之前 viewedCircles 是组件内部状态，CircleDetail 记录浏览后
// 只有返回 CircleDiscover 并触发 onActivated 才会刷新，存在时序/缓存导致的延迟
const viewedCircles = computed(() => circleStore.viewedCircles)
// 足迹加载中状态：用于显示骨架屏，避免"先空白 → 随后出现"的闪烁
const viewedLoading = ref(false)

async function loadViewedCircles() {
  if (!session.userId) return
  viewedLoading.value = true
  try {
    const res = await listViewedCircles(20, {
      showGlobalLoading: false,
      showGlobalError: false,
    })
    circleStore.setViewedCircles(res.data.data || [])
  } catch {
    circleStore.setViewedCircles([])
  } finally {
    viewedLoading.value = false
  }
}

/** 静默加载足迹：不显示骨架屏，保留旧数据可见，数据变化时触发渐变 */
async function loadViewedCirclesSilent() {
  if (!session.userId) return
  try {
    const res = await listViewedCircles(20, {
      showGlobalLoading: false,
      showGlobalError: false,
    })
    const newList = res.data.data || []
    // 数据指纹对比：只有圈子列表真的变了才更新 + 触发渐变
    const oldFp = viewedCircles.value.map(c => `${c.id}:${c.name}`).join('|')
    const newFp = newList.map(c => `${c.id}:${c.name}`).join('|')
    circleStore.setViewedCircles(newList)
    if (oldFp !== newFp) triggerFade()
  } catch {
    /* 静默刷新失败不影响用户 */
  }
}

onMounted(async () => {
  // 性能优化：validateSession 后台并行，不阻塞第一波加载
  // 基于 localStorage 中的 session.userId 决定第二波请求（已登录用户加载互动状态）
  const validPromise = session.validateSession()
  // 第一波：公告 + 圈子列表（与 session 校验并行）
  await Promise.all([
    announcementStore.loadAnnouncements(),
    circleStore.loadCircles(),
  ])
  // 圈子页 feed：使用 view=all 拉取全部帖子，"我加入的" Tab 在客户端过滤
  postStore.setView('all')
  postStore.setCategory('')
  // 用 localStorage 的 userId 立即判断（validateSession 结果回填到 store）
  const hasUserId = !!session.userId
  if (hasUserId) {
    // 第二波：登录用户的互动数据 + 帖子 feed + 浏览过的圈子（全部并行）
    await Promise.all([
      userStore.loadProfile(),
      interactionStore.loadAll(),
      postStore.loadPosts(),
      loadViewedCircles(),
    ])
  } else {
    // 匿名用户：等 validateSession 结果确认是否真的未登录
    const valid = await validPromise
    if (valid) {
      await Promise.all([
        userStore.loadProfile(),
        interactionStore.loadAll(),
        postStore.loadPosts(),
        loadViewedCircles(),
      ])
    } else {
      // 匿名用户也能看圈子页 feed
      await postStore.loadPosts()
    }
  }
})

/**
 * keep-alive 重新激活时：恢复圈子页 view=all + 从缓存即时展示 + SWR 后台刷新。
 *
 * 关键：KeepAlive 首次挂载时 onMounted 和 onActivated 都会触发！
 * onMounted 是 async，第一波 await 让出执行权时 onActivated 触发，
 * 此时 loading 还是 false → 会和 onMounted 的 loadPosts 并发。
 * 用 skipFirstActivated 跳过首次触发。
 */
let skipFirstActivated = true
onActivated(() => {
  if (skipFirstActivated) {
    skipFirstActivated = false
    return // 首次由 onMounted 处理，不重复加载
  }
  // 恢复圈子页 view（可能被首页改成 hot/latest）
  if (postStore.activeView !== 'all' || postStore.activeCategory !== '') {
    postStore.setView('all')
    postStore.setCategory('')
  }
  // SWR：有缓存先展示旧数据，后台刷新；无缓存则正常加载
  if (postStore.restoreFromCache()) {
    postStore.ensureFresh().then((changed) => { if (changed) triggerFade() })
  } else {
    postStore.loadPosts()
  }
  // 重新加载"我的足迹"：用户可能在其他页面浏览了新圈子，回来后需要同步
  // 静默刷新：不显示骨架屏，保留旧数据可见，数据变化时触发渐变
  loadViewedCirclesSilent()
})

async function onTabChange(tab: 'joined' | 'all') {
  if (tab === 'joined' && !session.userId) {
    toast.info('请先登录后查看「我加入的」')
    return
  }
  await router.replace({ query: { ...route.query, tab } })
  // Tab 切换不需要重新拉接口，displayedPosts 计算属性会自动过滤
}

async function onJoinCircle(e: Event, slug: string) {
  e.stopPropagation()
  e.preventDefault()
  if (!session.userId) {
    toast.info('请先登录')
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

function openCircle(slug: string) {
  if (!slug) return
  router.push(`/circle/${slug}`)
}

// 滚动到「全部圈子」模块（无关注圈子时，"加入圈子" 入口点击触发）
function scrollToAllCircles() {
  const el = document.querySelector('.all-circles-section')
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

function openSearch() {
  if (!session.userId) {
    toast.info('请先登录')
    return
  }
  router.push('/search')
}

function isJoined(slug: string): boolean {
  const c = circleStore.circles.find((x) => x.slug === slug)
  return !!c?.is_joined
}

// ============ 阶段四：创建吧（申请建吧）============
// 预设 8 个图标（与圈子图标库对齐）
const PRESET_ICONS = [
  { icon: 'sparkles', label: '综合' },
  { icon: 'heart', label: '情感' },
  { icon: 'file', label: '学习' },
  { icon: 'tag', label: '交易' },
  { icon: 'map-pin', label: '生活' },
  { icon: 'star', label: '兴趣' },
  { icon: 'camera', label: '影像' },
  { icon: 'gamepad', label: '游戏' },
]
// 预设 8 种颜色
const PRESET_COLORS = [
  '#007aff', '#ff3b30', '#ff9500', '#34c759',
  '#5856d6', '#af52de', '#00c7be', '#ff6b35',
]

const applyDialogVisible = ref(false)
const applySubmitting = ref(false)
const applyForm = reactive({
  name: '',
  slug: '',
  description: '',
  icon: 'sparkles',
  color: '#007aff',
})

function openApplyDialog() {
  if (!session.userId) {
    toast.info('请先登录后再创建吧')
    return
  }
  // 重置表单
  applyForm.name = ''
  applyForm.slug = ''
  applyForm.description = ''
  applyForm.icon = 'sparkles'
  applyForm.color = '#007aff'
  applyDialogVisible.value = true
}

// name 变化时自动生成 slug（仅未手动编辑过 slug 时）
let slugTouched = false
function onNameInput() {
  if (slugTouched) return
  // 中文转拼音较复杂，这里简单用拼音占位：取首字母+英文数字
  // 改为：自动用 name 的英文/数字部分，否则留空让用户手填
  const en = applyForm.name.replace(/[^a-zA-Z0-9-]/g, '').toLowerCase()
  applyForm.slug = en.slice(0, 32)
}
function onSlugInput() {
  slugTouched = true
  // 强制小写 + 仅保留英文/数字/横线
  applyForm.slug = applyForm.slug.toLowerCase().replace(/[^a-z0-9-]/g, '')
}

function validateApply(): string | null {
  const name = applyForm.name.trim()
  const slug = applyForm.slug.trim()
  if (name.length < 2 || name.length > 16) return '吧名称长度需为 2-16 字'
  if (slug.length < 2 || slug.length > 32) return '吧标识长度需为 2-32 字'
  if (!/^[a-z0-9-]+$/.test(slug)) return '吧标识仅支持英文/数字/横线'
  if (applyForm.description.length > 200) return '简介最多 200 字'
  return null
}

async function submitApply() {
  const err = validateApply()
  if (err) {
    toast.error(err)
    return
  }
  applySubmitting.value = true
  try {
    await applyCreateCircle({
      name: applyForm.name.trim(),
      slug: applyForm.slug.trim(),
      description: applyForm.description.trim() || undefined,
      icon: applyForm.icon,
      color: applyForm.color,
    })
    toast.success('申请已提交，等待管理员审核')
    applyDialogVisible.value = false
    // 跳转到「我创建的吧」页面查看审核状态
    router.push('/my/circles-applied')
  } catch (e) {
    toast.error((e as Error).message)
  } finally {
    applySubmitting.value = false
  }
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

onUnmounted(() => stopAuditPolling())
</script>

<template>
  <main class="page-discover">
    <!-- ====== 顶部固定栏：标题「圈子」居中 + 右侧搜索图标 ====== -->
    <header class="site-header" role="banner">
      <div class="header-inner">
        <div class="header-side header-side--left" aria-hidden="true"></div>
        <h1 class="header-title">立洋社区·圈子</h1>
        <div class="header-side header-side--right">
          <button class="icon-btn" type="button" aria-label="创建圈子" @click="openApplyDialog">
            <Icon name="plus" :size="20" />
          </button>
          <button class="icon-btn" type="button" aria-label="搜索圈子" @click="openSearch">
            <Icon name="search" :size="20" />
          </button>
        </div>
      </div>
    </header>

    <!-- ====== 主内容 ====== -->
    <div class="page-container">
      <!-- ====== 模块1：我的足迹（横向滑动快捷入口）====== -->
      <section class="footprint-section" aria-label="我的足迹">
        <input
          type="checkbox"
          id="footprint-toggle"
          class="footprint-checkbox"
          checked
        />
        <div class="section-head">
          <h2 class="section-title-bold">我的足迹</h2>
          <label class="footprint-toggle-label" for="footprint-toggle">
            <span class="toggle-text-hide">隐藏</span>
            <span class="toggle-text-show">显示</span>
          </label>
        </div>

        <div class="footprint-content">
          <div v-if="!session.userId" class="empty-mini">
            请先登录后查看足迹
          </div>
          <!-- 足迹骨架屏：加载中显示 shimmer 占位，避免空白后突然出现 -->
          <div v-else-if="viewedLoading" class="footprint-skeleton">
            <div v-for="i in 5" :key="'fs-' + i" class="footprint-sk-item sk-shimmer"></div>
          </div>
          <div
            v-else-if="!viewedCircles.length"
            class="empty-mini"
          >
            还没有浏览过任何吧，去下面看看吧
          </div>
          <div v-else :class="{ 'swr-updated': fadeActive }" class="footprint-scroll">
            <button
              v-for="circle in viewedCircles"
              :key="'fp-' + circle.id"
              class="footprint-item"
              type="button"
              @click="openCircle(circle.slug)"
            >
              <span
                class="footprint-icon"
                :style="{ background: getCircleMeta(circle.slug).gradient }"
                aria-hidden="true"
              >
                <Icon :name="getCircleMeta(circle.slug).icon" :size="22" color="#fff" />
              </span>
              <span class="footprint-name">{{ circle.name }}</span>
            </button>
          </div>
        </div>
      </section>

      <!-- ====== 模块2：我关注的吧（2列网格）====== -->
      <section class="followed-section" aria-label="我关注的吧">
        <input type="checkbox" id="followed-expand" class="expand-checkbox" />
        <div class="section-head">
          <h2 class="section-title-bold">我关注的吧</h2>
          <button class="section-more" type="button" @click="router.push('/circles/all')">
            全部
            <Icon name="chevron-right" :size="13" />
          </button>
        </div>

        <div class="followed-grid">
          <!-- 加入圈子入口（无关注时显示） -->
          <button v-if="!session.userId || !circleStore.circles.filter((c) => c.is_joined).length"
                  class="followed-item join-item" type="button" @click="scrollToAllCircles">
            <span class="followed-icon followed-icon--join" aria-hidden="true">
              <Icon name="compass" :size="24" color="#34c759" />
            </span>
            <span class="followed-name">加入圈子</span>
          </button>

          <!-- 创建圈子入口（第一行第一个） -->
          <button
            class="followed-item create-item"
            type="button"
            @click="openApplyDialog"
          >
            <span class="followed-icon followed-icon--create" aria-hidden="true">
              <Icon name="plus" :size="26" color="#8e8e93" />
            </span>
            <span class="followed-name">创建圈子</span>
          </button>

          <!-- 已加入的圈子 -->
          <template v-if="session.userId && circleStore.circles.filter((c) => c.is_joined).length">
            <button
              v-for="(circle, i) in circleStore.circles.filter((c) => c.is_joined)"
              :key="'fw-' + circle.id"
              class="followed-item"
              :class="{ 'is-extra': i >= 6 }"
              type="button"
              @click="openCircle(circle.slug)"
            >
              <span
                class="followed-icon"
                :style="{ background: getCircleMeta(circle.slug).gradient }"
                aria-hidden="true"
              >
                <Icon :name="getCircleMeta(circle.slug).icon" :size="22" color="#fff" />
              </span>
              <span class="followed-name">{{ circle.name }}</span>
              <span class="followed-heat">
                <Icon name="flame" :size="10" color="#34c759" />
                {{ formatCount(circle.member_count) }}
              </span>
            </button>
          </template>

          <!-- 空状态占位 -->
          <div v-if="!session.userId" class="followed-empty-cell">
            请先登录后查看
          </div>
          <div
            v-else-if="!circleStore.circles.filter((c) => c.is_joined).length"
            class="followed-empty-cell"
          >
            还没有关注的吧，点击上方加入圈子
          </div>

          <!-- 意见反馈入口（最后一个） -->
          <button class="followed-item feedback-item" type="button" @click="router.push('/feedback')">
            <span class="followed-icon followed-icon--feedback" aria-hidden="true">
              <Icon name="message-square" :size="22" color="#8e8e93" />
            </span>
            <span class="followed-name">意见反馈</span>
          </button>
        </div>

        <label
          v-if="session.userId && circleStore.circles.filter((c) => c.is_joined).length > 6"
          for="followed-expand"
          class="expand-btn"
        >
          <span class="expand-text-collapsed">展开</span>
          <span class="expand-text-expanded">收起</span>
          <span class="expand-arrow" aria-hidden="true">
            <Icon name="chevron-down" :size="14" />
          </span>
        </label>
      </section>

      <!-- ====== 模块3：精选圈子（横向滚动卡片）====== -->
      <section
        v-if="featuredCircles.length"
        class="featured-section"
        aria-label="精选圈子"
      >
        <div class="section-head">
          <h2 class="section-title-bold">精选圈子</h2>
        </div>

        <div class="featured-scroll">
          <article
            v-for="circle in featuredCircles"
            :key="'fc-' + circle.id"
            class="featured-card"
            @click="openCircle(circle.slug)"
          >
            <div class="featured-top">
              <span
                class="featured-icon"
                :style="{ background: getCircleMeta(circle.slug).gradient }"
                aria-hidden="true"
              >
                <Icon :name="getCircleMeta(circle.slug).icon" :size="22" color="#fff" />
              </span>
              <div class="featured-info">
                <div class="featured-name">{{ circle.name }}</div>
                <div class="featured-members">
                  {{ formatCount(circle.member_count) }} 成员
                </div>
              </div>
              <button
                class="join-btn"
                :class="{ 'is-joined': isJoined(circle.slug) }"
                type="button"
                @click="(e) => onJoinCircle(e, circle.slug)"
              >
                {{ isJoined(circle.slug) ? '已加入' : '加入' }}
              </button>
            </div>
            <p v-if="circle.description" class="featured-desc">
              {{ circle.description }}
            </p>
          </article>
        </div>
      </section>

      <!-- ====== 模块4：全部圈子（圈子列表入口）====== -->
      <section class="all-circles-section" aria-label="全部圈子">
        <div class="section-head">
          <h2 class="section-title-bold">全部圈子</h2>
        </div>
        <div class="all-circles-grid">
          <button v-for="circle in topCircles" :key="'ac-' + circle.id"
                  class="all-circle-item" type="button" @click="openCircle(circle.slug)">
            <span class="all-circle-icon" :style="{ background: getCircleMeta(circle.slug).gradient }">
              <Icon :name="getCircleMeta(circle.slug).icon" :size="24" color="#fff" />
            </span>
            <div class="all-circle-info">
              <span class="all-circle-name">{{ circle.name }}</span>
              <span class="all-circle-heat">
                <Icon name="flame" :size="12" color="#ff9500" />
                {{ formatCount(circle.member_count) }}
              </span>
            </div>
          </button>
        </div>
        <button class="view-all-circles-btn" type="button" @click="router.push('/circles/all')">
          查看全部圈子
          <Icon name="chevron-right" :size="14" color="var(--text-400)" />
        </button>
      </section>

      <!-- ====== 模块5：圈子动态 Feed（Tab 切换 + 瀑布流）====== -->
      <section class="feed-section" aria-label="圈子动态">
        <div class="feed-tabs" role="tablist" aria-label="圈子动态来源">
          <button
            v-if="session.userId"
            class="feed-tab"
            type="button"
            :class="{ 'is-active': feedTab === 'joined' }"
            role="tab"
            :aria-selected="feedTab === 'joined'"
            @click="onTabChange('joined')"
          >
            我加入的
          </button>
          <button
            class="feed-tab"
            type="button"
            :class="{ 'is-active': feedTab === 'all' || !session.userId }"
            role="tab"
            :aria-selected="feedTab === 'all' || !session.userId"
            @click="onTabChange('all')"
          >
            全部圈子
          </button>
        </div>

        <PostListSkeleton v-if="postStore.loading" :count="6" />

        <!-- :class swr-updated：SWR 刷新数据变化时渐变过渡（文字逐字淡变+图片滑动），不销毁 DOM 保持滚动 -->
        <div v-else-if="displayedPosts.length" :class="{ 'swr-updated': fadeActive }" class="feed">
          <article
            v-for="post in displayedPosts"
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
                  <span class="avatar avatar-sm" :class="`av-${(post.author_id || 0) % 5 + 1}`" aria-hidden="true"></span>
                  <span class="author-name">{{ post.is_anonymous ? '匿名同学' : post.author }}</span>
                </div>
                <div class="card-likes">
                  <Icon name="heart" :size="14" />
                  <span class="like-count">{{ formatCount(post.like_count) }}</span>
                </div>
              </div>
            </div>
          </article>

          <InfiniteScrollFooter
            :loading="loadMoreLoading"
            :error="loadMoreError"
            :has-more="postStore.hasMore"
            :has-items="displayedPosts.length > 0"
            @retry="retryLoadMore"
          />
        </div>

        <EmptyState
          v-else
          :text="feedTab === 'joined' ? '你还没有加入任何圈子，先在「全部圈子」里找感兴趣的加入吧' : '暂无帖子，发布第一条校园动态。'"
        />
      </section>
    </div>

    <!-- ====== 创建吧申请弹窗 ====== -->
    <Dialog v-model="applyDialogVisible" title="创建新圈子" width="460px">
      <div class="apply-form">
        <!-- 吧名称 -->
        <div class="form-row">
          <label class="form-label">
            吧名称 <span class="req">*</span>
          </label>
          <input
            v-model="applyForm.name"
            class="form-input"
            type="text"
            maxlength="16"
            placeholder="2-16 字，如「校园音乐」"
            @input="onNameInput"
          />
        </div>

        <!-- 吧标识（slug） -->
        <div class="form-row">
          <label class="form-label">
            吧标识 <span class="req">*</span>
          </label>
          <input
            v-model="applyForm.slug"
            class="form-input"
            type="text"
            maxlength="32"
            placeholder="英文/数字/横线，2-32 字，如 music"
            @input="onSlugInput"
          />
          <p class="form-hint">用于 URL，如 /circle/music</p>
        </div>

        <!-- 简介 -->
        <div class="form-row">
          <label class="form-label">简介（可选）</label>
          <textarea
            v-model="applyForm.description"
            class="form-textarea"
            rows="3"
            maxlength="200"
            placeholder="一句话介绍这个圈子（最多 200 字）"
          />
        </div>

        <!-- 图标选择 -->
        <div class="form-row">
          <label class="form-label">图标</label>
          <div class="icon-grid">
            <button
              v-for="opt in PRESET_ICONS"
              :key="opt.icon"
              type="button"
              class="icon-option"
              :class="{ active: applyForm.icon === opt.icon }"
              @click="applyForm.icon = opt.icon"
            >
              <Icon :name="opt.icon" :size="20" />
              <span class="icon-label">{{ opt.label }}</span>
            </button>
          </div>
        </div>

        <!-- 颜色选择 -->
        <div class="form-row">
          <label class="form-label">主题色</label>
          <div class="color-grid">
            <button
              v-for="c in PRESET_COLORS"
              :key="c"
              type="button"
              class="color-option"
              :class="{ active: applyForm.color === c }"
              :style="{ background: c }"
              :aria-label="`颜色 ${c}`"
              @click="applyForm.color = c"
            >
              <Icon v-if="applyForm.color === c" name="check" :size="14" color="#fff" />
            </button>
          </div>
        </div>

        <!-- 预览 -->
        <div class="form-preview">
          <span
            class="preview-ic"
            :style="{ background: applyForm.color }"
          >
            <Icon :name="applyForm.icon" :size="20" color="#fff" />
          </span>
          <div class="preview-info">
            <div class="preview-name">{{ applyForm.name || '吧名称预览' }}</div>
            <div class="preview-slug">/{{ applyForm.slug || 'slug' }}</div>
          </div>
        </div>
      </div>

      <template #footer>
        <button class="btn-cancel" type="button" @click="applyDialogVisible = false">取消</button>
        <button
          class="btn-submit"
          type="button"
          :disabled="applySubmitting"
          @click="submitApply"
        >
          {{ applySubmitting ? '提交中…' : '提交申请' }}
        </button>
      </template>
    </Dialog>
  </main>
</template>

<style scoped>
/* ================================================
   RESET & BASE
   ================================================ */
*, *::before, *::after { box-sizing: border-box; }

.page-discover {
  min-height: 100vh;
  background: var(--bg-100);
  /* Desktop: header 56; mobile: header 48 */
  padding-top: 56px;
  padding-bottom: calc(56px + 28px + env(safe-area-inset-bottom));
  color: var(--text-800);
  font-family: var(--font-sans, inherit);
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* ================================================
   SITE HEADER (centered title, right icon button)
   ================================================ */
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

/* ================================================
   PAGE CONTAINER
   ================================================ */
.page-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px 20px calc(56px + env(safe-area-inset-bottom));
}

/* ================================================
   SECTION HEAD (title + more)
   ================================================ */
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  padding: 0 2px;
}
.section-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-800);
  letter-spacing: -0.01em;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}
.section-title-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--brand-500);
}
.section-more {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-400);
  display: inline-flex;
  align-items: center;
  gap: 2px;
  background: transparent;
  border: none;
  cursor: pointer;
  transition: color 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.section-more:hover { color: var(--brand-500); }

/* ================================================
   HOT CIRCLES ENTRY GRID (3 x 2)
   ================================================ */
.circles-entry {
  margin-bottom: 28px;
}
.circles-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.circle-entry {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 8px;
  padding: 18px 10px 16px;
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  border: none;
  cursor: pointer;
  transition: transform 150ms cubic-bezier(0.32, 0.72, 0, 1),
              box-shadow 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.circle-entry:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.circle-ic {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-sm);
}

.circle-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-800);
  line-height: 1.2;
}
.circle-members {
  font-size: 11.5px;
  color: var(--text-400);
  line-height: 1.2;
}

/* ================================================
   SECTION TITLE BOLD (for new sections, no dot)
   ================================================ */
.section-title-bold {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-800);
  letter-spacing: -0.01em;
  margin: 0;
  display: inline-flex;
  align-items: center;
}

/* ================================================
   FOOTPRINT SECTION (我的足迹 - 横向滑动)
   ================================================ */
.footprint-section {
  margin-bottom: 24px;
}
.footprint-checkbox {
  position: absolute;
  width: 0;
  height: 0;
  opacity: 0;
  pointer-events: none;
}
/* 切换文字显示 */
.footprint-checkbox:checked ~ .section-head .toggle-text-show { display: none; }
.footprint-checkbox:not(:checked) ~ .section-head .toggle-text-hide { display: none; }
/* 折叠时隐藏内容 */
.footprint-checkbox:not(:checked) ~ .footprint-content { display: none; }

.footprint-toggle-label {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text-400);
  cursor: pointer;
  user-select: none;
  transition: color 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.footprint-toggle-label:hover { color: var(--brand-500); }

.footprint-content {
  padding-top: 2px;
}

.footprint-scroll {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 4px 2px 8px;
  scroll-snap-type: x proximity;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}
.footprint-scroll::-webkit-scrollbar { display: none; }

.footprint-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  width: 64px;
  padding: 0;
  background: transparent;
  border: none;
  cursor: pointer;
  scroll-snap-align: start;
  transition: transform 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.footprint-item:hover { transform: translateY(-2px); }
.footprint-item:active { transform: scale(0.94); }

/* 足迹骨架屏 */
.footprint-skeleton {
  display: flex;
  gap: 12px;
  overflow: hidden;
}
.footprint-sk-item {
  flex-shrink: 0;
  width: 52px;
  height: 52px;
  border-radius: 16px;
}

.footprint-icon {
  position: relative;
  width: 52px;
  height: 52px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-sm);
}

.footprint-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-700, #3a3a3c);
  line-height: 1.2;
  text-align: center;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ================================================
   FOLLOWED SECTION (我关注的吧 - 2列网格)
   ================================================ */
.followed-section {
  margin-bottom: 24px;
}
.expand-checkbox {
  position: absolute;
  width: 0;
  height: 0;
  opacity: 0;
  pointer-events: none;
}

.followed-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.followed-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 16px 10px 14px;
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  border: none;
  cursor: pointer;
  text-align: center;
  transition: transform 150ms cubic-bezier(0.32, 0.72, 0, 1),
              box-shadow 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.followed-item:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}
.followed-item:active { transform: scale(0.97); }

/* 默认隐藏第 7+ 个圈子（展开时显示） */
.followed-item.is-extra { display: none; }
.expand-checkbox:checked ~ .followed-grid .followed-item.is-extra { display: flex; }

.followed-icon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-sm);
  flex-shrink: 0;
}
.followed-icon--create,
.followed-icon--feedback,
.followed-icon--join {
  background: var(--bg-100);
  box-shadow: none;
  border: 1.5px dashed var(--bg-300, #d1d1d6);
}

.followed-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-800);
  line-height: 1.2;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.followed-heat {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 11px;
  font-weight: 600;
  color: #34c759;
  background: rgba(52, 199, 89, 0.1);
  padding: 1px 7px;
  border-radius: 999px;
  line-height: 1.4;
}
.followed-heat :deep(svg) { width: 10px; height: 10px; }

/* 空状态占位单元格 */
.followed-empty-cell {
  grid-column: span 2;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 18px 12px;
  font-size: 13px;
  color: var(--text-400);
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
}

/* 展开按钮 */
.expand-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  margin: 14px auto 0;
  padding: 6px 22px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-500);
  background: var(--bg-50);
  border-radius: 999px;
  box-shadow: var(--shadow-xs);
  cursor: pointer;
  user-select: none;
  width: fit-content;
  transition: background 150ms cubic-bezier(0.32, 0.72, 0, 1),
              color 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.expand-btn:hover { color: var(--brand-500); }
.expand-text-expanded { display: none; }
.expand-checkbox:checked ~ .expand-btn .expand-text-collapsed { display: none; }
.expand-checkbox:checked ~ .expand-btn .expand-text-expanded { display: inline; }
.expand-checkbox:checked ~ .expand-btn .expand-arrow { transform: rotate(180deg); }
.expand-arrow {
  display: inline-flex;
  align-items: center;
  transition: transform 200ms cubic-bezier(0.32, 0.72, 0, 1);
}

/* ================================================
   FEATURED SECTION (精选圈子 - 横向滚动卡片)
   ================================================ */
.featured-section {
  margin-bottom: 24px;
}
.featured-scroll {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 4px 2px 8px;
  scroll-snap-type: x proximity;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}
.featured-scroll::-webkit-scrollbar { display: none; }

.featured-card {
  flex-shrink: 0;
  width: 260px;
  padding: 14px;
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  cursor: pointer;
  scroll-snap-align: start;
  border: none;
  text-align: left;
  transition: transform 150ms cubic-bezier(0.32, 0.72, 0, 1),
              box-shadow 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.featured-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.featured-top {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.featured-icon {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-sm);
  flex-shrink: 0;
}
.featured-info {
  flex: 1;
  min-width: 0;
}
.featured-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-800);
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.featured-members {
  font-size: 11.5px;
  color: var(--text-400);
  margin-top: 2px;
}
.featured-desc {
  margin: 0;
  font-size: 12.5px;
  color: var(--text-500);
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}

/* ================================================
   ALL CIRCLES SECTION (全部圈子 - 2列网格 + 查看全部)
   ================================================ */
.all-circles-section {
  margin: 0 16px 20px;
}
.all-circles-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}
.all-circle-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  border: none;
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  box-shadow: var(--shadow-xs);
  transition: transform 0.15s var(--ease-apple);
}
.all-circle-item:active {
  transform: scale(0.97);
}
.all-circle-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.all-circle-info {
  flex: 1;
  min-width: 0;
}
.all-circle-name {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-800);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.all-circle-heat {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  color: var(--text-400);
  margin-top: 2px;
}
.view-all-circles-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  width: 100%;
  padding: 12px;
  margin-top: 12px;
  background: var(--bg-100);
  border: none;
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 500;
  color: var(--text-600);
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s;
}
.view-all-circles-btn:hover {
  background: var(--bg-200);
}

/* ================================================
   EMPTY MINI (轻量空状态)
   ================================================ */
.empty-mini {
  padding: 18px 14px;
  font-size: 13px;
  color: var(--text-400);
  text-align: center;
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
}

/* ================================================
   FEED TABS (segmented pill switch)
   ================================================ */
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

/* ================================================
   FEED (masonry via CSS columns, dual column)
   ================================================ */
.feed {
  column-count: 2;
  column-gap: 12px;
  /* 列宽严格固定，防止内容撑开 */
  column-fill: balance;
}

/* 桌面端：增加列数限制卡片大小，防止方块过大 */
@media (min-width: 769px) {
  .feed {
    column-count: 3;
    column-gap: 14px;
  }
  .card-img {
    max-height: 280px;
  }
}
@media (min-width: 1100px) {
  .feed {
    column-count: 4;
  }
  .card-img {
    max-height: 260px;
  }
}

/* ================================================
   POST CARDS (lightweight, no thick border)
   ================================================ */
.card {
  display: block;
  width: 100%;
  max-width: 100%;
  break-inside: avoid;
  margin-bottom: 12px;
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
  height: auto;
  display: block;
  object-fit: cover;
}

.card-body {
  padding: 10px 12px 12px;
}

/* ---- Card top row: circle pill + join button ---- */
.card-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.circle-pill {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
  letter-spacing: 0.01em;
  white-space: nowrap;
  flex-shrink: 0;
}

/* ---- Join button (CTA, brand filled; joined = muted gray) ---- */
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
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--text-800);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}

/* ---- Text-only cards (soft tinted surfaces, no border) ---- */
.card--text .card-body { padding: 14px; }

.card-title--text {
  display: flex;
  gap: 7px;
  align-items: flex-start;
  -webkit-line-clamp: 3;
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

/* ---- Avatars (gradient placeholders) ---- */
.avatar {
  display: inline-block;
  border-radius: 50%;
  flex-shrink: 0;
}
.avatar-sm { width: 22px; height: 22px; }

.av-1 { background: linear-gradient(135deg, #66abff, #007aff); }
.av-2 { background: linear-gradient(135deg, #34c759, #2e8dff); }
.av-3 { background: linear-gradient(135deg, #ff9500, #007aff); }
.av-4 { background: linear-gradient(135deg, #5856d6, #0064d6); }
.av-5 { background: linear-gradient(135deg, #d1d1d6, #8e8e93); }

.author-name {
  font-size: 12px;
  color: var(--text-500);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.card-likes {
  display: flex;
  align-items: center;
  gap: 3px;
  color: var(--text-400);
  flex-shrink: 0;
}
.like-count {
  font-size: 12px;
  color: var(--text-400);
}

/* ================================================
   RESPONSIVE — Mobile (<768px)
   ================================================ */
@media (max-width: 768px) {
  .page-discover {
    padding-top: 48px;
    padding-bottom: calc(52px + env(safe-area-inset-bottom));
  }

  .site-header { height: 48px; }
  .header-inner { padding: 0 12px; gap: 8px; }
  .header-title { font-size: 17px; }
  .icon-btn { width: 34px; height: 34px; }
  .icon-btn :deep(svg) { width: 19px; height: 19px; }

  .page-container { padding: 14px 12px 24px; }

  .section-title { font-size: 16px; }
  .section-more { font-size: 12px; }

  .circles-entry { margin-bottom: 22px; }
  .circles-grid { grid-template-columns: repeat(2, 1fr); gap: 10px; }
  .circle-entry { padding: 14px 8px 12px; border-radius: calc(var(--radius-lg) * 0.85); }
  .circle-ic { width: 46px; height: 46px; }
  .circle-name { font-size: 13px; }
  .circle-members { font-size: 11px; }

  /* 新模块：我的足迹 / 我关注的吧 / 精选圈子 移动端适配 */
  .section-title-bold { font-size: 16px; }

  .footprint-section { margin-bottom: 20px; }
  .footprint-scroll { gap: 14px; }
  .footprint-item { width: 58px; }
  .footprint-icon { width: 46px; height: 46px; border-radius: 12px; }
  .footprint-name { font-size: 11px; }

  .followed-section { margin-bottom: 20px; }
  .followed-grid { gap: 10px; }
  .followed-item { padding: 14px 8px 12px; border-radius: calc(var(--radius-lg) * 0.85); }
  .followed-icon { width: 42px; height: 42px; }
  .followed-name { font-size: 12.5px; }
  .followed-heat { font-size: 10px; padding: 1px 6px; }
  .followed-empty-cell { padding: 14px 10px; font-size: 12px; }
  .expand-btn { padding: 5px 18px; font-size: 12px; margin-top: 12px; }

  .featured-section { margin-bottom: 20px; }
  .featured-card { width: 220px; padding: 12px; border-radius: calc(var(--radius-lg) * 0.85); }
  .featured-icon { width: 40px; height: 40px; }
  .featured-name { font-size: 13px; }
  .featured-members { font-size: 11px; }
  .featured-desc { font-size: 12px; }
  .featured-top { gap: 8px; margin-bottom: 6px; }

  .feed-tab { padding: 5px 13px; font-size: 12.5px; }

  .feed { column-gap: 8px; }
  .card {
    margin-bottom: 8px;
    border-radius: calc(var(--radius-lg) * 0.8);
  }
  .card-img { border-radius: calc(var(--radius-lg) * 0.8) calc(var(--radius-lg) * 0.8) 0 0; }
  .card-body { padding: 8px 10px 10px; }
  .card-top { margin-bottom: 6px; gap: 6px; }
  .circle-pill { font-size: 10px; padding: 2px 7px; }
  .join-btn { font-size: 10px; padding: 2px 8px; }
  .card-title { font-size: 13px; margin-bottom: 6px; line-height: 1.38; }
  .card--text .card-body { padding: 12px; }
  .avatar-sm { width: 20px; height: 20px; }
  .author-name { font-size: 12px; }
  .like-count { font-size: 12px; }
  .card-likes :deep(svg) { width: 13px; height: 13px; }
  .title-icon { margin-top: 2px; }
}

/* ================================================
   REDUCED MOTION
   ================================================ */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
  }
}

/* ================================================
   APPLY CREATE CIRCLE DIALOG（创建吧申请表单）
   ================================================ */
.apply-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.form-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.form-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-700, #3a3a3c);
}
.req {
  color: var(--state-error, #ff3b30);
  margin-left: 2px;
}
.form-input,
.form-textarea {
  width: 100%;
  padding: 9px 12px;
  font-size: 14px;
  font-family: inherit;
  color: var(--text-800);
  background: var(--bg-100, #f2f2f7);
  border: 1px solid transparent;
  border-radius: 10px;
  outline: none;
  transition: border-color 150ms cubic-bezier(0.32, 0.72, 0, 1),
    background 150ms cubic-bezier(0.32, 0.72, 0, 1);
  resize: none;
}
.form-input:focus,
.form-textarea:focus {
  border-color: var(--brand-500);
  background: var(--bg-50, #fff);
}
.form-hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-400, #8e8e93);
}

/* 图标选择网格 */
.icon-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}
.icon-option {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 10px 4px;
  border-radius: 10px;
  border: 1px solid var(--bg-200, #e5e5ea);
  background: var(--bg-50, #fff);
  color: var(--text-600, #6e6e73);
  cursor: pointer;
  transition: all 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.icon-option:hover {
  border-color: var(--brand-400, #66abff);
  color: var(--brand-500);
}
.icon-option.active {
  border-color: var(--brand-500);
  background: var(--brand-50);
  color: var(--brand-600);
}
.icon-label {
  font-size: 11px;
  font-weight: 500;
}

/* 颜色选择网格 */
.color-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.color-option {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 2px solid transparent;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: transform 150ms cubic-bezier(0.32, 0.72, 0, 1);
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.05);
}
.color-option:hover {
  transform: scale(1.1);
}
.color-option.active {
  border-color: var(--bg-50, #fff);
  box-shadow: 0 0 0 2px var(--text-800, #1d1d1f);
}

/* 表单预览 */
.form-preview {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: var(--bg-100, #f2f2f7);
  border-radius: 12px;
}
.preview-ic {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.preview-info {
  flex: 1;
  min-width: 0;
}
.preview-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-800);
  line-height: 1.2;
}
.preview-slug {
  font-size: 12px;
  color: var(--text-400, #8e8e93);
  margin-top: 2px;
}

/* 弹窗底部按钮 */
.btn-cancel,
.btn-submit {
  padding: 8px 18px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.btn-cancel {
  background: var(--bg-200, #e5e5ea);
  color: var(--text-700, #3a3a3c);
  border: none;
}
.btn-cancel:hover {
  background: var(--bg-300, #d1d1d6);
}
.btn-submit {
  background: var(--brand-500);
  color: #fff;
  border: none;
}
.btn-submit:hover:not(:disabled) {
  background: var(--brand-600);
}
.btn-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
