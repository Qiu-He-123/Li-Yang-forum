<script setup lang="ts">
/**
 * 我的宠物窝（已领养宠物列表）
 * - 每只宠物播放帧动画（点击卡片进详情）
 * - 等级徽章 Lv1-Lv6 + 进化标记
 * - 好感度进度条 + 等级进度（带节点标记）
 * - 每只宠物「陪我」一键放到桌面
 * - 快速互动按钮（喂食/摸头/玩耍）带冷却提示
 * - 遗弃（两段式确认）
 * - 背包食物横滑展示
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import { useSessionStore } from '../stores/session'
import { useUIStore } from '../stores/ui'
import {
  abandonPet,
  feedPet,
  interactPet,
  listMyBag,
  listMyPets,
  playPetToy,
  formatCooldown,
  type BagItem,
  type MyPetItem,
  type InteractResp,
} from '../api/petShop'
import PetAnimation from '../components/pet/PetAnimation.vue'

const router = useRouter()
const session = useSessionStore()
const uiStore = useUIStore()

const loading = ref(false)
const pets = ref<MyPetItem[]>([])
const coins = ref<number | null>(null)
// 已养数量 / 上限（基础上限+已购领养位）
const owned = ref(0)
const petLimit = ref(0)
const extraSlots = ref(0)
const bag = ref<BagItem[]>([])
const bagTotal = ref(0)

// 快速互动中状态
const actingId = ref<number | null>(null)

async function load() {
  if (!session.isLoggedIn()) return
  loading.value = true
  try {
    const { data: resp } = await listMyPets()
    pets.value = resp.data.items || []
    coins.value = resp.data.coins
    owned.value = resp.data.owned ?? pets.value.length
    petLimit.value = resp.data.limit ?? 2
    extraSlots.value = resp.data.extra_slots ?? 0
  } catch {
    pets.value = []
  } finally {
    loading.value = false
  }
  loadBag()
}

async function loadBag() {
  if (!session.isLoggedIn()) return
  try {
    const { data: resp } = await listMyBag({ showGlobalLoading: false, showGlobalError: false })
    bag.value = resp.data.items || []
    bagTotal.value = resp.data.total_qty || 0
  } catch { bag.value = []; bagTotal.value = 0 }
}

function fmtDate(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function onBack() {
  if (window.history.length > 1) router.back()
  else router.push('/pet-shop')
}

function onSummon() {
  localStorage.removeItem('floating_pet_hidden')
  window.dispatchEvent(new Event('floating-pet:summon'))
  toast.success('宠物已放到桌面啦～')
}

function onAccompany(pet: MyPetItem) {
  localStorage.setItem('floating_pet_id', String(pet.id))
  localStorage.removeItem('floating_pet_hidden')
  window.dispatchEvent(new CustomEvent('floating-pet:select', { detail: pet.id }))
  window.dispatchEvent(new Event('floating-pet:summon'))
  toast.success(`${pet.nickname || pet.name} 陪你来了～`)
}

// ====== 快速互动 ======
// 道具选择弹层：mode=feed 选食物喂食 / mode=play 选玩具陪玩
const picker = ref<null | { mode: 'feed' | 'play'; pet: MyPetItem }>(null)

/** 背包里的可用玩具数量（kind=2 且带 play 增益） */
const hasToy = computed(() =>
  bag.value.filter((b) => b.kind === 2 && Number((b.attrs || {}).play || 0) > 0).reduce((n, b) => n + b.qty, 0),
)

/** 当前道具弹层可选的背包项（feed=kind2 且有 satiety/affinity 增益；play=kind2 且有 play/affinity 增益） */
const pickerItems = computed(() => {
  if (!picker.value) return []
  const mode = picker.value.mode
  return bag.value.filter((b) => {
    if (b.kind !== 2) return false
    const a = b.attrs || {}
    if (mode === 'feed') return Number(a.satiety || 0) > 0 || (b.affinity_gain || 0) > 0
    return (b.name.includes('玩具') || Number(a.play || 0) > 0 || (b.affinity_gain || 0) > 0) && mode === 'play'
  })
})

function openFeed(pet: MyPetItem) {
  if (actingId.value) return
  if (pet.cooldowns.feed > 0) { toast.info(`还不饿呢，${formatCooldown(pet.cooldowns.feed)}再来吧~`); return }
  if (bagTotal.value <= 0) { toast.info('背包空空的，先去买点食物吧'); return }
  picker.value = { mode: 'feed', pet }
}

