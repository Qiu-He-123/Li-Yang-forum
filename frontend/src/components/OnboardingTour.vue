<script setup lang="ts">
/**
 * 新手引导（Onboarding Tour）—— 全论坛教程
 *
 * 视觉实现参考 GitHub 开源引导库 driver.js
 * （https://github.com/kamranahmedse/driver.js）：
 * - 遮罩：全屏 SVG path + `fill-rule: evenodd`，外圈覆盖全屏压暗，
 *   内圈圆角矩形挖洞，目标元素完全透亮
 * - 交互：引导期间页面全部锁死（body 层禁点 + 全屏点击拦截层），
 *   用户只能点引导气泡里的「上一步 / 下一步 / 跳过」
 * - 气泡：白底、细边框、浅阴影、小按钮、进度文字（driver.js popover 样式语言）
 *
 * 教程覆盖整个论坛：首页频道 → 微信朋友圈 → 圈子 → 发布 → 消息 → 我的 → 完成
 *
 * 交互约定：
 * - 引导期间页面全部锁死，只能点气泡按钮
 * - 每一步聚焦一个具体可点的元素，文案告诉用户"点哪里、会发生什么"
 * - 目标找不到时先等待页面加载，超时给出兜底提示，绝不卡死
 */
import {
  computed,
  nextTick,
  onMounted,
  onUnmounted,
  reactive,
  ref,
  watch,
} from 'vue'
import { useRouter } from 'vue-router'

import { completeOnboarding, getOnboardingStatus } from '../api/onboarding'
import { getWechatStatus } from '../api/wechat'
import { useSessionStore } from '../stores/session'

const session = useSessionStore()
const router = useRouter()
const visible = ref(false)
const stepIdx = ref(0)
const rect = reactive({ left: 0, top: 0, width: 0, height: 0, found: false })
const locating = ref(false)
const located = ref(false)
const wechatBound = ref(false)

// 高亮孔相对目标元素外扩的间距 / 圆角半径（driver.js 的 stagePadding / stageRadius）
const PAD = 10
const RADIUS = 10

const HOME = () => '/'
const MOMENTS = () => ({ path: '/', query: { tab: 'moments' } })

interface TourStep {
  /** 点击下一步后跳转到的路由 */
  goto: () => string | { path: string; query: Record<string, string> }
  /** 当前页面里要高亮的目标元素选择器 */
  selector: string
  title: string
  desc: string
  /** 目标元素加载失败的兜底提示 */
  fallback?: string
  /** 整屏遮罩模式：不挖洞、不高亮任何元素，只压暗全屏（用于欢迎页） */
  fullscreen?: boolean
  /** 完全无遮罩：不压暗、不挖洞、不高亮，只显示气泡（用于"我的"页） */
  noMask?: boolean
  /** 滚动对齐方式：center 居中 / bottom 滚到页面底部 / top 顶部 */
  align?: 'center' | 'bottom' | 'top'
  /** 先滚动到页面最底部再定位（用于"结束在最底部"的步骤） */
  scrollToBottom?: boolean
}

// 基础步骤（不依赖用户状态）；第 2 步会按绑定状态动态生成
const BASE_STEPS: TourStep[] = [
  {
    goto: HOME,
    selector: '.feed-tabs',
    title: '第 1 步 · 首页帖子',
    desc: '首页顶部是帖子频道：点「推荐」看热门，点「最新」看实时动态，点「微信朋友圈」看同学同步的内容。',
  },
  {
    goto: MOMENTS,
    selector: '.moments-guide-btn, .feed-tab--moments',
    title: '第 2 步 · 微信朋友圈频道',
    desc: '这里是微信朋友圈频道。',
    fallback: '微信朋友圈频道暂无可展示内容，先去看看其他功能吧。',
  },
  {
    goto: () => '/post/create',
    selector: '.bottom-tab--publish',
    title: '第 3 步 · 发布内容',
    desc: '点中间凸起的「发布」按钮，就能发帖子：写文字、传图片、选圈子，让同学看到你。',
  },
  {
    goto: () => '/circles',
    selector: '.all-circles-section',
    title: '第 4 步 · 加入圈子',
    desc: '圈子按主题分类：表白墙、树洞、兴趣小组……找到喜欢的圈子点进去，先看看大家聊什么。',
    scrollToBottom: true,
  },
  {
    goto: () => '/notifications',
    selector: '.bottom-tabbar',
    title: '第 5 步 · 消息提醒',
    desc: '「消息」Tab 管理所有互动：点赞、评论、关注、私信。有红点就点进来看。',
  },
  {
    goto: () => `/user/${session.userId}`,
    selector: '',
    title: '第 6 步 · 我的主页',
    desc: '这里是你的功能入口区：绑定微信、我的作品、收藏、签到、徽章都在这里。点「绑定微信」可以把朋友圈同步到社区。',
    fallback: '「我的」页面暂时没有可展示的功能入口，直接继续吧。',
    noMask: true,
  },
]

