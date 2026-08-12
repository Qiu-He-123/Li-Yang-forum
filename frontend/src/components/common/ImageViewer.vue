<script setup lang="ts">
/**
 * 全屏图片查看器（微信/抖音式）
 * - 左上角返回按钮
 * - 双击 / 双指捏合缩放（1x ~ 5x），单指拖动平移
 * - 多图支持左右切换（缩放状态下用按钮切换）
 * - 滚轮缩放（桌面）
 */
import { computed, onUnmounted, ref, watch } from 'vue'

import { Icon } from '../native'

const props = withDefaults(
  defineProps<{
    visible: boolean
    url: string
    urls?: string[]
    initialIndex?: number
  }>(),
  { urls: () => [], initialIndex: 0 },
)

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'update:index', idx: number): void
}>()

const index = ref(props.initialIndex)
const currentUrl = computed(() => (props.urls.length ? props.urls[index.value] : props.url) || '')
const multiple = computed(() => props.urls.length > 1)

// 缩放状态
const scale = ref(1)
const translateX = ref(0)
const translateY = ref(0)
const dragging = ref(false)
const dragStartX = ref(0)
const dragStartY = ref(0)
const lastPinchDist = ref(0)
const startScale = ref(1)
const lastTap = ref(0)
const transform = computed(
  () => `translate(${translateX.value}px, ${translateY.value}px) scale(${scale.value})`,
)

const MIN_SCALE = 1
const MAX_SCALE = 5

watch(
  () => props.initialIndex,
  (v) => {
    if (props.visible) {
      index.value = v
      resetTransform()
    }
  },
)

function close() {
  emit('update:visible', false)
}

// ---- 返回键/返回手势：关闭查看器而不是返回上一页 ----
// 打开时 push 一条 history 记录，返回键（浏览器 / App WebView goBack）会先触发 popstate 关掉查看器
let historyPushed = false

function onPopState() {
  if (historyPushed) {
    historyPushed = false
    close()
  }
}

watch(
  () => props.visible,
  (v) => {
    if (v) {
      try {
        window.history.pushState({ iv: true }, '')
        historyPushed = true
      } catch {
        /* ignore */
      }
      window.addEventListener('popstate', onPopState)
      index.value = props.initialIndex
      resetTransform()
    } else {
      window.removeEventListener('popstate', onPopState)
      if (historyPushed) {
        try {
          window.history.back()
        } catch {
          /* ignore */
        }
        historyPushed = false
      }
    }
  },
)

onUnmounted(() => {
  window.removeEventListener('popstate', onPopState)
  if (historyPushed) {
    try {
      window.history.back()
    } catch {
      /* ignore */
    }
    historyPushed = false
  }
})

function resetTransform() {
  scale.value = 1
  translateX.value = 0
  translateY.value = 0
}

function clampTranslate() {
  // 限制拖动范围：缩放越大可拖动范围越大
  const maxX = (scale.value - 1) * 200
  const maxY = (scale.value - 1) * 200
  translateX.value = Math.max(-maxX, Math.min(maxX, translateX.value))
  translateY.value = Math.max(-maxY, Math.min(maxY, translateY.value))
}

function prev() {
  if (!multiple.value) return
  index.value = (index.value - 1 + props.urls.length) % props.urls.length
  emit('update:index', index.value)
  resetTransform()
}

function next() {
  if (!multiple.value) return
  index.value = (index.value + 1) % props.urls.length
  emit('update:index', index.value)
  resetTransform()
}

function dist(a: Touch, b: Touch): number {
  return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY)
}

function onTouchStart(e: TouchEvent) {
  if (e.touches.length === 1) {
    dragging.value = true
    dragStartX.value = e.touches[0].clientX - translateX.value
    dragStartY.value = e.touches[0].clientY - translateY.value
    lastPinchDist.value = 0
    // 双击检测
    const now = Date.now()
    if (now - lastTap.value < 280) {
      lastTap.value = 0
      toggleZoom()
      dragging.value = false
      return
    }
    lastTap.value = now
  } else if (e.touches.length === 2) {
    dragging.value = false
    lastPinchDist.value = dist(e.touches[0], e.touches[1])
    startScale.value = scale.value
  }
}

