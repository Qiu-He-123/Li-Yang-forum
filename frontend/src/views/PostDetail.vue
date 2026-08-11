<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import EmptyState from '../components/common/EmptyState.vue'
import BadgeIcon from '../components/common/BadgeIcon.vue'
import PostDetailSkeleton from '../components/post/PostDetailSkeleton.vue'
import { Icon } from '../components/native'
import { Dialog as NativeDialog } from '../components/native'
import { toast } from '../components/native/Toast'
import PostEditor from '../components/post/PostEditor.vue'
import PostImages from '../components/post/PostImages.vue'
import MarkdownText from '../components/common/MarkdownText.vue'
import CommentList from '../components/comment/CommentList.vue'
import {
  deletePost,
  fetchPost,
  fetchRelatedPosts,
  sharePost,
  updatePost,
  viewPost,
} from '../api/post'
import {
  favoritePost,
  unlikeTarget,
  likeTarget,
  unfavoritePost,
  reportTarget,
} from '../api/interaction'
import { getPoll, votePoll, type Poll as PostPoll } from '../api/poll'
import { useSessionStore } from '../stores/session'
import { useInteractionStore } from '../stores/interaction'
import { useFollowStore } from '../stores/follow'
import { usePostStore } from '../stores/post'
import { useUIStore } from '../stores/ui'
import type { CommentItem, MentionUser, Post } from '../types/api'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const interactionStore = useInteractionStore()
const followStore = useFollowStore()
const postStore = usePostStore()
const uiStore = useUIStore()

const postId = ref<number>(Number(route.params.id))
const post = ref<Post | null>(null)
const related = ref<Post[]>([])
// Bug 修复：初始 loading 必须为 true。
// 原先 loading=false + post=null，onMounted 中 await session.validateSession() 期间
// 模板会先渲染 EmptyState "帖子不存在或已被删除"，再切到 loading-tip，造成闪烁误导用户。
const loading = ref(true)
// 帖子加载失败提示（区分私密发布与已删除）
const postError = ref('')

// 编辑帖子弹窗
const editDialogVisible = ref(false)
const editSubmitting = ref(false)
const editEditorRef = ref<InstanceType<typeof PostEditor> | null>(null)
// 举报弹窗
const reportDialogVisible = ref(false)
const reportReason = ref('')
const reportType = ref('其他')
const reportTypes = ['垃圾广告', '人身攻击', '色情低俗', '诈骗', '其他']

// 操作 loading
const likeLoading = ref(false)
const favLoading = ref(false)
const shareLoading = ref(false)
const deleteLoading = ref(false)
const reportLoading = ref(false)
const commentLikeLoading = ref<Set<number>>(new Set())
// 私密切换：二次确认弹窗 + 请求中状态
const privateConfirmVisible = ref(false)
const togglePrivateLoading = ref(false)

// ============ 阶段二：投票相关状态 ============
const poll = ref<PostPoll | null>(null)
const pollLoading = ref(false)
const pollVoting = ref(false)
/** 多选投票时用户勾选的选项 id 集合 */
const selectedOptionIds = ref<Set<number>>(new Set())

// 状态派生
const liked = computed(() => (post.value ? interactionStore.likedPostIds.has(post.value.id) : false))
const favorited = computed(() => (post.value ? interactionStore.favoritedPostIds.has(post.value.id) : false))
const isAuthor = computed(() => {
  if (post.value?.author_id == null || session.userId == null) return false
  return Number(post.value.author_id) === Number(session.userId)
})
const following = ref(false)
const followLoading = ref(false)

// 头像渐变
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

function formatCount(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, '') + 'w'
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k'
  return String(n)
}

function isCommentLiked(commentId: number): boolean {
  return interactionStore.likedCommentIds.has(commentId)
}

function isCommentLikeLoading(commentId: number): boolean {
  return commentLikeLoading.value.has(commentId)
}

function timeAgo(dateStr?: string | null): string {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const diff = (Date.now() - date.getTime()) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  if (diff < 604800) return `${Math.floor(diff / 86400)}天前`
  return date.toLocaleDateString('zh-CN')
}

async function loadPost() {
  // keep-alive 守卫：route.params.id 变 undefined 时 Number(undefined)=NaN，必须跳过
  if (!postId.value || isNaN(postId.value)) return
  loading.value = true
  try {
    const { data } = await fetchPost(postId.value)
    post.value = data.data
    // 异步上报浏览量（不阻塞）
    viewPost(postId.value).catch(() => {})
    // 加载关注状态
    if (post.value?.author_id && !isAuthor.value) {
      following.value = await followStore.loadFollowing(post.value.author_id)
    }
    // 加载相关推荐
    fetchRelatedPosts(postId.value, {
      showGlobalLoading: false,
      showGlobalError: false,
    })
      .then(({ data: rel }) => {
        related.value = rel.data
      })
      .catch(() => {})
    // 阶段二：若帖子含投票，加载投票详情
    if (post.value?.has_poll) {
      loadPoll()
    } else {
      poll.value = null
      selectedOptionIds.value = new Set()
    }
  } catch (err) {
    // 区分"帖子私密"与"帖子已删除/不存在"两种状态，给出不同提示
    const e = err as { code?: number; message?: string }
    if (e.code === -211) {
      postError.value = '该帖子为私密发布，仅作者可见'
    } else if (e.code === -205) {
      postError.value = '帖子不存在或已被删除'
    } else {
      postError.value = e.message || '加载失败'
    }
    post.value = null
  } finally {
    loading.value = false
  }
}

