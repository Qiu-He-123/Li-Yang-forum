<script setup lang="ts">
/**
 * 今日竞猜押注弹窗。
 *
 * 打开时机由全局"启动弹窗编排器"管理（公告→押注→新手教程），
 * 即 uiStore.guessPopupOpen。同时兼容首页焦点区 TodayGuessHero 的
 * 手动点击（通过 window.__TRY_OPEN_GUESS_POPUP__ 置 true）。
 *
 * 关闭方式有三种：
 * 1) 用户完成押注 confirmBet() → close()
 * 2) 用户点「今日不押注」 skipToday() → close()
 * 3) 用户点右上角 × / 点遮罩空白 → close()
 *
 * 任意一种关闭都会把 uiStore.guessPopupDone=true，让编排器继续
 * 往下走（弹新手教程 / 或结束序列）。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import Icon from '../native/Icon.vue'
import { useGuessStore } from '../../stores/guess'
import { useSessionStore } from '../../stores/session'
import { useUIStore } from '../../stores/ui'
import { useCoinStore } from '../../stores/coin'
import { toast } from '../../components/native/Toast'

const guessStore = useGuessStore()
const sessionStore = useSessionStore()
const uiStore = useUIStore()
const coinStore = useCoinStore()
const { guess, myBet, loading } = storeToRefs(guessStore)
const { guessPopupOpen } = storeToRefs(uiStore)

const optionId = ref<number | null>(null)
const amount = ref(50)
const submitting = ref(false)
const errMsg = ref('')

const presetAmounts = [10, 50, 100, 500, 1000]

const balance = computed(() => coinStore.balance)
const total = computed(() => guess.value?.total_points ?? 0)
const options = computed(() => guess.value?.options ?? [])

/** 未登录游客：弹窗照常展示，但确认按钮改为「登录即可参与」，点击前往登录 */
const isGuest = computed(() => !sessionStore.userId)

// ——— UI 显隐/禁用态辅助 ———
/**
 * 积分不足：当前用户余额 < 选择的押注金额，或余额为 0 都算"不足"。
 * - 为 0 时，不管选多少都会不足，这时顶部红色警告条也该出现。
 * （游客不参与此项判断：游客按钮恒可点，点击即去登录）
 */
const balanceInsufficient = computed(() => balance.value <= 0 || amount.value > balance.value)

/**
 * 确认押注按钮是否可用：
 *  - 游客：恒可点（点击跳转登录），仅提交/加载中禁用
 *  - 登录用户：需要 没截止 / 选了选项 / 金额合法且余额充足
 */
const confirmDisabled = computed(() => {
  if (submitting.value || loading.value) return true
  if (isGuest.value) return false
  if (expired.value) return true
  if (optionId.value == null) return true
  if (balanceInsufficient.value) return true
  if (amount.value < 10 || amount.value > 10000) return true
  return false
})

// 为每个选项生成 A/B/C 标签字母
function letterFor(index: number) {
  return ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'][index] ?? ''
}

const deadlineTs = computed(() => {
  if (!guess.value?.deadline) return 0
  return new Date(guess.value.deadline.replace('Z', '')).getTime()
})
const expired = computed(() => deadlineTs.value > 0 && deadlineTs.value <= Date.now())

const remainText = ref('')
let timer: number | null = null
function updateRemain() {
  if (!deadlineTs.value) return
  const d = deadlineTs.value - Date.now()
  if (d <= 0) { remainText.value = '押注已截止'; return }
  const h = Math.floor(d / 3600000)
  const m = Math.floor((d % 3600000) / 60000)
  const s = Math.floor((d % 60000) / 1000)
  remainText.value = `距截止 ${h}时${m}分${s}秒`
}
onMounted(() => { timer = window.setInterval(updateRemain, 1000); updateRemain() })
onBeforeUnmount(() => { if (timer) window.clearInterval(timer) })

watch(
  () => guessPopupOpen.value,
  (o) => {
    if (o) {
      optionId.value = null
      amount.value = 50
      errMsg.value = ''
      uiStore.guessPopupDone = false
      // 游客没有余额接口，跳过拉取避免 401；登录用户再同步余额
      if (!isGuest.value) void coinStore.loadBalance()
    }
  },
  { immediate: true },
)

function close() {
  guessStore.dismissPopup()
  uiStore.guessPopupOpen = false
  uiStore.guessPopupDone = true
}

function pickPreset(a: number) {
  amount.value = a
}
function addAmount(v: number) {
  const next = Math.min(10000, Math.max(10, amount.value + v))
  amount.value = next
}
function allIn() {
  amount.value = Math.min(10000, Math.max(10, balance.value))
}

