<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  getBadgeShop,
  getCoinTransactions,
  getCoinsMe,
  purchaseBadge,
  type BadgeShopItem,
  type CoinTransactionItem,
} from '../api/coins'
import { toast } from '../components/native/Toast'

defineOptions({ name: 'CoinsView' })

const router = useRouter()
const coins = ref(0)
const transactions = ref<CoinTransactionItem[]>([])
const shop = ref<BadgeShopItem[]>([])
const loading = ref(true)
const buyingId = ref<number | null>(null)

const TYPE_LABELS: Record<string, string> = {
  bind_reward: '绑定微信奖励',
  pin: '朋友圈置顶',
  badge_purchase: '购买徽章',
  skin_purchase: '购买皮肤',
  checkin: '每日签到',
}

async function loadAll() {
  try {
    const me = (await getCoinsMe()).data.data
    coins.value = me.coins
    const tx = (await getCoinTransactions(1, 50)).data.data
    transactions.value = tx.items
    const s = (await getBadgeShop()).data.data
    shop.value = s.items
    coins.value = s.coins
  } finally {
    loading.value = false
  }
}

async function buy(badge: BadgeShopItem) {
  if (badge.owned) return
  buyingId.value = badge.id
  try {
    const data = (await purchaseBadge(badge.id)).data.data
    coins.value = data.coins
    badge.owned = true
    toast.success(`已获得徽章「${badge.name}」`)
    await loadAll()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { msg?: string } } }
    toast.error(err.response?.data?.msg || '购买失败')
  } finally {
    buyingId.value = null
  }
}

function fmtTime(t: string): string {
  const d = new Date(t)
  if (Number.isNaN(d.getTime())) return t
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

onMounted(loadAll)
</script>

<template>
  <div class="coins-page">
    <header class="page-header">
      <button type="button" class="back-btn" @click="router.back()">←</button>
      <h1>金币中心</h1>
    </header>

    <div v-if="loading" class="empty-tip">加载中…</div>
    <template v-else>
      <section class="balance-card">
        <p class="balance-label">我的金币</p>
        <p class="balance-num">🪙 {{ coins }}</p>
        <p class="balance-tip">绑定微信送 10 金币 · 每日签到送 1-7 金币 · 被点赞也能赚</p>
      </section>

      <section class="shop-card">
        <h2>徽章商城</h2>
        <div v-if="!shop.length" class="empty-tip">暂无可购买徽章</div>
        <div v-for="badge in shop" :key="badge.id" class="shop-row">
          <span class="badge-icon">{{ badge.icon }}</span>
          <div class="badge-info">
            <p class="badge-name">{{ badge.name }}</p>
            <p class="badge-desc">{{ badge.description || '' }}</p>
          </div>
          <span v-if="badge.owned" class="owned-tag">已拥有</span>
          <button v-else type="button" class="buy-btn" :disabled="buyingId === badge.id" @click="buy(badge)">
            {{ buyingId === badge.id ? '购买中…' : `${badge.price} 金币` }}
          </button>
        </div>
      </section>

      <section class="tx-card">
        <h2>金币流水</h2>
        <div v-if="!transactions.length" class="empty-tip">暂无记录</div>
        <div v-for="tx in transactions" :key="tx.id" class="tx-row">
          <div class="tx-left">
            <p class="tx-type">{{ TYPE_LABELS[tx.type] || tx.type }}</p>
            <p class="tx-time">{{ fmtTime(tx.created_at) }}</p>
          </div>
          <span class="tx-amount" :class="tx.amount >= 0 ? 'plus' : 'minus'">
            {{ tx.amount >= 0 ? '+' : '' }}{{ tx.amount }}
          </span>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.coins-page {
  max-width: 720px;
  margin: 0 auto;
  padding: 0 14px 80px;
  min-height: 100vh;
}
.page-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 0;
}
.page-header h1 {
  font-size: 17px;
}
.back-btn {
  border: none;
  background: transparent;
  font-size: 20px;
  cursor: pointer;
  padding: 0 4px;
}
.balance-card {
  background: linear-gradient(135deg, #fff8e1, #ffe0b2);
  border-radius: 16px;
  padding: 22px;
  text-align: center;
}
.balance-label {
  font-size: 13px;
  color: #b26a00;
  margin: 0;
}
.balance-num {
  font-size: 34px;
  font-weight: 700;
  color: #8a4b00;
  margin: 6px 0;
}
.balance-tip {
  font-size: 12px;
  color: #a5713a;
  margin: 0;
}
.shop-card,
.tx-card {
  background: #fff;
  border-radius: 14px;
  padding: 16px;
  margin-top: 12px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
}
.shop-card h2,
.tx-card h2 {
  font-size: 15px;
  margin: 0 0 10px;
}
.shop-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid #f5f5f5;
}
.badge-icon {
  font-size: 26px;
}
.badge-info {
  flex: 1;
  min-width: 0;
}
.badge-name {
  font-size: 14px;
  margin: 0;
  font-weight: 600;
}
.badge-desc {
  font-size: 12px;
  color: var(--text-400, #999);
  margin: 2px 0 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.owned-tag {
  font-size: 12px;
  color: #2e7d32;
  background: #e8f5e9;
  border-radius: 999px;
  padding: 4px 10px;
}
.buy-btn {
  border: none;
  background: #ffb300;
  color: #fff;
  border-radius: 999px;
  padding: 6px 14px;
  font-size: 13px;
  cursor: pointer;
}
.tx-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 0;
  border-bottom: 1px solid #f7f7f7;
}
.tx-type {
  font-size: 13px;
  margin: 0;
}
.tx-time {
  font-size: 11px;
  color: var(--text-400, #999);
  margin: 2px 0 0;
}
.tx-amount {
  font-weight: 700;
  font-size: 15px;
}
.tx-amount.plus {
  color: #2e7d32;
}
.tx-amount.minus {
  color: #c62828;
}
.empty-tip {
  text-align: center;
  color: var(--text-400, #999);
  padding: 30px 0;
  font-size: 13px;
}
</style>
