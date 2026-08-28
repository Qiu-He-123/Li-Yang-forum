<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useGuessStore } from '../../stores/guess'
import { useRouter } from 'vue-router'
import Icon from '../native/Icon.vue'

const guessStore = useGuessStore()
const router = useRouter()
const emitting = ref(false) // 脉冲动画
const expanded = ref(false) // 展开/收起状态

function toggleExpand(e: Event) {
  e.stopPropagation()
  expanded.value = !expanded.value
}

const total = computed(() => guessStore.guess?.total_points ?? 0)
const totalUsers = computed(() => guessStore.guess?.total_users ?? 0)

// 计算每个选项的百分比（带一位小数，最低 0.1% 避免视觉消失）
function getOptionPct(opt: { total_points: number }) {
  if (!total.value) return 100 / (guessStore.guess?.options.length || 1)
  const pct = (opt.total_points / total.value) * 100
  return pct < 0.1 ? 0.1 : pct
}
function fmtPct(pct: number) {
  if (pct >= 99.9) return '99.9%'
  if (pct < 0.1) return '0.1%'
  return pct.toFixed(1) + '%'
}
const deadline = computed(() => {
  if (!guessStore.guess?.deadline) return ''
  return guessStore.guess.deadline
})

const remainText = ref('')
// 收起态精简倒计时（只显示 时:分:秒）
const remainCompact = ref('')
let remainTimer: number | null = null

function fmtRemain() {
  if (!deadline.value) {
    remainText.value = ''
    remainCompact.value = ''
    return
  }
  const t = new Date(deadline.value.replace('Z', '')).getTime() - Date.now()
  if (t <= 0) {
    remainText.value = '已截止'
    remainCompact.value = '已截止'
    return
  }
  const h = Math.floor(t / 3600000)
  const m = Math.floor((t % 3600000) / 60000)
  const s = Math.floor((t % 60000) / 1000)
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  remainText.value = `还剩 ${h}时${m}分${s}秒`
  remainCompact.value = `${h}:${mm}:${ss}`
}

watch(
  () => guessStore.guess?.id,
  () => {
    fmtRemain()
    emitting.value = false
    window.setTimeout(() => (emitting.value = true), 30)
  },
  { immediate: true },
)

onMounted(() => {
  remainTimer = window.setInterval(fmtRemain, 1000)
})
onUnmounted(() => {
  if (remainTimer) window.clearInterval(remainTimer)
})

function openGuessPanel() {
  if (!guessStore.guess) return
  const fn = (window as unknown as { __TRY_OPEN_GUESS_POPUP__?: () => void }).__TRY_OPEN_GUESS_POPUP__
  if (!fn) return
  fn()
}
</script>

