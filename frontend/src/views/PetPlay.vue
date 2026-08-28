<script setup lang="ts">
/**
 * 宠物游乐场「陪我玩」- 游戏中心
 * - 分类 TAB：单人游戏 / 多人游戏（多人开发中，暂只展示占位）
 * - 「制作游戏」按钮：上传 HTML 小游戏，后台审核通过后上架
 * - 内置 6 款宠物互动小游戏（接零食/戳泡泡/记忆翻牌/猜拳/幸运轮/打地鼠）
 * - 移植 tufang-games 11 款 HTML 小游戏（iframe 内嵌在当前页面，不新开界面）
 * - 每局/每次游玩可领金币奖励（后台可配每局金币与每日上限），本地游戏同时加好感
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import PetAnimation from '../components/pet/PetAnimation.vue'
import { listMyPets, type MyPetItem } from '../api/petShop'
import { submitGameScore } from '../api/rankings'
import { claimGameReward, listGames, getGameHtml, submitUserGame, getGameMyStatus, type GameItem } from '../api/games'
import { useSessionStore } from '../stores/session'
import { useUIStore } from '../stores/ui'

const PET_KEY = 'floating_pet_id'

const router = useRouter()
const session = useSessionStore()
const uiStore = useUIStore()

// ================= 宠物 =================
const pets = ref<MyPetItem[]>([])
const pet = ref<MyPetItem | null>(null)
const petRef = ref<InstanceType<typeof PetAnimation> | null>(null)
const loading = ref(true)
const petSay = ref('')
const petSayType = ref<'chat' | 'feedback'>('chat')
let sayTimer: number | null = null

function say(text: string, type: 'chat' | 'feedback' = 'chat', duration = 2600) {
  petSay.value = text
  petSayType.value = type
  if (sayTimer !== null) window.clearTimeout(sayTimer)
  sayTimer = window.setTimeout(() => {
    petSay.value = ''
  }, duration)
}

// ===== 游戏触发话术（后台配置的 game_speech，空则用内置默认）=====
const speech = ref<Record<string, string>>({})
function gs(key: string, fallback: string): string {
  return speech.value[key] || fallback
}
function loadGameSpeech(p: MyPetItem | null) {
  if (!p?.game_speech) {
    speech.value = {}
    return
  }
  try {
    const obj = typeof p.game_speech === 'string' ? JSON.parse(p.game_speech) : p.game_speech
    speech.value = obj && typeof obj === 'object' ? obj : {}
  } catch {
    speech.value = {}
  }
}

function petAction(key: string) {
  try {
    petRef.value?.switchAction(key)
  } catch { /* 忽略 */ }
}

/** 胜利/失败反应 */
function reactWin() {
  petAction('interact')
  say(gs('win', '嘿嘿，你真棒！我们太默契啦~ 🎉'), 'feedback', 2800)
}
function reactLose() {
  petAction('interact')
  say(gs('lose', '差一点点！再陪我玩一次嘛~'), 'chat', 2600)
}

// ================= 游戏中心 =================
const LOCAL_KEYS = new Set(['catch', 'bubble', 'memory', 'rps', 'wheel', 'mole'])
const gameTab = ref<'single' | 'multi'>('single')
const games = ref<GameItem[]>([])
const loadingGames = ref(false)
/** 每个游戏今日金币/好感剩余状态（已登录用户），key 为 slug */
const gameDaily = ref<Record<string, { coins_remaining: number; affinity_remaining: number }>>({})

/** 单人游戏列表（已上架） */
const singleGames = computed(() =>
  games.value.filter((g) => g.type === 'single' && g.is_active && g.status === 'active'),
)

/** 当前正在玩的游戏（本地 slug 或 HTML 游戏对象） */
const activeGame = ref<string | null>(null) // 本地小游戏 slug
const activeHtml = ref<GameItem | null>(null) // HTML 游戏
const inGame = computed(() => activeGame.value !== null || activeHtml.value !== null)
const isLocalGame = computed(() => activeGame.value !== null)

/** 内置 HTML 游戏 -> public 静态文件映射 */
const PUBLIC_HTML_GAMES: Record<string, string> = {
  'game-2048': '/games/game-2048.html',
  'game-breakout': '/games/game-breakout.html',
  'game-flappy': '/games/game-flappy.html',
  'game-reaction': '/games/game-reaction.html',
  'game-snake': '/games/game-snake.html',
  'game-tetris': '/games/game-tetris.html',
  'game-match': '/games/game-match.html',
  'game-memory': '/games/game-memory.html',
  'game-minesweeper': '/games/game-minesweeper.html',
  'game-sudoku': '/games/game-sudoku.html',
  'game-whack': '/games/game-whack.html',
}

const htmlGameUrl = ref('')
const htmlGameSrcdoc = ref('')
const htmlGameStatus = ref<{ reward_coins: number; daily_remaining: number; claimed_today: number; daily_limit: number } | null>(null)
const claimingHtml = ref(false)

async function loadGames() {
  loadingGames.value = true
  try {
    games.value = await listGames({ showGlobalLoading: false, showGlobalError: false })
  } catch {
    games.value = []
  } finally {
    loadingGames.value = false
  }
  // 已登录用户：并行拉取每个单人游戏今日金币/好感剩余，用于卡片展示"还能赚多少"
  if (session.isLoggedIn()) {
    const map: Record<string, { coins_remaining: number; affinity_remaining: number }> = {}
    await Promise.all(
      singleGames.value.map(async (g) => {
        try {
          const st = await getGameMyStatus(g.slug, { showGlobalLoading: false, showGlobalError: false })
          map[g.slug] = {
            coins_remaining: Math.max(0, st.daily_limit - st.claimed_today) * st.reward_coins,
            affinity_remaining: Math.max(0, (st.affinity_daily_limit || 0) - (st.affinity_today || 0)),
          }
        } catch { /* 忽略单个失败 */ }
      }),
    )
    gameDaily.value = map
  } else {
    gameDaily.value = {}
  }
}

function dailyCoinsText(g: GameItem): string {
  const d = gameDaily.value[g.slug]
  if (d) return `今日可赚金币还剩 ${d.coins_remaining} 个`
  return `今日可赚金币还剩 ${g.reward_coins * g.daily_limit} 个`
}

function startGame(g: GameItem) {
  say(gs('start', '开始啦！加油鸭~ 💪'))
  if (LOCAL_KEYS.has(g.slug)) {
    activeHtml.value = null
    activeGame.value = g.slug
    window.setTimeout(() => {
      const key = g.slug
      if (key === 'catch') startCatch()
      else if (key === 'bubble') startBubble()
      else if (key === 'memory') startMemory()
      else if (key === 'rps') startRps()
      else if (key === 'wheel') startWheel()
      else if (key === 'mole') startMole()
    }, 250)
    return
  }
  startHtmlGame(g)
}

async function startHtmlGame(g: GameItem) {
  activeGame.value = null
  activeHtml.value = g
  htmlGameStatus.value = null
  if (PUBLIC_HTML_GAMES[g.slug]) {
    htmlGameUrl.value = PUBLIC_HTML_GAMES[g.slug]
    htmlGameSrcdoc.value = ''
  } else {
    htmlGameUrl.value = ''
    try {
      const info = await getGameHtml(g.slug, { showGlobalLoading: false, showGlobalError: false })
      htmlGameSrcdoc.value = info.html
    } catch {
      say('游戏加载失败，请稍后再试~', 'chat', 2200)
    }
  }
  // 拉取今日领取状态
  if (session.isLoggedIn()) {
    try {
      const mod = await import('../api/games')
      const st = await mod.getGameMyStatus(g.slug, { showGlobalLoading: false, showGlobalError: false })
      htmlGameStatus.value = {
        reward_coins: st.reward_coins,
        daily_remaining: Math.max(0, st.daily_limit - st.claimed_today),
        claimed_today: st.claimed_today,
        daily_limit: st.daily_limit,
      }
    } catch { /* 忽略 */ }
  }
}

async function claimHtmlReward() {
  if (!activeHtml.value || claimingHtml.value) return
  if (!session.isLoggedIn()) {
    uiStore.openAuthDialog()
    return
  }
  claimingHtml.value = true
  try {
    const r = await claimGameReward(activeHtml.value.slug, 0, false, {
      showGlobalLoading: false,
      showGlobalError: false,
    }, pet.value?.id)
    const parts: string[] = []
    if (r.awarded > 0) parts.push(`金币 +${r.awarded}`)
    if (r.gained_affinity && r.gained_affinity > 0) {
      parts.push(`好感 +${r.gained_affinity}`)
      if (pet.value) pet.value.affinity = Math.min(100, (pet.value.affinity ?? 0) + r.gained_affinity)
    }
    if (parts.length) {
      say(`${parts.join('、')}！今天还能领 ${r.daily_remaining} 次金币~`, 'feedback', 2600)
    } else {
      say('今天的奖励都领完啦，明天再来~', 'chat', 2200)
    }
    htmlGameStatus.value = {
      reward_coins: r.reward_coins,
      daily_remaining: r.daily_remaining,
      claimed_today: Math.max(0, r.daily_limit - r.daily_remaining),
      daily_limit: r.daily_limit,
    }
    refreshDaily(activeHtml.value.slug)
  } catch {
    say('领取失败，稍后再试~', 'chat', 2200)
  } finally {
    claimingHtml.value = false
  }
}

function goBackToLobby() {
  // 游戏中：先回大厅；大厅页：返回上一级页面
  if (activeGame.value) {
    stopAll()
    activeGame.value = null
  } else if (activeHtml.value) {
    activeHtml.value = null
    htmlGameUrl.value = ''
    htmlGameSrcdoc.value = ''
    htmlGameStatus.value = null
  } else {
    router.back()
  }
}

