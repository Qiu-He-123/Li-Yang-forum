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
import BadgeIcon from '../components/common/BadgeIcon.vue'
import ImageViewer from '../components/common/ImageViewer.vue'
import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import { fetchUser } from '../api/user'
import { getMessages, sendMessage } from '../api/friend'
import { uploadImage, uploadAudio } from '../api/image'
import { isAppEnv, downloadApp } from '../utils/platform'
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
  is_read?: boolean
  read_at?: string | null
  /** 本地上传进度 0-100（上传中），完成后为 100 */
  uploadProgress?: number
  /** 本地语音时长（秒） */
  duration?: number
  /** 本地临时消息（上传中，无服务端 id） */
  isLocal?: boolean
  created_at: string | null
}

const sendingImage = ref(false)
const imageInputRef = ref<HTMLInputElement | null>(null)
const cameraInputRef = ref<HTMLInputElement | null>(null)

// 输入面板状态（微信式）
const inputMode = ref<'keyboard' | 'voice'>('keyboard')
const panelOpen = ref(false)
const panelType = ref<'plus' | 'emoji'>('plus')
const showEmoji = ref(false)
/** 面板高度：移动端 = 键盘高度，保证收起键盘后面板顶上来不跳动 */
const panelHeight = ref(0)

const EMOJIS = [
  '😀','😁','😂','🤣','😊','😍','😘','😜','🤔','😭',
  '😅','😉','🙂','😴','🤗','🤩','😎','🥳','😡','👍',
  '👎','👏','🙏','💪','🤝','❤️','💔','🎉','🔥','🌹',
  '🍀','🌟','🎂','🚀','⚽','🏀','🐶','🐱','🍉','☕',
]

// 语音录制
const voiceMode = ref(false)
const recording = ref(false)
const recordingCancel = ref(false)
const recordSeconds = ref(0)
const recordingTimer = ref<ReturnType<typeof setInterval> | null>(null)
const mediaRecorder = ref<MediaRecorder | null>(null)
const recordChunks = ref<Blob[]>([])
const recordStartTime = ref(0)
const recordStartY = ref(0)

const friendId = computed(() => Number(route.params.id))
const friend = ref<Profile | null>(null)
const displayFriendName = computed(() => friend.value?.nickname || `用户 ${friendId.value || ''}`.trim())
const displayFriendInitial = computed(() => (displayFriendName.value || '?').charAt(0).toUpperCase())
const messages = ref<ChatMessage[]>([])
/** 最后一条自己发的消息 id：已读/未读只挂在最后一条下方 */
const lastSelfMsgId = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i--) {
    if (messages.value[i].sender_id === session.userId) {
      return messages.value[i].id
    }
  }
  return -1
})
const inputText = ref('')
const loading = ref(false)
const sending = ref(false)
const messagesContainer = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLInputElement | null>(null)

// 权限状态
const isMutual = ref(false)
const isDefaultFriend = ref(false)
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
    isDefaultFriend.value = payload.is_default_friend ?? false
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
    isDefaultFriend.value = payload.is_default_friend ?? false
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
      is_read: msg.is_read ?? false,
      read_at: msg.read_at ?? null,
      created_at: msg.created_at,
    })
    lastMsgFingerprint = buildMsgFingerprint(messages.value)
    await nextTick()
    scrollToBottom()
    inputRef.value?.focus()
    // 仅更新权限状态（stranger_once 模式下次数可能减少），不重新拉消息列表
    remainingToday.value = msg.remaining_today ?? remainingToday.value
    if (msg.is_mutual !== undefined) isMutual.value = msg.is_mutual
    if (msg.is_default_friend !== undefined) isDefaultFriend.value = msg.is_default_friend
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