<template>
  <section v-if="guessStore.guess" class="guess-hero" :class="{ 'is-expanded': expanded }" @click="openGuessPanel">
    <div class="hero-decor decor-1" aria-hidden="true"></div>
    <div class="hero-decor decor-2" aria-hidden="true"></div>

    <!-- ============ 收起态 ============ -->
    <div v-if="!expanded" class="hero-compact">
      <div class="hero-compact__left">
        <span class="hero-tag">
          <span class="dot" :class="{ pulse: emitting }"></span>
          今日竞猜
        </span>
        <h2 class="hero-title hero-title--compact">{{ guessStore.guess.title }}</h2>
      </div>
      <div class="hero-compact__right">
        <!-- 两个大数字并排，平衡左侧标题的视觉重量 -->
        <div class="compact-stats">
          <div class="compact-stat">
            <span class="compact-stat__num">{{ total.toLocaleString() }}</span>
            <span class="compact-stat__label">积分池</span>
          </div>
          <div class="compact-stat__divider" aria-hidden="true"></div>
          <div class="compact-stat">
            <span class="compact-stat__num">{{ totalUsers.toLocaleString() }}</span>
            <span class="compact-stat__label">人参与</span>
          </div>
        </div>
        <div class="compact-time" v-if="remainCompact">
          <Icon :size="12" name="clock" />
          {{ remainCompact }}
        </div>
      </div>
      <button class="hero-chevron" type="button" aria-label="展开" @click="toggleExpand">
        <Icon :size="18" name="chevron-down" />
      </button>
    </div>

    <!-- ============ 展开态 ============ -->
    <template v-else>
      <header class="hero-head">
        <span class="hero-tag">
          <span class="dot" :class="{ pulse: emitting }"></span>
          今日竞猜
        </span>
        <button class="hero-chevron" type="button" aria-label="收起" @click="toggleExpand">
          <Icon :size="18" name="chevron-up" />
        </button>
      </header>

      <h2 class="hero-title">{{ guessStore.guess.title }}</h2>

      <!-- 数据栏：两个主数据左对齐，倒计时右对齐 -->
      <div class="hero-stats">
        <div class="stat-group">
          <div class="stat">
            <span class="stat__num">{{ total.toLocaleString() }}</span>
            <span class="stat__label">积分池</span>
          </div>
          <div class="stat-divider" aria-hidden="true"></div>
          <div class="stat">
            <span class="stat__num">{{ totalUsers.toLocaleString() }}</span>
            <span class="stat__label">人参与</span>
          </div>
        </div>
        <div class="stat-time" v-if="remainText">
          <Icon :size="13" name="clock" />
          {{ remainText }}
        </div>
      </div>

      <!-- 选项进度条 -->
      <div class="hero-bars">
        <template v-for="(opt, i) in (guessStore.guess.options || [])" :key="opt.id">
          <div class="bar-row">
            <div class="bar-label">
              <span class="idx">{{ ['A','B','C','D','E','F','G','H'][i] }}</span>
              <span class="text">{{ opt.label }}</span>
              <span class="bar-pct">{{ fmtPct(getOptionPct(opt)) }}</span>
              <span v-if="guessStore.guess?.winning_option_id === opt.id" class="tag tag--gold">冠军</span>
              <span v-if="guessStore.myBet && guessStore.myBet.option_id === opt.id" class="tag tag--you">已押</span>
            </div>
            <div class="bar-outer">
              <div
                class="bar-fill"
                :class="{
                  'is-winner': guessStore.guess?.winning_option_id === opt.id,
                  'is-you': guessStore.myBet?.option_id === opt.id,
                }"
                :style="{ width: getOptionPct(opt) + '%' }"
              />
            </div>
          </div>
        </template>
      </div>

      <!-- 底部操作区 -->
      <footer class="hero-footer">
        <span v-if="guessStore.myBet && guessStore.myBet.skipped" class="hint">今天已跳过 · 明天再来</span>
        <span v-else-if="guessStore.myBet && guessStore.myBet.amount > 0" class="hint">已押 {{ guessStore.myBet.amount }} 积分</span>
        <span v-else class="hint">登录押注 · 冠军瓜分奖池</span>
        <span class="cta">
          立即押注
          <Icon :size="14" name="chevron-right" />
        </span>
      </footer>
    </template>
  </section>
</template>

<style scoped>
.guess-hero {
  position: relative;
  overflow: hidden;
  border-radius: 18px;
  padding: 16px 18px;
  margin: 4px 0 16px;
  color: #fff;
  cursor: pointer;
  background: linear-gradient(135deg, #5856d6 0%, #007aff 100%);
  box-shadow: 0 6px 16px rgba(88, 86, 214, 0.28);
  isolation: isolate;
  transition: padding 0.25s var(--ease-apple), box-shadow 0.25s var(--ease-apple);
}
.guess-hero:hover {
  box-shadow: 0 10px 24px rgba(88, 86, 214, 0.32);
}
.guess-hero.is-expanded {
  padding: 18px 20px 20px;
}

/* ============ 背景装饰圆 ============ */
.hero-decor {
  position: absolute;
  border-radius: 50%;
  z-index: -1;
  pointer-events: none;
}
.decor-1 {
  width: 200px;
  height: 200px;
  background: rgba(255, 255, 255, 0.08);
  top: -80px;
  right: -60px;
}
.decor-2 {
  width: 140px;
  height: 140px;
  background: rgba(255, 255, 255, 0.05);
  bottom: -40px;
  left: -30px;
}

/* ============ 展开/收起按钮 ============ */
.hero-chevron {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.22);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.3);
  color: #fff;
  cursor: pointer;
  flex-shrink: 0;
  transition: transform 0.2s var(--ease-apple), background 0.2s var(--ease-apple);
}
.hero-chevron:hover {
  background: rgba(255, 255, 255, 0.32);
}
.hero-chevron:active {
  transform: scale(0.92);
}
.hero-chevron :deep(svg) {
  width: 18px;
  height: 18px;
}

