<script setup lang="ts">
/**
 * 评论项（原生组件，替代 Element Plus）
 * 用于 PostCard 内嵌评论列表
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { Icon } from '../native'
import { toast } from '../native/Toast'
import { Dialog as NativeDialog } from '../native'
import { deleteComment } from '../../api/comment'
import { likeTarget, unlikeTarget } from '../../api/interaction'
import { useSessionStore } from '../../stores/session'
import { useInteractionStore } from '../../stores/interaction'
import { useUIStore } from '../../stores/ui'
import { formatRelative } from '../../utils/time'
import AiStatusBadge from '../common/AiStatusBadge.vue'
import BadgeIcon from '../common/BadgeIcon.vue'
import type { CommentItem as CommentItemType } from '../../types/api'

const props = defineProps<{
  comment: CommentItemType
  postId: number
  isReply?: boolean
  /** 回复目标作者名（当回复的是另一条回复时，显示「回复 @xxx」） */
  replyToAuthor?: string | null
}>()

const emit = defineEmits<{
  (e: 'reply', parentId: number): void
  (e: 'deleted', commentId: number): void
  (e: 'count-updated', total: number): void
}>()

const session = useSessionStore()
const interactionStore = useInteractionStore()
const uiStore = useUIStore()
const router = useRouter()
const likeLoading = ref(false)
const deleteDialogVisible = ref(false)

// 从 store 派生 active 态：刷新后仍能保持高亮
const liked = computed(() => interactionStore.likedCommentIds.has(props.comment.id))

// 头像首字母 + 渐变色（与 PostDetail 一致）
const avatarPalettes = [
  'linear-gradient(135deg, #66abff, #007aff)',
  'linear-gradient(135deg, #34c759, #2e8dff)',
  'linear-gradient(135deg, #ff9500, #007aff)',
  'linear-gradient(135deg, #5856d6, #af52de)',
  'linear-gradient(135deg, #d1d1d6, #8e8e93)',
]
const avatarGradient = computed(() => {
  const id = props.comment.user_id
  if (id == null) return avatarPalettes[4]
  return avatarPalettes[id % 5]
})
const authorInitial = computed(() =>
  (props.comment.author || '?').trim().charAt(0).toUpperCase(),
)

function timeAgo(iso?: string | null): string {
  return formatRelative(iso)
}

async function toggleLike() {
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  likeLoading.value = true
  try {
    if (liked.value) {
      const { data } = await unlikeTarget('comment', props.comment.id)
      props.comment.like_count = data.data.like_count
      interactionStore.toggleLikedComment(props.comment.id, false)
    } else {
      const { data } = await likeTarget('comment', props.comment.id)
      props.comment.like_count = data.data.like_count
      interactionStore.toggleLikedComment(props.comment.id, true)
    }
  } catch (error) {
    toast.error((error as Error).message)
  } finally {
    likeLoading.value = false
  }
}

async function confirmDelete() {
  deleteDialogVisible.value = true
}

async function doDelete() {
  deleteDialogVisible.value = false
  try {
    const { data } = await deleteComment(props.postId, props.comment.id)
    toast.success('已删除')
    emit('deleted', props.comment.id)
    // Bug 修复：用后端返回的绝对值覆盖 comment_count
    if (data?.data?.post_comment_count != null) {
      emit('count-updated', data.data.post_comment_count)
    }
  } catch (error) {
    toast.error((error as Error).message)
  }
}

function onReply() {
  emit('reply', props.comment.id)
}

const isAuthor = () => props.comment.user_id != null && props.comment.user_id === session.userId

/** 点击头像 / 昵称跳转到该用户主页 */
function goProfile() {
  if (props.comment.user_id == null) return
  router.push(`/user/${props.comment.user_id}`)
}
</script>