/** 发送图片：前端压缩到立即发送的大小，直接显示图片，后台上传替换为服务器地址 */
async function onSendImage(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || sending.value || sendingImage.value || !canSend.value) return
  sendingImage.value = true
  try {
    // 压缩到小体积（本地立即完成，不显示加载动画）
    const compressed = await compressImage(file)
    const localUrl = URL.createObjectURL(compressed)
    messages.value.push({
      id: -1,
      sender_id: session.userId ?? 0,
      content: localUrl,
      msg_type: 'image',
      is_read: false,
      read_at: null,
      isLocal: true,
      created_at: null,
    })
    scrollToBottom()
    closePanels()
    // 后台上传 + 发送（压缩后文件很小，秒传）
    const { data } = await uploadImage(compressed, undefined, 'chat')
    const url = data.data.url
    const { data: msgData } = await sendMessage(friendId.value, url, 'image')
    const msg = msgData.data
    const idx = messages.value.findIndex((x) => x.isLocal)
    if (idx >= 0) {
      URL.revokeObjectURL(localUrl)
      messages.value[idx] = {
        id: msg.id,
        sender_id: msg.sender_id,
        content: msg.content,
        msg_type: msg.msg_type,
        is_read: msg.is_read ?? false,
        read_at: msg.read_at ?? null,
        isLocal: false,
        created_at: msg.created_at,
      }
    }
    lastMsgFingerprint = buildMsgFingerprint(messages.value)
    await nextTick()
    scrollToBottom()
  } catch (err) {
    messages.value = messages.value.filter((x) => !x.isLocal)
    toast.error((err as Error).message)
  } finally {
    sendingImage.value = false
  }
}

/** 拍照：WebView/手机浏览器打开相机（hidden input capture） */
function openCamera() {
  const input = cameraInputRef.value
  if (!input) return
  input.setAttribute('capture', 'environment')
  input.click()
  // 下次点击恢复默认（避免相册也强制相机）
  setTimeout(() => input.removeAttribute('capture'), 500)
}

function closePanels() {
  panelOpen.value = false
  showEmoji.value = false
  inputMode.value = 'keyboard'
  panelHeight.value = 0
}

function toggleVoiceMode() {
  if (recording.value) return
  if (inputMode.value === 'voice') {
    inputMode.value = 'keyboard'
    panelOpen.value = false
    showEmoji.value = false
  } else {
    inputMode.value = 'voice'
    panelOpen.value = false
    showEmoji.value = false
    // 预申请麦克风，保证"按住"时立即开始录音
    void prepareMic()
  }
}

function togglePanel(type: 'plus' | 'emoji') {
  if (recording.value) return
  if (panelOpen.value && panelType.value === type && showEmoji.value === (type === 'emoji')) {
    closePanels()
    return
  }
  panelType.value = type
  panelOpen.value = true
  showEmoji.value = type === 'emoji'
  inputMode.value = 'keyboard'
  // 收起键盘前记录高度，面板用这个高度顶上来（键盘收起动画完成后设置）
  const kh = keyboardHeight.value
  if (inputRef.value) inputRef.value.blur()
  setTimeout(() => {
    panelHeight.value = kh > 0 ? kh : 240
  }, 50)
}

function insertEmoji(e: string) {
  inputText.value += e
  inputRef.value?.focus()
}

/** 预申请麦克风权限并缓存录音流（进入语音模式时调用，按下即录） */
let cachedAudioStream: MediaStream | null = null

async function prepareMic() {
  if (cachedAudioStream) return true
  if (!isAppEnv()) return false
  try {
    const s = await navigator.mediaDevices.getUserMedia({ audio: true })
    cachedAudioStream = s
    return true
  } catch (e) {
    toast.error('无法访问麦克风，请检查权限')
    return false
  }
}

/** 语音：按住开始录音（网页端提示移步手机端并自动下载 App） */
function startRecord() {
  if (recording.value || !canSend.value) return
  if (!isAppEnv()) {
    toast.info('语音功能请移步手机端 App 使用')
    downloadApp()
    return
  }
  const stream = cachedAudioStream
  if (!stream) {
    toast.error('无法访问麦克风，请检查权限')
    return
  }
  try {
    const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : 'audio/webm'
    const rec = new MediaRecorder(stream, { mimeType: mime })
    recordChunks.value = []
    rec.ondataavailable = (ev) => {
      if (ev.data && ev.data.size > 0) recordChunks.value.push(ev.data)
    }
    mediaRecorder.value = rec
    rec.start()
    recording.value = true
    recordingCancel.value = false
    recordSeconds.value = 0
    recordStartTime.value = Date.now()
    recordStartY.value = 0
    document.addEventListener('pointerup', onRecordRelease, { once: true })
    recordingTimer.value = setInterval(() => {
      recordSeconds.value = Math.floor((Date.now() - recordStartTime.value) / 1000)
      if (recordSeconds.value >= 60) {
        finishRecord()
      }
    }, 200)
  } catch {
    toast.error('录音启动失败')
  }
}

/** 按住说话：移动时上滑取消（微信式） */
function onRecordMove(e: PointerEvent) {
  if (!recording.value) return
  const startY = recordStartY.value
  if (startY === 0) {
    recordStartY.value = e.clientY
    return
  }
  if (e.clientY < startY - 80) {
    recordingCancel.value = true
  } else if (e.clientY >= startY - 80) {
    recordingCancel.value = false
  }
}

