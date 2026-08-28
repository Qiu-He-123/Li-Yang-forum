<script setup lang="ts">
/**
 * 宠物详情页（增强版）
 * - 未领养：商品展示 + 金币领养（原有功能）
 * - 已领养：等级/好感进度 + 升级方案时间线 + 快速互动（喂食/摸头/玩耍）+ 冷却提示
 *           + 进化（好感满100+水晶）+ 昵称自定义（进化后）+ 放到桌面 + 遗弃
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import { useSessionStore } from '../stores/session'
import { useUIStore } from '../stores/ui'
import {
  adoptPet,
  fetchPetProduct,
  getUpgradePlan,
  feedPet,
  interactPet,
  evolvePet,
  setPetNickname,
  abandonPet,
  listMyBag,
  purchaseItem,
  adoptSlot,
  type PetProduct,
  type MyPetItem,
  type UpgradePlanResp,
  type InteractResp,
  type BagItem,
  formatCooldown,
  PET_LEVEL_NAMES,
} from '../api/petShop'
import { getCoinsMe } from '../api/coins'
import PetAnimation from '../components/pet/PetAnimation.vue'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const uiStore = useUIStore()

const productId = computed(() => Number(route.params.id))
const loading = ref(false)
const loadError = ref('')

// 道具类商品（kind=2 食物/玩具/日用/医疗，kind=3 进化道具，kind=4 宠物领养位）：详情页走道具布局
const isItem = computed(() => product.value?.kind === 2 || product.value?.kind === 3 || product.value?.kind === 4)
// 宠物领养位（kind=4）：购买后永久 +1 宠物名额，走独立购买接口
const isSlot = computed(() => product.value?.kind === 4)
const itemBuying = ref(false)

// ====== 商品基础数据 ======
const product = ref<PetProduct | null>(null)
const coins = ref<number | null>(null)
const owned = ref(false)

// ====== 已领养宠物状态 ======
const myPet = ref<MyPetItem | null>(null)
const planData = ref<UpgradePlanResp | null>(null)
const bag = ref<BagItem[]>([])
const bagTotal = ref(0)

// 操作状态
const adopting = ref(false)
const acting = ref<string | null>(null) // 'feed' | 'pet' | 'play' | 'evolve'
const evolving = ref(false)
const summoned = ref(false)

// 昵称编辑
const editingNickname = ref(false)
const nicknameInput = ref('')
const savingNickname = ref(false)

// 遗弃确认
const confirmAbandon = ref(false)
const abandoning = ref(false)
let abandonTimer: number | null = null

// ====== 做动作 / 背包 ======
const animRef = ref<InstanceType<typeof PetAnimation> | null>(null)
const actionMenuOpen = ref(false)

// 动作 key → 图标
const ACTION_EMOJI: Record<string, string> = {
  stand: '✨', walk: '🐾', sleep: '💤', interact: '💕', fly: '🕊️', descend: '🪽',
}
function actionEmoji(key: string): string { return ACTION_EMOJI[key] || '🎭' }

/** 打开「做动作」弹窗（仅当宠物有帧动画动作时） */
function openActionMenu() {
  if (!product.value?.anim?.actions?.length) {
    toast.info('这只宠物还没有可展示的动作')
    return
  }
  actionMenuOpen.value = true
}

/** 选择动作并播放 */
function doAction(key: string, label: string) {
  try { animRef.value?.switchAction(key) } catch { /* 动画未就绪时忽略 */ }
  actionMenuOpen.value = false
  toast.success(`${myPet?.value?.nickname || product.value?.name || ''}做了「${label}」~`)
}

/** 前往背包页（携带当前宠物作为默认使用对象） */
function openBackpack() {
  router.push({ path: '/pet-backpack', query: myPet.value ? { pet: String(myPet.value.id) } : {} })
}

async function loadCoins() {
  if (!session.isLoggedIn()) { coins.value = null; return }
  try {
    const { data: resp } = await getCoinsMe()
    coins.value = resp.data.coins
  } catch { coins.value = null }
}

const coinsNotEnough = computed(() =>
  coins.value !== null && product.value !== null && !owned.value && coins.value < Math.ceil(product.value.price),
)

async function loadProduct() {
  loading.value = true
  loadError.value = ''
  try {
    const { data: resp } = await fetchPetProduct(productId.value)
    product.value = resp.data
    owned.value = !!resp.data.owned
    if (product.value?.model_3d_url && !product.value?.anim) {
      loadModelViewer().then((ready) => { modelViewerReady.value = ready })
    } else {
      modelViewerReady.value = false
    }
    // 如果已领养，加载宠物状态和升级方案
    if (owned.value && session.isLoggedIn()) {
      await Promise.all([loadMyPetData(), loadBag()])
    } else {
      myPet.value = null
      planData.value = null
      // 道具：加载背包以展示持有数量
      if ((product.value?.kind ?? 1) !== 1 && session.isLoggedIn()) {
        await loadBag()
      }
    }
  } catch (err) {
    loadError.value = (err as Error).message || '商品不存在或已下架'
    product.value = null
  } finally {
    loading.value = false
  }
}

async function loadMyPetData() {
  try {
    const { data: resp } = await getUpgradePlan(productId.value, { showGlobalLoading: false, showGlobalError: false })
    planData.value = resp.data
    myPet.value = resp.data.pet
  } catch {
    planData.value = null
    myPet.value = null
  }
}

async function loadBag() {
  if (!session.isLoggedIn()) return
  try {
    const { data: resp } = await listMyBag({ showGlobalLoading: false, showGlobalError: false })
    bag.value = resp.data.items || []
    bagTotal.value = resp.data.total_qty || 0
  } catch { bag.value = []; bagTotal.value = 0 }
}

/** 已领养宠物放到桌面 */
function onSummonToDesktop() {
  if (!product.value) return
  localStorage.setItem('floating_pet_id', String(product.value.id))
  localStorage.removeItem('floating_pet_hidden')
  window.dispatchEvent(new CustomEvent('floating-pet:select', { detail: product.value.id }))
  window.dispatchEvent(new Event('floating-pet:summon'))
  summoned.value = true
  window.setTimeout(() => (summoned.value = false), 2200)
  toast.success('宠物已召唤到桌面~')
}

async function onAdopt() {
  if (!product.value) return
  if (!session.isLoggedIn()) { uiStore.openAuthDialog(); return }
  if (owned.value) { toast.info('你已经领养过这只宠物啦'); return }
  if (adopting.value) return
  adopting.value = true
  try {
    const { data: resp } = await adoptPet(product.value.id)
    owned.value = true
    coins.value = resp.data.coins
    product.value.stock = Math.max(0, product.value.stock - 1)
    product.value.sales += 1
    toast.success(`领养成功！${product.value.name} 已加入你的宠物窝`)
    await Promise.all([loadMyPetData(), loadBag()])
  } catch { /* 拦截器处理 */ }
  finally { adopting.value = false }
}

/** 购买道具（kind=2/3）进背包 */
async function onBuyItem() {
  if (!product.value) return
  if (!session.isLoggedIn()) { uiStore.openAuthDialog(); return }
  if (itemBuying.value) return
  itemBuying.value = true
  try {
    const { data: resp } = await purchaseItem(product.value.id, { showGlobalLoading: false })
    coins.value = resp.data.coins
    product.value.stock = Math.max(0, product.value.stock - 1)
    product.value.sales += 1
    await loadBag()
    const tip = product.value.kind === 3
      ? '进化水晶已入背包，好感满100可用于进化！'
      : `「${product.value.name}」已放入背包，去喂宠物吧！`
    toast.success(tip)
  } catch (e: unknown) {
    handleActionError(e)
  } finally {
    itemBuying.value = false
  }
}

