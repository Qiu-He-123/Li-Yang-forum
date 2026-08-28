<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '../components/native'
import {
  listPetCategories,
  listPetProducts,
  purchaseItem,
  type PetCategory,
  type PetProduct,
} from '../api/petShop'
import { getCoinsMe } from '../api/coins'
import { useSessionStore } from '../stores/session'
import { toast } from '../components/native/Toast'
import { usePetAiTracker } from '../composables/usePetAiTracker'

/**
 * 宠物商城（统一网格布局）
 * - 顶部分类 Tab：全部 / 猫粮 / 狗粮 / 零食 / 玩具 / 日用 / 医疗 / 萌宠领养（来自后端 categories 接口）
 * - 商品网格：宠物(kind=1)用像素/图片卡片，道具(kind=2)用emoji+好感卡片，进化道具(kind=3)特殊高亮
 * - 搜索 + 金币余额 + 我的宠物入口
 * - 道具快捷购买进背包
 */
const router = useRouter()
const route = useRoute()
const session = useSessionStore()

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

// ====== 分类 ======
const categoryList = ref<PetCategory[]>([])
const activeCategory = ref('全部')
// 事件触发：停留宠物商城超过后台阈值时，让宠物 AI 说一句话
usePetAiTracker({
  type: 'pet_shop',
  getDetail: () => activeCategory.value,
})
const categoryTabs = computed(() => {
  const cats = categoryList.value.map((c) => ({ name: c.name, icon: c.icon || '' }))
  // 「萌宠领养」紧跟「全部」之后（第二位）
  const petCat = cats.find((c) => c.name === '萌宠领养')
  const others = cats.filter((c) => c.name !== '萌宠领养')
  return [{ name: '全部', icon: '🏪' }, ...(petCat ? [petCat] : []), ...others]
})

// ====== 商品列表 ======
const products = ref<PetProduct[]>([])
const loading = ref(false)
const loadingMore = ref(false)
const total = ref(0)
const page = ref(1)
const PAGE_SIZE = 100 // 后端上限 100；一次拉更多，避免首屏"好多数不显示/加载次数太多"
const hasMore = computed(() => products.value.length < total.value)

const searchQuery = ref('')
const searchKeyword = ref('')

async function loadCategories() {
  try {
    const { data: resp } = await listPetCategories({ showGlobalLoading: false })
    categoryList.value = resp.data || []
  } catch {
    categoryList.value = []
  }
}

async function loadProducts() {
  loading.value = true
  page.value = 1
  try {
    const { data: resp } = await listPetProducts({
      category: activeCategory.value !== '全部' ? activeCategory.value : undefined,
      keyword: searchKeyword.value || undefined,
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
  try {
    const { data: resp } = await listPetProducts({
      category: activeCategory.value !== '全部' ? activeCategory.value : undefined,
      keyword: searchKeyword.value || undefined,
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

function selectCategory(cat: string) {
  if (activeCategory.value === cat) return
  activeCategory.value = cat
  loadProducts()
}

// ====== 购买 ======
const buyingId = ref<number | null>(null)

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
    const action = product.kind === 3 ? '进化水晶已入背包，好感满100可用于进化！' : '已购买，去喂宠物涨好感吧！'
    toast.success(`「${product.name}」${action}`)
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { msg?: string } } })?.response?.data?.msg
    toast.error(msg || '购买失败，请稍后再试')
  } finally {
    buyingId.value = null
  }
}

function onSearch() {
  searchKeyword.value = searchQuery.value.trim()
  loadProducts()
}

// 移动端搜索图标：进入独立商品搜索页
function goSearch() {
  router.push('/pet-shop/search')
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
  if (p.kind === 1) return 'product-card product-card--pet'
  if (p.kind === 3) return 'product-card product-card--item product-card--crystal'
  return 'product-card product-card--item'
}

// 滚动加载
const loadMoreSentinel = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null

// 哨兵元素在 v-else 里，初始 loading=true 时尚未渲染，onMounted 时 observe(null) 会漏挂。
// 改为在 loading 变 false、列表渲染完成后再挂从根部观察，彻底修掉"更多商品加载不出来"。
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
  if (!l) {
    // 等哨兵元素进入 DOM 后再挂载观察器（用 post 刷帧，确保模板 ref 已就位）
    createObserver()
  }
}, { flush: 'post' })

