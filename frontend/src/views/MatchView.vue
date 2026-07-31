<script setup lang="ts">
/**
 * 在线实时匹配页面（类似假装情侣）
 *
 * 流程：
 * 1. 匹配设置：年龄范围/校区/兴趣标签/性别筛选
 * 2. 等待动画：匹配队列中等待对方
 * 3. 匹配成功：直接进入临时聊天窗口
 * 4. 临时聊天：180 秒倒计时，可关注/求关注对方
 * 5. 结束：倒计时结束或主动结束，互关则成为好友
 *
 * 实时通信：通过 WebSocket 推送匹配结果和聊天消息
 */
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import { useSessionStore } from '../stores/session'
import { useUserStore } from '../stores/user'
import { useUIStore } from '../stores/ui'
import {
  cancelMatch,
  enqueueMatch,
  getActiveSession,
  listSessionMessages,
  type MatchMessage,
  type MatchSession,
} from '../api/match'
import { fetchBottleStats, listBottleTags } from '../api/bottle'
import { updateMe } from '../api/user'
import { connectWs, wsClient, type WsMessage } from '../utils/ws'
import { formatRelative } from '../utils/time'

const router = useRouter()
const session = useSessionStore()
const userStore = useUserStore()
const uiStore = useUIStore()

// ============ 首次资料填写弹窗 ============
// 进入随机交友页时，如果用户未填写性别或生日，弹出一次性填写弹窗
// 提示：性别只能填写一次，不能修改
const showProfileSetup = ref(false)
const profileSetupForm = ref({
  gender: '' as '' | 'male' | 'female',
  birthday: '' as string,
})
const profileSetupLoading = ref(false)

/** 检查是否需要弹出首次资料填写 */
function checkProfileSetup(): boolean {
  const p = userStore.profile
  if (!p) return false
  // 性别未设置或生日未填写 → 需要填写
  const needGender = !p.gender || p.gender === 'unknown'
  const needBirthday = !p.birthday
  if (needGender || needBirthday) {
    // 预填已有值
    profileSetupForm.value.gender = (needGender ? '' : p.gender) as '' | 'male' | 'female'
    profileSetupForm.value.birthday = needBirthday ? '' : (p.birthday ? p.birthday.slice(0, 10) : '')
    showProfileSetup.value = true
    return true
  }
  return false
}

function pickSetupGender(g: 'male' | 'female') {
  profileSetupForm.value.gender = g
}

async function onSubmitProfileSetup() {
  if (!profileSetupForm.value.gender) {
    toast.error('请选择性别')
    return
  }
  if (!profileSetupForm.value.birthday) {
    toast.error('请选择生日')
    return
  }
  profileSetupLoading.value = true
  try {
    const { data } = await updateMe({
      gender: profileSetupForm.value.gender,
      birthday: profileSetupForm.value.birthday,
    })
    // 更新本地 profile
    userStore.profile = data.data
    showProfileSetup.value = false
    toast.success('资料已保存，后续不可修改')
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    profileSetupLoading.value = false
  }
}

// ============ 状态机 ============
type Phase = 'setup' | 'waiting' | 'chatting' | 'ended'
const phase = ref<Phase>('setup')
// waiting 阶段子状态：searching=搜索中 / matched=已匹配正在连接
const waitingSub = ref<'searching' | 'matched'>('searching')
// 立即匹配成功时缓存会话数据，等待动画展示后进入聊天
const pendingSession = ref<MatchSession | null>(null)
let matchedTransitionTimer: ReturnType<typeof setTimeout> | null = null

// ============ 选项 ============
// 年龄范围：13-18 岁（中学阶段）
const AGE_OPTIONS = [13, 14, 15, 16, 17, 18]
const SCHOOLS = [
  { id: 1, name: '本部校区' },
  { id: 2, name: '未来校区' },
  { id: 3, name: '香山校区' },
  { id: 4, name: '东校校区' },
]
const TARGET_GENDERS = [
  { value: 'male', label: '男' },
  { value: 'female', label: '女' },
  { value: 'any', label: '不限' },
] as const

const interestTags = ref<string[]>([])

// ============ 设置表单 ============
const setupForm = ref({
  /** 期望对方年龄下限（null=不限） */
  age_min: null as number | null,
  /** 期望对方年龄上限（null=不限） */
  age_max: null as number | null,
  school_ids: [] as number[],
  tags: [] as string[],
  target_gender: 'any' as 'male' | 'female' | 'any',
})

/**
 * 匹配标签三态点击机制（同漂流瓶拾取）：
 * - 0：无所谓（默认，点三下回到此态）
 * - 1：尽量有（点一下，候选中按重叠度排序优先）
 * - 2：必须有（点两下，对方必须符合此标签才能匹配到）
 */
const tagStates = ref<Record<string, 0 | 1 | 2>>({})

function toggleAgeMin(a: number) {
  // 点击已选中的最小年龄再次点击 → 取消
  if (setupForm.value.age_min === a) {
    setupForm.value.age_min = null
    return
  }
  setupForm.value.age_min = a
  // 自动校验：min 不能大于 max
  if (setupForm.value.age_max !== null && a > setupForm.value.age_max) {
    setupForm.value.age_max = a
  }
}
function toggleAgeMax(a: number) {
  if (setupForm.value.age_max === a) {
    setupForm.value.age_max = null
    return
  }
  setupForm.value.age_max = a
  if (setupForm.value.age_min !== null && a < setupForm.value.age_min) {
    setupForm.value.age_min = a
  }
}
function clearAgeRange() {
  setupForm.value.age_min = null
  setupForm.value.age_max = null
}
function toggleSchool(id: number) {
  const idx = setupForm.value.school_ids.indexOf(id)
  if (idx >= 0) setupForm.value.school_ids.splice(idx, 1)
  else setupForm.value.school_ids.push(id)
}
/** 三态标签点击：0 → 1 → 2 → 0 */
function toggleTagState(tag: string) {
  const current = tagStates.value[tag] || 0
  const next = current === 2 ? 0 : (current + 1) as 0 | 1 | 2
  tagStates.value = { ...tagStates.value, [tag]: next }
}
function getTagState(tag: string): 0 | 1 | 2 {
  return tagStates.value[tag] || 0
}
function getTagStateClass(tag: string) {
  const state = getTagState(tag)
  return {
    'tag-state-default': state === 0,
    'tag-state-prefer': state === 1,
    'tag-state-required': state === 2,
  }
}
function getTagStateLabel(tag: string): string {
  const state = getTagState(tag)
  if (state === 1) return '尽量'
  if (state === 2) return '必须'
  return ''
}
function setTargetGender(g: 'male' | 'female' | 'any') {
  setupForm.value.target_gender = g
}

// ============ 等待状态 ============
const waitingTimer = ref(0)
let waitingInterval: ReturnType<typeof setInterval> | null = null
const WAIT_TIMEOUT = 600 // 后端 600 秒（10 分钟）未匹配则超时

// 匹配中人数（轮询 stats 接口获取）
const matchingCount = ref(0)
let matchingCountTimer: ReturnType<typeof setInterval> | null = null

/** 等待时间格式化为 MM:SS */
const waitingDisplay = computed(() => {
  const m = Math.floor(waitingTimer.value / 60)
  const s = waitingTimer.value % 60
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
})

function startWaitingTimer() {
  waitingTimer.value = 0
  if (waitingInterval) clearInterval(waitingInterval)
  waitingInterval = setInterval(() => {
    waitingTimer.value += 1
    if (waitingTimer.value >= WAIT_TIMEOUT) {
      // 客户端超时兜底
      stopWaitingTimer()
      stopWaitingPolling()
      if (phase.value === 'waiting') {
        phase.value = 'setup'
        toast.error('匹配超时，请重新发起')
      }
    }
  }, 1000)
}
function stopWaitingTimer() {
  if (waitingInterval) {
    clearInterval(waitingInterval)
    waitingInterval = null
  }
}

