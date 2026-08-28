<script setup lang="ts">
/**
 * 宠物 AI 聊天页（DeepSeek 引擎）
 *
 * - 分段显示：AI 回复按后端拆分的多条消息依次展示（每条独立气泡）
 * - 工具卡片：AI 调用工具时显示居中卡片「[工具] xxx + 结果」
 * - 睡觉状态：宠物睡觉时输入框禁用，顶部显示「睡觉中，预计 X 点醒」
 * - 主动消息：WebSocket 收到 pet_ai_proactive 时自动追加展示
 */
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import { petAiChat, petAiMarkRead, petAiMessages, petAiState, type PetAiChatMessage, type PetAiState } from '../api/petAi'
import { fetchPetProduct, type PetProduct } from '../api/petShop'
import PetAnimation from '../components/pet/PetAnimation.vue'
import { formatTime } from '../utils/time'
import { wsClient, type WsMessage } from '../utils/ws'
import { useSessionStore } from '../stores/session'
import { useUserStore } from '../stores/user'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const userStore = useUserStore()
const petId = computed(() => Number(route.params.petId))

const pet = ref<PetProduct | null>(null)
const messages = ref<PetAiChatMessage[]>([])
const aiState = ref<PetAiState | null>(null)
const loading = ref(false)
const sending = ref(false)
const input = ref('')
const listRef = ref<HTMLDivElement | null>(null)

// 过滤系统发起的触发消息（旧数据兜底）：这些不是用户输入，不应显示成聊天气泡。
function isVisibleChatMessage(m?: PetAiChatMessage | null): boolean {
  if (!m || typeof m.content !== 'string') return false
  const c = m.content.trim()
  if (!c) return false
  // 「系统」「（系统）」等前缀均为系统触发提示，一律不展示
  if (c.startsWith('系统')) return false
  return true
}

// ====== 头像 ======
// 右侧「我」的头像：真实个人头像（未加载/无头像时用占位）
const userAvatar = computed(() => userStore.profile?.avatar_url || '')
// 左侧「宠物」的头像：取宠物帧动画「待机(stand)」首帧，回退商品图
const petAvatarUrl = computed(() => {
  const anim = pet.value?.anim as
    | { actions?: Array<{ key: string; frames?: string[] }> }
    | null
    | undefined
  const stand = anim?.actions?.find((a) => a.key === 'stand')
  const frame = stand?.frames?.[0]
  return frame || pet.value?.image_url || ''
})

// ====== 精力值（由每日 Token 换算成进度条） ======
const energyPercent = computed(() => {
  const limit = aiState.value?.daily_token_limit || 0
  const remaining = aiState.value?.remaining_token ?? aiState.value?.daily_token ?? limit
  if (!limit) return 0
  return Math.max(0, Math.min(100, Math.round((remaining / limit) * 100)))
})

// ====== 加载宠物信息 + 聊天记录 + 状态 ======
async function loadAll() {
  loading.value = true
  try {
    const [petResp, msgResp, stateResp] = await Promise.all([
      fetchPetProduct(petId.value, { showGlobalLoading: false, showGlobalError: false }),
      petAiMessages(petId.value, 50),
      petAiState(petId.value),
    ])
    pet.value = petResp.data.data
    messages.value = (msgResp.data.data.messages || []).filter(isVisibleChatMessage)
    aiState.value = stateResp.data.data
    scrollBottom()
  } catch {
    // 单独兜底：宠物信息失败不阻塞聊天记录
    try {
      const msgResp = await petAiMessages(petId.value, 50)
      messages.value = (msgResp.data.data.messages || []).filter(isVisibleChatMessage)
      scrollBottom()
    } catch { /* ignore */ }
  } finally {
    loading.value = false
  }
}

// ====== 发送 ======
async function onSend() {
  const text = input.value.trim()
  if (!text || sending.value || isSleeping.value) return
  sending.value = true
  // 乐观追加用户消息
  messages.value.push({ role: 'user', content: text, created_at: new Date().toISOString() })
  input.value = ''
  scrollBottom()
  try {
    const { data: resp } = await petAiChat(petId.value, text)
    const result = resp.data
    // 追加 AI 回复（可能含分段 + 工具卡片）：逐条顺延展示，
    // 文本分段间隔明显、工具卡片短间隔，形成"打字机分段"的阅读节奏
    if (result.messages && result.messages.length) {
      const vis = result.messages.filter(isVisibleChatMessage)
      let delay = 0
      for (const m of vis) {
        delay += m.role === 'assistant' ? 1100 : 280
        window.setTimeout(() => {
          messages.value.push(m)
          scrollBottom()
        }, delay)
      }
    }
    aiState.value = result.state || aiState.value
    if (result.skipped) toast.info('宠物这次没有回复')
  } catch (e: any) {
    // 移除乐观消息，避免误导
    messages.value.pop()
    input.value = text
    const msg = e?.response?.data?.msg || e?.message || '发送失败，请稍后再试'
    toast.error(msg)
  } finally {
    sending.value = false
    scrollBottom()
  }
}