onMounted(() => {
  loadCategories()
  loadCoins()
  // 支持 /pet-shop?category=零食 直达指定分类（宠物"饿了"跳转零食）
  const q = route.query.category
  if (typeof q === 'string' && q) {
    activeCategory.value = q
  }
  loadProducts()
  createObserver()
  // 切换分类时列表会先清空并回到 loading，等重新渲染后自动重挂（watch 已覆盖）
})

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
})

function formatPrice(price: number): string {
  return price.toFixed(price % 1 === 0 ? 0 : 1)
}

function formatSales(sales: number): string {
  if (sales >= 10000) return (sales / 10000).toFixed(1) + '万'
  if (sales >= 1000) return (sales / 1000).toFixed(1) + 'k'
  return String(sales)
}

function onCardClick(product: PetProduct) {
  // 所有商品（宠物 + 道具）点击都进入详情页
  router.push(`/pet-shop/${product.id}`)
}
</script>

<template>
  <div class="pet-shop-page">
    <!-- 顶部导航 -->
    <header class="shop-header">
      <div class="shop-header__inner">
        <button class="shop-back" type="button" aria-label="返回" @click="router.back()">
          <Icon name="chevron-left" :size="22" />
        </button>
        <h1 class="shop-title">宠物商城</h1>
        <button
          v-if="session.isLoggedIn() && coins !== null"
          class="shop-coins"
          type="button"
          title="金币余额"
          @click="router.push('/coins')"
        >
          🪙 {{ coins }}
        </button>
        <button class="shop-my-pets" type="button" @click="router.push('/pet-shop/my')">
          <Icon name="heart" :size="16" />
          <span>我的宠物</span>
        </button>
        <div class="shop-search">
          <Icon name="search" :size="16" class="shop-search__icon" />
          <input
            v-model="searchQuery"
            class="shop-search__input"
            type="text"
            placeholder="搜索商品..."
            @keyup.enter="onSearch"
          />
        </div>
        <!-- 移动端：仅搜索图标，点击进入独立搜索页 -->
        <button class="shop-search-btn" type="button" aria-label="搜索" @click="goSearch">
          <Icon name="search" :size="19" />
        </button>
      </div>
    </header>

    <!-- 分类 Tab（全部/猫粮/狗粮/零食/玩具/日用/医疗/萌宠领养） -->
    <div class="shop-categories">
      <div class="shop-categories__scroll">
        <button
          v-for="cat in categoryTabs"
          :key="cat.name"
          class="shop-cat"
          :class="{ 'is-active': activeCategory === cat.name }"
          @click="selectCategory(cat.name)"
        >
          <span v-if="cat.icon" class="shop-cat__icon">{{ cat.icon }}</span>
          {{ cat.name }}
        </button>
      </div>
    </div>

    <!-- 商品网格 -->
    <main class="shop-grid-wrap">
      <div v-if="loading" class="shop-grid">
        <div v-for="i in 6" :key="'sk-' + i" class="product-card product-card--skeleton"></div>
      </div>

      <template v-else>
        <div class="shop-grid">
          <article
            v-for="product in products"
            :key="product.id"
            :class="getCardClass(product)"
            @click="onCardClick(product)"
          >
            <!-- 宠物卡片 (kind=1) -->
            <template v-if="product.kind === 1">
              <div class="product-card__img" :class="{ 'product-card__img--pixel': !!product.anim }">
                <img
                  v-if="isImageUrl(product.image_url)"
                  class="product-card__photo"
                  :class="{ 'product-card__photo--pixel': !!product.anim }"
                  :src="product.image_url!"
                  :alt="product.name"
                  loading="lazy"
                />
                <span v-else class="product-card__emoji">{{ product.image_url || '🐾' }}</span>
                <span v-if="productTag(product)" class="product-card__tag">{{ productTag(product) }}</span>
                <span v-if="product.owned" class="product-card__owned">已领养 ✓</span>
              </div>
              <div class="product-card__info">
                <h3 class="product-card__name">{{ product.name }}</h3>
                <div class="product-card__bottom">
                  <div class="product-card__price">
                    <span class="price-current">🪙{{ formatPrice(product.price) }}</span>
                  </div>
                  <span class="product-card__sales">已售 {{ formatSales(product.sales) }}</span>
                </div>
              </div>
            </template>

            <!-- 道具/进化水晶卡片 (kind=2/3) -->
            <template v-else>
              <div class="item-card__img" :class="{ 'item-card__img--crystal': product.kind === 3 }">
                <span class="item-card__emoji">{{ product.image_url || '📦' }}</span>
                <span v-if="product.kind === 2 && (product.affinity_gain > 0 || (product.attrs?.satiety || 0) > 0)" class="item-card__gain">
                  饱腹 +{{ product.attrs?.satiety || 0 }} · 好感 +{{ product.affinity_gain || 0 }}
                </span>
                <span v-if="product.kind === 3" class="item-card__tag item-card__tag--crystal">💎 进化必需</span>
                <span v-if="product.bag_qty" class="item-card__qty">背包 ×{{ product.bag_qty }}</span>
              </div>
              <div class="item-card__info">
                <h3 class="item-card__name">{{ product.name }}</h3>
                <p class="item-card__desc">{{ product.description }}</p>
                <div class="item-card__bottom">
                  <div class="product-card__price">
                    <span class="price-current">🪙{{ formatPrice(product.price) }}</span>
                  </div>
                  <button
                    class="item-card__buy"
                    :class="{ 'item-card__buy--crystal': product.kind === 3 }"
                    type="button"
                    :disabled="buyingId === product.id"
                    @click.stop="onQuickBuy(product)"
                  >
                    {{ buyingId === product.id ? '购买中…' : (product.kind === 3 ? '购买' : '购买') }}
                  </button>
                </div>
              </div>
            </template>
          </article>
        </div>

        <div v-if="products.length === 0" class="shop-empty">
          <span class="shop-empty__icon">🔍</span>
          <p class="shop-empty__text">没有找到相关商品</p>
        </div>

        <div ref="loadMoreSentinel" class="shop-load-more">
          <span v-if="loadingMore">加载中...</span>
          <span v-else-if="!hasMore && products.length > 0" class="shop-load-more__end">— 已经到底啦 —</span>
        </div>
      </template>
    </main>
  </div>
