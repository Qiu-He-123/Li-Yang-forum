<script setup lang="ts">
/**
 * 抽奖中心（提现改抽奖 / 用户端）
 * - 交易币兑换抽奖券 → 消耗券抽奖
 * - 盲盒开箱动画（GSAP）：抖动→开盖→奖品弹出（多巴胺感）
 * - 抽中后可「领取」或「看广告抽数量」（至多 max_ad_times 次，单次数量不累计）
 * - 领取后提示添加管理员微信兑付
 */
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { gsap } from 'gsap'

import { Icon } from '../../components/native'
import { toast } from '../../components/native/Toast'
import {
  getWallet, lotteryClaim, lotteryDraw, lotteryExchange, lotteryMy, lotteryPool, lotteryAdGrant,
  type LotteryInventoryItem, type LotteryPrize,
} from '../../api/order'

const router = useRouter()
const loading = ref(true)

const enabled = ref(true)
const ticketRate = ref(1)
const drawCost = ref(1)
const adminWechat = ref('')
const prizes = ref<LotteryPrize[]>([])

const ticketQty = ref(0)
const totalDraws = ref(0)
const balance = ref<number | null>(null) // 交易币余额
const inventory = ref<LotteryInventoryItem[]>([])

// 兑换
const exchangeVisible = ref(false)
const exchangeCount = ref(1)
const exchanging = ref(false)

// 抽奖动画状态
const drawing = ref(false)
const stage = ref<'idle' | 'shaking' | 'opening' | 'result'>('idle')
const current = ref<{
  draw_id: number
  prize: LotteryPrize
  base_qty: number
  total_qty: number
  ad_times_left: number
  ad_qty_granted: number
} | null>(null)

const claimedDialog = ref(false)
const claimedInfo = reactive({ qty: 0, claimed: false })