// ============ 阶段二：投票加载与投票 ============
async function loadPoll() {
  pollLoading.value = true
  try {
    const { data } = await getPoll(postId.value, {
      showGlobalLoading: false,
      showGlobalError: false,
    })
    poll.value = data.data
    // 重置多选已勾选集合（仅未投票且未截止时允许选择）
    selectedOptionIds.value = new Set()
  } catch (err) {
    // 静默失败：投票详情可选
    console.warn('[PostDetail] loadPoll failed', err)
    poll.value = null
  } finally {
    pollLoading.value = false
  }
}

/** 单选/多选投票：均先勾选，再点击"提交投票"按钮确认 */
function onOptionClick(optionId: number) {
  if (!poll.value) return
  // 已投票或已截止：仅展示，不可点
  if (poll.value.user_voted || poll.value.is_expired) return
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  // 单选/多选统一行为：切换勾选状态，等用户点"提交投票"
  const next = new Set(selectedOptionIds.value)
  if (poll.value.multi_vote) {
    if (next.has(optionId)) next.delete(optionId)
    else next.add(optionId)
  } else {
    // 单选：切换为当前选项（已选则取消）
    if (next.has(optionId) && next.size === 1) next.clear()
    else {
      next.clear()
      next.add(optionId)
    }
  }
  selectedOptionIds.value = next
}

async function submitVote(optionIds: number[]) {
  if (!poll.value || pollVoting.value) return
  if (!optionIds.length) {
    toast.info('请至少选择一个选项')
    return
  }
  pollVoting.value = true
  try {
    const { data } = await votePoll(postId.value, optionIds)
    poll.value = data.data.poll
    selectedOptionIds.value = new Set()
    toast.success('投票成功')
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    pollVoting.value = false
  }
}

/** 计算单选项的投票百分比 */
function optionPercent(opt: { vote_count: number }): number {
  if (!poll.value || poll.value.total_votes <= 0) return 0
  return Math.round((opt.vote_count / poll.value.total_votes) * 100)
}

/** 是否展示投票结果（已投票或已截止） */
function showPollResults(): boolean {
  if (!poll.value) return false
  return poll.value.user_voted || poll.value.is_expired
}

/** 投票截止时间格式化 */
function formatPollDeadline(iso: string | null): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return ''
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  } catch {
    return ''
  }
}

/** 跳转到话题详情页 */
function openTopic() {
  if (post.value?.topic_id) {
    router.push(`/topic/${post.value.topic_id}`)
  }
}

/** 跳转到被 @ 的用户主页 */
function openMention(u: MentionUser) {
  router.push(`/user/${u.id}`)
}

// 评论计数更新（由 CommentList 组件 emit）
function onCommentCountUpdated(total: number) {
  if (post.value) post.value.comment_count = total
}

async function onToggleLike() {
  if (!post.value) return
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  likeLoading.value = true
  try {
    if (liked.value) {
      const { data } = await unlikeTarget('post', post.value.id)
      post.value.like_count = data.data.like_count
      interactionStore.toggleLikedPost(post.value.id, false)
    } else {
      const { data } = await likeTarget('post', post.value.id)
      post.value.like_count = data.data.like_count
      interactionStore.toggleLikedPost(post.value.id, true)
    }
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    likeLoading.value = false
  }
}

async function onToggleCommentLike(item: CommentItem) {
  if (!session.userId) {
    toast.info('璇峰厛鐧诲綍')
    return
  }
  if (commentLikeLoading.value.has(item.id)) return
  commentLikeLoading.value = new Set(commentLikeLoading.value).add(item.id)
  try {
    if (isCommentLiked(item.id)) {
      const { data } = await unlikeTarget('comment', item.id)
      item.like_count = data.data.like_count
      interactionStore.toggleLikedComment(item.id, false)
    } else {
      const { data } = await likeTarget('comment', item.id)
      item.like_count = data.data.like_count
      interactionStore.toggleLikedComment(item.id, true)
    }
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    const nextLoading = new Set(commentLikeLoading.value)
    nextLoading.delete(item.id)
    commentLikeLoading.value = nextLoading
  }
}

async function onToggleFavorite() {
  if (!post.value) return
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  favLoading.value = true
  try {
    if (favorited.value) {
      await unfavoritePost(post.value.id)
      interactionStore.toggleFavoritedPost(post.value.id, false)
      toast.success('已取消收藏')
    } else {
      await favoritePost(post.value.id)
      interactionStore.toggleFavoritedPost(post.value.id, true)
      toast.success('已收藏')
    }
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    favLoading.value = false
  }
}

async function onShare() {
  if (!post.value) return
  shareLoading.value = true
  try {
    const { data } = await sharePost(post.value.id)
    if (post.value.share_count != null) post.value.share_count = data.data.share_count
    // 复制链接到剪贴板
    try {
      await navigator.clipboard.writeText(window.location.href)
      toast.success('链接已复制')
    } catch {
      toast.success('已分享')
    }
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    shareLoading.value = false
  }
}

async function onToggleFollow() {
  if (!post.value?.author_id) return
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  followLoading.value = true
  try {
    following.value = await followStore.toggleFollow(post.value.author_id)
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    followLoading.value = false
  }
}

function onEdit() {
  editDialogVisible.value = true
}

function onEditUpdated() {
  editDialogVisible.value = false
  loadPost()
}

/** 编辑弹窗确认按钮：调用 PostEditor 的 publish 提交更新 */
async function onEditConfirm() {
  if (!editEditorRef.value) return
  editSubmitting.value = true
  try {
    await editEditorRef.value.publish()
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    editSubmitting.value = false
  }
}

async function onDeletePost() {
  if (!post.value) return
  if (!confirm('确认删除这条帖子？')) return
  deleteLoading.value = true
  try {
    await deletePost(post.value.id)
    toast.success('已删除')
    // 立即从帖子流 store 与 SWR 缓存移除，返回首页/圈子页不再残留已删除帖子
    postStore.removePost(post.value.id)
    setTimeout(() => onBack(), 600)
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    deleteLoading.value = false
  }
}