// ================= 加分（互动冷却 + 金币/好感奖励） =================
let lastPlayReward = 0
async function rewardPlay(showMsg = true) {
  if (!pet.value || !session.isLoggedIn()) return
  const now = Date.now()
  if (now - lastPlayReward < 8000) {
    if (showMsg) say('玩得真棒！(冷却中，稍后再结算~)', 'chat', 2000)
    return
  }
  lastPlayReward = now
  // 本地游戏统一结算：金币 + 好感（由后端按该游戏每日上限控制）
  if (activeGame.value) {
    try {
      const r = await claimGameReward(activeGame.value, 0, false, {
        showGlobalLoading: false,
        showGlobalError: false,
      }, pet.value.id)
      if (r.awarded > 0 || (r.gained_affinity ?? 0) > 0) {
        pet.value.affinity = Math.min(100, (pet.value.affinity ?? 0) + (r.gained_affinity ?? 0))
        const parts: string[] = []
        if (r.awarded > 0) parts.push(`金币 +${r.awarded}`)
        if (r.gained_affinity && r.gained_affinity > 0) parts.push(`好感 +${r.gained_affinity}`)
        say(`${parts.join('、')}！玩得太棒啦~`, 'feedback', 2600)
      } else {
        say('今天的金币和好感都赚满啦，明天再来~', 'chat', 2200)
      }
      // 刷新卡片剩余量
      refreshDaily(activeGame.value)
    } catch { /* 忽略 */ }
  }
}

function refreshDaily(slug: string) {
  if (!session.isLoggedIn()) return
  getGameMyStatus(slug, { showGlobalLoading: false, showGlobalError: false })
    .then((st) => {
      gameDaily.value = {
        ...gameDaily.value,
        [slug]: {
          coins_remaining: Math.max(0, st.daily_limit - st.claimed_today) * st.reward_coins,
          affinity_remaining: Math.max(0, (st.affinity_daily_limit || 0) - (st.affinity_today || 0)),
        },
      }
    })
    .catch(() => { /* 忽略 */ })
}

// ================= 制作游戏 =================
const showSubmit = ref(false)
const submitName = ref('')
const submitType = ref<'single' | 'multi'>('single')
const submitDesc = ref('')
const submitFile = ref<File | null>(null)
const submitting = ref(false)

function openSubmit() {
  if (!session.isLoggedIn()) {
    uiStore.openAuthDialog()
    return
  }
  submitName.value = ''
  submitType.value = 'single'
  submitDesc.value = ''
  submitFile.value = null
  showSubmit.value = true
}

function onPickFile(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0] ?? null
  if (f && !f.name.toLowerCase().endsWith('.html') && !f.name.toLowerCase().endsWith('.htm')) {
    say('请选择 .html 文件~', 'chat', 2200)
    submitFile.value = null
    return
  }
  submitFile.value = f
}

async function doSubmit() {
  if (submitting.value) return
  if (!submitName.value.trim()) {
    say('请填写游戏名称~', 'chat', 2000)
    return
  }
  if (!submitFile.value) {
    say('请上传游戏 HTML 文件~', 'chat', 2000)
    return
  }
  submitting.value = true
  try {
    await submitUserGame({
      name: submitName.value.trim(),
      type: submitType.value,
      description: submitDesc.value.trim(),
      file: submitFile.value,
    })
    showSubmit.value = false
    say('提交成功！审核通过后就会上架啦~ 🎉', 'feedback', 3000)
  } catch {
    say('提交失败，请稍后再试~', 'chat', 2200)
  } finally {
    submitting.value = false
  }
}

// ================= 本地游戏最佳战绩 =================
function bestScore(key: string): number {
  return Number(localStorage.getItem(`pet_play_best_${key}`) ?? 0)
}
function recordBest(key: string, score: number, lowerIsBetter = false) {
  const prev = bestScore(key)
  const isNewBest = lowerIsBetter ? prev === 0 || score < prev : score > prev
  if (isNewBest) {
    localStorage.setItem(`pet_play_best_${key}`, String(score))
    if (session.isLoggedIn()) {
      const rankScore = lowerIsBetter ? Math.max(0, 100 - score * 10) : score
      submitGameScore(key, rankScore, {
        showGlobalLoading: false,
        showGlobalError: false,
      }).catch(() => { /* 排行榜上报失败不打扰游戏 */ })
    }
  }
}

// ================= 本地游戏：接零食 =================
interface CatchItem { id: number; x: number; y: number; speed: number; emoji: string; size: number }
const CATCH_EMOJIS = ['🍎', '🍗', '🍩', '🍰', '🥕', '🍉', '🍓', '🍿']
const catchState = reactive({
  running: false,
  score: 0,
  lives: 5,
  time: 30,
  bowlX: 50,
  items: [] as CatchItem[],
  boom: [] as { id: number; x: number; emoji: string }[],
})
let catchSeq = 0
let catchRaf = 0
let catchLast = 0
let catchClock = 0
let catchTimer: number | null = null

function onCatchMove(e: PointerEvent) {
  if (!catchState.running) return
  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
  catchState.bowlX = Math.min(94, Math.max(6, ((e.clientX - rect.left) / rect.width) * 100))
}

function startCatch() {
  catchState.running = true
  catchState.score = 0
  catchState.lives = 5
  catchState.time = 30
  catchState.items = []
  catchState.bowlX = 50
  catchState.boom = []
  catchLast = performance.now()
  catchClock = 0
  catchTimer = window.setInterval(() => {
    if (catchState.running) catchState.time -= 1
  }, 1000)
  catchRaf = requestAnimationFrame(stepCatch)
  say('快！帮我接住好吃的！', 'chat', 1600)
}

function stepCatch(now: number) {
  if (!catchState.running) return
  const dt = Math.min(50, now - catchLast)
  catchLast = now
  catchClock += dt
  for (const it of catchState.items) it.y += it.speed * (dt / 16.6)
  const rest: CatchItem[] = []
  const boomBatch: { id: number; x: number; emoji: string }[] = []
  for (const it of catchState.items) {
    if (it.y > 92) {
      catchState.lives -= 1
      boomBatch.push({ id: it.id, x: it.x, emoji: '💥' })
      continue
    }
    if (it.y > 76 && Math.abs(it.x - catchState.bowlX) < 11) {
      catchState.score += 1
      boomBatch.push({ id: it.id, x: it.x, emoji: it.emoji })
      continue
    }
    rest.push(it)
  }
  catchState.items = rest
  if (boomBatch.length) catchState.boom.push(...boomBatch)
  if (catchClock >= 150 && catchState.items.length < 9) {
    const elapsed = 30 - catchState.time
    // 随时间逐渐加快：下落速度逐步提升，产物也更密（更难接）
    const spawnInterval = Math.max(250, 650 - elapsed * 14)
    if (catchClock >= spawnInterval) {
      catchState.items.push({
        id: catchSeq++,
        x: 6 + Math.random() * 88,
        y: -6,
        speed: 0.22 + Math.random() * 0.14 + elapsed * 0.022,
        emoji: CATCH_EMOJIS[Math.floor(Math.random() * CATCH_EMOJIS.length)],
        size: 20 + Math.random() * 8,
      })
      catchClock = 0
    }
  }
  if (catchState.boom.length) {
    window.setTimeout(() => {
      catchState.boom = []
    }, 500)
  }
  if (catchState.lives <= 0 || catchState.time <= 0) {
    endCatch()
    return
  }
  catchRaf = requestAnimationFrame(stepCatch)
}

function endCatch() {
  catchState.running = false
  if (catchTimer !== null) { window.clearInterval(catchTimer); catchTimer = null }
  catchState.items = []
  const s = catchState.score
  recordBest('catch', s)
  if (s >= 15) { reactWin(); rewardPlay() }
  else if (s >= 8) { say(gs('good', `接住 ${s} 个！不错哦~ (+好感)`), 'feedback', 2400); rewardPlay() }
  else reactLose()
}

function stopCatch() {
  catchState.running = false
  if (catchTimer !== null) { window.clearInterval(catchTimer); catchTimer = null }
}

// ================= 本地游戏：戳泡泡 =================
interface BubbleItem { id: number; x: number; y: number; size: number; dur: number; hue: string }
const bubbleState = reactive({
  running: false,
  score: 0,
  time: 30,
  bubbles: [] as BubbleItem[],
  pops: [] as { id: number; x: number; y: number; emoji: string }[],
})
let bubbleSeq = 0
let bubbleTimer: number | null = null
let bubbleSpawnTimer: number | null = null

function startBubble() {
  bubbleState.running = true
  bubbleState.score = 0
  bubbleState.time = 30
  bubbleState.bubbles = []
  bubbleState.pops = []
  bubbleTimer = window.setInterval(() => {
    if (bubbleState.running) bubbleState.time -= 1
  }, 1000)
  bubbleSpawnTimer = window.setInterval(spawnBubble, 520)
  for (let i = 0; i < 4; i++) window.setTimeout(spawnBubble, i * 160)
  say('泡泡飞起来啦，戳戳戳！', 'chat', 1600)
}

function spawnBubble() {
  if (!bubbleState.running || bubbleState.bubbles.length >= 12) return
  const hues = ['#ff6b81', '#5b8cff', '#ffb347', '#00c9a7', '#a18cd1', '#ff8a5c']
  bubbleState.bubbles.push({
    id: bubbleSeq++,
    x: 8 + Math.random() * 80,
    y: 5 + Math.random() * 45,
    size: 34 + Math.random() * 26,
    dur: 5.5 + Math.random() * 4,
    hue: hues[Math.floor(Math.random() * hues.length)],
  })
}

function popBubble(b: BubbleItem) {
  const idx = bubbleState.bubbles.findIndex((x) => x.id === b.id)
  if (idx < 0) return
  bubbleState.bubbles.splice(idx, 1)
  bubbleState.score += 1
  bubbleState.pops.push({ id: b.id, x: b.x, y: b.y, emoji: '✨' })
  window.setTimeout(() => {
    bubbleState.pops = bubbleState.pops.filter((p) => p.id !== b.id)
  }, 600)
  if (bubbleState.score === 1) say('哇！一下就戳中了！', 'chat', 1500)
}

