<script setup lang="ts">
/**
 * 桌面漂浮宠物（重构版）
 * - 默认静止待机（stand），不会自动走动
 * - 宠物主动发起需求：定时轮询后端状态，冷却结束后弹出请求气泡（饿了/想玩/想被摸）
 * - 用户点击气泡中的按钮响应互动（喂食/玩耍/摸摸头），有冷却防刷
 * - 单击宠物：宠物做个开心动作，不弹菜单
 * - 长按/右键：弹出极简菜单（换一只/去商城/收进窝）
 * - 拖拽移动 + 重力坠落（保留原有物理系统）
 * - 好感度心心气泡反馈
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session'
import {
  feedPet,
  interactPet,
  listMyBag,
  listMyPets,
  getPetStatus,
  tapPet,
  affinityLevel,
  type BagItem,
  type MyPetItem,
  type PetDrop,
  type PetStatusResp,
} from '../api/petShop'
import PetAnimation from './pet/PetAnimation.vue'
import { fetchPublicSettings } from '../api/settings'
import { petAiState } from '../api/petAi'

const HIDDEN_KEY = 'floating_pet_hidden'
const PET_KEY = 'floating_pet_id'
const POS_KEY = 'floating_pet_pos'

const session = useSessionStore()
const route = useRoute()
const router = useRouter()

const pets = ref<MyPetItem[]>([])
const petIndex = ref(0)
const currentPet = computed(() => pets.value[petIndex.value] ?? null)

const bag = ref<BagItem[]>([])
const bagTotal = computed(() => bag.value.reduce((n, b) => n + b.qty, 0))
// 食物选择面板：可喂的粮食（道具且带饱腹/好感）
const feedOpen = ref(false)
const feedingId = ref<number | null>(null)
const feedItems = computed(() =>
  bag.value.filter(
    (b) => b.kind === 2 && ((b.attrs?.satiety ?? 0) > 0 || (b.affinity_gain ?? 0) > 0),
  ),
)

/** 是否为真实图片地址（道具的 image_url 可能存的是 emoji 占位符）；同时作为 TS 类型收窄 */
function isImageUrl(url: string | null | undefined): url is string {
  return !!url && (url.startsWith('/') || url.startsWith('http'))
}
const hearts = computed(() => affinityLevel(currentPet.value?.affinity ?? 0))
const affinityPct = computed(() => Math.min(100, currentPet.value?.affinity ?? 0))

const hidden = ref(localStorage.getItem(HIDDEN_KEY) === '1')
const petRef = ref<InstanceType<typeof PetAnimation> | null>(null)

// ====== 位置与拖拽 ======
const PET_SIZE = 120
const pos = ref({ x: 0, y: 0 })
const vw = ref(typeof window !== 'undefined' ? window.innerWidth || 375 : 375)
const inited = ref(false)
const mode = ref<'idle' | 'action' | 'drag' | 'fall'>('idle')
const direction = ref<1 | -1>(1)
// 重力系数（后台可调，默认 0.5）；tick 中读取 gravity.value
const gravity = ref(0.5)
const FLOOR_GAP = 8
let fallVy = 0
// 非垂直下落物理量：水平漂移速度（仅保留一点点拖拽惯性）
let fallVx = 0
let fallAng = 0
let fallAngV = 0
// 呈现在页面上的额外旋转角（deg，仅下落时非 0；落地归零保持直立）
const bodyRot = ref(0)

// ====== 需求气泡倒计时（我想要… 还剩 X 秒） ======
const needRemain = ref(0)
const NEED_SECONDS = 12
let needCountdownTimer: number | null = null

function startNeedCountdown() {
  stopNeedCountdown()
  needRemain.value = NEED_SECONDS
  needCountdownTimer = window.setInterval(() => {
    needRemain.value -= 1
    if (needRemain.value <= 0) {
      needRemain.value = 0
      clearBubble()
    }
  }, 1000)
}

function stopNeedCountdown() {
  if (needCountdownTimer !== null) {
    window.clearInterval(needCountdownTimer)
    needCountdownTimer = null
  }
}

// ====== 气泡边界适配 ======
// 宠物贴边时气泡自动换方向：上半屏 → 气泡放下方；贴左/右边缘 → 气泡左/右对齐
const bubbleCls = computed(() => {
  const cls: string[] = []
  if (pos.value.y < 180) cls.push('is-bottom')
  if (pos.value.x < 110) cls.push('is-left')
  else if (pos.value.x > Math.max(0, vw.value - PET_SIZE - 110)) cls.push('is-right')
  return cls
})

function floorY() {
  return Math.max(0, window.innerHeight - PET_SIZE - FLOOR_GAP)
}

// ====== 地面感知：优先页面自定义地面（如聊天页输入框），否则底部导航栏 ======
// 桌面 Tab 栏为悬浮胶囊（bottom:14px、高56px），不占满整宽；移动端 bottom:0、高度 52px+safe-area。
// 聊天页（/pet-chat）隐藏了底部导航栏，改为给输入框加 data-pet-ground 作为"地面"，
// 让宠物降落在输入框顶边而非浏览器最底部。
// 直接测量元素矩形区域（top/left/right），避免硬编码导致"踏空/抽搐"。
// 测量值缓存，仅在 resize / 路由变化时刷新，避免每帧 DOM 查询。
let tabRectCache: { top: number; bottom: number; left: number; right: number } | null = null
let groundRectCache: { top: number; bottom: number; left: number; right: number } | null = null
function refreshTabBar() {
  tabRectCache = null
  groundRectCache = null
  if (typeof document === 'undefined') return
  // 页面自定义地面优先（整宽），如宠物聊天页输入框
  const groundEl = document.querySelector<HTMLElement>('[data-pet-ground]')
  if (groundEl) {
    const rg = groundEl.getBoundingClientRect()
    if (Number.isFinite(rg.top) && rg.top >= 0 && Number.isFinite(rg.left) && Number.isFinite(rg.right) && Number.isFinite(rg.bottom)) {
      groundRectCache = { top: rg.top, bottom: rg.bottom, left: rg.left, right: rg.right }
      return
    }
  }
  const el = document.querySelector<HTMLElement>('.bottom-tabbar')
  if (!el) return
  const r = el.getBoundingClientRect()
  if (Number.isFinite(r.top) && r.top >= 0 && Number.isFinite(r.left) && Number.isFinite(r.right) && Number.isFinite(r.bottom)) {
    tabRectCache = { top: r.top, bottom: r.bottom, left: r.left, right: r.right }
  }
}
function hasTabBar(): boolean {
  if (!tabRectCache && !groundRectCache) refreshTabBar()
  return !!tabRectCache
}
/** 当前页面宠物所在横向区间是否正下方有导航栏 */
function overTabBar(bx: number): boolean {
  if (!tabRectCache && !groundRectCache) refreshTabBar()
  if (groundRectCache) return true // 自定义地面整宽，正下方始终为地面
  const t = tabRectCache
  if (!t) return false
  return bx + PET_SIZE > t.left && bx < t.right
}
/**
 * 地面 y 坐标（宠物顶部落点）：
 * - 页面有自定义地面（data-pet-ground，如聊天页输入框）→ 抬升到其顶边（整宽）
 * - 水平区间正下方有导航栏 → 抬升地面到导航栏顶边（直接停下）
 * - 正下方没有导航栏（如电脑导航栏不占整宽，宠物在胶囊旁 / 或该页无导航栏）→ 落到浏览器最底部
 */
function barrierY(bx?: number): number {
  if (!tabRectCache && !groundRectCache) refreshTabBar()
  const x = bx ?? pos.value.x
  if (groundRectCache) {
    return Math.max(0, groundRectCache.top - PET_SIZE)
  }
  if (overTabBar(x)) {
    return tabRectCache ? Math.max(0, tabRectCache.top - PET_SIZE) : floorY()
  }
  return floorY()
}

