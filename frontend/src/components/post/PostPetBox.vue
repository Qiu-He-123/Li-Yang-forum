<script setup lang="ts">
/**
 * 帖子卡片 / 详情页上的「可互动宠物」
 * - 展示发帖人已领养的宠物：悬浮在卡片内，可拖动、可移动，时不时随机做一个有趣的小动作
 * - 不挡文字：默认出现在卡片右下角留白处；体积小、可被拖走，且默认 pointer-events 仅在宠物上生效
 * - 轻量自绘：先只预载「待机」帧，随机动作按需临时加载该动作帧
 * - IntersectionObserver 懒加载：滚入视口才拉取宠物数据并开始播放
 * - 同一作者缓存，避免重复请求
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { listUserPets, type UserPetLight, type PetAnimAction } from '../../api/petShop'

const props = withDefaults(
  defineProps<{
    userId: number
    /** 宠物尺寸 px */
    size?: number
    /** float: 绝对定位浮在父容器内、可拖动可移动；inline: 内联方格，仅播放动作不拖动 */
    mode?: 'float' | 'inline'
    /** 是否为发帖人自己（自己帖子/组局：不展示宠物，也不显示姓名帖） */
    self?: boolean
    /** 发帖人昵称（用于生成「xxx 的 [宠物名]」姓名帖） */
    authorName?: string
  }>(),
  { size: 46, mode: 'float', self: false, authorName: '' },
)

// 作者宠物缓存：userId -> pet
const userPetCache = new Map<number, UserPetLight | null>()
const shownNameCache = new Map<number, string>()

// canvas 逻辑展示尺寸：绘制像素为 size*0.8，物理像素再乘 dpr。
// 必须显式限定 CSS 尺寸，否则 canvas 会按「物理像素尺寸」显示：
// 高 DPR 手机（2x/3x，dpr 封顶 2）上会放大到 120*0.8*2=192px，导致宠物占比过大。
const canvasCssSize = computed(() => Math.round(props.size * 0.8))

const pet = ref<UserPetLight | null>(null)
const shownName = ref('')
const boxRef = ref<HTMLDivElement | null>(null)
const canvasRef = ref<HTMLCanvasElement | null>(null)
// 随机动作 / 飞行动作标记
const isEnter = ref(false)
const isWandering = ref(false)
const isFlying = ref(false)
let enterTimer: number | null = null
let wanderTimer: number | null = null
let flyTimer: number | null = null

// ====== 帧播放器（多动作） ======
let actions: PetAnimAction[] = []
let frames: string[] = []
let frameIdx = 0
let fps = 12
let animTimer: number | null = null
let rafId = 0
let actionTimer: number | null = null
const imgCache = new Map<string, HTMLImageElement>()
const readyUrls = new Set<string>()

function currentInterval(): number {
  return Math.max(60, Math.round(1000 / fps))
}

function setAction(act: PetAnimAction | null) {
  stopAnim()
  if (!act) return
  frames = act.frames ?? []
  fps = Math.min(14, Math.max(4, Math.round(1000 / (act.interval || 100))))
  frameIdx = 0
  startAnim()
}

function pickStand(): PetAnimAction | null {
  return actions.find((a) => a.key === 'stand') ?? actions[0] ?? null
}

function preloadFrames(act: PetAnimAction | null | undefined, onReady?: () => void) {
  for (const url of act?.frames ?? []) {
    if (imgCache.has(url)) continue
    const img = new Image()
    img.src = url
    imgCache.set(url, img)
    img
      .decode()
      .then(() => {
        readyUrls.add(url)
        draw()
        onReady?.()
      })
      .catch(() => {
        if (img.complete && img.naturalWidth > 0) {
          readyUrls.add(url)
          onReady?.()
        }
      })
  }
}