</template>

<style scoped>
.pet-shop-page {
  min-height: 100vh;
  background: var(--bg-100);
  padding-bottom: calc(72px + env(safe-area-inset-bottom));
}

/* ====== 顶部导航 ====== */
.shop-header {
  position: sticky;
  top: 0;
  z-index: 50;
  background: color-mix(in srgb, var(--bg-50) 92%, transparent);
  -webkit-backdrop-filter: blur(20px);
  backdrop-filter: blur(20px);
  border-bottom: 0.5px solid var(--bg-300);
}
.shop-header__inner {
  max-width: 720px;
  margin: 0 auto;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.shop-back {
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
.shop-back :deep(svg) { width: 22px; height: 22px; }
.shop-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-900);
  white-space: nowrap;
  margin: 0;
}
.shop-search {
  display: none; /* 移动端隐藏输入框，改用搜索图标按钮 */
  flex: 1;
  align-items: center;
  gap: 8px;
  height: 34px;
  padding: 0 12px;
  background: var(--bg-200);
  border-radius: 10px;
  color: var(--text-400);
  min-width: 0;
}
.shop-search__icon { flex-shrink: 0; }
.shop-search :deep(svg) { width: 16px; height: 16px; }
.shop-search__input {
  flex: 1;
  border: none;
  background: transparent;
  outline: none;
  font-size: 14px;
  color: var(--text-800);
  min-width: 0;
}
.shop-search__input::placeholder { color: var(--text-400); }

