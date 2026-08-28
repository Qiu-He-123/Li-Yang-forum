<script setup lang="ts">
/**
 * 广场页（路由：/circles，原"圈子发现页"，底部 Tab 更名为"广场"）
 * 对齐 TT 语音风格广场：
 * - 顶部大标题导航条：关注 / 为你推荐（派对已删）
 * - 圈子展示区：#图标 + 圆形/方形图 + 名字，最多 2 行 + 创建圈子按钮
 * - 帖子筛选 Tab 条：全部 / 推荐 / <每个圈子名称>（默认选中"推荐"）
 * - 帖子卡片：微信朋友圈风（头像/昵称/关注按钮/时间/正文/九宫图/转发 点赞 评论数据）
 * - 保留：创建圈子申请、加入圈子、搜索入口
 */
import { computed, onActivated, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useFadeUpdate } from '../composables/useFadeUpdate'
defineOptions({ name: 'CircleDiscoverView' })

const { fadeActive, triggerFade } = useFadeUpdate()
import { useRoute, useRouter } from 'vue-router'

import EmptyState from '../components/common/EmptyState.vue'
import PostImages from '../components/post/PostImages.vue'
import PostListSkeleton from '../components/post/PostListSkeleton.vue'
import PostPetBox from '../components/post/PostPetBox.vue'
import InfiniteScrollFooter from '../components/common/InfiniteScrollFooter.vue'
import { useInfiniteScroll } from '../composables/useInfiniteScroll'
import { Dialog, Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import { useSessionStore } from '../stores/session'
import { useUIStore } from '../stores/ui'
import { useNotificationStore } from '../stores/notification'
import { useUserStore } from '../stores/user'
import { usePostStore } from '../stores/post'
import { useCircleStore } from '../stores/circle'
import { useAnnouncementStore } from '../stores/announcement'
import { useInteractionStore } from '../stores/interaction'
import { viewPost } from '../api/post'
import { likeTarget, unlikeTarget } from '../api/interaction'
import { createComment } from '../api/comment'
import { followUser, unfollowUser } from '../api/follow'
import { applyCreateCircle } from '../api/circleApply'
import { listViewedCircles } from '../api/circle'
import { listActivities } from '../api/activity'
import type { Circle, Post } from '../types/api'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const uiStore = useUIStore()
const notificationStore = useNotificationStore()
const userStore = useUserStore()
const postStore = usePostStore()
const circleStore = useCircleStore()
const announcementStore = useAnnouncementStore()
const interactionStore = useInteractionStore()
import { useFollowStore } from '../stores/follow'
const followStore = useFollowStore()
import AiStatusBadge from '../components/common/AiStatusBadge.vue'

const { loading: loadMoreLoading, error: loadMoreError, retry: retryLoadMore } = useInfiniteScroll({
  hasMore: computed(() => postStore.hasMore),
  onLoadMore: () => postStore.loadMore(),
  containerSelector: '.page-discover',
})

/** 广场卡片宠物与首页组局一致：体积与桌面漂浮宠相同(120)、float 模式可动可飞 */
const CARD_PET_SIZE = 120

// ====== 广场顶部大标题 Tab（截图 2 风格：关注 / 为你推荐；删除"派对"）======
type PlazaTopTab = 'follow' | 'recommend'
const topTab = ref<PlazaTopTab>('recommend')

// ====== 圈子快捷入口（一行横滑，轻量小图标） ======
const plazaCircleSlots = 7 // 一行显示 7 个（创建圈子 + 6 个热门）
// 固定排序：按后端 sort_order 升序，保证「表白墙→求助区→游戏开黑」顺序永远不变
const sortedCircles = computed(() =>
  [...circleStore.circles]
    .filter((c) => c.slug !== 'default')
    .sort((a, b) => (a.sort_order ?? 99) - (b.sort_order ?? 99)),
)
const plazaCircles = computed(() => sortedCircles.value.slice(0, plazaCircleSlots - 1))
const totalCircleCount = computed(() => circleStore.circles.filter((c) => c.slug !== 'default').length)

// ====== 运营活动卡片（接后端 /activities，进行中活动横滑展示）======
interface PartyCard {
  id: number
  tag: string
  title: string
  variant: string
  link: string
}

const partyCards = ref<PartyCard[]>([])

/** 活动标题：超长截断，展示两行 */
function partyCardTitle(a: { title: string }): string {
  const t = a.title.trim()
  return t.length > 14 ? t.slice(0, 14) + '…' : t
}

async function loadPartyCards() {
  try {
    const { data: resp } = await listActivities(1, 6, { showGlobalLoading: false })
    const items: any[] = (resp as any).data?.items || (resp as any).data?.data?.items || []
    // 仅展示进行中（is_active）的活动，最多 6 个
    partyCards.value = items
      .filter((a: any) => a && a.is_active)
      .slice(0, 6)
      .map((a: any, i: number) => ({
        id: a.id,
        tag: a.organizer || '官方活动',
        title: partyCardTitle(a),
        variant: `gradient${(i % 3) + 1}`,
        link: `/activities/${a.id}`,
      }))
  } catch {
    partyCards.value = [] // 加载失败：整个模块隐藏，不阻塞广场
  }
}

// ====== 帖子筛选 Tab：全部 / 推荐 / <各圈子名称>（默认选中"推荐"）======
// 注意："推荐"在这里是我们自己做的"热门 + 按互动"视图，用 postStore.view = 'hot' 即可
type CircleFilterMode = 'all' | 'recommend' | string // string = 某个 circle.slug
const circleFilter = ref<CircleFilterMode>('recommend')

const circleFilterTabs = computed<{ key: CircleFilterMode; label: string }[]>(() => {
  const tabs: { key: CircleFilterMode; label: string }[] = [
    { key: 'all', label: '全部' },
    { key: 'recommend', label: '推荐' },
  ]
  for (const c of sortedCircles.value) {
    tabs.push({ key: c.slug, label: c.name })
  }
  return tabs
})

// 切换筛选 Tab：同步 postStore 的 view/category 并重新拉 feed
async function onCircleFilterChange(key: CircleFilterMode) {
  circleFilter.value = key
  postStore.setPage(1)
  applyCircleFilterToStore(key)
  await postStore.loadPosts()
  scrollFeedIntoView()
}

// 切换筛选/顶栏 Tab 后，精准让动态 Feed 停在「固定顶栏 + 吸顶筛选条」正下方，
// 保证首帖的头像与昵称完整露出，不被导航遮挡。
function scrollFeedIntoView() {
  const feed = document.querySelector<HTMLElement>('.page-discover .feed-section')
  if (!feed) return
  const header = document.querySelector<HTMLElement>('.page-discover .plaza-header')
  const filter = document.querySelector<HTMLElement>('.page-discover .plaza-filter')
  const overlay = (header ? header.clientHeight : 0) + (filter ? filter.clientHeight : 0)
  const target = feed.getBoundingClientRect().top + window.pageYOffset - overlay - 10
  window.scrollTo({ top: Math.max(0, target), behavior: 'smooth' })
}

// 把「圈子二级 Tab」同步到 postStore（不主动请求，由上层组合决定）
function applyCircleFilterToStore(key: CircleFilterMode) {
  if (key === 'all') {
    postStore.setView('all')
    postStore.setCategory('')
  } else if (key === 'recommend') {
    postStore.setView('hot')
    postStore.setCategory('')
  } else {
    postStore.setView('all')
    postStore.setCategory(key as string)
  }
}

// ====== 顶部广场 Tab 切换：关注 / 为你推荐（修复样式 + 接口双重问题）======
// 关键：点击谁，谁应用【20px/700/黑色/蓝色下划线】，不是永远"为你推荐"最大。
// 关注流 → 后端 view=following 接口；推荐流 → hot/all 按当前圈子筛选决定。
async function onTopTabChange(tab: PlazaTopTab) {
  if (topTab.value === tab) return // 点击同一个：不重复请求
  topTab.value = tab
  postStore.setPage(1)
  if (tab === 'follow') {
    // 关注流：走后端 view=following，忽略圈子筛选（圈子 Tab 视觉保持不变即可）
    postStore.setView('following')
    postStore.setCategory('')
  } else {
    // 推荐：还原为当前圈子 Tab 的配置
    applyCircleFilterToStore(circleFilter.value)
  }
  await postStore.loadPosts()
  scrollFeedIntoView()
}

// 展示给 feed：
// - 顶部 Tab=关注：后端已经用 view=following 返回关注用户动态，前端直接渲染；
// - 顶部 Tab=推荐：后端按当前 circleFilter 拉取，前端直接渲染。
//   保留旧的 followStore 客户端兜底只是防御性，实际用不到。
const displayedPosts = computed<Post[]>(() => {
  let list = postStore.posts
  if (topTab.value === 'follow' && session.userId) {
    const followingIds = new Set<number>(
      Object.entries(followStore.followingMap)
        .filter(([, v]) => v)
        .map(([k]) => Number(k))
    )
    if (followingIds.size > 0) {
      list = list.filter((p) => p.author_id === session.userId || (p.author_id && followingIds.has(p.author_id)))
    }
  }
  return list
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
  // —— 按规范：图标底色饱和度 +15%（加厚不褪色）；gradient 端色加深，保持艳俗边界以内
  confess:  { icon: 'heart', gradient: 'linear-gradient(135deg, #ff4e8a, #9a2ecf)', pillBg: '#f7eaff', pillColor: '#9a2ecf', cardBg: '#faf5ff', iconColor: '#9a2ecf' },
  help:     { icon: 'circle-question', gradient: 'linear-gradient(135deg, #4a96ff, #004fb0)', pillBg: '#e8f2ff', pillColor: '#0064d6', cardBg: '#e8f2ff', iconColor: '#0064d6' },
  lost:     { icon: 'circle-question', gradient: 'linear-gradient(135deg, #4a96ff, #004fb0)', pillBg: '#e8f2ff', pillColor: '#004fb0', cardBg: '#ffecea', iconColor: '#ff3b30' },
  market:   { icon: 'tag', gradient: 'linear-gradient(135deg, #ff821a, #e5551e)', pillBg: '#fff3e6', pillColor: '#c05800', cardBg: '#ffffff', iconColor: '#c05800' },
  study:    { icon: 'file', gradient: 'linear-gradient(135deg, #29b450, #0064d6)', pillBg: '#e8f2ff', pillColor: '#004fb0', cardBg: '#e8f2ff', iconColor: '#0064d6' },
  food:     { icon: 'map-pin', gradient: 'linear-gradient(135deg, #ffa024, #ef7d00)', pillBg: '#fff3e6', pillColor: '#c05800', cardBg: '#ffffff', iconColor: '#c05800' },
  game:     { icon: 'star', gradient: 'linear-gradient(135deg, #4a48c7, #9f3dcf)', pillBg: '#eeeaff', pillColor: '#4a48c7', cardBg: '#f3f0ff', iconColor: '#4a48c7' },
  photo:    { icon: 'camera', gradient: 'linear-gradient(135deg, #29b450, #00ada5)', pillBg: '#e9f9ee', pillColor: '#29b450', cardBg: '#ffffff', iconColor: '#29b450' },
  club:     { icon: 'star', gradient: 'linear-gradient(135deg, #9a2ecf, #ff4e8a)', pillBg: '#f7eaff', pillColor: '#9a2ecf', cardBg: '#ffffff', iconColor: '#9a2ecf' },
  sport:    { icon: 'flame', gradient: 'linear-gradient(135deg, #0064d6, #29b450)', pillBg: '#e8f2ff', pillColor: '#0064d6', cardBg: '#ffffff', iconColor: '#0064d6' },
  match:    { icon: 'shuffle', gradient: 'linear-gradient(135deg, #ef7d00, #e5551e)', pillBg: '#fff3e6', pillColor: '#c05800', cardBg: '#ffffff', iconColor: '#ef7d00' },
  treehole: { icon: 'lock', gradient: 'linear-gradient(135deg, #7d7d82, #3b3b3e)', pillBg: '#f2f2f7', pillColor: '#3b3b3e', cardBg: '#ffffff', iconColor: '#7d7d82' },
  qa:       { icon: 'circle-question', gradient: 'linear-gradient(135deg, #4a96ff, #004fb0)', pillBg: '#e8f2ff', pillColor: '#004fb0', cardBg: '#e8f2ff', iconColor: '#0064d6' },
  flea:     { icon: 'tag', gradient: 'linear-gradient(135deg, #29b450, #00ada5)', pillBg: '#e9f9ee', pillColor: '#29b450', cardBg: '#ffffff', iconColor: '#29b450' },
}

// ====== 精选圈子（横向滑动使用，原模板 featuredCircles 引用）======
const featuredCircles = computed(() => sortedCircles.value.slice(0, 12))
// ====== 全部圈子模块（原 topCircles 引用）======
const topCircles = computed(() => sortedCircles.value.slice(0, 8))

// ====== 旧 feedTab（兼容 onTabChange / feed 空状态文本）======
// 新广场用 topTab + circleFilter 驱动；保留 feedTab 仅避免模板空状态文案直接读变量报错
const feedTab = computed<'joined' | 'all'>(() => (topTab.value === 'follow' ? 'joined' : 'all'))

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

// ============ 广场帖子：点赞 / 评论 / 分享（真实接口，不再是死按钮）============
/** 点赞 / 取消点赞。未登录先弹登录框；乐观更新计数避免闪烁。 */
async function onToggleLikePost(e: Event, post: Post) {
  e.stopPropagation()
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  const liked = interactionStore.likedPostIds.has(post.id)
  // 乐观更新
  if (liked) {
    post.like_count = Math.max(0, (post.like_count ?? 1) - 1)
    interactionStore.toggleLikedPost(post.id, false)
  } else {
    post.like_count = (post.like_count ?? 0) + 1
    interactionStore.toggleLikedPost(post.id, true)
  }
  try {
    if (liked) {
      const { data } = await unlikeTarget('post', post.id)
      post.like_count = data.data.like_count
    } else {
      const { data } = await likeTarget('post', post.id)
      post.like_count = data.data.like_count
    }
  } catch (err) {
    // 回滚
    if (!liked) {
      post.like_count = Math.max(0, (post.like_count ?? 1) - 1)
      interactionStore.toggleLikedPost(post.id, false)
    } else {
      post.like_count = (post.like_count ?? 0) + 1
      interactionStore.toggleLikedPost(post.id, true)
    }
    toast.error((err as Error).message || '操作失败，请稍后再试')
  }
}
function isLikedPost(post: Post): boolean {
  return interactionStore.likedPostIds.has(post.id)
}

/** 分享：记录一次 +1（后端 /posts/:id/share），前端显示最新 share_count */
async function onSharePost(e: Event, post: Post) {
  e.stopPropagation()
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  try {
    // 优先调后端 viewPost 接口做一次浏览+分享计数兜底
    await viewPost(post.id)
    // 复制到剪贴板，提示（和微信朋友圈一样）
    try {
      const url = `${window.location.origin}/post/${post.id}`
      await navigator.clipboard.writeText(url)
      toast.success('链接已复制，快去分享给好友吧～')
    } catch {
      toast.success('感谢分享')
    }
    post.share_count = (post.share_count ?? 0) + 1
  } catch {
    toast.info('分享功能暂时不可用')
  }
}

/** 点击评论：展开就地评论框（不会打开详情页，像朋友圈一样） */
const activeCommentPostId = ref<number | null>(null)
const commentDraft = ref('')
const commentSubmitting = ref(false)
function onOpenCommentInput(e: Event, post: Post) {
  e.stopPropagation()
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  activeCommentPostId.value = post.id
  commentDraft.value = ''
  // 聚焦
  nextTick(() => {
    const el = document.querySelector<HTMLTextAreaElement>(`textarea[data-post-id="${post.id}"]`)
    el?.focus()
  })
}
function onCancelComment(e: Event) {
  e.stopPropagation()
  activeCommentPostId.value = null
  commentDraft.value = ''
}
async function onSubmitComment(post: Post) {
  const content = commentDraft.value.trim()
  if (!content) {
    toast.info('请输入评论内容')
    return
  }
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  commentSubmitting.value = true
  try {
    const { data } = await createComment(post.id, { content })
    post.comment_count = data.data.post_comment_count ?? (post.comment_count ?? 0) + 1
    toast.success('评论成功')
    activeCommentPostId.value = null
    commentDraft.value = ''
  } catch (err) {
    toast.error((err as Error).message || '评论失败，请稍后再试')
  } finally {
    commentSubmitting.value = false
  }
}

// 需要 nextTick 聚焦评论框
import { nextTick } from 'vue'

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
  // 运营活动卡片（后台并行加载，失败不影响广场主流程）
  loadPartyCards()
  // 第一波：公告 + 圈子列表（与 session 校验并行）
  await Promise.all([
    announcementStore.loadAnnouncements(),
    circleStore.loadCircles(),
  ])
  // 广场页：默认选中"推荐" Tab → 对应热门视图
  postStore.setView('hot')
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
  // 恢复广场页默认视图（可能被首页改成 latest）
  if (postStore.activeView !== 'hot' || postStore.activeCategory !== '') {
    postStore.setView('hot')
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
    uiStore.openAuthDialog()
    return
  }
  await router.replace({ query: { ...route.query, tab } })
  // Tab 切换不需要重新拉接口，displayedPosts 计算属性会自动过滤
}

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
  router.push('/search')
}