function draw() {
  const canvas = canvasRef.value
  if (!canvas || !frames.length) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  const px = Math.round(props.size * 0.8)
  if (canvas.width !== px * dpr) {
    canvas.width = px * dpr
    canvas.height = px * dpr
  }
  const url = frames[frameIdx % frames.length]
  const img = imgCache.get(url)
  if (!img || !readyUrls.has(url)) return
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.imageSmoothingEnabled = false
  const scale = Math.min(canvas.width / img.naturalWidth, canvas.height / img.naturalHeight)
  const w = Math.round(img.naturalWidth * scale)
  const h = Math.round(img.naturalHeight * scale)
  ctx.drawImage(img, Math.round((canvas.width - w) / 2), Math.round((canvas.height - h) / 2), w, h)
}

function startAnim() {
  stopAnim()
  if (!frames.length) return
  animTimer = window.setInterval(() => {
    frameIdx += 1
    draw()
  }, currentInterval())
  rafId = requestAnimationFrame(draw)
}

function stopAnim() {
  if (animTimer !== null) {
    window.clearInterval(animTimer)
    animTimer = null
  }
  if (rafId) cancelAnimationFrame(rafId)
}

// ====== 随机小动作 ======
/** 可随机表演的动作键（排除待机与长时动作） */
const FUN_ACTIONS = ['wave', 'interact', 'happy', 'dance', 'play', 'sleep', 'eat', 'attack']

function scheduleRandomAction() {
  if (actionTimer !== null) window.clearTimeout(actionTimer)
  if (!actions.length || !pet.value) return
  const delay = 2600 + Math.random() * 3800
  actionTimer = window.setTimeout(() => {
    const candidates = actions.filter((a) => FUN_ACTIONS.includes(a.key))
    const pool = candidates.length ? candidates : actions
    const act = pool[Math.floor(Math.random() * pool.length)] ?? pickStand()
    if (!act) { scheduleRandomAction(); return }
    // 表演一次后回到待机（待机帧已预热，异步加载，不依赖回调时序）
    const playMs = Math.max((act.frames?.length ?? 1) * (act.interval || 100), 700)
    setAction(act)
    preloadFrames(pickStand())
    actionTimer = window.setTimeout(() => {
      const stand = pickStand()
      if (stand) setAction(stand)
      scheduleRandomAction()
    }, playMs)
  }, delay)
}

// ====== 拖拽 ======
const dragPos = ref({ x: 0, y: 0 })
const dragActive = ref(false)
const isDragging = ref(false) // 是否发生过拖拽（用于抑制 click 冒泡）
let dragStart = { px: 0, py: 0, ox: 0, oy: 0 }
let dragMoved = false
let containerRect: DOMRect | null = null
/** 底部预留的操作行（作者+点赞行）高度：宠物被限制在这一行之上，永不盖住点赞，
 该处始终可点击、可滚动；越界拖拽会被 clamp 挡在点赞行上方 */
let bottomReserve = 0

function clampDrag(x: number, y: number) {
  if (!containerRect) return { x, y }
  const maxX = Math.max(0, containerRect.width - props.size - 4)
  const maxY = Math.max(0, containerRect.height - bottomReserve - props.size - 4)
  return { x: Math.min(maxX, Math.max(0, x)), y: Math.min(maxY, Math.max(0, y)) }
}

/** 可拖拽范围：相对最近的定位祖先（卡片本身）；
 * 若卡片内存在底部操作行(.card-meta，如点赞)，则将其底边到卡片底边的空间预留出来 */
function measureContainer(): DOMRect | null {
  const el = boxRef.value?.offsetParent as HTMLElement | null
  if (!el) return null
  containerRect = el.getBoundingClientRect()
  bottomReserve = 0
  const meta = el.querySelector?.('.card-meta')
  if (meta) {
    const m = meta.getBoundingClientRect()
    bottomReserve = Math.max(0, containerRect.bottom - m.bottom) + 6
  }
  return containerRect
}

/** 默认落位：卡片右下角留白处 */
function placeCorner() {
  const rect = measureContainer()
  if (!rect) {
    containerRect = null
    return
  }
  containerRect = rect
  const p = clampDrag(rect.width - props.size - 8, rect.height - props.size - 10)
  dragPos.value = p
}