function savedPos() {
  try {
    const raw = localStorage.getItem(POS_KEY)
    if (!raw) return null
    const p = JSON.parse(raw)
    if (typeof p.x === 'number' && typeof p.y === 'number') return p
  } catch { /* ignore */ }
  return null
}

function clampPos(p: { x: number; y: number }) {
  const maxX = Math.max(0, window.innerWidth - PET_SIZE)
  // 底部边界跟随"地面"：按宠物当前横向位置判断正下方是否有导航栏再定落点
  const maxY = barrierY(p.x)
  return { x: Math.min(Math.max(p.x, 0), maxX), y: Math.min(Math.max(p.y, 0), maxY) }
}

/**
 * 撞墙（请求9）：拖动时宠物矩形不允许侵入底部导航栏区域，模拟"撞墙"。
 * - 垂直墙：宠物水平跨过导航栏区间时，往下拖会被挡在导航栏顶边之上
 * - 水平墙：宠物纵向已压到导航栏高度带时，横向拖也会被导航栏左右边界挡住
 */
function wallClamp(x: number, y: number): { x: number; y: number } {
  let gx = x
  let gy = y
  if (groundRectCache) {
    // 页面自定义地面（整宽）：宠物底边不允许低于地面顶边
    if (gy + PET_SIZE > groundRectCache.top) gy = groundRectCache.top - PET_SIZE
  } else if (tabRectCache) {
    const t = tabRectCache
    // 垂直墙：宠物水平跨过导航栏区间且底边低于导航栏顶边 → 挡在顶边上
    if (gx + PET_SIZE > t.left && gx < t.right && gy + PET_SIZE > t.top) {
      gy = Math.min(gy, t.top - PET_SIZE)
    }
    // 水平墙：宠物纵向区间与导航栏高度带相交时，不能横向侵入导航栏左右边界
    if (gy + PET_SIZE > t.top && gy < t.bottom) {
      if (gx + PET_SIZE > t.left && gx < t.left) gx = t.left - PET_SIZE
      else if (gx < t.right && gx + PET_SIZE > t.right) gx = t.right
    }
  }
  return clampPos({ x: gx, y: gy })
}

function initPos() {
  const saved = savedPos()
  if (saved && (saved.x > 10 || saved.y > 10)) {
    pos.value = clampPos(saved)
    userPlaced = true
  } else {
    // 首次出现：在可视范围内随机横向位置（不要每次都放右上角，避免"总飘到右边"）
    const maxX = Math.max(20, window.innerWidth - PET_SIZE - 24)
    const startX = 12 + Math.random() * maxX
    pos.value = clampPos({ x: startX, y: barrierY(startX) })
  }
  inited.value = true
}

let userPlaced = false

function ensurePos() {
  if (window.innerWidth < 60 || window.innerHeight < 60) {
    window.setTimeout(ensurePos, 600)
    return
  }
  if (!inited.value || !userPlaced) initPos()
  else pos.value = clampPos(pos.value)
}

// ====== 动作控制 ======
function hasAction(key: string): boolean {
  return !!currentPet.value?.anim?.actions.some((a) => a.key === key)
}

function playAction(key: string) {
  petRef.value?.switchAction(key)
}

function playActionOnce(key: string, duration = 2500) {
  playAction(key)
  window.setTimeout(() => {
    if (mode.value === 'action') {
      mode.value = 'idle'
      playAction('stand')
    }
  }, duration)
}

// ====== 气泡系统 ======
const bubble = ref('')
const bubbleType = ref<'chat' | 'need' | 'feedback'>('chat')
const needAction = ref<'feed' | 'play' | 'pet' | null>(null)
let bubbleTimer: number | null = null

function say(text: string, type: 'chat' | 'feedback' = 'chat', duration = 2800) {
  clearBubble()
  bubble.value = text
  bubbleType.value = type
  needAction.value = null
  bubbleTimer = window.setTimeout(() => clearBubble(), duration)
}

function clearBubble() {
  bubble.value = ''
  needAction.value = null
  stopNeedCountdown()
  if (bubbleTimer !== null) {
    window.clearTimeout(bubbleTimer)
    bubbleTimer = null
  }
}

/** 需求气泡过期调度：拖拽中不消失（延后再查），其余情况 12 秒后自动收起 */
function scheduleNeedExpiry() {
  bubbleTimer = window.setTimeout(() => {
    if (mode.value === 'drag') {
      scheduleNeedExpiry()
      return
    }
    clearBubble()
  }, 12000)
}

/** 显示需求气泡（带操作按钮）；若该项互动仍在冷却，则不弹出，避免点了被拒绝 */
function showNeedBubble(need: 'feed' | 'play' | 'pet') {
  if (!currentPet.value || aiSleeping.value) return
  const cd = currentPet.value.cooldowns?.[need] ?? 0
  if (cd > 0) return // 还在冷却：别引导点击
  clearBubble()
  needAction.value = need
  bubbleType.value = 'need'
  const satiety = currentPet.value?.satiety ?? 100
  const texts: Record<string, string> = {
    feed: satiety < 30 ? '饿得没力气了… 快喂喂我！' : '好饿呀~ 想吃东西！',
    play: '好无聊~ 陪我玩嘛！',
    pet: '摸摸头嘛~',
  }
  bubble.value = texts[need] || ''
  scheduleNeedExpiry()
  startNeedCountdown()
  // 配合做个小动画
  if (need === 'play' && hasAction('interact')) {
    playAction('interact')
    window.setTimeout(() => {
      if (mode.value !== 'action') playAction('stand')
    }, 1500)
  }
}

// ====== 状态轮询（检测宠物需求） ======
let statusTimer: number | null = null
const STATUS_POLL_INTERVAL = 25000 // 25秒轮询一次
const NEED_CHECK_MIN_INTERVAL = 20000 // 两次需求之间最少间隔20秒
let lastNeedCheck = 0

async function checkPetStatus() {
  if (!currentPet.value || !session.isLoggedIn() || hidden.value) return
  if (aiSleeping.value) return // 睡着不产生需求气泡
  if (mode.value === 'drag' || mode.value === 'fall' || mode.value === 'action') return
  try {
    const { data: resp } = await getPetStatus(currentPet.value.id, { showGlobalLoading: false, showGlobalError: false })
    const data: PetStatusResp = resp.data
    // 更新宠物本地状态
    const pet = pets.value[petIndex.value]
    if (pet) {
      pet.affinity = data.pet.affinity
      pet.level = data.pet.level
      pet.cooldowns = data.pet.cooldowns
      pet.daily_affinity = data.pet.daily_affinity
      if (data.pet.satiety !== undefined) pet.satiety = data.pet.satiety
      if (data.pet.mood !== undefined) pet.mood = data.pet.mood
    }
    // 如果有需求且距离上次需求检查够久了，显示气泡；只显示"冷却已过"的需求，避免"弹出要摸结果要冷却"
    const now = Date.now()
    const activeCd = (data.cooldowns?.[data.need as 'feed' | 'play' | 'pet'] ?? 0) as number
    if (data.need !== 'none' && activeCd <= 0 && now - lastNeedCheck > NEED_CHECK_MIN_INTERVAL && bubble.value === '') {
      lastNeedCheck = now
      showNeedBubble(data.need as 'feed' | 'play' | 'pet')
    }
  } catch { /* 静默 */ }
}

function startStatusPolling() {
  if (statusTimer !== null) window.clearInterval(statusTimer)
  // 首次等5秒再检查（给页面加载时间）
  window.setTimeout(checkPetStatus, 5000)
  statusTimer = window.setInterval(checkPetStatus, STATUS_POLL_INTERVAL)
}

