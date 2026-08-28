<script setup lang="ts">
/**
 * 通用留言板（组局/活动详情页用）
 * - 一级留言 + 嵌套回复（楼层式：先根留言后所有子孙回复）
 * - 底部留言输入框 + 行内回复输入框
 * - 加载更多分页
 */
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'

import { Icon } from '../native'
import { toast } from '../native/Toast'
import {
  createTargetComment,
  deleteTargetComment,
  listTargetComments,
  type TargetCommentItem,
  type TargetType,
} from '../../api/targetComment'
import { useSessionStore } from '../../stores/session'
import { useUIStore } from '../../stores/ui'
import { formatRelative } from '../../utils/time'

const props = defineProps<{
  targetType: TargetType
  targetId: number
  /** 留言总数（可选，用于标题展示；组件内部自行加载） */
  title?: string
}>()

const session = useSessionStore()
const uiStore = useUIStore()

const comments = ref<TargetCommentItem[]>([])
const loading = ref(false)
const draft = ref('')
const replyTo = ref<number | null>(null)
const replyDraft = ref('')
const submitting = ref(false)
const replySubmitting = ref(false)
let replyInputEl: HTMLTextAreaElement | null = null
function setReplyRef(el: unknown) {
  // v-for 场景下 Vue 会传入元素/数组，这里只取当前激活的输入框
  replyInputEl = Array.isArray(el) ? (el[0] as HTMLTextAreaElement | undefined) ?? null : (el as HTMLTextAreaElement | null)
}

const currentPage = ref(1)
const pageSize = 20
const total = ref(0)
const loadingMore = ref(false)
const hasMore = computed(() => comments.value.length < total.value)

/** 由扁平列表构建楼层：根留言 + 各自子孙回复 */
const floors = computed(() => {
  const roots = comments.value.filter((c) => c.parent_id === null)
  const byParent = new Map<number, TargetCommentItem[]>()
  for (const c of comments.value) {
    if (c.parent_id === null) continue
    const arr = byParent.get(c.parent_id) || []
    arr.push(c)
    byParent.set(c.parent_id, arr)
  }
  return roots.map((root) => ({
    root,
    replies: byParent.get(root.id) || [],
  }))
})

/** 回复目标作者名映射（用于「回复 @xxx」展示） */
const authorNameById = computed(() => {
  const map = new Map<number, string>()
  for (const c of comments.value) map.set(c.id, c.author)
  return map
})

async function load(silent = false) {
  if (!silent) loading.value = true
  const currentId = props.targetId
  try {
    const { data } = await listTargetComments(props.targetType, props.targetId, 1, pageSize, {
      showGlobalLoading: false,
      showGlobalError: false,
    })
    if (currentId !== props.targetId) return
    const list = data?.data?.items
    comments.value = Array.isArray(list) ? list : []
    total.value = data?.data?.total ?? comments.value.length
    currentPage.value = 1
  } catch (error) {
    if (currentId === props.targetId && !silent) toast.error((error as Error).message)
  } finally {
    if (currentId === props.targetId) loading.value = false
  }
}

async function loadMore() {
  if (loadingMore.value || !hasMore.value) return
  loadingMore.value = true
  try {
    const nextPage = currentPage.value + 1
    const { data } = await listTargetComments(props.targetType, props.targetId, nextPage, pageSize, {
      showGlobalLoading: false,
      showGlobalError: false,
    })
    const list = data?.data?.items || []
    const ids = new Set(comments.value.map((c) => c.id))
    comments.value = [...comments.value, ...list.filter((c) => !ids.has(c.id))]
    total.value = data?.data?.total ?? total.value
    currentPage.value = nextPage
  } catch (error) {
    toast.error((error as Error).message)
  } finally {
    loadingMore.value = false
  }
}