/** 点击「转为私密」按钮：弹二次确认 */
function onTogglePrivate() {
  if (!post.value) return
  // 已是私密 → 直接切回公开（无需二次确认，公开是无害操作）
  if (post.value.is_public === false) {
    doTogglePrivate()
    return
  }
  // 公开 → 私密：弹二次确认
  privateConfirmVisible.value = true
}

/** 实际调用接口切换 is_public */
async function doTogglePrivate() {
  if (!post.value) return
  privateConfirmVisible.value = false
  const nextPrivate = !(post.value.is_public === false)
  togglePrivateLoading.value = true
  try {
    await updatePost(post.value.id, { is_public: !nextPrivate })
    post.value.is_public = !nextPrivate
    const cachedPost = postStore.posts.find((p) => p.id === post.value?.id)
    if (cachedPost) cachedPost.is_public = !nextPrivate
    toast.success(nextPrivate ? '已转为私密' : '已转为公开')
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    togglePrivateLoading.value = false
  }
}

async function submitReport() {
  if (!post.value) return
  if (!reportReason.value.trim()) {
    toast.info('请填写举报理由')
    return
  }
  reportLoading.value = true
  try {
    await reportTarget({
      target_type: 'post',
      target_id: post.value.id,
      reason: `[${reportType.value}] ${reportReason.value}`,
    })
    toast.success('举报已提交')
    reportDialogVisible.value = false
    reportReason.value = ''
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    reportLoading.value = false
  }
}

function onBack() {
  if (window.history.length > 1) router.back()
  else router.push('/')
}

function openPost(p: Post) {
  router.push(`/post/${p.id}`)
}

function openAuthor() {
  if (post.value?.author_id && !post.value.is_anonymous) {
    router.push(`/user/${post.value.author_id}`)
  }
}

// 路由参数变化时重新加载
watch(
  () => route.params.id,
  (newId) => {
    if (newId) {
      postId.value = Number(newId)
      post.value = null
      // Bug 修复：切换帖子时立即标记 loading，避免短暂闪现"帖子已删除"
      loading.value = true
      postError.value = ''
      // 重置投票状态
      poll.value = null
      selectedOptionIds.value = new Set()
      loadPost()
    }
  },
)

onMounted(() => {
  // 性能优化：去除 3 层串行阻塞（validateSession → loadAll → loadPost），
  // 改为全部并行。原先是"加载一下再加载一下"的根因。
  // - validateSession 仅刷新登录态/封号状态，不阻塞帖子加载（游客可看帖）
  // - loadAll 依赖 session.userId（初始从 localStorage 读取已有值），
  //   token 过期由 http 拦截器自动 refresh 处理，无需先等 validateSession
  // - loadPost 是核心数据，立即开始
  const tasks: Promise<unknown>[] = [loadPost()]
  if (session.userId) {
    tasks.push(interactionStore.loadAll())
    tasks.push(session.validateSession())
  }
  void Promise.allSettled(tasks)
})
</script>