// ====== AI 睡觉状态（宠物睡着 → 悬浮宠也播放睡眠，且不产生互动） ======
const aiSleeping = ref(false)
let aiSleepTimer: number | null = null

/** 查询当前宠物 AI 是否在睡觉（静默失败，非 AI 宠物/未开启时保持 false） */
async function checkAiSleep() {
  if (!currentPet.value || !session.isLoggedIn()) return
  try {
    const { data: resp } = await petAiState(currentPet.value.id)
    aiSleeping.value = !!resp.data?.sleeping
  } catch { /* 静默 */ }
}

function startAiSleepPolling() {
  if (aiSleepTimer !== null) window.clearInterval(aiSleepTimer)
  window.setTimeout(checkAiSleep, 4000)
  aiSleepTimer = window.setInterval(checkAiSleep, 25000)
}

// 睡着 → 一直播放睡眠动作；睡醒 → 恢复待机
watch(aiSleeping, (v) => {
  if (!currentPet.value) return
  clearBubble()
  if (v) {
    if (hasAction('sleep')) {
      mode.value = 'action'
      playAction('sleep')
    }
  } else {
    mode.value = 'idle'
    playAction('stand')
  }
})

// ====== 随机闲聊（会体现当前饱食度 / 小情绪，让"会饿、有情绪"看得见） ======
const IDLE_LINES = [
  '今天天气真好呀~', '你终于来看我啦！', '哼，才不想你呢。', 'Zzz...', '在看什么呢？',
]
const HUNGRY_LINES = ['肚子咕咕叫…', '好想吃点东西呀~', '有点没力气啦…', '主人~我饿饿！']
const STUFFED_LINES = ['吃得好饱~开心！', '元气满满！', '今天也超有精神~']

function idleLine(): string {
  const satiety = currentPet.value?.satiety ?? 100
  const mood = currentPet.value?.mood || ''
  if (satiety < 30) {
    return HUNGRY_LINES[Math.floor(Math.random() * HUNGRY_LINES.length)]
  }
  if (satiety < 60) {
    // 有点饿：偶尔也聊聊天，但透露"小情绪"
    if (Math.random() < 0.5) return HUNGRY_LINES[Math.floor(Math.random() * HUNGRY_LINES.length)]
    return mood || IDLE_LINES[Math.floor(Math.random() * IDLE_LINES.length)]
  }
  if (Math.random() < 0.4 && mood) return STUFFED_LINES[Math.floor(Math.random() * STUFFED_LINES.length)]
  return IDLE_LINES[Math.floor(Math.random() * IDLE_LINES.length)]
}

let chatTimer: number | null = null
function startChatter() {
  if (chatTimer !== null) window.clearInterval(chatTimer)
  chatTimer = window.setInterval(() => {
    if (mode.value === 'idle' && !bubble.value && !aiSleeping.value && Math.random() < 0.28) {
      say(idleLine(), 'chat', 2500)
    }
  }, 26000)
}

// ====== 主动随机动作 + 长停留页面反应 ======
// 让悬浮宠物更有"生命力"：待机时偶尔自己走动/玩耍/睡觉；
// 长时间（≥2分钟）停留在页面无人操作时，更大概率进入舒缓养神/睡觉动作，体现"有人陪着却不理我"的依赖感。
let lastUserAction = Date.now()
/** 任何用户触摸宠物（点击/拖拽/互动按钮）都会刷新，重置"长时间未操作"判定 */
function markInteract() {
  lastUserAction = Date.now()
}

const IDLE_ACTION_KEYS = ['walk', 'interact', 'fly', 'sleep']

/** 随机播放一个可用动作一小段时间后回到待机 */
function playRandomAction() {
  if (mode.value !== 'idle' || bubble.value || menuOpen.value || aiSleeping.value || !currentPet.value) return
  const keys = IDLE_ACTION_KEYS.filter(k => hasAction(k))
  if (!keys.length) return
  const key = keys[Math.floor(Math.random() * keys.length)]
  mode.value = 'action'
  playActionOnce(key, 2200 + Math.random() * 1800)
}

let idleActionTimer: number | null = null
function startIdleActions() {
  if (idleActionTimer !== null) window.clearInterval(idleActionTimer)
  idleActionTimer = window.setInterval(() => {
    if (!visible.value || mode.value !== 'idle' || bubble.value || menuOpen.value || aiSleeping.value) return
    const idleMs = Date.now() - lastUserAction
    if (idleMs > 120000) {
      // 长时间停留页面：大概率进入"睡觉/走动/发呆"的舒缓动作（时长更久）
      if (Math.random() < 0.68) {
        const key = hasAction('sleep') ? 'sleep' : hasAction('walk') ? 'walk' : 'interact'
        mode.value = 'action'
        playActionOnce(key, 7000 + Math.random() * 5000)
      }
      return
    }
    // 正常待机：小概率随机活动一下（动作姿态切换，不打扰）
    if (Math.random() < 0.3) playRandomAction()
  }, 18000)
}

// ====== 互动操作 ======
const acting = ref(false)

/** 食物图片加载失败（如链接失效）→ 换成 emoji 占位，避免破图 */
function onFeedImgError(e: Event) {
  const img = e.target as HTMLImageElement
  if (img && img.parentElement) {
    img.style.display = 'none'
    const span = document.createElement('span')
    span.className = 'fppet-feed__emoji'
    span.textContent = '🍗'
    img.parentElement.insertBefore(span, img.nextSibling)
  }
}

async function doFeed() {
  if (!currentPet.value || acting.value) return
  if (aiSleeping.value) {
    clearBubble()
    say('呼噜噜… 人家在睡觉呢~ Zzz', 'feedback', 2200)
    return
  }
  markInteract()
  feedOpen.value = false
  if (bagTotal.value <= 0) {
    clearBubble()
    if (hasAction('interact')) playActionOnce('interact', 1800)
    say('背包空空的… 好饿呀~', 'feedback', 2500)
    // 饿了 → 直达宠物商城"零食"分类
    window.setTimeout(() => router.push({ path: '/pet-shop', query: { category: '零食' } }), 1200)
    return
  }
  // 弹出自选食物面板，让用户挑喂哪一种（而不是默认喂最好的一种）
  if (feedItems.value.length === 1) {
    feedItem(feedItems.value[0])
    return
  }
  feedOpen.value = true
}

/** 喂指定食物 */
async function feedItem(item: BagItem) {
  if (!currentPet.value || acting.value || feedingId.value) return
  markInteract()
  feedOpen.value = false
  clearBubble()
  acting.value = true
  feedingId.value = item.id
  mode.value = 'action'
  if (hasAction('interact')) playAction('interact')
  try {
    const { data: resp } = await feedPet(currentPet.value.id, item.id, { showGlobalLoading: false, showGlobalError: false })
    bag.value = resp.data.bag
    updatePetAfterAction(resp.data)
    if (hasAction('interact')) playAction('interact')
    const gain = resp.data.gained
    if (gain > 0) {
      say(`🍖 吃 ${item.name} 啦！好感 +${gain}`, 'feedback', 2500)
    } else if (resp.data.satiety != null) {
      // 好感可能因每日上限为 0，但食物确实吃进去了（饱食度已恢复）——不能误报"别喂了"
      say(`🍖 吃 ${item.name} 啦，吃得饱饱的~`, 'feedback', 2500)
    } else {
      say('今天饱饱的，明天再喂吧~', 'feedback', 2500)
    }
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { msg?: string | { msg?: string } } } })?.response?.data?.msg
    const text = typeof msg === 'string' ? msg : (msg as { msg?: string })?.msg || '喂食失败了'
    say(text, 'feedback', 2500)
  } finally {
    acting.value = false
    feedingId.value = null
    window.setTimeout(() => {
      mode.value = 'idle'
      playAction('stand')
    }, 2000)
  }
}

