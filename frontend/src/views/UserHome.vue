<script setup lang="ts">
import { computed, onMounted, onActivated, ref, watch } from 'vue'
// keep-alive 需要 name，与 App.vue 的 cachedViewNames 对应
defineOptions({ name: 'UserHomeView' })
import { useFadeUpdate } from '../composables/useFadeUpdate'
import { useRoute, useRouter } from 'vue-router'

import EmptyState from '../components/common/EmptyState.vue'
import AiStatusBadge from '../components/common/AiStatusBadge.vue'
import BadgeIcon from '../components/common/BadgeIcon.vue'
import PostListSkeleton from '../components/post/PostListSkeleton.vue'
import ProfileSkeleton from '../components/common/ProfileSkeleton.vue'
import MarkdownText from '../components/common/MarkdownText.vue'
import InfiniteScrollFooter from '../components/common/InfiniteScrollFooter.vue'
import { Dialog as NativeDialog, Icon, Select as NativeSelect } from '../components/native'
import { toast } from '../components/native/Toast'
import { useInfiniteScroll } from '../composables/useInfiniteScroll'
import {
  fetchMyFavoritePosts,
  fetchMyLikedPosts,
  fetchMyWarningStatus,
  fetchUser,
  fetchUserPosts,
  type WarningStatus,
} from '../api/user'
import { updateMe } from '../api/user'
import { uploadImage } from '../api/image'
import {
  applyInviteCode,
  getMyInviteCode,
  type MyInviteCodeInfo,
} from '../api/auth'
import { useSessionStore } from '../stores/session'
import { useUserStore } from '../stores/user'
import { useFollowStore } from '../stores/follow'
import { useSchoolStore } from '../stores/school'
import type { Post, Profile } from '../types/api'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const userStore = useUserStore()
const followStore = useFollowStore()
const schoolStore = useSchoolStore()

// 关键修复：/user/:id 和 /post/:id 共用 :id 参数名。
// keep-alive 缓存 UserHome 后导航到 PostDetail，route.params.id 变成帖子 ID，
// watch 会触发 fetchUser(帖子ID) → "用户不存在"。
// 解决：只在当前路由是 user-home 时才解析 userId，否则返回 NaN。
const userId = computed(() => {
  if (route.name !== 'user-home') return NaN
  return Number(route.params.id)
})
const profile = ref<Profile | null>(null)
const posts = ref<Post[]>([])
const activeTab = ref<'posts' | 'favorites' | 'likes'>('posts')
const loading = ref(false)
// 分页状态
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const hasMore = computed(() => posts.value.length < total.value)
// 全页骨架屏：首次 onMounted 期间为 true，profile 就绪后永远 false
const pageLoading = ref(true)

// SWR 刷新渐变：数据变化时递增 key 触发 CSS 淡入动画
const { fadeActive, triggerFade } = useFadeUpdate()
const following = ref(false)
const followLoading = ref(false)
const warningStatus = ref<WarningStatus | null>(null)

// 好友关系状态已移除：互关即可发消息，不再需要加好友流程
// 仅保留互关状态用于判断是否显示「私信」按钮可点击
const isMutual = ref(false)
const isMe = computed(() => session.userId === userId.value)
const displayName = computed(() =>
  profile.value?.nickname || (isMe.value ? session.nickname : '') || `用户 ${userId.value || ''}`.trim(),
)
const displayInitial = computed(() => (displayName.value || 'U').charAt(0).toUpperCase())

const tabs = computed(() => [
  { key: 'posts' as const, label: '作品', count: profile.value?.post_count ?? 0 },
  { key: 'favorites' as const, label: '收藏', count: 0 },
  { key: 'likes' as const, label: '点赞', count: 0 },
])

const funcGrid = computed(() => {
  const items = [
  { icon: 'file-text', color: '#007aff', label: '我的作品', to: 'posts' },
  { icon: 'bookmark', color: '#ff3b30', label: '我的收藏', to: '/my/favorites' },
  { icon: 'heart', color: '#ff9500', label: '我的点赞', to: 'likes' },
  { icon: 'edit', color: '#af52de', label: '草稿箱', to: '/my/drafts' },
  { icon: 'history', color: '#5856d6', label: '浏览历史', to: '/my/history' },
  { icon: 'sparkles', color: '#34c759', label: '我创建的吧', to: '/my/circles-applied' },
  { icon: 'gift', color: '#00c7be', label: '每日签到', to: '/my/checkin' },
  { icon: 'medal', color: '#f7b500', label: '我的徽章', to: '/my/badges' },
  { icon: 'creditcard', color: '#ff6b35', label: '校园卡', to: '' },
  ]
  // 邀请码：未认证显示「填写邀请码」，已认证显示「分享邀请码」
  const inviteItem = session.isVerified()
    ? { icon: 'link' as const, color: '#007aff', label: '分享邀请码', to: 'invite' }
    : { icon: 'shield' as const, color: '#ff9500', label: '填写邀请码', to: 'invite' }
  items.push(inviteItem)
  return items
})

// ============ 邀请码：填写 / 分享 ============
const inviteDialogVisible = ref(false)
const inviteCodeInput = ref('')
const inviteSubmitting = ref(false)
const inviteInfo = ref<MyInviteCodeInfo | null>(null)
const inviteInfoLoading = ref(false)

async function loadInviteInfo() {
  if (!session.isVerified()) {
    inviteInfo.value = null
    return
  }
  inviteInfoLoading.value = true
  try {
    const { data } = await getMyInviteCode({
      showGlobalLoading: false,
      showGlobalError: false,
    })
    inviteInfo.value = data.data
  } catch {
    inviteInfo.value = null
  } finally {
    inviteInfoLoading.value = false
  }
}

function onInviteEntryClick() {
  if (!isMe.value) return
  if (session.isVerified()) {
    router.push('/settings')
    return
  }
  inviteCodeInput.value = ''
  inviteDialogVisible.value = true
}

async function submitInviteCode() {
  const code = inviteCodeInput.value.trim()
  if (!code) {
    toast.error('请输入邀请码')
    return
  }
  inviteSubmitting.value = true
  try {
    const { data } = await applyInviteCode({ code })
    if (data.data.verification_status === 'verified') {
      session.setVerificationStatus('verified')
      inviteDialogVisible.value = false
      toast.success('邀请码验证成功，已解锁全部功能')
      await loadInviteInfo()
    }
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    inviteSubmitting.value = false
  }
}