<template>
  <main class="page-detail">
    <!-- 顶部栏 -->
    <header class="detail-header">
      <div class="header-inner">
        <button class="icon-btn" type="button" aria-label="返回" @click="onBack">
          <Icon name="arrow-left" :size="20" />
        </button>
        <h1 class="header-title">帖子详情</h1>
        <button
          class="icon-btn icon-btn--report"
          type="button"
          aria-label="举报"
          title="举报"
          @click="reportDialogVisible = true"
        >
          <Icon name="report" :size="17" />
        </button>
      </div>
    </header>

    <div class="page-container">
      <div class="layout">
        <!-- 主帖列 -->
        <div class="post-col">
          <!-- 骨架屏：替代"加载中..."文字，展示内容结构 -->
          <PostDetailSkeleton v-if="loading" />

          <template v-else-if="post">
            <!-- 审核中/不可查看提示（非作者访问审核中帖子） -->
            <div v-if="post.is_viewable === false" class="audit-block-card">
              <div class="audit-block-icon">
                <Icon :name="post.view_block_reason === 'rejected' ? 'alert-triangle' : 'clock'" :size="32" color="#b45309" />
              </div>
              <h2 class="audit-block-title">
                {{ post.view_block_reason === 'rejected' ? '该帖子未通过审核' : '该帖子正在审核中' }}
              </h2>
              <p class="audit-block-desc">审核中，暂无法查看原文</p>
              <div class="audit-block-meta">
                <span class="post-cat">#{{ post.category || '校园' }}</span>
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
            </div>

            <!-- 正常帖子内容 -->
            <template v-else>
            <!-- 帖子卡片 -->
            <article class="post-card">
              <header class="author-row">
                <button class="avatar" :style="(post.author_avatar_url && !post.is_anonymous) ? {} : { background: avatarGradient(post.author_id) }" @click="openAuthor">
                  <img v-if="post.author_avatar_url && !post.is_anonymous" :src="post.author_avatar_url" :alt="post.author" />
                  <span v-else-if="!post.is_anonymous">{{ (post.author || 'U').charAt(0).toUpperCase() }}</span>
                  <Icon v-else name="user" :size="18" color="#fff" />
                </button>
                <div class="author-meta">
                  <div class="author-name">
                    <BadgeIcon v-if="!post.is_anonymous" :badge="post.author_badge" :size="15" />
                    {{ post.is_anonymous ? '匿名同学' : post.author }}
                    <span v-if="post.is_anonymous" class="anon-badge">匿名</span>
                  </div>
                  <div class="author-time">
                    {{ timeAgo(post.created_at) }}
                    <span class="dot">·</span>
                    <span class="cat-pill">#{{ post.category || '校园' }}</span>
                  </div>
                </div>
                <button
                  v-if="!isAuthor && !post.is_anonymous"
                  class="follow-btn"
                  :class="{ 'is-followed': following }"
                  type="button"
                  :disabled="followLoading"
                  @click="onToggleFollow"
                >
                  <Icon :name="following ? 'check' : 'user-plus'" :size="13" />
                  {{ following ? '已关注' : '关注' }}
                </button>
              </header>

              <div v-if="isAuthor" class="author-actions author-actions--top">
                <button class="btn-text" type="button" @click="onEdit">
                  <Icon name="edit" :size="14" />
                  编辑
                </button>
                <button
                  class="btn-text btn-text--private"
                  type="button"
                  :disabled="togglePrivateLoading"
                  @click="onTogglePrivate"
                >
                  <Icon name="lock" :size="14" />
                  {{ post.is_public === false ? '已私密，转公开' : '设为私密' }}
                </button>
                <button class="btn-text btn-text--danger" type="button" :disabled="deleteLoading" @click="onDeletePost">
                  <Icon name="trash" :size="14" />
                  删除
                </button>
              </div>

              <!-- AI 审核状态提示（仅作者本人可见） -->
              <div
                v-if="isAuthor && post.ai_status && post.ai_status !== 'approved'"
                class="audit-banner"
                :class="`audit-banner--${post.ai_status}`"
              >
                <div class="audit-banner-body">
                  <div class="audit-banner-title">
                    <Icon
                      :name="post.ai_status === 'rejected' ? 'alert-triangle' : 'clock'"
                      :size="16"
                    />
                    <span v-if="post.ai_status === 'rejected'">该帖子未通过审核</span>
                    <span v-else-if="post.ai_status === 'pending'">该帖子正在审核中</span>
                    <span v-else>该帖子审核状态：{{ post.ai_status }}</span>
                  </div>
                  <p v-if="post.ai_status === 'rejected'" class="audit-banner-desc">
                    {{ post.reject_reason || '内容违反社区规范' }}
                    <br />
                    别人看不到这条帖子，你可以编辑后重新发布触发审核。
                  </p>
                  <p v-else-if="post.ai_status === 'pending'" class="audit-banner-desc">
                    AI 审核中，审核通过后其他人才能看到。
                  </p>
                </div>
                <button
                  v-if="post.ai_status === 'rejected'"
                  class="audit-banner-action"
                  type="button"
                  @click="onEdit"
                >
                  <Icon name="edit" :size="14" />
                  编辑重新发布
                </button>
              </div>

              <!-- 私密标识 -->
              <div v-if="post.is_public === false" class="private-banner">
                <Icon name="lock" :size="14" />
                <span>该帖子已设为私密，仅你自己可见</span>
              </div>

              <h1 v-if="post.title" class="post-title">{{ post.title }}</h1>

              <!-- 图片墙（带预览）：详情页用原图保证清晰度，列表页才用缩略图 -->
              <div class="post-images-block">
                <PostImages v-if="post.image_urls?.length" :urls="post.image_urls" :thumb="false" />
              </div>

              <div v-if="post.content" class="post-body">
                <MarkdownText :content="post.content" />
              </div>

              <!-- 标签 -->
              <div v-if="post.tags?.length" class="post-tags">
                <span v-for="tag in post.tags" :key="tag" class="tag-chip">#{{ tag }}</span>
              </div>

              <!-- 阶段二：话题 / 位置 / @用户 元信息 -->
              <div
                v-if="post.topic_name || post.location || post.mention_users?.length"
                class="post-meta"
              >
                <button
                  v-if="post.topic_name"
                  class="meta-chip meta-chip--topic"
                  type="button"
                  :disabled="!post.topic_id"
                  @click="openTopic"
                >
                  <Icon name="tag" :size="13" />
                  <span>#{{ post.topic_name }}</span>
                </button>
                <span v-if="post.location" class="meta-chip meta-chip--location">
                  <Icon name="map-pin" :size="13" />
                  <span>{{ post.location }}</span>
                </span>
                <div v-if="post.mention_users?.length" class="meta-mentions">
                  <button
                    v-for="u in post.mention_users"
                    :key="u.id"
                    class="mention-avatar"
                    type="button"
                    :title="u.nickname"
                    :style="
                      u.avatar_url
                        ? { backgroundImage: `url(${u.avatar_url})` }
                        : { background: 'var(--brand-500)' }
                    "
                    @click="openMention(u)"
                  >
                    <span v-if="!u.avatar_url"><Icon name="user" :size="14" /></span>
                  </button>
                  <span class="meta-mentions-text">@他们</span>
                </div>
              </div>

              <!-- 阶段二：投票卡片 -->
              <section v-if="post.has_poll" class="poll-card">
                <div v-if="pollLoading" class="poll-loading">
                  <Icon name="refresh" :size="18" />
                  <span>加载投票中…</span>
                </div>
                <template v-else-if="poll">
                  <div class="poll-head">
                    <Icon name="circle-question" :size="16" :color="'var(--brand-500)'" />
                    <span class="poll-title">{{ poll.title }}</span>
                  </div>
                  <div class="poll-options">
                    <div
                      v-for="opt in poll.options"
                      :key="opt.id"
                      class="poll-option"
                      :class="{
                        'is-voted': opt.voted,
                        'is-selected': selectedOptionIds.has(opt.id),
                        'is-clickable': !poll.user_voted && !poll.is_expired && session.userId,
                      }"
                      @click="onOptionClick(opt.id)"
                    >
                      <div class="poll-option-bar" :style="{ width: showPollResults() ? optionPercent(opt) + '%' : '0%' }" />
                      <div class="poll-option-content">
                        <span
                          v-if="!poll.user_voted && !poll.is_expired"
                          class="poll-option-check"
                          :class="{ 'is-checked': selectedOptionIds.has(opt.id), 'is-radio': !poll.multi_vote }"
                        >
                          <Icon v-if="selectedOptionIds.has(opt.id)" name="check" :size="12" color="#fff" />
                        </span>
                        <span class="poll-option-text">{{ opt.content }}</span>
                        <span v-if="showPollResults()" class="poll-option-percent">{{ optionPercent(opt) }}%</span>
                        <span v-else-if="opt.voted" class="poll-option-voted-mark">
                          <Icon name="check" :size="14" :color="'var(--brand-500)'" />
                        </span>
                      </div>
                    </div>
                  </div>
                  <div class="poll-foot">
                    <span class="poll-meta">
                      {{ poll.multi_vote ? '多选' : '单选' }} · {{ poll.total_votes }} 人参与
                      <span v-if="poll.is_expired">· 已截止</span>
                      <span v-else-if="poll.deadline">· 截止 {{ formatPollDeadline(poll.deadline) }}</span>
                    </span>
                    <button
                      v-if="!poll.user_voted && !poll.is_expired && selectedOptionIds.size > 0"
                      class="poll-submit-btn"
                      type="button"
                      :disabled="pollVoting"
                      @click="submitVote(Array.from(selectedOptionIds))"
                    >
                      {{ pollVoting ? '提交中…' : '提交投票' }}
                    </button>
                  </div>
                </template>
              </section>

              <!-- 互动栏 -->
              <div class="interactions">
                <button
                  class="action-btn"
                  :class="{ active: liked }"
                  type="button"
                  :disabled="likeLoading"
                  @click="onToggleLike"
                >
                  <Icon :name="liked ? 'heart-filled' : 'heart'" :size="18" />
                  <span>点赞</span>
                  <span v-if="post.like_count" class="action-count">{{ formatCount(post.like_count) }}</span>
                </button>
                <button class="action-btn" type="button">
                  <Icon name="message-square" :size="18" />
                  <span>评论</span>
                  <span v-if="post.comment_count" class="action-count">{{ formatCount(post.comment_count) }}</span>
                </button>
                <button class="action-btn" type="button" :disabled="shareLoading" @click="onShare">
                  <Icon name="share" :size="18" />
                  <span>分享</span>
                </button>
                <button
                  class="action-btn"
                  :class="{ active: favorited }"
                  type="button"
                  :disabled="favLoading"
                  @click="onToggleFavorite"
                >
                  <Icon :name="favorited ? 'bookmark' : 'bookmark'" :size="18" />
                  <span>{{ favorited ? '已藏' : '收藏' }}</span>
                </button>
              </div>

            </article>

            <!-- 评论区（复用 CommentList 组件）-->
            <section class="comments-card">
              <h2 class="comments-title">
                全部评论<span class="count">{{ post.comment_count }}</span>
              </h2>
              <CommentList
                :post-id="postId"
                :comment-count="post.comment_count"
                @count-updated="onCommentCountUpdated"
              />
            </section>
            </template>
          </template>

          <EmptyState v-else :text="postError || '帖子不存在或已被删除'" />
        </div>

        <!-- 相关推荐侧栏 -->
        <aside class="related">
          <h2 class="related-title">相关推荐</h2>
          <div v-if="related.length" class="related-list">
            <article v-for="p in related" :key="p.id" class="related-card" @click="openPost(p)">
              <img v-if="p.image_urls?.length" :src="p.image_urls[0]" :alt="p.title || ''" class="related-img" />
              <div v-else class="related-img related-img--placeholder">
                <Icon name="image" :size="20" color="#c7c7cc" />
              </div>
              <div class="related-content">
                <h3 class="related-card-title">{{ p.title || p.content.slice(0, 50) }}</h3>
                <div class="related-meta">
                  <span v-if="p.is_public === false" class="private-badge">
                    <Icon name="lock" :size="11" />
                    已私密
                  </span>
                  <span>#{{ p.category || '校园' }}</span>
                  <span class="sep">·</span>
                  <span class="likes">
                    <Icon name="heart" :size="11" />
                    {{ formatCount(p.like_count) }}
                  </span>
                </div>
              </div>
            </article>
          </div>
          <div v-else class="related-empty">
            <Icon name="info" :size="20" color="#aeaeb2" />
            <p>暂无相关推荐</p>
          </div>
        </aside>
      </div>
    </div>

    <!-- 编辑弹窗 -->
    <NativeDialog v-model="editDialogVisible" title="编辑帖子" width="640px">
      <PostEditor
        v-if="post"
        ref="editEditorRef"
        :key="post.id"
        :post-id="post.id"
        :initial-content="post.content"
        :initial-title="post.title"
        :initial-category="post.category"
        :initial-image-urls="post.image_urls"
        :initial-is-anonymous="post.is_anonymous"
        :initial-school-id="post.school_id"
        @updated="onEditUpdated"
      />
      <template #footer>
        <button class="btn btn-outline" type="button" :disabled="editSubmitting" @click="editDialogVisible = false">
          取消
        </button>
        <button class="btn btn-primary" type="button" :disabled="editSubmitting" @click="onEditConfirm">
          {{ editSubmitting ? '保存中…' : '确认修改' }}
        </button>
      </template>
    </NativeDialog>

    <!-- 举报弹窗 -->
    <NativeDialog v-model="reportDialogVisible" title="举报" width="440px">
      <div class="report-form">
        <div class="form-row">
          <label class="form-label">举报类型</label>
          <div class="chip-row">
            <button
              v-for="t in reportTypes"
              :key="t"
              class="chip"
              :class="{ 'is-active': reportType === t }"
              type="button"
              @click="reportType = t"
            >
              {{ t }}
            </button>
          </div>
        </div>
        <div class="form-row">
          <label class="form-label">举报理由</label>
          <textarea
            v-model="reportReason"
            class="form-textarea"
            rows="4"
            placeholder="请描述具体原因"
          />
        </div>
      </div>
      <template #footer>
        <button class="btn btn-outline" type="button" @click="reportDialogVisible = false">取消</button>
        <button class="btn btn-primary" type="button" :disabled="reportLoading" @click="submitReport">
          {{ reportLoading ? '提交中…' : '提交' }}
        </button>
      </template>
    </NativeDialog>

    <!-- 转为私密二次确认 -->
    <NativeDialog v-model="privateConfirmVisible" title="转为私密发布" width="380px">
      <p class="private-confirm-text">
        转为私密后，该帖子仅你自己可见，其他人将无法在首页、圈子、搜索等任何列表中看到此帖。确认要转为私密吗？
      </p>
      <template #footer>
        <button class="btn btn-outline" type="button" @click="privateConfirmVisible = false">取消</button>
        <button class="btn btn-primary" type="button" :disabled="togglePrivateLoading" @click="doTogglePrivate">
          {{ togglePrivateLoading ? '处理中…' : '确认私密' }}
        </button>
      </template>
    </NativeDialog>
  </main>