/** 购买"宠物领养位"（kind=4）：永久 +1 宠物名额，突破基础上限 */
async function onBuySlot() {
  if (!product.value) return
  if (!session.isLoggedIn()) { uiStore.openAuthDialog(); return }
  if (itemBuying.value) return
  itemBuying.value = true
  try {
    const { data: resp } = await adoptSlot(product.value.id, { showGlobalLoading: false })
    coins.value = resp.data.coins
    product.value.stock = Math.max(0, product.value.stock - 1)
    product.value.sales += 1
    toast.success(`领养位 +1！现在最多可同时养 ${resp.data.max_owned} 只宠物`)
  } catch (e: unknown) {
    handleActionError(e)
  } finally {
    itemBuying.value = false
  }
}

// ====== 互动操作 ======
async function onFeed() {
  if (!myPet.value || acting.value) return
  if (myPet.value.cooldowns.feed > 0) {
    toast.info(`宠物还不饿呢，${formatCooldown(myPet.value.cooldowns.feed)}再来吧~`)
    return
  }
  if (bagTotal.value <= 0) {
    toast.info('背包空空的，先去商城买点食物吧')
    setTimeout(() => router.push('/pet-shop'), 800)
    return
  }
  acting.value = 'feed'
  try {
    const { data: resp } = await feedPet(myPet.value.id, undefined, { showGlobalLoading: false })
    bag.value = resp.data.bag
    bagTotal.value = bag.value.reduce((n, b) => n + b.qty, 0)
    handleInteractResult(resp.data, '喂食')
    if (resp.data.can_evolve) showEvolutionHint()
  } catch (e: unknown) {
    handleActionError(e)
  } finally {
    acting.value = null
    await loadMyPetData()
  }
}

async function onPet() {
  if (!myPet.value || acting.value) return
  if (myPet.value.cooldowns.pet > 0) {
    toast.info(`刚刚摸过啦，${formatCooldown(myPet.value.cooldowns.pet)}再来吧~`)
    return
  }
  acting.value = 'pet'
  try {
    const { data: resp } = await interactPet(myPet.value.id, 'pet', { showGlobalLoading: false })
    handleInteractResult(resp.data, '摸摸头')
    if (resp.data.can_evolve) showEvolutionHint()
  } catch (e: unknown) {
    handleActionError(e)
  } finally {
    acting.value = null
    await loadMyPetData()
  }
}

async function onPlay() {
  if (!myPet.value || acting.value) return
  if (myPet.value.cooldowns.play > 0) {
    toast.info(`刚玩过啦，${formatCooldown(myPet.value.cooldowns.play)}再来吧~`)
    return
  }
  acting.value = 'play'
  try {
    const { data: resp } = await interactPet(myPet.value.id, 'play', { showGlobalLoading: false })
    handleInteractResult(resp.data, '玩耍')
    if (resp.data.can_evolve) showEvolutionHint()
  } catch (e: unknown) {
    handleActionError(e)
  } finally {
    acting.value = null
    await loadMyPetData()
  }
}

function handleInteractResult(data: InteractResp, actionName: string) {
  if (data.gained > 0) {
    let msg = `${actionName}成功！`
    if (data.leveled_up) msg += ` 🎉升级到Lv${data.level}！`
    else msg += ` 好感+${data.gained}`
    if (data.daily_remaining <= 0) msg += '（今日好感已达上限）'
    toast.success(msg)
  } else if (data.daily_remaining <= 0) {
    toast.info('今日好感已达上限，明天再来吧~')
  } else {
    toast.info('刚刚互动过，让宠物歇会儿吧~')
  }
}

function handleActionError(e: unknown) {
  const err = e as { response?: { data?: { msg?: string | { msg?: string } } }, status?: number }
  const detail = err?.response?.data?.msg
  let text = '操作失败了'
  if (typeof detail === 'string') text = detail
  else if (detail && typeof detail === 'object' && 'msg' in detail) text = (detail as { msg?: string }).msg || text
  toast.error(text)
}

function showEvolutionHint() {
  setTimeout(() => {
    toast.success('💎 好感度已满！持有进化水晶即可超级进化~')
  }, 1500)
}

// ====== 进化 ======
async function onEvolve() {
  if (!myPet.value || evolving.value) return
  if (myPet.value.evolved) { toast.info('已经进化过啦'); return }
  if (myPet.value.affinity < 100) { toast.info('好感度未满100，还不能进化哦'); return }
  // 检查是否有进化水晶
  const hasCrystal = bag.value.some(b => b.kind === 3 && b.qty > 0)
  if (!hasCrystal) {
    toast.info('背包中没有进化水晶，去商城购买吧')
    setTimeout(() => router.push('/pet-shop'), 800)
    return
  }
  evolving.value = true
  try {
    const { data: resp } = await evolvePet(myPet.value.id, { showGlobalLoading: false })
    toast.success(resp.data.msg || '进化成功！🎉')
    await Promise.all([loadMyPetData(), loadBag(), loadCoins()])
    // 进化后弹出昵称编辑
    setTimeout(() => {
      nicknameInput.value = myPet.value?.nickname || product.value?.name || ''
      editingNickname.value = true
    }, 1000)
  } catch (e: unknown) { handleActionError(e) }
  finally { evolving.value = false }
}

// ====== 昵称 ======
function startEditNickname() {
  nicknameInput.value = myPet.value?.nickname || product.value?.name || ''
  editingNickname.value = true
}

async function saveNickname() {
  if (!myPet.value || savingNickname.value) return
  const name = nicknameInput.value.trim()
  if (!name) { toast.error('昵称不能为空'); return }
  if (name.length > 12) { toast.error('昵称最多12个字'); return }
  savingNickname.value = true
  try {
    await setPetNickname(myPet.value.id, name, { showGlobalLoading: false })
    myPet.value.nickname = name
    if (planData.value) planData.value.pet.nickname = name
    toast.success('昵称已更新~')
    editingNickname.value = false
  } catch (e: unknown) { handleActionError(e) }
  finally { savingNickname.value = false }
}

// ====== 遗弃 ======
function onAbandonClick() {
  if (abandoning.value) return
  if (!confirmAbandon.value) {
    confirmAbandon.value = true
    if (abandonTimer !== null) window.clearTimeout(abandonTimer)
    abandonTimer = window.setTimeout(() => (confirmAbandon.value = false), 5000)
    return
  }
  void doAbandon()
}

async function doAbandon() {
  if (!myPet.value) return
  abandoning.value = true
  try {
    await abandonPet(myPet.value.id, { showGlobalLoading: false })
    toast.success(`${product.value?.name || '宠物'}被遗弃了…好感度已清零`)
    owned.value = false
    myPet.value = null
    planData.value = null
    confirmAbandon.value = false
    window.dispatchEvent(new Event('floating-pet:reload'))
  } catch (e: unknown) { handleActionError(e) }
  finally { abandoning.value = false }
}