// 欢迎步骤 + 基础步骤；第 2 步（微信朋友圈）文案按绑定状态动态生成
const STEPS = ref<TourStep[]>([])
const WELCOME_STEP: TourStep = {
  goto: HOME,
  selector: '',
  title: '欢迎来到立洋社区',
  desc: '这是同学们的校园交流社区。接下来 6 步带你快速认识它：看帖子、同步朋友圈、发内容、逛圈子、收消息、管理主页。',
  fullscreen: true,
}

function buildSteps() {
  const base = BASE_STEPS.map((s) => ({ ...s }))
  const momentsStep = base.find((s) => s.title.includes('微信朋友圈'))
  if (momentsStep) {
    momentsStep.desc = wechatBound.value
      ? '这里是微信朋友圈频道，你已绑定的朋友圈动态会展示在这里。'
      : '这里是微信朋友圈频道。点下方「去绑定」，可以绑定你的微信并同步朋友圈到社区。'
  }
  STEPS.value = [WELCOME_STEP, ...base]
}

let locateTimer: ReturnType<typeof setTimeout> | null = null
let locateTries = 0
let observer: MutationObserver | null = null
let scrollLocked = false

/** 锁住用户手动滚动（滚轮/触摸/键盘），但程序 scrollIntoView 不受影响 */
function onWheel(e: WheelEvent) {
  if (scrollLocked) e.preventDefault()
}
function onTouchMove(e: TouchEvent) {
  if (scrollLocked) e.preventDefault()
}
function onKeydown(e: KeyboardEvent) {
  if (scrollLocked && ['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '].includes(e.key)) {
    e.preventDefault()
  }
}

function setScrollLock(locked: boolean) {
  scrollLocked = locked
  if (locked) {
    window.addEventListener('wheel', onWheel, { passive: false })
    window.addEventListener('touchmove', onTouchMove, { passive: false })
    window.addEventListener('keydown', onKeydown)
  } else {
    window.removeEventListener('wheel', onWheel)
    window.removeEventListener('touchmove', onTouchMove)
    window.removeEventListener('keydown', onKeydown)
  }
}

async function check() {
  if (!session.userId) return
  try {
    const data = (await getOnboardingStatus()).data.data
    if (!data.onboarding_done) {
      try {
        const ws = (await getWechatStatus()).data.data
        wechatBound.value = Boolean(ws?.bound)
      } catch {
        wechatBound.value = false
      }
      buildSteps()
      stepIdx.value = 0
      visible.value = true
      document.body.classList.add('tour-body-lock')
      setScrollLock(true)
      await showStep()
    }
  } catch {
    /* 静默，下次登录再触发 */
  }
}