async function loadAll() {
  loading.value = true
  try {
    const [poolRes, myRes] = await Promise.all([lotteryPool(), lotteryMy()])
    const pool = poolRes.data.data
    enabled.value = pool.enabled
    ticketRate.value = pool.ticket_rate
    drawCost.value = pool.draw_cost || 1
    adminWechat.value = pool.admin_wechat
    prizes.value = pool.prizes || []
    ticketQty.value = pool.my?.ticket_qty ?? 0
    totalDraws.value = pool.my?.total_draws ?? 0
    inventory.value = myRes.data.data.inventory || []
  } catch (e) {
    toast.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

async function loadBalance() {
  try {
    const { data } = await getWallet()
    balance.value = data.data.balance
  } catch { /* ignore */ }
}

const canDraw = computed(() => !drawing.value && enabled.value && ticketQty.value >= drawCost.value)

function openExchange() {
  exchangeVisible.value = true
  exchangeCount.value = 1
}
const exchangeCost = computed(() => exchangeCount.value * ticketRate.value)
const exchangeCanAfford = computed(() => balance.value == null || (balance.value ?? 0) >= exchangeCost.value)

async function submitExchange() {
  if (exchanging.value) return
  exchanging.value = true
  try {
    const n = Math.max(1, Math.floor(exchangeCount.value))
    const { data } = await lotteryExchange(n)
    ticketQty.value = data.data.ticket_qty
    exchangeVisible.value = false
    toast.success(`成功兑换 ${data.data.count} 张抽奖券`)
    await loadBalance()
  } catch (e) {
    toast.error((e as Error).message)
  } finally {
    exchanging.value = false
  }
}

// ==================== 抽奖动画 ====================
const boxRef = ref<HTMLElement | null>(null)
const boxInnerRef = ref<HTMLElement | null>(null)
const lidRef = ref<HTMLElement | null>(null)
const prizeRevealRef = ref<HTMLElement | null>(null)

function playReveal() {
  const el = boxRef.value
  if (!el) return null
  const ctx = gsap.context(() => {
    const tl = gsap.timeline()
    // 1. 摇晃 紧张感
    tl.to('.lt-box', { rotation: -18, x: -8, duration: 0.10, ease: 'power1.inOut' })
      .to('.lt-box', { rotation: 20, x: 9, duration: 0.12, ease: 'power1.inOut' })
      .to('.lt-box', { rotation: -14, x: -7, duration: 0.10, ease: 'power1.inOut' })
      .to('.lt-box', { rotation: 12, x: 6, duration: 0.10, ease: 'power1.inOut' })
      .to('.lt-box', { rotation: 0, x: 0, duration: 0.08, ease: 'back.out(3)' })
      // 2. 光晕脉冲
      .fromTo('.lt-box-glow', { opacity: 0.15, scale: 0.9 }, { opacity: 0.85, scale: 1.15, duration: 0.28, yoyo: true, repeat: 1, ease: 'sine.inOut' })
  }, el)
  return ctx
}

function startDraw() {
  if (!canDraw.value) { toast.warning('抽奖券不足，请先兑换'); return }
  drawing.value = true
  lotteryDraw()
    .then(({ data }) => {
      const d = data.data
      ticketQty.value = d.ticket_qty
      current.value = {
        draw_id: d.draw_id,
        prize: d.prize,
        base_qty: d.base_qty,
        total_qty: d.base_qty,
        ad_times_left: d.ad_times_left,
        ad_qty_granted: 0,
      }
      stage.value = 'shaking'
      // 重置动画元素状态
      nextTick(() => {
        const ctx = playReveal()
        gsap.delayedCall(1.2, () => {
          if (ctx) ctx.revert()
          openBox()
        })
      })
    })
    .catch((e) => {
      drawing.value = false
      toast.error((e as Error).message)
    })
}

function openBox() {
  stage.value = 'opening'
  const tl = gsap.timeline({
    onComplete: () => {
      stage.value = 'result'
      drawing.value = false
      totalDraws.value += 1
      burstConfetti()
    },
  })
  tl.to('.lt-lid', { y: -70, rotation: 25, opacity: 0, duration: 0.5, ease: 'back.in(1.5)' }, 0)
    .to('.lt-box', { scale: 0.6, opacity: 0.6, duration: 0.35, ease: 'power2.in' }, 0.35)
  // 奖品从盒中弹出
  tl.fromTo('.lt-prize-reveal', { y: 60, scale: 0.2, opacity: 0 }, { y: -30, scale: 1.15, opacity: 1, duration: 0.6, ease: 'back.out(2.2)', zIndex: 20 }, 0.6)
    .to('.lt-prize-reveal', { scale: 1, y: 0, duration: 0.35, ease: 'power2.out' }, 1.2)
}

// 弹射粒子（开箱紧张感转兴奋）
function burstConfetti() {
  if (!boxRef.value) return
  const el = boxRef.value
  const colors = ['#ffd60a', '#ff9f0a', '#ff453a', '#ff375f', '#5e5ce6', '#30d158']
  const tl = gsap.timeline()
  for (let i = 0; i < 26; i++) {
    const p = document.createElement('div')
    p.className = 'lt-confetti'
    p.style.background = colors[i % colors.length]
    p.style.left = '50%'
    p.style.top = '50%'
    p.style.width = `${6 + Math.random() * 8}px`
    p.style.height = `${6 + Math.random() * 10}px`
    el.appendChild(p)
    const angle = (Math.PI * 2 * i) / 26
    const dist = 120 + Math.random() * 140
    tl.fromTo(
      p,
      { x: 0, y: 0, opacity: 1, rotation: 0, scale: 1 },
      { x: Math.cos(angle) * dist, y: Math.sin(angle) * dist - 30, opacity: 0, rotation: Math.random() * 360, scale: 0.4, duration: 0.9 + Math.random() * 0.5, ease: 'power2.out' },
      i * 0.012,
    )
  }
  gsap.delayedCall(1.6, () => {
    el.querySelectorAll('.lt-confetti').forEach((n) => n.remove())
  })
}

// ==================== 看广告抽数量 ====================
const adBusy = ref(false)
function watchAd() {
  if (!current.value || adBusy.value) return
  if (current.value.ad_times_left <= 0) { toast.info('本单看广告次数已用尽，单次抽取数量不可累计'); return }
  adBusy.value = true
  lotteryAdGrant(current.value.draw_id)
    .then(({ data }) => {
      if (current.value) {
        current.value.ad_times_left = data.data.ad_times_left
        current.value.ad_qty_granted = data.data.ad_qty_granted
        current.value.total_qty = data.data.total_qty
      }
      toast.success(`看广告成功！数量 +1，累计 ×${data.data.total_qty}`)
    })
    .catch((e) => toast.error((e as Error).message))
    .finally(() => { adBusy.value = false })
}

// ==================== 领取 ====================
const claiming = ref(false)
function doClaim() {
  if (!current.value || claiming.value) return
  claiming.value = true
  lotteryClaim(current.value.draw_id)
    .then(({ data }) => {
      claimedInfo.qty = data.data.qty
      claimedInfo.claimed = data.data.claimed
      if (data.data.admin_wechat) adminWechat.value = data.data.admin_wechat
      claimedDialog.value = true
      stage.value = 'idle'
      current.value = null
      void loadAll()
    })
    .catch((e) => toast.error((e as Error).message))
    .finally(() => { claiming.value = false })
}

function copyWechat() {
  if (!adminWechat.value) return
  try {
    void navigator.clipboard.writeText(adminWechat.value)
    toast.success('已复制管理员微信')
  } catch { /* ignore */ }
}

function goWallet() { router.push('/orders/wallet') }
function goBack() { router.push('/orders') }

function prizeImg(p: LotteryPrize | null) {
  return p?.image_url || ''
}

onMounted(() => { void loadAll(); void loadBalance() })
</script>

<template>
  <div class="lt-page">
    <header class="lt-header">
      <button class="lt-back" type="button" aria-label="返回" @click="goBack"><Icon name="chevron-left" :size="22" /></button>
      <h1>抽奖中心</h1>
      <button class="lt-wallet" type="button" @click="goWallet"><Icon name="wallet" :size="20" /></button>
    </header>

    <main v-if="!loading" class="lt-body">
      <!-- 顶部：券账户 -->
      <section class="lt-account">
        <div class="lt-acc-top">
          <span class="lt-acc-lab">我的抽奖券</span>
          <button class="lt-acc-exchange" type="button" @click="openExchange">交易币兑换 →</button>
        </div>
        <div class="lt-acc-num">{{ ticketQty }}</div>
        <div class="lt-acc-sub">
          <span>已抽 {{ totalDraws }} 次</span>
          <span>1券 = {{ drawCost }} 次抽取</span>
        </div>
      </section>

      <!-- 奖池预告 -->
      <section class="lt-pool">
        <h3>本期奖池</h3>
        <div class="lt-pool-row">
          <div v-for="p in prizes" :key="p.id" class="lt-pool-item">
            <div class="lt-pool-icon">
              <img v-if="p.image_url" :src="p.image_url" alt="" />
              <Icon v-else name="gift" :size="22" />
            </div>
            <div class="lt-pool-name">{{ p.name }}</div>
            <div class="lt-pool-range">{{ p.min_qty }}~{{ p.max_qty }}份</div>
          </div>
        </div>
      </section>

      <!-- 抽奖台 -->
      <section class="lt-stage">
        <div v-if="stage === 'idle'" class="lt-idle-tip">
          {{ enabled ? '消耗 1 张抽奖券，开箱领取惊喜' : '抽奖活动暂时关闭' }}
        </div>

        <div v-else ref="boxRef" class="lt-box-wrap">
          <!-- 开盖 -->
          <div ref="lidRef" class="lt-lid"><span>?</span></div>
          <!-- 盒身 -->
          <div ref="boxInnerRef" class="lt-box">
            <span class="lt-box-glow"></span>
            <div class="lt-box-face">🎁</div>
          </div>
          <!-- 中奖提示（开箱后覆盖） -->
          <div ref="prizeRevealRef" class="lt-prize-reveal" :class="{ 'is-show': stage === 'result' }">
            <div class="lt-prize-icon">
              <img v-if="current?.prize && prizeImg(current.prize)" :src="prizeImg(current.prize)" alt="" />
              <Icon v-else name="gift" :size="34" />
            </div>
            <div class="lt-prize-name">{{ current?.prize?.name }}</div>
            <div class="lt-prize-qty">×{{ current?.total_qty }}</div>
            <div v-if="stage === 'result'" class="lt-prize-tag">恭喜抽中！</div>
          </div>
        </div>

        <!-- 结果操作 -->
        <div v-if="stage === 'result' && current" class="lt-result-actions">
          <div v-if="current.ad_times_left > 0" class="lt-ad-hint">
            看广告可再抽数量（剩余 {{ current.ad_times_left }} 次，当前 ×{{ current.total_qty }}，单次不可累计）
          </div>
          <div class="lt-result-btns">
            <button type="button" class="lt-btn lt-btn--ad" :disabled="adBusy" @click="watchAd">📺 看广告抽数量</button>
            <button type="button" class="lt-btn lt-btn--claim" :disabled="claiming" @click="doClaim">🎉 领取</button>
          </div>
        </div>
      </section>

      <!-- 抽奖按钮 -->
      <section class="lt-drawbar">
        <button type="button" class="lt-btn lt-btn--draw" :disabled="!canDraw" @click="startDraw">
          {{ drawing ? '开箱中…' : `开一次 (${drawCost}券)` }}
        </button>
      </section>

      <!-- 我的中奖记录 -->
      <section class="lt-inv">
        <h3>我的中奖记录</h3>
        <div v-if="inventory.length === 0" class="lt-empty">还没有中奖记录，快去抽取吧～</div>
        <div v-for="it in inventory" :key="it.id" class="lt-inv-item">
          <div class="lt-inv-icon">
            <img v-if="it.image_url" :src="it.image_url" alt="" />
            <Icon v-else name="gift" :size="18" />
          </div>
          <div class="lt-inv-mid">
            <div class="lt-inv-name">{{ it.prize_name }}</div>
            <div class="lt-inv-time">{{ it.created_at }}</div>
          </div>
          <div class="lt-inv-right">
            <div class="lt-inv-qty">×{{ it.qty }}</div>
            <el-tag :type="it.status === 'claimed' ? 'success' : 'warning'" size="small">{{ it.status === 'claimed' ? '已领取' : '待领取' }}</el-tag>
          </div>
        </div>
      </section>
    </main>

    <!-- 兑换弹窗 -->
    <div v-if="exchangeVisible" class="lt-mask" @click.self="exchangeVisible = false">
      <div class="lt-sheet">
        <h3>交易币兑换抽奖券</h3>
        <p class="lt-sheet-hint">当前汇率：{{ ticketRate }} 交易币 = 1 抽奖券</p>
        <div class="lt-ex-input">
          <input v-model.number="exchangeCount" type="number" min="1" step="1" placeholder="兑换数量" />
          <span>张</span>
        </div>
        <div class="lt-ex-quick">
          <button v-for="q in [1, 5, 10, 50]" :key="q" type="button" @click="exchangeCount = q">{{ q }}</button>
        </div>
        <div class="lt-ex-preview">
          需支付 <b>{{ exchangeCost }}</b> 交易币（账户 {{ balance == null ? '—' : balance }}）
          <span v-if="!exchangeCanAfford" class="lt-ex-no">余额不足</span>
        </div>
        <button type="button" class="lt-btn lt-btn--primary" :disabled="exchanging || !exchangeCanAfford" @click="submitExchange">
          {{ exchanging ? '兑换中…' : '确认兑换' }}
        </button>
        <button type="button" class="lt-btn lt-btn--ghost" @click="exchangeVisible = false">取消</button>
      </div>
    </div>

    <!-- 领取成功 -->
    <el-dialog v-model="claimedDialog" title="领取成功" width="340px" :close-on-click-modal="false">
      <div class="lt-claimed">
        <div class="lt-claimed-icon">🎊</div>
        <div class="lt-claimed-title">已领取 {{ claimedInfo.qty }} 份奖励</div>
        <p class="lt-claimed-tip">请添加管理员微信完成兑付送达：</p>
        <div class="lt-claimed-wx" @click="copyWechat">{{ adminWechat || '（后台未配置）' }}<Icon name="link" :size="14" /></div>
      </div>
      <template #footer><el-button type="primary" @click="claimedDialog = false">知道了</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.lt-page { min-height: 100vh; background: linear-gradient(180deg,#fff3e0 0%,#f7f8fb 260px, #f7f8fb 100%); color: #1d1d1f; padding-bottom: 40px; }
.lt-header { position: sticky; top: 0; z-index: 10; display: flex; align-items: center; gap: 8px; padding: calc(10px + env(safe-area-inset-top,0px)) 14px 10px; background: rgba(255,255,255,0.86); -webkit-backdrop-filter: saturate(1.8) blur(16px); backdrop-filter: saturate(1.8) blur(16px); border-bottom: 1px solid rgba(0,0,0,0.05); }
.lt-header h1 { margin: 0; font-size: 18px; font-weight: 800; flex: 1; text-align: center; }
.lt-back { width: 34px; height: 34px; border: none; background: transparent; cursor: pointer; display: grid; place-items: center; }
.lt-wallet { width: 34px; height: 34px; border: none; background: transparent; cursor: pointer; display: grid; place-items: center; color: #0071e3; }
.lt-body { max-width: 680px; margin: 0 auto; padding: 16px; }
.lt-account { border-radius: 20px; padding: 20px; background: linear-gradient(125deg,#ff9500,#ff2d55); color: #fff; box-shadow: 0 14px 34px rgba(255,45,85,0.3); }
.lt-acc-top { display: flex; align-items: center; justify-content: space-between; }
.lt-acc-lab { font-size: 13px; opacity: 0.9; }
.lt-acc-exchange { background: rgba(255,255,255,0.22); border: none; color: #fff; font-size: 12px; font-weight: 700; padding: 6px 12px; border-radius: 14px; cursor: pointer; }
.lt-acc-num { font-size: 44px; font-weight: 800; margin: 8px 0 6px; letter-spacing: -0.02em; }
.lt-acc-sub { display: flex; gap: 14px; font-size: 12px; opacity: 0.9; }

.lt-pool { margin-top: 16px; background: #fff; border-radius: 16px; padding: 14px 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); }
.lt-pool h3, .lt-inv h3 { margin: 0 0 10px; font-size: 15px; }
.lt-pool-row { display: flex; gap: 12px; overflow-x: auto; }
.lt-pool-item { flex: 0 0 auto; width: 72px; text-align: center; }
.lt-pool-icon { width: 60px; height: 60px; margin: 0 auto; border-radius: 14px; background: #fff3e0; display: grid; place-items: center; overflow: hidden; color: #ff9500; }
.lt-pool-icon img { width: 100%; height: 100%; object-fit: cover; }
.lt-pool-name { font-size: 12px; margin-top: 6px; font-weight: 700; }
.lt-pool-range { font-size: 11px; color: #8e8e93; }

.lt-stage { margin-top: 18px; position: relative; min-height: 240px; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.lt-idle-tip { color: #8e8e93; font-size: 14px; }
.lt-box-wrap { position: relative; width: 180px; height: 180px; }
.lt-box { position: absolute; inset: 0; background: linear-gradient(150deg,#ff8a00,#ff2d55); border-radius: 22px; display: grid; place-items: center; box-shadow: 0 18px 40px rgba(255,45,85,0.4); }
.lt-box-glow { position: absolute; inset: -14px; border-radius: 30px; background: radial-gradient(circle, rgba(255,214,10,0.7), transparent 65%); opacity: 0; pointer-events: none; }
.lt-box-face { font-size: 60px; filter: drop-shadow(0 4px 8px rgba(0,0,0,0.2)); }
.lt-lid { position: absolute; top: -26px; left: 12px; width: 156px; height: 44px; background: linear-gradient(150deg,#ffb347,#ff7a18); border-radius: 12px 12px 0 0; display: grid; place-items: center; font-size: 20px; color: #fff; font-weight: 800; box-shadow: 0 6px 16px rgba(255,122,24,0.4); z-index: 2; }
.lt-prize-reveal { position: absolute; top: 8px; left: 0; right: 0; text-align: center; z-index: 1; opacity: 0; }
.lt-prize-reveal.is-show { position: static; opacity: 1; margin-top: -6px; }
.lt-prize-icon { width: 88px; height: 88px; margin: 0 auto; border-radius: 20px; background: #fff; box-shadow: 0 12px 30px rgba(0,0,0,0.18); display: grid; place-items: center; overflow: hidden; color: #ff9500; }
.lt-prize-icon img { width: 100%; height: 100%; object-fit: cover; }
.lt-prize-name { margin-top: 10px; font-size: 20px; font-weight: 800; }
.lt-prize-qty { font-size: 26px; font-weight: 800; color: #ff2d55; }
.lt-prize-tag { display: inline-block; margin-top: 8px; padding: 4px 14px; border-radius: 14px; background: linear-gradient(135deg,#ffd60a,#ff9f0a); color: #fff; font-size: 13px; font-weight: 800; }

.lt-result-actions { margin-top: 16px; width: 100%; }
.lt-ad-hint { text-align: center; font-size: 12px; color: #8e8e93; margin-bottom: 8px; }
.lt-result-btns { display: flex; gap: 12px; }
.lt-btn { flex: 1; height: 46px; border: none; border-radius: 23px; font-size: 15px; font-weight: 700; cursor: pointer; }
.lt-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.lt-btn--ad { background: #fff; color: #0071e3; border: 1px solid #d1e3ff; }
.lt-btn--claim { background: linear-gradient(135deg,#ff9500,#ff2d55); color: #fff; }
.lt-btn--draw { background: linear-gradient(135deg,#ff9500,#ff2d55); color: #fff; box-shadow: 0 10px 26px rgba(255,45,85,0.35); }
.lt-btn--primary { width: 100%; margin-top: 6px; background: linear-gradient(135deg,#ff9500,#ff2d55); color: #fff; }
.lt-btn--ghost { margin-top: 8px; width: 100%; background: #f0f0f2; color: #6e6e73; }
.lt-drawbar { margin-top: 18px; }

.lt-inv { margin-top: 18px; }
.lt-inv-item { background: #fff; border-radius: 14px; padding: 12px 14px; margin-bottom: 8px; display: flex; align-items: center; gap: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); }
.lt-inv-icon { width: 42px; height: 42px; border-radius: 10px; background: #fff3e0; display: grid; place-items: center; overflow: hidden; color: #ff9500; flex-shrink: 0; }
.lt-inv-icon img { width: 100%; height: 100%; object-fit: cover; }
.lt-inv-mid { flex: 1; min-width: 0; }
.lt-inv-name { font-size: 14px; font-weight: 700; }
.lt-inv-time { font-size: 11px; color: #bfbfc4; margin-top: 2px; }
.lt-inv-right { text-align: right; flex-shrink: 0; }
.lt-inv-qty { font-size: 16px; font-weight: 800; color: #ff2d55; }
.lt-empty { text-align: center; color: #b0b0b6; padding: 26px 0; font-size: 14px; }

.lt-mask { position: fixed; inset: 0; z-index: 100; background: rgba(0,0,0,0.45); display: flex; align-items: flex-end; justify-content: center; }
.lt-sheet { width: 100%; max-width: 520px; background: #fff; border-radius: 22px 22px 0 0; padding: 20px 18px calc(22px + env(safe-area-inset-bottom,0px)); }
.lt-sheet h3 { margin: 0 0 4px; font-size: 18px; font-weight: 800; }
.lt-sheet-hint { margin: 0 0 14px; font-size: 13px; color: #6e6e73; }
.lt-ex-input { display: flex; align-items: center; gap: 8px; }
.lt-ex-input input { flex: 1; height: 48px; padding: 0 14px; border: 1px solid #e5e5ea; border-radius: 12px; font-size: 16px; outline: none; }
.lt-ex-input input:focus { border-color: #ff9500; box-shadow: 0 0 0 3px rgba(255,149,0,0.12); }
.lt-ex-quick { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
.lt-ex-quick button { height: 34px; padding: 0 16px; border-radius: 17px; border: 1px solid #e5e5ea; background: #fff; color: #ff9500; font-size: 13px; font-weight: 700; cursor: pointer; }
.lt-ex-preview { margin: 12px 0 4px; font-size: 13px; color: #6e6e73; }
.lt-ex-preview b { color: #ff2d55; font-size: 16px; }
.lt-ex-no { color: #ff3b30; margin-left: 8px; font-size: 12px; }
.lt-claimed { text-align: center; padding: 8px 0; }
.lt-claimed-icon { font-size: 44px; }
.lt-claimed-title { font-size: 18px; font-weight: 800; margin: 6px 0 10px; }
.lt-claimed-tip { font-size: 13px; color: #6e6e73; margin: 0 0 8px; }
.lt-claimed-wx { display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px; border: 1px dashed #ff9500; color: #0071e3; border-radius: 10px; font-size: 14px; font-weight: 700; cursor: pointer; }
/* 开箱粒子 */
.lt-confetti { position: absolute; border-radius: 2px; pointer-events: none; z-index: 30; }
@media (min-width: 720px) { .lt-sheet { border-radius: 22px; margin-bottom: 6vh; } }
</style>