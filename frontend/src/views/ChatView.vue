<script setup lang="ts">
/**
 * 聊天页（抖音/快手风格重构）
 *
 * 适配互关 + 陌生人消息权限：
 * - 互关用户：自由发送
 * - 非互关用户：受接收方 message_permission 控制
 *   - everyone       所有人可发
 *   - mutual_only    仅互关可发（禁用输入，提示「对方仅接受互关用户的消息」）
 *   - stranger_once  陌生人每天 1 条
 *   - no_stranger    不接受陌生人消息（禁用输入，提示「对方不接受陌生人消息」）
 *
 * 重构说明：
 * - 不再依赖 listFriends（好友列表），改为 fetchUser 加载对方资料
 * - 从 get_messages 响应读取 can_send / is_mutual / remaining_today
 * - 输入框根据权限禁用，并显示提示
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import EmptyState from '../components/common/EmptyState.vue'
import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import { fetchUser } from '../api/user'
import { getMessages, sendMessage } from '../api/friend'
import { isSilentRequestError } from '../api/http'
import { useSessionStore } from '../stores/session'
import { useUserStore } from '../stores/user'
import { wsClient } from '../utils/ws'
import type { Profile } from '../types/api'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const userStore = useUserStore()

// 键盘高度（visualViewport API：当软键盘弹起，visualViewport.height < window.innerHeight）
const keyboardHeight = ref(0)

function onVisualViewportResize() {
  const vv = window.visualViewport
  if (!vv) return
  const kh = Math.max(0, window.innerHeight - vv.height - vv.offsetTop)
  keyboardHeight.value = kh
}

interface ChatMessage {
  id: number
  sender_id: number
  content: string
  msg_type: string
  created_at: string | null
}

const friendId = computed(() => Number(route.params.id))
const friend = ref<Profile | null>(null)
const displayFriendName = computed(() => friend.value?.nickname || `用户 ${friendId.value || ''}`.trim())
const displayFriendInitial = computed(() => (displayFriendName.value || '?').charAt(0).toUpperCase())
const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const loading = ref(false)
const sending = ref(false)
const messagesContainer = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLInputElement | null>(null)

// 权限状态
const isMutual = ref(false)
const canSend = ref(true)
const canSendReason = ref('')
const remainingToday = ref(-1) // -1 表示无限制
const otherPermission = ref<string>('stranger_once')

// 轮询新消息（大厂方案：WebSocket 实时推送 + 轮询兜底）
let pollTimer: ReturnType<typeof setInterval> | null = null
// 上一次消息列表指纹，避免无变化时的重渲染（防闪烁）
let lastMsgFingerprint = ''
// 是否在底部（用于判断收到新消息时是否自动滚动）
const isNearBottom = ref(true)

async function loadFriendInfo() {
  if (!friendId.value) return
  try {
    const { data } = await fetchUser(friendId.value, {
      showGlobalLoading: false,
      showGlobalError: false,
    })
    friend.value = data.data
  } catch (err) {
    if (isSilentRequestError(err)) return
    toast.error((err as Error).message)
  }
}

/** 生成消息列表指纹：仅包含影响 UI 的关键字段 */
function buildMsgFingerprint(list: ChatMessage[]): string {
  return list.map((m) => `${m.id}:${m.content}:${m.created_at || ''}`).join('|')
}

/** 检查是否在底部附近（用于判断收到新消息时是否自动滚动） */
function checkNearBottom() {
  const el = messagesContainer.value
  if (!el) return
  isNearBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 100
}

