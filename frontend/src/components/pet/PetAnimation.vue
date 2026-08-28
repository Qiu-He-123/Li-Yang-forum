<script setup lang="ts">
/**
 * 像素宠物帧动画播放器（DyberPet 资源）
 * - Canvas 绘制：所有动作的帧一次性预载入内存，按帧率绘制到同一 canvas
 * - 不清屏策略：新帧未就绪时保留上一帧画面，杜绝首次加载/切动作闪白
 * - 动作栏/暂停钮为磨砂胶囊风（大厂交互风格），单动作宠物自动隐藏
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { PetAnim, PetAnimAction } from '../../api/petShop'

const props = withDefaults(
  defineProps<{
    anim: PetAnim | null
    /** 初始动作 key，缺省用第一个动作 */
    action?: string
    /** 展示尺寸（px），canvas 等比缩放居中 */
    size?: number
    /** 是否展示动作栏/暂停钮并可交互（详情页 true，漂浮宠物 false 由外部操控） */
    interactive?: boolean
    /** 是否展示动作切换栏（漂浮宠物外部控制时不展示） */
    showTabs?: boolean
  }>(),
  { action: '', size: 160, interactive: true, showTabs: true },
)

const emit = defineEmits<{ (e: 'action-change', key: string): void }>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
const currentKey = ref('')
const frameIndex = ref(0)
const paused = ref(false)

const actions = computed<PetAnimAction[]>(() => props.anim?.actions ?? [])
const hasMultipleActions = computed(() => actions.value.length > 1)

/** 动作图标（key → emoji） */
const ACTION_ICONS: Record<string, string> = {
  stand: '✨',
  walk: '🐾',
  sleep: '💤',
  interact: '💕',
  fly: '🕊️',
}
function actionIcon(key: string): string {
  return ACTION_ICONS[key] ?? '✨'
}

const currentAction = computed<PetAnimAction | null>(() => {
  if (!actions.value.length) return null
  return actions.value.find((a) => a.key === currentKey.value) ?? actions.value[0]
})

/** 帧缓存：url -> HTMLImageElement */
const frameCache = new Map<string, HTMLImageElement>()
/** 已解码帧：decode() resolve 后加入。只有解码完成的帧才可安全绘制到 canvas（complete ≠ 可画，未解码绘制=白屏） */
const decodedUrls = new Set<string>()

function loadFrame(url: string): HTMLImageElement {
  let img = frameCache.get(url)
  if (!img) {
    img = new Image()
    img.src = url
    frameCache.set(url, img)
    // 触发解码；完成后登记并主动重绘（此时可能正等待该帧）
    img
      .decode()
      .then(() => {
        decodedUrls.add(url)
        draw()
      })
      .catch(() => {
        // 解码失败（网络错误等）：complete 兜底登记，避免永久空白
        if (img!.complete && img!.naturalWidth > 0) {
          decodedUrls.add(url)
          draw()
        }
      })
  }
  return img
}

/** 预载：所有动作的全部帧（首次进入即并发加载，之后切动作零等待） */
function preloadAll(anim: PetAnim) {
  for (const act of anim.actions) {
    for (const url of act.frames) loadFrame(url)
  }
}

/** 按设备像素比设置 canvas 物理尺寸，保证像素图清晰 */
function resizeCanvas() {
  const canvas = canvasRef.value
  if (!canvas) return
  const dpr = Math.min(window.devicePixelRatio || 1, 3)
  canvas.width = Math.round(props.size * dpr)
  canvas.height = Math.round(props.size * dpr)
  draw()
}

function draw() {
  const canvas = canvasRef.value
  const act = currentAction.value
  if (!canvas || !act || !act.frames.length) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const url = act.frames[frameIndex.value % act.frames.length]
  const img = loadFrame(url)
  // 防闪白核心：仅绘制已解码帧；未就绪时不清屏、保留上一帧画面
  if (decodedUrls.has(url)) {
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.imageSmoothingEnabled = false
    const scale = Math.min(canvas.width / img.naturalWidth, canvas.height / img.naturalHeight)
    const w = Math.round(img.naturalWidth * scale)
    const h = Math.round(img.naturalHeight * scale)
    ctx.drawImage(img, Math.round((canvas.width - w) / 2), Math.round((canvas.height - h) / 2), w, h)
  }
}

let timer: number | null = null

function stopTimer() {
  if (timer !== null) {
    window.clearInterval(timer)
    timer = null
  }
}

function startTimer() {
  stopTimer()
  const act = currentAction.value
  if (!act || act.frames.length <= 1) return
  timer = window.setInterval(() => {
    if (!paused.value) {
      frameIndex.value = (frameIndex.value + 1) % act.frames.length
    }
    draw()
  }, Math.max(40, act.interval))
}