</template>

<style scoped>
.page-detail {
  min-height: 100vh;
  background: var(--bg-100);
  padding-bottom: calc(80px + env(safe-area-inset-bottom));
}

/* 顶部栏 */
.detail-header {
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
  max-width: 900px;
  margin: 0 auto;
  height: 100%;
  padding: 0 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.header-title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: var(--text-800);
  letter-spacing: -0.01em;
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
.icon-btn--report {
  color: var(--error);
}
.icon-btn--report:hover {
  background: rgba(255, 59, 48, 0.1);
  color: var(--error);
}
.icon-btn--report:active {
  background: rgba(255, 59, 48, 0.18);
  color: var(--error);
}

/* 容器 */
.page-container {
  max-width: 900px;
  margin: 0 auto;
  padding: 32px 22px 48px;
}
.layout {
  display: flex;
  flex-direction: column;
  gap: 24px;
}
.post-col {
  width: 100%;
  min-width: 0;
}
.related {
  width: 100%;
}

/* 加载状态 */
.loading-tip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 60px 0;
  color: var(--text-500);
  font-size: 14px;
}
.loading-tip :deep(svg) {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 帖子卡片 */
.post-card {
  background: var(--bg-50);
  border: 1px solid var(--bg-300);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  padding: 28px;
}
/* 作者行与图片之间留出呼吸间距 */
.post-images-block {
  margin-top: 18px;
}
.author-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: none;
  cursor: pointer;
  display: grid;
  place-items: center;
  color: #fff;
  font-weight: 600;
  font-size: 15px;
  flex-shrink: 0;
  overflow: hidden;
}
.avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.author-meta {
  flex: 1;
  min-width: 0;
}
.author-name {
  font-weight: 600;
  font-size: 15px;
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
.author-time {
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
.follow-btn {
  height: 32px;
  padding: 0 14px;
  border-radius: 999px;
  border: none;
  background: var(--brand-500);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: all 0.15s var(--ease-apple);
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

/* 私密帖子顶部横幅 */
.private-banner {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 12px 0 0;
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 500;
  color: #b45309;
  background: rgba(245, 158, 11, 0.1);
  border: 1px solid rgba(245, 158, 11, 0.25);
  border-radius: 8px;
}

/* 帖子正文 */
.post-title {
  font-weight: 700;
  font-size: 26px;
  color: var(--text-800);
  line-height: 1.25;
  letter-spacing: -0.02em;
  margin: 20px 0;
  text-wrap: balance;
  word-break: break-word;
  overflow-wrap: break-word;
}

/* AI 审核状态提示横幅（仅作者本人可见） */
.audit-banner {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin: 14px 0 4px;
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid transparent;
  text-align: left;
}
.audit-banner--rejected {
  background: #fef2f2;
  border-color: #fecaca;
}
.audit-banner--pending {
  background: #fffbeb;
  border-color: #fde68a;
}
.audit-banner--manual_review {
  background: #f0f9ff;
  border-color: #bae6fd;
}
.audit-banner-body {
  flex: 1;
  min-width: 0;
  text-align: left;
}
.audit-banner-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 15px;
  font-weight: 700;
  color: #1f2937;
  text-align: left;
}
.audit-banner--rejected .audit-banner-title {
  color: #b91c1c;
}
.audit-banner--pending .audit-banner-title {
  color: #b45309;
}
.audit-banner-desc {
  margin: 6px 0 0;
  font-size: 13px;
  color: #6b7280;
  line-height: 1.6;
}
.audit-banner-action {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 999px;
  border: none;
  background: #dc2626;
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  flex-shrink: 0;
  align-self: center;
  transition: opacity 0.15s, transform 0.15s;
}
.audit-banner-action:hover {
  opacity: 0.9;
}
.audit-banner-action:active {
  transform: scale(0.97);
}
.post-body {
  margin-top: 12px;
  width: 100%;
  box-sizing: border-box;
}
.post-body p {
  display: block;
  width: 100%;
  box-sizing: border-box;
  font-size: 15px;
  line-height: 1.7;
  color: var(--text-800);
  margin: 0 0 16px;
}
.post-body p:last-child {
  margin-bottom: 0;
}
.post-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 14px;
}
.tag-chip {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  background: var(--brand-50);
  color: var(--brand-600);
  font-size: 12px;
  font-weight: 500;
  border-radius: 999px;
}

/* ============ 阶段二：话题 / 位置 / @用户 元信息 ============ */
.post-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
}
.meta-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 500;
  border: none;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s var(--ease-apple);
}
.meta-chip:disabled {
  cursor: default;
  opacity: 0.85;
}
.meta-chip--topic {
  background: var(--brand-50);
  color: var(--brand-600);
}
.meta-chip--topic:hover:not(:disabled) {
  background: var(--brand-100);
}
.meta-chip--location {
  background: var(--bg-100);
  color: var(--text-700);
  cursor: default;
}
.meta-mentions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.meta-mentions .mention-avatar {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 2px solid var(--bg-50);
  background-size: cover;
  background-position: center;
  color: #fff;
  display: grid;
  place-items: center;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  padding: 0;
  margin-left: -8px;
  transition: transform 0.15s var(--ease-apple);
}
.meta-mentions .mention-avatar:first-child {
  margin-left: 0;
}
.meta-mentions .mention-avatar:hover {
  transform: translateY(-2px);
  z-index: 1;
}
.meta-mentions-text {
  font-size: 12px;
  color: var(--text-500);
  margin-left: 4px;
}

