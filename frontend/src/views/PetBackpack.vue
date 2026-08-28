<script setup lang="ts">
/**
 * 我的背包（宠物道具）
 * - 列出背包全部道具，按 食物/玩具/日用医疗/进化 分类筛选
 * - 需选择一只已领养的宠物作为作用对象
 * - 食物 → 喂食（恢复饱食+好感）；玩具 → 陪玩（好感）；日用/医疗 → 使用（按效果）
 *   进化水晶 → 进化（好感满100时可进化）；非食物道具不能「吃」，只用「使用」
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import { listMyPets, listMyBag, useBagItem, type MyPetItem, type BagItem } from '../api/petShop'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const pets = ref<MyPetItem[]>([])
const selectedPetId = ref<number | null>(null)
const bag = ref<BagItem[]>([])
const usingId = ref<number | null>(null) // 正在使用的道具 id

// 筛选标签：all=全部 food=食物 toy=玩具 use=日用/医疗 evolve=进化
const activeTab = ref<'all' | 'food' | 'toy' | 'use' | 'evolve'>('all')
const tabs: { key: (typeof activeTab.value); label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'food', label: '食物' },
  { key: 'toy', label: '玩具' },
  { key: 'use', label: '日用/医疗' },
  { key: 'evolve', label: '进化水晶' },
]

/** 道具分组类型：食物可喂食，玩具陪玩，日用/医疗使用，进化水晶进化 */
function groupOf(item: BagItem): 'food' | 'toy' | 'use' | 'evolve' {
  if ((item.kind ?? 1) === 3) return 'evolve'
  const a = item.attrs || {}
  if (!!a.satiety || ['零食', '狗粮', '猫粮'].includes(item.category || '')) return 'food'
  if (Number(a.play) > 0) return 'toy'
  return 'use'
}

const GROUP_LABEL: Record<string, { name: string; color: string }> = {
  food: { name: '食物', color: '' },
  toy: { name: '玩具', color: '' },
  use: { name: '日用/医疗', color: '' },
  evolve: { name: '进化水晶', color: 'crystal' },
}

function isFood(item: BagItem): boolean { return groupOf(item) === 'food' }

const filteredBag = computed(() => {
  if (activeTab.value === 'all') return bag.value
  return bag.value.filter((b) => groupOf(b) === activeTab.value)
})

const selectedPet = computed(() => pets.value.find((p) => p.id === selectedPetId.value) || null)

const bagTotal = computed(() => bag.value.reduce((n, b) => n + b.qty, 0))

function isImageUrl(url: string | null | undefined): boolean {
  return !!url && (url.startsWith('/') || url.startsWith('http'))
}

async function loadPets() {
  try {
    const { data: resp } = await listMyPets({ showGlobalLoading: false, showGlobalError: false })
    pets.value = resp.data.items || []
    // 优先级：路由指定 pet → 第一只宠物
    const qPet = Number(route.query.pet)
    if (pets.value.some((p) => p.id === qPet)) selectedPetId.value = qPet
    else selectedPetId.value = pets.value[0]?.id ?? null
  } catch { pets.value = [] }
}

async function loadBag() {
  try {
    const { data: resp } = await listMyBag({ showGlobalLoading: false, showGlobalError: false })
    bag.value = resp.data.items || []
  } catch { bag.value = [] }
}

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([loadPets(), loadBag()])
  } finally {
    loading.value = false
  }
})

/** 按钮文案：食物=喂食/吃，玩具=陪玩，日用医疗=使用，进化=进化 */
function useLabel(item: BagItem): string {
  const g = groupOf(item)
  if (g === 'food') return '喂食'
  if (g === 'toy') return '陪玩'
  if (g === 'evolve') return '进化'
  return '使用'
}

function usageHint(item: BagItem): string {
  const a = item.attrs || {}
  const parts: string[] = []
  if (isFood(item)) {
    if (a.satiety) parts.push(`饱食+${a.satiety}`)
    if (a.affinity ?? item.affinity_gain) parts.push(`好感+${a.affinity ?? item.affinity_gain}`)
  } else {
    if (a.affinity ?? item.affinity_gain) parts.push(`好感+${a.affinity ?? item.affinity_gain}`)
    if (a.health) parts.push(`健康+${a.health}`)
    if (a.stamina) parts.push(`体力+${a.stamina}`)
    if (a.mood) parts.push(`心情+${a.mood}`)
    if (a.play) parts.push('陪玩')
  }
  return parts.length ? parts.join('·') : ''
}