// ====== 3D 模型按需加载 ======
const modelViewerReady = ref(false)
let modelViewerLoading: Promise<boolean> | null = null
function loadModelViewer(): Promise<boolean> {
  if (typeof window === 'undefined') return Promise.resolve(false)
  if (customElements.get('model-viewer')) return Promise.resolve(true)
  if (modelViewerLoading) return modelViewerLoading
  modelViewerLoading = new Promise((resolve) => {
    const script = document.createElement('script')
    script.type = 'module'
    script.src = 'https://unpkg.com/@google/model-viewer@4.0.0/dist/model-viewer.min.js'
    script.onload = () => resolve(true)
    script.onerror = () => resolve(false)
    document.head.appendChild(script)
  })
  return modelViewerLoading
}

function isImageUrl(url: string | null | undefined): boolean {
  if (!url) return false
  return url.startsWith('/') || url.startsWith('http')
}

function onBack() {
  if (window.history.length > 1) router.back()
  else router.push('/pet-shop')
}

function formatPrice(p: number): string { return Math.round(p).toString() }
function formatSales(s: number): string {
  if (s >= 10000) return (s / 10000).toFixed(1) + '万'
  if (s >= 1000) return (s / 1000).toFixed(1) + 'k'
  return String(s)
}

// 升级步骤解锁动作中文名
const UNLOCK_LABELS: Record<string, string> = {
  stand: '待机', sleep: '睡觉', interact: '互动', walk: '散步', fly: '飞行', evolve: '超级进化',
}
function unlockLabel(key: string): string { return UNLOCK_LABELS[key] || key }

// 好感度百分比进度
const affinityPct = computed(() => {
  if (!myPet.value) return 0
  return Math.min(100, myPet.value.affinity)
})

// 当前等级的下一级好感需求
const nextLevelInfo = computed(() => myPet.value?.next_level || null)

onMounted(() => {
  loadProduct()
  loadCoins()
})

watch(productId, () => {
  if (route.name === 'pet-shop-detail') {
    loadProduct()
    loadCoins()
    confirmAbandon.value = false
    editingNickname.value = false
  }
})
</script>