/** 点击泡泡区域：用命中测试找到被点的具体泡泡再戳破（兼容动画/变换导致的点击失效） */
function onBubbleFieldClick(e: MouseEvent | TouchEvent) {
  if (!bubbleState.running) return
  const x = 'clientX' in e ? e.clientX : e.touches?.[0]?.clientX
  const y = 'clientY' in e ? e.clientY : e.touches?.[0]?.clientY
  if (x == null || y == null) return
  if ('touches' in e && e.touches.length === 0 && e.type === 'touchend') {
    // touchend 时无 touches，改用 changedTouches
  }
  let el: Element | null = document.elementFromPoint(x, y)
  // 沿命中链向上找最近的泡泡元素
  while (el && !(el instanceof HTMLElement && el.dataset.bubbleId)) {
    el = el.parentElement
  }
  if (el && el instanceof HTMLElement && el.dataset.bubbleId) {
    const id = Number(el.dataset.bubbleId)
    const b = bubbleState.bubbles.find((bb) => bb.id === id)
    if (b) popBubble(b)
  }
}

function endBubble() {
  bubbleState.running = false
  if (bubbleTimer !== null) { window.clearInterval(bubbleTimer); bubbleTimer = null }
  if (bubbleSpawnTimer !== null) { window.clearInterval(bubbleSpawnTimer); bubbleSpawnTimer = null }
  bubbleState.bubbles = []
  const s = bubbleState.score
  recordBest('bubble', s)
  if (s >= 20) { reactWin(); rewardPlay() }
  else if (s >= 10) { say(gs('good', `戳爆 ${s} 个！手速可以！(+好感)`), 'feedback', 2400); rewardPlay() }
  else reactLose()
}

function stopBubble() {
  bubbleState.running = false
  if (bubbleTimer !== null) { window.clearInterval(bubbleTimer); bubbleTimer = null }
  if (bubbleSpawnTimer !== null) { window.clearInterval(bubbleSpawnTimer); bubbleSpawnTimer = null }
}

// ================= 本地游戏：记忆翻牌 =================
const MEM_EMOJIS = ['🍎', '🐟', '🍭', '🎾', '🐾', '⭐']
const memoryState = reactive({
  running: false,
  cards: [] as { id: number; emoji: string; open: boolean; matched: boolean }[],
  openIds: [] as number[],
  moves: 0,
  pairs: 6,
  finished: false,
})
let memTimer: number | null = null
let memFlipTimer: number | null = null
let memSeq = 0

function startMemory() {
  memSeq = 0
  const list: { id: number; emoji: string; open: boolean; matched: boolean }[] = []
  for (let i = 0; i < 2; i++) {
    for (const emoji of MEM_EMOJIS) {
      list.push({ id: memSeq++, emoji, open: false, matched: false })
    }
  }
  for (let i = list.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[list[i], list[j]] = [list[j], list[i]]
  }
  memoryState.cards = list
  memoryState.openIds = []
  memoryState.moves = 0
  memoryState.pairs = 6
  memoryState.finished = false
  memoryState.running = true
  say('翻开两张一样的就配对啦！', 'chat', 1800)
}

function flipCard(card: { id: number; open: boolean; matched: boolean }) {
  if (!memoryState.running || memoryState.finished) return
  if (card.matched || card.open) return
  if (memoryState.openIds.length >= 2) return
  card.open = true
  memoryState.openIds.push(card.id)
  if (memoryState.openIds.length === 2) {
    memoryState.moves += 1
    const [a, b] = memoryState.openIds
    const ca = memoryState.cards.find((c) => c.id === a)!
    const cb = memoryState.cards.find((c) => c.id === b)!
    if (ca.emoji === cb.emoji) {
      ca.matched = true
      cb.matched = true
      memoryState.openIds = []
      memoryState.pairs -= 1
      if (memoryState.pairs === 0) endMemory()
    } else {
      if (memFlipTimer !== null) window.clearTimeout(memFlipTimer)
      memFlipTimer = window.setTimeout(() => {
        ca.open = false
        cb.open = false
        memoryState.openIds = []
      }, 700)
    }
  }
}

function endMemory() {
  memoryState.running = false
  memoryState.finished = true
  recordBest('memory', memoryState.moves)
  say(gs('win', `全配对了！只用 ${memoryState.moves} 步，聪明！(+好感)`), 'feedback', 2800)
  rewardPlay()
}

function stopMemory() {
  memoryState.running = false
  if (memTimer !== null) { window.clearInterval(memTimer); memTimer = null }
  if (memFlipTimer !== null) { window.clearTimeout(memFlipTimer); memFlipTimer = null }
}

// ================= 本地游戏：猜拳 =================
type Rps = 'rock' | 'scissors' | 'paper'
const RPS_META: Record<Rps, { emoji: string; label: string }> = {
  rock: { emoji: '✊', label: '石头' },
  scissors: { emoji: '✌️', label: '剪刀' },
  paper: { emoji: '🖐️', label: '布' },
}
const RPS_BEATS: Record<Rps, Rps> = { rock: 'scissors', scissors: 'paper', paper: 'rock' }
const rpsState = reactive({
  running: false,
  myPick: null as Rps | null,
  petPick: null as Rps | null,
  myScore: 0,
  petScore: 0,
  round: 1,
  result: '' as string,
  showHands: false,
})
let rpsTimer: number | null = null

function startRps() {
  rpsState.running = true
  rpsState.myPick = null
  rpsState.petPick = null
  rpsState.myScore = 0
  rpsState.petScore = 0
  rpsState.round = 1
  rpsState.result = ''
  rpsState.showHands = false
  say('石头剪刀布，准备好了吗？', 'chat', 1800)
}

function rpsChoose(pick: Rps) {
  if (!rpsState.running || rpsState.myPick) return
  rpsState.myPick = pick
  rpsState.showHands = false
  const petPick: Rps = (['rock', 'scissors', 'paper'] as Rps[])[Math.floor(Math.random() * 3)]
  rpsState.petPick = null
  if (rpsTimer !== null) window.clearTimeout(rpsTimer)
  rpsTimer = window.setTimeout(() => {
    rpsState.petPick = petPick
    rpsState.showHands = true
    rpsTimer = window.setTimeout(() => settleRps(pick, petPick), 500)
  }, 500)
}

function settleRps(my: Rps, pet: Rps) {
  let msg = ''
  if (my === pet) {
    msg = '平局！再来！'
  } else if (RPS_BEATS[my] === pet) {
    rpsState.myScore += 1
    msg = '你赢啦！'
  } else {
    rpsState.petScore += 1
    msg = '哎呀，我赢咯~'
  }
  rpsState.result = msg
  rpsState.round += 1
  if (rpsState.myScore >= 2 || rpsState.petScore >= 2) {
    rpsState.running = false
    const win = rpsState.myScore >= 2
    recordBest('rps', rpsState.myScore)
    if (win) { reactWin(); rewardPlay() }
    else reactLose()
  } else {
    rpsTimer = window.setTimeout(() => {
      rpsState.myPick = null
      rpsState.petPick = null
      rpsState.result = ''
      rpsState.showHands = false
    }, 1300)
  }
}

function stopRps() {
  rpsState.running = false
  if (rpsTimer !== null) { window.clearTimeout(rpsTimer); rpsTimer = null }
}

// ================= 本地游戏：幸运轮 =================
const WHEEL_SEGS = [
  { label: '好感+3', color: '#ff6b81', weight: 1 },
  { label: '好感+1', color: '#ffb347', weight: 2 },
  { label: '再来一次', color: '#5b8cff', weight: 1 },
  { label: '好感+2', color: '#00c9a7', weight: 2 },
  { label: '神秘礼物', color: '#a18cd1', weight: 1 },
  { label: '好感+5', color: '#ff8a5c', weight: 1 },
]
const wheelState = reactive({
  spinning: false,
  angle: 0,
  result: '',
  landed: false,
})

function startWheel() {
  wheelState.angle = 0
  wheelState.result = ''
  wheelState.landed = false
  wheelState.spinning = false
  say('转一转，看看今天运气如何！', 'chat', 1800)
}

function spinWheel() {
  if (wheelState.spinning) return
  wheelState.spinning = true
  wheelState.result = ''
  wheelState.landed = false
  const spins = 5 + Math.floor(Math.random() * 3)
  const final = wheelState.angle + spins * 360 + Math.random() * 360
  wheelState.angle = final
  const seg = WHEEL_SEGS[Math.floor(Math.random() * WHEEL_SEGS.length)]
  window.setTimeout(() => {
    wheelState.spinning = false
    wheelState.landed = true
    wheelState.result = seg.label
    if (seg.label.startsWith('好感')) {
      say(`恭喜抽到「${seg.label}」！🎉`, 'feedback', 2600)
      rewardPlay()
    } else if (seg.label === '再来一次') {
      say('再来一次！好运正在路上~', 'chat', 2200)
    } else {
      say('神秘礼物？哈哈我帮你保管了~ 🎁', 'feedback', 2600)
      rewardPlay()
    }
    recordBest('wheel', 1)
  }, 4600)
}

// ================= 本地游戏：打地鼠 =================
const moleState = reactive({
  running: false,
  score: 0,
  time: 30,
  holes: [false, false, false, false, false, false, false, false, false],
  activeIdx: -1,
})
let moleTimer: number | null = null
let moleSpawnTimer: number | null = null
let moleHideTimer: number | null = null

function startMole() {
  moleState.running = true
  moleState.score = 0
  moleState.time = 30
  moleState.holes = [false, false, false, false, false, false, false, false, false]
  moleState.activeIdx = -1
  moleTimer = window.setInterval(() => {
    if (moleState.running) moleState.time -= 1
  }, 1000)
  moleSpawnTimer = window.setInterval(spawnMole, 950)
  window.setTimeout(spawnMole, 300)
  say('小地鼠冒头啦，快敲它！', 'chat', 1600)
}