// ====== 睡觉状态 ======
const isSleeping = computed(() => !!aiState.value?.sleeping)
const wakeText = computed(() => {
  if (!aiState.value?.wake_at) return ''
  const d = new Date(aiState.value.wake_at)
  if (Number.isNaN(d.getTime())) return ''
  const h = d.getHours()
  const m = d.getMinutes()
  const ampm = h >= 12 ? '下午' : '上午'
  const hh = h % 12 === 0 ? 12 : h % 12
  return `${ampm}${hh}点${m ? ` ${m}分` : ''}醒`
})

// ====== WebSocket 主动消息 ======
// wsClient.on 收到的已是解析后的消息对象（WsMessage）
function onWsMessage(msg: WsMessage) {
  if (msg?.type === 'pet_ai_proactive' && Number(msg.pet_id) === petId.value) {
    const list = ((msg.messages as PetAiChatMessage[] | undefined) || []).filter(isVisibleChatMessage)
    if (list.length) {
      messages.value.push(...list)
      scrollBottom()
    }
    if (msg.state) aiState.value = msg.state as PetAiState
    // 主动消息实时展示在当前聊天页 → 即刻标记已读，避免"聊完返回消息中心仍有红点、需再点进去"
    void petAiMarkRead(petId.value)
    toast.info(`${(msg.pet_name as string) || '小宠物'} 来找你啦`)
  }
}

// 保存取消订阅函数，组件卸载时移除
let wsOff: (() => void) | null = null

// ====== 滚动到底部 ======
async function scrollBottom() {
  await nextTick()
  if (listRef.value) {
    listRef.value.scrollTop = listRef.value.scrollHeight
  }
}

// ====== 工具卡片文案 ======
const TOOL_LABELS: Record<string, string> = {
  give_coins: '赠送金币',
  increase_affinity: '增加好感度',
  decrease_affinity: '减少好感度',
  no_reply: '不回复',
  query_chat_history: '查询聊天记录',
  query_posts: '查询帖子',
  sleep: '睡觉',
}
function toolLabel(msg: PetAiChatMessage): string {
  const t = msg.meta?.tool || ''
  return TOOL_LABELS[t] || t || '工具'
}

onMounted(() => {
  loadAll()
  // 加载个人资料以展示真实头像（未登录时静默忽略）
  if (session.userId) void userStore.loadProfile()
  wsOff = wsClient.on(onWsMessage)
  // 聊天页停留时上报一次「看宠物详情」动作（AI 上下文）
  // 注：动作上报由全局事件追踪统一处理，这里不重复上报
})

onBeforeUnmount(() => {
  if (wsOff) wsOff()
})

function onBack() {
  if (window.history.length > 1) router.back()
  else router.push('/pet-shop/my')
}

watch(() => route.params.petId, () => loadAll())
</script>