function openNotifications() {
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  router.push('/notifications')
}

function isJoined(slug: string): boolean {
  const c = circleStore.circles.find((x) => x.slug === slug)
  return !!c?.is_joined
}

// ============ 帖子卡片辅助：关注/取关 + 时间格式化 ============
async function onToggleFollowPostAuthor(e: Event, post: Post) {
  e.stopPropagation()
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  if (!post.author_id || post.is_anonymous) return
  try {
    await followStore.toggleFollow(post.author_id)
  } catch (err) {
    toast.error((err as Error).message)
  }
}

function isFollowingAuthor(post: Post): boolean {
  if (!post.author_id) return false
  return followStore.isFollowing(post.author_id)
}

function formatRelativeTime(input: string | Date | null | undefined): string {
  if (!input) return ''
  const d = input instanceof Date ? input : new Date(input)
  if (Number.isNaN(d.getTime())) return String(input)
  const diffMs = Date.now() - d.getTime()
  const s = Math.max(1, Math.floor(diffMs / 1000))
  if (s < 60) return `${s}秒前`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}分钟前`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}小时前`
  const day = Math.floor(h / 24)
  if (day < 30) return `${day}天前`
  const mo = Math.floor(day / 30)
  if (mo < 12) return `${mo}个月前`
  return `${Math.floor(mo / 12)}年前`
}