function spawnMole() {
  if (!moleState.running) return
  const idx = Math.floor(Math.random() * 9)
  moleState.activeIdx = idx
  moleState.holes[idx] = true
  if (moleHideTimer !== null) window.clearTimeout(moleHideTimer)
  moleHideTimer = window.setTimeout(() => {
    if (moleState.activeIdx === idx) {
      moleState.holes[idx] = false
      moleState.activeIdx = -1
    }
  }, 950)
}

function whack(idx: number) {
  if (!moleState.running) return
  if (moleState.holes[idx]) {
    moleState.holes[idx] = false
    moleState.activeIdx = -1
    moleState.score += 1
    if (moleState.score === 1) say('嗷！敲中了！', 'chat', 1200)
  }
}

function endMole() {
  moleState.running = false
  if (moleTimer !== null) { window.clearInterval(moleTimer); moleTimer = null }
  if (moleSpawnTimer !== null) { window.clearInterval(moleSpawnTimer); moleSpawnTimer = null }
  if (moleHideTimer !== null) { window.clearTimeout(moleHideTimer); moleHideTimer = null }
  moleState.holes = [false, false, false, false, false, false, false, false, false]
  const s = moleState.score
  recordBest('mole', s)
  if (s >= 18) { reactWin(); rewardPlay() }
  else if (s >= 10) { say(`敲中 ${s} 只！好眼力！(+好感)`, 'feedback', 2400); rewardPlay() }
  else reactLose()
}

function stopMole() {
  moleState.running = false
  if (moleTimer !== null) { window.clearInterval(moleTimer); moleTimer = null }
  if (moleSpawnTimer !== null) { window.clearInterval(moleSpawnTimer); moleSpawnTimer = null }
  if (moleHideTimer !== null) { window.clearTimeout(moleHideTimer); moleHideTimer = null }
}

/** 停止所有本地小游戏（退出/卸载页面时调用） */
function stopAll() {
  stopCatch()
  stopBubble()
  stopMemory()
  stopRps()
  stopMole()
}

// ================= 数据加载 =================
async function loadPet() {
  loading.value = true
  try {
    if (!session.isLoggedIn()) {
      pets.value = []
      loading.value = false
      return
    }
    const { data } = await listMyPets({ showGlobalLoading: false, showGlobalError: false })
    const items: MyPetItem[] = data.data.items ?? []
    pets.value = items
    const savedId = Number(localStorage.getItem(PET_KEY))
    const found = items.find((p) => p.id === savedId) ?? items[0] ?? null
    pet.value = found
    loadGameSpeech(found)
  } catch {
    pets.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadPet()
  loadGames()
})

onBeforeUnmount(() => {
  stopAll()
  if (sayTimer !== null) window.clearTimeout(sayTimer)
})

function goShop() {
  router.push('/pet-shop')
}
</script>