function onPointerDown(e: PointerEvent) {
  if (props.mode !== 'float') return
  if (!pet.value) return
  isDragging.value = true
  dragMoved = false
  dragActive.value = true
  containerRect = measureContainer()
  dragStart = { px: e.clientX, py: e.clientY, ox: dragPos.value.x, oy: dragPos.value.y }
  ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
}

function onPointerMove(e: PointerEvent) {
  if (props.mode !== 'float') return
  if (!dragActive.value) return
  const dx = e.clientX - dragStart.px
  const dy = e.clientY - dragStart.py
  if (!dragMoved && Math.hypot(dx, dy) < 4) return
  dragMoved = true
  dragPos.value = clampDrag(dragStart.ox + dx, dragStart.oy + dy)
}

function onPointerUp() {
  dragActive.value = false
  // 结束后自动回到固定的小动作循环
}

// ====== 懒加载 ======
let io: IntersectionObserver | null = null
let loaded = false

function startBehavior() {
  // 自己帖子/组局：默认隐藏卡片内宠物，也不显示姓名帖
  if (props.self) return
  if (actions.length) setAction(pickStand())
  scheduleRandomAction()
  if (props.mode === 'float') placeCorner()
  // 入场动画：进入视口/加载后从角落滑入
  isEnter.value = false
  if (enterTimer !== null) window.clearTimeout(enterTimer)
  enterTimer = window.setTimeout(() => {
    isEnter.value = true
    if (props.mode === 'float') scheduleWander()
    scheduleFlight()
  }, 80)
}

/** 随机小飞行/跳跃（可飞行宠物）：偶尔在原地做上浮回落 */
function scheduleFlight() {
  if (flyTimer !== null) window.clearTimeout(flyTimer)
  if (!pet.value) return
  const canFly = !!pet.value.can_fly
  if (!canFly || props.mode !== 'float') return
  flyTimer = window.setTimeout(() => {
    isFlying.value = true
    if (hasAnimAction('fly')) setAction(findAction('fly'))
    window.setTimeout(() => {
      isFlying.value = false
      scheduleFlight()
    }, 1100)
  }, 4000 + Math.random() * 5000)
}

function findAction(key: string): PetAnimAction | null {
  return actions.find((a) => a.key === key) ?? null
}
function hasAnimAction(key: string): boolean {
  return !!findAction(key)
}

/** 随机在卡片内小范围移动到不同位置（让宠物更"活"） */
function scheduleWander() {
  if (wanderTimer !== null) window.clearTimeout(wanderTimer)
  if (!pet.value || props.mode !== 'float') return
  wanderTimer = window.setTimeout(() => {
    if (isDragging.value) { scheduleWander(); return }
    const rect = containerRect
    if (!rect) return
    const pad = 4
    const maxX = Math.max(0, rect.width - props.size - pad)
    const maxY = Math.max(0, rect.height - props.size - pad)
    const nx = Math.min(maxX, Math.max(0, dragPos.value.x + (Math.random() - 0.5) * 90))
    const ny = Math.min(maxY, Math.max(0, dragPos.value.y + (Math.random() - 0.5) * 70))
    isWandering.value = true
    dragPos.value = { x: nx, y: ny }
    window.setTimeout(() => { isWandering.value = false }, 1000)
    scheduleWander()
  }, 3400 + Math.random() * 3200)
}

