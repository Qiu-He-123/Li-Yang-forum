<script setup lang="ts">
/**
 * 圈子详情页（P1 新增）
 * 对齐设计稿：圈子详情 - 校园美食吧.html
 * - 顶部固定栏：返回 + 圈子名 + 关注/已关注
 * - 圈子信息卡：头像 + 名称 + 简介 + 关注 + 统计（吧主/成员/帖子）
 * - 分类 Tab：全部 / 精品 / 图片 / 视频（下划线指示器）
 * - 帖子列表：单列贴吧风格，作者行 + 标题 + 摘要 + 元数据 + 可选缩略图
 *
 * 阶段四新增：
 * - 吧主管理面板（is_admin=true 可见）
 * - 帖子列表项上的删除按钮（is_admin 可见）
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { Dialog, Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import EmptyState from '../components/common/EmptyState.vue'
import CircleDetailSkeleton from '../components/common/CircleDetailSkeleton.vue'
import InfiniteScrollFooter from '../components/common/InfiniteScrollFooter.vue'
import { useInfiniteScroll } from '../composables/useInfiniteScroll'
import { useCircleStore } from '../stores/circle'
import { useSessionStore } from '../stores/session'
import { listCirclePosts } from '../api/circle'
import {
  addCircleAdmin,
  deletePostAsCircleAdmin,
  listCircleAdmins,
  removeCircleAdmin,
} from '../api/circleApply'
import type { CircleAdmin, CircleDetail, Post } from '../types/api'

const route = useRoute()
const router = useRouter()
const circleStore = useCircleStore()
const session = useSessionStore()

const slug = computed(() => String(route.params.slug ?? ''))
const circle = ref<CircleDetail | null>(null)
const posts = ref<Post[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
// 全页骨架屏：首次 onMounted 期间为 true，circle 就绪后永远 false
const pageLoading = ref(true)
const loadingMore = ref(false)
const followLoading = ref(false)
const activeTab = ref<'all' | 'essence' | 'image' | 'video'>('all')

const tabs: { key: typeof activeTab.value; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'essence', label: '精品' },
  { key: 'image', label: '图片' },
  { key: 'video', label: '视频' },
]

const hasMore = computed(() => posts.value.length < total.value)

// ============ 阶段四：吧主管理面板 ============
const manageVisible = ref(false)
const admins = ref<CircleAdmin[]>([])
const adminsLoading = ref(false)
const newAdminId = ref('')
const adminOperating = ref(false)

// 当前用户是否是吧主/管理员
const isAdmin = computed(() => !!circle.value?.is_admin)

// 头像首字母（吧主/作者头像兜底）
function avatarGradient(id?: number) {
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

async function loadCircle() {
  if (!slug.value) return
  try {
    const data = await circleStore.loadCircle(slug.value)
    circle.value = data
    // 乐观更新足迹：loadCircle 成功（后端已记录浏览）后立即把圈子加到 store 足迹最前面，
    // 这样返回 CircleDiscover 时足迹已同步，避免"延迟一步"问题
    circleStore.recordView(data as any)
  } catch (err) {
    toast.error((err as Error).message)
  }
}

async function loadPosts(reset = false) {
  if (!slug.value) return
  if (reset) {
    page.value = 1
    loading.value = true
  } else {
    loadingMore.value = true
  }
  try {
    const { data } = await listCirclePosts(slug.value, {
      type: activeTab.value,
      page: page.value,
      page_size: pageSize,
    })
    const list = data.data?.items ?? []
    if (reset) posts.value = list
    else posts.value = [...posts.value, ...list]
    total.value = data.data?.total ?? list.length
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

async function loadMore() {
  if (!hasMore.value || loadingMore.value) return
  page.value += 1
  await loadPosts(false)
}

// 无限滚动：复用已有的 hasMore 计算属性与 loadMore 函数
const { loading: scrollLoading, error: scrollError, retry: scrollRetry } = useInfiniteScroll({
  hasMore,
  onLoadMore: loadMore,
})

function onTabChange(key: typeof activeTab.value) {
  if (activeTab.value === key) return
  activeTab.value = key
  loadPosts(true)
}

async function onToggleFollow() {
  if (!circle.value) return
  if (!session.userId) {
    toast.info('请先登录')
    return
  }
  followLoading.value = true
  try {
    const joined = await circleStore.toggleJoin(circle.value as any)
    circle.value.is_joined = joined
    toast.success(joined ? `已加入「${circle.value.name}」` : `已退出「${circle.value.name}」`)
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    followLoading.value = false
  }
}

function onBack() {
  if (window.history.length > 1) router.back()
  else router.push('/')
}

function openPost(p: Post) {
  router.push({ name: 'post-detail', params: { id: p.id } })
}

// ============ 阶段四：吧主管理面板逻辑 ============
async function openManagePanel() {
  manageVisible.value = true
  await loadAdmins()
}

async function loadAdmins() {
  if (!slug.value) return
  adminsLoading.value = true
  try {
    const { data } = await listCircleAdmins(slug.value)
    admins.value = data.data || []
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    adminsLoading.value = false
  }
}

async function onAddAdmin() {
  const idStr = newAdminId.value.trim()
  if (!idStr) {
    toast.error('请输入用户 ID')
    return
  }
  const userId = Number(idStr)
  if (!Number.isFinite(userId) || userId <= 0) {
    toast.error('用户 ID 必须为正整数')
    return
  }
  adminOperating.value = true
  try {
    await addCircleAdmin(slug.value, userId)
    toast.success('已任命管理员')
    newAdminId.value = ''
    await loadAdmins()
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    adminOperating.value = false
  }
}

async function onRemoveAdmin(admin: CircleAdmin) {
  if (admin.role === 'owner') {
    toast.info('吧主不可移除')
    return
  }
  if (!confirm(`确认移除管理员「${admin.nickname || '用户' + admin.user_id}」？`)) return
  adminOperating.value = true
  try {
    await removeCircleAdmin(slug.value, admin.user_id)
    toast.success('已移除管理员')
    await loadAdmins()
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    adminOperating.value = false
  }
}

// 吧主删帖
async function onDeletePost(post: Post, e: Event) {
  e.stopPropagation()
  if (!confirm(`确认删除帖子「${post.title || post.content.slice(0, 30)}」？此操作不可恢复。`)) return
  try {
    await deletePostAsCircleAdmin(slug.value, post.id)
    toast.success('已删除帖子')
    posts.value = posts.value.filter((p) => p.id !== post.id)
    if (circle.value && circle.value.post_count > 0) {
      circle.value.post_count -= 1
    }
  } catch (err) {
    toast.error((err as Error).message)
  }
}

onMounted(async () => {
  // 性能优化：loadCircle 与 loadPosts 相互独立（都只依赖 slug 路由参数），
  // 改为并行，避免"加载两次"的全屏 loading 闪烁
  // 最小骨架显示 200ms，避免本地加载太快骨架屏一闪而过
  const minDelay = new Promise(resolve => setTimeout(resolve, 200))
  await Promise.allSettled([loadCircle(), loadPosts(true), minDelay])
  pageLoading.value = false
})

watch(slug, () => {
  // 路由切换圈子时同样并行加载
  void Promise.allSettled([loadCircle(), loadPosts(true)])
})
</script>

<template>
  <!-- 首次加载骨架屏：circle 未就绪时展示全页骨架，避免空白闪烁 -->
  <CircleDetailSkeleton v-if="pageLoading" />
  <main v-else class="page-circle">
    <!-- 顶部固定栏：返回 + 圈子名 + 关注 + 吧主管理 -->
    <header class="site-header" role="banner">
      <div class="header-inner">
        <div class="header-side header-side--left">
          <button class="icon-btn" type="button" aria-label="返回" @click="onBack">
            <Icon name="arrow-left" :size="20" />
          </button>
        </div>
        <h1 class="header-title">{{ circle?.name || '圈子' }}</h1>
        <div class="header-side header-side--right">
          <button
            v-if="isAdmin"
            class="icon-btn"
            type="button"
            aria-label="吧主管理"
            @click="openManagePanel"
          >
            <Icon name="settings" :size="20" />
          </button>
          <button
            v-if="circle"
            class="follow-btn"
            :class="{ 'is-followed': circle.is_joined }"
            type="button"
            :disabled="followLoading"
            aria-label="关注圈子"
            @click="onToggleFollow"
          >
            <span class="state-followed">
              <Icon name="check" :size="14" />
              <span>已关注</span>
            </span>
            <span class="state-not">
              <Icon name="user-plus" :size="14" />
              <span>关注</span>
            </span>
          </button>
        </div>
      </div>
    </header>

    <!-- 主内容 -->
    <div class="page-container">
      <!-- 圈子信息卡 -->
      <section v-if="circle" class="bar-card" aria-label="圈子信息">
        <div class="bar-card-head">
          <span
            class="bar-avatar"
            :style="{ background: avatarGradient(circle.id) }"
            aria-hidden="true"
          >
            <span class="bar-avatar-letter">{{ (circle.name || 'C').charAt(0) }}</span>
          </span>
          <div class="bar-info">
            <h2 class="bar-name">{{ circle.name }}</h2>
            <p class="bar-desc">{{ circle.description || '暂无简介' }}</p>
          </div>
          <button
            class="follow-btn"
            :class="{ 'is-followed': circle.is_joined }"
            type="button"
            :disabled="followLoading"
            aria-label="关注圈子"
            @click="onToggleFollow"
          >
            <span class="state-followed">
              <Icon name="check" :size="14" />
              <span>已关注</span>
            </span>
            <span class="state-not">
              <Icon name="user-plus" :size="14" />
              <span>关注</span>
            </span>
          </button>
        </div>
        <div class="bar-stats">
          <div class="bar-stat">
            <span class="bar-stat-ic" aria-hidden="true">
              <Icon name="crown" :size="14" />
            </span>
            <span class="bar-stat-text">
              <span class="bar-stat-label">吧主</span>
              <span class="bar-stat-value">待认领</span>
            </span>
          </div>
          <div class="bar-stat">
            <span class="bar-stat-ic" aria-hidden="true">
              <Icon name="users" :size="14" />
            </span>
            <span class="bar-stat-text">
              <span class="bar-stat-label">成员</span>
              <span class="bar-stat-value">{{ formatCount(circle.member_count) }}</span>
            </span>
          </div>
          <div class="bar-stat">
            <span class="bar-stat-ic" aria-hidden="true">
              <Icon name="file-text" :size="14" />
            </span>
            <span class="bar-stat-text">
              <span class="bar-stat-label">帖子</span>
              <span class="bar-stat-value">{{ formatCount(circle.post_count) }}</span>
            </span>
          </div>
        </div>
      </section>

      <!-- 分类 Tab -->
      <div class="cat-tabs" role="tablist" aria-label="帖子分类">
        <button
          v-for="t in tabs"
          :key="t.key"
          class="cat-tab"
          :class="{ 'is-active': activeTab === t.key }"
          type="button"
          role="tab"
          :aria-selected="activeTab === t.key"
          @click="onTabChange(t.key)"
        >
          {{ t.label }}
        </button>
      </div>

      <!-- 帖子列表 -->
      <section class="post-list" aria-label="帖子列表">
        <div v-if="loading" class="loading-tip">
          <Icon name="refresh" :size="20" />
          <span>加载中…</span>
        </div>

        <template v-else-if="posts.length">
          <article
            v-for="post in posts"
            :key="post.id"
            class="post-item"
            :class="{ 'is-essence': (post.like_count ?? 0) >= 10 }"
            @click="openPost(post)"
          >
            <div class="post-main">
              <div class="post-author-row">
                <span
                  class="avatar avatar-xs"
                  :style="(post.author_avatar_url && !post.is_anonymous) ? {} : { background: avatarGradient(post.author_id) }"
                  aria-hidden="true"
                >
                  <img v-if="post.author_avatar_url && !post.is_anonymous" :src="post.author_avatar_url" :alt="post.author" />
                </span>
                <span class="post-author">{{ post.is_anonymous ? '匿名同学' : post.author }}</span>
                <span class="post-dot" aria-hidden="true">·</span>
                <span class="post-time">{{ timeAgo(post.created_at) }}</span>
                <span v-if="(post.like_count ?? 0) >= 10" class="post-badge">
                  <Icon name="award" :size="11" />
                  精品
                </span>
                <span v-if="post.is_public === false" class="private-badge">
                  <Icon name="lock" :size="11" />
                  已私密
                </span>
                <!-- 吧主删除按钮 -->
                <button
                  v-if="isAdmin"
                  class="post-delete-btn"
                  type="button"
                  aria-label="删除帖子"
                  @click="onDeletePost(post, $event)"
                >
                  <Icon name="trash" :size="13" />
                  删除
                </button>
              </div>
              <h3 class="post-title">{{ post.title || post.content.slice(0, 50) }}</h3>
              <p v-if="post.title" class="post-summary">{{ post.content }}</p>
              <div class="post-meta-row">
                <span class="post-bar-tag">{{ circle?.name || post.category || '校园' }}</span>
                <span class="post-meta-item">
                  <Icon name="eye" :size="13" />
                  <span>{{ formatCount(post.view_count ?? 0) }}</span>
                </span>
                <span class="post-meta-item">
                  <Icon name="message-circle" :size="13" />
                  <span>{{ formatCount(post.comment_count) }}</span>
                </span>
                <span v-if="post.last_reply_at" class="post-last-reply">
                  最后回复 {{ timeAgo(post.last_reply_at) }}
                </span>
              </div>
            </div>
            <img
              v-if="post.image_urls?.length"
              class="post-thumb"
              :src="post.image_urls[0]"
              :alt="post.title || ''"
              loading="lazy"
            />
          </article>

          <!-- 无限滚动底部状态 -->
          <InfiniteScrollFooter
            :loading="scrollLoading"
            :error="scrollError"
            :has-more="hasMore"
            :has-items="posts.length > 0"
            @retry="scrollRetry"
          />
        </template>

        <EmptyState v-else text="这个圈子还没人发帖，来做第一个吧" />
      </section>
    </div>

    <!-- ====== 吧主管理面板 ====== -->
    <Dialog v-model="manageVisible" title="吧主管理" width="480px">
      <div class="manage-panel">
        <!-- 添加管理员 -->
        <div class="manage-section">
          <h4 class="manage-section-title">添加管理员</h4>
          <div class="add-admin-row">
            <input
              v-model="newAdminId"
              class="add-admin-input"
              type="text"
              inputmode="numeric"
              placeholder="输入用户 ID"
              @keyup.enter="onAddAdmin"
            />
            <button
              class="add-admin-btn"
              type="button"
              :disabled="adminOperating"
              @click="onAddAdmin"
            >
              {{ adminOperating ? '处理中…' : '任命' }}
            </button>
          </div>
          <p class="manage-hint">仅可任命本社区注册用户为管理员</p>
        </div>

        <!-- 管理员列表 -->
        <div class="manage-section">
          <h4 class="manage-section-title">管理员列表</h4>
          <div v-if="adminsLoading" class="manage-loading">加载中…</div>
          <ul v-else-if="admins.length" class="admin-list">
            <li v-for="admin in admins" :key="admin.id" class="admin-item">
              <span
                class="admin-avatar"
                :style="
                  admin.avatar_url
                    ? { backgroundImage: `url(${admin.avatar_url})` }
                    : { background: avatarGradient(admin.user_id) }
                "
              >
                <span v-if="!admin.avatar_url">{{ (admin.nickname || 'U').charAt(0).toUpperCase() }}</span>
              </span>
              <div class="admin-info">
                <div class="admin-name">{{ admin.nickname || '用户' + admin.user_id }}</div>
                <div class="admin-meta">
                  <span class="admin-role" :class="`role-${admin.role}`">
                    {{ admin.role === 'owner' ? '吧主' : '管理员' }}
                  </span>
                  <span class="admin-time">加入于 {{ timeAgo(admin.created_at) }}</span>
                </div>
              </div>
              <button
                v-if="admin.role !== 'owner'"
                class="admin-remove-btn"
                type="button"
                :disabled="adminOperating"
                @click="onRemoveAdmin(admin)"
              >
                移除
              </button>
            </li>
          </ul>
          <div v-else class="manage-empty">暂无管理员</div>
        </div>
      </div>
    </Dialog>
  </main>
</template>

<style scoped>
.page-circle {
  min-height: 100vh;
  background: var(--bg-100);
  padding-top: 56px;
  padding-bottom: calc(76px + env(safe-area-inset-bottom));
}

/* 顶部固定栏 */
.site-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  height: 56px;
  background: color-mix(in srgb, var(--bg-50) 88%, transparent);
  -webkit-backdrop-filter: blur(20px);
  backdrop-filter: blur(20px);
  border-bottom: 0.5px solid var(--bg-300);
}
.header-inner {
  max-width: 720px;
  margin: 0 auto;
  height: 100%;
  padding: 0 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.header-side {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
}
.header-side--left {
  justify-content: flex-start;
}
.header-side--right {
  justify-content: flex-end;
}
.header-title {
  flex: 0 1 auto;
  min-width: 0;
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  color: var(--text-800);
  letter-spacing: -0.01em;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  color: var(--text-700, var(--text-600));
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 0;
  transition: background 150ms var(--ease-apple), color 150ms var(--ease-apple);
  flex-shrink: 0;
}
.icon-btn:hover {
  background: var(--bg-100);
  color: var(--text-800);
}

/* 关注按钮 */
.follow-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 14px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  line-height: 1;
  flex-shrink: 0;
  font-family: inherit;
  border: none;
  cursor: pointer;
  transition: background 150ms var(--ease-apple), color 150ms var(--ease-apple),
    transform 150ms var(--ease-apple);
}
.follow-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.follow-btn .state-followed,
.follow-btn .state-not {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.follow-btn .state-not {
  display: none;
}
.follow-btn:not(.is-followed) .state-followed {
  display: none;
}
.follow-btn:not(.is-followed) .state-not {
  display: inline-flex;
}
.follow-btn.is-followed {
  background: var(--brand-50);
  color: var(--brand-600);
}
.follow-btn:not(.is-followed) {
  background: var(--brand-500);
  color: #fff;
}
.follow-btn:not(.is-followed):hover:not(:disabled) {
  background: var(--brand-600);
}
.follow-btn:active:not(:disabled) {
  transform: scale(0.96);
}

/* 主容器 */
.page-container {
  max-width: 720px;
  margin: 0 auto;
  padding: 16px 16px 24px;
}

/* 圈子信息卡 */
.bar-card {
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  padding: 18px 18px 16px;
  margin-bottom: 14px;
}
.bar-card-head {
  display: flex;
  align-items: center;
  gap: 14px;
}
.bar-avatar {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  box-shadow: var(--shadow-xs);
}
.bar-avatar-letter {
  font-size: 24px;
  font-weight: 600;
  color: #fff;
}
.bar-info {
  flex: 1;
  min-width: 0;
}
.bar-name {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-800);
  letter-spacing: -0.01em;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bar-desc {
  margin: 3px 0 0;
  font-size: 12.5px;
  color: var(--text-400);
  line-height: 1.3;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.bar-stats {
  display: flex;
  align-items: center;
  gap: 22px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 0.5px solid var(--bg-300);
}
.bar-stat {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}
.bar-stat-ic {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--brand-50);
  color: var(--brand-500);
  flex-shrink: 0;
}
.bar-stat-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.bar-stat-label {
  font-size: 11px;
  color: var(--text-400);
  line-height: 1.1;
  white-space: nowrap;
}
.bar-stat-value {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-800);
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 分类 Tab */
.cat-tabs {
  display: flex;
  align-items: center;
  gap: 2px;
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  padding: 0 6px;
  margin-bottom: 12px;
}
.cat-tab {
  position: relative;
  padding: 12px 14px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-500);
  white-space: nowrap;
  background: transparent;
  border: none;
  cursor: pointer;
  font-family: inherit;
  transition: color 150ms var(--ease-apple);
}
.cat-tab:hover {
  color: var(--text-800);
}
.cat-tab.is-active {
  color: var(--text-800);
  font-weight: 600;
}
.cat-tab.is-active::after {
  content: '';
  position: absolute;
  left: 14px;
  right: 14px;
  bottom: 0;
  height: 2px;
  background: var(--brand-500);
  border-radius: 2px;
}