<template>
  <div class="pet-play">
    <!-- 背景装饰 -->
    <div class="pp-bg">
      <i class="pp-bg__blob pp-bg__blob--1"></i>
      <i class="pp-bg__blob pp-bg__blob--2"></i>
      <i class="pp-bg__blob pp-bg__blob--3"></i>
      <span class="pp-bg__star" style="left: 8%; top: 12%">✦</span>
      <span class="pp-bg__star" style="left: 86%; top: 8%">✦</span>
      <span class="pp-bg__star" style="left: 72%; top: 26%">✦</span>
      <span class="pp-bg__star" style="left: 16%; top: 30%">✦</span>
    </div>

    <!-- 顶部栏 -->
    <header class="pp-header">
      <button class="pp-header__back" type="button" aria-label="返回" @click="goBackToLobby">
        <span class="pp-header__back-icon">←</span>
      </button>
      <div class="pp-header__title">
        <span class="pp-header__title-emoji">🎮</span>
        <h1>游戏中心</h1>
      </div>
      <div v-if="pet" class="pp-header__pet">
        <span class="pp-header__pet-lv">Lv{{ pet.level }}</span>
        <span class="pp-header__pet-aff">{{ pet.affinity }}</span>
        <span class="pp-header__pet-heart">❤</span>
      </div>
    </header>

    <!-- 宠物舞台 -->
    <section class="pp-stage">
      <div v-if="loading" class="pp-stage__loading">
        <span class="pp-stage__loading-dot"></span>
        <span class="pp-stage__loading-dot"></span>
        <span class="pp-stage__loading-dot"></span>
      </div>
      <template v-else-if="pet?.anim">
        <div class="pp-stage__pet" :class="{ 'is-dancing': petSayType === 'feedback' }">
          <PetAnimation
            ref="petRef"
            :anim="pet.anim"
            :size="132"
            :interactive="false"
            :show-tabs="false"
          />
        </div>
        <!-- 对话气泡 -->
        <Transition name="pp-say">
          <div v-if="petSay" class="pp-stage__bubble" :class="{ 'is-feedback': petSayType === 'feedback' }">
            {{ petSay }}
          </div>
        </Transition>
      </template>
      <div v-else class="pp-stage__empty">
        <div class="pp-stage__empty-icon">🐾</div>
        <p class="pp-stage__empty-text">{{ session.isLoggedIn() ? '还没有宠物伙伴，去领养一只吧！' : '登录后就能和宠物一起玩啦' }}</p>
        <button class="pp-stage__empty-btn" type="button" @click="goShop">去领养 →</button>
      </div>
    </section>

    <!-- 游戏大厅 -->
    <section v-if="!inGame" class="pp-lobby">
      <!-- 分类 TAB + 制作游戏 -->
      <div class="pp-tabs">
        <div class="pp-tabs__nav">
          <button
            type="button"
            class="pp-tabs__btn"
            :class="{ active: gameTab === 'single' }"
            @click="gameTab = 'single'"
          >
            单人游戏
          </button>
          <button
            type="button"
            class="pp-tabs__btn"
            :class="{ active: gameTab === 'multi' }"
            @click="gameTab = 'multi'"
          >
            多人游戏
          </button>
        </div>
        <button type="button" class="pp-tabs__create" @click="openSubmit">
          <span class="pp-tabs__create-icon">＋</span>
          制作游戏
        </button>
      </div>

      <!-- 多人游戏占位 -->
      <div v-if="gameTab === 'multi'" class="pp-multi">
        <div class="pp-multi__icon">👥</div>
        <p class="pp-multi__title">多人游戏开发中，敬请期待～</p>
        <p class="pp-multi__desc">先玩玩单人游戏赚金币，多人对战很快就会上线！</p>
      </div>

      <!-- 单人游戏网格 -->
      <template v-else>
        <div v-if="loadingGames" class="pp-lobby__loading">加载游戏中…</div>
        <div v-else-if="singleGames.length" class="pp-lobby__grid">
          <button
            v-for="g in singleGames"
            :key="g.id"
            class="game-card"
            type="button"
            @click="startGame(g)"
          >
            <span class="game-card__icon">{{ g.icon_url }}</span>
            <span class="game-card__info">
              <span class="game-card__name">{{ g.name }}</span>
              <span class="game-card__desc">{{ g.description }}</span>
            </span>
            <span class="game-card__play">
              <span class="game-card__reward">{{ dailyCoinsText(g) }}</span>
              <span v-if="gameDaily[g.slug]" class="game-card__affinity">❤ 今天还能 +{{ gameDaily[g.slug].affinity_remaining }} 好感</span>
              <span v-if="LOCAL_KEYS.has(g.slug) && bestScore(g.slug) > 0" class="game-card__best">最佳 {{ bestScore(g.slug) }}</span>
              <span class="game-card__go">▶</span>
            </span>
          </button>
        </div>
        <div v-else class="pp-lobby__empty">
          <p>暂无上架的单人游戏，快去「制作游戏」投稿吧！</p>
        </div>
      </template>
    </section>

    <!-- 游戏区域 -->
    <section v-else class="pp-game">
      <!-- HTML 小游戏（iframe 内嵌当前页面） -->
      <div v-if="activeHtml" class="pp-html">
        <div class="pp-html__bar">
          <span class="pp-html__name">{{ activeHtml.icon_url }} {{ activeHtml.name }}</span>
          <button type="button" class="pp-html__quit" @click="goBackToLobby">返回大厅</button>
        </div>
        <div class="pp-html__frame">
          <iframe
            v-if="htmlGameUrl"
            :src="htmlGameUrl"
            class="pp-html__iframe"
            allow="fullscreen"
            sandbox="allow-scripts allow-same-origin allow-pointer-lock allow-modals allow-popups"
          />
          <iframe
            v-else-if="htmlGameSrcdoc"
            :srcdoc="htmlGameSrcdoc"
            class="pp-html__iframe"
            allow="fullscreen"
            sandbox="allow-scripts allow-same-origin allow-pointer-lock allow-modals allow-popups"
          />
          <div v-else class="pp-html__loading">游戏加载中…</div>
        </div>
        <div class="pp-html__footer">
          <button type="button" class="pp-html__claim" :disabled="claimingHtml" @click="claimHtmlReward">
            <span class="pp-html__claim-icon">💰</span>
            领取金币
            <span v-if="activeHtml" class="pp-html__claim-sub">+{{ activeHtml.reward_coins }}/次</span>
          </button>
          <span v-if="htmlGameStatus" class="pp-html__left">
            今日已领 {{ htmlGameStatus.claimed_today }}/{{ htmlGameStatus.daily_limit }} 次
          </span>
          <span v-else class="pp-html__left">玩完一局点按钮领金币</span>
        </div>
      </div>

      <!-- 本地宠物小游戏 -->
      <template v-else>
        <!-- 通用顶栏 -->
        <div class="pp-game__bar">
          <div v-if="activeGame === 'catch' || activeGame === 'bubble' || activeGame === 'mole'" class="pp-game__hud">
            <span class="pp-game__hud-item">⏱ {{ activeGame === 'catch' ? catchState.time : activeGame === 'bubble' ? bubbleState.time : moleState.time }}s</span>
            <span class="pp-game__hud-item pp-game__hud-item--score">⭐ {{ activeGame === 'catch' ? catchState.score : activeGame === 'bubble' ? bubbleState.score : moleState.score }}</span>
            <span v-if="activeGame === 'catch'" class="pp-game__hud-item pp-game__hud-item--lives">❤️ {{ catchState.lives }}</span>
          </div>
          <button class="pp-game__quit" type="button" @click="goBackToLobby">退出</button>
        </div>

        <!-- 1. 接零食 -->
        <div v-if="activeGame === 'catch'" class="catch-game" @pointermove="onCatchMove">
          <TransitionGroup name="pp-fall" tag="div" class="catch-game__items">
            <span
              v-for="it in catchState.items"
              :key="it.id"
              class="catch-game__item"
              :style="{ left: it.x + '%', top: it.y + '%', fontSize: it.size + 'px' }"
            >{{ it.emoji }}</span>
          </TransitionGroup>
          <TransitionGroup name="pp-boom" tag="div" class="catch-game__booms">
            <span
              v-for="b in catchState.boom"
              :key="b.id"
              class="catch-game__boom"
              :style="{ left: b.x + '%' }"
            >{{ b.emoji }}</span>
          </TransitionGroup>
          <div class="catch-game__bowl" :style="{ left: catchState.bowlX + '%' }">
            <span class="catch-game__bowl-emoji">🥣</span>
          </div>
          <div v-if="!catchState.running" class="catch-game__overlay">
            <div class="catch-game__overlay-card">
              <p class="catch-game__overlay-title">接住 {{ catchState.score }} 个零食！</p>
              <div class="catch-game__overlay-actions">
                <button type="button" @click="startCatch">再来一局</button>
                <button type="button" @click="goBackToLobby">返回大厅</button>
              </div>
            </div>
          </div>
        </div>

        <!-- 2. 戳泡泡 -->
        <div v-else-if="activeGame === 'bubble'" class="bubble-game">
          <div class="bubble-game__field" @click="onBubbleFieldClick">
            <TransitionGroup name="pp-bubble" tag="div" class="bubble-game__inner">
              <span
                v-for="b in bubbleState.bubbles"
                :key="b.id"
                class="bubble-game__bubble"
                :style="{
                  left: b.x + '%',
                  bottom: b.y + '%',
                  width: b.size + 'px',
                  height: b.size + 'px',
                  animationDuration: b.dur + 's',
                  background: `radial-gradient(circle at 32% 30%, rgba(255,255,255,.85), ${b.hue} 58%, rgba(23,32,64,.15))`,
                }"
                :data-bubble-id="b.id"
              ></span>
            </TransitionGroup>
          </div>
          <TransitionGroup name="pp-boom" tag="div" class="bubble-game__pops">
            <span
              v-for="p in bubbleState.pops"
              :key="p.id"
              class="bubble-game__pop"
              :style="{ left: p.x + '%', bottom: p.y + '%' }"
            >{{ p.emoji }}</span>
          </TransitionGroup>
          <div v-if="!bubbleState.running" class="bubble-game__overlay">
            <div class="bubble-game__overlay-card">
              <p class="bubble-game__overlay-title">戳爆 {{ bubbleState.score }} 个泡泡！</p>
              <div class="bubble-game__overlay-actions">
                <button type="button" @click="startBubble">再来一局</button>
                <button type="button" @click="goBackToLobby">返回大厅</button>
              </div>
            </div>
          </div>
        </div>

        <!-- 3. 记忆翻牌 -->
        <div v-else-if="activeGame === 'memory'" class="memory-game">
          <div class="memory-game__hud">
            <span class="memory-game__hud-item">剩余 {{ memoryState.pairs }} 对</span>
            <span class="memory-game__hud-item">步数 {{ memoryState.moves }}</span>
          </div>
          <div class="memory-game__grid">
            <button
              v-for="c in memoryState.cards"
              :key="c.id"
              class="memory-card"
              :class="{ 'is-open': c.open, 'is-matched': c.matched }"
              type="button"
              @click="flipCard(c)"
            >
              <span class="memory-card__face memory-card__face--back">?</span>
              <span class="memory-card__face memory-card__face--front">{{ c.emoji }}</span>
            </button>
          </div>
          <div v-if="memoryState.finished" class="memory-game__overlay">
            <div class="memory-game__overlay-card">
              <p class="memory-game__overlay-title">🎉 全部配对成功！</p>
              <p class="memory-game__overlay-sub">用了 {{ memoryState.moves }} 步</p>
              <div class="memory-game__overlay-actions">
                <button type="button" @click="startMemory">再来一局</button>
                <button type="button" @click="goBackToLobby">返回大厅</button>
              </div>
            </div>
          </div>
        </div>

        <!-- 4. 猜拳 -->
        <div v-else-if="activeGame === 'rps'" class="rps-game">
          <div class="rps-game__score">
            <div class="rps-game__score-side">
              <span class="rps-game__score-name">你</span>
              <span class="rps-game__score-num">{{ rpsState.myScore }}</span>
            </div>
            <span class="rps-game__score-vs">VS</span>
            <div class="rps-game__score-side">
              <span class="rps-game__score-name">{{ pet?.nickname || pet?.name || '宠物' }}</span>
              <span class="rps-game__score-num">{{ rpsState.petScore }}</span>
            </div>
          </div>
          <div class="rps-game__hands">
            <div class="rps-game__hand">
              <span class="rps-game__hand-emoji">{{ rpsState.myPick ? RPS_META[rpsState.myPick].emoji : '👊' }}</span>
              <span class="rps-game__hand-label">{{ rpsState.myPick ? RPS_META[rpsState.myPick].label : '…' }}</span>
            </div>
            <div class="rps-game__hand">
              <span class="rps-game__hand-emoji" :class="{ 'is-flip': rpsState.showHands }">
                {{ rpsState.petPick ? RPS_META[rpsState.petPick].emoji : '👊' }}
              </span>
              <span class="rps-game__hand-label">{{ rpsState.petPick ? RPS_META[rpsState.petPick].label : '…' }}</span>
            </div>
          </div>
          <Transition name="pp-say">
            <p v-if="rpsState.result" class="rps-game__result">{{ rpsState.result }}</p>
          </Transition>
          <div class="rps-game__pick">
            <button
              v-for="(meta, key) in RPS_META"
              :key="key"
              class="rps-game__pick-btn"
              type="button"
              :class="{ 'is-picked': rpsState.myPick === key }"
              :disabled="!!rpsState.myPick || !rpsState.running"
              @click="rpsChoose(key as Rps)"
            >
              <span class="rps-game__pick-emoji">{{ meta.emoji }}</span>
              <span class="rps-game__pick-label">{{ meta.label }}</span>
            </button>
          </div>
          <div v-if="!rpsState.running" class="rps-game__overlay">
            <div class="rps-game__overlay-card">
              <p class="rps-game__overlay-title">{{ rpsState.myScore >= 2 ? '🎉 你赢啦！' : '你输啦~ 再来！' }}</p>
              <div class="rps-game__overlay-actions">
                <button type="button" @click="startRps">再来一局</button>
                <button type="button" @click="goBackToLobby">返回大厅</button>
              </div>
            </div>
          </div>
        </div>

        <!-- 5. 幸运轮 -->
        <div v-else-if="activeGame === 'wheel'" class="wheel-game">
          <div class="wheel-game__wrap">
            <div
              class="wheel-game__wheel"
              :style="{ transform: `rotate(${wheelState.angle}deg)` }"
            >
              <div
                v-for="(seg, i) in WHEEL_SEGS"
                :key="i"
                class="wheel-game__seg"
                :style="{
                  background: seg.color,
                  transform: `rotate(${i * 60}deg)`,
                }"
              >
                <span class="wheel-game__seg-label" :style="{ transform: `rotate(${i * 60}deg)` }">{{ seg.label }}</span>
              </div>
              <span class="wheel-game__hub">🎡</span>
            </div>
            <span class="wheel-game__pointer">▼</span>
          </div>
          <button class="wheel-game__spin" type="button" :disabled="wheelState.spinning" @click="spinWheel">
            {{ wheelState.spinning ? '转动中…' : '转一次' }}
          </button>
          <Transition name="pp-say">
            <p v-if="wheelState.result" class="wheel-game__result">🎉 抽到：{{ wheelState.result }}</p>
          </Transition>
        </div>

        <!-- 6. 打地鼠 -->
        <div v-else-if="activeGame === 'mole'" class="mole-game">
          <div class="mole-game__field">
            <button
              v-for="(up, i) in moleState.holes"
              :key="i"
              class="mole-game__hole"
              type="button"
              @click="whack(i)"
            >
              <span class="mole-game__dirt">🌰</span>
              <Transition name="pp-mole">
                <span v-if="up" class="mole-game__mole">🐹</span>
              </Transition>
            </button>
          </div>
          <div v-if="!moleState.running" class="mole-game__overlay">
            <div class="mole-game__overlay-card">
              <p class="mole-game__overlay-title">敲中 {{ moleState.score }} 只地鼠！</p>
              <div class="mole-game__overlay-actions">
                <button type="button" @click="startMole">再来一局</button>
                <button type="button" @click="goBackToLobby">返回大厅</button>
              </div>
            </div>
          </div>
        </div>
      </template>
    </section>

    <!-- 制作游戏弹窗 -->
    <Teleport to="body">
      <Transition name="pp-modal">
        <div v-if="showSubmit" class="pp-modal" @click.self="showSubmit = false">
          <div class="pp-modal__card">
            <div class="pp-modal__head">
              <h3 class="pp-modal__title">🎨 制作游戏</h3>
              <button type="button" class="pp-modal__close" @click="showSubmit = false">✕</button>
            </div>
            <div class="pp-modal__body">
              <label class="pp-modal__field">
                <span class="pp-modal__label">游戏名称</span>
                <input v-model="submitName" class="pp-modal__input" maxlength="30" placeholder="给你的游戏起个名字" />
              </label>
              <label class="pp-modal__field">
                <span class="pp-modal__label">游戏类型</span>
                <div class="pp-modal__types">
                  <button
                    type="button"
                    class="pp-modal__type"
                    :class="{ active: submitType === 'single' }"
                    @click="submitType = 'single'"
                  >单人游戏</button>
                  <button
                    type="button"
                    class="pp-modal__type"
                    :class="{ active: submitType === 'multi' }"
                    @click="submitType = 'multi'"
                  >多人游戏</button>
                </div>
              </label>
              <label class="pp-modal__field">
                <span class="pp-modal__label">简介（选填）</span>
                <input v-model="submitDesc" class="pp-modal__input" maxlength="100" placeholder="简单介绍一下玩法" />
              </label>
              <div class="pp-modal__field">
                <span class="pp-modal__label">游戏文件（.html）</span>
                <label class="pp-modal__file">
                  <input type="file" accept=".html,.htm,text/html" class="pp-modal__file-input" @change="onPickFile" />
                  <span class="pp-modal__file-btn">选择文件</span>
                  <span class="pp-modal__file-name">{{ submitFile ? submitFile.name : '未选择文件' }}</span>
                </label>
                <p class="pp-modal__tip">上传一个完整的 HTML 小游戏，审核通过后即可上架赚金币</p>
              </div>
            </div>
            <div class="pp-modal__foot">
              <button type="button" class="pp-modal__cancel" @click="showSubmit = false">取消</button>
              <button type="button" class="pp-modal__ok" :disabled="submitting" @click="doSubmit">
                {{ submitting ? '提交中…' : '提交审核' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.pet-play {
  position: relative;
  min-height: 100vh;
  overflow-x: hidden;
  background: var(--bg-200);
  color: var(--text-800);
  padding-bottom: 28px;
  font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

/* ===== 背景装饰（柔和浅色，贴合浅灰底） ===== */
.pp-bg {
  position: fixed;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
  z-index: 0;
}
.pp-bg__blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(70px);
  opacity: 0.55;
}
.pp-bg__blob--1 { width: 300px; height: 300px; background: var(--brand-100); top: -80px; left: -60px; animation: pp-blob 14s ease-in-out infinite; }
.pp-bg__blob--2 { width: 260px; height: 260px; background: #ffe0ef; bottom: -60px; right: -40px; animation: pp-blob 18s ease-in-out infinite reverse; }
.pp-bg__blob--3 { width: 200px; height: 200px; background: #d6f7e3; top: 38%; left: 55%; opacity: 0.4; animation: pp-blob 22s ease-in-out infinite; }
@keyframes pp-blob {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(28px, -22px) scale(1.12); }
}
.pp-bg__star {
  position: absolute;
  font-size: 16px;
  color: var(--brand-200);
  animation: pp-twinkle 2.6s ease-in-out infinite;
}
@keyframes pp-twinkle {
  0%, 100% { opacity: 0.25; transform: scale(0.85); }
  50% { opacity: 0.9; transform: scale(1.15); }
}

/* ===== 顶部栏（毛玻璃 + 深色文字） ===== */
.pp-header {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px 10px;
  background: color-mix(in srgb, var(--bg-50) 82%, transparent);
  -webkit-backdrop-filter: blur(16px);
  backdrop-filter: blur(16px);
  border-bottom: 0.5px solid var(--bg-300);
}
.pp-header__back {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  background: var(--bg-100);
  color: var(--text-800);
  cursor: pointer;
  transition: transform 120ms ease, background 120ms ease;
}
.pp-header__back:active { transform: scale(0.9); background: var(--bg-300); }
.pp-header__back-icon { font-size: 17px; font-weight: 700; line-height: 1; }
.pp-header__title {
  display: flex;
  align-items: center;
  gap: 8px;
}
.pp-header__title-emoji { font-size: 20px; }
.pp-header__title h1 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--text-900);
  background: none;
  -webkit-background-clip: initial;
  background-clip: initial;
}
.pp-header__pet {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border-radius: 999px;
  background: var(--bg-100);
  font-size: 12px;
  font-weight: 600;
}
.pp-header__pet-lv {
  color: var(--brand-500);
}
.pp-header__pet-aff { color: var(--warning); }
.pp-header__pet-heart { color: var(--error); font-size: 11px; }

/* ===== 宠物舞台（白卡片 + 浅阴影） ===== */
.pp-stage {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  height: 190px;
  margin: 4px 16px 0;
  padding: 0 16px 8px;
  border-radius: var(--radius);
  background: var(--bg-50);
  box-shadow: var(--shadow-sm);
}
.pp-stage__pet {
  filter: drop-shadow(0 8px 18px rgba(0, 0, 0, 0.12));
  animation: pp-idle 2.8s ease-in-out infinite;
}
.pp-stage__pet.is-dancing { animation: pp-dance 0.55s ease-in-out infinite; }
@keyframes pp-idle {
  0%, 100% { transform: translateY(0) rotate(0deg); }
  50% { transform: translateY(-5px) rotate(1.5deg); }
}
@keyframes pp-dance {
  0%, 100% { transform: translateY(0) rotate(-3deg); }
  50% { transform: translateY(-8px) rotate(3deg); }
}
.pp-stage__bubble {
  position: relative;
  margin-top: 10px;
  max-width: 84%;
  padding: 9px 16px;
  border-radius: 16px;
  background: var(--bg-50);
  color: var(--text-800);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
  box-shadow: var(--shadow-md);
  animation: pp-bubble-pop 240ms cubic-bezier(0.32, 1.3, 0.4, 1) both;
}
.pp-stage__bubble.is-feedback {
  background: linear-gradient(135deg, #fff7e0, #ffe9b8);
  color: #7a4d12;
}
.pp-stage__bubble::after {
  content: '';
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 7px solid transparent;
  border-bottom-color: var(--bg-50);
}
.pp-stage__bubble.is-feedback::after { border-bottom-color: #fff1c9; }
@keyframes pp-bubble-pop {
  from { opacity: 0; transform: translateY(6px) scale(0.85); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
.pp-stage__loading {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 30px 0;
}
.pp-stage__loading-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--brand-300);
  animation: pp-load 1s ease-in-out infinite;
}
.pp-stage__loading-dot:nth-child(2) { animation-delay: 0.15s; }
.pp-stage__loading-dot:nth-child(3) { animation-delay: 0.3s; }
@keyframes pp-load {
  0%, 100% { transform: translateY(0); opacity: 0.5; }
  50% { transform: translateY(-8px); opacity: 1; }
}
.pp-stage__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 26px 20px;
  text-align: center;
}
.pp-stage__empty-icon { font-size: 42px; animation: pp-idle 2s ease-in-out infinite; }
.pp-stage__empty-text { margin: 0; font-size: 13px; color: var(--text-400); }
.pp-stage__empty-btn {
  padding: 8px 20px;
  border: none;
  border-radius: 999px;
  background: var(--brand-500);
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(0, 122, 255, 0.28);
  transition: transform 120ms ease;
}
.pp-stage__empty-btn:active { transform: scale(0.94); }

/* ===== 游戏大厅 ===== */
.pp-lobby {
  position: relative;
  z-index: 2;
  padding: 14px 16px 0;
}

/* ---- 分类 TAB（浅色胶囊，选中蓝字浅蓝底） ---- */
.pp-tabs {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}
.pp-tabs__nav {
  display: flex;
  gap: 4px;
  padding: 4px;
  border-radius: 999px;
  background: var(--bg-100);
}
.pp-tabs__btn {
  padding: 7px 18px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--text-400);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: color 150ms cubic-bezier(0.32, 0.72, 0, 1), background 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.pp-tabs__btn.active {
  background: var(--brand-50);
  color: var(--brand-600);
  font-weight: 700;
}
.pp-tabs__create {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 8px 14px;
  border: none;
  border-radius: 999px;
  background: var(--brand-500);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(0, 122, 255, 0.26);
  transition: transform 120ms ease, background 120ms ease;
}
.pp-tabs__create:active { transform: scale(0.95); background: var(--brand-600); }
.pp-tabs__create-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.24);
  font-size: 12px;
  font-weight: 800;
}