/** 加载当前匹配中人数 */
async function loadMatchingCount() {
  try {
    const { data } = await fetchBottleStats({
      showGlobalLoading: false,
      showGlobalError: false,
    })
    matchingCount.value = data.data?.matching_count || 0
  } catch {
    /* 静默 */
  }
}

function startMatchingCountPolling() {
  loadMatchingCount()
  if (matchingCountTimer) clearInterval(matchingCountTimer)
  // 每 5 秒刷新一次匹配中人数
  matchingCountTimer = setInterval(loadMatchingCount, 5000)
}
function stopMatchingCountPolling() {
  if (matchingCountTimer) {
    clearInterval(matchingCountTimer)
    matchingCountTimer = null
  }
}

// ============ 聊天状态 ============
const activeSession = ref<MatchSession | null>(null)
const messages = ref<MatchMessage[]>([])
const inputMessage = ref('')
const remainingSeconds = ref(0)
let countdownInterval: ReturnType<typeof setInterval> | null = null
const messageListRef = ref<HTMLDivElement | null>(null)
const isMutualFollow = ref(false)
const myConsent = ref(false)        // 我是否已同意互关
const peerConsent = ref(false)      // 对方是否已同意互关
const sessionEndedReason = ref('')

function startCountdown(expiresAt: string) {
  stopCountdown()
  const update = () => {
    // 已结束的会话不再倒计时
    if (phase.value !== 'chatting') {
      stopCountdown()
      return
    }
    const now = Date.now()
    const expires = new Date(expiresAt).getTime()
    const diff = Math.max(0, Math.floor((expires - now) / 1000))
    remainingSeconds.value = diff
    if (diff <= 0) {
      stopCountdown()
      // 倒计时结束：后端会推送 match_end 事件，这里作为兜底
      endChat('timeout')
    }
  }
  update()
  countdownInterval = setInterval(update, 1000)
}
function stopCountdown() {
  if (countdownInterval) {
    clearInterval(countdownInterval)
    countdownInterval = null
  }
}

const remainingDisplay = computed(() => {
  const m = Math.floor(remainingSeconds.value / 60)
  const s = remainingSeconds.value % 60
  return `${m}:${s.toString().padStart(2, '0')}`
})

const isMyMessage = (msg: MatchMessage) => msg.sender_id === session.userId

async function scrollToBottom() {
  await nextTick()
  if (messageListRef.value) {
    messageListRef.value.scrollTop = messageListRef.value.scrollHeight
  }
}

// ============ WebSocket 消息处理 ============
let unsubscribeWs: (() => void) | null = null

function onWsMessage(msg: WsMessage) {
  switch (msg.type) {
    case 'match_found': {
      // 匹配成功：进入聊天
      const sessionId = msg.session_id as number
      const peer = msg.peer as MatchSession['peer']
      const expiresAt = msg.expires_at as string
      stopWaitingTimer()
      stopMatchingCountPolling()
      stopWaitingPolling()
      const s: MatchSession = {
        id: sessionId,
        user_a: session.userId!,
        user_b: peer?.id || 0,
        status: 'active',
        expires_at: expiresAt,
        ended_at: null,
        mutual_follow: false,
        created_at: new Date().toISOString(),
        peer,
      }
      // 如果在 waiting 阶段，先展示"匹配成功"动画 1.2s
      if (phase.value === 'waiting') {
        pendingSession.value = s
        waitingSub.value = 'matched'
        if (matchedTransitionTimer) clearTimeout(matchedTransitionTimer)
        matchedTransitionTimer = setTimeout(() => {
          enterChatWithSession(pendingSession.value!)
          pendingSession.value = null
          matchedTransitionTimer = null
        }, 1200)
      } else {
        // 不在 waiting 阶段（如刷新恢复），直接进入聊天
        enterChatWithSession(s)
      }
      break
    }
    case 'match_timeout': {
      // 等待匹配超时
      stopWaitingTimer()
      stopMatchingCountPolling()
      stopWaitingPolling()
      if (phase.value === 'waiting') {
        phase.value = 'setup'
        waitingSub.value = 'searching'
        toast.error('匹配超时，暂无合适的对方，请稍后再试')
      }
      break
    }
    case 'match_chat': {
      // 收到对方的聊天消息（后端不再回传给发送者，这里只处理对方消息）
      const sessionId = msg.session_id as number
      if (activeSession.value?.id !== sessionId) return
      const senderId = msg.sender_id as number
      const content = msg.content as string
      const createdAt = msg.created_at as string
      const serverMsgId = msg.message_id as number | undefined
      // 去重：优先用服务端 message_id，其次用 sender_id + content + created_at
      if (serverMsgId && messages.value.some((m) => m.id === serverMsgId)) {
        return
      }
      if (messages.value.some((m) => m.sender_id === senderId && m.content === content && m.created_at === createdAt)) {
        return
      }
      messages.value.push({
        id: serverMsgId || Date.now() + Math.random(),
        session_id: sessionId,
        sender_id: senderId,
        content,
        created_at: createdAt,
      })
      scrollToBottom()
      break
    }
    case 'match_follow_event': {
      // 关注事件（在"同意互关"机制下：一方同意就触发 follow，双方都同意则互关）
      const sessionId = msg.session_id as number
      if (activeSession.value?.id !== sessionId) return
      const followerId = msg.follower_id as number
      const mutual = msg.is_mutual as boolean
      isMutualFollow.value = mutual
      if (mutual) {
        // 双方都同意 → 自动互关
        myConsent.value = true
        peerConsent.value = true
        toast.success('双方已同意，自动互相关注！匹配结束后可在好友列表继续联系')
      } else if (followerId === session.userId) {
        // 我同意了，但对方还没同意
        myConsent.value = true
        toast.success('已同意互关，等待对方同意')
      } else {
        // 对方同意了，等我同意
        peerConsent.value = true
        toast.info('对方已同意互关，等你同意')
      }
      break
    }
    case 'match_end': {
      // 会话结束
      const sessionId = msg.session_id as number
      if (activeSession.value?.id !== sessionId) return
      // 如果已经结束（自己点了结束），不再重复处理
      if (phase.value === 'ended') return
      const reason = (msg.reason as string) || 'ended'
      endChat(reason)
      break
    }
  }
}

// ============ 操作 ============
async function onStartMatch() {
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  // 性别筛选需用户已设置性别
  if (userStore.profile?.gender === 'unknown' || !userStore.profile?.gender) {
    toast.error('请先在「我的-设置」中完善性别信息后再匹配')
    return
  }
  // 先进入匹配动画页面，让用户看到"正在匹配"的过程
  phase.value = 'waiting'
  waitingSub.value = 'searching'
  startWaitingTimer()
  startMatchingCountPolling()
  // 启动 waiting 阶段轮询：作为 WS match_found 推送的兜底
  startWaitingPolling()
  // 把三态标签拆分为 tag_required 和 tag_preferred
  const tagRequired: string[] = []
  const tagPreferred: string[] = []
  for (const [tag, state] of Object.entries(tagStates.value)) {
    if (state === 2) tagRequired.push(tag)
    else if (state === 1) tagPreferred.push(tag)
  }
  try {
    const { data } = await enqueueMatch({
      school_ids: setupForm.value.school_ids,
      tags: tagPreferred,
      tag_required: tagRequired,
      target_gender: setupForm.value.target_gender,
      age_min: setupForm.value.age_min,
      age_max: setupForm.value.age_max,
    })
    const result = data.data
    if (result.status === 'matched' && result.session) {
      // 立即匹配成功：先缓存会话数据，展示"匹配成功"动画，1.5s 后进入聊天
      pendingSession.value = result.session
      waitingSub.value = 'matched'
      stopWaitingTimer()
      stopMatchingCountPolling()
      stopWaitingPolling()
      // 展示匹配成功动画 1.5 秒后进入聊天
      if (matchedTransitionTimer) clearTimeout(matchedTransitionTimer)
      matchedTransitionTimer = setTimeout(() => {
        enterChatWithSession(pendingSession.value!)
        pendingSession.value = null
        matchedTransitionTimer = null
      }, 1500)
    } else {
      // 进入等待（保持 searching 子状态）
      waitingSub.value = 'searching'
    }
  } catch (err) {
    stopWaitingTimer()
    stopMatchingCountPolling()
    stopWaitingPolling()
    phase.value = 'setup'
    waitingSub.value = 'searching'
    toast.error((err as Error).message)
  }
}