async function submit() {
  const content = draft.value.trim()
  if (!content) return
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  if (submitting.value) return
  submitting.value = true
  try {
    await createTargetComment(props.targetType, props.targetId, { content })
    draft.value = ''
    toast.success('留言成功')
    await load(true)
  } catch (error) {
    toast.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

function startReply(commentId: number) {
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  // 只在目标消息下方展开回复框（根留言或某个子回复均可）
  replyTo.value = replyTo.value === commentId ? null : commentId
  replyDraft.value = ''
  if (replyTo.value === commentId) {
    void nextTick(() => replyInputEl?.focus())
  }
}

function cancelReply() {
  replyTo.value = null
  replyDraft.value = ''
}

async function submitReply(parentId: number) {
  const content = replyDraft.value.trim()
  if (!content) return
  if (replySubmitting.value) return
  replySubmitting.value = true
  try {
    await createTargetComment(props.targetType, props.targetId, { content, parent_id: parentId })
    replyDraft.value = ''
    cancelReply()
    toast.success('回复成功')
    await load(true)
  } catch (error) {
    const err = error as { response?: { data?: { msg?: string } } }
    const msg = err.response?.data?.msg || (error as Error).message || '回复失败，请稍后再试'
    toast.error(msg)
  } finally {
    replySubmitting.value = false
  }
}

async function onDelete(commentId: number) {
  if (!window.confirm('确定删除该留言吗？（删除根留言会连同其下所有回复一起删除）')) return
  try {
    await deleteTargetComment(props.targetType, props.targetId, commentId)
    toast.success('已删除')
    await load(true)
  } catch (error) {
    toast.error((error as Error).message)
  }
}

function timeAgo(iso?: string | null): string {
  return formatRelative(iso)
}

// 头像占位配色
const avatarPalettes = [
  'linear-gradient(135deg, #66abff, #007aff)',
  'linear-gradient(135deg, #34c759, #2e8dff)',
  'linear-gradient(135deg, #ff9500, #007aff)',
  'linear-gradient(135deg, #5856d6, #af52de)',
  'linear-gradient(135deg, #d1d1d6, #8e8e93)',
]
function avatarGradient(c: TargetCommentItem): string {
  return c.user_id == null ? avatarPalettes[4] : avatarPalettes[c.user_id % 5]
}
function authorInitial(c: TargetCommentItem): string {
  return (c.author || '?').trim().charAt(0).toUpperCase()
}

watch(
  () => [props.targetType, props.targetId],
  () => {
    if (props.targetId) void load()
  },
  { immediate: true },
)

onUnmounted(() => {
  /* nothing to clean */
})
</script>

<template>
  <section class="mb-board">
    <div class="mb-board__title">
      <Icon name="message-circle" :size="16" />
      <span>{{ title || '留言板' }}</span>
      <span class="mb-board__count">{{ total }}</span>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="mb-loading">加载中…</div>

    <!-- 留言列表 -->
    <template v-else>
      <div v-if="floors.length" class="mb-list">
        <div v-for="floor in floors" :key="floor.root.id" class="mb-floor">
          <!-- 根留言 -->
          <div class="mb-item">
            <span class="mb-avatar" :style="{ background: avatarGradient(floor.root) }">
              {{ authorInitial(floor.root) }}
            </span>
            <div class="mb-item__main">
              <div class="mb-item__head">
                <span class="mb-item__author">{{ floor.root.author }}</span>
                <span class="mb-item__time">{{ timeAgo(floor.root.created_at) }}</span>
              </div>
              <p class="mb-item__content">{{ floor.root.content }}</p>
              <div class="mb-item__actions">
                <button class="mb-action-btn" type="button" @click="startReply(floor.root.id)">
                  <Icon name="chevron-left" :size="13" />
                  回复
                </button>
                <button
                  v-if="session.userId && floor.root.user_id === session.userId"
                  class="mb-action-btn mb-action-btn--danger"
                  type="button"
                  @click="onDelete(floor.root.id)"
                >
                  <Icon name="trash" :size="13" />
                  删除
                </button>
              </div>

              <!-- 行内回复输入框（回复根留言：显示在根留言下方） -->
              <div v-if="replyTo === floor.root.id" class="mb-reply-box">
                <textarea
                  :ref="setReplyRef"
                  v-model="replyDraft"
                  class="mb-reply-input"
                  rows="2"
                  maxlength="500"
                  :placeholder="`回复 @${floor.root.author}…`"
                ></textarea>
                <div class="mb-reply-box__foot">
                  <button class="mb-btn mb-btn--ghost" type="button" @click="cancelReply">取消</button>
                  <button
                    class="mb-btn mb-btn--primary"
                    type="button"
                    :disabled="!replyDraft.trim() || replySubmitting"
                    @click="submitReply(floor.root.id)"
                  >
                    {{ replySubmitting ? '发送中…' : '回复' }}
                  </button>
                </div>
              </div>

              <!-- 子回复 -->
              <div v-if="floor.replies.length" class="mb-replies">
                <div v-for="r in floor.replies" :key="r.id" class="mb-item mb-item--reply">
                  <span class="mb-avatar mb-avatar--sm" :style="{ background: avatarGradient(r) }">
                    {{ authorInitial(r) }}
                  </span>
                  <div class="mb-item__main">
                    <div class="mb-item__head">
                      <span class="mb-item__author">{{ r.author }}</span>
                      <span v-if="r.parent_id !== null && r.parent_id !== floor.root.id" class="mb-item__replyto">
                        回复 @{{ authorNameById.get(r.parent_id) || '同学' }}
                      </span>
                      <span class="mb-item__time">{{ timeAgo(r.created_at) }}</span>
                    </div>
                    <p class="mb-item__content">{{ r.content }}</p>
                    <div class="mb-item__actions">
                      <button class="mb-action-btn" type="button" @click="startReply(r.id)">
                        <Icon name="chevron-left" :size="13" />
                        回复
                      </button>
                      <button
                        v-if="session.userId && r.user_id === session.userId"
                        class="mb-action-btn mb-action-btn--danger"
                        type="button"
                        @click="onDelete(r.id)"
                      >
                        <Icon name="trash" :size="13" />
                        删除
                      </button>
                    </div>

                    <!-- 回复某条子回复：输入框显示在该条消息下方 -->
                    <div v-if="replyTo === r.id" class="mb-reply-box">
                      <textarea
                        :ref="setReplyRef"
                        v-model="replyDraft"
                        class="mb-reply-input"
                        rows="2"
                        maxlength="500"
                        :placeholder="`回复 @${r.author}…`"
                      ></textarea>
                      <div class="mb-reply-box__foot">
                        <button class="mb-btn mb-btn--ghost" type="button" @click="cancelReply">取消</button>
                        <button
                          class="mb-btn mb-btn--primary"
                          type="button"
                          :disabled="!replyDraft.trim() || replySubmitting"
                          @click="submitReply(r.id)"
                        >
                          {{ replySubmitting ? '发送中…' : '回复' }}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 加载更多 -->
        <button
          v-if="hasMore"
          class="mb-load-more"
          type="button"
          :disabled="loadingMore"
          @click="loadMore"
        >
          {{ loadingMore ? '加载中…' : '加载更多留言' }}
        </button>
      </div>

      <div v-else class="mb-empty">
        <Icon name="message-circle" :size="28" />
        <p>还没有留言，来抢沙发吧～</p>
      </div>
    </template>

    <!-- 底部留言输入框 -->
    <div class="mb-composer">
      <textarea
        v-model="draft"
        class="mb-composer__input"
        rows="2"
        maxlength="500"
        :placeholder="session.userId ? '写下你的留言…' : '登录后即可留言'"
        @focus="() => { if (!session.userId) uiStore.openAuthDialog() }"
      ></textarea>
      <button
        class="mb-btn mb-btn--primary mb-composer__send"
        type="button"
        :disabled="!draft.trim() || submitting"
        @click="submit"
      >
        {{ submitting ? '发送中…' : '留言' }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.mb-board {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.mb-board__title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-900, #1c1c1e);
}
.mb-board__title :deep(svg) {
  color: var(--brand-500, #0a6cff);
}
.mb-board__count {
  margin-left: 2px;
  padding: 0 8px;
  border-radius: 999px;
  background: var(--bg-100, #f2f2f7);
  color: var(--text-500, #8e8e93);
  font-size: 12px;
  font-weight: 500;
  line-height: 20px;
}

.mb-loading {
  padding: 24px 0;
  text-align: center;
  font-size: 13px;
  color: var(--text-400, #aeaeb2);
}

.mb-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.mb-item {
  display: flex;
  gap: 10px;
}
.mb-avatar {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
}
.mb-avatar--sm {
  width: 28px;
  height: 28px;
  font-size: 12px;
}
.mb-item__main {
  flex: 1;
  min-width: 0;
}
.mb-item__head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}
.mb-item__author {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-800, #3a3a3c);
}
.mb-item__replyto {
  font-size: 12px;
  color: var(--brand-500, #0a6cff);
}
.mb-item__time {
  font-size: 11px;
  color: var(--text-400, #aeaeb2);
}
.mb-item__content {
  margin: 4px 0 6px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-900, #1c1c1e);
  white-space: pre-wrap;
  word-break: break-word;
}
.mb-item__actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.mb-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px 8px;
  border: none;
  background: transparent;
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-500, #8e8e93);
  cursor: pointer;
}
.mb-action-btn:hover {
  background: var(--bg-100, #f2f2f7);
  color: var(--brand-500, #0a6cff);
}
.mb-action-btn--danger:hover {
  background: rgba(255, 59, 48, 0.08);
  color: #ff3b30;
}
.mb-action-btn :deep(svg) {
  width: 13px;
  height: 13px;
}

.mb-replies {
  margin-top: 10px;
  padding: 10px 12px;
  background: var(--bg-100, #f7f8fa);
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.mb-item--reply {
  gap: 8px;
}

.mb-reply-box {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.mb-reply-input,
.mb-composer__input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--bg-300, #e5e5ea);
  border-radius: 10px;
  background: var(--bg-50, #fff);
  font-size: 14px;
  line-height: 1.5;
  color: var(--text-900, #1c1c1e);
  resize: vertical;
  font-family: inherit;
  box-sizing: border-box;
}
.mb-reply-input:focus,
.mb-composer__input:focus {
  outline: none;
  border-color: var(--brand-500, #0a6cff);
}
.mb-reply-box__foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.mb-btn {
  padding: 7px 18px;
  border: none;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.mb-btn--primary {
  background: linear-gradient(135deg, #2b5ae0, #1942c2);
  color: #fff;
}
.mb-btn--primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.mb-btn--ghost {
  background: var(--bg-100, #f2f2f7);
  color: var(--text-600, #5e5e63);
}

.mb-load-more {
  margin: 4px auto 0;
  padding: 8px 20px;
  border: none;
  border-radius: 999px;
  background: var(--bg-100, #f2f2f7);
  color: var(--text-600, #5e5e63);
  font-size: 13px;
  cursor: pointer;
}
.mb-load-more:hover {
  background: var(--bg-200, #e9e9ee);
}

.mb-empty {
  padding: 28px 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: var(--text-400, #aeaeb2);
}
.mb-empty p {
  margin: 0;
  font-size: 13px;
}

.mb-composer {
  margin-top: 4px;
  padding-top: 12px;
  border-top: 0.5px solid var(--bg-200, #e5e5ea);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.mb-composer__send {
  align-self: flex-end;
}
</style>