async function copyMyInviteCode() {
  if (!inviteInfo.value?.code) return
  try {
    await navigator.clipboard.writeText(inviteInfo.value.code)
    toast.success('邀请码已复制')
  } catch {
    toast.info(`邀请码：${inviteInfo.value.code}`)
  }
}

function formatCooldown(sec: number): string {
  if (sec <= 0) return ''
  const d = Math.floor(sec / 86400)
  const h = Math.floor((sec % 86400) / 3600)
  const m = Math.floor((sec % 3600) / 60)
  if (d > 0) return `${d}天${h}小时`
  if (h > 0) return `${h}小时${m}分钟`
  return `${Math.max(1, m)}分钟`
}

// ============ 我的页直接编辑（点头像/名字/校区） ============
const avatarUploading = ref(false)
const avatarInputRef = ref<HTMLInputElement | null>(null)
const bgUploading = ref(false)
const bgInputRef = ref<HTMLInputElement | null>(null)

const nameDialogVisible = ref(false)
const nameSaving = ref(false)
const editName = ref('')

const schoolDialogVisible = ref(false)
const schoolSaving = ref(false)
const selectedSchoolId = ref<number>(0)

function onAvatarClick() {
  if (!isMe.value) return
  avatarInputRef.value?.click()
}

function onHeroBgClick(e: MouseEvent) {
  if (!isMe.value || bgUploading.value) return
  const target = e.target as HTMLElement
  if (target.closest('button')) return
  bgInputRef.value?.click()
}

function openBgPicker() {
  if (!isMe.value || bgUploading.value) return
  bgInputRef.value?.click()
}

async function onBgFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  bgUploading.value = true
  try {
    const { data } = await uploadImage(file)
    await updateMe({ background_url: data.data.url })
    await userStore.loadProfile()
    profile.value = userStore.profile
    toast.success('背景图已更新')
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    bgUploading.value = false
  }
}

async function onAvatarFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  avatarUploading.value = true
  try {
    const { data } = await uploadImage(file, undefined, 'avatar')
    await updateMe({ avatar_url: data.data.url })
    await userStore.loadProfile()
    profile.value = userStore.profile
    toast.success('头像已更新')
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    avatarUploading.value = false
  }
}

function onNameClick() {
  if (!isMe.value) return
  editName.value = displayName.value
  nameDialogVisible.value = true
}

async function saveName() {
  const name = editName.value.trim()
  if (!name) {
    toast.error('昵称不能为空')
    return
  }
  nameSaving.value = true
  try {
    await updateMe({ nickname: name.slice(0, 32) })
    await userStore.loadProfile()
    profile.value = userStore.profile
    session.setNickname(name.slice(0, 32))
    nameDialogVisible.value = false
    toast.success('昵称已更新')
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    nameSaving.value = false
  }
}

function onSchoolClick() {
  if (!isMe.value) return
  if (!schoolStore.loaded) void schoolStore.loadSchools()
  selectedSchoolId.value = profile.value?.school_id || 0
  schoolDialogVisible.value = true
}

const schoolOptions = computed(() =>
  schoolStore.schools.map((s) => ({ label: s.name, value: s.id })),
)

async function saveSchool() {
  if (!selectedSchoolId.value) {
    toast.error('请选择校区')
    return
  }
  schoolSaving.value = true
  try {
    await updateMe({ school_id: selectedSchoolId.value })
    await userStore.loadProfile()
    profile.value = userStore.profile
    schoolDialogVisible.value = false
    toast.success('校区已更新')
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    schoolSaving.value = false
  }
}

function goMyBadges() {
  router.push('/my/badges')
}

const settingsList = [
  { icon: 'bell', label: '消息通知中心设置', desc: '管理各类通知提醒', to: '/settings' },
  { icon: 'lock', label: '隐私设置', desc: '谁可以看你的内容', to: '/settings' },
  { icon: 'help-circle', label: '帮助与反馈', desc: '常见问题与意见反馈', to: '' },
  { icon: 'info', label: '关于立洋社区', desc: '版本 v1.2.0', to: '' },
]

function avatarGradient(id: number | undefined): string {
  const idx = (id || 0) % 5
  const grads = [
    'linear-gradient(135deg, #66abff, #007aff)',
    'linear-gradient(135deg, #34c759, #2e8dff)',
    'linear-gradient(135deg, #ff9500, #007aff)',
    'linear-gradient(135deg, #5856d6, #0064d6)',
    'linear-gradient(135deg, #d1d1d6, #8e8e93)',
  ]
  return grads[idx]
}

// ============ 警告值进度计算 ============
const warningPercent = computed(() => {
  if (!warningStatus.value) return 0
  const { score, perm_ban_threshold } = warningStatus.value
  return Math.min(100, Math.round((score / perm_ban_threshold) * 100))
})

const warningLevelMeta = computed(() => {
  if (!warningStatus.value) return null
  const level = warningStatus.value.level
  const map = {
    normal: { text: '状态良好', color: '#34c759', bg: '#e8f9ee', icon: 'check-circle' },
    warn: { text: '已警告', color: '#ff9500', bg: '#fff4e0', icon: 'triangle-alert' },
    ban: { text: '已封号', color: '#ff3b30', bg: '#ffe5e3', icon: 'circle-alert' },
    danger: { text: '危险', color: '#ff3b30', bg: '#ffe5e3', icon: 'circle-alert' },
  } as const
  return map[level] || map.normal
})

async function loadWarningStatus() {
  if (!isMe.value) {
    warningStatus.value = null
    return
  }
  try {
    const { data } = await fetchMyWarningStatus({
      showGlobalLoading: false,
      showGlobalError: false,
    })
    warningStatus.value = data.data
  } catch {
    // 警告值加载失败不阻塞主流程
    warningStatus.value = null
  }
}

function goWarningLogs() {
  router.push('/my/warning-logs')
}

async function loadProfile() {
  if (!userId.value || isNaN(userId.value)) return
  try {
    if (isMe.value && userStore.profile) {
      profile.value = userStore.profile
    } else {
      const { data } = await fetchUser(userId.value)
      profile.value = data.data
      // 直接使用后端返回的关注关系字段，避免 followStore 缓存导致的状态不一致
      // （匹配互关后缓存未刷新，主页仍显示"未关注"的 bug 根因）
      following.value = !!(data.data as Profile & { is_following?: boolean }).is_following
      isMutual.value = !!(data.data as Profile & { is_mutual?: boolean }).is_mutual
      // 同步刷新 followStore 缓存，保证其他页面（如关注列表）状态一致
      followStore.setFollowing(userId.value, following.value)
    }
  } catch (err) {
    // 封号错误静默：HTTP 拦截器已会跳转 /banned，无需再弹 toast
    const msg = (err as Error).message || ''
    if (msg.includes('封禁') || msg.includes('BANNED')) return
    toast.error(msg)
  }
}