/** 进入聊天会话（共用入口） */
function enterChatWithSession(s: MatchSession) {
  activeSession.value = s
  isMutualFollow.value = s.mutual_follow
  myConsent.value = false
  peerConsent.value = false
  messages.value = []
  phase.value = 'chatting'
  if (s.expires_at) {
    startCountdown(s.expires_at)
  }
  toast.success('匹配成功，开始聊天吧')
  loadSessionMessages(s.id)
  startSessionPolling()
}

async function onCancelMatch() {
  try {
    await cancelMatch()
  } catch {
    /* ignore */
  }
  stopWaitingTimer()
  stopMatchingCountPolling()
  stopWaitingPolling()
  if (matchedTransitionTimer) {
    clearTimeout(matchedTransitionTimer)
    matchedTransitionTimer = null
  }
  pendingSession.value = null
  phase.value = 'setup'
  waitingSub.value = 'searching'
}

async function loadSessionMessages(sessionId: number) {
  try {
    const { data } = await listSessionMessages(sessionId, {
      showGlobalLoading: false,
      showGlobalError: false,
    })
    messages.value = data.data || []
    scrollToBottom()
  } catch {
    /* 静默 */
  }
}

async function onSend() {
  const content = inputMessage.value.trim()
  if (!content || !activeSession.value) return
  const sessionId = activeSession.value.id
  // 通过 WebSocket 发送
  const ok = wsClient.send({
    type: 'match_chat',
    session_id: sessionId,
    content,
  })
  if (ok) {
    inputMessage.value = ''
    // 本地立即显示（乐观更新）
    messages.value.push({
      id: Date.now(),
      session_id: sessionId,
      sender_id: session.userId!,
      content,
      created_at: new Date().toISOString(),
    })
    scrollToBottom()
  } else {
    toast.error('消息发送失败，请检查网络')
  }
}

function onInputKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    onSend()
  }
}

/**
 * 同意互关：发送 match_follow，后端会自动检测双方是否都同意。
 * - 一方同意：标记 myConsent，对方收到 match_follow_event(is_mutual=false)
 * - 双方都同意：后端自动触发互关，双方收到 match_follow_event(is_mutual=true)
 */
function onConsent() {
  if (!activeSession.value || myConsent.value || isMutualFollow.value) return
  const ok = wsClient.send({
    type: 'match_follow',
    session_id: activeSession.value.id,
  })
  if (!ok) {
    toast.error('操作失败，请检查网络')
  }
  // 实际状态由 match_follow_event 事件回传更新
}

function onEndChat() {
  if (!activeSession.value) return
  // 立即本地结束（不等 WS 回传），避免倒计时/轮询竞争导致显示错误的结束原因
  endChat('manual')
  // 同时通过 WS 通知后端结束会话（后端会推 match_end 给对方）
  wsClient.send({
    type: 'match_end',
    session_id: activeSession.value.id,
  })
}

function endChat(reason: string) {
  // 防止重复结束（倒计时/轮询/WS推送可能在同一时刻触发）
  if (phase.value === 'ended') return
  stopCountdown()
  stopSessionPolling()
  sessionEndedReason.value = reason
  phase.value = 'ended'
  if (reason === 'timeout') {
    toast.info('180 秒聊天时间已结束')
  } else if (reason === 'peer_left') {
    toast.error('对方已退出，聊天已结束')
  } else if (reason === 'manual') {
    // 对方或自己主动结束
    toast.info('聊天已结束')
  }
}

function onBackToSetup() {
  phase.value = 'setup'
  waitingSub.value = 'searching'
  activeSession.value = null
  messages.value = []
  isMutualFollow.value = false
  myConsent.value = false
  peerConsent.value = false
  sessionEndedReason.value = ''
}

/** 互关成功后跳转对方主页 */
function goPeerProfile() {
  const peerId = activeSession.value?.peer?.id
  if (!peerId) return
  router.push(`/user/${peerId}`)
}

function goBack() {
  // 离开页面时清理
  if (phase.value === 'waiting') {
    onCancelMatch()
  } else if (phase.value === 'chatting') {
    onEndChat()
  }
  router.back()
}

function goBottle() {
  router.push('/bottle')
}

// ============ 恢复活动会话 ============
async function checkActiveSession() {
  if (!session.userId) return
  try {
    const { data } = await getActiveSession({
      showGlobalLoading: false,
      showGlobalError: false,
    })
    // 后端 ok() 将 None 转为 {}，所以需要检查 id 字段而非 truthy
    if (data.data && data.data.id) {
      activeSession.value = data.data
      isMutualFollow.value = data.data.mutual_follow
      // 恢复同意状态：若已互关，则双方都同意；否则无法准确恢复，默认未同意
      myConsent.value = data.data.mutual_follow
      peerConsent.value = data.data.mutual_follow
      phase.value = 'chatting'
      if (data.data.expires_at) {
        startCountdown(data.data.expires_at)
      }
      await loadSessionMessages(data.data.id)
      startSessionPolling()
    }
  } catch {
    /* 静默 */
  }
}

// ============ 会话状态轮询（实时同步服务器数据） ============
// 作为 WebSocket 推送的兜底：WS 可能因网络抖动丢失消息，
// 每 5 秒轮询一次 /match/active-session，检测会话是否已结束、
// 同步最新消息和互关状态。
let sessionPollingTimer: ReturnType<typeof setInterval> | null = null
const SESSION_POLL_INTERVAL = 5000

// ============ waiting 阶段轮询（匹配结果兜底） ============
// Bug 修复：A 先入队 waiting，B 入队触发匹配成功后端通过 WS 推 match_found 给 A。
// 但 WS 推送可能因各种原因失败（loop 引用错误、网络抖动、连接未就绪等），
// 导致 A 卡在 waiting 页面需要刷新。此处主动轮询 getActiveSession 兜底，
// 即使 WS 推送失败，A 也能在 3 秒内发现自己已被匹配。
let waitingPollingTimer: ReturnType<typeof setInterval> | null = null
const WAITING_POLL_INTERVAL = 3000

function startWaitingPolling() {
  stopWaitingPolling()
  waitingPollingTimer = setInterval(pollWaitingMatch, WAITING_POLL_INTERVAL)
}

function stopWaitingPolling() {
  if (waitingPollingTimer) {
    clearInterval(waitingPollingTimer)
    waitingPollingTimer = null
  }
}

async function pollWaitingMatch() {
  // 仅在 waiting 阶段且尚未收到 match_found 时轮询
  if (phase.value !== 'waiting' || pendingSession.value) return
  try {
    const { data } = await getActiveSession({
      showGlobalLoading: false,
      showGlobalError: false,
    })
    if (data.data && data.data.id) {
      // 服务器已有活动会话 → 匹配成功，但 WS 推送丢失，主动恢复
      stopWaitingTimer()
      stopMatchingCountPolling()
      stopWaitingPolling()
      // 复用 match_found 的恢复逻辑（不在 waiting 阶段时直接进入聊天）
      enterChatWithSession(data.data)
    }
  } catch {
    /* 静默 */
  }
}