async function confirmBet() {
  if (isGuest.value) {
    // 游客：不押注，直接关掉弹窗并跳转登录
    close()
    uiStore.openAuthDialog()
    return
  }
  if (!guess.value) return
  if (optionId.value == null) { errMsg.value = '请先选择押注的选项'; return }
  if (expired.value) { errMsg.value = '押注已截止'; return }
  if (amount.value > balance.value) { errMsg.value = `积分不足（当前 ${balance.value}）`; return }
  if (amount.value < 10 || amount.value > 10000) { errMsg.value = '押注金额必须在 10 - 10000 之间'; return }

  try {
    submitting.value = true
    errMsg.value = ''
    await guessStore.bet(optionId.value, amount.value)
    await coinStore.loadBalance()
    submitting.value = false
    close()
    toast.success(`押注成功！已押 ${amount.value.toLocaleString()} 积分`)
  } catch (err) {
    submitting.value = false
    errMsg.value = (err as Error).message || '押注失败'
  }
}

async function skipToday() {
  if (isGuest.value) { close(); return }
  try {
    submitting.value = true
    await guessStore.skip()
    submitting.value = false
    close()
  } catch (err) {
    submitting.value = false
    errMsg.value = (err as Error).message || '操作失败'
  }
}

function pct(opt: { total_points: number }) {
  if (total.value <= 0) return 0
  return Math.round((opt.total_points / total.value) * 1000) / 10
}
</script>

<template>
  <Teleport to="body">
    <div v-if="guessPopupOpen" class="guess-mask" @click.self="close">
      <div class="guess-modal" role="dialog" aria-modal="true">
        <!-- 右上角小面积紫红光晕（点缀用，不是大面积糊底） -->
        <div class="modal-bg">
          <div class="m-glow accent" />
        </div>

        <header class="modal-head">
          <div class="modal-title-row">
            <span class="brand">🔥 今日竞猜</span>
            <button class="close-btn" @click="close" aria-label="关闭">
              <Icon :size="16" name="x" />
            </button>
          </div>
          <h2 class="modal-title">{{ guess?.title || '今日竞猜即将上线' }}</h2>
          <div class="modal-sub">
            <span v-if="remainText">{{ remainText }}</span>
            <span>·</span>
            <span>奖池 {{ (guess?.total_points ?? 0).toLocaleString() }} 积分</span>
            <span>·</span>
            <span>{{ guess?.total_users ?? 0 }} 人参与</span>
          </div>
        </header>

        <section v-if="guess?.description" class="modal-desc">
          <Icon :size="14" name="info" />
          <div>{{ guess.description }}</div>
        </section>

        <section class="opts" v-if="guess">
          <h3 class="sec-title">选择押注对象</h3>
          <div
            v-for="(opt, i) in options"
            :key="opt.id"
            class="opt"
            :class="{
              active: optionId === opt.id,
              expired: expired,
              winner: guess.winning_option_id === opt.id,
            }"
            @click="!expired && !submitting && (optionId = opt.id)"
          >
            <div class="opt-selbar" aria-hidden="true"></div>
            <div class="opt-inner">
              <div class="opt-row">
                <div class="opt-left">
                  <span class="tag">{{ letterFor(i) }}</span>
                  <span class="lbl">{{ opt.label }}</span>
                </div>
                <div class="opt-right">
                  <span class="pts">{{ opt.total_points.toLocaleString() }} pts</span>
                  <span class="pct">{{ pct(opt) }}%</span>
                </div>
              </div>
              <div class="bar"><div class="bar-in" :style="{ width: pct(opt) + '%' }" /></div>
              <div class="foot-note">{{ opt.total_users }} 人押这个</div>
            </div>
          </div>
        </section>

        <section class="amount">
          <div class="sec-title-row">
            <h3 class="sec-title">押注积分</h3>
            <div class="balance">
              <Icon :size="14" name="coins" />
              <template v-if="isGuest">登录后可查看积分</template>
              <template v-else>我的：<b>{{ balance.toLocaleString() }}</b></template>
            </div>
          </div>

          <div class="preset-row">
            <button
              v-for="p in presetAmounts"
              :key="p"
              class="preset-btn"
              :class="{ active: amount === p }"
              @click="pickPreset(p)"
            >{{ p }}</button>
            <button class="preset-btn allin" @click="allIn">All-in</button>
          </div>

          <!-- 积分不足警告条（在快捷按钮和输入框之间，余额不足时显示；游客不显示） -->
          <div v-if="balanceInsufficient && !isGuest" class="balance-warn" role="alert">
            <Icon :size="14" name="triangle-alert" class="warn-icon" />
            <span>积分不足，无法下注（当前 {{ balance.toLocaleString() }}）</span>
          </div>

          <div class="amount-editor" :class="{ 'has-warn': balanceInsufficient }">
            <button class="step-btn" @click="addAmount(-50)" aria-label="减少">
              <Icon :size="16" name="minus" />
            </button>
            <input
              v-model.number="amount"
              type="number"
              min="10"
              max="10000"
              class="amount-input"
            />
            <button class="step-btn" @click="addAmount(50)" aria-label="增加">
              <Icon :size="16" name="plus" />
            </button>
          </div>

          <p v-if="errMsg" class="err-msg">{{ errMsg }}</p>
        </section>

        <footer class="modal-actions">
          <button class="btn skip" :disabled="submitting" @click="skipToday">
            今日不押注
          </button>
          <button
            class="btn confirm"
            :class="{ disabled: confirmDisabled }"
            :disabled="confirmDisabled"
            @click="confirmBet"
          >
            <template v-if="loading || submitting">
              <span class="spinner"></span>
              处理中...
            </template>
            <template v-else>
              <template v-if="isGuest">登录即可参与</template>
              <template v-else>确认押注 · {{ amount.toLocaleString() }}</template>
            </template>
          </button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* ============================================================
   今日竞猜弹窗 · 去除"AI 廉价感"改造
   - 深浅对比：深紫黑打底 + 局部弱光，不做整块艳渐变糊脸
   - 圆角分级：弹窗 20px / 内部卡片 12px / 按钮 14px
   - 描边替代发光：1px 内描边 + 真实阴影，不用模糊外发光
   - 信息层级：字重/字号/透明度三重区分，文字全去发光
   ============================================================ */