<template>
  <div class="pet-detail-page">
    <!-- 顶部导航 -->
    <header class="pd-header">
      <button class="pd-header__btn" type="button" @click="onBack">
        <Icon name="chevron-left" :size="22" />
      </button>
      <button class="pd-header__btn" type="button">
        <Icon name="share" :size="20" />
      </button>
    </header>

    <!-- 加载中 -->
    <div v-if="loading" class="pd-state">
      <div class="pd-state__spinner"></div>
      <p class="pd-state__text">加载中...</p>
    </div>

    <!-- 加载失败 -->
    <div v-else-if="!product" class="pd-state">
      <span class="pd-state__emoji">🐾</span>
      <p class="pd-state__text">{{ loadError || '商品不存在或已下架' }}</p>
      <button class="pd-state__btn" type="button" @click="onBack">返回商城</button>
    </div>

    <template v-else>
      <!-- ====== Hero 动画区 ====== -->
      <div class="pd-hero" :class="{ 'pd-hero--anim': !!product.anim, 'pd-hero--evolved': myPet?.evolved }">
        <div v-if="product.anim" class="pd-hero__anim">
          <div class="pd-hero__anim-stage">
            <PetAnimation ref="animRef" :anim="product.anim" :size="230" :show-tabs="false" />
          </div>
          <!-- 已领养：显示等级徽章在动画区 -->
          <div v-if="myPet" class="pd-hero__pet-badges">
            <span class="pd-badge pd-badge--level">
              Lv{{ myPet.level }} {{ myPet.level_name }}
            </span>
            <span v-if="myPet.evolved" class="pd-badge pd-badge--evolved">✨ 灵魂伴侣</span>
          </div>
        </div>
        <div v-else-if="product.model_3d_url && modelViewerReady" class="pd-hero__3d">
          <model-viewer :src="product.model_3d_url" alt="宠物 3D 模型" camera-controls
            auto-rotate rotation-per-second="30deg" shadow-intensity="1"
            environment-image="neutral" exposure="1" class="pd-hero__model">
            <div slot="progress-bar" class="pd-hero__model-progress"></div>
          </model-viewer>
        </div>
        <template v-else>
          <img v-if="isImageUrl(product.image_url)" class="pd-hero__photo" :src="product.image_url!" :alt="product.name" />
          <span v-else class="pd-hero__emoji">{{ product.image_url || '🐾' }}</span>
        </template>
        <span v-if="isItem && product.kind === 3" class="pd-hero__tag pd-hero__tag--crystal">💎 进化道具</span>
        <span v-else-if="isItem && product.kind === 4" class="pd-hero__tag pd-hero__tag--item">🪺 宠物领养位</span>
        <span v-else-if="isItem" class="pd-hero__tag pd-hero__tag--item">宠物道具</span>
        <span v-else-if="product.anim && !myPet" class="pd-hero__tag">像素宠物</span>
        <span v-else-if="product.model_3d_url" class="pd-hero__tag">3D 展示</span>
      </div>

      <!-- ====== 价格/名称区（未领养） ====== -->
      <section v-if="!owned" class="pd-price-card">
        <div class="pd-price-row">
          <span class="pd-price-current">🪙 {{ formatPrice(product.price) }}</span>
          <span v-if="product.original_price" class="pd-price-original">🪙 {{ formatPrice(product.original_price) }}</span>
          <span v-if="product.original_price" class="pd-price-discount">
            {{ Math.round((1 - product.price / product.original_price) * 10) }}折
          </span>
        </div>
        <h1 class="pd-title">{{ product.name }}</h1>
        <div class="pd-meta">
          <span class="pd-meta__item">已售 {{ formatSales(product.sales) }}</span>
          <span class="pd-meta__divider">·</span>
          <span class="pd-meta__item">库存 {{ product.stock }}</span>
          <template v-if="product.category">
            <span class="pd-meta__divider">·</span>
            <span class="pd-meta__item">{{ product.category }}</span>
          </template>
        </div>
        <div v-if="session.isLoggedIn() && coins !== null" class="pd-coins" :class="{ 'is-not-enough': coinsNotEnough }">
          <template v-if="coinsNotEnough">
            ⚠️ 金币余额 {{ coins }}，还差 {{ formatPrice(product.price - coins) }} {{ isItem ? '可购买' : '可领养' }}
            <button class="pd-coins__link" type="button" @click="router.push('/coins')">去赚金币</button>
          </template>
          <template v-else>💰 金币余额 {{ coins }}</template>
        </div>
      </section>

      <!-- ====== 已领养：宠物信息卡 ====== -->
      <section v-else class="pd-pet-card">
        <div class="pd-pet-card__head">
          <div class="pd-pet-card__name-row">
            <h1 class="pd-title">
              {{ myPet?.nickname || product.name }}
              <span v-if="myPet?.nickname" class="pd-pet-card__orig-name">（原名：{{ product.name }}）</span>
            </h1>
            <button v-if="myPet?.evolved" class="pd-nickname-btn" type="button" @click="startEditNickname">
              ✏️ 改名
            </button>
          </div>
          <div class="pd-pet-card__tags">
            <span class="pd-pet-tag pd-pet-tag--lv">Lv{{ myPet?.level }} {{ myPet?.level_name }}</span>
            <span v-if="myPet?.evolved" class="pd-pet-tag pd-pet-tag--evolved">✨ 灵魂伴侣</span>
            <span v-else-if="myPet?.level === 5" class="pd-pet-tag pd-pet-tag--max">满级好感</span>
          </div>
        </div>

        <!-- 好感度进度条 -->
        <div class="pd-affinity">
          <div class="pd-affinity__top">
            <span class="pd-affinity__label">好感度</span>
            <span class="pd-affinity__num">{{ myPet?.affinity ?? 0 }}/100</span>
          </div>
          <div class="pd-affinity__bar">
            <i :style="{ width: affinityPct + '%' }" :class="{ 'is-full': (myPet?.affinity ?? 0) >= 100 }"></i>
            <!-- 等级节点 -->
            <span v-for="lv in [20,40,60,80,100]" :key="lv" class="pd-affinity__node" :style="{ left: lv + '%' }"></span>
          </div>
          <div class="pd-affinity__bottom">
            <span v-if="nextLevelInfo" class="pd-affinity__next">
              距 {{ nextLevelInfo.name }} 还需 {{ nextLevelInfo.affinity_needed }} 好感
            </span>
            <span v-else-if="myPet?.evolved" class="pd-affinity__next">已达最高等级</span>
            <span class="pd-affinity__daily">
              今日 {{ myPet?.daily_affinity.gained ?? 0 }}/{{ myPet?.daily_affinity.cap ?? 20 }}
            </span>
          </div>
        </div>
      </section>

      <!-- ====== 未领养/道具：商品描述 ====== -->
      <template v-if="!owned">
        <!-- 道具详情（kind=2/3） -->
        <template v-if="isItem">
          <section class="pd-section">
            <div class="pd-section__title">道具详情</div>
            <p class="pd-desc">{{ product.description || '暂无道具介绍。' }}</p>
          </section>
          <section class="pd-section">
            <div class="pd-section__title">道具档案</div>
            <div class="pd-params">
              <div class="pd-param-row">
                <span class="pd-param__label">道具类型</span>
                <span class="pd-param__value">{{ product.kind === 3 ? '💎 进化道具' : '🎁 宠物道具' }}</span>
              </div>
              <div class="pd-param-row">
                <span class="pd-param__label">所属分类</span>
                <span class="pd-param__value">{{ product.category || '-' }}</span>
              </div>
              <div class="pd-param-row" v-if="product.kind === 2">
                <span class="pd-param__label">好感加成</span>
                <span class="pd-param__value pd-param__value--gain">+{{ product.affinity_gain }} 好感</span>
              </div>
              <div class="pd-param-row" v-if="product.kind === 3">
                <span class="pd-param__label">用途</span>
                <span class="pd-param__value">宠物好感满100后可超级进化</span>
              </div>
              <div class="pd-param-row" v-if="product && bag.some(b => b.id === product!.id && b.qty > 0)">
                <span class="pd-param__label">背包持有</span>
                <span class="pd-param__value">×{{ bag.find(b => b.id === product!.id)?.qty ?? 0 }}</span>
              </div>
              <div class="pd-param-row">
                <span class="pd-param__label">持有上限</span>
                <span class="pd-param__value">{{ product.kind === 3 ? '进化道具最多持有 1 个' : '最多持有 99 个' }}</span>
              </div>
            </div>
          </section>
          <section class="pd-section">
            <div class="pd-section__title">💡 使用说明</div>
            <p class="pd-desc">
              {{ product.kind === 3
                ? '在宠物详情页的「超级进化」中使用，消耗 1 个进化水晶。'
                : '购买后自动放入背包。在宠物详情页点击「喂食」，或桌宠饿了时点「喂食」即可消耗，提升宠物好感度并恢复饱食度。' }}
            </p>
          </section>
        </template>

        <!-- 宠物详情（kind=1） -->
        <template v-else>
          <section class="pd-section">
            <div class="pd-section__title">宠物介绍</div>
            <p class="pd-desc">{{ product.description || '暂无宠物介绍，可咨询客服了解更多详情。' }}</p>
          </section>
          <section class="pd-section">
            <div class="pd-section__title">宠物档案</div>
            <div class="pd-params">
              <div class="pd-param-row">
                <span class="pd-param__label">宠物分类</span>
                <span class="pd-param__value">{{ product.category || '-' }}</span>
              </div>
              <div class="pd-param-row" v-if="product.anim">
                <span class="pd-param__label">动作</span>
                <span class="pd-param__value">{{ product.anim.actions.map((a: { label: string }) => a.label).join(' / ') }}</span>
              </div>
              <div class="pd-param-row">
                <span class="pd-param__label">展示形式</span>
                <span class="pd-param__value">{{ product.anim ? '像素帧动画' : product.model_3d_url ? '3D 模型' : '图片' }}</span>
              </div>
              <div class="pd-param-row">
                <span class="pd-param__label">领养限制</span>
                <span class="pd-param__value">每人限领 1 只</span>
              </div>
            </div>
          </section>
        </template>
      </template>

      <!-- ====== 已领养：快速互动 ====== -->
      <template v-else>
        <section class="pd-section">
          <div class="pd-section__title">
            🎮 陪我玩
            <span class="pd-section__hint">点按钮和宠物互动，提升好感度（有冷却防刷）</span>
          </div>
          <div class="pd-actions">
            <button class="pd-action-btn pd-action-btn--feed" type="button"
              :disabled="!!acting || (myPet?.cooldowns.feed ?? 0) > 0 || bagTotal <= 0"
              @click="onFeed">
              <span class="pd-action-btn__icon">🍖</span>
              <span class="pd-action-btn__label">喂食</span>
              <span class="pd-action-btn__cd" v-if="(myPet?.cooldowns.feed ?? 0) > 0">
                {{ formatCooldown(myPet!.cooldowns.feed) }}
              </span>
              <span class="pd-action-btn__cd" v-else-if="bagTotal <= 0">无食物</span>
              <span class="pd-action-btn__cd" v-else-if="acting === 'feed'">喂食中…</span>
            </button>
            <button class="pd-action-btn pd-action-btn--pet" type="button"
              :disabled="!!acting || (myPet?.cooldowns.pet ?? 0) > 0"
              @click="onPet">
              <span class="pd-action-btn__icon">🫳</span>
              <span class="pd-action-btn__label">摸摸头</span>
              <span class="pd-action-btn__cd" v-if="(myPet?.cooldowns.pet ?? 0) > 0">
                {{ formatCooldown(myPet!.cooldowns.pet) }}
              </span>
              <span class="pd-action-btn__cd" v-else-if="acting === 'pet'">摸摸中…</span>
            </button>
            <button class="pd-action-btn pd-action-btn--play" type="button"
              :disabled="!!acting || (myPet?.cooldowns.play ?? 0) > 0"
              @click="onPlay">
              <span class="pd-action-btn__icon">🎾</span>
              <span class="pd-action-btn__label">玩耍</span>
              <span class="pd-action-btn__cd" v-if="(myPet?.cooldowns.play ?? 0) > 0">
                {{ formatCooldown(myPet!.cooldowns.play) }}
              </span>
              <span class="pd-action-btn__cd" v-else-if="acting === 'play'">玩耍中…</span>
            </button>
          </div>
          <!-- 第二行：做动作 / 背包 -->
          <div class="pd-actions pd-actions--ext">
            <button class="pd-action-btn pd-action-btn--action" type="button" @click="openActionMenu">
              <span class="pd-action-btn__icon">🎭</span>
              <span class="pd-action-btn__label">做动作</span>
            </button>
            <button class="pd-action-btn pd-action-btn--bag" type="button" @click="openBackpack">
              <span class="pd-action-btn__icon">🎒</span>
              <span class="pd-action-btn__label">背包</span>
              <span class="pd-action-btn__cd">×{{ bagTotal }}</span>
            </button>
          </div>
          <p class="pd-action-tip">
            🍱 背包食物 ×{{ bagTotal }}
            <span v-if="(myPet?.daily_affinity.remaining ?? 20) <= 0" class="pd-action-tip--warn">· 今日好感已满</span>
          </p>
        </section>

        <!-- ====== 升级方案时间线 ====== -->
        <section class="pd-section">
          <div class="pd-section__title">📈 成长路线</div>
          <div class="pd-plan">
            <div v-for="(step, idx) in planData?.plan" :key="step.level" class="pd-plan__step"
              :class="{ 'is-current': step.is_current, 'is-reached': step.is_reached, 'is-evolve': step.level === 6 }">
              <div class="pd-plan__dot">
                <span v-if="step.is_reached">✓</span>
                <span v-else>{{ step.level }}</span>
              </div>
              <div class="pd-plan__line" v-if="idx < (planData?.plan.length ?? 0) - 1"></div>
              <div class="pd-plan__content">
                <div class="pd-plan__head">
                  <span class="pd-plan__name">Lv{{ step.level }} {{ step.name }}</span>
                  <span class="pd-plan__req" v-if="!step.is_reached">好感 {{ step.affinity_required }}</span>
                  <span v-else-if="step.is_current" class="pd-plan__cur">当前</span>
                  <span v-else class="pd-plan__done">已达成</span>
                </div>
                <p class="pd-plan__desc">{{ step.desc }}</p>
                <div class="pd-plan__unlocks">
                  <span v-for="u in step.unlocks" :key="u" class="pd-plan__unlock-tag">
                    🔓 {{ unlockLabel(u) }}
                  </span>
                  <template v-if="step.level === 6 && step.evolution_item_required">
                    <span class="pd-plan__unlock-tag pd-plan__unlock-tag--crystal">
                      💎 进化水晶
                      <span :class="step.has_evolution_item ? 'is-ok' : 'is-no'">
                        {{ step.has_evolution_item ? '✓' : '×' }}
                      </span>
                    </span>
                  </template>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- ====== 超级进化区 ====== -->
        <section v-if="myPet && !myPet.evolved" class="pd-section pd-section--evolve">
          <div class="pd-evolve">
            <div class="pd-evolve__head">
              <span class="pd-evolve__icon">💎</span>
              <div>
                <h3 class="pd-evolve__title">超级进化</h3>
                <p class="pd-evolve__desc">好感度满100 + 进化水晶 → 灵魂伴侣（解锁专属昵称和光效）</p>
              </div>
            </div>
            <div class="pd-evolve__status">
              <div class="pd-evolve__cond" :class="{ 'is-ok': (myPet?.affinity ?? 0) >= 100 }">
                好感度 {{ myPet?.affinity ?? 0 }}/100
                <span v-if="(myPet?.affinity ?? 0) >= 100">✓</span>
                <span v-else>×</span>
              </div>
              <div class="pd-evolve__cond" :class="{ 'is-ok': bag.some(b => b.kind === 3 && b.qty > 0) }">
                进化水晶 {{ bag.some(b => b.kind === 3 && b.qty > 0) ? '✓' : '×' }}
              </div>
            </div>
            <button class="pd-evolve__btn" type="button"
              :disabled="evolving || (myPet?.affinity ?? 0) < 100 || !bag.some(b => b.kind === 3 && b.qty > 0)"
              @click="onEvolve">
              {{ evolving ? '进化中…' : ((myPet?.affinity ?? 0) >= 100 && bag.some(b => b.kind === 3 && b.qty > 0)) ? '✨ 立即超级进化' : '条件未满足' }}
            </button>
            <button v-if="myPet && !bag.some(b => b.kind === 3 && b.qty > 0) && myPet.affinity >= 100"
              class="pd-evolve__buy-link" type="button" @click="router.push('/pet-shop')">
              去商城购买进化水晶 →
            </button>
          </div>
        </section>

        <!-- ====== 昵称编辑弹窗 ====== -->
        <Teleport to="body">
          <div v-if="editingNickname" class="pd-modal-mask" @click.self="editingNickname = false">
            <div class="pd-modal">
              <h3 class="pd-modal__title">✏️ 给宠物起个昵称</h3>
              <p class="pd-modal__desc">最多12个字，进化后的专属特权~</p>
              <input v-model="nicknameInput" class="pd-modal__input" type="text" maxlength="12"
                placeholder="输入昵称" @keyup.enter="saveNickname" />
              <div class="pd-modal__btns">
                <button class="pd-modal__btn pd-modal__btn--cancel" type="button"
                  @click="editingNickname = false">取消</button>
                <button class="pd-modal__btn pd-modal__btn--ok" type="button"
                  :disabled="savingNickname" @click="saveNickname">
                  {{ savingNickname ? '保存中…' : '确定' }}
                </button>
              </div>
            </div>
          </div>
        </Teleport>

        <!-- ====== 做动作弹窗 ====== -->
        <Teleport to="body">
          <div v-if="actionMenuOpen" class="pd-modal-mask" @click.self="actionMenuOpen = false">
            <div class="pd-modal pd-modal--actions">
              <h3 class="pd-modal__title">🎭 让宠物做动作</h3>
              <p class="pd-modal__desc">选择一个动作，宠物会立刻表演给你看</p>
              <div class="pd-action-grid">
                <button v-for="a in product?.anim?.actions || []" :key="a.key" type="button"
                  class="pd-action-opt" @click="doAction(a.key, a.label)">
                  <span class="pd-action-opt__icon">{{ actionEmoji(a.key) }}</span>
                  <span class="pd-action-opt__label">{{ a.label }}</span>
                </button>
              </div>
              <div class="pd-modal__btns">
                <button class="pd-modal__btn pd-modal__btn--cancel" type="button"
                  @click="actionMenuOpen = false">取消</button>
              </div>
            </div>
          </div>
        </Teleport>
      </template>

      <div class="pd-bottom-space"></div>

      <!-- ====== 底部操作栏 ====== -->
      <footer class="pd-bottom-bar">
        <button class="pd-bar__icon-btn" type="button" @click="router.push('/pet-shop')">
          <Icon name="store" :size="22" />
          <span>商城</span>
        </button>
        <button class="pd-bar__icon-btn" type="button" @click="router.push('/pet-shop/my')">
          <Icon name="heart" :size="22" />
          <span>我的</span>
        </button>

        <!-- 未领养：领养按钮（宠物）/ 购买按钮（道具） -->
        <button v-if="!owned && !isItem" class="pd-bar__buy" type="button"
          :disabled="adopting || coinsNotEnough" @click="onAdopt">
          <template v-if="adopting">领养中…</template>
          <template v-else-if="coinsNotEnough">金币不足</template>
          <template v-else>🪙 {{ formatPrice(product.price) }} 领养</template>
        </button>
        <button v-else-if="!owned && isItem" class="pd-bar__buy" type="button"
          :class="{ 'pd-bar__buy--crystal': product.kind === 3 }"
          :disabled="itemBuying || coinsNotEnough || product.stock <= 0"
          @click="isSlot ? onBuySlot() : onBuyItem()">
          <template v-if="itemBuying">{{ isSlot ? '处理中…' : '购买中…' }}</template>
          <template v-else-if="product.stock <= 0">已售罄</template>
          <template v-else-if="coinsNotEnough">金币不足</template>
          <template v-else-if="isSlot">🪙 {{ formatPrice(product.price) }} 解锁领养位</template>
          <template v-else>🪙 {{ formatPrice(product.price) }} 购买</template>
        </button>

        <!-- 已领养：放到桌面 + 遗弃 -->
        <template v-else>
          <button class="pd-bar__abandon" type="button"
            :class="{ 'is-confirm': confirmAbandon }" :disabled="abandoning"
            @click="onAbandonClick">
            {{ confirmAbandon ? '确认遗弃？' : '遗弃' }}
          </button>
          <button class="pd-bar__buy pd-bar__buy--summon" type="button" @click="onSummonToDesktop">
            {{ summoned ? '已召唤 ✓' : '🐾 放到桌面' }}
          </button>
        </template>
      </footer>
    </template>
  </div>