/** 定位当前步骤的目标元素；找不到就重试，最多 3 秒 */
function locateTarget() {
  const s = STEPS.value[stepIdx.value]
  if (!s) return
  // 整屏遮罩步骤：不需要定位任何元素
  if (s.fullscreen) {
    locating.value = false
    located.value = true
    rect.left = rect.top = rect.width = rect.height = 0
    rect.found = false
    return
  }
  // 无遮罩步骤：只显示气泡，不定位、不高亮
  if (s.noMask) {
    locating.value = false
    located.value = true
    rect.left = rect.top = rect.width = rect.height = 0
    rect.found = false
    return
  }
  const el = document.querySelector(s.selector)
  if (el) {
    locateTries = 0
    locating.value = false
    located.value = true
    if (locateTimer) {
      clearTimeout(locateTimer)
      locateTimer = null
    }
    const measure = () => {
      const r = el.getBoundingClientRect()
      rect.left = r.left - PAD
      rect.top = r.top - PAD
      rect.width = r.width + PAD * 2
      rect.height = r.height + PAD * 2
      rect.found = true
    }
    // 结束在最底部：先滚到页面底部，再等动画结束后测量
    if (s.scrollToBottom) {
      const scroller = document.scrollingElement || document.documentElement
      try {
        scroller.scrollTo({ top: scroller.scrollHeight, behavior: 'smooth' })
      } catch {
        scroller.scrollTop = scroller.scrollHeight
      }
      locateTimer = setTimeout(measure, 650)
      return
    }
    try {
      const block = s.align === 'bottom' ? 'end' : s.align === 'top' ? 'start' : 'center'
      ;(el as HTMLElement).scrollIntoView({ block, behavior: 'smooth' })
    } catch {
      /* 忽略滚动失败 */
    }
    // 平滑滚动需要时间：滚动动画结束后再测量，避免高亮停在滚动前的位置
    locateTimer = setTimeout(measure, 620)
    return
  }
  locating.value = true
  if (locateTries < 20) {
    locateTries += 1
    locateTimer = setTimeout(locateTarget, 150)
  } else {
    locating.value = false
    located.value = false
    rect.left = rect.top = rect.width = rect.height = 0
    rect.found = false
  }
}

async function showStep() {
  const s = STEPS.value[stepIdx.value]
  const target = s.goto()
  const targetPath = typeof target === 'string' ? target : router.resolve(target).fullPath
  if (router.currentRoute.value.fullPath !== targetPath) {
    await router.push(target as never)
    await nextTick()
  }
  locating.value = true
  located.value = false
  locateTries = 0
  if (locateTimer) clearTimeout(locateTimer)
  locateTimer = setTimeout(locateTarget, 120)
}

async function next() {
  if (stepIdx.value < STEPS.value.length - 1) {
    stepIdx.value += 1
    await showStep()
  } else {
    await finish()
  }
}

async function prev() {
  if (stepIdx.value > 0) {
    stepIdx.value -= 1
    located.value = false
    locating.value = true
    await showStep()
  }
}

async function finish() {
  visible.value = false
  document.body.classList.remove('tour-body-lock')
  setScrollLock(false)
  try {
    await completeOnboarding()
  } catch {
    /* 标记失败不阻塞 */
  }
  router.push('/')
}

/**
 * 生成 driver.js 同款遮罩 path：
 * 第一条子路径覆盖整个视口，第二条子路径是带圆角的矩形孔，
 * 配合 `fill-rule: evenodd`，孔内（目标元素）不填充、完全透亮。
 */
function generateStageSvgPathString() {
  const windowX = window.innerWidth
  const windowY = window.innerHeight
  const radius = Math.min(RADIUS, rect.width / 2, rect.height / 2)
  const hx = rect.left + radius
  const hy = rect.top
  const hw = rect.width - radius * 2
  const hh = rect.height - radius * 2
  return (
    `M${windowX},0L0,0L0,${windowY}L${windowX},${windowY}L${windowX},0Z` +
    `M${hx},${hy} h${hw} a${radius},${radius} 0 0 1 ${radius},${radius}` +
    ` v${hh} a${radius},${radius} 0 0 1 -${radius},${radius}` +
    ` h-${hw} a${radius},${radius} 0 0 1 -${radius},-${radius}` +
    ` v-${hh} a${radius},${radius} 0 0 1 ${radius},-${radius} z`
  )
}

const fullscreenStep = computed(() => STEPS.value[stepIdx.value]?.fullscreen === true)
const noMaskStep = computed(() => STEPS.value[stepIdx.value]?.noMask === true)
const svgPath = computed(() => {
  if (fullscreenStep.value) {
    // 全屏压暗：整屏矩形，不挖洞
    return `M${window.innerWidth},0L0,0L0,${window.innerHeight}L${window.innerWidth},${window.innerHeight}Z`
  }
  if (noMaskStep.value) return ''
  return rect.found ? generateStageSvgPathString() : ''
})
const viewBox = computed(() => {
  if (noMaskStep.value) return '0 0 0 0'
  if (fullscreenStep.value || rect.found) {
    return `0 0 ${window.innerWidth} ${window.innerHeight}`
  }
  return '0 0 0 0'
})

const belowSpace = computed(() =>
  rect.found ? window.innerHeight - (rect.top + rect.height) >= 216 : false,
)
// 目标上方的空间是否足够放气泡（气泡高约 196px）
const aboveSpace = computed(() =>
  rect.found ? rect.top >= 210 : false,
)