function openPlay(pet: MyPetItem) {
  if (actingId.value) return
  if (pet.cooldowns.play > 0) { toast.info(`刚玩过啦，${formatCooldown(pet.cooldowns.play)}再来吧~`); return }
  const toys = bag.value.filter((b) => b.kind === 2 && (b.attrs?.play || 0) > 0)
  if (!toys.length) { toast.info('背包里没有玩具，去商城挑一个吧'); return }
  picker.value = { mode: 'play', pet }
}

/** 从弹层里选择一个道具并应用到宠物 */
async function applyItem(item: BagItem) {
  if (!picker.value) return
  const pet = picker.value.pet
  const mode = picker.value.mode
  actingId.value = pet.id
  try {
    let resp
    if (mode === 'feed') {
      resp = await feedPet(pet.id, item.id, { showGlobalLoading: false })
      bag.value = resp.data.data.bag
      bagTotal.value = bag.value.reduce((n, b) => n + b.qty, 0)
      handleQuickResult(pet, resp.data.data, `喂了${item.name}`)
    } else {
      resp = await playPetToy(pet.id, item.id, { showGlobalLoading: false })
      bag.value = resp.data.data.bag
      bagTotal.value = bag.value.reduce((n, b) => n + b.qty, 0)
      handleQuickResult(pet, resp.data.data, `用${item.name}陪他玩`)
    }
    picker.value = null
  } catch (e: unknown) { handleQuickError(e) }
  finally { actingId.value = null; await load() }
}

async function quickPet(pet: MyPetItem) {
  if (actingId.value) return
  if (pet.cooldowns.pet > 0) { toast.info(`刚摸过啦，${formatCooldown(pet.cooldowns.pet)}再来吧~`); return }
  actingId.value = pet.id
  try {
    const { data: resp } = await interactPet(pet.id, 'pet', { showGlobalLoading: false })
    handleQuickResult(pet, resp.data, '摸摸头')
  } catch (e: unknown) { handleQuickError(e) }
  finally { actingId.value = null; await load() }
}

async function quickPlay(pet: MyPetItem) {
  if (actingId.value) return
  if (pet.cooldowns.play > 0) { toast.info(`刚玩过啦，${formatCooldown(pet.cooldowns.play)}再来吧~`); return }
  actingId.value = pet.id
  try {
    const { data: resp } = await interactPet(pet.id, 'play', { showGlobalLoading: false })
    handleQuickResult(pet, resp.data, '玩耍')
  } catch (e: unknown) { handleQuickError(e) }
  finally { actingId.value = null; await load() }
}

function handleQuickResult(pet: MyPetItem, data: InteractResp, action: string) {
  if (data.gained > 0) {
    let msg = `${action}成功！好感+${data.gained}`
    if (data.leveled_up) msg = `🎉 ${pet.nickname || pet.name}升级到Lv${data.level}！`
    if (data.daily_remaining <= 0) msg += '（今日好感已达上限）'
    toast.success(msg)
  } else if (data.daily_remaining <= 0) {
    toast.info('今日好感已达上限，明天再来吧~')
  } else {
    toast.info('刚刚互动过，让宠物歇会儿吧~')
  }
}

function handleQuickError(e: unknown) {
  const err = e as { response?: { data?: { msg?: string | { msg?: string } } } }
  const detail = err?.response?.data?.msg
  let text = '操作失败了'
  if (typeof detail === 'string') text = detail
  else if (detail && typeof detail === 'object' && 'msg' in detail) text = (detail as { msg?: string }).msg || text
  toast.error(text)
}

// ====== 遗弃 ======
const confirmAbandonId = ref<number | null>(null)
const abandoning = ref(false)
let abandonTimer: number | null = null

function onAbandonClick(pet: MyPetItem) {
  if (abandoning.value) return
  if (confirmAbandonId.value !== pet.id) {
    confirmAbandonId.value = pet.id
    if (abandonTimer !== null) window.clearTimeout(abandonTimer)
    abandonTimer = window.setTimeout(() => (confirmAbandonId.value = null), 5000)
    return
  }
  void doAbandon(pet)
}

async function doAbandon(pet: MyPetItem) {
  abandoning.value = true
  try {
    await abandonPet(pet.id)
    toast.success(`${pet.nickname || pet.name} 被遗弃了…好感度已清零`)
    confirmAbandonId.value = null
    await load()
    window.dispatchEvent(new Event('floating-pet:reload'))
  } catch { /* 拦截器处理 */ }
  finally { abandoning.value = false }
}