/** 初始加载（显示 loading 动画） */
async function loadMessagesInitial() {
  if (!friendId.value) return
  loading.value = true
  try {
    const { data } = await getMessages(friendId.value, 1, 30, {
      showGlobalLoading: false,
      showGlobalError: false,
    })
    const payload = data.data
    const next = payload.items || []
    messages.value = next
    lastMsgFingerprint = buildMsgFingerprint(next)
    isMutual.value = payload.is_mutual ?? false
    canSend.value = payload.can_send ?? true
    canSendReason.value = payload.can_send_reason ?? ''
    remainingToday.value = payload.remaining_today ?? -1
    otherPermission.value = payload.other_message_permission ?? 'stranger_once'
    await nextTick()
    scrollToBottom()
  } catch (err) {
    if (isSilentRequestError(err)) return
    toast.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

/** 增量轮询：不显示 loading，仅在有变化时更新（防闪烁） */
async function pollMessages() {
  if (!friendId.value) return
  try {
    const { data } = await getMessages(friendId.value, 1, 30, {
      showGlobalLoading: false,
      showGlobalError: false,
    })
    const payload = data.data
    const next = payload.items || []
    const fp = buildMsgFingerprint(next)
    // 仅在指纹变化时更新，避免无变化重渲染导致的闪烁
    if (fp !== lastMsgFingerprint) {
      const wasNearBottom = isNearBottom.value
      messages.value = next
      lastMsgFingerprint = fp
      // 仅在用户在底部附近时自动滚动（避免用户正在查看历史消息时被强制拉到底部）
      if (wasNearBottom) {
        await nextTick()
        scrollToBottom()
      }
    }
    // 同步权限状态（可能有变化）
    isMutual.value = payload.is_mutual ?? false
    canSend.value = payload.can_send ?? true
    canSendReason.value = payload.can_send_reason ?? ''
    remainingToday.value = payload.remaining_today ?? -1
    otherPermission.value = payload.other_message_permission ?? 'stranger_once'
  } catch {
    // 轮询失败静默处理，不打断用户
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

async function onSend() {
  const text = inputText.value.trim()
  if (!text || sending.value || !canSend.value) return
  sending.value = true
  const sentText = text
  inputText.value = ''
  try {
    const { data } = await sendMessage(friendId.value, sentText)
    const msg = data.data
    // 乐观更新：直接 push 到列表，不重新拉取整个列表
    messages.value.push({
      id: msg.id,
      sender_id: msg.sender_id,
      content: msg.content,
      msg_type: msg.msg_type,
      created_at: msg.created_at,
    })
    lastMsgFingerprint = buildMsgFingerprint(messages.value)
    await nextTick()
    scrollToBottom()
    inputRef.value?.focus()
    // 仅更新权限状态（stranger_once 模式下次数可能减少），不重新拉消息列表
    remainingToday.value = msg.remaining_today ?? remainingToday.value
    if (msg.is_mutual !== undefined) isMutual.value = msg.is_mutual
  } catch (err) {
    toast.error((err as Error).message)
    // 还原输入内容，方便用户复制
    inputText.value = sentText
    // 发送失败时仅更新权限状态，不重新拉取整个列表
    await pollMessages()
  } finally {
    sending.value = false
  }
}

/** WebSocket 消息处理器：实时接收对方消息，无需等轮询 */
let wsUnsubscribe: (() => void) | null = null

function setupWsListener() {
  wsUnsubscribe = wsClient.on((msg) => {
    if (msg.type !== 'dm_message') return
    const senderId = msg.sender_id as number
    if (senderId !== friendId.value) return
    const msgId = msg.id as number
    // 去重：避免与轮询结果重复
    if (messages.value.some((m) => m.id === msgId)) return
    messages.value.push({
      id: msgId,
      sender_id: senderId,
      content: msg.content as string,
      msg_type: (msg.msg_type as string) || 'text',
      created_at: msg.created_at as string | null,
    })
    lastMsgFingerprint = buildMsgFingerprint(messages.value)
    if (isNearBottom.value) {
      nextTick(() => scrollToBottom())
    }
  })
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    onSend()
  }
}

function formatTime(dateStr: string | null): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function timeGroup(msg: ChatMessage, idx: number): string {
  if (idx === 0) return formatTime(msg.created_at)
  const prev = messages.value[idx - 1]
  if (!prev?.created_at) return formatTime(msg.created_at)
  const diff = new Date(msg.created_at!).getTime() - new Date(prev.created_at!).getTime()
  if (diff > 5 * 60 * 1000) return formatTime(msg.created_at)
  return ''
}

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

function goBack() {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/notifications')
  }
}

/** 输入框获取焦点（键盘弹起）时，延迟滚动到底部，确保输入框可见 */
function onInputFocus() {
  // 键盘动画大约 300ms，延迟滚动确保输入框不被遮挡
  setTimeout(() => {
    scrollToBottom()
    // 主动触发一次 visualViewport 检测（部分浏览器 focus 时还未触发 resize）
    onVisualViewportResize()
  }, 350)
}

// 输入框 placeholder：根据权限动态显示
const inputPlaceholder = computed(() => {
  if (!canSend.value) return canSendReason.value || '无法发送消息'
  if (isMutual.value) return '输入消息…'
  // 双向对话已破冰（remaining_today === -1 表示无限制）
  if (remainingToday.value === -1) return '输入消息…'
  if (remainingToday.value === 1) return '今日还可发送 1 条消息…'
  if (remainingToday.value === 0) return '今日发送次数已用完'
  return '输入消息…'
})

// 顶部副标题：显示关系
const headerSubtitle = computed(() => {
  if (isMutual.value) return '互相关注'
  if (!canSend.value) return canSendReason.value
  // 双向对话破冰后显示「已破冰」
  if (remainingToday.value === -1) return '今日已破冰 · 可自由发送'
  if (otherPermission.value === 'stranger_once') {
    return remainingToday.value > 0 ? `陌生人 · 今日还可发 ${remainingToday.value} 条` : '陌生人 · 今日次数已用完'
  }
  if (otherPermission.value === 'everyone') return '所有人可发'
  return '陌生人'
})

/** 页面可见性变化：标签页隐藏时暂停轮询，可见时立即拉取一次补漏 */
function onVisibilityChange() {
  if (document.hidden) {
    // 标签页隐藏：暂停轮询，节省请求
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  } else {
    // 标签页重新可见：立即拉取一次（补漏隐藏期间可能错过的消息），再恢复轮询
    pollMessages()
    if (!pollTimer) {
      // 轮询兜底：10 秒间隔（WebSocket 实时推送为主，轮询为辅）
      pollTimer = setInterval(pollMessages, 10000)
    }
  }
}

onMounted(async () => {
  const valid = await session.validateSession()
  if (!valid) return
  if (!userStore.profile) await userStore.loadProfile()
  await loadFriendInfo()
  await loadMessagesInitial()
  // 轮询兜底：10 秒间隔（WebSocket 实时推送为主，轮询为辅，减少闪烁）
  pollTimer = setInterval(pollMessages, 10000)
  // WebSocket 实时推送监听
  setupWsListener()
  // 监听滚动：判断用户是否在底部附近（决定收到新消息时是否自动滚动）
  messagesContainer.value?.addEventListener('scroll', checkNearBottom)
  // 监听软键盘弹起/收起（visualViewport API）
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', onVisualViewportResize)
    window.visualViewport.addEventListener('scroll', onVisualViewportResize)
  }
  // 监听页面可见性：隐藏时暂停轮询，可见时补漏
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (wsUnsubscribe) wsUnsubscribe()
  messagesContainer.value?.removeEventListener('scroll', checkNearBottom)
  if (window.visualViewport) {
    window.visualViewport.removeEventListener('resize', onVisualViewportResize)
    window.visualViewport.removeEventListener('scroll', onVisualViewportResize)
  }
  document.removeEventListener('visibilitychange', onVisibilityChange)
})

watch(friendId, async () => {
  await loadFriendInfo()
  await loadMessagesInitial()
})
</script>

<template>
  <div class="chat-page">
    <!-- 顶部栏 -->
    <header class="chat-header">
      <button class="back-btn" type="button" @click="goBack">
        <Icon name="arrow-left" :size="20" />
      </button>
      <div class="chat-header-info" @click="friend && router.push(`/user/${friend.id}`)">
        <div
          class="chat-avatar"
          :style="
            friend?.avatar_url
              ? { backgroundImage: `url(${friend.avatar_url})` }
              : { background: avatarGradient(friend?.id) }
          "
        >
          <span v-if="!friend?.avatar_url">{{ displayFriendInitial }}</span>
        </div>
        <div class="chat-name-wrap">
          <span class="chat-name">{{ displayFriendName }}</span>
          <span class="chat-subtitle" :class="{ 'is-mutual': isMutual, 'is-blocked': !canSend }">
            {{ headerSubtitle }}
          </span>
        </div>
      </div>
      <span class="more-btn-placeholder" />
    </header>

    <!-- 消息列表 -->
    <div ref="messagesContainer" class="chat-messages">
      <div v-if="loading" class="chat-loading">加载中…</div>
      <template v-for="(msg, i) in messages" :key="msg.id">
        <div v-if="timeGroup(msg, i)" class="chat-time-divider">
          <span>{{ timeGroup(msg, i) }}</span>
        </div>
        <div
          class="chat-bubble-row"
          :class="{ 'is-self': msg.sender_id === session.userId }"
        >
          <div
            v-if="msg.sender_id !== session.userId"
            class="chat-avatar chat-avatar-sm"
            :style="
              friend?.avatar_url
                ? { backgroundImage: `url(${friend.avatar_url})` }
                : { background: avatarGradient(friend?.id) }
            "
          >
            <span v-if="!friend?.avatar_url">{{ displayFriendInitial }}</span>
          </div>
          <div class="chat-bubble">
            <span class="chat-text">{{ msg.content }}</span>
          </div>
          <div
            v-if="msg.sender_id === session.userId"
            class="chat-avatar chat-avatar-sm chat-avatar--self"
            :style="
              userStore.profile?.avatar_url
                ? { backgroundImage: `url(${userStore.profile.avatar_url})` }
                : { background: avatarGradient(session.userId) }
            "
          >
            <span v-if="!userStore.profile?.avatar_url">{{ session.nickname?.charAt(0).toUpperCase() || '我' }}</span>
          </div>
        </div>
      </template>
      <EmptyState v-if="!loading && !messages.length" icon="message-circle" text="开始聊天吧" />
    </div>

    <!-- 权限提示条（非互关且不能发消息时） -->
    <div v-if="!canSend" class="chat-perm-banner">
      <Icon name="lock" :size="14" />
      <span>{{ canSendReason || '无法发送消息' }}</span>
    </div>

    <!-- 底部输入区 -->
    <div
      class="chat-input-bar"
      :style="keyboardHeight > 0 ? { paddingBottom: `${keyboardHeight}px` } : {}"
    >
      <div class="chat-input-wrap" :class="{ 'is-disabled': !canSend }">
        <input
          ref="inputRef"
          v-model="inputText"
          class="chat-input"
          type="text"
          :placeholder="inputPlaceholder"
          :disabled="!canSend"
          @keydown="onKeydown"
          @focus="onInputFocus"
        />
      </div>
      <button
        class="chat-send-btn"
        type="button"
        :disabled="!inputText.trim() || sending || !canSend"
        @click="onSend"
      >
        {{ sending ? '发送中' : '发送' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  height: 100dvh;
  background: #ededed;
  /* 防止 iOS Safari 顶部地址栏导致高度异常 */
  height: -webkit-fill-available;
}

/* 顶部栏 */
.chat-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: #ededed;
  border-bottom: 0.5px solid #d9d9d9;
  flex-shrink: 0;
  min-height: 56px;
  padding-top: calc(8px + env(safe-area-inset-top));
}
.back-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: transparent;
  cursor: pointer;
  display: grid;
  place-items: center;
  color: #000;
}
.more-btn-placeholder {
  width: 36px;
  height: 36px;
  display: inline-block;
}
.chat-header-info {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  cursor: pointer;
}
.chat-avatar {
  width: 36px;
  height: 36px;
  border-radius: 6px;
  background: #07c160;
  color: #fff;
  display: grid;
  place-items: center;
  font-size: 14px;
  font-weight: 600;
  flex-shrink: 0;
  background-size: cover;
  background-position: center;
}
.chat-avatar-sm {
  width: 34px;
  height: 34px;
  border-radius: 4px;
  font-size: 13px;
}
.chat-avatar--self {
  background: #1482f0;
}
.chat-name-wrap {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.chat-name {
  font-size: 16px;
  font-weight: 600;
  color: #000;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.chat-subtitle {
  font-size: 11px;
  color: #888;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.chat-subtitle.is-mutual {
  color: #07c160;
  font-weight: 600;
}
.chat-subtitle.is-blocked {
  color: #ff3b30;
}

/* 消息列表 */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.chat-loading {
  text-align: center;
  color: #999;
  font-size: 13px;
  padding: 20px;
}
.chat-time-divider {
  text-align: center;
  padding: 8px 0;
}
.chat-time-divider span {
  font-size: 11px;
  color: #b2b2b2;
  background: #dcdcdc;
  padding: 2px 8px;
  border-radius: 2px;
}

/* 气泡 */
.chat-bubble-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 8px;
}
.chat-bubble-row.is-self {
  justify-content: flex-end;
}
.chat-bubble {
  max-width: 70%;
  padding: 10px 14px;
  border-radius: 4px;
  position: relative;
  word-break: break-word;
}
.chat-bubble-row:not(.is-self) .chat-bubble {
  background: #fff;
  border-radius: 4px 16px 16px 16px;
}
.chat-bubble-row.is-self .chat-bubble {
  background: #95ec69;
  border-radius: 16px 4px 16px 16px;
}
.chat-text {
  font-size: 15px;
  line-height: 1.5;
  color: #000;
}