function startSessionPolling() {
  stopSessionPolling()
  sessionPollingTimer = setInterval(pollSessionSync, SESSION_POLL_INTERVAL)
}

function stopSessionPolling() {
  if (sessionPollingTimer) {
    clearInterval(sessionPollingTimer)
    sessionPollingTimer = null
  }
}

async function pollSessionSync() {
  // 已结束的会话不再轮询（避免覆盖 endChat 设置的 reason）
  if (phase.value !== 'chatting' || !activeSession.value) return
  try {
    const { data } = await getActiveSession({
      showGlobalLoading: false,
      showGlobalError: false,
    })
    const serverSession = data.data
    // 后端 ok() 将 None 转为 {}，检查 id 字段判断会话是否还存在
    if (!serverSession || !serverSession.id) {
      // 服务器上会话已结束（对方退出/超时等），本地同步结束
      // 注意：如果 phase 已经是 'ended'（自己刚点了结束），endChat 会阻止重复处理
      endChat('peer_left')
      return
    }
    // 同步互关状态
    if (serverSession.mutual_follow && !isMutualFollow.value) {
      isMutualFollow.value = true
      myConsent.value = true
      peerConsent.value = true
    }
    // 同步消息（拉取服务器最新消息，去重后合并）
    await syncMessages(serverSession.id)
  } catch {
    /* 静默 */
  }
}

async function syncMessages(sessionId: number) {
  try {
    const { data } = await listSessionMessages(sessionId, {
      showGlobalLoading: false,
      showGlobalError: false,
    })
    const serverMsgs = data.data || []
    // 合并服务端消息与本地乐观消息，去重策略：
    // 1. 服务端消息按 id 去重
    // 2. 本地乐观消息（id 为 Date.now() 时间戳）通过 sender_id + content 匹配服务端消息
    const serverIds = new Set(serverMsgs.map((m: MatchMessage) => m.id))
    // 用 sender_id+content 标识本地乐观消息，匹配服务端同内容消息
    const serverKeys = new Set(
      serverMsgs.map((m: MatchMessage) => `${m.sender_id}:${m.content}`)
    )
    // 保留本地消息中：未在服务端出现的（可能是刚发送还没同步的乐观消息）
    const localOnly = messages.value.filter((m) => {
      // 服务端消息 id 是整数，本地乐观 id 是 Date.now()（很大但也是整数）
      // 用 sender_id+content 做内容去重
      const key = `${m.sender_id}:${m.content}`
      return !serverKeys.has(key)
    })
    // 合并：服务端消息（权威） + 本地独有的乐观消息
    const merged = [...serverMsgs, ...localOnly]
    // 检查是否有变化，避免不必要的重渲染
    if (merged.length !== messages.value.length || merged.some((m, i) => m.id !== messages.value[i]?.id)) {
      messages.value = merged
      scrollToBottom()
    }
  } catch {
    /* 静默 */
  }
}

// ============ 生命周期 ============
onMounted(async () => {
  // 性能优化：validateSession 后台并行，不阻塞（邀请码检查基于 localStorage 缓存的 verificationStatus）
  void session.validateSession()
  // 邀请码系统：未认证用户进入随机匹配页时直接弹邀请码框并返回
  if (session.isLoggedIn() && !session.isVerified()) {
    // 先返回再弹窗，避免路由 watcher 立即关闭弹窗
    router.back()
    setTimeout(() => uiStore.openInviteCodeDialog(), 100)
    return
  }
  if (session.userId) {
    await userStore.loadProfile()
    // 进入随机交友页时，如果性别或生日未填写，弹出一次性资料填写弹窗
    checkProfileSetup()
  }
  // 加载兴趣标签
  try {
    const { data } = await listBottleTags({
      showGlobalLoading: false,
      showGlobalError: false,
    })
    interestTags.value = data.data || []
  } catch {
    /* 静默 */
  }
  // 连接 WebSocket
  if (session.userId) {
    connectWs()
    // 注册消息处理器
    unsubscribeWs = wsClient.on(onWsMessage)
    // 检查是否有未完成的活动会话（页面刷新后恢复）
    await checkActiveSession()
  }
})

onUnmounted(() => {
  stopWaitingTimer()
  stopMatchingCountPolling()
  stopWaitingPolling()
  stopCountdown()
  stopSessionPolling()
  if (matchedTransitionTimer) {
    clearTimeout(matchedTransitionTimer)
    matchedTransitionTimer = null
  }
  if (unsubscribeWs) {
    unsubscribeWs()
    unsubscribeWs = null
  }
  // 不主动断开 WS（其他页面可能还会用到），但若在等待中则取消
  if (phase.value === 'waiting') {
    onCancelMatch()
  }
})

function genderLabel(g: string | undefined): string {
  if (g === 'male') return '男'
  if (g === 'female') return '女'
  return '未知'
}
function ageLabel(age: number | null | undefined): string {
  if (age === null || age === undefined) return '未知年龄'
  return `${age} 岁`
}
</script>