/* 帖子列表 */
.post-list {
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  overflow: hidden;
  min-height: 200px;
}
.loading-tip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 16px;
  color: var(--text-500);
  font-size: 14px;
}
.loading-tip :deep(svg) {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from {
    transform: rotate(0);
  }
  to {
    transform: rotate(360deg);
  }
}

.post-item {
  display: flex;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 0.5px solid var(--bg-300);
  cursor: pointer;
  transition: background 120ms var(--ease-apple);
}
.post-item:last-of-type {
  border-bottom: none;
}
.post-item:hover {
  background: var(--bg-100);
}
.post-item:active {
  background: var(--bg-200);
}
.post-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.post-author-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  min-width: 0;
}
.avatar {
  display: inline-block;
  border-radius: 50%;
  flex-shrink: 0;
  overflow: hidden;
}
.avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.avatar-xs {
  width: 22px;
  height: 22px;
}
.post-author {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text-700);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  flex: 0 1 auto;
}
.post-dot {
  flex-shrink: 0;
  color: var(--text-300);
  font-size: 12px;
}
.post-time {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--text-400);
  white-space: nowrap;
}
.post-badge {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-left: 4px;
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 10.5px;
  font-weight: 600;
  color: var(--chart-3);
  background: color-mix(in srgb, var(--chart-3) 14%, var(--bg-50));
  white-space: nowrap;
}