async function doPlay() {
  if (!currentPet.value || acting.value) return
  if (aiSleeping.value) {
    clearBubble()
    say('呼噜噜… 人家在睡觉呢~ Zzz', 'feedback', 2200)
    return
  }
  markInteract()
  clearBubble()
  // 宠物发出"陪我玩"请求：直接跳转到玩法页，不再只是加好感度
  if (hasAction('interact')) playActionOnce('interact', 900)
  router.push('/pet-play')
}

async function doPet() {
  if (!currentPet.value || acting.value) return
  if (aiSleeping.value) {
    clearBubble()
    say('呼噜噜… 人家在睡觉呢~ Zzz', 'feedback', 2200)
    return
  }
  markInteract()
  clearBubble()
  acting.value = true
  mode.value = 'action'
  if (hasAction('interact')) playAction('interact')
  try {
    const { data: resp } = await interactPet(currentPet.value.id, 'pet', { showGlobalLoading: false, showGlobalError: false })
    updatePetAfterAction(resp.data)
    const gain = resp.data.gained
    if (gain > 0) {
      say(`❤ 好舒服~ 好感 +${gain}`, 'feedback', 2500)
    } else {
      say('今日好感已经满啦，明天再来摸摸吧~', 'feedback', 2500)
    }
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { msg?: string | { msg?: string } } } })?.response?.data?.msg
    const text = typeof msg === 'string' ? msg : (msg as { msg?: string })?.msg || '摸头失败了'
    say(text, 'feedback', 2500)
  } finally {
    acting.value = false
    window.setTimeout(() => {
      mode.value = 'idle'
      playAction('stand')
    }, 1500)
  }
}

function updatePetAfterAction(data: { affinity: number; gained: number; level: number; leveled_up: boolean; can_evolve: boolean; daily_remaining: number; satiety?: number }) {
  const pet = pets.value[petIndex.value]
  if (!pet) return
  pet.affinity = data.affinity
  pet.level = data.level
  if (data.satiety !== undefined) pet.satiety = data.satiety
  if (data.leveled_up) {
    window.setTimeout(() => {
      say(`🎉 升级啦！Lv${data.level}！`, 'feedback', 3500)
    }, 2800)
  }
  if (data.can_evolve) {
    window.setTimeout(() => {
      say('💎 好感已满！持有进化水晶即可进化~', 'feedback', 3500)
    }, 6000)
  }
}

/** 平滑移动（玩耍时小步走动） */
function animateMove(target: { x: number; y: number }, duration: number) {
  const start = { ...pos.value }
  const startTime = performance.now()
  function step(now: number) {
    const t = Math.min(1, (now - startTime) / duration)
    const ease = 1 - (1 - t) * (1 - t)
    pos.value = clampPos({
      x: start.x + (target.x - start.x) * ease,
      y: start.y + (target.y - start.y) * ease,
    })
    if (t < 1 && mode.value === 'action') requestAnimationFrame(step)
  }
  requestAnimationFrame(step)
}

// ====== 点击/拖拽/长按 ======
const dragState = {
  startX: 0,
  startY: 0,
  moved: false,
  pointerId: -1,
  startTime: 0,
  // 拖拽释放初速度（DyperPet 拖甩：放手时保留最后拖动方向 → 斜抛下落）
  velX: 0,
  velY: 0,
  lastMoveT: 0,
  lastClientX: 0,
  lastClientY: 0,
}
let longPressTimer: number | null = null
const menuOpen = ref(false)

function onPointerDown(e: PointerEvent) {
  markInteract()
  dragState.startX = e.clientX
  dragState.startY = e.clientY
  dragState.moved = false
  dragState.pointerId = e.pointerId
  dragState.startTime = Date.now()
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  // 长按 600ms 弹出菜单
  longPressTimer = window.setTimeout(() => {
    if (!dragState.moved) {
      menuOpen.value = true
      clearBubble()
    }
  }, 600)
}

function onPointerMove(e: PointerEvent) {
  if (dragState.pointerId !== e.pointerId) return
  const dx = e.clientX - dragState.startX
  const dy = e.clientY - dragState.startY
  if (!dragState.moved && Math.hypot(dx, dy) < 6) return
  dragState.moved = true
  if (longPressTimer !== null) { window.clearTimeout(longPressTimer); longPressTimer = null }
  mode.value = 'drag'
  menuOpen.value = false
  // 拖拽时保留需求气泡（用户可能拖着宠物去找按钮）；闲聊/反馈气泡照常清除
  if (bubbleType.value !== 'need') clearBubble()
  // 撞墙：拖动中实时校验，宠物矩形不可侵入底部导航栏
  pos.value = wallClamp(pos.value.x + dx, pos.value.y + dy)
  // DyperPet 拖甩：记录最近一次位移的瞬时速度（px/帧），Execution仍在拖动中每秒采样
  const nowT = performance.now()
  const dt = Math.max(8, nowT - dragState.lastMoveT)
  if (dragState.lastMoveT > 0) {
    dragState.velX = (e.clientX - dragState.lastClientX) * (1000 / dt)
    dragState.velY = (e.clientY - dragState.lastClientY) * (1000 / dt)
  }
  dragState.lastMoveT = nowT
  dragState.lastClientX = e.clientX
  dragState.lastClientY = e.clientY
  dragState.startX = e.clientX
  dragState.startY = e.clientY
}

function onPointerUp(e: PointerEvent) {
  if (dragState.pointerId !== e.pointerId) return
  dragState.pointerId = -1
  if (longPressTimer !== null) { window.clearTimeout(longPressTimer); longPressTimer = null }
  if (dragState.moved) {
    // 只在上方（未落在障碍物顶部）才触发"拖甩斜抛下落"；贴近障碍物顶部则直接放下
    const dvx = dragState.velX
    const dvy = dragState.velY
    userPlaced = true
    if (pos.value.y < barrierY(pos.value.x) - 6) {
      startFall(dvx, dvy)
    } else {
      mode.value = 'idle'
      playAction('stand')
      localStorage.setItem(POS_KEY, JSON.stringify(pos.value))
    }
    dragState.velX = 0
    dragState.velY = 0
    dragState.lastMoveT = 0
    return
  }
  // 未移动 = 轻点
  const elapsed = Date.now() - dragState.startTime
  if (elapsed < 400 && !menuOpen.value) {
    // 短点击：宠物开心反应，不弹菜单
    onTap()
  }
}

// ====== 点击爱心特效 + 假随机掉落 ======
const heartsFx = ref<{ id: number; x: number; delay: number; scale: number }[]>([])
let heartSeq = 0

function spawnHearts(count = 3) {
  const batch: { id: number; x: number; delay: number; scale: number }[] = []
  for (let i = 0; i < count; i++) {
    batch.push({
      id: heartSeq++,
      x: 18 + Math.random() * 64,
      delay: i * 140,
      scale: 0.8 + Math.random() * 0.5,
    })
  }
  heartsFx.value.push(...batch)
  window.setTimeout(() => {
    const ids = new Set(batch.map((b) => b.id))
    heartsFx.value = heartsFx.value.filter((h) => !ids.has(h.id))
  }, 2400)
}

/** 掉落物展示（弹跳礼物 + 气泡提示） */
const dropFx = ref<PetDrop | null>(null)
let dropFxTimer: number | null = null

function showDrop(drop: PetDrop) {
  dropFx.value = drop
  if (dropFxTimer !== null) window.clearTimeout(dropFxTimer)
  dropFxTimer = window.setTimeout(() => {
    dropFx.value = null
    dropFxTimer = null
  }, 3600)
}