function activate() {
  if (loaded) return
  loaded = true
  // 自己帖子/组局：不做宠物数据加载与展示
  if (props.self) {
    startBehavior()
    return
  }
  if (userPetCache.has(props.userId)) {
    pet.value = userPetCache.get(props.userId) ?? null
    shownName.value = shownNameCache.get(props.userId) ?? ''
    if (pet.value?.anim) {
      actions = pet.value.anim.actions ?? []
      preloadFrames(pickStand()!)
    }
    startBehavior()
    return
  }
  void (async () => {
    try {
      const { data } = await listUserPets(props.userId, { showGlobalLoading: false, showGlobalError: false })
      const items = data.data.items ?? []
      let chosen: UserPetLight | null = items.find((p) => p.evolved && p.anim) ?? null
      if (!chosen) chosen = items.find((p) => p.anim) ?? null
      userPetCache.set(props.userId, chosen)
      const name = (chosen?.nickname || chosen?.name || '').slice(0, 6)
      shownNameCache.set(props.userId, name)
      pet.value = chosen
      shownName.value = name
      if (chosen?.anim) {
        actions = chosen.anim.actions ?? []
        preloadFrames(pickStand()!)
      }
      startBehavior()
    } catch {
      userPetCache.set(props.userId, null)
      pet.value = null
    }
  })()
}

/** 判断宠物容器当前是否已在可视区域内（用于 mount 时立即加载，避免进入页面首屏宠物不显示） */
function isInViewport(): boolean {
  const el = boxRef.value
  if (!el) return false
  const r = el.getBoundingClientRect()
  return r.top < window.innerHeight && r.bottom > 0 && r.left < window.innerWidth && r.right > 0
}

onMounted(() => {
  // 首屏即已出现在可视区：直接激活（不依赖 IntersectionObserver 的触发时机）
  if (isInViewport()) {
    activate()
    return
  }
  io = new IntersectionObserver(
    (entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        activate()
        io?.disconnect()
      }
    },
    { rootMargin: '120px' },
  )
  if (boxRef.value) io.observe(boxRef.value)
})

onBeforeUnmount(() => {
  io?.disconnect()
  stopAnim()
  if (actionTimer !== null) window.clearTimeout(actionTimer)
  if (enterTimer !== null) window.clearTimeout(enterTimer)
  if (wanderTimer !== null) window.clearTimeout(wanderTimer)
  if (flyTimer !== null) window.clearTimeout(flyTimer)
})
</script>

<template>
  <div
    ref="boxRef"
    class="post-pet-box"
    :class="[
      `is-${props.mode}`,
      {
        'is-visible': pet,
        'is-dragging': isDragging,
        'is-wandering': isWandering,
      },
    ]"
    :style="props.mode === 'float' ? { width: size + 'px', height: size + 'px', transform: `translate(${dragPos.x}px, ${dragPos.y}px)` } : { width: size + 'px', height: size + 'px' }"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerUp"
    @click.stop
  >
    <!-- 整块盒子即拖动把手（好抓）：touch-action:none 保证上下左右都能自由拖；
         通过 bottomReserve 把宠物限制在底部作者+点赞行上方，该处照常可点击/可滚动 -->
    <div
      v-if="pet && pet.anim"
      class="post-pet-box__inner"
      :class="{ 'is-enter': isEnter, 'is-flying': isFlying }"
    >
      <canvas ref="canvasRef" class="post-pet-box__canvas" :style="{ width: canvasCssSize + 'px', height: canvasCssSize + 'px' }" />
    </div>
    <!-- 姓名帖：xxx 的 [宠物名]（仅别人的宠物显示，自己帖子不显示） -->
    <transition name="post-pet-tag">
      <div
        v-if="pet && shownName && !props.self"
        class="post-pet-box__tag"
      >{{ (props.authorName ? props.authorName.slice(0, 6) : '神秘同学') }} 的 [{{ shownName }}]</div>
    </transition>
  </div>
</template>