<template>
  <main class="page-match">
    <!-- ====== 首次资料填写弹窗（性别+生日，只能填一次） ====== -->
    <Teleport to="body">
      <Transition name="profile-setup">
        <div v-if="showProfileSetup" class="profile-setup-overlay" @click.self="() => {}">
          <div class="profile-setup-modal" role="dialog" aria-modal="true" aria-label="完善资料">
            <div class="profile-setup-head">
              <h2 class="profile-setup-title">完善资料</h2>
              <p class="profile-setup-desc">为了更好的匹配体验，请先完善你的基础资料</p>
            </div>
            <div class="profile-setup-body">
              <!-- 性别选择 -->
              <div class="setup-field">
                <label class="setup-field-label">性别</label>
                <div class="setup-gender-row">
                  <button
                    type="button"
                    class="setup-gender-btn"
                    :class="{ 'is-active': profileSetupForm.gender === 'male' }"
                    @click="pickSetupGender('male')"
                  >
                    <Icon name="user" :size="18" />
                    <span>男生</span>
                  </button>
                  <button
                    type="button"
                    class="setup-gender-btn"
                    :class="{ 'is-active': profileSetupForm.gender === 'female' }"
                    @click="pickSetupGender('female')"
                  >
                    <Icon name="user" :size="18" />
                    <span>女生</span>
                  </button>
                </div>
              </div>
              <!-- 生日选择 -->
              <div class="setup-field">
                <label class="setup-field-label">生日</label>
                <input
                  v-model="profileSetupForm.birthday"
                  type="date"
                  class="setup-date-input"
                  :max="new Date().toISOString().slice(0, 10)"
                  :min="new Date(new Date().getFullYear() - 100, 0, 1).toISOString().slice(0, 10)"
                />
                <p class="setup-field-tip">设置生日后系统会自动计算年龄，用于匹配</p>
              </div>
              <p class="setup-once-tip">
                <Icon name="info" :size="12" />
                <span>注意：资料只能填写一次，保存后不可修改</span>
              </p>
            </div>
            <div class="profile-setup-foot">
              <button
                type="button"
                class="setup-submit-btn"
                :disabled="profileSetupLoading"
                @click="onSubmitProfileSetup"
              >
                {{ profileSetupLoading ? '保存中...' : '保存并开始匹配' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- ====== 顶部固定栏 ====== -->
    <header class="site-header" role="banner">
      <div class="header-inner">
        <div class="header-side header-side--left">
          <button class="icon-btn" type="button" aria-label="返回" @click="goBack">
            <Icon name="arrow-left" :size="20" />
          </button>
        </div>
        <h1 class="header-title">在线匹配</h1>
        <div class="header-side header-side--right">
          <button class="icon-btn" type="button" aria-label="漂流瓶" @click="goBottle">
            <Icon name="box" :size="20" />
          </button>
        </div>
      </div>
    </header>

    <div class="page-container">
      <!-- ====== Phase: 设置 ====== -->
      <section v-if="phase === 'setup'" class="setup-panel">
        <div class="setup-hero">
          <div class="hero-icon">
            <Icon name="shuffle" :size="36" />
          </div>
          <h2 class="hero-title">在线实时匹配</h2>
          <p class="hero-desc">匹配成功即可开启 180 秒临时聊天<br/>双方都同意即可自动互相关注，匹配结束后继续联系</p>
        </div>

        <div class="form-card">
          <div class="form-group">
            <label class="form-label">对方性别 <span class="required">*</span></label>
            <div class="option-row">
              <button
                v-for="g in TARGET_GENDERS"
                :key="g.value"
                type="button"
                class="option-chip"
                :class="{ 'is-active': setupForm.target_gender === g.value }"
                @click="setTargetGender(g.value)"
              >{{ g.label }}</button>
            </div>
            <p v-if="userStore.profile?.gender === 'unknown' || !userStore.profile?.gender" class="form-warn">
              <Icon name="circle-alert" :size="12" />
              <span>请先在「我的-设置」中完善性别信息</span>
            </p>
          </div>

          <div class="form-group">
            <label class="form-label">
              期望年龄范围
              <span class="form-hint-inline">选填，不选则不限</span>
            </label>
            <div class="age-range-row">
              <div class="age-range-side">
                <span class="age-side-label">最小</span>
                <button
                  v-for="a in AGE_OPTIONS"
                  :key="`min-${a}`"
                  type="button"
                  class="option-chip age-chip"
                  :class="{ 'is-active': setupForm.age_min === a }"
                  @click="toggleAgeMin(a)"
                >{{ a }}</button>
              </div>
              <div class="age-range-side">
                <span class="age-side-label">最大</span>
                <button
                  v-for="a in AGE_OPTIONS"
                  :key="`max-${a}`"
                  type="button"
                  class="option-chip age-chip"
                  :class="{ 'is-active': setupForm.age_max === a }"
                  @click="toggleAgeMax(a)"
                >{{ a }}</button>
              </div>
            </div>
            <button
              v-if="setupForm.age_min !== null || setupForm.age_max !== null"
              type="button"
              class="clear-age-btn"
              @click="clearAgeRange"
            >清除年龄筛选</button>
          </div>

          <div class="form-group">
            <label class="form-label">期望校区 <span class="form-hint-inline">可多选</span></label>
            <div class="option-row">
              <button
                v-for="s in SCHOOLS"
                :key="s.id"
                type="button"
                class="option-chip"
                :class="{ 'is-active': setupForm.school_ids.includes(s.id) }"
                @click="toggleSchool(s.id)"
              >{{ s.name }}</button>
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">兴趣标签 <span class="form-hint-inline">点一下=尽量有，点两下=必须有，点三下=无所谓</span></label>
            <div class="tag-legend">
              <span class="legend-item"><span class="legend-dot legend-default"></span>无所谓</span>
              <span class="legend-item"><span class="legend-dot legend-prefer"></span>尽量有</span>
              <span class="legend-item"><span class="legend-dot legend-required"></span>必须有</span>
            </div>
            <div class="option-row">
              <button
                v-for="t in interestTags"
                :key="t"
                type="button"
                class="option-chip tag-chip"
                :class="getTagStateClass(t)"
                @click="toggleTagState(t)"
              >
                <span class="tag-name">{{ t }}</span>
                <span v-if="getTagState(t) === 1" class="tag-state-badge tag-state-badge--prefer">尽量</span>
                <span v-if="getTagState(t) === 2" class="tag-state-badge tag-state-badge--required">必须</span>
              </button>
            </div>
          </div>

          <button type="button" class="primary-btn" @click="onStartMatch">
            <Icon name="shuffle" :size="16" />
            <span>开始匹配</span>
          </button>
        </div>

        <div class="setup-tips">
          <h4 class="tips-title">玩法说明</h4>
          <ul class="tips-list">
            <li>匹配成功后，双方进入 180 秒临时聊天窗口</li>
            <li>聊天过程中双方都点「同意互关」即自动成为好友</li>
            <li>未互关则匹配结束后无法再联系</li>
            <li>请文明交流，遵守校园社区规范</li>
          </ul>
        </div>
      </section>

      <!-- ====== Phase: 等待 ====== -->
      <section v-else-if="phase === 'waiting'" class="waiting-panel" :class="{ 'is-matched': waitingSub === 'matched' }">
        <div class="waiting-hero">
          <div class="waiting-ring" :class="{ 'ring-matched': waitingSub === 'matched' }">
            <div class="waiting-ring--outer"></div>
            <div class="waiting-ring--inner"></div>
            <div class="waiting-icon">
              <Icon :name="waitingSub === 'matched' ? 'user-check' : 'shuffle'" :size="32" />
            </div>
          </div>
          <h2 class="waiting-title">
            {{ waitingSub === 'matched' ? '匹配成功！' : '正在为你匹配...' }}
          </h2>
          <p class="waiting-desc">
            <template v-if="waitingSub === 'matched'">正在建立连接，马上开始聊天</template>
            <template v-else>寻找同时在线且符合条件的同学</template>
          </p>
          <p v-if="waitingSub === 'searching'" class="waiting-time">已等待 {{ waitingDisplay }}</p>
          <p v-if="waitingSub === 'searching'" class="waiting-count">
            <Icon name="users" :size="12" />
            <span>{{ matchingCount }} 人匹配中</span>
          </p>
        </div>

        <button v-if="waitingSub === 'searching'" type="button" class="cancel-btn" @click="onCancelMatch">
          取消匹配
        </button>
      </section>

      <!-- ====== Phase: 聊天中 ====== -->
      <section v-else-if="phase === 'chatting' && activeSession" class="chat-panel" :class="{ 'is-urgent': remainingSeconds <= 30 }">
        <!-- 倒计时背景水印（绝对定位，铺满整个聊天面板） -->
        <div class="chat-bg-countdown" aria-hidden="true">
          <span class="bg-countdown-num">{{ remainingDisplay }}</span>
          <span class="bg-countdown-label">剩余时间</span>
        </div>

        <!-- 聊天头部：对方信息 + 倒计时 -->
        <div class="chat-header">
          <div class="chat-peer">
            <img
              v-if="activeSession.peer?.avatar_url"
              :src="activeSession.peer.avatar_url"
              :alt="activeSession.peer?.nickname || '对方'"
              class="avatar avatar-md"
            />
            <span v-else class="avatar avatar-md" aria-hidden="true">{{ (activeSession.peer?.nickname || 'U').charAt(0) }}</span>
            <div class="peer-info">
              <span class="peer-name">{{ activeSession.peer?.nickname || '匿名同学' }}</span>
              <span class="peer-meta">
                <span>{{ ageLabel(activeSession.peer?.age) }}</span>
                <span class="meta-dot">·</span>
                <span>{{ genderLabel(activeSession.peer?.gender) }}</span>
              </span>
            </div>
          </div>
          <div class="chat-countdown" :class="{ 'is-urgent': remainingSeconds <= 30 }">
            <Icon name="clock" :size="14" />
            <span>{{ remainingDisplay }}</span>
          </div>
        </div>

        <!-- 互关状态提示 -->
        <div v-if="isMutualFollow" class="mutual-banner">
          <Icon name="user-check" :size="14" />
          <span>双方已同意互关，已成为好友！匹配结束后仍可在好友列表联系</span>
        </div>
        <!-- 对方已同意，等我同意 -->
        <div v-else-if="peerConsent && !myConsent" class="consent-banner consent-banner--peer">
          <Icon name="heart" :size="14" />
          <span>对方已同意互关，等你同意</span>
          <button type="button" class="banner-btn" @click="onConsent">同意互关</button>
        </div>
        <!-- 我已同意，等对方同意 -->
        <div v-else-if="myConsent && !peerConsent" class="consent-banner consent-banner--me">
          <Icon name="clock" :size="14" />
          <span>你已同意互关，等待对方同意...</span>
        </div>

        <!-- 消息列表 -->
        <div ref="messageListRef" class="message-list">
          <div
            v-for="msg in messages"
            :key="msg.id"
            class="message-item"
            :class="{ 'is-mine': isMyMessage(msg) }"
          >
            <div class="message-bubble">
              <p class="message-text">{{ msg.content }}</p>
            </div>
            <span class="message-time">{{ formatRelative(msg.created_at || '') }}</span>
          </div>
          <div v-if="!messages.length" class="message-empty">
            <Icon name="message-circle" :size="32" />
            <p>开始聊天吧～</p>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="chat-actions">
          <button
            v-if="!isMutualFollow && !myConsent"
            type="button"
            class="action-btn action-btn--consent"
            @click="onConsent"
          >
            <Icon name="user-check" :size="14" />
            <span>同意互关</span>
          </button>
          <button
            v-if="myConsent && !isMutualFollow"
            type="button"
            class="action-btn action-btn--disabled"
            disabled
          >
            <Icon name="check" :size="14" />
            <span>已同意，等对方</span>
          </button>
          <button
            v-if="isMutualFollow"
            type="button"
            class="action-btn action-btn--success"
            disabled
          >
            <Icon name="user-check" :size="14" />
            <span>已互关</span>
          </button>
          <button
            type="button"
            class="action-btn action-btn--danger"
            @click="onEndChat"
          >
            <Icon name="x" :size="14" />
            <span>结束</span>
          </button>
        </div>

        <!-- 输入区 -->
        <div class="chat-input-bar">
          <textarea
            v-model="inputMessage"
            class="chat-input"
            placeholder="输入消息，Enter 发送，Shift+Enter 换行"
            rows="1"
            maxlength="500"
            @keydown="onInputKeydown"
          ></textarea>
          <button
            type="button"
            class="send-btn"
            :disabled="!inputMessage.trim()"
            @click="onSend"
          >
            <Icon name="send" :size="16" />
          </button>
        </div>
      </section>

      <!-- ====== Phase: 结束 ====== -->
      <section v-else-if="phase === 'ended'" class="ended-panel">
        <div class="ended-hero">
          <div class="ended-icon" :class="{ 'is-mutual': isMutualFollow, 'is-peer-left': sessionEndedReason === 'peer_left' }">
            <Icon :name="isMutualFollow ? 'user-check' : (sessionEndedReason === 'peer_left' ? 'log-out' : 'clock')" :size="40" />
          </div>
          <h2 class="ended-title">
            {{ sessionEndedReason === 'peer_left' ? '对方已退出' : '匹配时间结束' }}
          </h2>
          <!-- 双方都同意 → 互关成功 -->
          <p v-if="isMutualFollow" class="ended-desc">
            你们已互相关注，成为好友<br/>可在「消息-好友」列表继续联系
          </p>
          <!-- 对方退出 -->
          <p v-else-if="sessionEndedReason === 'peer_left'" class="ended-desc">
            对方已退出网页<br/>聊天已结束
          </p>
          <!-- 未互关：区分双方同意状态 -->
          <p v-else-if="myConsent && !peerConsent" class="ended-desc">
            你已同意互关，但对方未同意<br/>本次未能成为好友
          </p>
          <p v-else-if="!myConsent && peerConsent" class="ended-desc">
            对方已同意互关，但你未同意<br/>本次未能成为好友
          </p>
          <p v-else-if="!myConsent && !peerConsent" class="ended-desc">
            双方均未同意互关<br/>本次未能成为好友
          </p>
          <p v-else class="ended-desc">
            匹配已结束<br/>未互关则无法再联系
          </p>
        </div>
        <div class="ended-actions">
          <!-- 互关成功：显示查看对方主页按钮 -->
          <button
            v-if="isMutualFollow && activeSession?.peer?.id"
            type="button"
            class="primary-btn"
            @click="goPeerProfile"
          >
            <Icon name="user" :size="16" />
            <span>查看对方主页</span>
          </button>
          <button type="button" class="primary-btn" @click="onBackToSetup">
            <Icon name="shuffle" :size="16" />
            <span>再来一次</span>
          </button>
          <button type="button" class="link-btn" @click="goBack">返回</button>
        </div>
      </section>
    </div>
  </main>
</template>

<style scoped>
*, *::before, *::after { box-sizing: border-box; }

.page-match {
  min-height: 100vh;
  background: linear-gradient(180deg, #f0eaff 0%, #f5f7fa 30%);
  padding-top: 56px;
  padding-bottom: calc(56px + 28px + env(safe-area-inset-bottom));
  color: var(--text-800);
  font-family: var(--font-sans, inherit);
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

/* 顶部固定栏 */
.site-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  height: 56px;
  background: var(--bg-50);
  border-bottom: 0.5px solid var(--bg-300);
}
.header-inner {
  max-width: 640px;
  margin: 0 auto;
  height: 100%;
  padding: 0 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.header-side {
  flex: 1;
  display: flex;
  align-items: center;
}
.header-side--left { justify-content: flex-start; }
.header-side--right { justify-content: flex-end; }
.header-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-800);
  margin: 0;
}
.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  color: var(--text-600);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: background 150ms;
}
.icon-btn:hover { background: var(--bg-100); }

.page-container {
  max-width: 640px;
  margin: 0 auto;
  padding: 16px;
  /* 减去顶部 header(56px) + 底部 TabBar(70px=14px offset+56px) + 呼吸空间(14px) */
  height: calc(100vh - 56px - 84px);
  display: flex;
  flex-direction: column;
}

/* ============ 设置面板 ============ */
.setup-panel {
  flex: 1;
  overflow-y: auto;
}
.setup-hero {
  text-align: center;
  padding: 24px 20px;
  margin-bottom: 16px;
}
.hero-icon {
  width: 80px;
  height: 80px;
  margin: 0 auto 16px;
  border-radius: 50%;
  background: linear-gradient(135deg, #af52de, #5856d6);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-md);
}
.hero-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-800);
  margin: 0 0 8px;
}
.hero-desc {
  font-size: 13px;
  color: var(--text-500);
  line-height: 1.6;
  margin: 0;
}