onMounted(() => {
  if (!session.isLoggedIn()) {
    uiStore.openAuthDialog()
    return
  }
  load()
})
</script>

<template>
  <div class="my-pets-page">
    <header class="mp-header">
      <div class="mp-header__inner">
        <button class="mp-back" type="button" aria-label="返回" @click="onBack">
          <Icon name="chevron-left" :size="22" />
        </button>
        <h1 class="mp-title">我的宠物窝</h1>
        <button
          v-if="session.isLoggedIn() && coins !== null"
          class="mp-coins"
          type="button"
          @click="router.push('/coins')"
        >
          🪙 {{ coins }}
        </button>
      </div>
    </header>

    <div v-if="!session.isLoggedIn()" class="mp-state">
      <span class="mp-state__emoji">🐾</span>
      <p class="mp-state__text">登录后即可查看你的宠物</p>
    </div>

    <template v-else>
      <div v-if="loading" class="mp-state">
        <div class="mp-state__spinner"></div>
        <p class="mp-state__text">加载中...</p>
      </div>

      <template v-else>
        <!-- 背包食物 -->
        <section v-if="bag.length" class="mp-bag">
          <div class="mp-bag__head">
            <h2 class="mp-bag__title">🍱 我的背包</h2>
            <span class="mp-bag__total">道具 ×{{ bagTotal }}</span>
          </div>
          <div class="mp-bag__scroll">
            <div v-for="item in bag" :key="item.id" class="mp-bag__chip" @click="router.push('/pet-shop')">
              <span class="mp-bag__emoji">{{ item.image_url || (item.kind === 3 ? '💎' : '🍱') }}</span>
              <span class="mp-bag__name">{{ item.name }}</span>
              <span class="mp-bag__qty">×{{ item.qty }}</span>
            </div>
            <div class="mp-bag__chip mp-bag__chip--more" @click="router.push('/pet-shop')">
              <span class="mp-bag__emoji">🛒</span>
              <span class="mp-bag__name">去商城</span>
            </div>
          </div>
        </section>

        <!-- 已养 / 上限提示 -->
        <section class="mp-limit" :class="{ 'mp-limit--full': owned >= petLimit, 'mp-limit--expanded': extraSlots > 0 }">
          <span class="mp-limit__icon">🪺</span>
          <div class="mp-limit__info">
            <span class="mp-limit__num">已养 <b>{{ owned }}</b> / 上限 <b>{{ petLimit }}</b></span>
            <span class="mp-limit__sub">
              <template v-if="extraSlots > 0">已解锁 {{ extraSlots }} 个'宠物领养位'</template>
              <template v-else-if="owned >= petLimit">已达上限，可在商城购买『宠物领养位』扩充 🛒</template>
              <template v-else>基础上限 2 只，可在商城购买『宠物领养位』再多养</template>
            </span>
          </div>
          <button class="mp-limit__btn" type="button" @click="router.push('/pet-shop')">去商城</button>
        </section>

        <!-- 宠物网格 -->
        <main v-if="pets.length" class="mp-grid">
          <article v-for="pet in pets" :key="pet.id" class="mp-card">
            <!-- 顶部等级条 -->
            <div class="mp-card__lvbar">
              <span class="mp-card__lvbadge" :class="{ 'is-evolved': pet.evolved }">
                Lv{{ pet.level }} {{ pet.level_name }}
              </span>
              <span v-if="pet.evolved" class="mp-card__evolved">✨ 灵魂伴侣</span>
              <span v-else-if="pet.affinity >= 100" class="mp-card__max">💎 可进化</span>
            </div>

            <div class="mp-card__stage" @click="router.push(`/pet-shop/${pet.id}`)">
              <PetAnimation v-if="pet.anim" :anim="pet.anim" :size="140" :interactive="false" :show-tabs="false" />
              <img v-else-if="pet.image_url" class="mp-card__photo" :src="pet.image_url" :alt="pet.name" />
              <span v-else class="mp-card__emoji">{{ pet.image || '🐾' }}</span>
              <!-- 宠物名（昵称优先） -->
              <div class="mp-card__name-on-stage">
                {{ pet.nickname || pet.name }}
                <span v-if="pet.nickname" class="mp-card__orig-name">{{ pet.name }}</span>
              </div>
            </div>

            <div class="mp-card__info">
              <!-- 好感度条（带等级节点） -->
              <div class="mp-card__affinity">
                <div class="mp-card__affinity-top">
                  <span class="mp-card__hearts">❤ {{ pet.affinity }}/100</span>
                  <span class="mp-card__affinity-daily">
                    今日 {{ pet.daily_affinity.gained }}/{{ pet.daily_affinity.cap }}
                  </span>
                </div>
                <div class="mp-card__affinity-bar">
                  <i :style="{ width: Math.min(100, pet.affinity) + '%' }"
                     :class="{ 'is-full': pet.affinity >= 100 }"></i>
                  <span v-for="lv in [20,40,60,80,100]" :key="lv"
                    class="mp-card__affinity-node" :style="{ left: lv + '%' }"></span>
                </div>
                <div class="mp-card__affinity-next" v-if="pet.next_level">
                  → Lv{{ pet.next_level.level }} {{ pet.next_level.name }} 还需 {{ pet.next_level.affinity_needed }}
                </div>
                <div class="mp-card__affinity-next" v-else-if="pet.evolved">
                  ✨ 已达最高等级
                </div>
              </div>

              <!-- 快速互动按钮 -->
              <div class="mp-card__quick">
                <button class="mp-quick-btn mp-quick-btn--feed" type="button"
                  :disabled="actingId === pet.id || pet.cooldowns.feed > 0 || bagTotal <= 0"
                  @click.stop="openFeed(pet)">
                  <span>🍖</span>
                  <span v-if="pet.cooldowns.feed > 0">{{ formatCooldown(pet.cooldowns.feed) }}</span>
                  <span v-else-if="bagTotal <= 0">无食物</span>
                  <span v-else>喂食</span>
                </button>
                <button class="mp-quick-btn mp-quick-btn--toy" type="button"
                  :disabled="actingId === pet.id || pet.cooldowns.play > 0 || hasToy <= 0"
                  @click.stop="openPlay(pet)">
                  <span>🎁</span>
                  <span v-if="pet.cooldowns.play > 0">{{ formatCooldown(pet.cooldowns.play) }}</span>
                  <span v-else-if="hasToy <= 0">无玩具</span>
                  <span v-else>玩具</span>
                </button>
                <button class="mp-quick-btn mp-quick-btn--pet" type="button"
                  :disabled="actingId === pet.id || pet.cooldowns.pet > 0"
                  @click.stop="quickPet(pet)">
                  <span>🫳</span>
                  <span v-if="pet.cooldowns.pet > 0">{{ formatCooldown(pet.cooldowns.pet) }}</span>
                  <span v-else>摸摸</span>
                </button>
                <button class="mp-quick-btn mp-quick-btn--play" type="button"
                  :disabled="actingId === pet.id || pet.cooldowns.play > 0"
                  @click.stop="quickPlay(pet)">
                  <span>🎾</span>
                  <span v-if="pet.cooldowns.play > 0">{{ formatCooldown(pet.cooldowns.play) }}</span>
                  <span v-else>玩耍</span>
                </button>
              </div>

              <div class="mp-card__footer">
                <p class="mp-card__date">🐾 {{ fmtDate(pet.adopted_at) }} 领养</p>
                <div class="mp-card__footbtns">
                  <button
                    v-if="pet.ai_enabled"
                    class="mp-card__accompany mp-card__chat"
                    type="button"
                    @click.stop="router.push(`/pet-chat/${pet.id}`)"
                  >
                    💬 聊天
                  </button>
                  <button class="mp-card__accompany" type="button" @click.stop="onAccompany(pet)">🐾 陪我</button>
                  <button class="mp-card__abandon"
                    :class="{ 'is-confirm': confirmAbandonId === pet.id }"
                    type="button" :disabled="abandoning"
                    @click.stop="onAbandonClick(pet)">
                    {{ confirmAbandonId === pet.id ? '确认遗弃？' : '遗弃' }}
                  </button>
                </div>
              </div>
            </div>
          </article>
        </main>

        <div v-else class="mp-state">
          <span class="mp-state__emoji">🏠</span>
          <p class="mp-state__text">宠物窝还空着，去领养一只像素宠物吧～</p>
          <button class="mp-state__btn" type="button" @click="router.push('/pet-shop')">去商城逛逛</button>
        </div>

        <div v-if="pets.length" class="mp-footer">
          <button class="mp-footer__btn mp-footer__btn--primary" type="button" @click="onSummon">
            <span class="mp-footer__icon">🐾</span> 放到桌面陪我
          </button>
          <button class="mp-footer__btn" type="button" @click="router.push('/pet-shop')">
            <Icon name="store" :size="16" /> 再领养一只
          </button>
        </div>
      </template>
    </template>

    <!-- 道具选择弹层（喂食选食物 / 玩具陪玩） -->
    <teleport to="body">
      <transition name="mp-picker">
        <div v-if="picker" class="mp-picker-mask" @click.self="picker = null">
          <div class="mp-picker">
            <div class="mp-picker__head">
              <h3 class="mp-picker__title">
                {{ picker.mode === 'feed' ? '🍖 选一份食物投喂' : '🎁 选一个玩具陪玩' }}
              </h3>
              <button class="mp-picker__close" type="button" aria-label="关闭" @click="picker = null">✕</button>
            </div>
            <p class="mp-picker__sub">
              <span>{{ picker.pet.nickname || picker.pet.name }}</span>
              <span v-if="picker.mode === 'feed'" class="mp-picker__satiety">饱食度 {{ picker.pet.satiety }}/100</span>
            </p>
            <div class="mp-picker__list">
              <button
                v-for="item in pickerItems"
                :key="item.id"
                class="mp-pitem"
                type="button"
                :disabled="actingId === picker.pet.id || item.qty <= 0"
                @click="applyItem(item)"
              >
                <span class="mp-pitem__emoji">{{ item.image_url || (item.kind === 3 ? '💎' : '🧀') }}</span>
                <span class="mp-pitem__body">
                  <span class="mp-pitem__name">{{ item.name }}</span>
                  <span class="mp-pitem__effect">
                    <template v-if="picker.mode === 'feed'">
                      饱腹 +{{ item.attrs?.satiety || 0 }} · 好感 +{{ item.affinity_gain || 0 }}
                    </template>
                    <template v-else>
                      趣味 +{{ item.attrs?.play || 0 }} · 好感 +{{ item.affinity_gain || 0 }}
                    </template>
                  </span>
                </span>
                <span class="mp-pitem__qty">×{{ item.qty }}</span>
              </button>
              <div v-if="!pickerItems.length" class="mp-picker__empty">
                {{ picker.mode === 'feed' ? '背包里没有可喂的食物，去商城买点吧' : '背包里没有玩具，去商城挑一个吧' }}
              </div>
            </div>
            <button class="mp-picker__cancel" type="button" @click="picker = null">取消</button>
          </div>
        </div>
      </transition>
    </teleport>
  </div>