let lastTapCall = 0

async function onTap() {
  if (bubbleType.value === 'need') {
    // 有需求气泡时轻点不打断，只冒爱心
    spawnHearts(2)
    return
  }
  clearBubble()
  if (acting.value) return
  spawnHearts(3)
  if (hasAction('interact')) {
    mode.value = 'action'
    playActionOnce('interact', 1200)
  }
  // 随机开心反应
  const happyLines = ['嘿嘿~', '哇！', '你来啦！', '想我了吗？']
  say(happyLines[Math.floor(Math.random() * happyLines.length)], 'chat', 1500)

  // 点击接口：饱食度结算 + 假随机掉落（800ms 节流，防止连点刷屏）
  if (!currentPet.value || !session.isLoggedIn()) return
  const now = Date.now()
  if (now - lastTapCall < 800) return
  lastTapCall = now
  try {
    const { data: resp } = await tapPet(currentPet.value.id, { showGlobalLoading: false, showGlobalError: false })
    const pet = pets.value[petIndex.value]
    if (pet && resp.data.satiety !== undefined) pet.satiety = resp.data.satiety
    if (resp.data.drop) showDrop(resp.data.drop)
  } catch { /* 静默 */ }
}

function onContextMenu(e: Event) {
  e.preventDefault()
  toggleMenu()
}

/** 显式菜单按钮（手机友好：无需长按/右键，直接点 ⋯ 呼出菜单） */
function toggleMenu() {
  menuOpen.value = !menuOpen.value
  if (menuOpen.value && bubbleType.value !== 'need') clearBubble()
}

// ====== 重力坠落（非垂直：水平漂移 + 摆动 + 触地弹跳摆动） ======
const FALL_LINES = ['哎呀呀——！', '要摔屁屁啦！', '放我下来嘛！']

/**
 * 松开后的下落逻辑：采用"方案二"——放到指定位置后，竖直落下（不做向上弹射/斜抛甩出）。
 * - fallVx=0：不再保留拖拽水平漂移，宠物就在松手位置竖直下落，不会总偏到某一侧
 * - 全程 switchAction('stand') + bodyRot=0：下落与落地角度都 = 初始待机角度（直立、不歪斜）
 */
function startFall(dragVx = 0, dragVy = 0) {
  menuOpen.value = false
  clearBubble()
  mode.value = 'fall'
  fallVy = 0 // 由重力加速下落，不做向上抛
  fallVx = 0 // 竖直下落，不水平漂移
  fallAng = 0
  fallAngV = 0
  bodyRot.value = 0 // 全程直立：下落/落地角度 = 初始角度
  playAction('stand')
  say(FALL_LINES[Math.floor(Math.random() * FALL_LINES.length)], 'feedback', 2000)
}

function landOnFloor() {
  userPlaced = true
  pos.value = clampPos({ x: pos.value.x, y: barrierY(pos.value.x) })
  mode.value = 'idle'
  bodyRot.value = 0 // 落地回到初始角度（直立模型）
  playAction('stand')
  localStorage.setItem(POS_KEY, JSON.stringify(pos.value))
}

// ====== 帧循环 ======
let rafId = 0

function tick() {
  if (mode.value === 'fall') {
    // 竖直下落 + 重力加速
    fallVy += gravity.value
    let y = pos.value.y + fallVy
    let x = pos.value.x + fallVx
    // 根据宠物实时横向位置决定地面：正下方是导航栏→停导航栏顶边；否则→浏览器底部
    const fy = barrierY(x)
    // DyperPet 挡板反弹：撞到地板先弹跳，弹到无力再落地（落地角度始终正直）
    if (y >= fy) {
      if (fallVy > 5) {
        y = fy
        fallVy = -fallVy * 0.28
      } else {
        y = fy
        landOnFloor()
      }
    }
    // DyperPet 边缘反弹：撞左/右壁水平速度衰减反向（不再一路飘向某个固定方向）
    const lx = 0
    const rx = vw.value - PET_SIZE
    if (x < lx) {
      x = lx
      fallVx = Math.abs(fallVx) * 0.4
    } else if (x > rx) {
      x = rx
      fallVx = -Math.abs(fallVx) * 0.4
    }
    if (y < 0) {
      y = 0
      fallVy = Math.abs(fallVy) * 0.4
    }
    pos.value = clampPos({ x, y })
    // 全程不旋转，保持直立
  }
  rafId = requestAnimationFrame(tick)
}
function onMenuSwitch() {
  menuOpen.value = false
  if (pets.value.length <= 1) {
    say('就我一个还不够吗？', 'chat', 2000)
    return
  }
  petIndex.value = (petIndex.value + 1) % pets.value.length
  localStorage.setItem(PET_KEY, String(currentPet.value?.id ?? ''))
  say(`嗨！我是${currentPet.value?.nickname || (currentPet.value?.name ?? '新朋友')}~`, 'chat', 2500)
  playAction('stand')
}

function onMenuShop() {
  menuOpen.value = false
  router.push('/pet-shop')
}

function onMenuHide() {
  menuOpen.value = false
  hidden.value = true
  localStorage.setItem(HIDDEN_KEY, '1')
}

/** 陪我玩：进入宠物游乐场 */
function onMenuPlay() {
  menuOpen.value = false
  router.push('/pet-play')
}

function onMenuUpgrade() {
  menuOpen.value = false
  if (currentPet.value) router.push(`/pet-shop/${currentPet.value.id}`)
}

// ====== 数据加载 ======
async function loadGravity() {
  try {
    const { data } = await fetchPublicSettings()
    const g = Number(data.data?.pet_gravity ?? '0.5')
    if (!Number.isNaN(g)) gravity.value = Math.min(1, Math.max(0, g))
  } catch { /* 静默，保持默认 */ }
}

async function loadPets() {
  if (!session.isLoggedIn()) return
  try {
    const [petsResp, bagResp] = await Promise.all([
      listMyPets({ showGlobalLoading: false, showGlobalError: false }),
      listMyBag({ showGlobalLoading: false, showGlobalError: false }).catch(() => null),
    ])
    pets.value = petsResp.data.data.items ?? []
    if (bagResp) bag.value = bagResp.data.data.items ?? []
    if (!pets.value.length) return
    const savedId = Number(localStorage.getItem(PET_KEY))
    const idx = pets.value.findIndex((p) => p.id === savedId)
    petIndex.value = idx >= 0 ? idx : 0
  } catch {
    pets.value = []
  }
}

function onSelectPet(e: Event) {
  const id = Number((e as CustomEvent<number>).detail)
  if (!id) return
  void loadPets().then(() => {
    const idx = pets.value.findIndex((p) => p.id === id)
    if (idx >= 0) {
      petIndex.value = idx
      localStorage.setItem(PET_KEY, String(id))
      playAction('stand')
      say(`嗨！我是${currentPet.value?.nickname || (currentPet.value?.name ?? '新朋友')}~`, 'chat', 2500)
    }
  })
}

function onSummon() {
  hidden.value = false
  localStorage.removeItem(HIDDEN_KEY)
  loadPets()
}

function onReload() {
  loadPets()
}

// 路由判断
const showOnRoute = computed(() => {
  const p = route.path
  return !(
    p === '/admin' ||
    p.startsWith('/admin/') ||
    p.startsWith('/chat/') ||
    p === '/pet-play' // 陪我玩界面不显示第二只桌宠（连对话一起隐藏），离开该路由即恢复
  )
})

const visible = computed(
  () => session.isLoggedIn() && !hidden.value && !!currentPet.value?.anim && showOnRoute.value,
)

watch(
  () => session.userId,
  () => {
    if (session.isLoggedIn()) loadPets()
    else {
      pets.value = []
      menuOpen.value = false
      clearBubble()
    }
  },
)