.post-title {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--text-800);
  letter-spacing: -0.005em;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}
.post-summary {
  margin: 0 0 8px;
  font-size: 13px;
  line-height: 1.45;
  color: var(--text-500);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}
.post-thumb {
  width: 96px;
  height: 72px;
  border-radius: 8px;
  object-fit: cover;
  flex-shrink: 0;
  background: var(--bg-200);
}

.post-meta-row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  margin-top: auto;
}
.post-bar-tag {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
  color: color-mix(in srgb, var(--chart-3) 72%, var(--text-800));
  background: color-mix(in srgb, var(--chart-3) 12%, var(--bg-50));
  white-space: nowrap;
}
.post-meta-item {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  color: var(--text-400);
  font-size: 12px;
  white-space: nowrap;
}
.post-last-reply {
  margin-left: auto;
  min-width: 0;
  font-size: 12px;
  color: var(--text-400);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.post-list-more {
  display: flex;
  justify-content: center;
  padding: 14px 16px;
  border-top: 0.5px solid var(--bg-300);
}
.btn-text {
  background: transparent;
  border: none;
  font-family: inherit;
  font-size: 13px;
  color: var(--brand-500);
  cursor: pointer;
  padding: 6px 12px;
  border-radius: var(--radius-sm);
  transition: background 0.15s var(--ease-apple);
}
.btn-text:hover:not(:disabled) {
  background: var(--brand-50);
}
.btn-text:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.post-list-end {
  text-align: center;
  padding: 16px 12px 18px;
  font-size: 12px;
  color: var(--text-300);
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

/* 响应式 — Tablet (<=1024px) */
@media (max-width: 1024px) {
  .page-container {
    padding: 14px 14px 24px;
  }
}

/* 响应式 — Mobile (<=768px) */
@media (max-width: 768px) {
  .page-circle {
    padding-top: 48px;
    padding-bottom: calc(52px + env(safe-area-inset-bottom));
  }

  .site-header {
    height: 48px;
  }
  .header-inner {
    padding: 0 10px;
    gap: 6px;
  }
  .header-title {
    font-size: 16px;
  }
  .icon-btn {
    width: 34px;
    height: 34px;
  }
  .follow-btn {
    padding: 5px 12px;
    font-size: 12px;
  }

  .page-container {
    padding: 12px 12px 20px;
  }

  /* Bar card */
  .bar-card {
    padding: 16px 14px 14px;
    border-radius: calc(var(--radius-lg) * 0.9);
  }
  .bar-avatar {
    width: 54px;
    height: 54px;
  }
  .bar-avatar-letter {
    font-size: 22px;
  }
  .bar-name {
    font-size: 17px;
  }
  .bar-desc {
    font-size: 12px;
  }
  .bar-stats {
    gap: 14px;
    margin-top: 12px;
    padding-top: 12px;
  }
  .bar-stat-ic {
    width: 24px;
    height: 24px;
  }
  .bar-stat-label {
    font-size: 10.5px;
  }
  .bar-stat-value {
    font-size: 13px;
  }

  /* Category tabs */
  .cat-tab {
    padding: 11px 12px;
    font-size: 13px;
  }
  .cat-tab.is-active::after {
    left: 12px;
    right: 12px;
  }

  /* Post list */
  .post-list {
    border-radius: calc(var(--radius-lg) * 0.85);
  }
  .post-item {
    padding: 12px 14px;
    gap: 10px;
  }
  .post-title {
    font-size: 14px;
    line-height: 1.38;
    margin-bottom: 3px;
  }
  .post-summary {
    font-size: 12.5px;
    line-height: 1.4;
    margin-bottom: 7px;
  }
  .post-thumb {
    width: 80px;
    height: 60px;
    border-radius: 6px;
  }
  .post-author {
    font-size: 12px;
  }
  .post-time {
    font-size: 11px;
  }
  .post-meta-row {
    gap: 10px;
  }
  .post-bar-tag {
    font-size: 10px;
    padding: 2px 7px;
  }
  .post-meta-item {
    font-size: 11px;
  }
  .post-last-reply {
    font-size: 11px;
  }
  .post-badge {
    font-size: 10px;
    padding: 1px 6px;
  }
}

/* ================================================
   阶段四：吧主管理 - 帖子删除按钮
   ================================================ */
.post-delete-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-left: auto;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  font-family: inherit;
  color: #ff3b30;
  background: rgba(255, 59, 48, 0.1);
  border: none;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 150ms var(--ease-apple), transform 150ms var(--ease-apple);
}
.post-delete-btn:hover {
  background: rgba(255, 59, 48, 0.18);
}
.post-delete-btn:active {
  transform: scale(0.94);
}

/* ================================================
   阶段四：吧主管理面板
   ================================================ */
.manage-panel {
  display: flex;
  flex-direction: column;
  gap: 22px;
}
.manage-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.manage-section-title {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--text-800, #1d1d1f);
}
.manage-hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-400, #8e8e93);
}
.manage-loading,
.manage-empty {
  padding: 16px 0;
  text-align: center;
  font-size: 13px;
  color: var(--text-400, #8e8e93);
}

/* 添加管理员输入框 */
.add-admin-row {
  display: flex;
  gap: 8px;
}
.add-admin-input {
  flex: 1;
  min-width: 0;
  padding: 9px 12px;
  font-size: 14px;
  font-family: inherit;
  color: var(--text-800);
  background: var(--bg-100, #f2f2f7);
  border: 1px solid transparent;
  border-radius: 10px;
  outline: none;
  transition: border-color 150ms var(--ease-apple),
    background 150ms var(--ease-apple);
}
.add-admin-input:focus {
  border-color: var(--brand-500);
  background: var(--bg-50, #fff);
}
.add-admin-btn {
  flex-shrink: 0;
  padding: 9px 18px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  background: var(--brand-500);
  color: #fff;
  border: none;
  cursor: pointer;
  transition: background 150ms var(--ease-apple);
}
.add-admin-btn:hover:not(:disabled) {
  background: var(--brand-600);
}
.add-admin-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 管理员列表 */
.admin-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.admin-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: var(--bg-100, #f2f2f7);
  border-radius: 12px;
}
.admin-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  flex-shrink: 0;
  background-size: cover;
  background-position: center;
  display: grid;
  place-items: center;
  color: #fff;
  font-size: 14px;
  font-weight: 700;
}
.admin-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.admin-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-800, #1d1d1f);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.admin-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}
.admin-role {
  display: inline-flex;
  align-items: center;
  font-size: 10.5px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 999px;
}
.admin-role.role-owner {
  color: #ff9500;
  background: rgba(255, 149, 0, 0.12);
}
.admin-role.role-admin {
  color: var(--brand-600);
  background: var(--brand-50);
}
.admin-time {
  font-size: 11.5px;
  color: var(--text-400, #8e8e93);
}
.admin-remove-btn {
  flex-shrink: 0;
  padding: 5px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  font-family: inherit;
  color: #ff3b30;
  background: rgba(255, 59, 48, 0.1);
  border: none;
  cursor: pointer;
  transition: background 150ms var(--ease-apple);
}
.admin-remove-btn:hover:not(:disabled) {
  background: rgba(255, 59, 48, 0.18);
}
.admin-remove-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