async function onUse(item: BagItem) {
  if (!selectedPetId.value) { toast.warning('请先选择要使用的宠物'); return }
  if (usingId.value !== null) return
  usingId.value = item.id
  try {
    const { data: resp } = await useBagItem(selectedPetId.value, item.id, { showGlobalLoading: false })
    toast.success(resp.data.message || '使用成功')
    bag.value = resp.data.bag || []
    // 进化成功提示
    if (groupOf(item) === 'evolve' && resp.data.evolved) toast.success('🎉 宠物进化成功！')
    else if (resp.data.can_evolve) toast.info('💡 好感已满，可使用进化水晶进阶！')
  } catch (e: unknown) {
    const err = e as { response?: { data?: { msg?: string | { msg?: string } } } }
    const detail = err?.response?.data?.msg
    let text = '使用失败'
    if (typeof detail === 'string') text = detail
    else if (detail && typeof detail === 'object' && 'msg' in detail) text = (detail as { msg?: string }).msg || text
    toast.error(text)
  } finally {
    usingId.value = null
  }
}

function onBack() {
  if (window.history.length > 1) router.back()
  else router.push('/pet-shop/my')
}
</script>

<template>
  <div class="bp-page">
    <!-- 顶部导航 -->
    <header class="bp-header">
      <div class="bp-header__inner">
        <button class="bp-header__btn" type="button" @click="onBack">
          <Icon name="chevron-left" :size="22" />
        </button>
        <span class="bp-header__title">我的背包</span>
        <span class="bp-header__btn bp-header__btn--spacer"></span>
      </div>
    </header>

    <!-- 选择宠物 -->
    <div class="bp-petbar">
      <span class="bp-petbar__label">作用宠物</span>
      <div class="bp-petbar__chips">
        <template v-if="pets.length">
          <button v-for="p in pets" :key="p.id" type="button" class="bp-petchip"
            :class="{ 'is-active': selectedPetId === p.id }"
            @click="selectedPetId = p.id">
            <span class="bp-petchip__name">{{ p.nickname || p.name }}</span>
            <span class="bp-petchip__lv">Lv{{ p.level }}</span>
          </button>
        </template>
        <p v-else class="bp-petbar__empty">
          还没有领养宠物
          <button type="button" @click="router.push('/pet-shop')">去领养 →</button>
        </p>
      </div>
    </div>

    <!-- 统计 -->
    <div class="bp-stats">
      <div class="bp-stats__col">
        <span class="bp-stats__num">{{ bag.length }}</span>
        <span class="bp-stats__label">道具种类</span>
      </div>
      <div class="bp-stats__col">
        <span class="bp-stats__num">{{ bagTotal }}</span>
        <span class="bp-stats__label">总数量</span>
      </div>
      <div class="bp-stats__col">
        <span class="bp-stats__num">{{ selectedPet?.satiety ?? '—' }}</span>
        <span class="bp-stats__label">饱食度</span>
      </div>
      <div class="bp-stats__col">
        <span class="bp-stats__num">{{ selectedPet?.affinity ?? '—' }}</span>
        <span class="bp-stats__label">好感度</span>
      </div>
    </div>

    <!-- 分类筛选 -->
    <div class="bp-tabs">
      <button v-for="t in tabs" :key="t.key" type="button" class="bp-tab"
        :class="{ 'is-active': activeTab === t.key }" @click="activeTab = t.key">
        {{ t.label }}
      </button>
    </div>

    <!-- 道具列表 -->
    <div v-if="loading" class="bp-state">
      <div class="bp-state__spinner"></div>
      <p class="bp-state__text">背包加载中…</p>
    </div>

    <div v-else-if="!filteredBag.length" class="bp-state">
      <span class="bp-state__emoji">🎒</span>
      <p class="bp-state__text">背包空空如也，去宠物商城逛逛吧</p>
      <button class="bp-state__btn" type="button" @click="router.push('/pet-shop')">去商城购买 →</button>
    </div>

    <div v-else class="bp-list">
      <div v-for="item in filteredBag" :key="item.id" class="bp-card">
        <div class="bp-card__thumb">
          <img v-if="isImageUrl(item.image_url)" :src="item.image_url!" :alt="item.name" />
          <span v-else class="bp-card__emoji">{{ item.image_url || '🎁' }}</span>
        </div>
        <div class="bp-card__info">
          <div class="bp-card__name-row">
            <span class="bp-card__name">{{ item.name }}</span>
            <span class="bp-card__qty">×{{ item.qty }}</span>
          </div>
          <div class="bp-card__tags">
            <span class="bp-card__type" :class="{ 'is-crystal': groupOf(item) === 'evolve' }">
              {{ GROUP_LABEL[groupOf(item)].name }}
              <template v-if="isFood(item)">·可吃</template>
              <template v-else-if="groupOf(item) === 'evolve'">·进化</template>
              <template v-else>·不可食用</template>
            </span>
            <span v-if="usageHint(item)" class="bp-card__effect">{{ usageHint(item) }}</span>
          </div>
        </div>
        <button class="bp-card__use" type="button" :disabled="usingId !== null"
          :class="{ 'is-evolve': groupOf(item) === 'evolve' }"
          @click="onUse(item)">
          {{ usingId === item.id ? '使用中…' : useLabel(item) }}
        </button>
      </div>
    </div>

    <div class="bp-foot">
      <button class="bp-foot__shop" type="button" @click="router.push('/pet-shop')">🛒 去商城补货</button>
    </div>
  </div>