<template>
  <div class="comment-item" :class="{ 'is-reply': isReply }">
    <div class="comment-head">
      <button
        type="button"
        class="comment-avatar"
        :style="comment.author_avatar_url ? {} : { background: avatarGradient }"
        :aria-label="`查看 ${comment.author} 的主页`"
        @click="goProfile"
      >
        <img v-if="comment.author_avatar_url" :src="comment.author_avatar_url" :alt="comment.author" />
        <span v-else>{{ authorInitial }}</span>
      </button>
      <div class="comment-meta">
        <div class="comment-name-row">
          <BadgeIcon :badge="comment.author_badge" :size="13" />
          <b class="comment-author" role="link" tabindex="0" @click="goProfile" @keydown.enter="goProfile">{{ comment.author }}</b>
          <AiStatusBadge :status="comment.ai_status" :reject-reason="comment.reject_reason" />
        </div>
        <span class="comment-time">{{ timeAgo(comment.created_at) }}</span>
      </div>
      <div class="comment-actions">
        <button
          class="action-btn"
          :class="{ 'is-liked': liked }"
          type="button"
          :disabled="likeLoading"
          @click="toggleLike"
        >
          <Icon :name="liked ? 'heart-filled' : 'heart'" :size="13" />
          <span>{{ comment.like_count }}</span>
        </button>
        <button class="action-btn" type="button" @click="onReply">
          <Icon name="message-square" :size="13" />
          <span>回复</span>
        </button>
        <button
          v-if="isAuthor()"
          class="action-btn action-btn--danger"
          type="button"
          @click="confirmDelete"
        >
          <Icon name="trash" :size="13" />
          <span>删除</span>
        </button>
      </div>
    </div>
    <p class="comment-text">
      <span v-if="replyToAuthor" class="reply-to-prefix">回复 @{{ replyToAuthor }}：</span>{{ comment.content }}
    </p>

    <!-- 删除确认弹窗 -->
    <NativeDialog v-model="deleteDialogVisible" title="删除评论" width="380px">
      <p class="dialog-text">确认删除这条评论？删除后不可恢复。</p>
      <template #footer>
        <button class="btn btn-outline" type="button" @click="deleteDialogVisible = false">取消</button>
        <button class="btn btn-danger" type="button" @click="doDelete">删除</button>
      </template>
    </NativeDialog>
  </div>
</template>

<style scoped>
.comment-item {
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--bg-100);
  margin-bottom: 6px;
}
.comment-item.is-reply {
  margin-left: 38px;
  background: var(--bg-50);
  border: 0.5px solid var(--color-border);
}
.comment-head {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.comment-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  overflow: hidden;
  border: none;
  padding: 0;
  background: transparent;
  cursor: pointer;
}
.comment-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.comment-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.comment-name-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.comment-author {
  font-size: 13px;
  color: var(--text-800);
  cursor: pointer;
  transition: color 0.15s var(--ease-apple);
}
.comment-author:hover {
  color: var(--brand-500);
}
.comment-time {
  font-size: 11px;
  color: var(--text-500);
}
.comment-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  background: transparent;
  border: none;
  font-family: inherit;
  font-size: 12px;
  color: var(--text-500);
  cursor: pointer;
  transition: all 0.15s var(--ease-apple);
}
.action-btn:hover:not(:disabled) {
  background: var(--bg-200);
  color: var(--text-800);
}
.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.action-btn.is-liked {
  color: var(--error);
}
.action-btn--danger {
  color: var(--text-500);
}
.action-btn--danger:hover:not(:disabled) {
  color: var(--error);
  background: rgba(255, 59, 48, 0.08);
}
.comment-text {
  margin: 6px 0 0;
  padding-left: 36px;
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--text-800);
  word-break: break-word;
  white-space: pre-wrap;
}
.reply-to-prefix {
  color: var(--brand-500);
  font-weight: 600;
  margin-right: 2px;
}

.dialog-text {
  margin: 0;
  font-size: 14px;
  color: var(--text-800);
  line-height: 1.5;
}
</style>