function openCreatePost() {
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  router.push('/post/create')
}

function openAuthorHome(e: Event, post: Post) {
  e.stopPropagation()
  if (!post.author_id) return
  router.push(`/user/${post.author_id}`)
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
    uiStore.openAuthDialog()
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
    <!-- ====== 广场顶部加粗标题 Tab：关注 / 为你推荐 ====== -->
    <header class="plaza-header" role="banner">
      <div class="plaza-header__inner">
        <div class="plaza-header__tabs">
          <button
            class="plaza-tab"
            :class="{ 'is-active': topTab === 'follow' }"
            type="button"
            @click="onTopTabChange('follow')"
          >
            关注
          </button>
          <button
            class="plaza-tab"
            :class="{ 'is-active': topTab === 'recommend' }"
            type="button"
            @click="onTopTabChange('recommend')"
          >
            为你推荐
          </button>
        </div>
        <div class="plaza-header__actions">
          <button class="plaza-icon-btn" type="button" aria-label="通知" @click="openNotifications">
            <Icon name="bell" :size="22" />
            <span v-if="notificationStore.unreadCount > 0" class="plaza-icon-badge">
              {{ notificationStore.unreadCount > 99 ? '99+' : notificationStore.unreadCount }}
            </span>
          </button>
          <button class="plaza-icon-btn" type="button" aria-label="搜索" @click="openSearch">
            <Icon name="search" :size="22" />
          </button>
        </div>
      </div>
    </header>

    <!-- ====== 主内容 ====== -->
    <div class="page-container">
      <!-- ====== 模块1：圈子快捷入口（横滑，末尾带"查看全部"卡片）====== -->
      <section class="plaza-quick" aria-label="圈子入口">
        <div class="plaza-quick__scroll">
          <button class="plaza-quick__item plaza-quick__item--create" type="button" @click="openApplyDialog">
            <span class="plaza-quick__icon plaza-quick__icon--create">
              <Icon name="plus" :size="20" color="#fff" />
            </span>
            <span class="plaza-quick__name">创建</span>
          </button>
          <button
            v-for="circle in plazaCircles"
            :key="'qc-' + circle.id"
            class="plaza-quick__item"
            type="button"
            @click="openCircle(circle.slug)"
          >
            <span
              class="plaza-quick__icon"
              :style="{ background: getCircleMeta(circle.slug).gradient }"
              aria-hidden="true"
            >
              <Icon :name="getCircleMeta(circle.slug).icon" :size="20" />
            </span>
            <span class="plaza-quick__name">{{ circle.name }}</span>
          </button>
          <!-- 末尾：查看全部（圈子总数 > 6 时显示）-->
          <button
            v-if="totalCircleCount > 6"
            class="plaza-quick__item"
            type="button"
            @click="router.push('/circles/all')"
          >
            <span class="plaza-quick__icon plaza-quick__icon--more">
              <Icon name="grid" :size="20" />
            </span>
            <span class="plaza-quick__name">查看全部</span>
          </button>
        </div>
        <div class="plaza-quick__fade" aria-hidden="true"></div>
      </section>

      <!-- ====== 模块2：运营活动横滑卡片（数组驱动，空数组时隐藏）====== -->
      <section v-if="partyCards.length > 0" class="plaza-party" aria-label="活动推荐">
        <div class="plaza-party__scroll">
          <button
            v-for="(card, idx) in partyCards"
            :key="'pp-' + idx"
            class="plaza-party__card"
            :class="'plaza-party__card--' + card.variant"
            type="button"
            @click="card.link ? router.push(card.link) : null"
          >
            <span class="plaza-party__tag">{{ card.tag }}</span>
            <h3 class="plaza-party__title">{{ card.title }}</h3>
          </button>
        </div>
      </section>

      <!-- ====== 模块3：帖子筛选 Tab 条（全部 / 推荐 / 每个圈子名）====== -->
      <section class="plaza-filter" aria-label="内容分类">
        <div class="plaza-filter__scroll">
          <button
            v-for="tab in circleFilterTabs"
            :key="'ft-' + tab.key"
            class="plaza-filter__tab"
            :class="{ 'is-active': circleFilter === tab.key }"
            type="button"
            @click="onCircleFilterChange(tab.key)"
          >
            {{ tab.label }}
          </button>
        </div>
      </section>

      <!-- ====== 模块3：微信朋友圈风 Feed（单列卡片）====== -->
      <section class="feed-section plaza-feed" aria-label="广场动态">
        <PostListSkeleton v-if="postStore.loading" :count="4" />

        <div v-else-if="displayedPosts.length" :class="{ 'swr-updated': fadeActive }" class="plaza-feed__list">
          <article
            v-for="post in displayedPosts"
            :key="post.id"
            class="post-card"
            @click="openPost(post)"
          >
            <!-- 顶部：头像 / 昵称-推荐时间 / 关注 / 更多 (图2朋友圈样式) -->
            <div class="post-card__head">
              <div class="post-card__avatar-wrap">
                <img
                  v-if="!post.is_anonymous && post.author_avatar_url"
                  class="post-card__avatar"
                  :src="post.author_avatar_url"
                  :alt="post.author"
                  loading="lazy"
                />
                <span
                  v-else
                  class="post-card__avatar post-card__avatar--ph"
                  :class="`av-${(post.author_id || 0) % 5 + 1}`"
                >{{ post.is_anonymous ? '匿' : (post.author || 'U').slice(0,1) }}</span>
                <!-- 头像右下角小标记（粉色♀符号） -->
                <span class="post-card__avatar-dot" aria-hidden="true">♀</span>
              </div>
              <div class="post-card__author-info">
                <div class="post-card__name-row">
                  <button
                    class="post-card__name-btn"
                    type="button"
                    @click="(e) => openAuthorHome(e, post)"
                  >{{ post.is_anonymous ? '匿名同学' : post.author }}</button>
                  <!-- 发帖人的宠物（与首页组局同样采用 float：体积同漂浮宠、可移动可飞行）；
                       自己的帖子默认隐藏卡片宠物，由桌面漂浮宠自动飞入 -->
                  <PostPetBox
                    v-if="!post.is_anonymous && post.author_id"
                    :user-id="post.author_id"
                    :size="CARD_PET_SIZE"
                    :self="post.author_id === session.userId"
                    :author-name="post.author"
                  />
                </div>
                <div class="post-card__sub">
                  <span>{{ formatRelativeTime(post.created_at) }}推荐</span>
                </div>
              </div>

              <div class="post-card__actions-top">
                <button
                  v-if="!post.is_anonymous && post.author_id && post.author_id !== session.userId"
                  class="post-card__follow"
                  :class="{ 'is-following': isFollowingAuthor(post) }"
                  type="button"
                  @click="(e) => onToggleFollowPostAuthor(e, post)"
                >
                  {{ isFollowingAuthor(post) ? '已关注' : '+ 关注' }}
                </button>
                <button class="post-card__more" type="button" aria-label="更多">
                  <Icon name="more-horizontal" :size="20" />
                </button>
              </div>
            </div>

            <!-- 正文文字 -->
            <p v-if="post.content" class="post-card__text">{{ post.content }}</p>

            <!-- 图片/视频 (2列并排，圆角) -->
            <PostImages
              v-if="post.image_urls?.length || post.video_urls?.length"
              class="post-card__media"
              :urls="post.image_urls"
              :videos="post.video_urls"
            />

            <!-- 底部：分享/点赞/评论 均匀分布 -->
            <div class="post-card__foot">
              <button
                class="post-card__stat"
                type="button"
                @click="(e) => onSharePost(e, post)"
              >
                <Icon name="repeat" :size="20" />
                <span>{{ formatCount(post.share_count ?? 0) }}</span>
              </button>
              <button
                class="post-card__stat"
                :class="{ 'is-liked': isLikedPost(post) }"
                type="button"
                @click="(e) => onToggleLikePost(e, post)"
              >
                <Icon :name="isLikedPost(post) ? 'heart-filled' : 'heart'" :size="20" />
                <span>{{ formatCount(post.like_count ?? 0) }}</span>
              </button>
              <button
                class="post-card__stat"
                type="button"
                @click="(e) => onOpenCommentInput(e, post)"
              >
                <Icon name="message-circle" :size="20" />
                <span>{{ formatCount(post.comment_count ?? 0) }}</span>
              </button>
            </div>

            <!-- 就地展开的评论框（朋友圈风格：点评论按钮直接在卡片里展开） -->
            <Transition name="comment-bar">
              <div
                v-if="activeCommentPostId === post.id"
                class="post-card__comment-bar"
                @click.stop
              >
                <textarea
                  :data-post-id="post.id"
                  v-model="commentDraft"
                  class="comment-bar__input"
                  rows="2"
                  placeholder="写评论…"
                ></textarea>
                <div class="comment-bar__actions">
                  <button
                    class="comment-bar__btn comment-bar__btn--ghost"
                    type="button"
                    @click="onCancelComment"
                  >取消</button>
                  <button
                    class="comment-bar__btn comment-bar__btn--primary"
                    type="button"
                    :disabled="commentSubmitting || !commentDraft.trim()"
                    @click="onSubmitComment(post)"
                  >{{ commentSubmitting ? '发送中…' : '发送' }}</button>
                </div>
              </div>
            </Transition>
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
          icon="file-text"
          :text="topTab === 'follow' ? '你还没有关注的人，去为你推荐看看吧' : '暂无帖子，去发布第一条动态吧。'"
        />
      </section>
    </div>

    <!-- ====== 右下角：发布相机 FAB ====== -->
    <button class="plaza-fab" type="button" aria-label="发布动态" @click="openCreatePost">
      <Icon name="camera" :size="24" color="#fff" />
    </button>

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
  --plaza-header-h: 52px;
  min-height: 100vh;
  /* 规范：背景加深一档 #F2F3F7，清爽不刺眼 */
  background: #F2F3F7;
  padding-top: 52px;
  padding-bottom: calc(56px + 28px + env(safe-area-inset-bottom));
  color: #1d1d1f;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', var(--font-sans, inherit);
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  position: relative;
}