.form-card {
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  padding: 18px 16px;
  box-shadow: var(--shadow-xs);
  margin-bottom: 16px;
}
.form-group {
  margin-bottom: 16px;
}
.form-label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-700);
  margin-bottom: 8px;
}
.required {
  color: #ff3b30;
  margin-left: 2px;
}
.form-hint-inline {
  font-size: 11px;
  color: var(--text-400);
  font-weight: 400;
  margin-left: 6px;
}
.form-warn {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 6px 0 0;
  font-size: 11px;
  color: #ff6b35;
}
.option-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.option-chip {
  padding: 6px 14px;
  border-radius: 999px;
  font-size: 13px;
  color: var(--text-600);
  background: var(--bg-100);
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 150ms;
}
.option-chip:hover { background: var(--bg-200); }
.option-chip.is-active {
  color: var(--brand-600);
  background: var(--brand-50);
  border-color: var(--brand-500);
  font-weight: 600;
}

/* ============ 年龄范围选择 ============ */
.age-range-row {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.age-range-side {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.age-side-label {
  font-size: 12px;
  color: var(--text-500);
  font-weight: 600;
  min-width: 36px;
  flex-shrink: 0;
}
.age-chip {
  min-width: 44px;
  text-align: center;
  padding: 6px 10px;
}
.clear-age-btn {
  margin-top: 8px;
  padding: 4px 10px;
  border: none;
  background: transparent;
  color: var(--text-400);
  font-size: 12px;
  cursor: pointer;
  text-decoration: underline;
}
.clear-age-btn:hover {
  color: var(--brand-600);
}

/* ============ 三态标签样式 ============ */
.tag-legend {
  display: flex;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 11px;
  color: var(--text-400);
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 1.5px solid var(--bg-300);
}
.legend-default { background: var(--bg-100); }
.legend-prefer { background: #fff8e6; border-color: #ffd60a; }
.legend-required { background: #ffedef; border-color: #ff3b30; }
.tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.tag-chip .tag-name { font-size: 13px; }
.tag-chip.tag-state-prefer {
  background: #fff8e6;
  color: #b8860b;
  border-color: #ffd60a;
  font-weight: 600;
}
.tag-chip.tag-state-required {
  background: #ffedef;
  color: #ff3b30;
  border-color: #ff3b30;
  font-weight: 700;
}
.tag-state-badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 4px;
  font-weight: 600;
  line-height: 1.3;
}
.tag-state-badge--prefer { background: #ffd60a; color: #fff; }
.tag-state-badge--required { background: #ff3b30; color: #fff; }

.primary-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  padding: 12px;
  border: none;
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, #af52de, #5856d6);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 150ms;
  margin-top: 8px;
}
.primary-btn:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.setup-tips {
  background: var(--bg-50);
  border-radius: var(--radius-md);
  padding: 14px 16px;
  box-shadow: var(--shadow-xs);
}
.tips-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-700);
  margin: 0 0 8px;
}
.tips-list {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--text-500);
  line-height: 1.8;
}

/* ============ 等待面板 ============ */
.waiting-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 32px;
}
.waiting-hero {
  text-align: center;
}
.waiting-ring {
  position: relative;
  width: 120px;
  height: 120px;
  margin: 0 auto 24px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.waiting-ring--outer,
.waiting-ring--inner {
  position: absolute;
  border-radius: 50%;
  border: 2px solid #af52de;
}
.waiting-ring--outer {
  width: 120px;
  height: 120px;
  animation: ring-spread 1.8s ease-out infinite;
}
.waiting-ring--inner {
  width: 120px;
  height: 120px;
  animation: ring-spread 1.8s ease-out 0.6s infinite;
}
@keyframes ring-spread {
  0% { transform: scale(0.6); opacity: 0.8; }
  100% { transform: scale(1.3); opacity: 0; }
}
.waiting-icon {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: linear-gradient(135deg, #af52de, #5856d6);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
  box-shadow: var(--shadow-md);
  transition: background 300ms;
}
/* 匹配成功状态：图标变绿色，环停止扩散并变绿 */
.waiting-ring.ring-matched .waiting-ring--outer,
.waiting-ring.ring-matched .waiting-ring--inner {
  border-color: #34c759;
  animation: none;
  opacity: 0;
}
.waiting-ring.ring-matched .waiting-icon {
  background: linear-gradient(135deg, #34c759, #30b866);
  animation: matched-bounce 600ms ease-out;
}
@keyframes matched-bounce {
  0% { transform: scale(0.8); }
  50% { transform: scale(1.15); }
  100% { transform: scale(1); }
}
.waiting-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-800);
  margin: 0 0 8px;
}
.waiting-desc {
  font-size: 13px;
  color: var(--text-500);
  margin: 0 0 6px;
}
.waiting-time {
  font-size: 13px;
  color: var(--text-500);
  margin: 0;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  letter-spacing: 0.5px;
}
.waiting-count {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #af52de;
  background: #f3e8ff;
  padding: 4px 10px;
  border-radius: 999px;
  margin: 8px 0 0;
  font-weight: 600;
}
.cancel-btn {
  padding: 10px 32px;
  border: 1px solid var(--bg-300);
  background: var(--bg-50);
  color: var(--text-600);
  font-size: 14px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 150ms;
}
.cancel-btn:hover {
  background: var(--bg-100);
}

/* ============ 聊天面板 ============ */
.chat-panel {
  position: relative;  /* 给倒计时水印提供定位基准 */
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  gap: 10px;
  overflow: hidden;  /* 水印不溢出 */
}

/* 倒计时背景水印：绝对定位，铺满整个 chat-panel */
.chat-bg-countdown {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  pointer-events: none;  /* 不阻挡交互 */
  z-index: 0;            /* 在所有内容下方 */
  user-select: none;
  opacity: 0.08;
  gap: 4px;
}
.bg-countdown-num {
  font-size: 160px;
  font-weight: 900;
  line-height: 1;
  color: #af52de;
  font-variant-numeric: tabular-nums;
  letter-spacing: -4px;
  font-family: var(--font-metric, 'SF Mono', 'Menlo', monospace);
}
.bg-countdown-label {
  font-size: 14px;
  font-weight: 600;
  color: #5856d6;
  letter-spacing: 2px;
}
/* 倒计时进入紧急状态时（<=30s），背景水印变红 */
.chat-bg-countdown.is-urgent .bg-countdown-num,
.chat-bg-countdown.is-urgent .bg-countdown-label {
  color: #ff3b30;
}
/* 紧急态通过父级 class 同步触发（在 chat-panel 上加 is-urgent） */
.chat-panel.is-urgent .chat-bg-countdown {
  opacity: 0.12;
}
.chat-panel.is-urgent .bg-countdown-num,
.chat-panel.is-urgent .bg-countdown-label {
  color: #ff3b30;
}

/* 让 chat-panel 内其他直接子元素 z-index 高于水印 */
.chat-panel > :not(.chat-bg-countdown) {
  position: relative;
  z-index: 1;
}
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  background: var(--bg-50);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-xs);
}
.chat-peer {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: linear-gradient(135deg, #af52de, #5856d6);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  flex-shrink: 0;
  overflow: hidden;
}
.avatar-md { width: 40px; height: 40px; }
.avatar img { object-fit: cover; width: 100%; height: 100%; }
.peer-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.peer-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-800);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.peer-meta {
  font-size: 11px;
  color: var(--text-400);
  display: flex;
  align-items: center;
  gap: 4px;
}
.meta-dot {
  color: var(--text-300);
}
.chat-countdown {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: #e9f9ee;
  color: #34c759;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}
.chat-countdown.is-urgent {
  background: #ffecea;
  color: #ff3b30;
  animation: urgent-pulse 1s ease-in-out infinite;
}
@keyframes urgent-pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.05); }
}