<style scoped>
.post-pet-box {
  position: absolute;
  top: 0;
  left: 0;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.04);
  /* 默认不拦截任何指针（含未加载时的隐形盒子）；仅在宠物显示(is-visible)时才作为
     拖动把手参与交互：全向(touch-action:none)自由拖拽，目标大、易抓住；
     通过 bottomReserve 限制宠物不进入底部作者+点赞行，该处仍可点击/滚动 */
  pointer-events: none;
  touch-action: none;
  cursor: grab;
  user-select: none;
  z-index: 3;
  opacity: 0;
  transition: opacity 350ms ease;
  display: flex;
  align-items: center;
  justify-content: center;
}
/* inline 模式：非绝对定位的内联方格，仅播放动作，不影响父级布局、不可拖动 */
.post-pet-box.is-inline {
  position: static;
  display: inline-flex;
  opacity: 1;
  cursor: default;
  pointer-events: none;
  touch-action: auto;
  vertical-align: middle;
  flex-shrink: 0;
}
.post-pet-box.is-visible {
  opacity: 1;
  /* 宠物显示后整块盒子才可抓取拖动 */
  pointer-events: auto;
}
/* 随机移动：位置变化用平滑过渡 */
.post-pet-box.is-float.is-wandering {
  transition: transform 900ms ease;
}
.post-pet-box.is-float.is-dragging {
  cursor: grabbing;
  background: rgba(255, 255, 255, 0.16);
  border-radius: 14px;
}
.post-pet-box.is-inline .post-pet-box__inner {
  opacity: 1;
  /* inline 模式（帖子详情/组局静态宠物）：不参与拖动、不拦截页面滚动 */
  pointer-events: none;
  touch-action: auto;
  cursor: default;
}
.post-pet-box__inner {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-direction: column;
  animation: post-pet-bob 3.2s ease-in-out infinite;
  /* 只有宠物本体可被当作拖动把手：完整上下左右拖拽，且不把拖动抢成页面手势 */
  pointer-events: auto;
  touch-action: none;
  cursor: grab;
  user-select: none;
  -webkit-user-select: none;
  /* 默认静止到最终位置（进入时才用 is-enter 覆盖，做"飞入"） */
  opacity: 0;
}
.post-pet-box__inner:active { cursor: grabbing; }
.post-pet-box__canvas {
  pointer-events: auto;
  touch-action: none;
}
/* 飞入：从偏右下角滑动放大入场 */
.post-pet-box__inner.is-enter {
  opacity: 1;
  animation: post-pet-bob 3.2s ease-in-out infinite, post-pet-enter 560ms cubic-bezier(0.2, 0.9, 0.3, 1.2) both;
}
@keyframes post-pet-enter {
  0% {
    transform: translate(16px, 20px) scale(0.4);
    opacity: 0;
  }
  60% {
    transform: translate(-3px, -2px) scale(1.06);
    opacity: 1;
  }
  100% {
    transform: translate(0, 0) scale(1);
    opacity: 1;
  }
}
/* 可飞行宠物：在原地做"上抛悬空再落回"的小动作 */
.post-pet-box__inner.is-flying {
  animation: post-pet-bob 3.2s ease-in-out infinite, post-pet-fly 1.1s ease-in-out;
}
@keyframes post-pet-fly {
  0%   { transform: translateY(0); }
  30%  { transform: translateY(-14px); }
  55%  { transform: translateY(-4px); }
  75%  { transform: translateY(-10px); }
  100% { transform: translateY(0); }
}
.post-pet-box.is-dragging .post-pet-box__inner {
  animation: none;
}
@keyframes post-pet-bob {
  0%, 100% { transform: translateY(0) rotate(-1deg); }
  50% { transform: translateY(-3px) rotate(1deg); }
}
.post-pet-box__canvas {
  display: block;
  filter: drop-shadow(0 2px 6px rgba(23, 32, 64, 0.18));
}
/* 姓名帖：xxx 的 [宠物名] 小胶囊，浮在宠物上方 */
.post-pet-box__tag {
  position: absolute;
  top: -2px;
  left: 50%;
  transform: translateX(-50%);
  white-space: nowrap;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(23, 32, 64, 0.72);
  color: #fff;
  font-size: 10px;
  line-height: 1.4;
  font-weight: 600;
  letter-spacing: 0.2px;
  pointer-events: none;
  z-index: 4;
  backdrop-filter: blur(6px);
}
.post-pet-tag-enter-active,
.post-pet-tag-leave-active {
  transition: opacity 260ms ease, transform 260ms ease;
}
.post-pet-tag-enter-from,
.post-pet-tag-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(4px);
}
</style>