/* ================================================
   PLAZA HEADER (TT 风格：左文字 Tab / 右 社团胶囊 + 搜索)
   ================================================ */
.plaza-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  height: 52px;
  background: #ffffff;
  border-bottom: 0.5px solid rgba(0, 0, 0, 0.06);
}
.plaza-header__inner {
  max-width: 1200px;
  margin: 0 auto;
  height: 100%;
  padding: 0 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.plaza-header__tabs {
  display: flex;
  align-items: baseline;
  gap: 18px;
  flex: 1;
  min-width: 0;
}
/* ====== 广场顶部 Tab：关注 / 为你推荐（规范严格对齐）
   未选中：18px / 400 / #666；
   选中态：20px / 700 / #111 + 底部蓝色短下划线（宽度跟随文字）。 */
.plaza-tab {
  position: relative;
  padding: 2px 0;
  background: transparent;
  border: none;
  cursor: pointer;
  /* 未选中 */
  font-size: 18px;
  font-weight: 400;
  color: #666666;
  letter-spacing: 0;
  line-height: 1.3;
  transition: font-size 160ms ease, font-weight 160ms ease, color 160ms ease;
  white-space: nowrap;
}
.plaza-tab.is-active {
  font-size: 20px;
  font-weight: 700;
  color: #111111;
}
.plaza-tab.is-active::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: -6px;
  /* 宽度跟随文字：left/right:0 自然等于 tab 自身宽度；高度 2px，饱和蓝 */
  height: 2px;
  border-radius: 2px;
  background: #0a6cff;
}
.plaza-header__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.plaza-club-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px 4px 4px;
  background: linear-gradient(135deg, #7b5cff 0%, #30b3ff 100%);
  color: #fff;
  border-radius: 999px;
  border: none;
  cursor: pointer;
  font-size: 11px;
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(48, 179, 255, 0.25);
}
.plaza-club-btn__avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.22);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.plaza-icon-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: transparent;
  border: none;
  /* 规范：铃铛/搜索图标颜色加深到 #222 */
  color: #222222;
  cursor: pointer;
  transition: background 150ms ease, color 150ms ease;
}
.plaza-icon-btn:hover { background: rgba(0,0,0,0.05); color: #000; }
.plaza-icon-badge {
  position: absolute;
  top: 2px;
  right: 0;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  background: #ff3b30;
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  line-height: 16px;
  text-align: center;
  border-radius: 8px;
  border: 1.5px solid #fff;
  box-shadow: 0 1px 3px rgba(255, 59, 48, 0.3);
  white-space: nowrap;
}

/* ================================================
   PAGE CONTAINER
   ================================================ */
.page-container {
  max-width: 720px;
  margin: 0 auto;
  padding: 14px 14px calc(72px + env(safe-area-inset-bottom));
}

/* ================================================
   SECTION TITLE BOLD (legacy, 保留避免残留引用报错)
   ================================================ */
.section-title-bold {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-800);
  margin: 0;
}