/** 任意位置松开手指都会结束录音（防止录音浮层拦截 pointerup） */
function onRecordRelease() {
  void finishRecord()
}

/** 语音：松开结束录音并发送 */
async function finishRecord() {
  if (!recording.value) return
  const cancel = recordingCancel.value
  const secs = Math.max(1, Math.floor((Date.now() - recordStartTime.value) / 1000))
  recording.value = false
  recordingCancel.value = false
  document.removeEventListener('pointerup', onRecordRelease)
  if (recordingTimer.value) {
    clearInterval(recordingTimer.value)
    recordingTimer.value = null
  }
  const rec = mediaRecorder.value
  mediaRecorder.value = null
  if (rec && rec.state !== 'inactive') {
    rec.stop()
  }
  if (cancel || secs < 1 || !rec || recordChunks.value.length === 0) {
    recordChunks.value = []
    return
  }
  const blob = new Blob(recordChunks.value, { type: rec.mimeType || 'audio/webm' })
  recordChunks.value = []
  await sendVoice(blob, secs)
}

async function sendVoice(blob: Blob, secs: number) {
  if (!canSend.value) return
  const localId = `local-voice-${Date.now()}`
  messages.value.push({
    id: -1,
    sender_id: session.userId ?? 0,
    content: URL.createObjectURL(blob),
    msg_type: 'voice',
    is_read: false,
    read_at: null,
    uploadProgress: 0,
    duration: secs,
    isLocal: true,
    created_at: null,
  })
  scrollToBottom()
  try {
    const { data } = await uploadAudio(blob, (p) => {
      const target = messages.value[messages.value.length - 1]
      if (target && target.isLocal && target.uploadProgress !== undefined) {
        target.uploadProgress = p
      }
    })
    const url = data.data.url
    const { data: msgData } = await sendMessage(friendId.value, url, 'voice')
    const msg = msgData.data
    const idx = messages.value.findIndex((x) => x.isLocal && x.uploadProgress !== undefined)
    if (idx >= 0) {
      messages.value[idx] = {
        id: msg.id,
        sender_id: msg.sender_id,
        content: msg.content,
        msg_type: msg.msg_type,
        is_read: msg.is_read ?? false,
        read_at: msg.read_at ?? null,
        uploadProgress: 100,
        duration: secs,
        isLocal: false,
        created_at: msg.created_at,
      }
    }
    lastMsgFingerprint = buildMsgFingerprint(messages.value)
    await nextTick()
    scrollToBottom()
  } catch (err) {
    messages.value = messages.value.filter((x) => !(x.isLocal && x.uploadProgress !== undefined))
    toast.error((err as Error).message)
  }
}

/** 前端压缩图片：canvas 重绘到最长边 MAX_EDGE，JPEG 质量 0.62，体积小到可立即上传 */
const CHAT_IMG_MAX_EDGE = 1200
const CHAT_IMG_QUALITY = 0.62

function compressImage(file: File): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => {
      try {
        let { width, height } = img
        const scale = Math.min(1, CHAT_IMG_MAX_EDGE / Math.max(width, height))
        width = Math.max(1, Math.round(width * scale))
        height = Math.max(1, Math.round(height * scale))
        const canvas = document.createElement('canvas')
        canvas.width = width
        canvas.height = height
        const ctx = canvas.getContext('2d')
        if (!ctx) throw new Error('canvas error')
        ctx.fillStyle = '#fff'
        ctx.fillRect(0, 0, width, height)
        ctx.drawImage(img, 0, 0, width, height)
        canvas.toBlob(
          (blob) => {
            URL.revokeObjectURL(url)
            if (blob) resolve(blob)
            else reject(new Error('压缩失败'))
          },
          'image/jpeg',
          CHAT_IMG_QUALITY,
        )
      } catch (err) {
        URL.revokeObjectURL(url)
        reject(err as Error)
      }
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('图片加载失败'))
    }
    img.src = url
  })
}

