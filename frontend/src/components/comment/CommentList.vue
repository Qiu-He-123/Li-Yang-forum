<script setup lang="ts">
/**
 * 评论列表（原生组件，替代 Element Plus）
 * - 一级评论 + 二级回复分组展示
 * - 底部评论输入框 + 行内回复输入框
 * - 加载更多分页
 */
import { computed, onUnmounted, ref, watch } from 'vue'

import { Icon } from '../native'
import { toast } from '../native/Toast'
import CommentItem from './CommentItem.vue'
import { listComments, createComment } from '../../api/comment'
import { useSessionStore } from '../../stores/session'
import { useUIStore } from '../../stores/ui'
import type { CommentItem as CommentItemType } from '../../types/api'

const props = defineProps<{
  postId: number
  commentCount: number
}>()

const emit = defineEmits<{
  (e: 'count-updated', total: number): void
}>()

const session = useSessionStore()
const uiStore = useUIStore()
const comments = ref<CommentItemType[]>([])
const loading = ref(false)
const draft = ref('')
const replyTo = ref<number | null>(null)
const replyDraft = ref('')
const submitting = ref(false)
// 评论分页状态，支持「加载更多」
const currentPage = ref(1)
const pageSize = 20
const total = ref(0)
const loadingMore = ref(false)

const hasMore = computed(() => comments.value.length < total.value)

// 是否存在 AI 审核中的评论（用于驱动轮询刷新）
const hasPendingAudit = computed(() => comments.value.some((c) => c.ai_status === 'pending'))

async function load(silent = false) {
  if (!silent) loading.value = true
  // 重置分页
  currentPage.value = 1
  // 记录当前 postId，用于忽略过期请求的响应
  const currentPostId = props.postId
  try {
    const { data } = await listComments(
      props.postId,
      1,
      pageSize,
      silent ? { showGlobalLoading: false, showGlobalError: false } : {},
    )
    // 如果在请求期间 postId 已变化，丢弃本次响应
    if (currentPostId !== props.postId) return
    const list = data?.data?.items
    // 防御性处理：确保一定是数组
    comments.value = Array.isArray(list) ? list : []
    total.value = data?.data?.total ?? comments.value.length
  } catch (error) {
    if (currentPostId !== props.postId) return
    if (!silent) toast.error((error as Error).message)
  } finally {
    if (currentPostId === props.postId) {
      loading.value = false
    }
  }
}

// AI 审核状态轮询：仅当存在 pending 评论时，每 6 秒静默刷新
let auditPollTimer: ReturnType<typeof setInterval> | null = null
const AUDIT_POLL_INTERVAL = 6000

function stopAuditPolling() {
  if (auditPollTimer) {
    clearInterval(auditPollTimer)
    auditPollTimer = null
  }
}

function startAuditPollingIfNeeded() {
  if (!hasPendingAudit.value) {
    stopAuditPolling()
    return
  }
  if (auditPollTimer) return
  auditPollTimer = setInterval(async () => {
    if (hasPendingAudit.value) {
      await load(true)
    } else {
      stopAuditPolling()
    }
  }, AUDIT_POLL_INTERVAL)
}

watch(hasPendingAudit, (has) => {
  if (has) startAuditPollingIfNeeded()
  else stopAuditPolling()
})

onUnmounted(() => {
  stopAuditPolling()
})

async function loadMore() {
  if (loadingMore.value || !hasMore.value) return
  loadingMore.value = true
  try {
    const nextPage = currentPage.value + 1
    const { data } = await listComments(props.postId, nextPage, pageSize)
    const list = data?.data?.items
    if (Array.isArray(list)) {
      comments.value.push(...list)
      currentPage.value = nextPage
    }
  } catch (error) {
    toast.error((error as Error).message)
  } finally {
    loadingMore.value = false
  }
}

watch(
  () => props.postId,
  () => {
    // 切换帖子时立即清空旧评论，避免评论串台
    comments.value = []
    total.value = 0
    currentPage.value = 1
    replyTo.value = null
    replyDraft.value = ''
    draft.value = ''
    load()
  },
  { immediate: true },
)