/* ---- 多人占位 ---- */
.pp-multi {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 56px 24px;
  text-align: center;
  border-radius: var(--radius);
  background: var(--bg-50);
  box-shadow: var(--shadow-xs);
}
.pp-multi__icon {
  font-size: 52px;
  animation: pp-idle 2.6s ease-in-out infinite;
  filter: drop-shadow(0 8px 18px rgba(0, 0, 0, 0.12));
}
.pp-multi__title {
  margin: 8px 0 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-800);
}
.pp-multi__desc {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-400);
}

.pp-lobby__loading,
.pp-lobby__empty {
  padding: 40px 20px;
  text-align: center;
  font-size: 13px;
  color: var(--text-400);
}
.pp-lobby__grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
.game-card {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
  padding: 14px;
  border: none;
  border-radius: var(--radius);
  background: var(--bg-50);
  box-shadow: var(--shadow-xs);
  color: var(--text-800);
  text-align: left;
  cursor: pointer;
  overflow: hidden;
  transition: transform 160ms cubic-bezier(0.32, 0.9, 0.4, 1), box-shadow 160ms ease;
}
.game-card:hover { box-shadow: var(--shadow-md); }
.game-card:active { transform: scale(0.97); }
.game-card__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  border-radius: 16px;
  font-size: 28px;
  background: var(--bg-100);
  box-shadow: var(--shadow-xs);
}
.game-card__info {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-height: 40px;
}
.game-card__name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-800);
}
.game-card__desc {
  font-size: 12px;
  line-height: 1.4;
  color: var(--text-400);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.game-card__play {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.game-card__reward {
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--brand-50);
  color: var(--brand-600);
  font-size: 12px;
  font-weight: 700;
}
.game-card__best {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-400);
  margin-left: auto;
  margin-right: 8px;
}
.game-card__go {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--bg-100);
  color: var(--text-500);
  font-size: 12px;
}