function isImageUrl(url: string): boolean {
  return url.startsWith('blob:') || /^(https?:)?\/\//.test(url) || url.startsWith('/uploads/') || url.startsWith('/images/')
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
      is_read: (msg.is_read as boolean) ?? false,
      read_at: (msg.read_at as string | null) ?? null,
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

/** 播放语音消息 */
let voiceAudio: HTMLAudioElement | null = null
function playVoice(msg: ChatMessage) {
  if (!msg.content) return
  try {
    if (voiceAudio) {
      voiceAudio.pause()
      voiceAudio = null
    }
    const audio = new Audio(msg.content)
    voiceAudio = audio
    void audio.play().catch(() => toast.error('语音播放失败'))
    audio.onended = () => {
      voiceAudio = null
    }
  } catch {
    toast.error('语音播放失败')
  }
}

// 图片查看器（公共组件：返回 + 双指/双击缩放）
const imagePreviewVisible = ref(false)
const imagePreviewUrl = ref('')

function goBack() {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/notifications')
  }
}

/** 输入框获取焦点（键盘弹起）时，延迟滚动到底部，确保输入框可见 */
function onInputFocus() {
  // 唤起键盘时收起表情/加号面板
  panelOpen.value = false
  showEmoji.value = false
  panelHeight.value = 0
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
  if (isDefaultFriend.value) return '官方账号'
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
      // 轮询兜底：30 秒间隔（WebSocket 实时推送为主，轮询为辅）
      pollTimer = setInterval(pollMessages, 60_000)
    }
  }
}