/* ============ 阶段二：投票卡片 ============ */
.poll-card {
  margin-top: 18px;
  padding: 18px;
  background: var(--brand-50);
  border-radius: var(--radius-md);
  border: 1px solid var(--brand-100);
}
.poll-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 16px 0;
  color: var(--text-500);
  font-size: 13px;
}
.poll-loading :deep(svg) {
  animation: spin 1s linear infinite;
}
.poll-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}
.poll-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-800);
  flex: 1;
  min-width: 0;
}
.poll-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.poll-option {
  position: relative;
  padding: 12px 14px;
  background: var(--bg-50);
  border: 1px solid var(--bg-300);
  border-radius: var(--radius-sm);
  overflow: hidden;
  transition: all 0.15s var(--ease-apple);
}
.poll-option.is-clickable {
  cursor: pointer;
}
.poll-option.is-clickable:hover {
  border-color: var(--brand-300);
  background: var(--brand-50);
}
.poll-option.is-selected {
  border-color: var(--brand-500);
  background: var(--brand-50);
}
.poll-option.is-voted {
  border-color: var(--brand-300);
}
.poll-option-bar {
  position: absolute;
  inset: 0;
  background: var(--brand-100);
  transition: width 0.4s var(--ease-apple);
  z-index: 0;
}
.poll-option-content {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 8px;
}
.poll-option-check {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 2px solid var(--bg-400);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.15s var(--ease-apple);
}
.poll-option-check.is-checked {
  background: var(--brand-500);
  border-color: var(--brand-500);
}
.poll-option-text {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  color: var(--text-800);
  word-break: break-word;
}
.poll-option-percent {
  font-size: 13px;
  font-weight: 600;
  color: var(--brand-600);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}