/* 权限提示条 */
.chat-perm-banner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 16px;
  background: #fff7e6;
  color: #ff9500;
  font-size: 12px;
  border-top: 0.5px solid #ffd591;
  flex-shrink: 0;
}

/* 输入区 */
.chat-input-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  /* 默认底部留出安全区（iPhone X 等的 Home Indicator）；
     键盘弹起时由内联样式覆盖为键盘高度，确保输入框紧贴键盘上方 */
  padding-bottom: calc(8px + env(safe-area-inset-bottom));
  background: #f7f7f7;
  border-top: 0.5px solid #d9d9d9;
  flex-shrink: 0;
  /* 平滑过渡：键盘弹起/收起时输入框向上/向下移动 */
  transition: padding-bottom 0.2s ease;
}
.chat-input-wrap {
  flex: 1;
  background: #fff;
  border-radius: 6px;
  padding: 0 12px;
}
.chat-input-wrap.is-disabled {
  background: #f0f0f0;
}
.chat-input {
  width: 100%;
  border: none;
  outline: none;
  /* ≥16px 防止 iOS Safari 聚焦时自动放大页面 */
  font-size: 16px;
  line-height: 1.5;
  padding: 10px 0;
  background: transparent;
  font-family: inherit;
  color: #000;
}
.chat-input:disabled {
  color: #999;
  cursor: not-allowed;
}
.chat-input::placeholder {
  color: #b2b2b2;
}
.chat-send-btn {
  padding: 8px 18px;
  border: none;
  border-radius: 6px;
  background: #07c160;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  flex-shrink: 0;
  font-family: inherit;
  transition: background 0.15s;
}
.chat-send-btn:disabled {
  background: #c0c0c0;
  cursor: not-allowed;
}

/* 移动端：确保输入框可见，键盘弹起时跟随上移 */
@media (max-width: 768px) {
  .chat-page {
    /* 移动端使用 dvh，键盘弹起时自动收缩可视区域 */
    height: 100dvh;
  }
  .chat-input-bar {
    padding: 6px 10px;
  }
  .chat-input {
    padding: 9px 0;
  }
  .chat-send-btn {
    padding: 8px 16px;
  }
}
</style>