/* ===== 游戏区域 ===== */
.pp-game {
  position: relative;
  z-index: 2;
  padding: 8px 14px 0;
}
.pp-game__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.pp-game__hud {
  display: flex;
  gap: 8px;
}
.pp-game__hud-item {
  padding: 5px 12px;
  border-radius: 999px;
  background: var(--bg-50);
  color: var(--text-500);
  font-size: 12px;
  font-weight: 600;
  box-shadow: var(--shadow-2xs);
}
.pp-game__hud-item--score { color: var(--brand-600); }
.pp-game__hud-item--lives { color: var(--error); }
.pp-game__quit {
  padding: 6px 14px;
  border: none;
  border-radius: 999px;
  background: var(--bg-50);
  color: var(--text-600);
  font-size: 12px;
  font-weight: 600;
  box-shadow: var(--shadow-2xs);
  cursor: pointer;
  transition: transform 120ms ease;
}
.pp-game__quit:active { transform: scale(0.94); }

/* ===== HTML 小游戏 ===== */
.pp-html {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.pp-html__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.pp-html__name {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-800);
}
.pp-html__quit {
  padding: 6px 14px;
  border: none;
  border-radius: 999px;
  background: var(--bg-50);
  color: var(--text-600);
  font-size: 12px;
  font-weight: 600;
  box-shadow: var(--shadow-2xs);
  cursor: pointer;
}
.pp-html__frame {
  height: min(720px, calc(100dvh - 168px));
  border-radius: var(--radius);
  overflow: hidden;
  border: 0.5px solid var(--bg-300);
  background: #fff;
  box-shadow: var(--shadow-sm);
}
.pp-html__iframe {
  width: 100%;
  height: 100%;
  border: none;
  display: block;
}
.pp-html__loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-400);
  font-size: 13px;
}
.pp-html__footer {
  display: flex;
  align-items: center;
  gap: 12px;
}
.pp-html__claim {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 11px 22px;
  border: none;
  border-radius: 999px;
  background: var(--brand-500);
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 6px 16px rgba(0, 122, 255, 0.28);
  transition: transform 120ms ease, opacity 120ms ease;
}
.pp-html__claim:disabled { opacity: 0.6; cursor: default; }
.pp-html__claim:not(:disabled):active { transform: scale(0.95); }
.pp-html__claim-icon { font-size: 16px; }
.pp-html__claim-sub {
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.24);
  font-size: 11px;
  font-weight: 700;
}
.pp-html__left {
  font-size: 12px;
  color: var(--text-400);
}