// 按 parent_id 分层：一级评论 + 各自的所有子孙回复（支持无限层级）
const grouped = computed(() => {
  const roots = comments.value.filter((c) => !c.parent_id)
  // 建立 parent_id -> children 映射
  const childrenMap = new Map<number, CommentItemType[]>()
  for (const c of comments.value) {
    if (c.parent_id != null) {
      const arr = childrenMap.get(c.parent_id) || []
      arr.push(c)
      childrenMap.set(c.parent_id, arr)
    }
  }
  // 递归收集所有子孙
  function collectDescendants(parentId: number): CommentItemType[] {
    const result: CommentItemType[] = []
    for (const child of childrenMap.get(parentId) || []) {
      result.push(child)
      result.push(...collectDescendants(child.id))
    }
    return result
  }
  return roots.map((root) => ({
    root,
    replies: collectDescendants(root.id),
  }))
})

// 构建评论 id -> author 映射，用于显示「回复 @xxx」
const commentAuthorMap = computed(() => {
  const m = new Map<number, string>()
  for (const c of comments.value) {
    m.set(c.id, c.author)
  }
  return m
})

async function submit() {
  const content = draft.value.trim()
  if (!content) {
    toast.error('评论不能为空')
    return
  }
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  // 邀请码系统：未认证用户做评论操作时弹邀请码框
  if (!session.isVerified()) {
    uiStore.openInviteCodeDialog()
    return
  }
  try {
    submitting.value = true
    const { data } = await createComment(props.postId, { content })
    draft.value = ''
    await load()
    emit('count-updated', data.data.post_comment_count)
  } catch (error) {
    toast.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

function startReply(parentId: number) {
  replyTo.value = parentId
  replyDraft.value = ''
}

function cancelReply() {
  replyTo.value = null
  replyDraft.value = ''
}

/** 判断 replyTo 目标是否属于当前楼层（根评论或其子孙回复） */
function isReplyInGroup(group: { root: CommentItemType; replies: CommentItemType[] }, targetId: number): boolean {
  if (group.root.id === targetId) return true
  return group.replies.some((r) => r.id === targetId)
}

/** 获取回复目标的名字（用于输入框 placeholder） */
function getReplyTargetName(targetId: number): string {
  return commentAuthorMap.value.get(targetId) || '同学'
}

async function submitReply(parentId: number) {
  const content = replyDraft.value.trim()
  if (!content) {
    toast.error('回复不能为空')
    return
  }
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  // 邀请码系统：未认证用户做回复操作时弹邀请码框
  if (!session.isVerified()) {
    uiStore.openInviteCodeDialog()
    return
  }
  try {
    const { data } = await createComment(props.postId, { content, parent_id: parentId })
    replyDraft.value = ''
    replyTo.value = null
    await load()
    emit('count-updated', data.data.post_comment_count)
  } catch (error) {
    toast.error((error as Error).message)
  }
}

function onDeleted(_commentId: number) {
  // 重新加载以同步层级结构
  load()
}

function onCountUpdated(totalCount: number) {
  emit('count-updated', totalCount)
}
</script>

<template>
  <div class="comment-list">
    <!-- 加载中 -->
    <div v-if="loading" class="loading-tip">
      <Icon name="refresh" :size="18" />
      <span>加载中…</span>
    </div>

    <template v-else>
      <!-- 评论分组 -->
      <div v-for="group in grouped" :key="group.root.id" class="comment-group">
        <CommentItem
          :comment="group.root"
          :post-id="postId"
          :reply-to-author="null"
          @reply="startReply"
          @deleted="onDeleted"
          @count-updated="onCountUpdated"
        />
        <CommentItem
          v-for="reply in group.replies"
          :key="reply.id"
          :comment="reply"
          :post-id="postId"
          is-reply
          :reply-to-author="reply.parent_id === group.root.id ? null : (commentAuthorMap.get(reply.parent_id!) || null)"
          @reply="startReply"
          @deleted="onDeleted"
          @count-updated="onCountUpdated"
        />
        <!-- 行内回复输入框：对当前楼层内任意评论回复时显示 -->
        <div v-if="replyTo !== null && isReplyInGroup(group, replyTo)" class="reply-input">
          <input
            v-model="replyDraft"
            class="reply-input-field"
            type="text"
            :placeholder="`回复 @${getReplyTargetName(replyTo)}…`"
            @keyup.enter="submitReply(replyTo)"
          />
          <button class="btn btn-primary btn-sm" type="button" @click="submitReply(replyTo)">发送</button>
          <button class="btn btn-ghost btn-sm" type="button" @click="cancelReply">取消</button>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="!comments.length" class="empty-tip">暂无评论</div>

      <!-- 加载更多 -->
      <div v-if="hasMore" class="load-more">
        <button class="btn-text" type="button" :disabled="loadingMore" @click="loadMore">
          {{ loadingMore ? '加载中…' : `加载更多（剩余 ${total - comments.length} 条）` }}
        </button>
      </div>
    </template>

    <!-- 占位：为固定底部输入框腾出空间，避免最后的内容被遮挡 -->
    <div class="comment-input-placeholder"></div>

    <!-- 底部评论输入框（固定在视口底部，TabBar 上方） -->
    <div class="comment-input">
      <button v-if="!session.userId" class="comment-guest-btn" type="button" @click="uiStore.openAuthDialog()">
        <Icon name="log-in" :size="15" />
        登录后参与评论
      </button>
      <template v-else>
        <input
          v-model="draft"
          class="comment-input-field"
          type="text"
          placeholder="写评论…"
          :disabled="submitting"
          @keyup.enter="submit"
        />
        <button class="btn btn-primary btn-sm" type="button" :disabled="submitting" @click="submit">
          {{ submitting ? '发送中…' : '发送' }}
        </button>
      </template>
    </div>
  </div>
</template>

<style scoped>
.comment-list {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 0.5px solid var(--color-border);
}
.loading-tip,
.empty-tip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 16px;
  color: var(--text-500);
  font-size: 13px;
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
.comment-group {
  margin-bottom: 4px;
}
.reply-input {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 4px 0 8px 38px;
}
.reply-input-field,
.comment-input-field {
  flex: 1;
  min-width: 0;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border);
  background: var(--bg-50);
  font-size: 13px;
  color: var(--text-800);
  outline: none;
  font-family: inherit;
  transition: border-color 0.15s var(--ease-apple), box-shadow 0.15s var(--ease-apple);
}
.reply-input-field:focus,
.comment-input-field:focus {
  border-color: var(--brand-500);
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.12);
}
.reply-input-field:disabled,
.comment-input-field:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.load-more {
  text-align: center;
  padding: 10px;
}
.btn-text {
  background: transparent;
  border: none;
  font-family: inherit;
  font-size: 12px;
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

/* 占位元素：高度与固定输入框一致，避免内容被遮挡 */
.comment-input-placeholder {
  height: 56px;
}

/* 底部评论输入框：固定在视口底部，TabBar 上方
   解决"评论越多输入框越靠下"的问题 */
.comment-input {
  position: fixed;
  left: 0;
  right: 0;
  bottom: calc(70px + env(safe-area-inset-bottom));
  z-index: 50;
  display: flex;
  align-items: center;
  gap: 6px;
  max-width: 900px;
  margin: 0 auto;
  padding: 8px 16px;
  background: color-mix(in srgb, var(--bg-50) 92%, transparent);
  -webkit-backdrop-filter: blur(16px);
  backdrop-filter: blur(16px);
  border-top: 0.5px solid var(--bg-300);
  box-shadow: 0 -2px 12px rgba(0, 0, 0, 0.04);
}

/* 游客评论入口 */
.comment-guest-btn {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 38px;
  border-radius: 999px;
  border: 1px dashed var(--brand-300, #7cb8ff);
  background: var(--brand-50);
  color: var(--brand-600);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s;
}
.comment-guest-btn:hover {
  background: var(--brand-100);
}

/* 移动端：TabBar 高度不同，输入框宽度全屏 */
@media (max-width: 768px) {
  .comment-input {
    max-width: 100%;
    /* 移动端 TabBar: calc(52px + env(safe-area-inset-bottom)) */
    bottom: calc(52px + env(safe-area-inset-bottom));
    padding: 8px 12px;
  }
  .comment-input-field {
    font-size: 16px; /* >=16px 防止 iOS 自动缩放 */
  }
}
</style>