/* ================================================
   PLAZA QUICK ENTRY (横滑，末尾"查看全部"卡片)
   ================================================ */
.plaza-quick {
  position: relative;
  margin-bottom: 20px;
}
.plaza-quick__scroll {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 2px 2px 6px;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;
}
.plaza-quick__scroll::-webkit-scrollbar { display: none; }
.plaza-quick__item {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 7px;
  width: 52px;
  padding: 0;
  background: transparent;
  border: none;
  cursor: pointer;
  text-align: center;
  transition: transform 120ms ease;
}
.plaza-quick__item:active { transform: scale(0.92); }
.plaza-quick__icon {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  /* 去掉全局压饱和滤镜，让底色饱和度自然体现（实际 gradient 已 +15%）*/
  filter: none;
}
.plaza-quick__icon--create {
  /* 橙：饱和度提高 */
  background: linear-gradient(135deg, #ff9e50, #ff6b1a);
  filter: none;
}
.plaza-quick__icon--more {
  background: #e6e8ef;
  filter: none;
  color: #555566;
}
.plaza-quick__icon :deep(svg) { width: 20px; height: 20px; color: #fff; }
.plaza-quick__icon--more :deep(svg) { color: #555566; }
.plaza-quick__name {
  font-size: 11px;
  font-weight: 500;
  /* 规范：文字 #555566，远距离可读 */
  color: #555566;
  line-height: 1.2;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.plaza-quick__fade {
  position: absolute;
  top: 0;
  right: -1px;
  bottom: 6px;
  width: 28px;
  background: linear-gradient(90deg, transparent, #F2F3F7);
  pointer-events: none;
}

/* ================================================
   PLAZA PARTY BANNER (横向滑动运营卡片 - 一屏一张+露出下张)
   ================================================ */
.plaza-party {
  margin: 0 -12px 24px;
}
.plaza-party__scroll {
  display: flex;
  gap: 0;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 4px 16px 8px;
  scroll-snap-type: x mandatory;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;
}
.plaza-party__scroll::-webkit-scrollbar { display: none; }
.plaza-party__card {
  flex-shrink: 0;
  width: calc(100vw - 56px);
  max-width: 340px;
  height: 84px;
  border-radius: 16px;
  padding: 14px 16px;
  color: #fff;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  cursor: pointer;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06);
  transition: transform 150ms ease;
  position: relative;
  overflow: hidden;
  border: none;
  text-align: left;
  scroll-snap-align: start;
  margin-right: 10px;
}
.plaza-party__card:active { transform: scale(0.98); }
.plaza-party__tag {
  display: inline-block;
  align-self: flex-start;
  padding: 3px 8px;
  /* 规范：标签用"实色深色半透黑"底，文字纯白，立刻醒目；不再半透淡灰 */
  background: rgba(0, 0, 0, 0.55);
  border-radius: 8px;
  font-size: 10px;
  font-weight: 600;
  color: #ffffff;
  letter-spacing: 0.02em;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}
.plaza-party__title {
  font-size: 15px;
  /* 规范：标题字重 600，识别度提升 */
  font-weight: 600;
  line-height: 1.35;
  margin: 0;
  color: #ffffff;
}
/* 规范：Banner 渐变饱和度适度拉高（告别低饱和马卡龙）*/
.plaza-party__card--gradient1 { background: linear-gradient(135deg, #8a96ff 0%, #9f7bd6 50%, #d47fb0 100%); }
.plaza-party__card--gradient2 { background: linear-gradient(135deg, #64b6bf 0%, #4ea28f 50%, #8fb46a 100%); }
.plaza-party__card--gradient3 { background: linear-gradient(135deg, #f2a45a 0%, #e08550 50%, #d77575 100%); }

/* ================================================
   PLAZA FILTER (筛选 Tab：全部 / 推荐 / 圈子名)
   ================================================ */
.plaza-filter {
  position: sticky;
  top: var(--plaza-header-h);
  z-index: 20;
  margin: 0 -12px 16px;
  padding: 6px 0 10px;
  background: #F2F3F7;
}
.plaza-filter__scroll {
  display: flex;
  align-items: center;
  gap: 0;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 0 12px;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;
}
.plaza-filter__scroll::-webkit-scrollbar { display: none; }
.plaza-filter__tab {
  position: relative;
  flex-shrink: 0;
  padding: 8px 2px 10px;
  margin-right: 20px;
  background: transparent;
  border: none;
  font-size: 15px;
  font-weight: 400;
  /* 规范：未选中 → #606474，远距离可读 */
  color: #606474;
  cursor: pointer;
  transition: color 150ms ease, font-weight 150ms ease, font-size 150ms ease;
}
.plaza-filter__tab.is-active {
  /* 选中态：主色、字重加粗；视觉不再发虚 */
  color: var(--brand-600);
  font-weight: 700;
  font-size: 16px;
}
.plaza-filter__tab.is-active::after {
  content: '';
  position: absolute;
  /* 宽度跟随文字：left/right 自然撑开；不写死宽度 */
  left: 10%;
  right: 10%;
  bottom: 2px;
  height: 2px;
  border-radius: 2px;
  /* 规范：2px + 饱和蓝 */
  background: #0a6cff;
}

/* ================================================
   PLAZA FEED (朋友圈风单列卡片)
   ================================================ */
.plaza-feed { padding-bottom: 24px; }
/* 切换筛选/顶部 Tab 后精准定位：由 scrollFeedIntoView 动态计算偏移，
   不再依赖静态 scroll-margin */
.plaza-feed__list {
  display: flex;
  flex-direction: column;
  gap: 0;
  background: #F2F3F7;
}

.post-card {
  position: relative;
  background: #ffffff;
  border-radius: 0;
  padding: 16px 16px 10px;
  margin: 0 0 8px;
  box-shadow: none;
  border-top: 0.5px solid rgba(0, 0, 0, 0.05);
  border-bottom: 0.5px solid rgba(0, 0, 0, 0.05);
  cursor: pointer;
  transition: transform 150ms ease;
  text-align: left;
  width: 100%;
  display: block;
}
.post-card:active { background: #fafafc; }

.post-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}
.post-card__avatar-wrap {
  position: relative;
  flex-shrink: 0;
}
.post-card__author {
  display: flex;
  align-items: center;
  gap: 10px;
  background: transparent;
  border: none;
  padding: 0;
  cursor: pointer;
  text-align: left;
  flex: 1;
  min-width: 0;
}
.post-card__avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
  background: #e5e5ea;
  display: inline-block;
}
.post-card__avatar--ph {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 17px;
  font-weight: 600;
  color: #fff;
  border: 2px solid #fff !important;
}
.post-card__avatar-dot {
  position: absolute;
  right: -1px;
  bottom: -1px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #FF4D8D;
  color: #fff;
  font-size: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid #fff;
  line-height: 1;
}
.post-card__author-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}
.post-card__name-row {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.post-card__name-btn {
  background: none;
  border: none;
  padding: 0;
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #1d1d1f;
  line-height: 1.2;
  cursor: pointer;
  text-align: left;
}
.post-card__name-btn:hover { color: #0A6CFF; }
.post-card__name {
  font-size: 14px;
  font-weight: 700;
  color: #1d1d1f;
  line-height: 1.2;
}
.post-card__badge {
  font-size: 10px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(90deg, #ff6b9d, #af52de);
  padding: 2px 6px;
  border-radius: 4px;
  line-height: 1.3;
}
.post-card__sub {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #8e8e93;
  line-height: 1.3;
  letter-spacing: 0.01em;
}
.post-card__sub-dot {
  width: 2px;
  height: 2px;
  border-radius: 50%;
  background: #c7c7cc;
}
.post-card__sub-topic { color: #0080ff; }

.post-card__actions-top {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}
.post-card__follow {
  padding: 5px 16px;
  background: #E8F2FF;
  color: #0A6CFF;
  font-size: 13px;
  font-weight: 600;
  border-radius: 999px;
  border: none;
  cursor: pointer;
}
.post-card__follow.is-following {
  background: rgba(0, 0, 0, 0.04);
  color: #8E8E93;
  font-weight: 500;
}
.post-card__more {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: transparent;
  border: none;
  color: #8e8e93;
  cursor: pointer;
}
.post-card__more:active { background: #f2f2f7; }

.post-card__text {
  margin: 0 0 10px;
  font-size: 15px;
  line-height: 1.55;
  color: #1d1d1f;
  white-space: pre-wrap;
  word-break: break-word;
}

.post-card__badges {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin: -2px 0 10px;
}
.post-card__badges :deep(.ai-status-badge) { transform: scale(0.9); transform-origin: left center; }
.post-card__tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 999px;
  line-height: 1.4;
}
.post-card__tag--circle { letter-spacing: 0.01em; }
.post-card__tag--warn {
  color: #b45309;
  background: rgba(245, 158, 11, 0.12);
}

.post-card__media {
  margin: 6px 0 4px;
  display: block;
}

.post-card__location {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin: 0 0 10px;
  font-size: 11px;
  color: #007aff;
}
.post-card__location :deep(svg) { width: 12px; height: 12px; }

.post-card__foot {
  display: flex;
  align-items: center;
  justify-content: space-around;
  gap: 0;
  padding: 10px 0 4px;
  border-top: none;
  margin-top: 4px;
}
.post-card__stat {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 6px;
  background: transparent;
  border: none;
  color: #6e6e73;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: color 150ms ease, background 150ms ease;
  border-radius: 6px;
}
.post-card__stat:hover { color: #007aff; background: rgba(0,122,255,0.06); }
.post-card__stat:active { background: rgba(0,0,0,0.05); }
.post-card__stat.is-liked { color: #ff3b60; }
.post-card__stat.is-liked :deep(svg) { color: #ff3b60; fill: #ff3b60; }
.post-card__stat :deep(svg) { width: 22px; height: 22px; }

/* === 就地评论框（朋友圈风：点评论按钮展开，卡片内直接发送） === */
.post-card__comment-bar {
  margin-top: 10px;
  padding: 10px;
  background: #f4f4f7;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.comment-bar__input {
  width: 100%;
  resize: none;
  border: 0.5px solid rgba(0,0,0,0.06);
  background: #ffffff;
  border-radius: 10px;
  padding: 9px 11px;
  font-size: 14px;
  line-height: 1.5;
  color: #1d1d1f;
  outline: none;
  font-family: inherit;
  transition: border-color 150ms ease, box-shadow 150ms ease;
}
.comment-bar__input:focus {
  border-color: #0a6cff;
  box-shadow: 0 0 0 3px rgba(10,108,255,0.10);
}
.comment-bar__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.comment-bar__btn {
  padding: 6px 14px;
  border-radius: 999px;
  border: none;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 150ms ease;
}
.comment-bar__btn--ghost {
  background: #ffffff;
  color: #555566;
}
.comment-bar__btn--ghost:hover { background: #e8e8ed; }
.comment-bar__btn--primary {
  background: linear-gradient(135deg, #2e6bff 0%, #1942c2 100%);
  color: #fff;
  box-shadow: 0 2px 6px rgba(30, 79, 224, 0.25);
}
.comment-bar__btn--primary[disabled] {
  background: #c0c3cf;
  box-shadow: none;
  cursor: not-allowed;
  color: #fff;
}
.comment-bar-enter-active, .comment-bar-leave-active {
  transition: all 220ms cubic-bezier(0.32, 0.72, 0, 1);
}
.comment-bar-enter-from, .comment-bar-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* Moments图片：更紧凑，宽度更贴近截图的2列并排（不再铺满） */
.post-card__media--moments {
  max-width: 78%;
}
@media (max-width: 768px) {
  .post-card__media--moments { max-width: 92%; }
}

/* ================================================
   PLAZA CAMERA FAB (右下发布按钮)
   ================================================ */
.plaza-fab {
  position: fixed;
  right: max(16px, calc((100vw - 720px) / 2 + 16px));
  bottom: calc(80px + env(safe-area-inset-bottom));
  width: 52px;
  height: 52px;
  border-radius: 50%;
  border: 1px solid rgba(0,0,0,0.06);
  cursor: pointer;
  /* 规范：蓝色略微加深；过亮蓝去掉，无重外发光（轻微阴影即可） */
  background: linear-gradient(135deg, #2e6bff 0%, #1e4fe0 60%, #1942c2 100%);
  box-shadow: 0 8px 18px rgba(30, 79, 224, 0.24), 0 2px 4px rgba(0, 0, 0, 0.08);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  z-index: 60;
  transition: transform 150ms ease, box-shadow 150ms ease, filter 150ms ease;
}
.plaza-fab:hover { transform: translateY(-2px); filter: brightness(1.04); box-shadow: 0 10px 22px rgba(30, 79, 224, 0.3), 0 3px 6px rgba(0,0,0,0.1); }
.plaza-fab:active { transform: scale(0.95); filter: brightness(0.98); }
.plaza-fab :deep(svg) { width: 24px; height: 24px; }

/* 渐变头像占位（与旧 .av-* 保持一致，仅改尺寸类） */
.av-1 { background: linear-gradient(135deg, #66abff, #007aff); }
.av-2 { background: linear-gradient(135deg, #34c759, #2e8dff); }
.av-3 { background: linear-gradient(135deg, #ff9500, #007aff); }
.av-4 { background: linear-gradient(135deg, #5856d6, #0064d6); }
.av-5 { background: linear-gradient(135deg, #d1d1d6, #8e8e93); }

/* ================================================
   RESPONSIVE — Mobile (<= 768px)
   ================================================ */
@media (max-width: 768px) {
  .page-discover {
    --plaza-header-h: 48px;
    padding-top: 48px;
    padding-bottom: calc(52px + env(safe-area-inset-bottom));
  }
  .plaza-header { height: 48px; }
  .plaza-header__inner { padding: 0 12px; gap: 10px; }
  .plaza-header__tabs { gap: 14px; }
  .plaza-tab { font-size: 17px; }
  .plaza-tab.is-active { font-size: 19px; }
  .plaza-club-btn__label { display: none; }
  .plaza-club-btn { padding: 4px; }
  .page-container { padding: 12px 12px calc(64px + env(safe-area-inset-bottom)); }

  .plaza-circles { padding: 14px 12px 8px; border-radius: 16px; }
  .plaza-circles__grid { gap: 10px 8px; }
  .plaza-circle-entry__icon { width: 52px; height: 52px; border-radius: 16px; }
  .plaza-circle-entry__icon :deep(svg) { width: 24px; height: 24px; }
  .plaza-circle-entry__name { font-size: 11px; }

  .plaza-filter__tab { padding: 5px 12px; font-size: 13px; }

  .post-card { padding: 12px 12px 8px; border-radius: 16px; }
  .post-card__avatar { width: 40px; height: 40px; }
  .post-card__text { font-size: 14.5px; }
  .post-card__stat { gap: 5px; font-size: 12.5px; padding: 4px 8px; }

  .plaza-fab {
    right: 14px;
    bottom: calc(68px + env(safe-area-inset-bottom));
    width: 48px;
    height: 48px;
  }
  .plaza-fab :deep(svg) { width: 22px; height: 22px; }
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