.mutual-banner {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #e9f9ee;
  color: #34c759;
  border-radius: var(--radius-sm);
  font-size: 12px;
}
/* 同意互关状态横幅 */
.consent-banner {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: 12px;
}
.consent-banner--peer {
  background: #fff3e6;
  color: #d26510;
}
.consent-banner--me {
  background: #e8f2ff;
  color: #0064d6;
}
.banner-btn {
  margin-left: auto;
  padding: 4px 10px;
  background: #ff9500;
  color: #fff;
  border: none;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}
.banner-btn:hover { background: #ff6b35; }

.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  background: var(--bg-50);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-xs);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.message-item {
  display: flex;
  flex-direction: column;
  max-width: 75%;
}
.message-item.is-mine {
  align-self: flex-end;
  align-items: flex-end;
}
.message-bubble {
  padding: 8px 12px;
  border-radius: 14px;
  background: var(--bg-100);
  color: var(--text-800);
  font-size: 14px;
  word-break: break-word;
}
.message-item.is-mine .message-bubble {
  background: var(--brand-500);
  color: #fff;
}
.message-text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}
.message-time {
  font-size: 10px;
  color: var(--text-400);
  margin-top: 4px;
}
.message-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: auto;
  color: var(--text-400);
  font-size: 13px;
}