watch(visible, (v) => {
  if (v) {
    ensurePos()
    playAction('stand')
  }
})

watch(currentPet, () => {
  if (currentPet.value) {
    if (aiSleeping.value && hasAction('sleep')) {
      mode.value = 'action'
      playAction('sleep')
    } else {
      playAction('stand')
    }
  }
})

// 路由变化时导航栏/自定义地面存在与否会改变：重测矩形区域并把宠物拉回合法落点，避免上一个页面残留位置导致"抽搐"
// 页面多为懒加载，DOM 可能晚于路由变化渲染，故延迟再测一次确保 data-pet-ground 能被识别
watch(
  () => route.path,
  () => {
    refreshTabBar()
    window.setTimeout(() => {
      refreshTabBar()
      if (inited.value) {
        if (userPlaced) pos.value = clampPos(pos.value)
        else initPos()
      }
    }, 150)
  },
)

// ====== 宠物发消息 → 漂浮宠说出这句话 ======
// App.vue 收到 pet_ai_proactive 后派发全局事件，这里让当前漂浮宠物开口并短暂保持说话时长。
function onPetAiSay(e: Event) {
  const detail = (e as CustomEvent<{ petId: number; text: string }>).detail
  if (!detail || !detail.text) return
  // 只让"当前悬浮的那只"说这句话；睡着/隐藏/未召唤则不打断
  if (!currentPet.value || hidden.value) return
  if (currentPet.value.id !== detail.petId) return
  if (aiSleeping.value) {
    clearBubble()
    say('呼噜噜… 人家在睡觉呢~ Zzz', 'feedback', 2200)
    return
  }
  say(detail.text, 'chat', Math.min(6000, 2000 + detail.text.length * 90))
}

onMounted(() => {
  ensurePos()
  loadGravity()
  if (session.isLoggedIn()) loadPets()
  window.addEventListener('resize', onResize)
  window.addEventListener('floating-pet:summon', onSummon)
  window.addEventListener('floating-pet:reload', onReload)
  window.addEventListener('floating-pet:select', onSelectPet as EventListener)
  window.addEventListener('pet-ai-say', onPetAiSay)
  rafId = requestAnimationFrame(tick)
  startStatusPolling()
  startAiSleepPolling()
  startChatter()
  startIdleActions()
})

function onResize() {
  if (window.innerWidth < 60 || window.innerHeight < 60) return
  vw.value = window.innerWidth
  refreshTabBar() // 视口变化后导航栏区域可能改变，需重测
  if (!inited.value || !userPlaced) initPos()
  else pos.value = clampPos(pos.value)
}

onBeforeUnmount(() => {
  clearBubble()
  if (bubbleTimer !== null) window.clearTimeout(bubbleTimer)
  if (dropFxTimer !== null) window.clearTimeout(dropFxTimer)
  if (statusTimer !== null) window.clearInterval(statusTimer)
  if (aiSleepTimer !== null) window.clearInterval(aiSleepTimer)
  if (chatTimer !== null) window.clearInterval(chatTimer)
  if (idleActionTimer !== null) window.clearInterval(idleActionTimer)
  if (longPressTimer !== null) window.clearTimeout(longPressTimer)
  cancelAnimationFrame(rafId)
  window.removeEventListener('resize', onResize)
  window.removeEventListener('floating-pet:summon', onSummon)
  window.removeEventListener('floating-pet:reload', onReload)
  window.removeEventListener('floating-pet:select', onSelectPet as EventListener)
  window.removeEventListener('pet-ai-say', onPetAiSay)
})
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="floating-pet"
      :class="{ 'is-dragging': mode === 'drag' }"
      :style="{
        transform: `translate(${pos.x}px, ${pos.y}px)`,
        width: PET_SIZE + 'px',
        height: PET_SIZE + 'px',
      }"
    >
      <!-- 需求气泡（带操作按钮） -->
      <Transition name="fp-bubble">
        <div v-if="bubble && bubbleType === 'need'" class="floating-pet__need-bubble" :class="bubbleCls">
          <div class="fp-need__text">{{ bubble }}</div>
          <!-- 需求倒计时（我想要… 还剩 X 秒） -->
          <div v-if="needRemain > 0" class="fp-need__countdown">
            <i class="fp-need__countdown-ring" :style="{ animationDuration: needRemain + 's' }"></i>
            <span>「想要」剩 {{ needRemain }}s</span>
          </div>
          <div class="fp-need__actions">
            <button
              v-if="needAction === 'feed'"
              class="fp-need__btn fp-need__btn--feed"
              type="button"
              @click.stop="doFeed"
            >
              🍖 喂食
            </button>
            <button
              v-if="needAction === 'play'"
              class="fp-need__btn fp-need__btn--play"
              type="button"
              @click.stop="doPlay"
            >
              🎾 陪玩
            </button>
            <button
              v-if="needAction === 'pet'"
              class="fp-need__btn fp-need__btn--pet"
              type="button"
              @click.stop="doPet"
            >
              🫳 摸摸
            </button>
            <button class="fp-need__btn fp-need__btn--later" type="button" @click.stop="clearBubble">
              稍后
            </button>
          </div>
          <!-- 好感度 + 饱食度 -->
          <div class="fp-need__hearts">
            <span>{{ '❤'.repeat(hearts.hearts) }}{{ '♡'.repeat(5 - hearts.hearts) }}</span>
            <span class="fp-need__lv">Lv{{ currentPet?.level || 1 }} <template v-if="currentPet?.mood">· {{ currentPet.mood }}</template></span>
          </div>
          <div class="fp-need__satiety">
            <span class="fp-need__satiety-icon">🍖</span>
            <div class="fp-need__satiety-bar">
              <i
                :style="{ width: (currentPet?.satiety ?? 100) + '%' }"
                :class="{ 'is-hungry': (currentPet?.satiety ?? 100) < 30 }"
              ></i>
            </div>
            <span class="fp-need__satiety-num">{{ currentPet?.satiety ?? 100 }}</span>
          </div>
        </div>
      </Transition>

      <!-- 普通/反馈气泡 -->
      <Transition name="fp-bubble">
        <div v-if="bubble && bubbleType !== 'need'" class="floating-pet__bubble" :class="bubbleCls">{{ bubble }}</div>
      </Transition>

      <!-- 自选食物面板 -->
      <Transition name="fp-bubble">
        <div v-if="feedOpen" class="fppet-feed" @click.stop>
          <h4 class="fppet-feed__title">🍖 喂点什么？</h4>
          <button class="fppet-feed__close" type="button" @click.stop="feedOpen = false">✕</button>
          <div class="fppet-feed__list">
            <button
              v-for="item in feedItems"
              :key="item.id"
              class="fppet-feed__item"
              type="button"
              :disabled="feedingId === item.id"
              @click.stop="feedItem(item)"
            >
              <img v-if="isImageUrl(item.image_url)" class="fppet-feed__emoji" :src="item.image_url" alt="" @error="onFeedImgError" />
              <span v-else class="fppet-feed__emoji">{{ item.image_url || '🍗' }}</span>
              <span class="fppet-feed__meta">
                <b>{{ item.name }}</b>
                <small>饱腹+{{ item.attrs?.satiety || 0 }} 好感+{{ item.affinity_gain || 0 }} · ×{{ item.bag_qty ?? item.qty ?? 1 }}</small>
              </span>
            </button>
          </div>
          <button v-if="!feedItems.length" class="fppet-feed__empty" type="button" @click.stop="doFeed">背包里没有食物，去商城看看 →</button>
        </div>
      </Transition>

      <!-- 掉落物展示（假随机掉落） -->
      <Transition name="fp-drop">
        <div v-if="dropFx" class="floating-pet__drop">
          <div class="fp-drop__item">{{ dropFx.emoji || '🎁' }}</div>
          <div class="fp-drop__label">
            {{ dropFx.pity ? '保底掉落！' : '捡到了' }}
            <b>{{ dropFx.name }}</b>
            <span class="fp-drop__qty">×1</span>
          </div>
        </div>
      </Transition>

      <!-- 点击爱心特效 -->
      <div class="floating-pet__hearts" aria-hidden="true">
        <span
          v-for="h in heartsFx"
          :key="h.id"
          class="fp-heart"
          :style="{ left: h.x + '%', animationDelay: h.delay + 'ms', fontSize: 14 * h.scale + 'px' }"
        >❤</span>
      </div>

      <!-- 菜单按钮（手机友好，替代右键/长按） -->
      <button
        v-if="!menuOpen"
        class="floating-pet__menu-btn"
        type="button"
        aria-label="宠物菜单"
        @pointerdown.stop
        @pointerup.stop
        @click.stop="toggleMenu"
      >⋯</button>

      <!-- 菜单（长按 / ⋯ 按钮均可呼出） -->
      <Transition name="fp-menu">
        <div v-if="menuOpen" class="floating-pet__menu" :class="bubbleCls">
          <div class="fp-menu__head">
            <span class="fp-menu__pet-name">{{ currentPet?.nickname || currentPet?.name || '宠物' }}</span>
            <span class="fp-menu__pet-lv">Lv{{ currentPet?.level || 1 }} · 🍖{{ currentPet?.satiety ?? 100 }}<template v-if="currentPet?.mood"> · {{ currentPet.mood }}</template></span>
          </div>
          <button class="fp-menu__item" type="button" @click.stop="onMenuUpgrade">
            <span class="fp-menu__icon">📋</span>宠物详情
          </button>
          <button v-if="pets.length > 1" class="fp-menu__item" type="button" @click.stop="onMenuSwitch">
            <span class="fp-menu__icon">🔄</span>换一只
          </button>
          <button class="fp-menu__item" type="button" @click.stop="onMenuPlay">
            <span class="fp-menu__icon">🎮</span>陪我玩
          </button>
          <button class="fp-menu__item" type="button" @click.stop="onMenuShop">
            <span class="fp-menu__icon">🛒</span>去商城
          </button>
          <button class="fp-menu__item fp-menu__item--muted" type="button" @click.stop="onMenuHide">
            <span class="fp-menu__icon">🏠</span>收进窝
          </button>
        </div>
      </Transition>

      <!-- 宠物本体 -->
      <div
        class="floating-pet__body"
        :style="{ transform: `scaleX(${direction}) rotate(${bodyRot}deg)` }"
        @pointerdown.prevent="onPointerDown"
        @pointermove.prevent="onPointerMove"
        @pointerup.prevent="onPointerUp"
        @pointercancel.prevent="onPointerUp"
        @contextmenu.prevent="onContextMenu"
      >
        <PetAnimation
          :key="currentPet!.id"
          ref="petRef"
          :anim="currentPet!.anim"
          :size="PET_SIZE"
          :interactive="false"
          :show-tabs="false"
        />
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.floating-pet {
  position: fixed;
  top: 0;
  left: 0;
  z-index: 1800;
  touch-action: none;
  cursor: pointer;
  user-select: none;
}
.floating-pet.is-dragging {
  cursor: grabbing;
}
.floating-pet__body {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 120ms ease;
}
.floating-pet.is-dragging .floating-pet__body {
  transform: scale(1.06);
}
.floating-pet :deep(.pet-anim__canvas) {
  filter: drop-shadow(0 4px 10px rgba(23, 32, 64, 0.22));
  cursor: pointer;
}