/* ---------- 遮罩 ---------- */
.guess-mask {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(10, 4, 20, 0.72);
  backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
  animation: fadein 0.2s ease;
}
@keyframes fadein { from { opacity: 0 } to { opacity: 1 } }

/* ---------- 弹窗本体 ---------- */
.guess-modal {
  position: relative;
  width: 100%; max-width: 420px;
  border-radius: 20px;                     /* 外框圆角 20 */
  background: #181226;                     /* 深紫黑实底（色值按规范） */
  color: #fff;
  padding: 18px 18px 16px;
  overflow: hidden;
  /* 1px 内描边 + 真实阴影，不要模糊外发光 */
  border: 1px solid #443460;
  box-shadow: 0 8px 24px rgba(0,0,0,0.55), 0 20px 60px rgba(0,0,0,0.55);
  animation: popup 0.26s cubic-bezier(.2,1.2,.3,1);
}
@keyframes popup { from { transform: scale(.92); opacity: 0 } to { transform: scale(1); opacity: 1 } }

/* 右上角小面积弱光晕点缀，不是大面积糊底 */
.modal-bg { position: absolute; inset: 0; pointer-events: none; overflow: hidden; border-radius: 20px; }
.m-glow {
  position: absolute;
  width: 280px; height: 280px;
  border-radius: 50%;
  filter: blur(60px);
  opacity: 0.35;
  background: radial-gradient(circle at 30% 30%, #7a3fa8 0%, #c2426a 60%, transparent 70%);
  top: -140px; right: -120px;
}

/* ---------- 头部 ---------- */
.modal-head { position: relative; }
.modal-title-row { display: flex; align-items: center; justify-content: space-between; }

/* 今日竞猜标签：实色暗金底，去发光 */
.brand {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 10px; border-radius: 999px;
  background: #6b531f;
  color: #f2d98b;
  font-weight: 700; font-size: 12px;
  border: 1px solid #886830;
}

.close-btn {
  width: 28px; height: 28px; border-radius: 50%;
  background: #2a2040;      /* 圆形实底，不做虚光 */
  color: #cbc3e6;
  display: inline-flex; align-items: center; justify-content: center;
  border: 1px solid #3a2e55;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}
.close-btn:hover { background: #352a52; color: #fff; }

/* 大标题 22px 字重 700 */
.modal-title { margin: 10px 0 6px; font-size: 22px; font-weight: 700; letter-spacing: 0.2px; color: #ffffff; }

/* 截止时间等次要信息：字重 400 透明度降，拉开层级 */
.modal-sub {
  font-size: 12px;
  font-weight: 400;
  opacity: 0.62;
  color: #cfc7ff;
  display: flex; gap: 6px; flex-wrap: wrap;
}

/* 描述条 */
.modal-desc {
  margin-top: 12px;
  display: flex; gap: 8px;
  padding: 10px 12px;
  border-radius: 12px;                    /* 内部卡片圆角 12 */
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.06);
  font-size: 13px; line-height: 1.6;
  color: #cbc3e6;
  white-space: pre-wrap;
}

/* 区块标题 */
.sec-title {
  font-size: 13px; font-weight: 700;
  color: #e8e1ff;
  margin: 0 0 8px;
  letter-spacing: 0.2px;
}
.sec-title-row { display: flex; align-items: center; justify-content: space-between; }

/* 余额：字号加大 13px，右对齐更清晰 */
.balance {
  font-size: 13px;
  display: inline-flex; align-items: center; gap: 4px;
  color: #cbc3e6;
}
.balance b { color: #f2d98b; font-weight: 700; font-variant-numeric: tabular-nums; }

/* ============================================================
   A/B/C 选项
   ============================================================ */
.opts { margin: 14px 0 6px; display: flex; flex-direction: column; gap: 10px; }

.opt {
  position: relative;
  border-radius: 12px;                    /* 内部卡片圆角 12 */
  background: #241D38;                    /* 选项默认底色 规范色值 */
  border: 1px solid #3E3258;              /* 默认弱描边 */
  cursor: pointer;
  overflow: hidden;
  transition: border-color 0.15s ease, background 0.15s ease, transform 0.12s ease;
}
.opt:hover:not(.expired) { border-color: #4e3f72; background: #292140; }

/* 左侧 4px 金色竖条：只在 active / winner 时显示，默认透明 */
.opt-selbar {
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 4px;
  background: transparent;
  border-radius: 4px 0 0 4px;
  transition: background 0.15s ease;
}
.opt.active .opt-selbar { background: #D4AF58; }  /* 选中标记金色 规范 */
.opt.winner .opt-selbar { background: #f2d98b; }

/* 选中状态：底色提亮，描边变金，不再用粗暴的黄框+糊 */
.opt.active {
  border-color: #94722E;
  background: #2e2442;
}
.opt.winner {
  border-color: #c9a75a;
  background: linear-gradient(90deg, rgba(212,175,88,0.18), rgba(36,29,56,1));
}
.opt.expired { cursor: not-allowed; opacity: 0.7; }

.opt-inner { padding: 10px 12px 10px 14px; }
.opt-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.opt-left { display: inline-flex; align-items: center; gap: 10px; }

/* A/B/C 小胶囊：深色胶囊（不是原浅灰方块） */
.opt-left .tag {
  min-width: 22px; height: 22px;
  padding: 0 7px;
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: 999px;
  background: #1a1328;
  border: 1px solid #362a52;
  color: #c2b8e4;
  font-weight: 700;
  font-size: 12px;
  line-height: 1;
}
.opt-left .lbl { font-size: 17px; font-weight: 600; color: #f2ecff; }  /* 选项标题 17px */

/* 右侧 pts 弱化 + 百分比主色化（不再一样重） */
.opt-right {
  font-size: 12px;
  display: inline-flex;
  gap: 10px;
  align-items: baseline;
}
.opt-right .pts { color: #9a90c2; font-variant-numeric: tabular-nums; opacity: 0.9; }   /* pts 弱化 */
.opt-right .pct { color: #D4AF58; font-weight: 700; }                                  /* 百分比主色 */

/* 进度条：细实色，不要模糊渐变 */
.bar {
  height: 6px;
  border-radius: 999px;
  background: rgba(255,255,255,0.06);
  overflow: hidden;
}
.bar-in {
  height: 100%;
  border-radius: 999px;
  background: #D4AF58;    /* 规范金色实色条 */
  transition: width 0.5s ease;
}
.foot-note {
  margin-top: 5px;
  font-size: 13px;
  color: #8c82b0;
  opacity: 0.85;
}

/* ============================================================
   下注区 + 警告条
   ============================================================ */
.amount { margin-top: 14px; }

/* 快捷按钮组：深色描边，选中金色实底（不刺眼亮黄） */
.preset-row { display: flex; gap: 8px; flex-wrap: wrap; }
.preset-btn {
  padding: 6px 12px;
  border-radius: 12px;                     /* 圆角 14px 规范 → 视觉上 12 与输入框 12 统一 */
  border: 1px solid #3a2e55;
  background: #241D38;
  color: #e5deff;
  cursor: pointer;
  font-weight: 600;
  font-size: 13px;
  transition: background 0.14s ease, border-color 0.14s ease, color 0.14s ease, transform 0.1s ease;
}
.preset-btn:active { transform: translateY(1px); }
.preset-btn:hover { background: #2a2143; border-color: #4b3c6d; }
.preset-btn.active {
  background: #D4AF58;                    /* 规范选中金色填充，不刺眼亮黄 */
  color: #211836;
  border-color: #D4AF58;
  font-weight: 700;
}
.preset-btn.allin {
  background: transparent;
  border-color: #D12C4E;                  /* 规范低饱和红，不艳粉 */
  color: #ff8fa0;
}
.preset-btn.allin:hover { background: rgba(209, 44, 78, 0.12); }

/* ——— 重点：积分不足警告条 ——— */
.balance-warn {
  margin-top: 10px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  border-radius: 12px;
  background: rgba(230, 55, 75, 0.20);   /* 规范警告条背景 */
  color: #FF6472;                         /* 规范警告文字 */
  border: 1px solid rgba(255,100,114,0.25);
  font-size: 15px;                        /* 规范警告文字 15px */
  font-weight: 500;
  width: 100%;
  box-sizing: border-box;
}
.balance-warn .warn-icon { flex-shrink: 0; margin-top: 1px; }

/* 输入框：深色底色 + 边框区分，不做渐变 */
.amount-editor {
  margin-top: 10px;
  display: flex;
  align-items: center;
  background: #201836;
  border: 1px solid #3a2e55;
  border-radius: 12px;
  padding: 4px;
  transition: border-color 0.15s ease;
}
.amount-editor.has-warn {
  border-color: rgba(255,100,114,0.45);
}
.step-btn {
  width: 40px; height: 40px;
  border-radius: 12px;
  background: #292041;
  color: #d7cfff;
  border: 1px solid #3a2e55;
  cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center;
  transition: background 0.14s ease, color 0.14s ease;
}
.step-btn:hover { background: #332852; color: #fff; }

.amount-input {
  flex: 1;
  height: 40px;
  background: transparent;
  border: none;
  outline: none;
  color: #F4E4B5;                         /* 数字用偏金，不刺眼黄 */
  text-align: center;
  font-size: 20px;                        /* 数字加大加粗 */
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.amount-input::placeholder { color: rgba(255,255,255,0.35); }

/* 底部错误小字（兜底错误提示，不是警告条的主要提示） */
.err-msg {
  color: #ff7a86;
  font-size: 12px;
  margin: 6px 2px 0;
}

/* ============================================================
   底部双按钮
   ============================================================ */
.modal-actions {
  margin-top: 16px;
  display: flex;
  gap: 10px;
}
.btn {
  flex: 1;
  padding: 12px 14px;
  border-radius: 14px;                   /* 按钮圆角 14 规范 */
  border: 1px solid transparent;
  font-weight: 700;
  font-size: 14px;
  cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  transition: transform 0.12s ease, filter 0.12s ease, background 0.15s ease, opacity 0.15s ease;
  user-select: none;
}
.btn:active { transform: translateY(1px); }

/* 左侧「今日不押注」镂空按钮，视觉降级 */
.btn.skip {
  background: transparent;
  color: #a9b6ff;
  border: 1px solid rgba(120, 145, 255, 0.45);  /* 淡蓝色描边，镂空 */
}
.btn.skip:hover { background: rgba(120, 145, 255, 0.10); }
.btn.skip:disabled { opacity: 0.5; cursor: not-allowed; }

/* 右侧「确认押注」主按钮：规范的低饱和金橙渐变 */
.btn.confirm {
  background: linear-gradient(135deg, #B8862F 0%, #E6952E 100%);
  color: #1e1630;
  box-shadow: 0 8px 20px rgba(230, 149, 46, 0.24);
  border-color: transparent;
}
.btn.confirm:hover { filter: brightness(1.04); }

/* 禁用态（积分不足 / 没选项 / 截止 / 提交中）：置灰 + 降透明 + 不可点 */
.btn.confirm:disabled,
.btn.confirm.disabled {
  background: #3b3158;
  color: #8479a5;
  box-shadow: none;
  opacity: 0.7;
  cursor: not-allowed;
  filter: none;
}

.spinner {
  width: 14px; height: 14px; border-radius: 50%;
  border: 2px solid rgba(0,0,0,0.2);
  border-top-color: rgba(0,0,0,0.8);
  animation: spin 0.8s linear infinite;
}
.btn.confirm:disabled .spinner,
.btn.confirm.disabled .spinner {
  border-color: rgba(255,255,255,0.15);
  border-top-color: rgba(255,255,255,0.45);
}
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 420px) {
  .guess-mask { padding: 16px 12px; }
}
</style>