// 欢迎步骤 / 目标缺失：气泡居中展示，不带箭头
const centeredPanel = computed(() => isWelcome.value || noMaskStep.value || !rect.found)
const panelStyle = computed(() => {
  if (centeredPanel.value) {
    return { top: '34vh', left: '50%', transform: 'translateX(-50%)' }
  }
  // 优先放目标下方；下方放不下但上方放得下时放上方；两边都放不下时
  // 贴底放（保证不遮住高亮目标本身）
  if (belowSpace.value) {
    return {
      top: `${rect.top + rect.height + 12}px`,
      left: '50%',
      transform: 'translateX(-50%)',
    }
  }
  if (aboveSpace.value) {
    return {
      top: `${Math.max(10, rect.top - 208)}px`,
      left: '50%',
      transform: 'translateX(-50%)',
    }
  }
  return {
    top: `${Math.min(rect.top + rect.height + 12, window.innerHeight - 208)}px`,
    left: '50%',
    transform: 'translateX(-50%)',
  }
})

const arrowStyle = computed(() => {
  if (centeredPanel.value) return { display: 'none' }
  // 气泡宽度 300px、水平居中：先算出气泡相对视口的 left，再算箭头相对气泡的 left
  const popoverLeft = (window.innerWidth - 300) / 2
  const targetCenter = rect.left + rect.width / 2
  const cx = Math.min(Math.max(targetCenter - popoverLeft, 20), 280)
  return belowSpace.value
    ? { left: `${cx}px`, top: '0px', transform: 'translateY(-100%)' }
    : { left: `${cx}px`, bottom: '0px', transform: 'translateY(100%) rotate(180deg)' }
})

const holeStyle = computed(() => ({
  left: `${rect.left}px`,
  top: `${rect.top}px`,
  width: `${rect.width}px`,
  height: `${rect.height}px`,
  display: rect.found ? 'block' : 'none',
}))

const progressText = computed(() => `${stepIdx.value + 1} / ${STEPS.value.length}`)
const isWelcome = computed(() => stepIdx.value === 0)
const isLast = computed(() => stepIdx.value === STEPS.value.length - 1)
const currentStep = computed(() => STEPS.value[stepIdx.value])
const currentFallback = computed(() => currentStep.value?.fallback ?? '')

watch(() => session.userId, (id) => {
  if (id) check()
})

onMounted(() => {
  check()
  // 动态内容（如朋友圈频道异步加载后的引导条）出现时，重新定位高亮
  observer = new MutationObserver(() => {
    if (visible.value && !rect.found) locateTarget()
  })
  observer.observe(document.body, { childList: true, subtree: true })
})

onUnmounted(() => {
  document.body.classList.remove('tour-body-lock')
  setScrollLock(false)
  if (locateTimer) clearTimeout(locateTimer)
  if (observer) observer.disconnect()
})
</script>

<template>
  <Teleport to="body">
    <Transition name="tour-fade">
      <div v-if="visible" class="tour-root">
        <!-- 全屏点击拦截层：引导期间页面任何地方都点不动，只能点气泡按钮 -->
        <div class="tour-click-trap"></div>
        <!-- 全屏遮罩：SVG path + evenodd 挖洞（driver.js 实现） -->
        <svg
          class="tour-overlay"
          :viewBox="viewBox"
          preserveAspectRatio="xMinYMin slice"
          aria-hidden="true"
        >
          <path
            class="tour-overlay-path"
            :class="{ 'tour-overlay-path--soft': fullscreenStep }"
            fill-rule="evenodd"
            :d="svgPath"
          />
        </svg>
        <!-- 目标高亮框：白色描边，不遮内容 -->
        <div v-if="!fullscreenStep" class="tour-hole" :style="holeStyle"></div>
        <!-- 说明气泡 -->
        <div class="tour-popover" :style="panelStyle" role="dialog" aria-label="新手引导">
          <span class="tour-arrow" :style="arrowStyle"></span>
          <div class="tour-progress-bar">
            <span class="tour-progress-fill" :style="{ width: `${((stepIdx + 1) / STEPS.length) * 100}%` }"></span>
          </div>
          <p class="tour-title">{{ STEPS[stepIdx].title }}</p>
          <p v-if="locating && !located" class="tour-desc tour-desc--loading">
            正在定位页面内容…
          </p>
          <p v-else-if="!located && !rect.found && currentFallback" class="tour-desc">
            {{ currentFallback }}
          </p>
          <p v-else class="tour-desc">{{ STEPS[stepIdx].desc }}</p>
          <div class="tour-footer">
            <span class="tour-progress">{{ progressText }}</span>
            <div class="tour-btns">
              <button type="button" class="tour-btn" @click="finish">跳过</button>
              <button
                v-if="stepIdx > 0"
                type="button"
                class="tour-btn"
                @click="prev"
              >上一步</button>
              <button
                type="button"
                class="tour-btn tour-btn--primary"
                @click="next"
              >{{ isLast ? '完成' : '下一步' }}</button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* 引导期间页面全部锁死：禁点 + 禁滚动 */