<template>
  <div class="pet-chat page">
    <!-- 顶栏 -->
    <header class="chat-header">
      <button class="back-btn" aria-label="返回" @click="onBack">
        <Icon name="chevron-left" :size="26" />
      </button>
      <div class="header-pet">
        <PetAnimation v-if="pet?.anim" :anim="pet.anim" :size="44" :interactive="false" :show-tabs="false" />
        <span v-else class="header-emoji">🐾</span>
      </div>
      <div class="header-info">
        <div class="header-name">
          <template v-if="sending">宠物正在输入中<span class="typing-ellipsis">…</span></template>
          <template v-else>{{ pet?.name || '小宠物' }}</template>
        </div>
        <div class="header-sub">
          <template v-if="isSleeping">
            <span class="sleep-dot">💤</span> 睡觉中，预计 {{ wakeText || '稍后' }}醒
          </template>
          <template v-else-if="aiState?.warn_mode">
            <span class="warn-dot">🌙</span> 有点困了…
          </template>
          <template v-else>
            <span class="online-dot"></span> 在线
          </template>
        </div>
      </div>
      <div class="header-energy" v-if="aiState && aiState.daily_token_limit > 0">
        <div class="energy-row">
          <span class="energy-label">宠物精力值</span>
        </div>
        <div class="energy-bar">
          <div
            class="energy-fill"
            :class="{ low: energyPercent <= 20, warn: aiState.warn_mode }"
            :style="{ width: energyPercent + '%' }"
          ></div>
        </div>
      </div>
    </header>

    <!-- 消息区 -->
    <div ref="listRef" class="msg-list" :class="{ 'is-sleeping': isSleeping }">
      <div v-if="loading && !messages.length" class="loading-tip">加载中…</div>
      <div v-else-if="!messages.length" class="empty-tip">
        <div class="empty-emoji">💬</div>
        <p>和 {{ pet?.name || '小宠物' }} 聊聊天吧～</p>
      </div>

      <template v-for="(msg, idx) in messages" :key="idx">
        <!-- 工具卡片：居中展示 -->
        <div v-if="msg.role === 'tool'" class="tool-card">
          <div class="tool-name">🛠️ {{ toolLabel(msg) }}</div>
          <div v-if="msg.meta?.result" class="tool-result">{{ msg.meta.result }}</div>
        </div>

        <!-- AI 消息：左侧（真实宠物头像） -->
        <div v-else-if="msg.role === 'assistant'" class="msg-row msg-ai">
          <div class="avatar avatar-ai" :style="petAvatarUrl ? { backgroundImage: `url(${petAvatarUrl})` } : {}">
            <span v-if="!petAvatarUrl">🐾</span>
          </div>
          <div class="bubble-wrap">
            <div class="bubble bubble-ai" :class="{ 'forced-sleep': msg.meta?.forced_sleep }">
              {{ msg.content }}
            </div>
            <div v-if="msg.created_at" class="msg-time">{{ formatTime(msg.created_at) }}</div>
          </div>
        </div>

        <!-- 用户消息：右侧（真实个人头像） -->
        <div v-else-if="msg.role === 'user'" class="msg-row msg-me">
          <div class="bubble-wrap bubble-wrap-me">
            <div class="bubble bubble-me">{{ msg.content }}</div>
            <div v-if="msg.created_at" class="msg-time msg-time-me">{{ formatTime(msg.created_at) }}</div>
          </div>
          <div class="avatar avatar-me" :style="userAvatar ? { backgroundImage: `url(${userAvatar})` } : {}">
            <span v-if="!userAvatar">🙂</span>
          </div>
        </div>
      </template>

      <!-- 输入中占位 -->
      <div v-if="sending" class="msg-row msg-ai">
        <div class="avatar avatar-ai" :style="petAvatarUrl ? { backgroundImage: `url(${petAvatarUrl})` } : {}">
          <span v-if="!petAvatarUrl">🐾</span>
        </div>
        <div class="bubble bubble-ai typing"><span></span><span></span><span></span></div>
      </div>
    </div>

    <!-- 睡觉提示条 -->
    <div v-if="isSleeping" class="sleep-bar">
      💤 宠物正在睡觉，预计 {{ wakeText || '稍后' }} 醒，醒了再来找它吧
    </div>

    <!-- 输入区：data-pet-ground 让桌面漂浮宠以输入框顶边为"地面"（聊天页无底部导航栏） -->
    <footer class="input-bar" data-pet-ground :class="{ disabled: isSleeping }">
      <div class="input-wrap">
        <textarea
          v-model="input"
          :placeholder="isSleeping ? '宠物在睡觉…' : '说点什么…'"
          :disabled="isSleeping"
          rows="1"
          @keydown.enter.exact.prevent="onSend"
        ></textarea>
      </div>
      <button class="send-btn" :disabled="isSleeping || !input.trim() || sending" @click="onSend">
        <Icon name="arrow-up" :size="18" />
      </button>
    </footer>
  </div>
</template>

<style scoped>
.pet-chat {
  display: flex;
  flex-direction: column;
  height: 100dvh;
  background: #f6f7f9;
  max-width: 640px;
  margin: 0 auto;
}

