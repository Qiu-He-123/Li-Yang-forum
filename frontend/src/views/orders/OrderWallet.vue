<script setup lang="ts">
/**
 * 交易币钱包（项目 2）
 * - 展示余额 / 冻结 / 汇率 / 最低提现
 * - 充值申请 / 提现申请
 * - 近 100 条流水
 */
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { Icon } from '../../components/native'
import { toast } from '../../components/native/Toast'
import { getWallet, recharge, withdraw, type WalletInfo } from '../../api/order'

const router = useRouter()
const w = ref<WalletInfo | null>(null)
const loading = ref(true)
const submitting = ref(false)

// 充值
const rechargeVisible = ref(false)
const rechargeForm = reactive({ amt: '' as string }) // 元
// 提现
const withdrawVisible = ref(false)
const withdrawForm = reactive({ amt: '' as string, payee: '' }) // 交易币

async function load() {
  loading.value = true
  try {
    const { data } = await getWallet()
    w.value = data.data
  } catch (e) {
    toast.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

async function submitRecharge() {
  const amt = Number(rechargeForm.amt)
  if (!amt || amt <= 0) { toast.error('请输入充值金额'); return }
  if (submitting.value) return
  submitting.value = true
  try {
    const { data } = await recharge(amt)
    toast.success(`已提交充值申请，将到账 ${data.data.bin} 交易币，等待后台审核`)
    rechargeVisible.value = false
    rechargeForm.amt = ''
    await load()
  } catch (e) {
    toast.error((e as Error).message)
  } finally {
    submitting.value = false
  }
}

async function submitWithdraw() {
  const amt = Number(withdrawForm.amt)
  if (!amt || amt <= 0) { toast.error('请输入提现交易币数量'); return }
  if (!withdrawForm.payee.trim()) { toast.error('请填写收款账号（支付宝/微信）'); return }
  if (submitting.value) return
  submitting.value = true
  try {
    const { data } = await withdraw(amt, withdrawForm.payee.trim())
    toast.success(`提现申请已提交（¥${(data.data.amount_cents / 100).toFixed(2)}），等待审核`)
    withdrawVisible.value = false
    withdrawForm.amt = ''
    withdrawForm.payee = ''
    await load()
  } catch (e) {
    toast.error((e as Error).message)
  } finally {
    submitting.value = false
  }
}

function goBack() { router.push('/orders') }
function goHall() { router.push('/orders') }

const TX_TYPE_TEXT: Record<string, string> = {
  task_publish: '发布任务托管', recharge: '充值', withdraw: '提现', withdraw_refund: '提现退回',
  task_reward: '任务收益', boost: '曝光消费', refund: '悬赏退回', task_commission: '平台抽成', withdraw_paid: '提现打款',
}

onMounted(load)
</script>

<template>
  <div class="ow-page">
    <header class="ow-header">
      <button class="ow-back" type="button" aria-label="返回" @click="goBack">
        <Icon name="chevron-left" :size="22" />
      </button>
      <h1>交易币钱包</h1>
      <div class="ow-spacer" />
    </header>

    <main class="ow-body">
      <!-- 余额卡 -->
      <section class="ow-card" :style="{ animation: loading ? 'none' : '' }">
        <div class="ow-balance-lab">可用交易币</div>
        <div class="ow-balance" :class="{ 'ow-balance--loading': loading && !w }">
          {{ w ? w.balance : '—' }}
        </div>
        <div class="ow-sub">
          <span>冻结 {{ w?.frozen ?? 0 }}</span>
          <span>汇率 1元 = {{ w?.rate ?? '—' }} 交易币</span>
        </div>
        <div class="ow-cta">
          <button type="button" class="ow-btn ow-btn--light" @click="rechargeVisible = true">充值</button>
          <button type="button" class="ow-btn ow-btn--dark" @click="withdrawVisible = true">提现</button>
        </div>
      </section>

      <!-- 规则提示 -->
      <section class="ow-rules">
        <h3><Icon name="info" :size="15" /> 平台规则</h3>
        <ul>
          <li>充值按后台汇率兑换交易币，到账需审核（生产接入支付后自动到账）。</li>
          <li>提现最低 {{ w ? (w.withdraw_min_cents / 100) : 6 }} 元，按汇率折算交易币，需填写收款账号。</li>
          <li>发布任务按悬赏托管交易币，验收后发放接单人，平台按 {{ w?.commission_rate ?? '—' }}% 抽成。</li>
          <li>曝光置顶每次 {{ w?.boost_price ?? '—' }} 交易币。</li>
        </ul>
      </section>

      <!-- 流水 -->
      <section class="ow-tx">
        <h3>交易流水</h3>
        <div v-if="w && w.transactions.length === 0" class="ow-empty">暂无流水</div>
        <div v-for="tx in w?.transactions || []" :key="tx.id" class="ow-tx-item">
          <div class="ow-tx-left">
            <div class="ow-tx-type">{{ TX_TYPE_TEXT[tx.type] || tx.type }}</div>
            <div class="ow-tx-desc">{{ tx.description }}</div>
            <div class="ow-tx-time">{{ tx.created_at }}</div>
          </div>
          <div class="ow-tx-right">
            <div class="ow-tx-amt" :class="{ plus: tx.amount > 0, minus: tx.amount < 0 }">
              {{ tx.amount > 0 ? '+' : '' }}{{ tx.amount }}
            </div>
            <span class="ow-tx-status" :class="tx.status">{{ tx.status }}</span>
          </div>
        </div>
      </section>
    </main>

    <!-- 充值弹窗 -->
    <div v-if="rechargeVisible" class="ow-mask" @click.self="rechargeVisible = false">
      <div class="ow-sheet">
        <h3>充值交易币</h3>
        <p class="ow-sheet-hint">实时汇率：1 元 = {{ w?.rate ?? '—' }} 交易币</p>
        <div class="ow-amt-box">
          <input v-model="rechargeForm.amt" type="number" inputmode="decimal" min="0" step="0.01" placeholder="输入充值金额（元）" />
        </div>
        <div class="ow-quick">
          <button v-for="q in [1, 6, 10, 30]" :key="q" type="button" @click="rechargeForm.amt = String(q)">¥{{ q }}</button>
        </div>
        <div class="ow-prev">预计到账：<b>{{ (Number(rechargeForm.amt || 0) * (w?.rate || 0)).toFixed(0) }}</b> 交易币</div>
        <button class="ow-btn ow-btn--primary" type="button" :disabled="submitting" @click="submitRecharge">提交充值申请</button>
        <button class="ow-btn ow-btn--ghost" type="button" @click="rechargeVisible = false">取消</button>
      </div>
    </div>

    <!-- 提现弹窗 -->
    <div v-if="withdrawVisible" class="ow-mask" @click.self="withdrawVisible = false">
      <div class="ow-sheet">
        <h3>申请提现</h3>
        <p class="ow-sheet-hint">最低提现 ¥{{ w ? (w.withdraw_min_cents / 100) : 6 }}（{{ w ? Math.ceil(w.withdraw_min_cents / 100 * (w.rate || 1)) : 600 }} 交易币）</p>
        <div class="ow-amt-box">
          <input v-model="withdrawForm.amt" type="number" inputmode="numeric" min="1" step="1" placeholder="输入提现交易币数量" />
        </div>
        <div class="ow-field">
          <input v-model="withdrawForm.payee" type="text" maxlength="120" placeholder="收款账号（支付宝 / 微信）" />
        </div>
        <div class="ow-prev">预计到账：<b>¥{{ ((Number(withdrawForm.amt || 0) / (w?.rate || 1))).toFixed(2) }}</b></div>
        <button class="ow-btn ow-btn--primary" type="button" :disabled="submitting" @click="submitWithdraw">提交提现申请</button>
        <button class="ow-btn ow-btn--ghost" type="button" @click="withdrawVisible = false; withdrawForm.amt = ''">取消</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ow-page { min-height: 100vh; background: linear-gradient(180deg,#eaf1ff 0%,#f7f8fb 240px, #f7f8fb 100%); color: #1d1d1f; padding-bottom: 40px; }
.ow-header { position: sticky; top: 0; z-index: 10; display: flex; align-items: center; gap: 8px; padding: calc(10px + env(safe-area-inset-top,0px)) 14px 10px; background: rgba(255,255,255,0.86); -webkit-backdrop-filter: saturate(1.8) blur(16px); backdrop-filter: saturate(1.8) blur(16px); border-bottom: 1px solid rgba(0,0,0,0.05); }
.ow-header h1 { margin: 0; font-size: 18px; font-weight: 800; flex: 1; text-align: center; }
.ow-back { width: 34px; height: 34px; border: none; background: transparent; cursor: pointer; display: grid; place-items: center; }
.ow-spacer { width: 34px; }
.ow-body { max-width: 680px; margin: 0 auto; padding: 16px; }
.ow-card { border-radius: 20px; padding: 22px 20px; background: linear-gradient(125deg,#0071e3,#5856d6); color: #fff; box-shadow: 0 14px 34px rgba(0,113,227,0.35); }
.ow-balance-lab { font-size: 13px; opacity: 0.85; }
.ow-balance { font-size: 44px; font-weight: 800; margin: 6px 0 4px; letter-spacing: -0.02em; }
.ow-balance--loading { animation: pulse 1s infinite; opacity: 0.4; }
@keyframes pulse { 50% { opacity: 0.2; } }
.ow-sub { display: flex; gap: 16px; font-size: 12px; opacity: 0.85; }
.ow-cta { display: flex; gap: 12px; margin-top: 18px; }
.ow-btn { flex: 1; height: 46px; border: none; border-radius: 23px; font-size: 15px; font-weight: 700; cursor: pointer; }
.ow-btn--light { background: #fff; color: #0071e3; }
.ow-btn--dark { background: rgba(0,0,0,0.18); color: #fff; border: 1px solid rgba(255,255,255,0.4); }
.ow-btn--primary { width: 100%; margin-top: 6px; background: linear-gradient(135deg,#0071e3,#5856d6); color: #fff; box-shadow: 0 8px 20px rgba(0,113,227,0.3); }
.ow-btn--ghost { margin-top: 8px; background: #f0f0f2; color: #6e6e73; }
.ow-rules { margin-top: 16px; background: #fff; border-radius: 16px; padding: 14px 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); }
.ow-rules h3 { margin: 0 0 8px; font-size: 15px; display: flex; align-items: center; gap: 6px; }
.ow-rules ul { margin: 0; padding-left: 18px; font-size: 13px; color: #6e6e73; line-height: 1.8; }
.ow-tx { margin-top: 16px; }
.ow-tx h3 { font-size: 15px; margin: 0 0 10px; padding-left: 2px; }
.ow-tx-item { background: #fff; border-radius: 14px; padding: 12px 14px; margin-bottom: 8px; display: flex; justify-content: space-between; gap: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); }
.ow-tx-left { min-width: 0; }
.ow-tx-type { font-size: 14px; font-weight: 700; }
.ow-tx-desc { font-size: 12px; color: #8e8e93; margin-top: 2px; word-break: break-all; }
.ow-tx-time { font-size: 11px; color: #bfbfc4; margin-top: 3px; }
.ow-tx-right { text-align: right; flex-shrink: 0; }
.ow-tx-amt { font-size: 16px; font-weight: 800; }
.ow-tx-amt.plus { color: #34c759; }
.ow-tx-amt.minus { color: #1d1d1f; }
.ow-tx-status { font-size: 11px; color: #8e8e93; }
.ow-tx-status.completed { color: #34c759; }
.ow-tx-status.pending { color: #ff9500; }
.ow-tx-status.rejected { color: #ff3b30; }
.ow-empty { text-align: center; color: #b0b0b6; padding: 30px 0; font-size: 14px; }

.ow-mask { position: fixed; inset: 0; z-index: 100; background: rgba(0,0,0,0.45); display: flex; align-items: flex-end; justify-content: center; }
.ow-sheet { width: 100%; max-width: 520px; background: #fff; border-radius: 22px 22px 0 0; padding: 20px 18px calc(22px + env(safe-area-inset-bottom,0px)); }
.ow-sheet h3 { margin: 0 0 4px; font-size: 18px; font-weight: 800; }
.ow-sheet-hint { margin: 0 0 14px; font-size: 13px; color: #6e6e73; }
.ow-amt-box input, .ow-field input { width: 100%; height: 48px; padding: 0 14px; border: 1px solid #e5e5ea; border-radius: 12px; font-size: 16px; outline: none; box-sizing: border-box; }
.ow-amt-box input:focus, .ow-field input:focus { border-color: #0071e3; box-shadow: 0 0 0 3px rgba(0,113,227,0.12); }
.ow-field { margin-top: 10px; }
.ow-quick { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
.ow-quick button { height: 34px; padding: 0 16px; border-radius: 17px; border: 1px solid #e5e5ea; background: #fff; color: #0071e3; font-size: 13px; font-weight: 700; cursor: pointer; }
.ow-prev { margin: 12px 0 4px; font-size: 13px; color: #6e6e73; }
.ow-prev b { color: #0071e3; font-size: 16px; }
@media (min-width: 720px) { .ow-sheet { border-radius: 22px; margin-bottom: 6vh; } }
</style>