.poll-option-voted-mark {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
}
.poll-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 14px;
}
.poll-meta {
  font-size: 12px;
  color: var(--text-500);
}
.poll-submit-btn {
  padding: 6px 16px;
  border-radius: 999px;
  background: var(--brand-500);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s var(--ease-apple);
  flex-shrink: 0;
}
.poll-submit-btn:hover:not(:disabled) {
  background: var(--brand-600);
}
.poll-submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 互动栏 */
.interactions {
  display: flex;
  align-items: center;
  gap: 24px;
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid var(--bg-300);
}
.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 14px;
  border-radius: 999px;
  background: transparent;
  border: none;
  color: var(--text-500);
  font-size: 14px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s var(--ease-apple);
}
.action-btn:hover:not(:disabled) {
  background: var(--bg-200);
  color: var(--text-800);
}
.action-btn.active {
  color: var(--brand-500);
}
.action-btn.active:hover:not(:disabled) {
  background: var(--brand-50);
}
.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.action-count {
  font-weight: 600;
}

/* 作者操作 */
.author-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--bg-200);
}
.author-actions--top {
  margin-top: 10px;
  padding-top: 0;
  border-top: none;
  flex-wrap: wrap;
}
.btn-text {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border: none;
  background: transparent;
  color: var(--text-600);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: all 0.15s var(--ease-apple);
}
.btn-text:hover:not(:disabled) {
  background: var(--bg-100);
  color: var(--text-800);
}
.btn-text--private {
  background: rgba(245, 158, 11, 0.12);
  color: #b45309;
  font-weight: 700;
}
.btn-text--private:hover:not(:disabled) {
  background: rgba(245, 158, 11, 0.2);
  color: #92400e;
}
.btn-text--danger {
  color: var(--error);
}
.btn-text--danger:hover:not(:disabled) {
  background: #ffecea;
}
.btn-text:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 评论区 */
.comments-card {
  background: var(--bg-50);
  border: 1px solid var(--bg-300);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  padding: 28px;
  margin-top: 24px;
}
.comments-title {
  font-weight: 700;
  font-size: 18px;
  color: var(--text-800);
  margin: 0 0 16px;
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.comments-title .count {
  color: var(--text-400);
  font-weight: 600;
}

.comment-input {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 44px;
  padding: 0 6px 0 16px;
  background: var(--bg-50);
  border: 1px solid var(--bg-300);
  border-radius: var(--radius-md);
  transition: all 0.15s var(--ease-apple);
}
.comment-input:focus-within {
  border-color: var(--brand-500);
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.12);
}
.comment-input input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  font-size: 14px;
  color: var(--text-800);
}
.comment-input input::placeholder {
  color: var(--text-500);
}
.send-btn {
  height: 30px;
  padding: 0 16px;
  background: var(--brand-500);
  color: #fff;
  border: none;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s var(--ease-apple);
}
.send-btn:hover:not(:disabled) {
  background: var(--brand-600);
}
.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.send-btn--sm {
  height: 28px;
  padding: 0 12px;
  font-size: 12px;
}