</template>

<style scoped>
.my-pets-page {
  min-height: 100vh;
  background: var(--bg-100);
  padding-bottom: calc(72px + env(safe-area-inset-bottom));
}

/* ====== 顶部导航 ====== */
.mp-header {
  position: sticky; top: 0; z-index: 50;
  background: color-mix(in srgb, var(--bg-50) 92%, transparent);
  -webkit-backdrop-filter: blur(20px); backdrop-filter: blur(20px);
  border-bottom: 0.5px solid var(--bg-300);
}
.mp-header__inner {
  max-width: 720px; margin: 0 auto; padding: 12px 16px;
  display: flex; align-items: center; gap: 12px;
}
.mp-back {
  flex-shrink: 0; width: 34px; height: 34px; border-radius: 50%; border: none;
  background: rgba(0,0,0,0.04); color: #222;
  display: inline-flex; align-items: center; justify-content: center; cursor: pointer;
}
.mp-back :deep(svg) { width: 22px; height: 22px; }
.mp-title {
  flex: 1; font-size: 17px; font-weight: 700; color: var(--text-900);
  white-space: nowrap; margin: 0;
}
.mp-coins {
  flex-shrink: 0; padding: 6px 14px; border: none; border-radius: 16px;
  background: linear-gradient(135deg, #fff3d6, #ffe7b3); color: #9a6b00;
  font-size: 13px; font-weight: 700; cursor: pointer;
}

/* ====== 已养 / 上限 ====== */
.mp-limit {
  max-width: 720px; margin: 14px auto 0; padding: 10px 14px;
  display: flex; align-items: center; gap: 12px;
  background: linear-gradient(135deg, #eef4ff, #e6efff);
  border: 1px solid #d7e3ff; border-radius: 14px;
}
.mp-limit--full { background: linear-gradient(135deg, #fff3d6, #ffe7b3); border-color: #ffdc8f; }
.mp-limit--expanded { background: linear-gradient(135deg, #e9fff1, #cff3dd); border-color: #b9e6cb; }
.mp-limit__icon { font-size: 20px; }
.mp-limit__info { flex: 1; min-width: 0; }
.mp-limit__num { display: block; font-size: 14px; font-weight: 600; color: var(--text-900); }
.mp-limit__num b { color: #2b63d9; }
.mp-limit--full .mp-limit__num b { color: #b26a00; }
.mp-limit__sub { display: block; margin-top: 2px; font-size: 12px; color: var(--text-500); }
.mp-limit__btn {
  flex-shrink: 0; padding: 6px 14px; border: none; border-radius: 14px;
  background: #2b63d9; color: #fff; font-size: 12px; font-weight: 700; cursor: pointer;
}

/* ====== 背包 ====== */
.mp-bag {
  max-width: 720px; margin: 14px auto 0; padding: 12px 16px 4px;
}
.mp-bag__head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.mp-bag__title { font-size: 14px; font-weight: 700; color: var(--text-900); margin: 0; }
.mp-bag__total {
  font-size: 12px; color: var(--text-500);
  background: var(--bg-100); padding: 2px 10px; border-radius: 10px;
}
.mp-bag__scroll {
  display: flex; gap: 8px; overflow-x: auto; padding-bottom: 6px;
  scrollbar-width: none;
}
.mp-bag__scroll::-webkit-scrollbar { display: none; }
.mp-bag__chip {
  flex-shrink: 0; display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px; background: var(--bg-50);
  border: 1px solid rgba(23,32,64,0.08); border-radius: 999px;
  font-size: 12.5px; color: var(--text-700); cursor: pointer;
  box-shadow: 0 2px 8px rgba(23,32,64,0.06);
}
.mp-bag__chip--more { color: var(--brand-500); }
.mp-bag__emoji { font-size: 16px; line-height: 1; }
.mp-bag__name { font-weight: 600; }
.mp-bag__qty { color: #b07a2a; font-weight: 700; }

/* ====== 宠物网格 ====== */
.mp-grid {
  max-width: 720px; margin: 0 auto; padding: 16px;
  display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px;
}
.mp-card {
  background: var(--bg-50); border-radius: 16px;
  border: 1px solid rgba(23,32,64,0.08);
  box-shadow: 0 3px 14px rgba(23,32,64,0.1);
  overflow: hidden; display: flex; flex-direction: column;
  transition: transform 150ms ease, box-shadow 150ms ease;
}
.mp-card:hover { transform: translateY(-2px); box-shadow: 0 8px 22px rgba(23,32,64,0.16); }

/* 等级条 */
.mp-card__lvbar {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 10px 4px;
}
.mp-card__lvbadge {
  padding: 2px 10px; border-radius: 10px;
  background: linear-gradient(135deg, #5b8cff, #3d7bff);
  color: #fff; font-size: 11px; font-weight: 700;
}
.mp-card__lvbadge.is-evolved {
  background: linear-gradient(135deg, #a78bfa, #7c3aed);
}
.mp-card__evolved {
  font-size: 10px; padding: 2px 8px; border-radius: 8px;
  background: rgba(124,58,237,0.1); color: #7c3aed; font-weight: 600;
}
.mp-card__max {
  font-size: 10px; padding: 2px 8px; border-radius: 8px;
  background: rgba(255,184,0,0.15); color: #b8860b; font-weight: 600;
}

/* 动画舞台 */
.mp-card__stage {
  position: relative; aspect-ratio: 1;
  display: flex; align-items: center; justify-content: center;
  padding: 4px 0 40px; cursor: pointer;
  background:
    radial-gradient(circle at 30% 22%, #fff4de 0%, transparent 52%),
    radial-gradient(circle at 74% 68%, #e3edff 0%, transparent 52%),
    linear-gradient(165deg, #f7f9ff 0%, #fdf5ff 100%);
}
.mp-card__stage::after {
  content: ''; position: absolute; bottom: 28px; left: 50%; width: 56%; height: 24px;
  transform: translateX(-50%);
  background: radial-gradient(ellipse at center, rgba(23,32,64,0.13) 0%, transparent 68%);
  pointer-events: none;
}
.mp-card__name-on-stage {
  position: absolute; bottom: 8px; left: 50%; transform: translateX(-50%);
  font-size: 12px; font-weight: 700; color: var(--text-700);
  white-space: nowrap; display: flex; align-items: center; gap: 4px;
  z-index: 2;
}
.mp-card__orig-name {
  font-size: 10px; font-weight: 400; color: var(--text-400);
}
.mp-card__photo {
  position: relative; z-index: 1; width: 70%; height: 70%;
  object-fit: contain; image-rendering: pixelated;
}
.mp-card__emoji { font-size: 64px; }
.mp-card__info { padding: 4px 12px 12px; }

/* 好感度条 */
.mp-card__affinity { margin-bottom: 8px; }
.mp-card__affinity-top {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;
}
.mp-card__hearts { font-size: 11px; color: #ff5b7a; font-weight: 700; letter-spacing: 0.5px; }
.mp-card__affinity-daily { font-size: 10px; color: var(--text-400); }
.mp-card__affinity-bar {
  position: relative; height: 6px; border-radius: 3px;
  background: rgba(23,32,64,0.08); overflow: visible;
}
.mp-card__affinity-bar i {
  display: block; height: 100%; border-radius: 3px;
  background: linear-gradient(90deg, #ff8fa8, #ff5b7a);
  transition: width 400ms ease;
}
.mp-card__affinity-bar i.is-full {
  background: linear-gradient(90deg, #c4b5fd, #a78bfa, #7c3aed);
}
.mp-card__affinity-node {
  position: absolute; top: -1px; width: 3px; height: 8px;
  background: var(--bg-50); border-radius: 1px; transform: translateX(-50%);
  box-shadow: 0 0 0 1px rgba(23,32,64,0.12);
}
.mp-card__affinity-next {
  font-size: 10px; color: var(--text-400); margin-top: 3px;
}

/* 快速互动按钮 */
.mp-card__quick {
  display: flex; gap: 6px; margin-bottom: 8px;
}
.mp-quick-btn {
  flex: 1; display: flex; flex-direction: column; align-items: center; gap: 1px;
  padding: 7px 4px 5px; border: none; border-radius: 10px;
  font-size: 10px; font-weight: 600; cursor: pointer;
  transition: transform 100ms ease, opacity 100ms ease;
}
.mp-quick-btn:active { transform: scale(0.94); }
.mp-quick-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.mp-quick-btn span:first-child { font-size: 16px; line-height: 1; }
.mp-quick-btn--feed { background: rgba(255,107,53,0.12); color: #ff6b35; }
.mp-quick-btn--pet { background: rgba(255,59,92,0.12); color: #ff3b5c; }
.mp-quick-btn--play { background: rgba(61,123,255,0.12); color: #3d7bff; }
.mp-quick-btn--toy { background: rgba(168,85,247,0.12); color: #a855f7; }

/* 底部 */
.mp-card__footer {
  display: flex; align-items: center; justify-content: space-between; gap: 6px;
}
.mp-card__date { font-size: 10.5px; color: var(--text-400); margin: 0; }
.mp-card__footbtns { display: flex; gap: 4px; }
.mp-card__accompany {
  flex-shrink: 0; border: none;
  background: linear-gradient(135deg, #5b8cff, #3d7bff);
  color: #fff; font-size: 11px; font-weight: 700;
  padding: 4px 10px; border-radius: 999px; cursor: pointer;
  box-shadow: 0 2px 8px rgba(61,123,255,0.25);
}
.mp-card__abandon {
  border: none; background: transparent; color: var(--text-400);
  font-size: 10.5px; padding: 3px 8px; border-radius: 8px; cursor: pointer;
}
.mp-card__abandon:hover { color: #ff3b30; background: rgba(255,59,48,0.08); }
.mp-card__abandon.is-confirm { color: #fff; background: #ff3b30; font-weight: 700; }
.mp-card__chat {
  background: linear-gradient(135deg, #00c48c, #00a877);
  box-shadow: 0 2px 8px rgba(0,164,119,0.25);
}

/* ====== 状态页 ====== */
.mp-state {
  min-height: 60vh; display: flex; flex-direction: column; align-items: center;
  justify-content: center; gap: 12px; padding: 40px 24px; text-align: center;
}
.mp-state__emoji { font-size: 48px; line-height: 1; }
.mp-state__text { font-size: 14px; color: var(--text-500); margin: 0; }
.mp-state__btn {
  margin-top: 8px; padding: 10px 32px; background: var(--brand-500); color: #fff;
  border: none; border-radius: 20px; font-size: 14px; font-weight: 600; cursor: pointer;
}
.mp-state__spinner {
  width: 32px; height: 32px; border: 3px solid var(--bg-200);
  border-top-color: var(--brand-500); border-radius: 50%;
  animation: mp-spin 0.8s linear infinite;
}
@keyframes mp-spin { to { transform: rotate(360deg); } }

/* ====== 底部 ====== */
.mp-footer {
  max-width: 720px; margin: 0 auto; padding: 8px 16px 24px;
  text-align: center; display: flex; gap: 12px; justify-content: center; flex-wrap: wrap;
}
.mp-footer__btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 10px 28px; border: 1px solid var(--bg-200); border-radius: 20px;
  background: var(--bg-50); color: var(--text-700);
  font-size: 13.5px; font-weight: 600; cursor: pointer; transition: all 150ms ease;
}
.mp-footer__btn:hover { border-color: var(--brand-400); color: var(--brand-500); }
.mp-footer__btn--primary {
  border: none; background: linear-gradient(135deg, #5b8cff, #3d7bff);
  color: #fff; box-shadow: 0 4px 14px rgba(61,123,255,0.32);
}
.mp-footer__btn--primary:hover { color: #fff; opacity: 0.92; }
.mp-footer__icon { font-size: 15px; line-height: 1; }

/* ====== 道具选择弹层 ====== */
.mp-picker-mask {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(10,14,28,0.45);
  -webkit-backdrop-filter: blur(3px); backdrop-filter: blur(3px);
  display: flex; align-items: flex-end; justify-content: center;
}
.mp-picker {
  width: 100%; max-width: 720px; max-height: 78vh;
  background: var(--bg-50); border-radius: 20px 20px 0 0;
  padding: 16px 16px calc(16px + env(safe-area-inset-bottom));
  display: flex; flex-direction: column;
  box-shadow: 0 -6px 30px rgba(10,14,28,0.2);
}
.mp-picker__head {
  display: flex; align-items: center; justify-content: space-between;
}
.mp-picker__title { font-size: 16px; font-weight: 700; color: var(--text-900); margin: 0; }
.mp-picker__close {
  border: none; background: rgba(0,0,0,0.06); color: var(--text-500);
  width: 28px; height: 28px; border-radius: 50%; cursor: pointer;
}
.mp-picker__sub {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 12px; color: var(--text-500); margin: 10px 2px 8px;
}
.mp-picker__satiety { color: #b07a2a; font-weight: 700; }
.mp-picker__list {
  flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 8px;
}
.mp-pitem {
  display: flex; align-items: center; gap: 12px;
  padding: 12px; border: 1px solid rgba(23,32,64,0.08); border-radius: 12px;
  background: var(--bg-100); cursor: pointer; text-align: left;
  transition: transform 100ms ease, border-color 150ms ease;
}
.mp-pitem:active { transform: scale(0.98); }
.mp-pitem:disabled { opacity: 0.45; cursor: not-allowed; }
.mp-pitem__emoji { font-size: 26px; line-height: 1; }
.mp-pitem__body { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.mp-pitem__name { font-size: 14px; font-weight: 700; color: var(--text-900); }
.mp-pitem__effect { font-size: 11.5px; color: var(--text-500); }
.mp-pitem__qty { font-size: 13px; color: #b07a2a; font-weight: 700; }
.mp-picker__empty {
  text-align: center; font-size: 13px; color: var(--text-400); padding: 24px 0;
}
.mp-picker__cancel {
  margin-top: 12px; padding: 11px; border: none; border-radius: 12px;
  background: rgba(0,0,0,0.06); color: var(--text-600); font-size: 14px; font-weight: 600;
  cursor: pointer;
}
.mp-picker-enter-active, .mp-picker-leave-active { transition: opacity 200ms ease; }
.mp-picker-enter-active .mp-picker, .mp-picker-leave-active .mp-picker { transition: transform 220ms ease; }
.mp-picker-enter-from, .mp-picker-leave-to { opacity: 0; }
.mp-picker-enter-from .mp-picker, .mp-picker-leave-to .mp-picker { transform: translateY(30%); }

/* ====== 响应式 ====== */
@media (min-width: 540px) {
  .mp-grid { grid-template-columns: repeat(3, 1fr); gap: 16px; }
}
</style>
