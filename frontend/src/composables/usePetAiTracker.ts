/**
 * 宠物 AI 事件触发追踪器
 *
 * 对应需求「四、事件触发系统」：当用户在某页面停留超过后台阈值范围时，
 * 模拟系统消息让 AI 说一句话；同时定期上报用户动作供 AI 理解上下文。
 *
 * 用法（在需要追踪的页面调用）：
 *   const { stop } = usePetAiTracker({
 *     type: 'post_detail',
 *     getDetail: () => post.value?.title || '',
 *     keepAlive: false, // keep-alive 页面（如首页）传 true，改用 activated/deactivated
 *   })
 *
 * 说明：
 * - 配置（事件阈值）与「用户当前 AI 宠物」均做进程级缓存，避免每个页面重复请求。
 * - 每页只触发一次事件（触发时刻在 [min, max] 内取随机值）；每 60s 上报一次动作。
 * - 事件触发与动作上报都静默失败，不影响用户浏览。
 */
import { onActivated, onBeforeUnmount, onDeactivated, onMounted } from 'vue'
import { useSessionStore } from '../stores/session'
import { petAiEventConfig, petAiRecordActivity, petAiTriggerEvent, type PetAiEventConfig } from '../api/petAi'
import { listMyPets } from '../api/petShop'

/** 动作记录间隔（秒） */
const RECORD_INTERVAL_MS = 60_000
/** 触发判断检查间隔（秒） */
const CHECK_INTERVAL_MS = 5_000

// ===== 进程级缓存 =====
let configCache: PetAiEventConfig | null = null
let configPromise: Promise<PetAiEventConfig | null> | null = null
let petIdCache: number | null = null
let petIdPromise: Promise<number | null> | null = null

/** 读取事件阈值配置（缓存，并发安全） */
function loadConfig(): Promise<PetAiEventConfig | null> {
  if (configCache) return Promise.resolve(configCache)
  if (configPromise) return configPromise
  configPromise = (async () => {
    try {
      const { data } = await petAiEventConfig()
      configCache = data.data
      return data.data
    } catch {
      return null
    } finally {
      configPromise = null
    }
  })()
  return configPromise
}

/** 解析用户当前可对话的 AI 宠物 id（优先悬浮宠，其次第一只开启 AI 的宠物） */
function loadActivePetId(): Promise<number | null> {
  if (petIdCache) return Promise.resolve(petIdCache)
  if (petIdPromise) return petIdPromise
  petIdPromise = (async () => {
    try {
      // 悬浮宠优先（localStorage 由 FloatingPet/MyPets 维护）
      const floatId = Number(localStorage.getItem('floating_pet_id') || 0)
      if (floatId > 0) {
        petIdCache = floatId
        return floatId
      }
      const { data } = await listMyPets({ showGlobalLoading: false, showGlobalError: false })
      const item = (data.data.items || []).find((p: { ai_enabled?: boolean }) => p.ai_enabled)
      petIdCache = item ? Number(item.id) : null
      return petIdCache
    } catch {
      return null
    } finally {
      petIdPromise = null
    }
  })()
  return petIdPromise
}

export interface PetAiTrackerOptions {
  /** 事件类型：post_detail（帖子详情）/ post_list（帖子列表）/ pet_shop（宠物商城） */
  type: 'post_detail' | 'post_list' | 'pet_shop'
  /** 动态获取页面详情（标题/标签名），用于系统消息模板 */
  getDetail?: () => string
  /** keep-alive 页面传 true，改用 activated/deactivated 计时 */
  keepAlive?: boolean
  /** 是否禁用（如未登录时不追踪） */
  disabled?: boolean
}

export function usePetAiTracker(options: PetAiTrackerOptions) {
  const session = useSessionStore()

  let elapsedSec = 0
  let started = false
  let triggered = false
  let targetSec = 0
  let checkTimer: ReturnType<typeof setInterval> | null = null
  let recordTimer: ReturnType<typeof setInterval> | null = null
  let lastRecordSec = 0

  async function ensureReady(): Promise<void> {
    if (!session.userId || options.disabled) return
    const cfg = await loadConfig()
    if (!cfg || !cfg.enabled) return
    // 未开启该类型事件的页面不追踪
    const range = cfg[options.type]
    const [min, max] = range || [0, 0]
    if (!(min > 0 && max > 0)) return
    // 触发时刻在 [min, max] 内随机取
    targetSec = Math.round(min + Math.random() * Math.max(0, max - min))
    // 首次进入立即上报一次动作（让 AI 知道用户在做什么）
    reportActivity()
    start()
  }

  function reportActivity() {
    if (!session.userId || options.disabled) return
    const detail = options.getDetail ? options.getDetail() : ''
    petAiRecordActivity(options.type, detail).catch(() => { /* 静默 */ })
  }

  async function fireEvent(sec: number) {
    if (triggered || !session.userId || options.disabled) return
    const petId = await loadActivePetId()
    if (!petId) return
    triggered = true
    const detail = options.getDetail ? options.getDetail() : ''
    petAiTriggerEvent(petId, options.type, detail, sec).catch(() => { /* 静默 */ })
  }

  function start() {
    if (started) return
    started = true
    elapsedSec = 0
    lastRecordSec = 0
    // 定时检查：到达目标时刻则触发事件
    checkTimer = setInterval(() => {
      elapsedSec += CHECK_INTERVAL_MS / 1000
      if (!triggered && elapsedSec >= targetSec) {
        fireEvent(Math.round(elapsedSec))
      }
      // 每 60s 上报一次动作，刷新 AI 上下文
      if (elapsedSec - lastRecordSec >= RECORD_INTERVAL_MS / 1000) {
        lastRecordSec = elapsedSec
        reportActivity()
      }
    }, CHECK_INTERVAL_MS)
    recordTimer = setInterval(reportActivity, RECORD_INTERVAL_MS)
  }

  function stop() {
    started = false
    if (checkTimer) { clearInterval(checkTimer); checkTimer = null }
    if (recordTimer) { clearInterval(recordTimer); recordTimer = null }
  }

  if (options.keepAlive) {
    onActivated(() => { ensureReady() })
    onDeactivated(stop)
  } else {
    onMounted(() => { ensureReady() })
    onBeforeUnmount(stop)
  }

  return { stop }
}