function switchAction(key: string) {
  if (!actions.value.some((a) => a.key === key)) return
  if (currentKey.value === key) return
  currentKey.value = key
  frameIndex.value = 0
  emit('action-change', key)
}

/** 点击宠物：在所有动作间轮换（互动彩蛋） */
function onTapPet() {
  if (!props.interactive || !hasMultipleActions.value) return
  const idx = actions.value.findIndex((a) => a.key === currentKey.value)
  const next = actions.value[(idx + 1) % actions.value.length]
  switchAction(next.key)
}

// 暴露给外部（漂浮宠物通过 ref 操控动作）
defineExpose({ switchAction })

watch(
  () => props.anim,
  (anim) => {
    if (!anim || !anim.actions.length) return
    preloadAll(anim)
    const initKey =
      props.action && anim.actions.some((a) => a.key === props.action)
        ? props.action
        : anim.actions[0].key
    currentKey.value = initKey
    frameIndex.value = 0
  },
  { immediate: true },
)

watch(currentAction, () => {
  startTimer()
})

watch(() => props.size, () => resizeCanvas())
watch(frameIndex, () => draw())

onMounted(() => {
  resizeCanvas()
  startTimer()
})
onBeforeUnmount(() => stopTimer())
</script>

<template>
  <div class="pet-anim" :style="{ width: size + 'px', height: size + 'px' }">
    <canvas
      ref="canvasRef"
      class="pet-anim__canvas"
      :class="{ 'is-clickable': interactive && hasMultipleActions }"
      :style="{ width: size + 'px', height: size + 'px' }"
      @click="onTapPet"
    />

    <!-- 动作切换栏：磨砂胶囊分段控件（单动作/外部操控时不展示） -->
    <div
      v-if="interactive && showTabs && hasMultipleActions"
      class="pet-anim__tabs"
    >
      <div class="pet-anim__tabs-inner">
        <button
          v-for="act in actions"
          :key="act.key"
          class="pet-anim__tab"
          :class="{ 'is-active': act.key === currentKey }"
          type="button"
          @click="switchAction(act.key)"
        >
          <span class="pet-anim__tab-icon">{{ actionIcon(act.key) }}</span>
          <span class="pet-anim__tab-label">{{ act.label }}</span>
        </button>
      </div>
    </div>

    <!-- 暂停/播放：磨砂圆形按钮 -->
    <button
      v-if="interactive && hasMultipleActions"
      class="pet-anim__toggle"
      type="button"
      :aria-label="paused ? '播放' : '暂停'"
      @click="paused = !paused"
    >
      <svg v-if="paused" viewBox="0 0 24 24" width="12" height="12" fill="currentColor">
        <path d="M8 5v14l11-7z" />
      </svg>
      <svg v-else viewBox="0 0 24 24" width="12" height="12" fill="currentColor">
        <rect x="6" y="5" width="4" height="14" rx="1" />
        <rect x="14" y="5" width="4" height="14" rx="1" />
      </svg>
    </button>
  </div>
</template>

<style scoped>
.pet-anim {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  user-select: none;
}
.pet-anim__canvas {
  display: block;
  filter: drop-shadow(0 6px 12px rgba(23, 32, 64, 0.16));
}
.pet-anim__canvas.is-clickable {
  cursor: pointer;
}
.pet-anim__canvas.is-clickable:active {
  transform: scale(0.94);
}

/* ====== 动作切换栏：磨砂胶囊分段控件 ====== */
.pet-anim__tabs {
  position: absolute;
  bottom: -8px;
  left: 50%;
  transform: translate(-50%, 100%);
  z-index: 2;
}
.pet-anim__tabs-inner {
  display: flex;
  gap: 2px;
  padding: 3px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(23, 32, 64, 0.06);
  box-shadow: 0 4px 16px rgba(23, 32, 64, 0.12);
  -webkit-backdrop-filter: blur(12px);
  backdrop-filter: blur(12px);
}
.pet-anim__tab {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: #5a5f6e;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 160ms cubic-bezier(0.32, 0.72, 0, 1);
  white-space: nowrap;
}
.pet-anim__tab:hover {
  color: #1c2030;
  background: rgba(23, 32, 64, 0.05);
}
.pet-anim__tab.is-active {
  background: linear-gradient(135deg, #5b8cff, #3d7bff);
  color: #fff;
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(61, 123, 255, 0.35);
}
.pet-anim__tab-icon {
  font-size: 13px;
  line-height: 1;
}

/* ====== 暂停/播放：磨砂圆钮 ====== */
.pet-anim__toggle {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 24px;
  height: 24px;
  border: 1px solid rgba(23, 32, 64, 0.08);
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.82);
  color: #5a5f6e;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(23, 32, 64, 0.1);
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
  transition: all 150ms ease;
}
.pet-anim__toggle:hover {
  color: #1c2030;
  transform: scale(1.06);
}
</style>