/* 通用结束遮罩 */
.catch-game__overlay,
.bubble-game__overlay,
.memory-game__overlay,
.rps-game__overlay,
.mole-game__overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.35);
  -webkit-backdrop-filter: blur(4px);
  backdrop-filter: blur(4px);
  z-index: 5;
}
.catch-game__overlay-card,
.bubble-game__overlay-card,
.memory-game__overlay-card,
.rps-game__overlay-card,
.mole-game__overlay-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 22px 26px;
  border-radius: var(--radius);
  background: var(--bg-50);
  color: var(--text-800);
  box-shadow: var(--shadow-xl);
  animation: pp-bubble-pop 300ms cubic-bezier(0.32, 1.3, 0.4, 1) both;
}
.catch-game__overlay-title,
.bubble-game__overlay-title,
.memory-game__overlay-title,
.rps-game__overlay-title,
.mole-game__overlay-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
}
.memory-game__overlay-sub {
  margin: -4px 0 0;
  font-size: 12px;
  color: var(--text-400);
}
.catch-game__overlay-actions,
.bubble-game__overlay-actions,
.memory-game__overlay-actions,
.rps-game__overlay-actions,
.mole-game__overlay-actions {
  display: flex;
  gap: 10px;
}
.catch-game__overlay-actions button,
.bubble-game__overlay-actions button,
.memory-game__overlay-actions button,
.rps-game__overlay-actions button,
.mole-game__overlay-actions button {
  padding: 9px 18px;
  border: none;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.catch-game__overlay-actions button:first-child,
.bubble-game__overlay-actions button:first-child,
.memory-game__overlay-actions button:first-child,
.rps-game__overlay-actions button:first-child,
.mole-game__overlay-actions button:first-child {
  background: var(--brand-500);
  color: #fff;
}
.catch-game__overlay-actions button:last-child,
.bubble-game__overlay-actions button:last-child,
.memory-game__overlay-actions button:last-child,
.rps-game__overlay-actions button:last-child,
.mole-game__overlay-actions button:last-child {
  background: var(--bg-100);
  color: var(--text-600);
}

/* ===== 接零食 ===== */
.catch-game {
  position: relative;
  height: 400px;
  border-radius: var(--radius);
  overflow: hidden;
  background:
    radial-gradient(circle at 20% 20%, rgba(0, 122, 255, 0.10), transparent 45%),
    radial-gradient(circle at 80% 15%, rgba(255, 95, 158, 0.10), transparent 42%),
    linear-gradient(180deg, #ffffff, #f0f4ff);
  border: 0.5px solid var(--bg-300);
  touch-action: none;
}
.catch-game__items { position: absolute; inset: 0; }
.catch-game__item {
  position: absolute;
  line-height: 1;
  filter: drop-shadow(0 3px 6px rgba(0, 0, 0, 0.2));
  animation: pp-fall-tilt 0.8s ease-in-out infinite alternate;
}
@keyframes pp-fall-tilt {
  from { transform: rotate(-8deg); }
  to { transform: rotate(8deg); }
}
.catch-game__booms { position: absolute; inset: 0; pointer-events: none; }
.catch-game__boom {
  position: absolute;
  top: 72%;
  transform: translateX(-50%);
  font-size: 24px;
  animation: pp-boom 480ms ease-out forwards;
}
@keyframes pp-boom {
  0% { opacity: 1; transform: translateX(-50%) translateY(0) scale(0.6); }
  100% { opacity: 0; transform: translateX(-50%) translateY(-34px) scale(1.3); }
}
.catch-game__bowl {
  position: absolute;
  bottom: 16px;
  transform: translateX(-50%);
  width: 64px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 42px;
  filter: drop-shadow(0 5px 12px rgba(0, 0, 0, 0.25));
  transition: left 60ms linear;
}
.catch-game__bowl-emoji { animation: pp-bowl 0.5s ease-in-out infinite alternate; }
@keyframes pp-bowl {
  from { transform: rotate(-4deg); }
  to { transform: rotate(4deg); }
}

/* ===== 戳泡泡 ===== */
.bubble-game {
  position: relative;
  height: 400px;
  border-radius: var(--radius);
  overflow: hidden;
  background:
    radial-gradient(circle at 70% 25%, rgba(124, 91, 255, 0.12), transparent 45%),
    linear-gradient(180deg, #ffffff, #f4f2ff);
  border: 0.5px solid var(--bg-300);
  touch-action: none;
}
.bubble-game__field { position: absolute; inset: 0; cursor: pointer; touch-action: manipulation; }
.bubble-game__inner { position: absolute; inset: 0; }
.bubble-game__bubble {
  position: absolute;
  border: 1px solid rgba(255, 255, 255, 0.6);
  border-radius: 50%;
  cursor: pointer;
  pointer-events: none;
  animation: pp-bubble-rise linear forwards;
  box-shadow: inset -6px -6px 14px rgba(255, 255, 255, 0.6), 0 6px 18px rgba(0, 0, 0, 0.12);
}
@keyframes pp-bubble-rise {
  0% { transform: translateY(0); opacity: 0; }
  8% { opacity: 1; }
  100% { transform: translateY(-720px); opacity: 0.9; }
}
.bubble-game__pops { position: absolute; inset: 0; pointer-events: none; }
.bubble-game__pop {
  position: absolute;
  transform: translate(-50%, -50%);
  font-size: 26px;
  animation: pp-boom 520ms ease-out forwards;
  filter: drop-shadow(0 3px 8px rgba(0, 0, 0, 0.3));
}

/* ===== 记忆翻牌 ===== */
.memory-game {
  position: relative;
  border-radius: var(--radius);
  padding: 14px;
  background: var(--bg-50);
  box-shadow: var(--shadow-sm);
  border: 0.5px solid var(--bg-300);
  min-height: 400px;
}
.memory-game__hud {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
}
.memory-game__hud-item {
  padding: 5px 12px;
  border-radius: 999px;
  background: var(--bg-100);
  color: var(--text-600);
  font-size: 12px;
  font-weight: 600;
}
.memory-game__grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.memory-card {
  position: relative;
  aspect-ratio: 1;
  border: none;
  border-radius: 14px;
  cursor: pointer;
  perspective: 600px;
  background: transparent;
  padding: 0;
}
.memory-card__face {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 14px;
  font-size: 26px;
  backface-visibility: hidden;
  transition: transform 420ms cubic-bezier(0.32, 0.9, 0.4, 1);
}
.memory-card__face--back {
  background: var(--brand-500);
  color: rgba(255, 255, 255, 0.9);
  font-size: 20px;
  font-weight: 800;
  box-shadow: 0 4px 12px rgba(0, 122, 255, 0.2);
}
.memory-card__face--front {
  background: var(--bg-100);
  transform: rotateY(180deg);
}
.memory-card.is-open .memory-card__face--back,
.memory-card.is-matched .memory-card__face--back { transform: rotateY(180deg); }
.memory-card.is-open .memory-card__face--front,
.memory-card.is-matched .memory-card__face--front { transform: rotateY(0); }
.memory-card.is-matched .memory-card__face--front {
  background: linear-gradient(135deg, #d8ffe8, #b9f6d0);
  animation: pp-match 500ms ease;
}
@keyframes pp-match {
  0% { transform: rotateY(0) scale(1); }
  50% { transform: rotateY(0) scale(1.15); }
  100% { transform: rotateY(0) scale(1); }
}

/* ===== 猜拳 ===== */
.rps-game {
  position: relative;
  border-radius: 24px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.08);
  -webkit-backdrop-filter: blur(14px);
  backdrop-filter: blur(14px);
  border: 1px solid rgba(255, 255, 255, 0.12);
  min-height: 400px;
}
.rps-game__score {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 20px;
  margin-bottom: 14px;
}
.rps-game__score-side {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  min-width: 70px;
}
.rps-game__score-name { font-size: 11px; color: #bcd0ff; }
.rps-game__score-num { font-size: 30px; font-weight: 800; }
.rps-game__score-vs { font-size: 14px; font-weight: 800; color: #ffd08a; }
.rps-game__hands {
  display: flex;
  justify-content: center;
  gap: 60px;
  padding: 20px 0 10px;
}
.rps-game__hand {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.rps-game__hand-emoji {
  font-size: 64px;
  filter: drop-shadow(0 8px 18px rgba(0, 0, 0, 0.4));
  animation: pp-idle 2s ease-in-out infinite;
}
.rps-game__hand-emoji.is-flip { animation: pp-rps-flip 380ms cubic-bezier(0.32, 1.3, 0.4, 1) both; }
@keyframes pp-rps-flip {
  0% { transform: scale(0.4) rotate(-20deg); }
  100% { transform: scale(1) rotate(0); }
}
.rps-game__hand-label { font-size: 12px; color: #bcd0ff; }
.rps-game__result {
  text-align: center;
  font-size: 15px;
  font-weight: 800;
  color: #ffd08a;
  margin: 4px 0 10px;
}
.rps-game__pick {
  display: flex;
  justify-content: center;
  gap: 16px;
}
.rps-game__pick-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: 78px;
  padding: 12px 0 10px;
  border: 2px solid rgba(255, 255, 255, 0.14);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
  cursor: pointer;
  transition: transform 120ms ease, background 120ms ease, border-color 120ms ease;
}
.rps-game__pick-btn:disabled { opacity: 0.45; cursor: default; }
.rps-game__pick-btn.is-picked {
  border-color: #ffd08a;
  background: rgba(255, 208, 138, 0.16);
  transform: translateY(-4px);
}
.rps-game__pick-emoji { font-size: 32px; }
.rps-game__pick-label { font-size: 11px; color: #dce6ff; }

/* ===== 幸运轮 ===== */
.wheel-game {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 22px;
  border-radius: 24px;
  padding: 26px 16px;
  background: rgba(255, 255, 255, 0.08);
  -webkit-backdrop-filter: blur(14px);
  backdrop-filter: blur(14px);
  border: 1px solid rgba(255, 255, 255, 0.12);
}
.wheel-game__wrap { position: relative; width: 300px; height: 300px; }
.wheel-game__wheel {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  overflow: hidden;
  box-shadow: 0 12px 34px rgba(0, 0, 0, 0.45);
  transition: transform 4.2s cubic-bezier(0.16, 0.85, 0.28, 1);
  border: 8px solid rgba(255, 255, 255, 0.2);
}
.wheel-game__seg {
  position: absolute;
  inset: 0;
  clip-path: polygon(50% 50%, 50% 0, 100% 0);
  transform-origin: 50% 50%;
}
.wheel-game__seg-label {
  position: absolute;
  top: 26px;
  left: 50%;
  transform-origin: 50% 0;
  font-size: 11px;
  font-weight: 800;
  color: #fff;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.35);
  white-space: nowrap;
}
.wheel-game__hub {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.95);
  font-size: 26px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  z-index: 2;
}
.wheel-game__pointer {
  position: absolute;
  top: -12px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 26px;
  color: #ffd08a;
  z-index: 3;
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.4));
}
.wheel-game__spin {
  padding: 12px 34px;
  border: none;
  border-radius: 18px;
  background: linear-gradient(135deg, #ff9a56, #ff5f6d);
  color: #fff;
  font-size: 16px;
  font-weight: 800;
  cursor: pointer;
  box-shadow: 0 8px 22px rgba(255, 95, 109, 0.4);
  transition: transform 120ms ease;
}
.wheel-game__spin:disabled { opacity: 0.6; cursor: default; }
.wheel-game__spin:not(:disabled):active { transform: scale(0.94); }
.wheel-game__result {
  margin: 0;
  font-size: 16px;
  font-weight: 800;
  color: #ffd08a;
}

/* ===== 打地鼠 ===== */
.mole-game {
  position: relative;
  border-radius: 24px;
  padding: 20px 14px;
  background:
    radial-gradient(circle at 50% 100%, rgba(67, 233, 123, 0.16), transparent 60%),
    rgba(16, 26, 61, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.12);
  min-height: 400px;
}
.mole-game__field {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 18px 14px;
}
.mole-game__hole {
  position: relative;
  aspect-ratio: 1.15;
  border: none;
  border-radius: 50% 50% 40% 40%;
  background: radial-gradient(circle at 50% 120%, rgba(0, 0, 0, 0.55), transparent 62%);
  cursor: pointer;
  overflow: visible;
}
.mole-game__hole::before {
  content: '';
  position: absolute;
  left: 8%;
  right: 8%;
  bottom: 4%;
  height: 34%;
  border-radius: 50%;
  background: radial-gradient(circle at 50% 30%, #3a2a1e, #24170f);
  box-shadow: inset 0 6px 10px rgba(0, 0, 0, 0.6);
}
.mole-game__dirt {
  position: absolute;
  bottom: 8%;
  left: 50%;
  transform: translateX(-50%);
  font-size: 22px;
  opacity: 0.85;
}
.mole-game__mole {
  position: absolute;
  bottom: 20%;
  left: 50%;
  transform: translateX(-50%);
  font-size: 40px;
  filter: drop-shadow(0 4px 8px rgba(0, 0, 0, 0.4));
  z-index: 2;
  animation: pp-mole-wiggle 0.9s ease-in-out infinite;
}
@keyframes pp-mole-wiggle {
  0%, 100% { transform: translateX(-50%) rotate(-4deg); }
  50% { transform: translateX(-50%) rotate(4deg); }
}

/* ===== 转场动画 ===== */
.pp-say-enter-active,
.pp-say-leave-active { transition: all 220ms ease; }
.pp-say-enter-from,
.pp-say-leave-to { opacity: 0; transform: translateY(8px); }
.pp-fall-enter-active,
.pp-fall-leave-active { transition: opacity 200ms ease; }
.pp-fall-enter-from { opacity: 0; }
.pp-fall-leave-to { opacity: 0; }
.pp-boom-enter-active,
.pp-boom-leave-active { transition: all 200ms ease; }
.pp-bubble-enter-active { transition: all 200ms ease; }
.pp-bubble-enter-from { opacity: 0; transform: scale(0.3); }
.pp-mole-enter-active,
.pp-mole-leave-active { transition: all 160ms cubic-bezier(0.32, 1.4, 0.4, 1); }
.pp-mole-enter-from { opacity: 0; transform: translateX(-50%) translateY(22px) scale(0.5); }
.pp-mole-leave-to { opacity: 0; transform: translateX(-50%) translateY(22px) scale(0.5); }

/* ===== 制作游戏弹窗 ===== */
.pp-modal-enter-active,
.pp-modal-leave-active { transition: opacity 220ms ease; }
.pp-modal-enter-from,
.pp-modal-leave-to { opacity: 0; }
.pp-modal {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(8, 13, 32, 0.65);
  -webkit-backdrop-filter: blur(6px);
  backdrop-filter: blur(6px);
}
.pp-modal__card {
  width: 100%;
  max-width: 400px;
  max-height: 88vh;
  overflow-y: auto;
  border-radius: 24px;
  background: #1b2547;
  border: 1px solid rgba(255, 255, 255, 0.12);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  animation: pp-bubble-pop 260ms cubic-bezier(0.32, 1.3, 0.4, 1) both;
}
.pp-modal__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px 12px;
}
.pp-modal__title {
  margin: 0;
  font-size: 17px;
  font-weight: 800;
  color: #fff;
}
.pp-modal__close {
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.8);
  font-size: 14px;
  cursor: pointer;
}
.pp-modal__body {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 4px 20px 18px;
}
.pp-modal__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.pp-modal__label {
  font-size: 12px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.7);
}
.pp-modal__input {
  padding: 10px 12px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.07);
  color: #fff;
  font-size: 14px;
  outline: none;
  transition: border-color 120ms ease;
}
.pp-modal__input:focus { border-color: #5b8cff; }
.pp-modal__types {
  display: flex;
  gap: 8px;
}
.pp-modal__type {
  flex: 1;
  padding: 9px 0;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.65);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: all 120ms ease;
}
.pp-modal__type.active {
  border-color: #5b8cff;
  background: rgba(91, 140, 255, 0.2);
  color: #fff;
}
.pp-modal__file {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}
.pp-modal__file-input {
  display: none;
}
.pp-modal__file-btn {
  padding: 8px 16px;
  border-radius: 12px;
  background: linear-gradient(135deg, #5b8cff, #7c5bff);
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}
.pp-modal__file-name {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pp-modal__tip {
  margin: 0;
  font-size: 11px;
  line-height: 1.5;
  color: rgba(255, 255, 255, 0.45);
}
.pp-modal__foot {
  display: flex;
  gap: 10px;
  padding: 0 20px 20px;
}
.pp-modal__cancel {
  flex: 1;
  padding: 11px 0;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.75);
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
}
.pp-modal__ok {
  flex: 1;
  padding: 11px 0;
  border: none;
  border-radius: 14px;
  background: linear-gradient(135deg, #5b8cff, #7c5bff);
  color: #fff;
  font-size: 14px;
  font-weight: 800;
  cursor: pointer;
  box-shadow: 0 6px 18px rgba(91, 140, 255, 0.35);
}
.pp-modal__ok:disabled { opacity: 0.6; cursor: default; }
</style>