/* ============ 收起态 ============ */
.hero-compact {
  display: flex;
  align-items: center;
  gap: 14px;
}
.hero-compact__left {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
  flex: 1;
}
.hero-compact__right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  flex-shrink: 0;
}

/* 两个大数字并排 */
.compact-stats {
  display: flex;
  align-items: center;
  gap: 10px;
}
.compact-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  line-height: 1.1;
  min-width: 52px;
}
.compact-stat__num {
  font-size: 15px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: #fff;
}
.compact-stat__label {
  font-size: 10.5px;
  color: rgba(255, 255, 255, 0.6);
  margin-top: 2px;
}
.compact-stat__divider {
  width: 1px;
  height: 22px;
  background: rgba(255, 255, 255, 0.25);
}
.compact-time {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  opacity: 0.75;
  font-variant-numeric: tabular-nums;
}

/* ============ 标签 ============ */
.hero-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.hero-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  font-weight: 600;
  font-size: 12px;
}
.hero-tag .dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #ffd60a;
}
.hero-tag .dot.pulse {
  animation: pulsing 1.6s infinite;
}
@keyframes pulsing {
  0%   { box-shadow: 0 0 0 0 rgba(255, 214, 10, 0.6); }
  70%  { box-shadow: 0 0 0 8px rgba(255, 214, 10, 0); }
  100% { box-shadow: 0 0 0 0 rgba(255, 214, 10, 0); }
}

/* ============ 标题 ============ */
.hero-title {
  margin: 0 0 14px;
  font-size: 20px;
  font-weight: 700;
  line-height: 1.35;
  letter-spacing: -0.01em;
}
.hero-title--compact {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

/* ============ 数据栏（展开态） ============ */
.hero-stats {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  padding-bottom: 14px;
  border-bottom: 0.5px solid rgba(255, 255, 255, 0.15);
}
.stat-group {
  display: flex;
  align-items: center;
  gap: 14px;
}
.stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  line-height: 1.1;
  min-width: 60px;
}
.stat__num {
  font-size: 20px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: #fff;
}
.stat__label {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.65);
  margin-top: 4px;
}
.stat-divider {
  width: 1px;
  height: 28px;
  background: rgba(255, 255, 255, 0.2);
}
.stat-time {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  opacity: 0.8;
  font-variant-numeric: tabular-nums;
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
}

/* ============ 选项进度条 ============ */
.hero-bars {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 4px 2px;
}
.bar-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.bar-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
}
.bar-label .idx {
  display: inline-flex;
  width: 20px;
  height: 20px;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.18);
  border-radius: 6px;
  font-weight: 700;
  font-size: 11px;
  flex-shrink: 0;
}
.bar-label .text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  opacity: 0.95;
}
.bar-pct {
  font-size: 13px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  opacity: 0.9;
  flex-shrink: 0;
}
.tag {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 10.5px;
  font-weight: 700;
  flex-shrink: 0;
}
.tag--gold {
  background: #ffd60a;
  color: #1d1d1f;
}
.tag--you {
  background: rgba(255, 255, 255, 0.92);
  color: #5856d6;
}
.bar-outer {
  height: 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.18);
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  border-radius: 999px;
  background: #fff;
  transition: width 0.6s cubic-bezier(.2,.7,.2,1);
}
.bar-fill.is-you {
  background: #30d158;
}
.bar-fill.is-winner {
  background: #ffd60a;
}

/* ============ 底部操作区 ============ */
.hero-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 18px;
  padding-top: 14px;
  border-top: 0.5px solid rgba(255, 255, 255, 0.15);
}
.hero-footer .hint {
  font-size: 12px;
  opacity: 0.7;
}
.hero-footer .cta {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 10px 20px;
  border-radius: 999px;
  background: #fff;
  color: #5856d6;
  font-weight: 700;
  font-size: 14px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.18);
  transition: transform 0.15s var(--ease-apple), box-shadow 0.15s var(--ease-apple);
}
.hero-footer .cta:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.22);
}
.hero-footer .cta:active {
  transform: translateY(0) scale(0.97);
}
</style>