/* ===== 顶栏 ===== */
.chat-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--color-border);
  position: sticky;
  top: 0;
  z-index: 10;
}
.back-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  background: transparent;
  color: var(--color-text);
  border-radius: 50%;
}
.back-btn:active { background: rgba(0, 0, 0, 0.06); }
.header-pet {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: #fff;
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}
.header-emoji { font-size: 24px; }
.header-info { flex: 1; min-width: 0; }
.header-name {
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.typing-ellipsis {
  display: inline-block;
  animation: typingBlink 1.2s steps(2, end) infinite;
}
@keyframes typingBlink {
  0%, 100% { opacity: 0.25; }
  50% { opacity: 1; }
}
.header-sub {
  font-size: 12px;
  color: #8e8e93;
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 1px;
}
.online-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--success);
  display: inline-block;
}
.sleep-dot { font-size: 12px; }
.warn-dot { font-size: 12px; }
/* 精力值进度条 */
.header-energy {
  min-width: 104px;
  padding: 5px 8px;
  background: #f1f3f5;
  border-radius: 10px;
}
.energy-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  margin-bottom: 4px;
}
.energy-label { font-size: 10px; color: #8e8e93; white-space: nowrap; }
.energy-val { font-size: 11px; font-weight: 700; color: var(--color-ring); white-space: nowrap; }
.energy-bar {
  height: 6px;
  border-radius: 999px;
  background: #e5e7eb;
  overflow: hidden;
}
.energy-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #34c759, #30d158);
  transition: width 0.4s ease;
}
.energy-fill.warn { background: linear-gradient(90deg, #ffcc00, #ffb300); }
.energy-fill.low { background: linear-gradient(90deg, #ff3b30, #ff6961); }

/* ===== 消息区 ===== */
.msg-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.msg-list::-webkit-scrollbar { width: 0; }
.loading-tip, .empty-tip {
  text-align: center;
  color: #8e8e93;
  font-size: 13px;
  padding: 40px 0;
}
.empty-emoji { font-size: 40px; margin-bottom: 8px; }

.msg-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.msg-row.msg-me { justify-content: flex-end; }
.avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
  margin-top: 2px;
  background-size: cover;
  background-position: center;
  overflow: hidden;
}
.avatar-ai {
  background: linear-gradient(135deg, #fff7e6, #ffe8cc);
  /* background 简写会重置 background-size/position，需重新声明，否则头像按原图尺寸只显示左上角 */
  background-size: cover;
  background-position: center;
  box-shadow: inset 0 0 0 1px #ffd591;
}
.avatar-me {
  background: linear-gradient(135deg, #e6f4ff, #d1ecff);
  /* 同上：避免 background 简写重置背景缩放/定位 */
  background-size: cover;
  background-position: center;
  box-shadow: inset 0 0 0 1px #91caff;
}
.bubble-wrap { max-width: 74%; }
.bubble-wrap-me { display: flex; flex-direction: column; align-items: flex-end; }
.bubble {
  padding: 10px 14px;
  font-size: 15px;
  line-height: 1.5;
  border-radius: 16px;
  word-break: break-word;
  white-space: pre-wrap;
}
.bubble-ai {
  background: #fff;
  color: var(--color-text);
  border-top-left-radius: 4px;
  box-shadow: var(--shadow-sm);
}
.bubble-me {
  background: linear-gradient(135deg, #007aff, #0a84ff);
  color: #fff;
  border-top-right-radius: 4px;
}
.bubble-ai.forced-sleep {
  background: linear-gradient(135deg, #f1f3f5, #e9ecef);
  color: #6b7280;
}
.msg-time {
  font-size: 11px;
  color: #b0b0b5;
  margin-top: 4px;
}
.msg-time-me { text-align: right; }

/* 输入中动画 */
.typing { display: flex; gap: 4px; padding: 14px 16px; }
.typing span {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: #c7c7cc;
  animation: typing-bounce 1.2s infinite;
}
.typing span:nth-child(2) { animation-delay: 0.15s; }
.typing span:nth-child(3) { animation-delay: 0.3s; }
@keyframes typing-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.5; }
  30% { transform: translateY(-5px); opacity: 1; }
}

/* 工具卡片 */
.tool-card {
  align-self: center;
  max-width: 82%;
  background: rgba(255, 255, 255, 0.9);
  border: 1px dashed #d0d0d5;
  border-radius: 12px;
  padding: 8px 14px;
  font-size: 13px;
  color: #6b7280;
  text-align: center;
}
.tool-name { font-weight: 600; color: #495057; }
.tool-result {
  margin-top: 4px;
  font-size: 12px;
  color: #8e8e93;
}

/* ===== 睡觉提示 / 输入区 ===== */
.sleep-bar {
  margin: 0 12px 8px;
  padding: 8px 12px;
  background: #fff3e0;
  color: #b26a00;
  font-size: 13px;
  border-radius: 12px;
  text-align: center;
}
.input-bar {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 10px 12px;
  padding-bottom: calc(10px + env(safe-area-inset-bottom));
  background: rgba(255, 255, 255, 0.96);
  border-top: 1px solid var(--color-border);
}
.input-wrap {
  flex: 1;
  background: #f1f3f5;
  border-radius: 20px;
  padding: 8px 14px;
}
.input-wrap textarea {
  width: 100%;
  border: none;
  outline: none;
  background: transparent;
  font-size: 15px;
  font-family: inherit;
  resize: none;
  max-height: 96px;
  color: var(--color-text);
}
.input-wrap textarea::placeholder { color: #b0b0b5; }
.input-bar.disabled .input-wrap { opacity: 0.6; }
.send-btn {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: none;
  background: var(--color-ring);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: transform 0.15s var(--ease-apple);
}
.send-btn:active { transform: scale(0.92); }
.send-btn:disabled { background: #c7c7cc; }
</style>
