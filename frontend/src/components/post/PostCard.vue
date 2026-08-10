<script setup lang="ts">
/**
 * 帖子卡片（原生组件，替代 Element Plus）
 * 用于收藏夹、草稿箱等列表型页面展示帖子
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { Icon } from '../native'
import { toast } from '../native/Toast'
import { Dialog as NativeDialog } from '../native'
import PostImages from './PostImages.vue'
import MarkdownText from '../common/MarkdownText.vue'
import CommentList from '../comment/CommentList.vue'
import AiStatusBadge from '../common/AiStatusBadge.vue'
import BadgeIcon from '../common/BadgeIcon.vue'
import { deletePost } from '../../api/post'
import { likeTarget, unlikeTarget, favoritePost, unfavoritePost, reportTarget } from '../../api/interaction'
import { useSessionStore } from '../../stores/session'
import { usePostStore } from '../../stores/post'
import { useInteractionStore } from '../../stores/interaction'
import { useUIStore } from '../../stores/ui'
import type { Post } from '../../types/api'

const props = defineProps<{
  post: Post
}>()

const emit = defineEmits<{ (e: 'edit', post: Post): void; (e: 'deleted', postId: number): void }>()

const session = useSessionStore()
const postStore = usePostStore()
const interactionStore = useInteractionStore()
const uiStore = useUIStore()
const router = useRouter()

const showComments = ref(false)
const likeLoading = ref(false)
const favLoading = ref(false)
const reportDialogVisible = ref(false)
const deleteDialogVisible = ref(false)
const reportReason = ref('')
const reportType = ref('其他')

const reportTypes = ['垃圾广告', '人身攻击', '色情低俗', '诈骗', '其他']

// 从 store 派生 active 态：刷新后仍能保持高亮
const liked = computed(() => interactionStore.likedPostIds.has(props.post.id))
const favorited = computed(() => interactionStore.favoritedPostIds.has(props.post.id))

const isAuthor = () => props.post.author_id != null && props.post.author_id === session.userId

// 标题/摘要：取正文第一行作为主题标题（最多 48 字），其余作为摘要
const firstLine = computed(() => {
  const raw = props.post.content || ''
  const line = raw.split('\n').find((l) => l.trim()) || ''
  return line.length > 48 ? line.slice(0, 48) + '…' : line
})
const restText = computed(() => {
  const raw = props.post.content || ''
  const idx = raw.indexOf('\n')
  let rest = idx >= 0 ? raw.slice(idx + 1) : raw.length > 48 ? raw.slice(48) : ''
  return rest.trim()
})

// 头像首字母 + 渐变色
const avatarPalettes = [
  'linear-gradient(135deg, #66abff, #007aff)',
  'linear-gradient(135deg, #34c759, #2e8dff)',
  'linear-gradient(135deg, #ff9500, #007aff)',
  'linear-gradient(135deg, #5856d6, #af52de)',
  'linear-gradient(135deg, #d1d1d6, #8e8e93)',
]
const avatarGradient = computed(() => {
  const id = props.post.author_id
  if (id == null) return avatarPalettes[4]
  return avatarPalettes[id % 5]
})
const authorInitial = computed(() => (props.post.author || '?').trim().charAt(0).toUpperCase())

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

async function toggleLike() {
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  likeLoading.value = true
  try {
    if (liked.value) {
      const { data } = await unlikeTarget('post', props.post.id)
      props.post.like_count = data.data.like_count
      interactionStore.toggleLikedPost(props.post.id, false)
    } else {
      const { data } = await likeTarget('post', props.post.id)
      props.post.like_count = data.data.like_count
      interactionStore.toggleLikedPost(props.post.id, true)
    }
  } catch (error) {
    toast.error((error as Error).message)
  } finally {
    likeLoading.value = false
  }
}

async function toggleFavorite() {
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  favLoading.value = true
  try {
    if (favorited.value) {
      await unfavoritePost(props.post.id)
      interactionStore.toggleFavoritedPost(props.post.id, false)
      toast.success('已取消收藏')
    } else {
      await favoritePost(props.post.id)
      interactionStore.toggleFavoritedPost(props.post.id, true)
      toast.success('已收藏')
    }
  } catch (error) {
    toast.error((error as Error).message)
  } finally {
    favLoading.value = false
  }
}

function toggleComments() {
  showComments.value = !showComments.value
}

function goDetail() {
  if (props.post.is_viewable === false) {
    toast.info(props.post.content || '审核中，暂无法查看原文')
    return
  }
  // 游客可查看帖子详情
  router.push(`/post/${props.post.id}`)
}

function openReport() {
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  reportDialogVisible.value = true
}

async function onDelete() {
  deleteDialogVisible.value = false
  try {
    await deletePost(props.post.id)
    toast.success('已删除')
    postStore.removePost(props.post.id)
    emit('deleted', props.post.id)
  } catch (error) {
    toast.error((error as Error).message)
  }
}

function onEdit() {
  emit('edit', props.post)
}

async function submitReport() {
  if (!reportReason.value.trim()) {
    toast.error('请填写举报理由')
    return
  }
  try {
    await reportTarget({
      target_type: 'post',
      target_id: props.post.id,
      reason: `[${reportType.value}] ${reportReason.value}`,
    })
    toast.success('举报已提交')
    reportDialogVisible.value = false
    reportReason.value = ''
  } catch (error) {
    toast.error((error as Error).message)
  }
}

function onCommentCountUpdated(total: number) {
  props.post.comment_count = total
}

function goTagSearch(tag: string) {
  router.push({ path: '/search', query: { tag } })
}
</script>

<template>
  <article class="post-card">
    <!-- 作者行 -->
    <div class="author-row">
      <span class="avatar" :style="post.author_avatar_url && !post.is_anonymous ? {} : { background: avatarGradient }" aria-hidden="true">
        <img v-if="post.author_avatar_url && !post.is_anonymous" :src="post.author_avatar_url" :alt="post.author" loading="lazy" />
        <span v-else>{{ post.is_anonymous ? '匿' : authorInitial }}</span>
      </span>
      <div class="author-meta">
        <div class="author-name-row">
          <BadgeIcon v-if="!post.is_anonymous" :badge="post.author_badge" :size="14" />
          <span class="author-name">{{ post.is_anonymous ? '匿名同学' : post.author }}</span>
          <AiStatusBadge
            :status="post.ai_status"
            :reject-reason="post.reject_reason"
            :show-approved="isAuthor()"
          />
          <span class="cat-pill">#{{ post.category || '校园' }}</span>
          <span v-if="post.explored" class="explore-badge">探索</span>
        </div>
        <span class="post-time">{{ timeAgo(post.created_at) }} · {{ post.school }}</span>
      </div>
    </div>

    <!-- 标题 + 摘要 -->
    <a class="post-title-link" @click="goDetail">
      <h3 class="post-title">
        <span v-if="post.is_public === false" class="private-badge">
          <Icon name="lock" :size="12" />
          已私密
        </span>
        <span class="title-text">{{ firstLine }}</span>
      </h3>
      <MarkdownText v-if="restText" :content="restText" class="post-summary" :clamp="3" />
    </a>

    <!-- 缩略图 -->
    <div v-if="post.image_urls.length" class="post-images-wrap">
      <PostImages :urls="post.image_urls" />
    </div>

    <!-- 标签 -->
    <div v-if="post.tags.length" class="post-tags">
      <span
        v-for="tag in post.tags"
        :key="tag"
        class="tag-chip"
        @click="goTagSearch(tag)"
      >
        #{{ tag }}
      </span>
    </div>

    <!-- 操作行 -->
    <div class="actions-row">
      <button
        class="action-btn"
        :class="{ 'is-active': liked }"
        type="button"
        :disabled="likeLoading"
        @click="toggleLike"
      >
        <Icon :name="liked ? 'heart-filled' : 'heart'" :size="14" />
        <span>赞</span>
        <span v-if="post.like_count" class="action-count">{{ post.like_count }}</span>
      </button>
      <button
        class="action-btn"
        :class="{ 'is-active': showComments }"
        type="button"
        @click="toggleComments"
      >
        <Icon name="message-square" :size="14" />
        <span>评论</span>
        <span v-if="post.comment_count" class="action-count">{{ post.comment_count }}</span>
      </button>
      <button
        class="action-btn"
        :class="{ 'is-active': favorited }"
        type="button"
        :disabled="favLoading"
        @click="toggleFavorite"
      >
        <Icon name="bookmark" :size="14" />
        <span>{{ favorited ? '已藏' : '收藏' }}</span>
      </button>
      <button class="action-btn action-btn--report" type="button" @click="openReport">
        <Icon name="triangle-alert" :size="14" />
        <span>举报</span>
      </button>
      <template v-if="isAuthor()">
        <button class="action-btn" type="button" @click="onEdit">
          <Icon name="edit" :size="14" />
          <span>编辑</span>
        </button>
        <button class="action-btn action-btn--danger" type="button" @click="deleteDialogVisible = true">
          <Icon name="trash" :size="14" />
          <span>删除</span>
        </button>
      </template>
    </div>

    <!-- 评论列表 -->
    <CommentList
      v-if="showComments"
      :post-id="post.id"
      :comment-count="post.comment_count"
      @count-updated="onCommentCountUpdated"
    />

    <!-- 删除确认弹窗 -->
    <NativeDialog v-model="deleteDialogVisible" title="删除帖子" width="380px">
      <p class="dialog-text">确认删除这条帖子？删除后不可恢复。</p>
      <template #footer>
        <button class="btn btn-outline" type="button" @click="deleteDialogVisible = false">取消</button>
        <button class="btn btn-danger" type="button" @click="onDelete">删除</button>
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
        <button class="btn btn-primary" type="button" @click="submitReport">提交</button>
      </template>
    </NativeDialog>
  </article>
</template>

<style scoped>
.post-card {
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  padding: 14px 16px;
  transition: box-shadow 0.2s var(--ease-apple);
}
.post-card:hover {
  box-shadow: var(--shadow-sm);
}

.author-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
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
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.author-name-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.author-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-800);
}
.cat-pill {
  font-size: 11px;
  font-weight: 600;
  color: var(--brand-600);
  background: var(--brand-50);
  padding: 2px 8px;
  border-radius: 999px;
}
.explore-badge {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 999px;
  background: linear-gradient(135deg, #34c759, #2e8dff);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
}
.post-time {
  font-size: 12px;
  color: var(--text-500);
}

.post-title-link {
  display: block;
  cursor: pointer;
  text-decoration: none;
  color: inherit;
}
.post-title {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.45;
  color: var(--text-800);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
  transition: color 0.15s var(--ease-apple);
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
.post-title-link:hover .post-title {
  color: var(--brand-500);
}
.post-summary {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-500);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}

.post-images-wrap {
  margin-top: 10px;
  max-width: 360px;
}

.post-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.tag-chip {
  font-size: 11px;
  color: var(--brand-500);
  background: var(--brand-50);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s var(--ease-apple);
}
.tag-chip:hover {
  background: var(--brand-100);
}

.actions-row {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 10px;
  flex-wrap: wrap;
}
.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  border-radius: var(--radius-sm);
  background: transparent;
  border: none;
  font-family: inherit;
  font-size: 12.5px;
  color: var(--text-500);
  cursor: pointer;
  transition: all 0.15s var(--ease-apple);
}
.action-btn:hover:not(:disabled) {
  background: var(--bg-100);
  color: var(--text-800);
}
.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.action-btn.is-active {
  color: var(--brand-500);
}
.action-btn--danger:hover:not(:disabled) {
  color: var(--error);
  background: rgba(255, 59, 48, 0.08);
}
.action-btn--report {
  color: var(--error);
}
.action-btn--report:hover:not(:disabled) {
  color: var(--error);
  background: rgba(255, 59, 48, 0.1);
}
.action-count {
  font-variant-numeric: tabular-nums;
}

/* 举报表单 */
.report-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.form-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.form-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-800);
}
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chip {
  padding: 5px 12px;
  border-radius: 999px;
  border: 1px solid var(--color-border);
  background: var(--bg-50);
  font-family: inherit;
  font-size: 12.5px;
  color: var(--text-600);
  cursor: pointer;
  transition: all 0.15s var(--ease-apple);
}
.chip:hover {
  background: var(--bg-100);
}
.chip.is-active {
  background: var(--brand-500);
  border-color: var(--brand-500);
  color: #fff;
}
.form-textarea {
  width: 100%;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border);
  background: var(--bg-50);
  font-family: inherit;
  font-size: 13px;
  color: var(--text-800);
  outline: none;
  resize: vertical;
  transition: border-color 0.15s var(--ease-apple), box-shadow 0.15s var(--ease-apple);
}
.form-textarea:focus {
  border-color: var(--brand-500);
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.12);
}

.dialog-text {
  margin: 0;
  font-size: 14px;
  color: var(--text-800);
  line-height: 1.5;
}
</style>