.chat-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border: 1px solid var(--bg-300);
  background: var(--bg-50);
  color: var(--text-700);
  font-size: 12px;
  border-radius: 999px;
  cursor: pointer;
  transition: all 150ms;
}
.action-btn:hover { background: var(--bg-100); }
.action-btn--secondary {
  color: #ff9500;
  border-color: #ff9500;
}
.action-btn--secondary:hover { background: #fff3e6; }
/* 同意互关按钮：紫色主色 */
.action-btn--consent {
  color: #fff;
  background: linear-gradient(135deg, #af52de, #5856d6);
  border-color: transparent;
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(175, 82, 222, 0.25);
}
.action-btn--consent:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(175, 82, 222, 0.35);
}
.action-btn--danger {
  color: #ff3b30;
  border-color: #ff3b30;
  margin-left: auto;
}
.action-btn--danger:hover { background: #ffecea; }
.action-btn--success {
  color: #34c759;
  border-color: #34c759;
  cursor: default;
}
.action-btn--disabled {
  color: var(--text-400);
  cursor: default;
}

.chat-input-bar {
  display: flex;
  gap: 8px;
  padding: 8px;
  background: var(--bg-50);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-xs);
}
.chat-input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--bg-300);
  border-radius: var(--radius-sm);
  font-size: 14px;
  font-family: inherit;
  background: var(--bg-50);
  color: var(--text-800);
  outline: none;
  resize: none;
  min-height: 36px;
  max-height: 100px;
  transition: border-color 150ms;
}
.chat-input:focus { border-color: var(--brand-500); }
.send-btn {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  background: var(--brand-500);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 150ms;
}
.send-btn:hover:not(:disabled) { background: var(--brand-600); }
.send-btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* ============ 结束面板 ============ */
.ended-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 32px;
}
.ended-hero {
  text-align: center;
}
.ended-icon {
  width: 80px;
  height: 80px;
  margin: 0 auto 16px;
  border-radius: 50%;
  background: var(--bg-200);
  color: var(--text-500);
  display: flex;
  align-items: center;
  justify-content: center;
}
.ended-icon.is-mutual {
  background: #e9f9ee;
  color: #34c759;
}
.ended-icon.is-peer-left {
  background: #ffecea;
  color: #ff3b30;
}
.ended-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-800);
  margin: 0 0 8px;
}
.ended-desc {
  font-size: 13px;
  color: var(--text-500);
  line-height: 1.6;
  margin: 0;
}
.ended-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  width: 100%;
  max-width: 280px;
}
.link-btn {
  background: none;
  border: none;
  color: var(--text-500);
  font-size: 13px;
  cursor: pointer;
  padding: 6px 12px;
}
.link-btn:hover { color: var(--text-700); }

/* 移动端适配 */
@media (max-width: 768px) {
  .page-match {
    padding-top: 48px;
  }
  .site-header { height: 48px; }
  .header-title { font-size: 16px; }
  .page-container { padding: 12px; height: calc(100vh - 48px - 84px); }
  .hero-icon { width: 64px; height: 64px; }
  .hero-title { font-size: 18px; }
  .option-chip { padding: 5px 12px; font-size: 12px; }
  .chat-countdown { font-size: 12px; padding: 5px 10px; }

  /* 聊天面板：确保输入框始终可见，不被 TabBar 遮挡 */
  .chat-panel {
    height: calc(100vh - 48px - 84px);
  }
  /* 消息列表可滚动，输入区固定在底部 */
  .message-list {
    flex: 1;
    min-height: 0;
    -webkit-overflow-scrolling: touch;
  }
  .chat-input-bar {
    /* 输入栏始终固定在视口底部，不被键盘遮挡 */
    flex-shrink: 0;
    position: sticky;
    bottom: 0;
    padding: 8px;
    background: var(--bg-50);
    box-shadow: 0 -1px 8px rgba(0, 0, 0, 0.04);
    z-index: 10;
  }
  .chat-input {
    font-size: 16px; /* >=16px 防止 iOS 自动缩放 */
    min-height: 38px;
  }
  .send-btn {
    width: 38px;
    height: 38px;
  }
  /* 聊天操作按钮在移动端紧凑显示 */
  .chat-actions {
    flex-shrink: 0;
  }
}

/* 超小屏（手机竖屏）进一步优化 */
@media (max-width: 380px) {
  .chat-header {
    padding: 8px 10px;
  }
  .avatar-md { width: 34px; height: 34px; }
  .peer-name { font-size: 13px; }
  .chat-countdown { font-size: 11px; padding: 4px 8px; }
  .bg-countdown-num { font-size: 120px; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
  }
}

/* ====== 首次资料填写弹窗 ====== */
.profile-setup-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.profile-setup-modal {
  width: 100%;
  max-width: 380px;
  background: var(--bg-50, #fff);
  border-radius: 20px;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  display: flex;
  flex-direction: column;
}
.profile-setup-head {
  padding: 22px 22px 12px;
  text-align: center;
  background: linear-gradient(135deg, #4a9eff, #2575fc);
  color: #fff;
}
.profile-setup-title {
  margin: 0 0 6px;
  font-size: 18px;
  font-weight: 700;
}
.profile-setup-desc {
  margin: 0;
  font-size: 12px;
  opacity: 0.9;
}
.profile-setup-body {
  padding: 20px 22px 8px;
}
.setup-field {
  margin-bottom: 18px;
}
.setup-field-label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-700, #444);
  margin-bottom: 10px;
}
.setup-gender-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.setup-gender-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 14px 8px;
  border: 1.5px solid var(--bg-300, #e0e0e0);
  border-radius: 14px;
  background: var(--bg-50, #fff);
  color: var(--text-600, #666);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 180ms;
}
.setup-gender-btn:hover {
  border-color: #4a9eff;
}
.setup-gender-btn.is-active {
  border-color: #4a9eff;
  background: #eaf4ff;
  color: #2575fc;
  font-weight: 700;
  box-shadow: 0 2px 8px rgba(74, 158, 255, 0.2);
}
.setup-date-input {
  width: 100%;
  padding: 11px 12px;
  border: 1.5px solid var(--bg-300, #e0e0e0);
  border-radius: 10px;
  background: var(--bg-50, #fff);
  color: var(--text-800, #333);
  font-size: 14px;
  font-family: inherit;
  outline: none;
  transition: all 180ms;
}
.setup-date-input:focus {
  border-color: #4a9eff;
  box-shadow: 0 2px 8px rgba(74, 158, 255, 0.15);
}
.setup-field-tip {
  margin: 6px 0 0;
  font-size: 11px;
  color: var(--text-400, #999);
}
.setup-once-tip {
  display: flex;
  align-items: center;
  gap: 5px;
  margin: 4px 0 0;
  padding: 8px 10px;
  background: #fff4e5;
  border-radius: 8px;
  font-size: 11px;
  color: #ff9500;
  font-weight: 500;
}
.profile-setup-foot {
  padding: 8px 22px 20px;
}
.setup-submit-btn {
  width: 100%;
  padding: 13px;
  border: none;
  border-radius: 12px;
  background: linear-gradient(135deg, #4a9eff, #2575fc);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 180ms;
}
.setup-submit-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(74, 158, 255, 0.35);
}
.setup-submit-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
/* 进入/离开动画 */
.profile-setup-enter-active,
.profile-setup-leave-active {
  transition: opacity 220ms ease;
}
.profile-setup-enter-active .profile-setup-modal,
.profile-setup-leave-active .profile-setup-modal {
  transition: transform 280ms cubic-bezier(0.34, 1.56, 0.64, 1), opacity 220ms ease;
}
.profile-setup-enter-from,
.profile-setup-leave-to {
  opacity: 0;
}
.profile-setup-enter-from .profile-setup-modal,
.profile-setup-leave-to .profile-setup-modal {
  transform: scale(0.85);
  opacity: 0;
}
</style>