:global(body.tour-body-lock *),
:global(body.tour-body-lock *::before),
:global(body.tour-body-lock *::after) {
  pointer-events: none !important;
}
:global(body.tour-body-lock .tour-root),
:global(body.tour-body-lock .tour-root *),
:global(body.tour-body-lock .tour-root *::before),
:global(body.tour-body-lock .tour-root *::after) {
  pointer-events: auto !important;
}

.tour-root {
  position: fixed;
  inset: 0;
  z-index: 9999;
}
.tour-click-trap {
  position: fixed;
  inset: 0;
  z-index: 1;
  background: transparent;
}
.tour-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 2;
  pointer-events: none;
}
.tour-overlay-path {
  /* driver.js 同款：evenodd 挖洞 + 独立透明度 */
  fill: rgb(13, 17, 23);
  fill-rule: evenodd;
  clip-rule: evenodd;
  opacity: 0.68;
  transition: d 0.25s ease;
}
.tour-overlay-path--soft {
  /* 欢迎页整屏压暗：浅一点，能看到页面轮廓 */
  opacity: 0.45;
}
.tour-hole {
  position: fixed;
  z-index: 3;
  border: 2px solid rgba(255, 255, 255, 0.95);
  border-radius: 12px;
  box-shadow: 0 0 0 4px rgba(9, 105, 218, 0.32), 0 0 20px rgba(9, 105, 218, 0.28);
  pointer-events: none;
  transition: all 0.25s ease;
}
.tour-popover {
  position: fixed;
  z-index: 4;
  width: 300px;
  max-width: calc(100vw - 32px);
  background: #fff;
  border-radius: 6px;
  padding: 14px 15px;
  box-shadow: 0 1px 10px rgba(0, 0, 0, 0.38);
  color: #2d2d2d;
}
.tour-progress-bar {
  height: 3px;
  border-radius: 2px;
  background: #eceff1;
  overflow: hidden;
  margin-bottom: 12px;
}
.tour-progress-fill {
  display: block;
  height: 100%;
  border-radius: 2px;
  background: #0969da;
  transition: width 0.25s ease;
}
.tour-arrow {
  position: absolute;
  width: 0;
  height: 0;
  border-left: 8px solid transparent;
  border-right: 8px solid transparent;
  border-bottom: 9px solid #fff;
  filter: drop-shadow(0 -1px 1px rgba(0, 0, 0, 0.12));
}
.tour-title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  line-height: 1.5;
}
.tour-desc {
  margin: 5px 0 0;
  font-size: 14px;
  line-height: 1.6;
  color: #555;
}
.tour-desc--loading {
  color: #888;
}
.tour-footer {
  margin-top: 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.tour-progress {
  font-size: 13px;
  color: #727272;
}
.tour-btns {
  display: flex;
  gap: 6px;
}
.tour-btn {
  border: 1px solid #ccc;
  background: #fff;
  color: #2d2d2d;
  border-radius: 4px;
  padding: 3px 9px;
  font-size: 12px;
  line-height: 1.5;
  cursor: pointer;
}
.tour-btn:hover {
  background: #f7f7f7;
}
.tour-btn--primary {
  border-color: #0969da;
  background: #0969da;
  color: #fff;
}
.tour-btn--primary:hover {
  background: #0a5bc0;
}
.tour-fade-enter-active,
.tour-fade-leave-active {
  transition: opacity 0.25s;
}
.tour-fade-enter-from,
.tour-fade-leave-to {
  opacity: 0;
}
</style>