.comment-list {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
}
.comment-group {
  border-bottom: 1px solid var(--bg-200);
}
.comment-group:last-child {
  border-bottom: none;
}
.comment {
  display: flex;
  gap: 12px;
  padding: 16px 0;
}
.comment--reply {
  padding: 8px 0 8px 50px;
}
.comment-avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  color: #fff;
  font-weight: 600;
  font-size: 13px;
  overflow: hidden;
}
.comment-avatar--sm {
  width: 28px;
  height: 28px;
  font-size: 11px;
}
.comment-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.comment-body-wrap {
  flex: 1;
  min-width: 0;
}
.comment-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 3px;
}
.comment-user {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-800);
}
.comment-time {
  font-size: 11px;
  color: var(--text-500);
}
.comment-text {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-800);
  margin: 0;
  word-break: break-word;
}
.comment-foot {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 8px;
}
.comment-like {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 0;
  border: none;
  background: transparent;
  font-size: 12px;
  color: var(--text-500);
  cursor: pointer;
  font-family: inherit;
  transition: color 0.15s var(--ease-apple);
}
.comment-like:hover:not(:disabled),
.comment-like.active {
  color: var(--brand-500);
}
.comment-like:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.comment-reply {
  background: none;
  border: none;
  padding: 0;
  font-size: 12px;
  color: var(--text-600);
  cursor: pointer;
  transition: color 0.15s var(--ease-apple);
}
.comment-reply:hover {
  color: var(--brand-500);
}
.comment-reply--danger:hover {
  color: var(--error);
}

.reply-input {
  margin: 0 0 12px 50px;
  padding: 10px 12px;
  background: var(--bg-100);
  border-radius: var(--radius-md);
}
.reply-to {
  display: block;
  font-size: 12px;
  color: var(--text-500);
  margin-bottom: 6px;
}
.reply-row {
  display: flex;
  gap: 8px;
}
.reply-row input {
  flex: 1;
  min-width: 0;
  padding: 7px 12px;
  border: 1px solid var(--bg-300);
  border-radius: var(--radius-sm);
  background: var(--bg-50);
  font-size: 13px;
  color: var(--text-800);
  outline: none;
  transition: all 0.15s var(--ease-apple);
}
.reply-row input:focus {
  border-color: var(--brand-500);
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.12);
}
.btn-cancel {
  height: 30px;
  padding: 0 10px;
  background: transparent;
  border: none;
  color: var(--text-500);
  font-size: 12px;
  cursor: pointer;
  border-radius: var(--radius-sm);
}
.btn-cancel:hover {
  background: var(--bg-200);
}

.empty-comments {
  padding: 30px 0;
  text-align: center;
  color: var(--text-500);
  font-size: 13px;
}
.load-more {
  margin-top: 12px;
  text-align: center;
}

/* 相关推荐 */
.related-title {
  font-weight: 700;
  font-size: 18px;
  color: var(--text-800);
  margin: 0 0 16px;
}
.related-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
.related-card {
  display: flex;
  gap: 12px;
  padding: 14px;
  background: var(--bg-50);
  border: 1px solid var(--bg-300);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.15s var(--ease-apple);
}
.related-card:hover {
  box-shadow: var(--shadow-xs);
  border-color: var(--bg-400);
}
.related-img {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-sm);
  object-fit: cover;
  flex-shrink: 0;
  background: var(--bg-100);
}
.related-img--placeholder {
  display: grid;
  place-items: center;
}
.related-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.related-card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-800);
  line-height: 1.35;
  margin: 0 0 4px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.related-meta {
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--text-500);
}
.related-meta .sep {
  opacity: 0.6;
}
.related-meta .likes {
  display: inline-flex;
  align-items: center;
  gap: 2px;
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
.related-empty {
  text-align: center;
  padding: 30px 12px;
  color: var(--text-500);
  font-size: 12px;
  background: var(--bg-50);
  border-radius: var(--radius-md);
}
.related-empty p {
  margin: 6px 0 0;
}

/* 举报表单 */
.report-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
/* 私密二次确认提示文字 */
.private-confirm-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-700);
}
.form-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.form-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-600);
}
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chip {
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid var(--bg-300);
  background: var(--bg-50);
  font-size: 12px;
  color: var(--text-600);
  cursor: pointer;
  transition: all 0.15s var(--ease-apple);
}
.chip:hover {
  border-color: var(--bg-400);
}
.chip.is-active {
  background: var(--brand-500);
  border-color: var(--brand-500);
  color: #fff;
}
.form-textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--bg-300);
  border-radius: var(--radius-md);
  background: var(--bg-50);
  font-size: 14px;
  color: var(--text-800);
  font-family: inherit;
  resize: vertical;
  outline: none;
  transition: all 0.15s var(--ease-apple);
}
.form-textarea:focus {
  border-color: var(--brand-500);
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.12);
}

/* 响应式 */
@media (max-width: 560px) {
  .page-container {
    padding: 20px 16px 36px;
  }
  .post-card,
  .comments-card {
    padding: 20px;
  }
  .post-title {
    font-size: 22px;
  }
  .interactions {
    gap: 6px;
    flex-wrap: wrap;
  }
  .related-list {
    grid-template-columns: 1fr;
  }
  .action-btn {
    padding: 7px 10px;
    font-size: 13px;
  }
}

/* 审核中/不可查看提示卡片 */
.audit-block-card {
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: var(--radius-lg);
  padding: 40px 28px;
  text-align: center;
  box-shadow: var(--shadow-xs);
}
.audit-block-icon {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: #fef3c7;
  display: grid;
  place-items: center;
  margin: 0 auto 16px;
}
.audit-block-title {
  font-size: 18px;
  font-weight: 700;
  color: #92400e;
  margin: 0 0 8px;
}
.audit-block-desc {
  font-size: 14px;
  color: #78350f;
  margin: 0 0 20px;
}
.audit-block-meta {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-400);
}
</style>