function onTouchMove(e: TouchEvent) {
  if (e.touches.length === 1 && dragging.value && scale.value > 1) {
    translateX.value = e.touches[0].clientX - dragStartX.value
    translateY.value = e.touches[0].clientY - dragStartY.value
    clampTranslate()
  } else if (e.touches.length === 2) {
    const d = dist(e.touches[0], e.touches[1])
    if (lastPinchDist.value > 0) {
      const nextScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, startScale.value * (d / lastPinchDist.value)))
      scale.value = nextScale
    }
    lastPinchDist.value = d
  }
}

function onTouchEnd() {
  dragging.value = false
  lastPinchDist.value = 0
  clampTranslate()
}

function toggleZoom() {
  if (scale.value > 1) {
    resetTransform()
  } else {
    scale.value = 2.5
  }
}

function onWheel(e: WheelEvent) {
  e.preventDefault()
  const delta = e.deltaY < 0 ? 1.15 : 0.87
  scale.value = Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale.value * delta))
  clampTranslate()
}

function onKey(e: KeyboardEvent) {
  if (!props.visible) return
  if (e.key === 'Escape') close()
  else if (e.key === 'ArrowLeft') prev()
  else if (e.key === 'ArrowRight') next()
}

// 组件挂载时监听键盘（组件常驻）
if (typeof document !== 'undefined') {
  document.addEventListener('keydown', onKey)
}
</script>

<template>
  <Teleport to="body">
    <Transition name="iv-fade">
      <div
        v-if="visible"
        class="iv-overlay"
        role="dialog"
        aria-modal="true"
        @touchstart.passive="onTouchStart"
        @touchmove.passive="onTouchMove"
        @touchend="onTouchEnd"
        @touchcancel="onTouchEnd"
        @wheel.prevent="onWheel"
        @click.self="close"
      >
        <!-- 左上角返回 -->
        <button class="iv-back" type="button" aria-label="返回" @click="close">
          <Icon name="arrow-left" :size="22" color="#fff" />
        </button>

        <div class="iv-stage" :class="{ 'is-zoomed': scale > 1 }">
        <img
            :src="currentUrl"
            class="iv-img"
            :class="{ 'is-dragging': dragging }"
            :style="{ transform }"
            alt="图片预览"
            @dblclick.stop="toggleZoom"
            @dragstart.prevent
          />
        </div>

        <button
          v-if="multiple"
          class="iv-nav iv-prev"
          type="button"
          aria-label="上一张"
          @click.stop="prev"
        >
          <Icon name="chevron-left" :size="30" color="#fff" />
        </button>
        <button
          v-if="multiple"
          class="iv-nav iv-next"
          type="button"
          aria-label="下一张"
          @click.stop="next"
        >
          <Icon name="chevron-right" :size="30" color="#fff" />
        </button>

        <div v-if="multiple" class="iv-counter">{{ index + 1 }} / {{ urls.length }}</div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.iv-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.96);
  z-index: 9999;
  touch-action: none;
  overflow: hidden;
}

.iv-back {
  position: absolute;
  top: calc(10px + env(safe-area-inset-top));
  left: 12px;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.35);
  color: #fff;
  display: grid;
  place-items: center;
  cursor: pointer;
  z-index: 10;
}

.iv-stage {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
}

.iv-img {
  max-width: 100vw;
  max-height: 100vh;
  user-select: none;
  -webkit-user-select: none;
  transition: transform 0.08s ease-out;
  will-change: transform;
}

.iv-img.is-dragging {
  transition: none;
}

.iv-nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.35);
  color: #fff;
  display: grid;
  place-items: center;
  cursor: pointer;
  z-index: 10;
}

.iv-prev {
  left: 10px;
}

.iv-next {
  right: 10px;
}

.iv-counter {
  position: absolute;
  bottom: calc(24px + env(safe-area-inset-bottom));
  left: 50%;
  transform: translateX(-50%);
  color: #fff;
  font-size: 13px;
  background: rgba(0, 0, 0, 0.4);
  padding: 4px 12px;
  border-radius: 12px;
}

.iv-fade-enter-active,
.iv-fade-leave-active {
  transition: opacity 0.2s ease;
}

.iv-fade-enter-from,
.iv-fade-leave-to {
  opacity: 0;
}
</style>