</template>

<style scoped>
.pet-detail-page {
  min-height: 100vh;
  background: var(--bg-100);
  padding-bottom: calc(70px + env(safe-area-inset-bottom));
}

/* ====== 顶部导航 ====== */
.pd-header {
  position: fixed; top: 0; left: 0; right: 0; z-index: 60;
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px; max-width: 720px; margin: 0 auto;
}
.pd-header__btn {
  width: 36px; height: 36px; display: inline-flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,0.4); color: #fff; border: none; border-radius: 50%; cursor: pointer;
  -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px);
}
.pd-header__btn :deep(svg) { width: 22px; height: 22px; }

/* ====== 状态页 ====== */
.pd-state {
  min-height: 60vh; display: flex; flex-direction: column; align-items: center;
  justify-content: center; gap: 12px; padding: 40px 24px; text-align: center;
}
.pd-state__spinner {
  width: 32px; height: 32px; border: 3px solid var(--bg-200);
  border-top-color: var(--brand-500); border-radius: 50%;
  animation: pd-spin 0.8s linear infinite;
}
@keyframes pd-spin { to { transform: rotate(360deg); } }
.pd-state__emoji { font-size: 48px; }
.pd-state__text { font-size: 14px; color: var(--text-500); margin: 0; }
.pd-state__btn {
  margin-top: 8px; padding: 8px 24px; background: var(--brand-500); color: #fff;
  border: none; border-radius: 18px; font-size: 14px; font-weight: 600; cursor: pointer;
}