/* 普通气泡 */
.floating-pet__bubble {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  max-width: 180px;
  min-width: 26px;
  /* 宽度跟随内容自适应：短句小、长句大，超过 max-width 才换行，避免 nowrap 撑破气泡 */
  width: max-content;
  padding: 6px 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(23, 32, 64, 0.08);
  box-shadow: 0 4px 14px rgba(23, 32, 64, 0.14);
  color: #1c2030;
  font-size: 12px;
  line-height: 1.5;
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
  pointer-events: none;
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
}
.floating-pet__bubble::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 6px solid transparent;
  border-top-color: rgba(255, 255, 255, 0.95);
}

/* 气泡/菜单边界适配（宠物贴边时自动换方向，保证完整可见） */
.is-left.floating-pet__bubble,
.is-left.floating-pet__need-bubble,
.is-left.floating-pet__menu {
  left: 0;
  transform: none;
}
.is-left.floating-pet__bubble::after,
.is-left.floating-pet__need-bubble::after {
  left: 56px;
  transform: none;
}
.is-right.floating-pet__bubble,
.is-right.floating-pet__need-bubble,
.is-right.floating-pet__menu {
  left: auto;
  right: 0;
  transform: none;
}
.is-right.floating-pet__bubble::after,
.is-right.floating-pet__need-bubble::after {
  left: auto;
  right: 56px;
  transform: none;
}
.is-bottom.floating-pet__bubble {
  bottom: auto;
  top: calc(100% + 8px);
}
.is-bottom.floating-pet__bubble::after {
  top: auto;
  bottom: 100%;
  border-top-color: transparent;
  border-bottom-color: rgba(255, 255, 255, 0.95);
}
.is-bottom.floating-pet__need-bubble,
.is-bottom.floating-pet__menu {
  bottom: auto;
  top: calc(100% + 10px);
}
.is-bottom.floating-pet__need-bubble::after {
  top: auto;
  bottom: 100%;
  border-top-color: transparent;
  border-bottom-color: rgba(255, 255, 255, 0.97);
}