/** 打开私信聊天页 */
function onChat() {
  if (!session.userId) {
    toast.info('请先登录')
    return
  }
  router.push(`/chat/${userId.value}`)
}

async function loadPosts() {
  if (!userId.value || isNaN(userId.value)) return
  loading.value = true
  page.value = 1 // 重置到第1页
  try {
    let payload: { items: Post[]; total: number } | Post[]
    if (activeTab.value === 'posts') {
      const { data } = await fetchUserPosts(userId.value, 1, pageSize.value)
      payload = data.data as any
    } else if (activeTab.value === 'favorites') {
      if (isMe.value) {
        const { data } = await fetchMyFavoritePosts(1, pageSize.value)
        payload = data.data as any
      } else {
        payload = []
      }
    } else {
      if (isMe.value) {
        const { data } = await fetchMyLikedPosts(1, pageSize.value)
        payload = data.data as any
      } else {
        payload = []
      }
    }
    // 兼容分页结构和旧版数组结构
    if (Array.isArray(payload)) {
      posts.value = payload
      total.value = payload.length
    } else {
      posts.value = payload.items || []
      total.value = payload.total || 0
    }
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

/** 加载更多（append 模式）：由 useInfiniteScroll 在触底时调用 */
async function loadMore() {
  if (!hasMore.value || loading.value) return
  if (!userId.value || isNaN(userId.value)) return
  const nextPage = page.value + 1
  try {
    let payload: { items: Post[]; total: number } | Post[]
    if (activeTab.value === 'posts') {
      const { data } = await fetchUserPosts(userId.value, nextPage, pageSize.value, { showGlobalLoading: false, showGlobalError: false })
      payload = data.data as any
    } else if (activeTab.value === 'favorites') {
      if (isMe.value) {
        const { data } = await fetchMyFavoritePosts(nextPage, pageSize.value, { showGlobalLoading: false, showGlobalError: false })
        payload = data.data as any
      } else {
        return
      }
    } else {
      if (isMe.value) {
        const { data } = await fetchMyLikedPosts(nextPage, pageSize.value, { showGlobalLoading: false, showGlobalError: false })
        payload = data.data as any
      } else {
        return
      }
    }
    if (Array.isArray(payload)) {
      posts.value = [...posts.value, ...payload]
      total.value = posts.value.length
    } else {
      const existingIds = new Set(posts.value.map(p => p.id))
      const newItems = (payload.items || []).filter(p => !existingIds.has(p.id))
      posts.value = [...posts.value, ...newItems]
      total.value = payload.total || total.value
      page.value = nextPage
    }
  } catch {
    throw new Error('加载更多失败')
  }
}

// 无限滚动：触底预加载下一页
const { loading: scrollLoading, error: scrollError, retry: scrollRetry } = useInfiniteScroll({
  hasMore,
  onLoadMore: loadMore,
})

async function onToggleFollow() {
  if (!session.userId) {
    toast.info('请先登录')
    return
  }
  followLoading.value = true
  try {
    following.value = await followStore.toggleFollow(userId.value)
    toast.success(following.value ? '已关注' : '已取关')
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    followLoading.value = false
  }
}

function onTabChange(tab: 'posts' | 'favorites' | 'likes') {
  activeTab.value = tab
  loadPosts()
}

function onFuncClick(item: (typeof funcGrid.value)[number]) {
  if (item.to === 'invite') {
    onInviteEntryClick()
    return
  }
  if (!item.to) {
    toast.info('功能开发中')
    return
  }
  if (item.to === 'posts') {
    router.push(`/user/${userId.value}/posts`)
    return
  }
  if (item.to === 'likes') {
    activeTab.value = 'likes'
    loadPosts()
    return
  }
  router.push(item.to)
}

function openPost(post: Post) {
  if (post.is_viewable === false) {
    toast.info(post.content || '审核中，暂无法查看原文')
    return
  }
  router.push(`/post/${post.id}`)
}

function editProfile() {
  router.push('/settings')
}

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/')
}

// 跳转到统计详情页
function goStatPage(type: 'posts' | 'followers' | 'following' | 'likers') {
  router.push(`/user/${userId.value}/${type}`)
}

// keep-alive 关键修复：离开 /user/:id 路由时 route.params.id 变 undefined，
// Number(undefined) = NaN，watch 会触发 fetchUser(NaN) → /users/NaN → 参数错误。
// 用 isNaN 守卫，NaN 时跳过所有请求。
watch(userId, (newId) => {
  if (!newId || isNaN(newId)) return
  loadProfile()
  loadPosts()
  loadWarningStatus()
})

/**
 * keep-alive 重新激活时：静默刷新数据（SWR 风格）。
 * 首次由 onMounted 处理，跳过。
 * 切回时先保留旧数据不变，后台静默刷新，数据变化时触发渐变动画。
 */
let skipFirstActivated = true
onActivated(async () => {
  if (skipFirstActivated) {
    skipFirstActivated = false
    return
  }
  if (!userId.value || isNaN(userId.value)) return
  // 静默刷新：不触发 loading/骨架屏，保留旧数据可见
  const oldPostsFp = posts.value.map(p => `${p.id}:${p.like_count}:${p.comment_count}`).join('|')
  await Promise.all([loadProfile(), loadPostsSilent(), loadWarningStatus()])
  loadInviteInfo()
  const newPostsFp = posts.value.map(p => `${p.id}:${p.like_count}:${p.comment_count}`).join('|')
  if (oldPostsFp !== newPostsFp) triggerFade()
})

/** 静默加载帖子：不显示 loading/骨架屏，用于 keep-alive 激活时后台刷新 */
async function loadPostsSilent() {
  if (!userId.value || isNaN(userId.value)) return
  // 已加载多页时跳过静默刷新，避免覆盖后续页数据造成错乱
  if (posts.value.length > pageSize.value) return
  try {
    let payload: { items: Post[]; total: number } | Post[]
    if (activeTab.value === 'posts') {
      const { data } = await fetchUserPosts(userId.value, 1, pageSize.value, { showGlobalLoading: false, showGlobalError: false })
      payload = data.data as any
    } else if (activeTab.value === 'favorites') {
      if (isMe.value) {
        const { data } = await fetchMyFavoritePosts(1, pageSize.value, { showGlobalLoading: false, showGlobalError: false })
        payload = data.data as any
      } else {
        return
      }
    } else if (activeTab.value === 'likes') {
      if (isMe.value) {
        const { data } = await fetchMyLikedPosts(1, pageSize.value, { showGlobalLoading: false, showGlobalError: false })
        payload = data.data as any
      } else {
        return
      }
    } else {
      return
    }
    // 兼容分页结构和旧版数组结构
    if (Array.isArray(payload)) {
      posts.value = payload
      total.value = payload.length
    } else {
      posts.value = payload.items || []
      total.value = payload.total || 0
      page.value = 1
    }
  } catch {
    /* 静默刷新失败不影响用户 */
  }
}

onMounted(async () => {
  // 性能优化：validateSession 与业务请求并行，不阻塞。
  // 路由守卫已确保 session.userId 存在；封号/token 过期由 http 拦截器统一处理。
  // 最小骨架显示 200ms，避免本地加载太快骨架屏一闪而过
  void session.validateSession()
  const minDelay = new Promise(resolve => setTimeout(resolve, 200))
  await Promise.all([loadProfile(), loadPosts(), loadWarningStatus(), minDelay])
  loadInviteInfo()
  pageLoading.value = false
})
</script>

<template>
  <!-- 首次加载骨架屏：profile 未就绪时展示全页骨架，避免空白闪烁 -->
  <ProfileSkeleton v-if="pageLoading" />
  <main v-else class="page-me">
    <!-- Hero 区 -->
    <section
      class="profile-hero"
      :class="{ 'has-bg': !!profile?.background_url }"
      :style="profile?.background_url ? { backgroundImage: `url(${profile.background_url})` } : undefined"
      @click="onHeroBgClick"
    >
      <div class="hero-topbar">
        <button class="icon-btn" type="button" aria-label="返回" @click="goBack">
          <Icon name="arrow-left" :size="20" />
        </button>
        <span class="hero-title">{{ isMe ? '立洋社区·我的' : '个人主页' }}</span>
        <button v-if="isMe" class="icon-btn" type="button" aria-label="设置" @click="router.push('/settings')">
          <Icon name="settings" :size="20" />
        </button>
        <span v-else class="icon-btn-placeholder" />
      </div>

      <div class="hero-body">
        <button
          class="hero-avatar"
          :class="{ 'is-editable': isMe }"
          type="button"
          :disabled="avatarUploading"
          @click="onAvatarClick"
          :style="
            profile?.avatar_url
              ? { backgroundImage: `url(${profile.avatar_url})` }
              : { background: avatarGradient(profile?.id || userId) }
          "
          aria-label="修改头像"
        >
          <span v-if="!profile?.avatar_url">{{ displayInitial }}</span>
          <span v-if="isMe" class="avatar-camera">
            <Icon name="camera" :size="14" />
          </span>
        </button>
        <h2 class="hero-name" :class="{ 'is-editable': isMe }" @click="onNameClick">
          <span>{{ displayName }}</span>
          <span v-if="isMe" class="name-edit-hint">
            <Icon name="edit" :size="12" />
          </span>
        </h2>
        <div class="hero-meta">
          <span v-if="profile?.age !== null && profile?.age !== undefined" class="grade-pill">{{ profile.age }} 岁</span>
          <span v-if="profile?.school" class="hero-school" :class="{ 'is-editable': isMe }" @click="onSchoolClick">
            {{ profile.school }}
            <span v-if="isMe" class="school-edit-hint">
              <Icon name="chevron-right" :size="11" />
            </span>
          </span>
        </div>
        <!-- 佩戴徽章展示：让用户知道可以佩戴徽章 -->
        <button v-if="isMe" class="wearing-badge-row" type="button" @click="goMyBadges">
          <BadgeIcon :badge="profile?.wearing_badge" :size="16" />
          <span v-if="profile?.wearing_badge">佩戴中：{{ profile.wearing_badge.name }}</span>
          <span v-else>还没有佩戴徽章</span>
          <span class="wearing-badge-action">去管理<Icon name="chevron-right" :size="11" /></span>
        </button>
        <p v-if="profile?.bio" class="hero-bio">{{ profile.bio }}</p>

        <!-- 统计（可点击） -->
        <div class="profile-stats">
          <button class="stat-item" type="button" @click="goStatPage('posts')">
            <span class="stat-num">{{ profile?.post_count ?? 0 }}</span>
            <span class="stat-label">作品</span>
          </button>
          <div class="stat-divider" />
          <button class="stat-item" type="button" @click="goStatPage('followers')">
            <span class="stat-num">{{ profile?.followers_count ?? 0 }}</span>
            <span class="stat-label">粉丝</span>
          </button>
          <div class="stat-divider" />
          <button class="stat-item" type="button" @click="goStatPage('following')">
            <span class="stat-num">{{ profile?.following_count ?? 0 }}</span>
            <span class="stat-label">关注</span>
          </button>
          <div class="stat-divider" />
          <button class="stat-item" type="button" @click="goStatPage('likers')">
            <span class="stat-num">{{ profile?.like_count ?? 0 }}</span>
            <span class="stat-label">获赞</span>
          </button>
        </div>

        <!-- 操作按钮 -->
        <div class="hero-actions">
          <button v-if="isMe" class="btn-pill btn-pill--primary" type="button" @click="editProfile">
            <Icon name="edit" :size="14" />
            编辑资料
          </button>
          <template v-else>
            <button
              class="btn-pill"
              :class="following ? 'btn-pill--outline' : 'btn-pill--primary'"
              type="button"
              :disabled="followLoading"
              @click="onToggleFollow"
            >
              <Icon :name="following ? 'check' : 'user-plus'" :size="14" />
              {{ following ? '已关注' : '关注' }}
            </button>
            <button
              class="btn-pill btn-pill--outline"
              type="button"
              @click="onChat"
            >
              <Icon name="message-circle" :size="14" />
              私信
            </button>
          </template>
          <button v-if="isMe" class="btn-pill btn-pill--outline" type="button">
            <Icon name="share" :size="14" />
            分享主页
          </button>
        </div>
      </div>
      <button
        v-if="isMe"
        class="hero-bg-edit"
        type="button"
        :disabled="bgUploading"
        @click.stop="openBgPicker"
      >
        <Icon name="camera" :size="13" />
        {{ bgUploading ? '上传中…' : profile?.background_url ? '更换背景图' : '设置背景图' }}
      </button>
    </section>

    <!-- 邀请码卡片（填写 / 分享，仅自己可见） -->
    <section v-if="isMe" class="invite-section">
      <div v-if="!session.isVerified()" class="invite-card invite-card--fill">
        <div class="invite-card-icon">
          <Icon name="shield" :size="20" />
        </div>
        <div class="invite-card-body">
          <span class="invite-card-title">填写邀请码解锁全部功能</span>
          <span class="invite-card-desc">发帖 / 评论 / 随机匹配 / 漂流瓶 需要邀请码</span>
        </div>
        <button class="invite-card-btn" type="button" @click="onInviteEntryClick">立即填写</button>
      </div>
      <div v-else-if="inviteInfo" class="invite-card invite-card--share">
        <div class="invite-card-icon">
          <Icon name="link" :size="20" />
        </div>
        <div class="invite-card-body">
          <span class="invite-card-title">
            我的邀请码 <b class="invite-code">{{ inviteInfo.code }}</b>
          </span>
          <span class="invite-card-desc">
            <template v-if="inviteInfo.is_frozen">
              邀请资格已冻结（{{ formatCooldown(inviteInfo.frozen_remaining) }} 后解冻）
            </template>
            <template v-else-if="inviteInfo.can_share">
              分享给同学，对方填写后解锁全部功能
            </template>
            <template v-else>
              分享冷却中（{{ formatCooldown(inviteInfo.cooldown_remaining) }} 后可再分享）
            </template>
          </span>
        </div>
        <button
          class="invite-card-btn"
          type="button"
          :disabled="inviteInfo.is_frozen"
          @click="copyMyInviteCode"
        >
          复制
        </button>
      </div>
    </section>

    <!-- 功能宫格（仅自己可见） -->
    <section v-if="isMe" class="func-section">
      <div class="func-grid">
        <button
          v-for="item in funcGrid"
          :key="item.label"
          class="func-entry"
          type="button"
          @click="onFuncClick(item)"
        >
          <span class="func-ic" :style="{ background: item.color }">
            <Icon :name="item.icon" :size="20" color="#fff" />
          </span>
          <span class="func-label">{{ item.label }}</span>
        </button>
      </div>
    </section>

    <!-- 修改昵称 / 校区弹窗 -->
    <NativeDialog v-model="nameDialogVisible" title="修改昵称" width="420px">
      <input
        v-model="editName"
        class="edit-input"
        type="text"
        maxlength="32"
        placeholder="请输入新昵称（最多 32 字）"
        @keydown.enter="saveName"
      />
      <template #footer>
        <button class="btn btn-outline" type="button" @click="nameDialogVisible = false">取消</button>
        <button class="btn btn-primary" type="button" :disabled="nameSaving" @click="saveName">
          {{ nameSaving ? '保存中…' : '保存' }}
        </button>
      </template>
    </NativeDialog>

    <NativeDialog v-model="schoolDialogVisible" title="切换校区" width="420px">
      <NativeSelect
        v-model="selectedSchoolId"
        :options="schoolOptions"
        placeholder="请选择校区"
      />
      <p class="edit-hint">切换校区后，首页「本校区」内容将按新校区展示</p>
      <template #footer>
        <button class="btn btn-outline" type="button" @click="schoolDialogVisible = false">取消</button>
        <button class="btn btn-primary" type="button" :disabled="schoolSaving" @click="saveSchool">
          {{ schoolSaving ? '保存中…' : '保存' }}
        </button>
      </template>
    </NativeDialog>

    <!-- 填写邀请码弹窗 -->
    <NativeDialog v-model="inviteDialogVisible" title="填写邀请码" width="420px">
      <p class="edit-hint">
        输入同学分享给你的邀请码，验证后即可解锁发帖 / 评论 / 随机匹配 / 漂流瓶等功能。
      </p>
      <input
        v-model="inviteCodeInput"
        class="edit-input"
        type="text"
        maxlength="16"
        placeholder="请输入邀请码"
        @keydown.enter="submitInviteCode"
      />
      <template #footer>
        <button class="btn btn-outline" type="button" @click="inviteDialogVisible = false">取消</button>
        <button class="btn btn-primary" type="button" :disabled="inviteSubmitting" @click="submitInviteCode">
          {{ inviteSubmitting ? '验证中…' : '解锁功能' }}
        </button>
      </template>
    </NativeDialog>

    <!-- 隐藏的头像文件选择（点击头像直接触发） -->
    <input
      ref="avatarInputRef"
      class="hidden-file-input"
      type="file"
      accept="image/*"
      @change="onAvatarFileChange"
    />

    <!-- 隐藏的背景图文件选择（点击个人主页顶部背景直接触发） -->
    <input
      ref="bgInputRef"
      class="hidden-file-input"
      type="file"
      accept="image/*"
      @change="onBgFileChange"
    />

    <!-- 警告值状态卡片（仅自己可见） -->
    <section v-if="isMe && warningStatus" class="warning-section">
      <div class="warning-card" :style="{ background: warningLevelMeta?.bg }">
        <div class="warning-header">
          <div class="warning-title-wrap">
            <span class="warning-ic" :style="{ color: warningLevelMeta?.color }">
              <Icon :name="warningLevelMeta?.icon || 'check-circle'" :size="18" />
            </span>
            <span class="warning-title">我的警告值</span>
            <span class="warning-level-pill" :style="{ color: warningLevelMeta?.color, background: '#fff', border: `1px solid ${warningLevelMeta?.color}` }">
              {{ warningLevelMeta?.text }}
            </span>
          </div>
          <button class="warning-logs-btn" type="button" @click="goWarningLogs">
            <Icon name="clock" :size="14" />
            变动记录
          </button>
        </div>

        <div class="warning-score-row">
          <div class="warning-score-num" :style="{ color: warningLevelMeta?.color }">
            {{ warningStatus.score }}
          </div>
          <div class="warning-score-divider">/</div>
          <div class="warning-score-max">{{ warningStatus.perm_ban_threshold }}</div>
          <div class="warning-score-tip">永久封号阈值</div>
        </div>

        <div class="warning-progress">
          <div class="warning-progress-bar" :style="{ width: `${warningPercent}%`, background: warningLevelMeta?.color }" />
          <!-- 阈值刻度 -->
          <div class="warning-tick" :style="{ left: `${Math.min(100, (warningStatus.warn_threshold / warningStatus.perm_ban_threshold) * 100)}%` }">
            <span class="tick-label">警告 {{ warningStatus.warn_threshold }}</span>
          </div>
          <div class="warning-tick" :style="{ left: `${Math.min(100, (warningStatus.temp_ban_threshold / warningStatus.perm_ban_threshold) * 100)}%` }">
            <span class="tick-label">封号 {{ warningStatus.temp_ban_threshold }}</span>
          </div>
        </div>

        <div v-if="warningStatus.score < warningStatus.perm_ban_threshold" class="warning-hint">
          <Icon name="triangle-alert" :size="13" :color="warningLevelMeta?.color" />
          <span>
            达到 <b>{{ warningStatus.next_threshold }}</b> 将触发：<b>{{ warningStatus.next_action }}</b>
          </span>
        </div>
        <div v-else class="warning-hint">
          <Icon name="circle-alert" :size="13" color="#ff3b30" />
          <span>当前警告值已达永久封号阈值，账号已被永久封禁</span>
        </div>

        <div class="warning-reduce-tip">
          <Icon name="sparkles" :size="13" color="#34c759" />
          <span>{{ warningStatus.reduce_hint }}</span>
        </div>
      </div>
    </section>

    <!-- 帖子 Tab -->
    <section class="posts-section">
      <div class="posts-tabs">
        <button
          v-for="t in tabs"
          :key="t.key"
          class="posts-tab"
          :class="{ 'is-active': activeTab === t.key }"
          type="button"
          @click="onTabChange(t.key)"
        >
          {{ t.label }}
        </button>
      </div>

      <!-- 帖子列表骨架屏 -->
      <PostListSkeleton v-if="loading && !posts.length" :count="4" />

      <!-- :class swr-updated：SWR 刷新数据变化时渐变过渡（文字逐字淡变+图片滑动），不销毁 DOM 保持滚动 -->
      <div v-else-if="posts.length" :class="{ 'swr-updated': fadeActive }" class="posts-list">
        <article v-for="post in posts" :key="post.id" class="post-item" @click="openPost(post)">
          <h3 class="post-title">
            <span v-if="post.is_public === false" class="private-badge">
              <Icon name="lock" :size="12" />
              已私密
            </span>
            {{ post.title || post.content.slice(0, 50) }}
          </h3>
          <MarkdownText v-if="post.content && post.title" :content="post.content" class="post-excerpt" :clamp="3" />
          <img
            v-if="post.image_urls?.length"
            class="post-thumb"
            :src="post.image_urls[0]"
            :alt="post.title || ''"
          />
          <div class="post-meta">
            <span class="post-cat">#{{ post.category || '校园' }}</span>
            <AiStatusBadge
              :status="post.ai_status"
              :reject-reason="post.reject_reason"
            />
            <span class="dot">·</span>
            <span class="post-likes">
              <Icon name="heart" :size="12" />
              {{ post.like_count }}
            </span>
            <span class="dot">·</span>
            <span class="post-comments">
              <Icon name="message-square" :size="12" />
              {{ post.comment_count }}
            </span>
          </div>
        </article>

        <!-- 无限滚动底部状态：加载中 / 加载失败重试 / 已显示全部 -->
        <InfiniteScrollFooter
          :loading="scrollLoading"
          :error="scrollError"
          :has-more="hasMore"
          :has-items="posts.length > 0"
          @retry="scrollRetry"
        />
      </div>

      <EmptyState v-else :text="activeTab === 'posts' ? '还没有发布过作品' : '暂无内容'" />
    </section>

    <!-- 设置列表（仅自己可见） -->
    <section v-if="isMe" class="settings-section">
      <div class="settings-card">
        <button
          v-for="(item, idx) in settingsList"
          :key="item.label"
          class="settings-row"
          :class="{ 'no-border': idx === settingsList.length - 1 }"
          type="button"
          @click="item.to && router.push(item.to)"
        >
          <span class="settings-ic">
            <Icon :name="item.icon" :size="16" color="#fff" />
          </span>
          <div class="settings-body">
            <span class="settings-label">{{ item.label }}</span>
            <span class="settings-desc">{{ item.desc }}</span>
          </div>
          <Icon name="chevron-right" :size="16" color="#c7c7cc" />
        </button>
      </div>
    </section>
  </main>
</template>

<style scoped>
.page-me {
  min-height: 100vh;
  background: var(--bg-100);
  padding-bottom: calc(80px + env(safe-area-inset-bottom));
}

/* Hero */
.profile-hero {
  position: relative;
  background: linear-gradient(180deg, var(--brand-50) 0%, var(--bg-50) 100%);
  background-size: cover;
  background-position: center;
  overflow: hidden;
  padding-bottom: 20px;
}
.profile-hero::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 0;
  background: linear-gradient(180deg, rgba(15, 23, 42, 0.34) 0%, rgba(15, 23, 42, 0.58) 100%);
  opacity: 0;
  transition: opacity 0.3s ease;
  pointer-events: none;
}
.profile-hero.has-bg::before {
  opacity: 1;
}
.hero-topbar {
  position: relative;
  z-index: 1;
  max-width: 640px;
  margin: 0 auto;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.hero-body {
  position: relative;
  z-index: 1;
}
.hero-title {
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
}
.icon-btn:hover {
  background: rgba(0, 0, 0, 0.05);
}
.icon-btn-placeholder {
  width: 36px;
  height: 36px;
  display: inline-block;
}
.hero-body {
  max-width: 640px;
  margin: 0 auto;
  padding: 16px 24px 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}
.hero-avatar {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  border: 3px solid white;
  padding: 0;
  background-size: cover;
  background-position: center;
  display: grid;
  place-items: center;
  color: white;
  font-size: 32px;
  font-weight: 700;
  box-shadow: var(--shadow-md);
  position: relative;
}
.hero-avatar.is-editable {
  cursor: pointer;
  transition: transform 0.15s var(--ease-apple), box-shadow 0.15s;
}
.hero-avatar.is-editable:hover {
  transform: scale(1.03);
  box-shadow: var(--shadow-lg, 0 10px 24px -8px rgba(0, 0, 0, 0.25));
}
.hero-avatar.is-editable:active {
  transform: scale(0.98);
}
.avatar-camera {
  position: absolute;
  right: -3px;
  bottom: -3px;
  z-index: 5;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  display: grid;
  place-items: center;
  border: 2px solid #fff;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25);
}
.hero-name {
  margin: 12px 0 6px;
  font-size: 20px;
  font-weight: 700;
  color: var(--text-800);
  letter-spacing: -0.02em;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.hero-name.is-editable {
  cursor: pointer;
}
.name-edit-hint {
  display: inline-flex;
  align-items: center;
  color: var(--text-400);
  opacity: 0;
  transition: opacity 0.15s;
}
.hero-name.is-editable:hover .name-edit-hint {
  opacity: 1;
}
.hero-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.grade-pill {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  background: var(--brand-50);
  color: var(--brand-600);
  border-radius: 999px;
}
.hero-school {
  font-size: 12px;
  color: var(--text-500);
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.hero-school.is-editable {
  cursor: pointer;
  padding: 3px 8px;
  border-radius: 999px;
  transition: background 0.15s;
}
.hero-school.is-editable:hover {
  background: rgba(0, 0, 0, 0.06);
  color: var(--brand-600);
}
.school-edit-hint {
  display: inline-flex;
  align-items: center;
}
.hero-bg-edit {
  position: absolute;
  top: 68px;
  right: 16px;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 12px;
  border-radius: 999px;
  border: none;
  background: rgba(15, 23, 42, 0.35);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  transition: background 0.15s;
}
.hero-bg-edit:hover {
  background: rgba(15, 23, 42, 0.55);
}
.hero-bg-edit:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

/* 有背景图时：加深遮罩 + 白色文字，保证可读性 */
.profile-hero.has-bg .icon-btn {
  color: #fff;
}
.profile-hero.has-bg .icon-btn:hover {
  background: rgba(255, 255, 255, 0.16);
}
.profile-hero.has-bg .hero-title {
  color: #fff;
}
.profile-hero.has-bg .hero-name {
  color: #fff;
}
.profile-hero.has-bg .name-edit-hint {
  color: rgba(255, 255, 255, 0.75);
}
.profile-hero.has-bg .grade-pill {
  background: rgba(255, 255, 255, 0.92);
  color: var(--brand-600);
}
.profile-hero.has-bg .hero-school {
  color: rgba(255, 255, 255, 0.92);
}
.profile-hero.has-bg .hero-school.is-editable:hover {
  background: rgba(255, 255, 255, 0.16);
  color: #fff;
}
.profile-hero.has-bg .school-edit-hint {
  color: rgba(255, 255, 255, 0.75);
}
.profile-hero.has-bg .hero-bio {
  color: rgba(255, 255, 255, 0.92);
}
.profile-hero.has-bg .wearing-badge-row {
  border-color: rgba(255, 255, 255, 0.55);
  background: rgba(255, 255, 255, 0.14);
  color: #fff;
}
.profile-hero.has-bg .wearing-badge-row:hover {
  background: rgba(255, 255, 255, 0.22);
}
.profile-hero.has-bg .wearing-badge-action {
  color: #fff;
}
.profile-hero.has-bg .stat-num {
  color: #fff;
}
.profile-hero.has-bg .stat-label {
  color: rgba(255, 255, 255, 0.8);
}
.profile-hero.has-bg .stat-divider {
  background: rgba(255, 255, 255, 0.35);
}
.profile-hero.has-bg .btn-pill--outline {
  color: #fff;
  border-color: rgba(255, 255, 255, 0.55);
}
.profile-hero.has-bg .btn-pill--outline:hover {
  background: rgba(255, 255, 255, 0.16);
}
.wearing-badge-row {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 2px 0 6px;
  padding: 5px 12px;
  border-radius: 999px;
  border: 1px dashed var(--brand-300, #7cb8ff);
  background: rgba(0, 122, 255, 0.05);
  color: var(--text-600);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.wearing-badge-row:hover {
  background: rgba(0, 122, 255, 0.1);
  border-color: var(--brand-500);
}
.wearing-badge-action {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  color: var(--brand-500);
  font-weight: 600;
}
.edit-input {
  width: 100%;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid var(--color-border, #e5e5ea);
  font-size: 15px;
  font-family: inherit;
  color: var(--text-800);
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.edit-input:focus {
  border-color: var(--brand-500);
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.15);
}
.edit-hint {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--text-400);
  line-height: 1.5;
}
.hidden-file-input {
  display: none;
}
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 8px 18px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  border: none;
  cursor: pointer;
  transition: transform 0.15s, opacity 0.15s, background 0.15s;
}
.btn:active {
  transform: scale(0.98);
}
.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.btn-outline {
  background: transparent;
  color: var(--text-700);
  border: 1px solid var(--bg-300);
}
.btn-primary {
  background: var(--brand-500);
  color: #fff;
}

/* 邀请码卡片 */
.invite-section {
  max-width: 640px;
  margin: 14px auto 0;
  padding: 0 16px;
}
.invite-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
}
.invite-card--fill {
  background: linear-gradient(135deg, #fff4e0, #fff);
  border: 1px solid #ffd591;
}
.invite-card--share {
  background: linear-gradient(135deg, #eaf2ff, #fff);
  border: 1px solid #b3d8ff;
}
.invite-card-icon {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  color: #fff;
  flex-shrink: 0;
}
.invite-card--fill .invite-card-icon {
  background: linear-gradient(135deg, #ff9500, #ff6b00);
}
.invite-card--share .invite-card-icon {
  background: linear-gradient(135deg, #007aff, #0064d6);
}
.invite-card-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.invite-card-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-800);
}
.invite-code {
  font-family: 'Courier New', Menlo, monospace;
  letter-spacing: 1px;
  color: var(--brand-600);
  margin-left: 4px;
}
.invite-card-desc {
  font-size: 11px;
  color: var(--text-500);
  line-height: 1.5;
}
.invite-card-btn {
  padding: 7px 16px;
  border-radius: 999px;
  border: none;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  flex-shrink: 0;
  font-family: inherit;
  transition: transform 0.15s, opacity 0.15s;
}
.invite-card-btn:active {
  transform: scale(0.97);
}
.invite-card-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.invite-card--fill .invite-card-btn {
  background: linear-gradient(135deg, #ff9500, #ff6b00);
  color: #fff;
}
.invite-card--share .invite-card-btn {
  background: var(--brand-500);
  color: #fff;
}

.hero-bio {
  margin: 4px 0 16px;
  font-size: 13px;
  color: var(--text-600);
  max-width: 320px;
  line-height: 1.5;
}
.profile-stats {
  display: flex;
  align-items: center;
  gap: 0;
  padding: 14px 0;
  margin-bottom: 16px;
}
.stat-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 4px 0;
  transition: transform 0.15s;
}
.stat-item:hover {
  transform: scale(1.05);
}
.stat-item:active {
  transform: scale(0.98);
}
.stat-num {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-800);
  letter-spacing: -0.01em;
}
.stat-label {
  font-size: 11px;
  color: var(--text-500);
}
.stat-divider {
  width: 0.5px;
  height: 22px;
  background: var(--bg-300);
}
.hero-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: center;
}
.btn-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 8px 18px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  transition: transform 0.15s cubic-bezier(0.32, 0.72, 0, 1);
}
.btn-pill:active {
  transform: scale(0.98);
}
.btn-pill:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.btn-pill--primary {
  background: var(--brand-500);
  color: white;
}
.btn-pill--primary:hover {
  background: var(--brand-600);
}
.btn-pill--outline {
  background: transparent;
  color: var(--text-700);
  border: 1px solid var(--bg-300);
}
.btn-pill--outline:hover {
  background: var(--bg-100);
}

/* 功能宫格 */
.func-section {
  max-width: 640px;
  margin: 14px auto 0;
  padding: 0 16px;
}
.func-grid {
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  padding: 16px 8px;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px 4px;
}
.func-entry {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  background: transparent;
  border: none;
  cursor: pointer;
}
.func-ic {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: grid;
  place-items: center;
}
.func-label {
  font-size: 11px;
  color: var(--text-700);
  font-weight: 500;
}

/* 帖子区 */
.posts-section {
  max-width: 640px;
  margin: 16px auto 0;
  padding: 0 16px;
}

/* 警告值卡片 */
.warning-section {
  max-width: 640px;
  margin: 14px auto 0;
  padding: 0 16px;
}
.warning-card {
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  padding: 16px;
}
.warning-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.warning-title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}
.warning-ic {
  display: grid;
  place-items: center;
}
.warning-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-800);
}
.warning-level-pill {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
}
.warning-logs-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid var(--bg-200);
  color: var(--text-700);
  font-size: 12px;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: 999px;
  cursor: pointer;
  transition: background 0.15s;
}
.warning-logs-btn:hover {
  background: #fff;
}
.warning-score-row {
  display: flex;
  align-items: baseline;
  gap: 4px;
  margin-bottom: 12px;
}
.warning-score-num {
  font-size: 32px;
  font-weight: 800;
  line-height: 1;
  letter-spacing: -0.02em;
}
.warning-score-divider {
  font-size: 18px;
  color: var(--text-400);
  font-weight: 600;
}
.warning-score-max {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-600);
}
.warning-score-tip {
  font-size: 11px;
  color: var(--text-500);
  margin-left: 8px;
}
.warning-progress {
  position: relative;
  width: 100%;
  height: 8px;
  background: rgba(255, 255, 255, 0.6);
  border-radius: 999px;
  margin-bottom: 24px;
  overflow: visible;
}
.warning-progress-bar {
  height: 100%;
  border-radius: 999px;
  transition: width 0.3s ease;
}
.warning-tick {
  position: absolute;
  top: -4px;
  width: 2px;
  height: 16px;
  background: rgba(0, 0, 0, 0.2);
  transform: translateX(-1px);
}
.tick-label {
  position: absolute;
  top: 14px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 10px;
  color: var(--text-500);
  white-space: nowrap;
}
.warning-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-700);
  margin-bottom: 6px;
}
.warning-hint b {
  color: var(--text-800);
  font-weight: 700;
}
.warning-reduce-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-500);
}
.posts-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--bg-200);
}
.posts-tab {
  padding: 10px 16px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-500);
  background: transparent;
  border: none;
  cursor: pointer;
  position: relative;
  transition: color 0.15s;
}
.posts-tab:hover {
  color: var(--text-800);
}
.posts-tab.is-active {
  color: var(--brand-500);
}
.posts-tab.is-active::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 16px;
  right: 16px;
  height: 2px;
  background: var(--brand-500);
  border-radius: 1px;
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

