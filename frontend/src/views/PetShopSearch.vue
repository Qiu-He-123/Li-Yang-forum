<script setup lang="ts">
/**
 * 宠物商城 · 商品搜索页
 * 移动端从商城右上角搜索图标进入；桌面端也可直接访问 /pet-shop/search。
 * 独立页：顶部全宽搜索框 + 商品网格结果（复用 listPetProducts keyword 检索）。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import { listPetProducts, purchaseItem, type PetProduct } from '../api/petShop'
import { getCoinsMe } from '../api/coins'
import { useSessionStore } from '../stores/session'

defineOptions({ name: 'PetShopSearch' })

const router = useRouter()
const route = useRoute()
const session = useSessionStore()

const keyword = ref<string>(String(route.query.q ?? ''))
const searched = ref(false)

const products = ref<PetProduct[]>([])
const loading = ref(false)
const loadingMore = ref(false)
const total = ref(0)
const page = ref(1)
const PAGE_SIZE = 100
const hasMore = computed(() => products.value.length < total.value)

const buyingId = ref<number | null>(null)
const coins = ref<number | null>(null)

async function loadCoins() {
  if (!session.isLoggedIn()) return
  try {
    const { data: resp } = await getCoinsMe()
    coins.value = resp.data.coins
  } catch {
    coins.value = null
  }
}

async function doSearch() {
  const q = keyword.value.trim()
  if (!q) {
    toast.info('请输入搜索关键词')
    return
  }
  loading.value = true
  searched.value = true
  page.value = 1
  router.replace({ path: '/pet-shop/search', query: { q } })
  try {
    const { data: resp } = await listPetProducts({
      keyword: q,
      page: 1,
      page_size: PAGE_SIZE,
    })
    const d = resp.data
    products.value = d.items || []
    total.value = d.total || 0
  } catch {
    products.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  if (loadingMore.value || !hasMore.value) return
  loadingMore.value = true
  const q = keyword.value.trim()
  try {
    const { data: resp } = await listPetProducts({
      keyword: q || undefined,
      page: page.value + 1,
      page_size: PAGE_SIZE,
    })
    const d = resp.data
    products.value = [...products.value, ...(d.items || [])]
    total.value = d.total || 0
    page.value += 1
  } finally {
    loadingMore.value = false
  }
}

function goBack() {
  router.back()
}

function isImageUrl(url: string | null | undefined): boolean {
  if (!url) return false
  return url.startsWith('/') || url.startsWith('http')
}

function productTag(p: PetProduct): string | null {
  if (p.kind === 3) return '💎进化'
  if (p.anim) return '像素宠物'
  if (p.model_3d_url) return '3D'
  if (p.sales >= 1000) return '热销'
  return null
}

function getCardClass(p: PetProduct): string {
  if (p.kind === 1) return 'ps-card ps-card--pet'
  if (p.kind === 3) return 'ps-card ps-card--item ps-card--crystal'
  return 'ps-card ps-card--item'
}

function formatPrice(price: number): string {
  return price.toFixed(price % 1 === 0 ? 0 : 1)
}

function openDetail(product: PetProduct) {
  router.push(`/pet-shop/${product.id}`)
}

async function onQuickBuy(product: PetProduct) {
  if (!session.isLoggedIn()) {
    router.push('/login')
    return
  }
  if (buyingId.value) return
  buyingId.value = product.id
  try {
    const { data: resp } = await purchaseItem(product.id, { showGlobalLoading: false })
    coins.value = resp.data.coins
    const p = products.value.find((x) => x.id === product.id)
    if (p) p.bag_qty = resp.data.item.bag_qty
    toast.success(`「${product.name}」已购买，去喂宠物涨好感吧！`)
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { msg?: string } } })?.response?.data?.msg
    toast.error(msg || '购买失败，请稍后再试')
  } finally {
    buyingId.value = null
  }
}

// 滚动加载
const loadMoreSentinel = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null
function createObserver() {
  if (observer) return
  const el = loadMoreSentinel.value
  if (!el) return
  observer = new IntersectionObserver(
    (entries) => {
      if (entries[0]?.isIntersecting && !loading.value && !loadingMore.value) {
        loadMore()
      }
    },
    { rootMargin: '200px' },
  )
  observer.observe(el)
}
watch(loading, (l) => {
  if (!l) setTimeout(() => createObserver())
}, { flush: 'post' })

onMounted(() => {
  loadCoins()
  if (keyword.value) doSearch()
  createObserver()
})

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
})
</script>

<template>
  <main class="ps-page">
    <!-- 顶部搜索栏 -->
    <header class="ps-header">
      <div class="ps-header__inner">
        <button class="ps-back" type="button" aria-label="返回" @click="goBack">
          <Icon name="chevron-left" :size="22" />
        </button>
        <form class="ps-search" @submit.prevent="doSearch">
          <Icon name="search" :size="16" class="ps-search__icon" />
          <input
            v-model="keyword"
            class="ps-search__input"
            type="text"
            placeholder="搜索商品..."
            autofocus
            @keyup.enter="doSearch"
          />
          <button v-if="keyword" class="ps-search__clear" type="button" aria-label="清空" @click="keyword = ''">
            <Icon name="x" :size="16" />
          </button>
        </form>
        <button class="ps-search__go" type="submit" @click.prevent="doSearch">搜索</button>
      </div>
    </header>

    <!-- 热门/历史联想：未搜索时给出引导 -->
    <div v-if="!searched" class="ps-guide">
      <div class="ps-guide__title">在宠物商城找点什么？</div>
      <div class="ps-guide__tags">
        <button
          v-for="t in ['猫粮', '狗粮', '零食', '玩具', '日用', '医疗', '萌宠领养', '进化水晶']"
          :key="t"
          class="ps-guide__tag"
          type="button"
          @click="keyword = t; doSearch()"
        >
          {{ t }}
        </button>
      </div>
    </div>

    <!-- 搜索结果 -->
    <main v-else class="ps-results">
      <div v-if="loading" class="ps-loading">
        <Icon name="refresh" :size="20" />
        <span>搜索中…</span>
      </div>
      <template v-else>
        <div v-if="products.length" class="ps-grid">
          <article
            v-for="product in products"
            :key="product.id"
            :class="getCardClass(product)"
            @click="openDetail(product)"
          >
            <!-- 宠物卡片 (kind=1) -->
            <template v-if="product.kind === 1">
              <div class="ps-card__img" :class="{ 'ps-card__img--pixel': !!product.anim }">
                <img
                  v-if="isImageUrl(product.image_url)"
                  class="ps-card__photo"
                  :class="{ 'ps-card__photo--pixel': !!product.anim }"
                  :src="product.image_url!"
                  :alt="product.name"
                  loading="lazy"
                />
                <span v-else class="ps-card__emoji">{{ product.image_url || '🐾' }}</span>
                <span v-if="productTag(product)" class="ps-card__tag">{{ productTag(product) }}</span>
                <span v-if="product.owned" class="ps-card__owned">已领养 ✓</span>
              </div>
              <div class="ps-card__info">
                <h3 class="ps-card__name">{{ product.name }}</h3>
                <div class="ps-card__bottom">
                  <div class="ps-card__price">
                    <span class="ps-price">🪙{{ formatPrice(product.price) }}</span>
                  </div>
                  <span class="ps-card__sales">已售 {{ product.sales }}</span>
                </div>
              </div>
            </template>

            <!-- 道具/进化水晶卡片 (kind=2/3) -->
            <template v-else>
              <div class="ps-card__img" :class="{ 'ps-card__img--crystal': product.kind === 3 }">
                <span class="ps-card__emoji">{{ product.image_url || '📦' }}</span>
                <span
                  v-if="product.kind === 2 && (product.affinity_gain > 0 || (product.attrs?.satiety || 0) > 0)"
                  class="ps-card__gain"
                >
                  饱腹 +{{ product.attrs?.satiety || 0 }} · 好感 +{{ product.affinity_gain || 0 }}
                </span>
                <span v-if="product.kind === 3" class="ps-tag ps-tag--crystal">💎 进化必需</span>
                <span v-if="product.bag_qty" class="ps-card__qty">背包 ×{{ product.bag_qty }}</span>
              </div>
              <div class="ps-card__info">
                <h3 class="ps-card__name">{{ product.name }}</h3>
                <p class="ps-card__desc">{{ product.description }}</p>
                <div class="ps-card__bottom">
                  <div class="ps-card__price">
                    <span class="ps-price">🪙{{ formatPrice(product.price) }}</span>
                  </div>
                  <button
                    class="ps-card__buy"
                    type="button"
                    :disabled="buyingId === product.id"
                    @click.stop="onQuickBuy(product)"
                  >
                    {{ buyingId === product.id ? '购买中…' : '购买' }}
                  </button>
                </div>
              </div>
            </template>
          </article>
        </div>
        <div v-else class="ps-empty">
          <span class="ps-empty__icon">🔍</span>
          <p class="ps-empty__text">没有找到相关商品</p>
        </div>

        <div ref="loadMoreSentinel" class="ps-load-more">
          <span v-if="loadingMore">加载中...</span>
          <span v-else-if="!hasMore && products.length > 0" class="ps-load-more__end">— 已经到底啦 —</span>
        </div>
      </template>
    </main>
  </main>
</template>

<style scoped>
.ps-page {
  min-height: 100vh;
  background: var(--bg-100);
  padding-bottom: calc(72px + env(safe-area-inset-bottom));
}
.ps-header {
  position: sticky;
  top: 0;
  z-index: 50;
  background: color-mix(in srgb, var(--bg-50) 92%, transparent);
  -webkit-backdrop-filter: blur(20px);
  backdrop-filter: blur(20px);
  border-bottom: 0.5px solid var(--bg-300);
}
.ps-header__inner {
  max-width: 720px;
  margin: 0 auto;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.ps-back {
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.04);
  color: #222;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.ps-back :deep(svg) { width: 22px; height: 22px; }
.ps-search {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 12px;
  background: var(--bg-200);
  border-radius: 12px;
  color: var(--text-400);
  min-width: 0;
}
.ps-search__icon { flex-shrink: 0; }
.ps-search :deep(svg) { width: 16px; height: 16px; }
.ps-search__input {
  flex: 1;
  border: none;
  background: transparent;
  outline: none;
  font-size: 14px;
  color: var(--text-800);
  min-width: 0;
}
.ps-search__input::placeholder { color: var(--text-400); }
.ps-search__clear {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.08);
  color: var(--text-500);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.ps-search__go {
  flex-shrink: 0;
  height: 32px;
  padding: 0 14px;
  border: none;
  border-radius: 16px;
  background: var(--brand-500, #2e6bff);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}
.ps-guide {
  max-width: 720px;
  margin: 0 auto;
  padding: 32px 20px;
}
.ps-guide__title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-700);
  margin-bottom: 16px;
}
.ps-guide__tags { display: flex; flex-wrap: wrap; gap: 10px; }
.ps-guide__tag {
  border: none;
  padding: 8px 16px;
  border-radius: 18px;
  background: var(--bg-200);
  color: var(--text-600);
  font-size: 13px;
  cursor: pointer;
}
.ps-results {
  max-width: 720px;
  margin: 0 auto;
  padding: 12px 16px calc(64px + env(safe-area-inset-bottom));
}
.ps-loading {
  padding: 60px 0;
  text-align: center;
  color: var(--text-400);
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.ps-loading :deep(svg) { animation: ps-spin 0.8s linear infinite; }
@keyframes ps-spin { to { transform: rotate(360deg); } }
.ps-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
@media (min-width: 540px) { .ps-grid { grid-template-columns: repeat(3, 1fr); gap: 14px; } }
@media (min-width: 768px) { .ps-grid { grid-template-columns: repeat(4, 1fr); gap: 16px; } }
.ps-card {
  border-radius: 14px;
  overflow: hidden;
  background: var(--bg-50);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  border: 0.5px solid var(--bg-200);
  cursor: pointer;
  display: flex;
  flex-direction: column;
}
.ps-card--item { position: relative; }
.ps-card--crystal { border-color: #c084fc; box-shadow: 0 0 0 1px rgba(192, 132, 252, 0.25); }
.ps-card__img {
  position: relative;
  aspect-ratio: 1 / 1;
  width: 100%;
  background: linear-gradient(160deg, #eef2ff, #f5f3ff);
  display: flex;
  align-items: center;
  justify-content: center;
}
.ps-card__img--pixel { background: #f0f0f3; }
.ps-card__img--crystal { background: linear-gradient(160deg, #f3e8ff, #ede9fe); }
.ps-card__photo { width: 100%; height: 100%; object-fit: cover; display: block; }
.ps-card__photo--pixel { image-rendering: pixelated; object-fit: contain; padding: 8px; }
.ps-card__emoji { font-size: 40px; }
.ps-card__tag {
  position: absolute;
  top: 8px;
  left: 8px;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 8px;
}
.ps-tag--crystal { position: absolute; top: 8px; left: 8px; }
.ps-card__owned {
  position: absolute;
  top: 8px;
  right: 8px;
  background: #22c55e;
  color: #fff;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 8px;
}
.ps-card__gain {
  position: absolute;
  bottom: 8px;
  left: 8px;
  background: rgba(255, 255, 255, 0.92);
  color: var(--text-600);
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 8px;
}
.ps-card__qty {
  position: absolute;
  bottom: 8px;
  right: 8px;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 8px;
}
.ps-card__info { padding: 10px 12px 12px; }
.ps-card__name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-800);
  margin: 0 0 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ps-card__desc {
  font-size: 12px;
  color: var(--text-500);
  margin: 0 0 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ps-card__bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 6px;
}
.ps-card__price { font-size: 13px; }
.ps-price { font-weight: 700; color: #9a6b00; }
.ps-card__sales { font-size: 11px; color: var(--text-400); }
.ps-card__buy {
  border: none;
  background: var(--brand-500, #2e6bff);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  padding: 5px 14px;
  border-radius: 14px;
  cursor: pointer;
}
.ps-card__buy:disabled { opacity: 0.6; }
.ps-empty { padding: 80px 0 60px; text-align: center; color: var(--text-400); }
.ps-empty__icon { display: block; font-size: 48px; margin-bottom: 12px; }
.ps-empty__text { font-size: 14px; margin: 0; }
.ps-load-more {
  padding: 20px 0 8px;
  text-align: center;
  font-size: 12.5px;
  color: var(--text-400);
  min-height: 40px;
}
.ps-load-more__end { opacity: 0.7; }
</style>