/* 需求气泡（带按钮） */
.floating-pet__need-bubble {
  position: absolute;
  bottom: calc(100% + 10px);
  left: 50%;
  transform: translateX(-50%);
  min-width: 170px;
  padding: 10px 12px 8px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.97);
  border: 1px solid rgba(23, 32, 64, 0.1);
  box-shadow: 0 8px 28px rgba(23, 32, 64, 0.18);
  -webkit-backdrop-filter: blur(14px);
  backdrop-filter: blur(14px);
}
.floating-pet__need-bubble::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 7px solid transparent;
  border-top-color: rgba(255, 255, 255, 0.97);
}
.fp-need__text {
  font-size: 13px;
  font-weight: 600;
  color: #1c2030;
  margin-bottom: 8px;
  white-space: nowrap;
}
/* 需求倒计时（我想要… 还剩 X 秒） */
.fp-need__countdown {
  display: flex;
  align-items: center;
  gap: 5px;
  margin: -2px 0 7px;
  font-size: 11px;
  font-weight: 600;
  color: #ff8a3d;
}
.fp-need__countdown-ring {
  position: relative;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: conic-gradient(#ff9a56 var(--p, 100%), rgba(23, 32, 64, 0.1) 0);
  animation: fp-countdown-ring linear forwards;
}
@keyframes fp-countdown-ring {
  from { --p: 0%; }
  to { --p: 100%; }
}
.fp-need__actions {
  display: flex;
  gap: 6px;
  margin-bottom: 6px;
}
.fp-need__btn {
  flex: 1;
  padding: 6px 0;
  border: none;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: transform 100ms ease, opacity 100ms ease;
}
.fp-need__btn:active { transform: scale(0.94); }
.fp-need__btn--feed {
  background: linear-gradient(135deg, #ff9a56, #ff6b35);
  color: #fff;
}
.fp-need__btn--play {
  background: linear-gradient(135deg, #5b8cff, #3d7bff);
  color: #fff;
}
.fp-need__btn--pet {
  background: linear-gradient(135deg, #ff6b81, #ff3b5c);
  color: #fff;
}
.fp-need__btn--later {
  flex: 0 0 auto;
  padding: 6px 10px;
  background: var(--bg-200, #f0f1f5);
  color: var(--text-500, #8a90a3);
}
.fp-need__hearts {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 10px;
  color: #ff5b7a;
  letter-spacing: 0.5px;
}
.fp-need__lv {
  color: var(--text-400, #8a90a3);
  font-weight: 500;
  letter-spacing: 0;
}
/* 饱食度条 */
.fp-need__satiety {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 5px;
}
.fp-need__satiety-icon {
  font-size: 11px;
  line-height: 1;
}
.fp-need__satiety-bar {
  flex: 1;
  height: 5px;
  border-radius: 3px;
  background: rgba(23, 32, 64, 0.08);
  overflow: hidden;
}
.fp-need__satiety-bar i {
  display: block;
  height: 100%;
  border-radius: 3px;
  background: linear-gradient(90deg, #ffb35c, #ff8a3d);
  transition: width 400ms ease;
}
.fp-need__satiety-bar i.is-hungry {
  background: linear-gradient(90deg, #ff6b81, #ff3b5c);
}
.fp-need__satiety-num {
  font-size: 10px;
  color: var(--text-400, #8a90a3);
  min-width: 18px;
  text-align: right;
}

/* 点击爱心特效 */
.floating-pet__hearts {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: visible;
}
.fp-heart {
  position: absolute;
  bottom: 30%;
  color: #ff5b7a;
  filter: drop-shadow(0 2px 4px rgba(255, 91, 122, 0.4));
  animation: fp-heart-up 1.6s cubic-bezier(0.22, 0.68, 0.42, 1) forwards;
}
@keyframes fp-heart-up {
  0% {
    opacity: 0;
    transform: translateY(0) scale(0.4);
  }
  18% {
    opacity: 1;
  }
  100% {
    opacity: 0;
    transform: translateY(-96px) scale(1.15);
  }
}

/* 掉落物展示 */
.floating-pet__drop {
  position: absolute;
  bottom: calc(100% + 10px);
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  pointer-events: none;
}
.fp-drop__item {
  font-size: 26px;
  animation: fp-drop-bounce 0.7s cubic-bezier(0.32, 1.2, 0.4, 1) both;
  filter: drop-shadow(0 4px 8px rgba(23, 32, 64, 0.25));
}
@keyframes fp-drop-bounce {
  0% {
    opacity: 0;
    transform: translateY(-26px) scale(0.5) rotate(-18deg);
  }
  55% {
    opacity: 1;
    transform: translateY(4px) scale(1.1) rotate(6deg);
  }
  100% {
    opacity: 1;
    transform: translateY(0) scale(1) rotate(0deg);
  }
}
.fp-drop__label {
  padding: 5px 10px;
  border-radius: 10px;
  background: rgba(255, 224, 138, 0.96);
  border: 1px solid rgba(214, 158, 46, 0.35);
  color: #7a4d12;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  box-shadow: 0 4px 14px rgba(214, 158, 46, 0.28);
}
.fp-drop__label b {
  margin: 0 2px;
  color: #5d3a0a;
}
.fp-drop__qty {
  margin-left: 3px;
  color: #a06a1f;
}
.fp-drop-enter-active,
.fp-drop-leave-active {
  transition: all 300ms cubic-bezier(0.32, 0.72, 0, 1);
}
.fp-drop-enter-from,
.fp-drop-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(8px) scale(0.9);
}

/* 菜单按钮（手机友好 ⋯ 按钮） */
.floating-pet__menu-btn {
  position: absolute;
  top: -4px;
  right: -4px;
  width: 26px;
  height: 26px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.92);
  color: #4a5064;
  font-size: 15px;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(23, 32, 64, 0.22);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  transition: transform 120ms ease, background 120ms ease;
  z-index: 3;
}
.floating-pet__menu-btn:active {
  transform: scale(0.88);
  background: #fff;
}

/* 长按/⋯ 菜单 */
.floating-pet__menu {
  position: absolute;
  bottom: calc(100% + 10px);
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 130px;
  padding: 4px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(23, 32, 64, 0.08);
  box-shadow: 0 8px 28px rgba(23, 32, 64, 0.18);
  -webkit-backdrop-filter: blur(14px);
  backdrop-filter: blur(14px);
  z-index: 4;
}
.fp-menu__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px 6px 12px;
  border-bottom: 1px solid rgba(23, 32, 64, 0.07);
  margin-bottom: 2px;
}
.fp-menu__pet-name {
  font-size: 12px;
  font-weight: 700;
  color: #1c2030;
  max-width: 90px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fp-menu__pet-lv {
  font-size: 10px;
  color: var(--text-400, #8a90a3);
  white-space: nowrap;
}
.fp-menu__item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: #2a2f3e;
  font-size: 13px;
  font-weight: 500;
  text-align: left;
  cursor: pointer;
  transition: background 120ms ease;
  white-space: nowrap;
}
.fp-menu__item:hover { background: rgba(61, 123, 255, 0.1); }
.fp-menu__item--muted { color: #8a90a3; }
.fp-menu__icon { font-size: 15px; line-height: 1; }

/* 自选食物面板 */
.fppet-feed {
  position: absolute;
  bottom: calc(100% + 12px);
  left: 50%;
  transform: translateX(-50%);
  min-width: 200px;
  padding: 10px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(23, 32, 64, 0.08);
  box-shadow: 0 10px 32px rgba(23, 32, 64, 0.22);
  -webkit-backdrop-filter: blur(14px);
  backdrop-filter: blur(14px);
  z-index: 6;
}
.fppet-feed__title {
  margin: 0 0 8px;
  padding-right: 22px;
  font-size: 13px;
  font-weight: 700;
  color: #1c2030;
}
.fppet-feed__close {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 50%;
  background: rgba(23, 32, 64, 0.06);
  color: #5a5f6e;
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
}
.fppet-feed__close:active { background: rgba(23, 32, 64, 0.12); }
.fppet-feed__list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 46vh;
  overflow-y: auto;
}
.fppet-feed__item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: none;
  border-radius: 12px;
  background: rgba(61, 123, 255, 0.05);
  color: #2a2f3e;
  text-align: left;
  cursor: pointer;
  transition: background 120ms ease;
}
.fppet-feed__item:hover { background: rgba(61, 123, 255, 0.12); }
.fppet-feed__item:disabled { opacity: 0.6; cursor: default; }
.fppet-feed__emoji {
  width: 34px;
  height: 34px;
  flex: 0 0 34px;
  border-radius: 10px;
  object-fit: cover;
  background: #eef1f8;
  font-size: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.fppet-feed__meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.fppet-feed__meta b {
  font-size: 13px;
  color: #1c2030;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.fppet-feed__meta small {
  font-size: 11px;
  color: var(--text-400, #8a90a3);
  white-space: nowrap;
}
.fppet-feed__empty {
  width: 100%;
  padding: 10px;
  border: none;
  border-radius: 12px;
  background: transparent;
  color: #3d7bff;
  font-size: 13px;
  font-weight: 600;
  text-align: center;
  cursor: pointer;
}

/* 动画 */
.fp-bubble-enter-active,
.fp-bubble-leave-active {
  transition: all 200ms cubic-bezier(0.32, 0.72, 0, 1);
}
.fp-bubble-enter-from,
.fp-bubble-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(6px) scale(0.9);
}
.fp-menu-enter-active,
.fp-menu-leave-active {
  transition: all 180ms cubic-bezier(0.32, 0.72, 0, 1);
  transform-origin: bottom center;
}
.fp-menu-enter-from,
.fp-menu-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(6px) scale(0.92);
}
</style>