</template>

<style scoped>
.bp-page {
  min-height: 100vh;
  background: var(--bg-100);
  padding-bottom: calc(32px + env(safe-area-inset-bottom));
}

/* ====== 顶栏 ====== */
.bp-header {
  position: sticky; top: 0; z-index: 20;
  background: rgba(255,255,255,0.86);
  -webkit-backdrop-filter: blur(12px); backdrop-filter: blur(12px);
  border-bottom: 0.5px solid var(--bg-200);
}
.bp-header__inner {
  max-width: 720px; margin: 0 auto; height: 50px;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 12px;
}
.bp-header__btn {
  width: 34px; height: 34px; display: inline-flex; align-items: center; justify-content: center;
  background: transparent; border: none; color: var(--text-700); cursor: pointer;
  border-radius: 50%;
}
.bp-header__btn--spacer { visibility: hidden; }
.bp-header__title { font-size: 16px; font-weight: 600; color: var(--text-900); }

/* ====== 宠物选择条 ====== */
.bp-petbar {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 12px 14px 6px; max-width: 720px; margin: 0 auto;
}
.bp-petbar__label { font-size: 12px; color: var(--text-400); padding-top: 7px; flex-shrink: 0; }
.bp-petbar__chips { display: flex; gap: 8px; flex-wrap: wrap; flex: 1; }
.bp-petchip {
  display: inline-flex; align-items: baseline; gap: 6px;
  padding: 6px 12px; border-radius: 999px; border: 1px solid var(--bg-300);
  background: var(--bg-50); cursor: pointer; transition: all 150ms ease;
}
.bp-petchip.is-active {
  background: linear-gradient(135deg, #5b8cff, #3d7bff); border-color: transparent;
}
.bp-petchip__name { font-size: 13px; font-weight: 600; color: var(--text-700); }
.bp-petchip.is-active .bp-petchip__name { color: #fff; }
.bp-petchip__lv { font-size: 11px; color: var(--text-400); }
.bp-petchip.is-active .bp-petchip__lv { color: rgba(255,255,255,0.85); }
.bp-petbar__empty { margin: 0; font-size: 13px; color: var(--text-500); }
.bp-petbar__empty button {
  border: none; background: none; color: var(--brand-500); font-size: 13px; font-weight: 600; cursor: pointer;
  text-decoration: underline;
}

/* ====== 统计 ====== */
.bp-stats {
  display: flex; margin: 10px 14px; padding: 12px 0;
  background: var(--bg-50); border-radius: 14px; border: 0.5px solid var(--bg-200);
  box-shadow: 0 2px 10px rgba(23,32,64,0.04);
  max-width: calc(720px - 28px); margin-left: auto; margin-right: auto;
}
.bp-stats__col { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 2px; }
.bp-stats__num { font-size: 18px; font-weight: 700; color: var(--text-800); }
.bp-stats__label { font-size: 11px; color: var(--text-400); }

/* ====== 分类筛选 ====== */
.bp-tabs {
  display: flex; gap: 8px; padding: 4px 14px 8px; overflow-x: auto;
  max-width: 720px; margin: 0 auto; white-space: nowrap;
}
.bp-tab {
  flex-shrink: 0; padding: 6px 14px; border-radius: 999px;
  border: 1px solid var(--bg-300); background: var(--bg-50);
  color: var(--text-500); font-size: 12.5px; font-weight: 500; cursor: pointer;
  transition: all 150ms ease;
}
.bp-tab.is-active {
  background: linear-gradient(135deg, #5b8cff, #3d7bff); color: #fff;
  border-color: transparent; font-weight: 600;
}

/* ====== 空/加载状态 ====== */
.bp-state { min-height: 40vh; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; text-align: center; padding: 30px 20px; }
.bp-state__spinner {
  width: 30px; height: 30px; border: 3px solid var(--bg-200);
  border-top-color: var(--brand-500); border-radius: 50%;
  animation: bp-spin 0.8s linear infinite;
}
@keyframes bp-spin { to { transform: rotate(360deg); } }
.bp-state__emoji { font-size: 44px; }
.bp-state__text { margin: 0; font-size: 13.5px; color: var(--text-500); }
.bp-state__btn {
  margin-top: 4px; padding: 8px 18px; border: none; border-radius: 18px;
  background: var(--brand-500); color: #fff; font-size: 13px; font-weight: 600; cursor: pointer;
}

/* ====== 道具卡片 ====== */
.bp-list {
  display: flex; flex-direction: column; gap: 10px;
  max-width: 720px; margin: 0 auto; padding: 4px 14px 0;
}
.bp-card {
  display: flex; align-items: center; gap: 12px;
  background: var(--bg-50); border: 0.5px solid var(--bg-200); border-radius: 14px;
  padding: 12px; box-shadow: 0 2px 10px rgba(23,32,64,0.04);
}
.bp-card__thumb {
  width: 52px; height: 52px; border-radius: 12px; overflow: hidden; flex-shrink: 0;
  background: linear-gradient(135deg, #eef2ff, #f5f3ff);
  display: flex; align-items: center; justify-content: center;
}
.bp-card__thumb img { width: 100%; height: 100%; object-fit: cover; }
.bp-card__emoji { font-size: 30px; }
.bp-card__info { flex: 1; min-width: 0; }
.bp-card__name-row { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.bp-card__name { font-size: 14px; font-weight: 600; color: var(--text-800); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bp-card__qty { font-size: 13px; font-weight: 700; color: var(--text-600); flex-shrink: 0; }
.bp-card__tags { display: flex; align-items: center; gap: 6px; margin-top: 5px; flex-wrap: wrap; }
.bp-card__type {
  font-size: 10.5px; padding: 1px 8px; border-radius: 8px;
  background: rgba(61,123,255,0.1); color: #3d7bff; font-weight: 600;
}
.bp-card__type.is-crystal { background: rgba(124,58,237,0.1); color: #7c3aed; }
.bp-card__effect { font-size: 11px; color: var(--text-400); }
.bp-card__use {
  flex-shrink: 0; padding: 8px 16px; border: none; border-radius: 18px;
  background: linear-gradient(135deg, #5b8cff, #3d7bff); color: #fff;
  font-size: 13px; font-weight: 600; cursor: pointer; transition: all 150ms ease;
}
.bp-card__use.is-evolve { background: linear-gradient(135deg, #a78bfa, #7c3aed); }
.bp-card__use:active { transform: scale(0.95); }
.bp-card__use:disabled { opacity: 0.5; cursor: not-allowed; }

/* ====== 底部补货 ====== */
.bp-foot { padding: 16px 14px; text-align: center; }
.bp-foot__shop {
  width: 100%; max-width: 720px; height: 46px; border: none; border-radius: 23px;
  background: linear-gradient(135deg, #ff6b6b, #ff3b30); color: #fff;
  font-size: 15px; font-weight: 600; cursor: pointer;
  box-shadow: 0 4px 14px rgba(255,59,48,0.28);
}
</style>