/* ====== Hero ====== */
.pd-hero {
  position: relative; width: 100%; height: clamp(280px, 45vh, 400px);
  max-width: 720px; margin: 0 auto;
  background: linear-gradient(135deg, #eef2ff, #f5f3ff, #fdf4ff);
  display: flex; align-items: center; justify-content: center; overflow: hidden;
}
.pd-hero--evolved {
  background:
    radial-gradient(circle at 50% 40%, rgba(167,139,250,0.25) 0%, transparent 60%),
    linear-gradient(135deg, #f5f0ff, #ede9fe, #ddd6fe);
}
.pd-hero__emoji { font-size: 140px; }
.pd-hero--anim {
  background:
    radial-gradient(circle at 30% 22%, #fff4de 0%, transparent 52%),
    radial-gradient(circle at 74% 68%, #e3edff 0%, transparent 52%),
    linear-gradient(165deg, #f7f9ff 0%, #fdf5ff 100%);
}
.pd-hero__anim { width: 100%; height: 100%; display: flex; flex-direction: column; align-items: center; }
.pd-hero__anim-stage {
  position: relative; flex: 1; min-height: 0; width: 100%;
  display: flex; align-items: center; justify-content: center; padding-bottom: 44px;
}
.pd-hero__anim-stage::before {
  content: ''; position: absolute; bottom: 30px; left: 50%; width: 190px; height: 42px;
  transform: translateX(-50%);
  background: radial-gradient(ellipse at center, rgba(23,32,64,0.14) 0%, transparent 68%);
  pointer-events: none;
}
.pd-hero__pet-badges {
  position: absolute; bottom: 12px; left: 50%; transform: translateX(-50%);
  display: flex; gap: 8px; z-index: 2;
}
.pd-badge {
  padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 700;
  box-shadow: 0 2px 8px rgba(23,32,64,0.15);
}
.pd-badge--level {
  background: linear-gradient(135deg, #5b8cff, #3d7bff); color: #fff;
}
.pd-badge--evolved {
  background: linear-gradient(135deg, #a78bfa, #7c3aed); color: #fff;
}
.pd-hero__photo { width: 100%; height: 100%; object-fit: cover; }
.pd-hero__3d { position: relative; width: 100%; height: 100%; }
.pd-hero__model { width: 100%; height: 100%; --progress-bar-color: var(--brand-500); --progress-mask: transparent; }
.pd-hero__model-progress { display: none; }
.pd-hero__tag {
  position: absolute; top: 64px; left: 16px; padding: 4px 10px;
  background: rgba(255,59,48,0.92); color: #fff; font-size: 11px; font-weight: 600;
  border-radius: 6px; box-shadow: 0 2px 8px rgba(255,59,48,0.3);
}
.pd-hero__tag--crystal {
  background: rgba(124,58,237,0.92); box-shadow: 0 2px 8px rgba(124,58,237,0.3);
}
.pd-hero__tag--item {
  background: rgba(255,138,61,0.92); box-shadow: 0 2px 8px rgba(255,138,61,0.3);
}

/* ====== 价格卡片（未领养） ====== */
.pd-price-card {
  margin: -24px 12px 10px; padding: 18px; background: var(--bg-50);
  border-radius: 18px; border: 0.5px solid var(--bg-200);
  box-shadow: 0 6px 20px rgba(23,32,64,0.08);
  position: relative; z-index: 1; max-width: 720px; margin-left: auto; margin-right: auto;
  width: calc(100% - 24px);
}
.pd-price-row { display: flex; align-items: baseline; gap: 8px; margin-bottom: 8px; }
.pd-price-current { font-size: 26px; font-weight: 700; color: #ff3b30; }
.pd-price-original { font-size: 14px; color: var(--text-400); text-decoration: line-through; }
.pd-price-discount { padding: 2px 6px; background: #ffe5e5; color: #ff3b30; font-size: 11px; font-weight: 600; border-radius: 4px; }
.pd-coins {
  margin-top: 10px; padding: 8px 12px; background: #fffbe8; border: 1px solid #ffe9a8;
  border-radius: 8px; font-size: 12.5px; color: #9a7b1f;
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.pd-coins.is-not-enough { background: #fff1f0; border-color: #ffccc7; color: #cf1322; }
.pd-coins__link {
  border: none; background: transparent; color: var(--brand-500); font-size: 12.5px;
  font-weight: 600; cursor: pointer; padding: 0; text-decoration: underline;
}

/* ====== 已领养宠物信息卡 ====== */
.pd-pet-card {
  margin: -24px 12px 10px; padding: 18px; background: var(--bg-50);
  border-radius: 18px; border: 0.5px solid var(--bg-200);
  box-shadow: 0 6px 20px rgba(23,32,64,0.08);
  position: relative; z-index: 1; max-width: 720px; margin-left: auto; margin-right: auto;
  width: calc(100% - 24px);
}
.pd-pet-card__head { margin-bottom: 12px; }
.pd-pet-card__name-row {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
}
.pd-pet-card__orig-name {
  font-size: 12px; font-weight: 400; color: var(--text-400);
}
.pd-nickname-btn {
  flex-shrink: 0; padding: 4px 10px; border: 1px solid var(--bg-300); border-radius: 12px;
  background: var(--bg-100); color: var(--text-600); font-size: 12px; cursor: pointer;
}
.pd-pet-card__tags { display: flex; gap: 6px; margin-top: 6px; flex-wrap: wrap; }
.pd-pet-tag {
  padding: 2px 10px; border-radius: 10px; font-size: 11px; font-weight: 600;
}
.pd-pet-tag--lv { background: linear-gradient(135deg, #5b8cff, #3d7bff); color: #fff; }
.pd-pet-tag--evolved { background: linear-gradient(135deg, #a78bfa, #7c3aed); color: #fff; }
.pd-pet-tag--max { background: linear-gradient(135deg, #ffd700, #ffb800); color: #7a5700; }

/* 好感度条 */
.pd-affinity { margin-top: 4px; }
.pd-affinity__top {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;
}
.pd-affinity__label { font-size: 13px; font-weight: 600; color: var(--text-700); }
.pd-affinity__num { font-size: 12px; color: var(--text-500); font-weight: 600; }
.pd-affinity__bar {
  position: relative; height: 10px; border-radius: 5px;
  background: rgba(23,32,64,0.08); overflow: visible;
}
.pd-affinity__bar i {
  display: block; height: 100%; border-radius: 5px;
  background: linear-gradient(90deg, #ff8fa8, #ff5b7a);
  transition: width 400ms ease;
}
.pd-affinity__bar i.is-full {
  background: linear-gradient(90deg, #c4b5fd, #a78bfa, #7c3aed);
}
.pd-affinity__node {
  position: absolute; top: -2px; width: 4px; height: 14px;
  background: var(--bg-50); border-radius: 2px; transform: translateX(-50%);
  box-shadow: 0 0 0 1px rgba(23,32,64,0.15);
}
.pd-affinity__bottom {
  display: flex; justify-content: space-between; align-items: center; margin-top: 6px;
  font-size: 11px; color: var(--text-400);
}
.pd-affinity__next { color: var(--text-500); }
.pd-affinity__daily { color: var(--text-400); }

.pd-title {
  font-size: 17px; font-weight: 600; color: var(--text-900); line-height: 1.4;
  margin: 0 0 10px;
}
.pd-meta { display: flex; align-items: center; font-size: 12px; color: var(--text-400); }
.pd-meta__item { display: inline; }
.pd-meta__divider { margin: 0 8px; }

/* ====== 通用 Section ====== */
.pd-section {
  margin: 10px 12px; padding: 16px; background: var(--bg-50);
  border-radius: 14px; border: 0.5px solid var(--bg-200);
  max-width: 720px; margin-left: auto; margin-right: auto; width: calc(100% - 24px);
}
.pd-section--evolve {
  background: linear-gradient(135deg, #f5f0ff, #ede9fe);
  border-color: #c4b5fd;
}
.pd-section__title {
  font-size: 15px; font-weight: 600; color: var(--text-900); margin-bottom: 12px;
  display: flex; align-items: center; gap: 8px;
}
.pd-section__hint {
  font-size: 11px; font-weight: 400; color: var(--text-400);
}
.pd-desc { font-size: 14px; line-height: 1.7; color: var(--text-600); margin: 0; white-space: pre-wrap; }
.pd-params { display: flex; flex-direction: column; gap: 10px; }
.pd-param-row { display: flex; font-size: 13.5px; }
.pd-param__label { width: 80px; color: var(--text-400); flex-shrink: 0; }
.pd-param__value { flex: 1; color: var(--text-700); }
.pd-param__value--gain { color: #ff5b7a; font-weight: 700; }

/* ====== 快速互动按钮 ====== */
.pd-actions { display: flex; gap: 10px; }
.pd-action-btn {
  flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: 14px 8px 10px; border: none; border-radius: 14px; cursor: pointer;
  font-size: 12px; font-weight: 600; transition: transform 120ms ease, opacity 120ms ease;
}
.pd-action-btn:active { transform: scale(0.96); }
.pd-action-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.pd-action-btn__icon { font-size: 28px; line-height: 1; }
.pd-action-btn__label { color: #fff; }
.pd-action-btn__cd { font-size: 10px; opacity: 0.85; color: #fff; }
.pd-action-btn--feed { background: linear-gradient(135deg, #ff9a56, #ff6b35); color: #fff; }
.pd-action-btn--pet { background: linear-gradient(135deg, #ff6b81, #ff3b5c); color: #fff; }
.pd-action-btn--play { background: linear-gradient(135deg, #5b8cff, #3d7bff); color: #fff; }
.pd-action-btn--action { background: linear-gradient(135deg, #a78bfa, #7c3aed); color: #fff; }
.pd-action-btn--bag { background: linear-gradient(135deg, #34c78f, #16a46a); color: #fff; }
.pd-actions--ext { margin-top: 10px; }
.pd-action-tip {
  margin: 10px 0 0; font-size: 11.5px; color: var(--text-400); text-align: center;
}
.pd-action-tip--warn { color: #ff6b35; font-weight: 600; }

/* ====== 升级方案时间线 ====== */
.pd-plan { display: flex; flex-direction: column; gap: 0; }
.pd-plan__step {
  display: flex; gap: 12px; position: relative; padding-bottom: 16px;
}
.pd-plan__step:last-child { padding-bottom: 0; }
.pd-plan__dot {
  flex-shrink: 0; width: 28px; height: 28px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; z-index: 1;
  background: var(--bg-200); color: var(--text-400);
  border: 2px solid var(--bg-200);
}
.pd-plan__step.is-reached .pd-plan__dot {
  background: #3fba7a; color: #fff; border-color: #3fba7a;
}
.pd-plan__step.is-current .pd-plan__dot {
  background: linear-gradient(135deg, #5b8cff, #3d7bff);
  color: #fff; border-color: #3d7bff;
  box-shadow: 0 0 0 4px rgba(61,123,255,0.15);
}
.pd-plan__step.is-evolve.is-reached .pd-plan__dot {
  background: linear-gradient(135deg, #a78bfa, #7c3aed);
  border-color: #7c3aed;
}
.pd-plan__line {
  position: absolute; left: 13px; top: 28px; width: 2px; bottom: 0;
  background: var(--bg-200);
}
.pd-plan__step.is-reached .pd-plan__line { background: #3fba7a; }
.pd-plan__content { flex: 1; padding-top: 2px; }
.pd-plan__head { display: flex; align-items: center; gap: 8px; margin-bottom: 2px; }
.pd-plan__name { font-size: 14px; font-weight: 700; color: var(--text-800); }
.pd-plan__step.is-current .pd-plan__name { color: #3d7bff; }
.pd-plan__step.is-evolve .pd-plan__name { color: #7c3aed; }
.pd-plan__req { font-size: 11px; color: var(--text-400); }
.pd-plan__cur {
  font-size: 10px; padding: 1px 8px; border-radius: 8px;
  background: rgba(61,123,255,0.1); color: #3d7bff; font-weight: 600;
}
.pd-plan__done { font-size: 10px; color: #3fba7a; font-weight: 600; }
.pd-plan__desc { font-size: 12px; color: var(--text-500); margin: 0 0 6px; line-height: 1.5; }
.pd-plan__unlocks { display: flex; gap: 6px; flex-wrap: wrap; }
.pd-plan__unlock-tag {
  font-size: 10.5px; padding: 2px 8px; border-radius: 6px;
  background: var(--bg-100); color: var(--text-500); font-weight: 500;
}
.pd-plan__step.is-reached .pd-plan__unlock-tag { background: rgba(63,186,122,0.1); color: #3fba7a; }
.pd-plan__unlock-tag--crystal {
  background: rgba(124,58,237,0.1) !important; color: #7c3aed !important;
}
.pd-plan__unlock-tag--crystal .is-ok { color: #3fba7a; font-weight: 700; margin-left: 2px; }
.pd-plan__unlock-tag--crystal .is-no { color: #ff3b30; font-weight: 700; margin-left: 2px; }

/* ====== 进化区 ====== */
.pd-evolve__head {
  display: flex; align-items: flex-start; gap: 12px; margin-bottom: 12px;
}
.pd-evolve__icon { font-size: 36px; line-height: 1; }
.pd-evolve__title {
  margin: 0 0 4px; font-size: 16px; font-weight: 700;
  background: linear-gradient(135deg, #a78bfa, #7c3aed);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
}
.pd-evolve__desc { margin: 0; font-size: 12px; color: var(--text-500); line-height: 1.5; }
.pd-evolve__status { display: flex; gap: 12px; margin-bottom: 14px; }
.pd-evolve__cond {
  flex: 1; padding: 8px 12px; border-radius: 10px; font-size: 12px; font-weight: 600;
  background: rgba(255,59,48,0.06); color: #ff3b30; text-align: center;
  border: 1px solid rgba(255,59,48,0.15);
}
.pd-evolve__cond.is-ok {
  background: rgba(63,186,122,0.08); color: #3fba7a;
  border-color: rgba(63,186,122,0.2);
}
.pd-evolve__btn {
  width: 100%; height: 44px; border: none; border-radius: 22px;
  background: linear-gradient(135deg, #c4b5fd, #a78bfa, #7c3aed);
  color: #fff; font-size: 15px; font-weight: 700; cursor: pointer;
  box-shadow: 0 4px 16px rgba(124,58,237,0.35);
  transition: transform 120ms ease, opacity 120ms ease;
}
.pd-evolve__btn:active { transform: scale(0.98); }
.pd-evolve__btn:disabled {
  background: var(--bg-200); color: var(--text-400); box-shadow: none; cursor: not-allowed;
}
.pd-evolve__buy-link {
  display: block; width: 100%; margin-top: 8px; text-align: center;
  border: none; background: transparent; color: #7c3aed;
  font-size: 13px; font-weight: 600; cursor: pointer;
}

/* ====== 昵称弹窗 ====== */
.pd-modal-mask {
  position: fixed; inset: 0; z-index: 2000;
  background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center;
  padding: 20px;
}
.pd-modal {
  width: 100%; max-width: 320px; background: var(--bg-50); border-radius: 18px;
  padding: 24px 20px 16px; box-shadow: 0 16px 48px rgba(0,0,0,0.2);
}
.pd-modal__title { margin: 0 0 6px; font-size: 17px; font-weight: 700; color: var(--text-900); text-align: center; }
.pd-modal__desc { margin: 0 0 16px; font-size: 12px; color: var(--text-400); text-align: center; }
.pd-modal__input {
  width: 100%; height: 42px; padding: 0 14px; border: 1.5px solid var(--bg-300);
  border-radius: 12px; font-size: 15px; outline: none;
  background: var(--bg-100); color: var(--text-800);
  box-sizing: border-box;
}
.pd-modal__input:focus { border-color: var(--brand-500); }
.pd-modal__btns { display: flex; gap: 10px; margin-top: 16px; }
.pd-modal__btn {
  flex: 1; height: 40px; border: none; border-radius: 12px;
  font-size: 14px; font-weight: 600; cursor: pointer;
}
.pd-modal__btn--cancel { background: var(--bg-200); color: var(--text-600); }
.pd-modal__btn--ok {
  background: linear-gradient(135deg, #a78bfa, #7c3aed); color: #fff;
}
.pd-modal__btn:disabled { opacity: 0.6; cursor: not-allowed; }

/* ====== 做动作弹窗 ====== */
.pd-modal--actions { padding-bottom: 12px; }
.pd-action-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;
}
.pd-action-opt {
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  padding: 14px 6px 10px; border: 1px solid var(--bg-200); border-radius: 14px;
  background: var(--bg-100); cursor: pointer; transition: all 140ms ease;
}
.pd-action-opt:active { transform: scale(0.95); }
.pd-action-opt:hover { border-color: #c4b5fd; background: #faf8ff; }
.pd-action-opt__icon { font-size: 26px; line-height: 1; }
.pd-action-opt__label { font-size: 12px; font-weight: 600; color: var(--text-700); }

/* ====== 底部空间 ====== */
.pd-bottom-space { height: 24px; }

/* ====== 底部操作栏 ====== */
.pd-bottom-bar {
  position: fixed; bottom: 0; left: 0; right: 0; z-index: 50;
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px calc(10px + env(safe-area-inset-bottom));
  background: var(--bg-50); border-top: 0.5px solid var(--bg-200);
  max-width: 720px; margin: 0 auto;
}
.pd-bar__icon-btn {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 2px; width: 52px; padding: 4px 0; background: transparent; border: none;
  color: var(--text-600); font-size: 10px; cursor: pointer; flex-shrink: 0;
}
.pd-bar__icon-btn :deep(svg) { width: 22px; height: 22px; }
.pd-bar__buy {
  flex: 1; height: 46px; background: linear-gradient(135deg, #ff6b6b, #ff3b30);
  color: #fff; border: none; border-radius: 23px; font-size: 15.5px;
  font-weight: 600; letter-spacing: 0.5px; cursor: pointer;
  box-shadow: 0 4px 14px rgba(255,59,48,0.32);
}
.pd-bar__buy:disabled { cursor: not-allowed; opacity: 0.6; box-shadow: none; }
.pd-bar__buy--crystal {
  background: linear-gradient(135deg, #a78bfa, #7c3aed);
  box-shadow: 0 4px 14px rgba(124,58,237,0.35);
}
.pd-bar__buy--summon {
  background: linear-gradient(135deg, #5b8cff, #3d7bff);
  box-shadow: 0 4px 14px rgba(61,123,255,0.35);
}
.pd-bar__abandon {
  padding: 0 14px; height: 46px; border: 1px solid rgba(255,59,48,0.3);
  border-radius: 23px; background: transparent; color: #ff3b30;
  font-size: 13px; font-weight: 600; cursor: pointer;
}
.pd-bar__abandon.is-confirm {
  background: #ff3b30; color: #fff; border-color: #ff3b30;
}
.pd-bar__abandon:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
