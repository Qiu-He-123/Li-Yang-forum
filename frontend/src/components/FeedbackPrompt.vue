<script setup lang="ts">
/**
 * 意见反馈轻提示「给点意见吧」
 *
 * 触发策略（要求"真实用了足够久"才提示，避免新用户刚注册/刚进站就弹）：
 * - 累计"前台活跃使用时长"达到阈值（默认 5 分钟）才考虑弹出
 * - 每个新用户周期最多弹 1 次；已弹过/已点过「先不了」则当天不再弹
 * - 点「给点意见」→ 去 /feedback 反馈页；被采纳可加金币
 * - 点「先不了」→ 收起，提示「可在『我的-最下方』随时反馈」，当天不再打扰
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { Icon } from './native'
import { toast } from './native/Toast'
import { useSessionStore } from '../stores/session'

const router = useRouter()
const session = useSessionStore()

const visible = ref(false)

const LS_KEY = 'xiguo_feedback_prompt_day'
const LS_SUPPRESS = 'xiguo_feedback_prompt_suppressed'
const LS_USAGE = 'xiguo_feedback_usage_ms'
/** 累计前台使用时长阈值：达到后才允许弹出（毫秒） */
const USAGE_THRESHOLD = 5 * 60 * 1000

function today(): string {
  const d = new Date()
  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`
}

function shouldShow(): boolean {
  if (!session.userId) return false // 未登录不强打扰
  try {
    if (localStorage.getItem(LS_SUPPRESS) === '1') return false // 曾点过「先不了」，长期不打扰
    if (localStorage.getItem(LS_KEY) === today()) return false // 今天已弹过
  } catch {
    return false
  }
  return true
}

function readUsage(): number {
  try {
    return Number(localStorage.getItem(LS_USAGE)) || 0
  } catch {
    return 0
  }
}
function writeUsage(ms: number) {
  try {
    localStorage.setItem(LS_USAGE, String(ms))
  } catch {
    /* ignore */
  }
}

function markShown() {
  try {
    localStorage.setItem(LS_KEY, today())
  } catch {
    /* ignore */
  }
}

let usageTimer: number | null = null
let lastTick = 0

function clearUsageTimer() {
  if (usageTimer !== null) {
    clearInterval(usageTimer)
    usageTimer = null
  }
}

function schedule() {
  lastTick = Date.now()
  // 每秒累计"前台可见"时长，只有真实用了足够久才弹，避免刚注册就被打扰。
  usageTimer = window.setInterval(() => {
    const now = Date.now()
    const delta = now - lastTick
    lastTick = now // 始终刷新基准，隐藏期间不计入使用时长
    if (document.visibilityState !== 'visible') return
    const total = readUsage() + delta
    writeUsage(total)
    if (visible.value) return
    if (total < USAGE_THRESHOLD) return
    if (!shouldShow()) return
    visible.value = true
    markShown()
    clearUsageTimer()
  }, 1000)
}

function go() {
  visible.value = false
  router.push('/feedback')
}

function later() {
  visible.value = false
  try {
    localStorage.setItem(LS_SUPPRESS, '1')
  } catch {
    /* ignore */
  }
  toast.info('已记下～也可在「我的」底部随时反馈，被采纳还有金币奖励')
}

onMounted(schedule)
onBeforeUnmount(clearUsageTimer)
</script>

<template>
  <Teleport to="body">
    <Transition name="fbp">
      <div v-if="visible" class="fbp-mask" @click.self="later">
        <div class="fbp-card" role="dialog" aria-modal="true" aria-label="给点意见吧">
          <button class="fbp-close" type="button" aria-label="关闭" @click="later">
            <Icon name="x" :size="18" />
          </button>
          <div class="fbp-icon" aria-hidden="true">💡</div>
          <h2 class="fbp-title">给点意见吧</h2>
          <p class="fbp-desc">
            用了这么久，感觉怎么样？你的每一条建议都会让我们做得更好，
            <b>意见被采纳还能获得金币奖励</b>哦～
          </p>
          <div class="fbp-actions">
            <button class="fbp-btn fbp-btn--ghost" type="button" @click="later">先不了</button>
            <button class="fbp-btn fbp-btn--primary" type="button" @click="go">给点意见</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.fbp-mask {
  position: fixed;
  inset: 0;
  z-index: 2100;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.fbp-card {
  position: relative;
  width: 100%;
  max-width: 340px;
  background: #fff;
  border-radius: 20px;
  padding: 26px 22px 20px;
  text-align: center;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.28);
}
.fbp-close {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 50%;
  background: #f2f2f5;
  color: #5a5a62;
  cursor: pointer;
  display: grid;
  place-items: center;
}
.fbp-icon {
  font-size: 46px;
  line-height: 1;
}
.fbp-title {
  margin: 12px 0 8px;
  font-size: 19px;
  font-weight: 800;
  color: #1d1d1f;
  letter-spacing: -0.01em;
}
.fbp-desc {
  margin: 0 auto 18px;
  font-size: 14px;
  line-height: 1.7;
  color: #6e6e73;
  max-width: 260px;
}
.fbp-desc b { color: #ff9500; }
.fbp-actions { display: flex; gap: 12px; }
.fbp-btn {
  flex: 1;
  height: 46px;
  border: none;
  border-radius: 23px;
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
}
.fbp-btn--ghost { background: #f2f2f5; color: #6e6e73; }
.fbp-btn--primary {
  background: linear-gradient(135deg, #0071e3, #5856d6);
  color: #fff;
  box-shadow: 0 8px 20px rgba(0, 113, 227, 0.3);
}

.fbp-enter-active, .fbp-leave-active { transition: opacity 0.2s var(--ease-apple, ease); }
.fbp-enter-active .fbp-card, .fbp-leave-active .fbp-card { transition: transform 0.2s var(--ease-apple, ease); }
.fbp-enter-from, .fbp-leave-to { opacity: 0; }
.fbp-enter-from .fbp-card, .fbp-leave-to .fbp-card { transform: scale(0.92) translateY(10px); }
</style>