onMounted(async () => {
  // 性能优化：validateSession / loadProfile 与业务请求并行，不阻塞主流程
  // loadFriendInfo → loadMessagesInitial 保持串行（后者依赖前者）
  const parallel: Promise<unknown>[] = [session.validateSession()]
  if (!userStore.profile) parallel.push(userStore.loadProfile())
  void Promise.allSettled(parallel)
  await loadFriendInfo()
  await loadMessagesInitial()
  // 轮询兜底：30 秒间隔（WebSocket 实时推送为主，轮询为辅，减少闪烁）
  pollTimer = setInterval(pollMessages, 60_000)
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
  if (recordingTimer.value) clearInterval(recordingTimer.value)
  document.removeEventListener('pointerup', onRecordRelease)
  if (voiceAudio) {
    voiceAudio.pause()
    voiceAudio = null
  }
  if (mediaRecorder.value && mediaRecorder.value.state !== 'inactive') {
    try {
      mediaRecorder.value.stop()
    } catch {
      /* ignore */
    }
  }
  if (cachedAudioStream) {
    cachedAudioStream.getTracks().forEach((tr) => tr.stop())
    cachedAudioStream = null
  }
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
          <span class="chat-name">
            <BadgeIcon :badge="friend?.wearing_badge" :size="15" />
            {{ displayFriendName }}
          </span>
          <span class="chat-subtitle" :class="{ 'is-mutual': isMutual, 'is-blocked': !canSend }">
            {{ headerSubtitle }}
          </span>
        </div>
      </div>
      <span class="more-btn-placeholder" />
    </header>

    <!-- 消息列表 -->
    <div ref="messagesContainer" class="chat-messages" @click="closePanels">
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
          <div class="chat-bubble" :class="{ 'is-voice': msg.msg_type === 'voice' }">
            <div v-if="msg.msg_type === 'image' && (isImageUrl(msg.content) || msg.isLocal)" class="chat-image-wrap">
              <img
                class="chat-image"
                :src="msg.content"
                alt="聊天图片"
                loading="lazy"
                @click="imagePreviewUrl = msg.content; imagePreviewVisible = true"
              />
            </div>
            <button
              v-else-if="msg.msg_type === 'voice'"
              class="chat-voice"
              type="button"
              :class="{ 'is-uploading': msg.uploadProgress !== undefined && msg.uploadProgress < 100 }"
              @click="playVoice(msg)"
            >
              <Icon name="mic" :size="18" />
              <span class="chat-voice-duration">{{ msg.duration ? `${msg.duration}″` : '1″' }}</span>
              <span v-if="msg.uploadProgress !== undefined && msg.uploadProgress < 100" class="chat-upload-progress">
                {{ msg.uploadProgress }}%
              </span>
            </button>
            <span v-else class="chat-text">{{ msg.content }}</span>
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
          <span
            v-if="msg.sender_id === session.userId && msg.id === lastSelfMsgId"
            class="chat-read-tag"
            :class="{ 'is-unread': !msg.is_read }"
          >{{ msg.is_read ? '已读' : '未读' }}</span>
        </div>
      </template>
      <EmptyState v-if="!loading && !messages.length" icon="message-circle" text="开始聊天吧" />
    </div>

    <!-- 权限提示条（非互关且不能发消息时） -->
    <div v-if="!canSend" class="chat-perm-banner">
      <Icon name="lock" :size="14" />
      <span>{{ canSendReason || '无法发送消息' }}</span>
    </div>

    <!-- 底部输入区（微信式） -->
    <div
      class="chat-input-bar"
      :style="keyboardHeight > 0 ? { paddingBottom: `${keyboardHeight}px` } : {}"
    >
      <div class="chat-input-row">
        <!-- 左侧：语音/键盘切换 -->
        <button
          class="chat-icon-btn"
          type="button"
          :class="{ 'is-active': inputMode === 'voice' }"
          :disabled="!canSend"
          aria-label="语音输入"
          @click="toggleVoiceMode"
        >
          <Icon :name="inputMode === 'voice' ? 'keyboard' : 'mic'" :size="20" />
        </button>

        <!-- 中间输入区 -->
        <div class="chat-input-wrap" :class="{ 'is-disabled': !canSend, 'is-voice-mode': inputMode === 'voice' }">
          <input
            v-if="inputMode === 'keyboard'"
            ref="inputRef"
            v-model="inputText"
            class="chat-input"
            type="text"
            :placeholder="inputPlaceholder"
            :disabled="!canSend"
            @keydown="onKeydown"
            @focus="onInputFocus"
          />
          <div
            v-else
            class="chat-hold-talk"
            :class="{ 'is-recording': recording }"
            @pointerdown="startRecord"
            @pointermove="onRecordMove"
            @pointerup="finishRecord"
            @pointercancel="recordingCancel = true"
          >
            <Icon name="mic" :size="18" />
            {{ recording ? `松开 发送 · ${recordSeconds}″` : '按住 说话' }}
          </div>
        </div>

        <!-- 右侧：空输入显示表情+加号；有文字显示绿色发送 -->
        <template v-if="!inputText.trim()">
          <button
            class="chat-icon-btn"
            type="button"
            :class="{ 'is-active': showEmoji }"
            :disabled="!canSend"
            aria-label="表情"
            @click="togglePanel('emoji')"
          >
            <Icon name="smile" :size="20" />
          </button>
          <button
            class="chat-icon-btn"
            type="button"
            :class="{ 'is-active': panelOpen && panelType === 'plus' }"
            :disabled="!canSend"
            aria-label="更多"
            @click="togglePanel('plus')"
          >
            <Icon name="plus" :size="20" />
          </button>
        </template>
        <button
          v-else
          class="chat-send-btn"
          type="button"
          :disabled="sending || !canSend"
          @click="onSend"
        >
          {{ sending ? '发送中' : '发送' }}
        </button>
      </div>

      <!-- 表情面板 -->
      <div v-if="showEmoji" class="chat-panel" :style="panelHeight > 0 ? { height: `${panelHeight}px` } : undefined">
        <div class="chat-emoji-grid">
          <button
            v-for="e in EMOJIS"
            :key="e"
            class="chat-emoji-item"
            type="button"
            @click="insertEmoji(e)"
          >
            {{ e }}
          </button>
        </div>
      </div>

      <!-- 加号面板：拍摄 / 相册 -->
      <div v-else-if="panelOpen && panelType === 'plus'" class="chat-panel chat-plus-panel" :style="panelHeight > 0 ? { height: `${panelHeight}px` } : undefined">
        <button class="chat-plus-item" type="button" @click="openCamera">
          <span class="chat-plus-icon">
            <Icon name="camera" :size="24" />
          </span>
          <span class="chat-plus-label">拍摄</span>
        </button>
        <button class="chat-plus-item" type="button" @click="imageInputRef?.click()">
          <span class="chat-plus-icon">
            <Icon name="image" :size="24" />
          </span>
          <span class="chat-plus-label">相册</span>
        </button>
      </div>

      <!-- 录音提示浮层 -->
      <div v-if="recording" class="chat-record-overlay" :class="{ 'is-cancel': recordingCancel }">
        <div class="chat-record-box">
          <Icon :name="recordingCancel ? 'close' : 'mic'" :size="34" />
          <span>{{ recordingCancel ? '松开手指，取消发送' : '松开 发送 · 上滑 取消' }}</span>
        </div>
      </div>

      <input
        ref="imageInputRef"
        class="hidden-file-input"
        type="file"
        accept="image/*"
        :multiple="false"
        @change="onSendImage"
      />
      <input
        ref="cameraInputRef"
        class="hidden-file-input"
        type="file"
        accept="image/*"
        capture="environment"
        @change="onSendImage"
      />
    </div>

    <!-- 图片查看器 -->
    <ImageViewer
      :visible="imagePreviewVisible"
      :url="imagePreviewUrl"
      @update:visible="imagePreviewVisible = $event"
    />
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
  /* 用 background-color 而不是 background 简写，避免重置
     .chat-avatar 中的 background-size: cover / background-position: center，
     否则自己的头像会按原图尺寸只显示左上角（对方看到正常）。 */
  background-color: #1482f0;
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
  display: inline-flex;
  align-items: center;
  gap: 4px;
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
  flex-wrap: wrap;
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
  flex-direction: column;
  align-items: stretch;
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
.chat-image {
  max-width: 200px;
  max-height: 220px;
  border-radius: 10px;
  display: block;
  cursor: zoom-in;
  background: #f0f0f0;
}
.chat-read-tag {
  flex-basis: 100%;
  width: 100%;
  text-align: right;
  font-size: 10px;
  line-height: 1.4;
  color: #999;
  margin: -4px 0 0;
  padding-right: 2px;
}
.chat-read-tag.is-unread {
  color: #b9b9b9;
}
.chat-input-row {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 4px;
}
.hidden-file-input {
  display: none;
}
.chat-icon-btn {
  flex: none;
  width: 36px;
  height: 36px;
  border: none;
  background: transparent;
  color: #444;
  display: grid;
  place-items: center;
  cursor: pointer;
  border-radius: 8px;
}
.chat-icon-btn.is-active {
  color: #07c160;
  background: rgba(7, 193, 96, 0.1);
}
.chat-icon-btn:active {
  background: rgba(0, 0, 0, 0.06);
}
.chat-icon-btn:disabled {
  opacity: 0.4;
}
.chat-hold-talk {
  flex: 1;
  height: 38px;
  border-radius: 6px;
  background: #fff;
  border: 0.5px solid #d9d9d9;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  font-size: 14px;
  color: #333;
  cursor: pointer;
  user-select: none;
  -webkit-user-select: none;
  touch-action: none;
}
.chat-hold-talk.is-recording {
  background: #e5e5e5;
  color: #07c160;
}
.chat-panel {
  border-top: 0.5px solid #e5e5e5;
  padding: 10px 8px;
  background: #f7f7f7;
  overflow-y: auto;
  box-sizing: border-box;
  width: 100%;
}
.chat-emoji-grid {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 4px;
}
.chat-emoji-item {
  font-size: 22px;
  line-height: 1.5;
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
}
.chat-emoji-item:active {
  background: rgba(0, 0, 0, 0.08);
}
.chat-plus-panel {
  display: flex;
  gap: 16px;
  padding: 14px;
}
.chat-plus-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  background: transparent;
  border: none;
  cursor: pointer;
  color: #444;
  font-size: 12px;
}
.chat-plus-icon {
  width: 54px;
  height: 54px;
  border-radius: 12px;
  background: #fff;
  display: grid;
  place-items: center;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}
.chat-plus-item:active .chat-plus-icon {
  transform: scale(0.96);
}
.chat-record-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: grid;
  place-items: center;
  z-index: 999;
}
.chat-record-box {
  width: 170px;
  height: 170px;
  border-radius: 16px;
  background: rgba(0, 0, 0, 0.72);
  color: #fff;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  font-size: 13px;
  text-align: center;
}
.chat-record-overlay.is-cancel .chat-record-box {
  background: rgba(255, 59, 48, 0.85);
}
.chat-upload-progress {
  position: absolute;
  right: 6px;
  bottom: 6px;
  font-size: 11px;
  color: #fff;
  background: rgba(0, 0, 0, 0.55);
  padding: 2px 6px;
  border-radius: 8px;
}
.chat-image-wrap {
  position: relative;
}
.chat-image.is-uploading {
  transition: filter 0.2s linear;
}
.chat-voice {
  display: flex;
  align-items: center;
  gap: 6px;
  border: none;
  background: #fff;
  color: #333;
  border-radius: 8px;
  padding: 8px 12px;
  cursor: pointer;
  position: relative;
  min-width: 110px;
}
.chat-voice.is-uploading {
  background: #d8d8d8;
  color: #888;
}
.chat-voice-duration {
  font-size: 13px;
}
.chat-voice .chat-upload-progress {
  right: 6px;
  bottom: auto;
  top: 6px;
}
.chat-input-wrap {
  flex: 1;
  min-width: 0;
  background: #fff;
  border-radius: 6px;
  padding: 0 12px;
}
.chat-input-wrap.is-disabled {
  background: #f0f0f0;
}
.chat-input {
  width: 100%;
  min-width: 0;
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