.posts-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.post-item {
  background: var(--bg-50);
  border-radius: var(--radius-md);
  padding: 14px;
  box-shadow: var(--shadow-xs);
  cursor: pointer;
  transition: box-shadow 0.15s;
  position: relative;
}
.post-item:hover {
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
.post-title {
  margin: 0 0 6px;
  padding-right: 80px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-800);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.post-excerpt {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--text-500);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.post-thumb {
  position: absolute;
  top: 14px;
  right: 14px;
  width: 60px;
  height: 60px;
  border-radius: 8px;
  object-fit: cover;
}
.post-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-400);
}
.post-cat {
  color: var(--brand-500);
}
.post-likes,
.post-comments {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
.dot {
  color: var(--bg-300);
}

/* 设置列表 */
.settings-section {
  max-width: 640px;
  margin: 16px auto 0;
  padding: 0 16px;
}
.settings-card {
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  overflow: hidden;
}
.settings-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  background: transparent;
  border: none;
  border-bottom: 0.5px solid var(--bg-200);
  cursor: pointer;
  width: 100%;
  text-align: left;
  transition: background 0.15s;
}
.settings-row:hover {
  background: var(--bg-100);
}
.settings-row.no-border {
  border-bottom: none;
}
.settings-ic {
  width: 30px;
  height: 30px;
  border-radius: 7px;
  background: linear-gradient(135deg, #8e8e93, #6e6e73);
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.settings-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.settings-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-800);
}
.settings-desc {
  font-size: 12px;
  color: var(--text-400);
}

@media (max-width: 768px) {
  .hero-body {
    padding: 12px 16px 0;
  }
  .hero-avatar {
    width: 64px;
    height: 64px;
    font-size: 26px;
  }
  .hero-name {
    font-size: 18px;
  }
  .func-section,
  .invite-section,
  .posts-section,
  .settings-section {
    padding: 0 12px;
  }
  .func-grid {
    grid-template-columns: repeat(4, 1fr);
    gap: 12px 4px;
  }
}
</style>