/* 移动端搜索图标按钮（默认展示，桌面端隐藏） */
.shop-search-btn {
  display: inline-flex;
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  border: none;
  background: var(--bg-200);
  color: var(--text-600);
  cursor: pointer;
  align-items: center;
  justify-content: center;
}

.shop-coins {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  height: 32px;
  padding: 0 11px;
  border: none;
  border-radius: 16px;
  background: linear-gradient(135deg, #fff3d6, #ffe7b3);
  color: #9a6b00;
  font-size: 12.5px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
}
.shop-my-pets {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 32px;
  padding: 0 10px;
  border: 1px solid var(--bg-200);
  border-radius: 16px;
  background: var(--bg-50);
  color: var(--text-600);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.shop-my-pets :deep(svg) { width: 14px; height: 14px; }

/* ====== 分类 Tab ====== */
.shop-categories {
  max-width: 720px;
  margin: 0 auto;
  padding: 10px 0 8px;
  position: sticky;
  top: 59px;
  z-index: 40;
  background: var(--bg-100);
}
.shop-categories__scroll {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 0 16px 4px;
  scrollbar-width: none;
}
.shop-categories__scroll::-webkit-scrollbar { display: none; }
.shop-cat {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 7px 14px;
  border: none;
  border-radius: 18px;
  background: var(--bg-200);
  color: var(--text-600);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 150ms ease;
  white-space: nowrap;
}
.shop-cat.is-active {
  background: var(--brand-500);
  color: #fff;
  font-weight: 600;
}
.shop-cat__icon { font-size: 14px; line-height: 1; }

/* ====== 商品网格 ====== */
.shop-grid-wrap {
  max-width: 720px;
  margin: 0 auto;
  padding: 8px 16px 24px;
}
.shop-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.product-card {
  background: var(--bg-50);
  border-radius: 16px;
  overflow: hidden;
  cursor: pointer;
  transition: transform 150ms ease, box-shadow 150ms ease;
  border: 1px solid rgba(23, 32, 64, 0.08);
  box-shadow: 0 3px 14px rgba(23, 32, 64, 0.1);
}
.product-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 22px rgba(23, 32, 64, 0.16);
}

/* 宠物卡片 */
.product-card--pet { cursor: pointer; }
.product-card__img {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  background: linear-gradient(135deg, var(--bg-100), var(--bg-200));
  display: flex;
  align-items: center;
  justify-content: center;
}
.product-card__emoji { font-size: 56px; line-height: 1; }
.product-card__photo {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.product-card__img--pixel {
  background:
    radial-gradient(circle at 30% 22%, #fff4de 0%, transparent 52%),
    radial-gradient(circle at 74% 68%, #e3edff 0%, transparent 52%),
    linear-gradient(165deg, #f7f9ff 0%, #fdf5ff 100%);
}
.product-card__img--pixel::after {
  content: '';
  position: absolute;
  bottom: 12px;
  left: 50%;
  width: 56%;
  height: 22px;
  transform: translateX(-50%);
  background: radial-gradient(ellipse at center, rgba(23, 32, 64, 0.13) 0%, transparent 68%);
  pointer-events: none;
}
.product-card__photo--pixel {
  position: relative;
  z-index: 1;
  object-fit: contain;
  padding: 12px 12px 26px;
  image-rendering: pixelated;
}
.product-card__owned {
  position: absolute;
  bottom: 8px;
  right: 8px;
  padding: 3px 8px;
  background: rgba(63, 186, 122, 0.92);
  color: #fff;
  font-size: 10.5px;
  font-weight: 600;
  border-radius: 6px;
}
.product-card__tag {
  position: absolute;
  top: 8px;
  left: 8px;
  padding: 3px 8px;
  background: #ff3b30;
  color: #fff;
  font-size: 10.5px;
  font-weight: 600;
  border-radius: 6px;
}
.product-card__info { padding: 10px 12px 12px; }
.product-card__name {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-900);
  line-height: 1.4;
  margin: 0 0 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.product-card__bottom {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
}
.product-card__price {
  display: flex;
  align-items: baseline;
  gap: 4px;
}
.price-current {
  font-size: 16px;
  font-weight: 700;
  color: #ff3b30;
}
.product-card__sales {
  font-size: 11px;
  color: var(--text-400);
}

/* 道具卡片 */
.product-card--item { cursor: pointer; }
.item-card__img {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(circle at 30% 22%, #fff4de 0%, transparent 52%),
    radial-gradient(circle at 74% 68%, #ffe8d6 0%, transparent 52%),
    linear-gradient(165deg, #fffaf2 0%, #fff3e8 100%);
}
.item-card__img--crystal {
  background:
    radial-gradient(circle at 50% 40%, rgba(139, 92, 246, 0.2) 0%, transparent 60%),
    linear-gradient(165deg, #f5f0ff 0%, #ede9fe 100%);
}
.item-card__emoji {
  font-size: 52px;
  line-height: 1;
  filter: drop-shadow(0 6px 12px rgba(154, 107, 0, 0.18));
}
.item-card__gain {
  position: absolute;
  top: 8px;
  left: 8px;
  padding: 3px 8px;
  border-radius: 6px;
  background: linear-gradient(135deg, #ff6b81, #ff3b5c);
  color: #fff;
  font-size: 10.5px;
  font-weight: 700;
}
.item-card__tag {
  position: absolute;
  top: 8px;
  left: 8px;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 10.5px;
  font-weight: 700;
}
.item-card__tag--crystal {
  background: linear-gradient(135deg, #a78bfa, #7c3aed);
  color: #fff;
}
.item-card__qty {
  position: absolute;
  bottom: 8px;
  right: 8px;
  padding: 3px 8px;
  border-radius: 6px;
  background: rgba(63, 186, 122, 0.92);
  color: #fff;
  font-size: 10.5px;
  font-weight: 600;
}
.item-card__info { padding: 10px 12px 12px; }
.item-card__name {
  margin: 0 0 3px;
  font-size: 13.5px;
  font-weight: 700;
  color: var(--text-900);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.item-card__desc {
  margin: 0 0 8px;
  font-size: 11px;
  color: var(--text-500);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 16px;
}
.item-card__bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.item-card__buy {
  padding: 6px 14px;
  border: none;
  border-radius: 14px;
  background: linear-gradient(135deg, #5b8cff, #3d7bff);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(61, 123, 255, 0.25);
}
.item-card__buy--crystal {
  background: linear-gradient(135deg, #a78bfa, #7c3aed);
  box-shadow: 0 2px 8px rgba(124, 58, 237, 0.3);
}
.item-card__buy:disabled { opacity: 0.6; cursor: not-allowed; }

.product-card--skeleton {
  aspect-ratio: auto;
  min-height: 200px;
  background: linear-gradient(100deg, var(--bg-100) 40%, var(--bg-200) 50%, var(--bg-100) 60%);
  background-size: 200% 100%;
  animation: shop-skeleton-wave 1.2s ease-in-out infinite;
}
@keyframes shop-skeleton-wave { to { background-position: -200% 0; } }

.shop-load-more {
  padding: 20px 0 8px;
  text-align: center;
  font-size: 12.5px;
  color: var(--text-400);
  min-height: 40px;
}
.shop-load-more__end { opacity: 0.7; }

.shop-empty {
  padding: 80px 0 60px;
  text-align: center;
  color: var(--text-400);
}
.shop-empty__icon { display: block; font-size: 48px; margin-bottom: 12px; }
.shop-empty__text { font-size: 14px; margin: 0; }

@media (min-width: 540px) {
  .shop-grid { grid-template-columns: repeat(3, 1fr); gap: 14px; }
  .shop-search { display: flex; }
  .shop-search-btn { display: none; }
}
@media (min-width: 768px) {
  .shop-grid { grid-template-columns: repeat(4, 1fr); gap: 16px; }
}
</style>
