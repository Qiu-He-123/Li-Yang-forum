<script setup lang="ts">
/**
 * 组局广场（真实后端）
 * - 顶部：返回 + 标题 + 发布按钮
 * - 筛选：类型（全部/线上/线下）+ 分类 Tab
 * - 列表：组局卡片（标题、时间、地点、人数进度、发起人、封面图）
 * - 分页加载（滚动到底自动加载更多）
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '../components/native'
import {
  listGatherings,
  listGatheringCategories,
  type Gathering,
} from '../api/gathering'

const router = useRouter()

// ====== 筛选 ======
const activeType = ref<'' | 'online' | 'offline'>('')
const activeCategory = ref('全部')
const categoryTabs = ref<string[]>(['全部'])
const typeTabs = computed(() => [
  { label: '全部', value: '' as const },
  { label: '线上', value: 'online' as const },
  { label: '线下', value: 'offline' as const },
])

// ====== 列表 ======
const gatherings = ref<Gathering[]>([])
const loading = ref(false)
const loadingMore = ref(false)
const total = ref(0)
const page = ref(1)
const PAGE_SIZE = 20
const hasMore = computed(() => gatherings.value.length < total.value)

async function loadCategories() {
  try {
    const { data: resp } = await listGatheringCategories()
    const cats = resp.data || []
    categoryTabs.value = ['全部', ...cats]
  } catch {
    categoryTabs.value = ['全部']
  }
}

async function load() {
  loading.value = true
  page.value = 1
  try {
    const { data: resp } = await listGatherings({
      category: activeCategory.value === '全部' ? undefined : activeCategory.value,
      type: activeType.value || undefined,
      page: 1,
      page_size: PAGE_SIZE,
    })
    const d = resp.data
    gatherings.value = d.items || []
    total.value = d.total || 0
  } catch {
    gatherings.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  if (loadingMore.value || !hasMore.value) return
  loadingMore.value = true
  try {
    const { data: resp } = await listGatherings({
      category: activeCategory.value === '全部' ? undefined : activeCategory.value,
      type: activeType.value || undefined,
      page: page.value + 1,
      page_size: PAGE_SIZE,
    })
    const d = resp.data
    gatherings.value = [...gatherings.value, ...(d.items || [])]
    total.value = d.total || 0
    page.value += 1
  } finally {
    loadingMore.value = false
  }
}

function selectType(t: '' | 'online' | 'offline') {
  if (activeType.value === t) return
  activeType.value = t
  load()
}

function selectCategory(cat: string) {
  if (activeCategory.value === cat) return
  activeCategory.value = cat
  load()
}

function onBack() {
  if (window.history.length > 1) router.back()
  else router.push('/')
}

// ====== 展示辅助 ======
function isImageUrl(url: string | null | undefined): boolean {
  return !!url && (url.startsWith('/') || url.startsWith('http'))
}

function fmtTime(iso: string | null): string {
  if (!iso) return '时间待定'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '时间待定'
  const now = new Date()
  const sameYear = d.getFullYear() === now.getFullYear()
  const md = `${d.getMonth() + 1}月${d.getDate()}日`
  const hm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  const week = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][d.getDay()]
  return sameYear ? `${md} ${week} ${hm}` : `${d.getFullYear()}年${md} ${hm}`
}

/** 距离开始的倒计时文案（招募中显示） */
function countdown(iso: string | null): string | null {
  if (!iso) return null
  const diff = new Date(iso).getTime() - Date.now()
  if (Number.isNaN(diff) || diff <= 0) return null
  const hours = Math.floor(diff / 3_600_000)
  if (hours < 1) return `即将开始`
  if (hours < 24) return `${hours}小时后开始`
  const days = Math.floor(hours / 24)
  return `${days}天后开始`
}

function statusText(g: Gathering): string {
  if (g.status === 'cancelled') return '已取消'
  if (g.status === 'ended') return '已结束'
  if (g.joined_people >= g.max_people) return '已满员'
  return '招募中'
}

// ====== 无限滚动 ======
const sentinel = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null

onMounted(() => {
  loadCategories()
  load()
  observer = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting) loadMore()
    },
    { rootMargin: '300px' },
  )
  if (sentinel.value) observer.observe(sentinel.value)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
})
</script>

<template>
  <div class="gatherings-page">
    <!-- 顶部导航 -->
    <header class="gg-header">
      <button class="gg-header__back" type="button" @click="onBack">
        <Icon name="chevron-left" :size="24" />
      </button>
      <h1 class="gg-header__title">组局广场</h1>
      <button class="gg-header__publish" type="button" @click="router.push('/publish/gathering')">
        <Icon name="plus" :size="16" />
        <span>发布</span>
      </button>
    </header>

    <!-- 类型筛选 -->
    <div class="gg-type-bar">
      <div class="gg-type-bar__inner">
        <button
          v-for="t in typeTabs"
          :key="t.value"
          class="gg-type"
          :class="{ 'is-active': activeType === t.value }"
          type="button"
          @click="selectType(t.value)"
        >
          {{ t.label }}
        </button>
      </div>
    </div>

    <!-- 分类 Tab -->
    <div class="gg-cats">
      <div class="gg-cats__scroll">
        <button
          v-for="cat in categoryTabs"
          :key="cat"
          class="gg-cat"
          :class="{ 'is-active': activeCategory === cat }"
          type="button"
          @click="selectCategory(cat)"
        >
          {{ cat }}
        </button>
      </div>
    </div>

    <!-- 列表 -->
    <main class="gg-list">
      <!-- 加载骨架 -->
      <div v-if="loading" class="gg-list__inner">
        <div v-for="i in 4" :key="'sk-' + i" class="gg-card gg-card--skeleton"></div>
      </div>

      <template v-else>
        <!-- 空状态 -->
        <div v-if="!gatherings.length" class="gg-empty">
          <span class="gg-empty__icon">🎉</span>
          <p class="gg-empty__text">还没有招募中的组局</p>
          <button class="gg-empty__btn" type="button" @click="router.push('/publish/gathering')">
            发起第一个组局
          </button>
        </div>

        <div v-else class="gg-list__inner">
          <article
            v-for="g in gatherings"
            :key="g.id"
            class="gg-card"
            @click="router.push(`/gatherings/${g.id}`)"
          >
            <!-- 封面图（有图时） -->
            <div v-if="g.images.length && isImageUrl(g.images[0])" class="gg-card__cover">
              <img :src="g.images[0]" :alt="g.title" loading="lazy" />
              <span class="gg-card__cover-mask"></span>
              <div class="gg-card__cover-info">
                <span class="gg-card__type-tag" :class="g.type === 'online' ? 'is-online' : 'is-offline'">
                  {{ g.type === 'online' ? '🎮 线上' : '📍 线下' }}
                </span>
                <span class="gg-card__status" :class="`is-${g.status}`">{{ statusText(g) }}</span>
              </div>
            </div>

            <div class="gg-card__body">
              <!-- 无图时状态放头部 -->
              <div v-if="!(g.images.length && isImageUrl(g.images[0]))" class="gg-card__tags">
                <span class="gg-card__type-tag" :class="g.type === 'online' ? 'is-online' : 'is-offline'">
                  {{ g.type === 'online' ? '🎮 线上' : '📍 线下' }}
                </span>
                <span class="gg-card__status" :class="`is-${g.status}`">{{ statusText(g) }}</span>
              </div>

              <h3 class="gg-card__title">{{ g.title }}</h3>

              <div class="gg-card__meta">
                <div class="gg-card__meta-row">
                  <Icon name="clock" :size="14" class="gg-card__meta-icon" />
                  <span>{{ fmtTime(g.start_time) }}</span>
                  <span v-if="countdown(g.start_time)" class="gg-card__countdown">
                    · {{ countdown(g.start_time) }}
                  </span>
                </div>
                <div v-if="g.location" class="gg-card__meta-row">
                  <Icon name="map-pin" :size="14" class="gg-card__meta-icon" />
                  <span class="gg-card__location">{{ g.location }}</span>
                </div>
              </div>

              <div class="gg-card__footer">
                <div class="gg-card__host">
                  <img v-if="g.host.avatar" class="gg-card__avatar" :src="g.host.avatar" alt="" />
                  <span v-else class="gg-card__avatar gg-card__avatar--fallback">
                    {{ g.host.nickname.slice(0, 1) }}
                  </span>
                  <span class="gg-card__host-name">{{ g.host.nickname }}</span>
                  <span class="gg-card__cat">{{ g.category }}</span>
                </div>
                <div class="gg-card__people">
                  <div class="gg-card__people-bar">
                    <div
                      class="gg-card__people-fill"
                      :style="{ width: Math.min(100, (g.joined_people / g.max_people) * 100) + '%' }"
                    ></div>
                  </div>
                  <span class="gg-card__people-num">
                    {{ g.joined_people }}/{{ g.max_people }}人
                  </span>
                </div>
              </div>
            </div>
          </article>

          <!-- 加载更多哨兵 -->
          <div ref="sentinel" class="gg-load-more">
            <span v-if="loadingMore">加载中...</span>
            <span v-else-if="!hasMore" class="gg-load-more__end">— 已经到底啦 —</span>
          </div>
        </div>
      </template>
    </main>

    <!-- 右下角发布 FAB -->
    <button class="gg-fab" type="button" @click="router.push('/publish/gathering')">
      <Icon name="plus" :size="24" />
      <span>组局</span>
    </button>
  </div>
</template>

<style scoped>
.gatherings-page {
  min-height: 100vh;
  background: var(--bg-100, #f2f3f7);
  padding-bottom: calc(90px + env(safe-area-inset-bottom));
}

/* ====== 顶部导航 ====== */
.gg-header {
  position: sticky;
  top: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 48px;
  padding: 0 8px 0 4px;
  background: color-mix(in srgb, var(--bg-50, #fff) 92%, transparent);
  -webkit-backdrop-filter: blur(20px);
  backdrop-filter: blur(20px);
  border-bottom: 0.5px solid var(--bg-300);
  max-width: 720px;
  margin: 0 auto;
}
.gg-header__back {
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--text-800);
  border-radius: 50%;
}
.gg-header__back :deep(svg) { width: 24px; height: 24px; }
.gg-header__title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-900, #111);
  margin: 0;
}
.gg-header__publish {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 14px;
  background: var(--brand-500, #1942c2);
  color: #fff;
  border: none;
  border-radius: 16px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.gg-header__publish :deep(svg) { width: 16px; height: 16px; }

/* ====== 类型筛选 ====== */
.gg-type-bar {
  background: var(--bg-50, #fff);
  border-bottom: 0.5px solid var(--bg-200);
  max-width: 720px;
  margin: 0 auto;
}
.gg-type-bar__inner {
  display: flex;
  gap: 8px;
  padding: 10px 16px;
}
.gg-type {
  padding: 6px 18px;
  background: var(--bg-100, #f2f3f7);
  border: 1px solid transparent;
  border-radius: 16px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-600, #606474);
  cursor: pointer;
  transition: all 150ms ease;
}
.gg-type.is-active {
  background: color-mix(in srgb, var(--brand-500, #1942c2) 10%, transparent);
  border-color: var(--brand-500, #1942c2);
  color: var(--brand-500, #1942c2);
  font-weight: 600;
}

/* ====== 分类 Tab ====== */
.gg-cats {
  position: sticky;
  top: 48px;
  z-index: 40;
  background: color-mix(in srgb, var(--bg-50, #fff) 94%, transparent);
  -webkit-backdrop-filter: blur(16px);
  backdrop-filter: blur(16px);
  border-bottom: 0.5px solid var(--bg-200);
  max-width: 720px;
  margin: 0 auto;
}
.gg-cats__scroll {
  display: flex;
  gap: 6px;
  padding: 10px 16px;
  overflow-x: auto;
  scrollbar-width: none;
}
.gg-cats__scroll::-webkit-scrollbar { display: none; }
.gg-cat {
  flex-shrink: 0;
  padding: 6px 14px;
  background: transparent;
  border: none;
  border-radius: 16px;
  font-size: 14px;
  font-weight: 500;
  color: #606474;
  cursor: pointer;
  transition: all 150ms ease;
}
.gg-cat.is-active {
  background: color-mix(in srgb, var(--brand-500, #1942c2) 10%, transparent);
  color: var(--brand-500, #1942c2);
  font-weight: 700;
}

/* ====== 列表 ====== */
.gg-list {
  padding: 12px 12px 0;
}
.gg-list__inner {
  max-width: 720px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ====== 卡片 ====== */
.gg-card {
  background: var(--bg-50, #fff);
  border-radius: 14px;
  border: 0.5px solid var(--bg-200);
  overflow: hidden;
  cursor: pointer;
  transition: transform 150ms ease, box-shadow 150ms ease;
}
.gg-card:active { transform: scale(0.985); }
.gg-card--skeleton {
  height: 150px;
  background: linear-gradient(100deg, var(--bg-100) 40%, var(--bg-200) 50%, var(--bg-100) 60%);
  background-size: 200% 100%;
  animation: gg-shimmer 1.2s infinite;
}
@keyframes gg-shimmer {
  to { background-position: -200% 0; }
}

.gg-card__cover {
  position: relative;
  aspect-ratio: 16 / 7;
  overflow: hidden;
}
.gg-card__cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.gg-card__cover-mask {
  position: absolute;
  inset: 0;
  background: linear-gradient(to top, rgba(0, 0, 0, 0.45), transparent 55%);
}
.gg-card__cover-info {
  position: absolute;
  top: 10px;
  left: 10px;
  right: 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.gg-card__tags {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.gg-card__type-tag {
  padding: 3px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
}
.gg-card__type-tag.is-online {
  background: rgba(25, 66, 194, 0.1);
  color: #1942c2;
}
.gg-card__type-tag.is-offline {
  background: rgba(255, 138, 0, 0.12);
  color: #e07800;
}
.gg-card__status {
  padding: 3px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  background: rgba(52, 199, 89, 0.12);
  color: #28a745;
}
.gg-card__status.is-cancelled { background: rgba(142, 142, 147, 0.15); color: #8e8e93; }
.gg-card__status.is-ended { background: rgba(142, 142, 147, 0.15); color: #8e8e93; }

.gg-card__body { padding: 14px; }
.gg-card__title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-900, #111);
  line-height: 1.4;
  margin: 0 0 10px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.gg-card__meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}
.gg-card__meta-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-500, #505464);
}
.gg-card__meta-icon { flex-shrink: 0; color: var(--text-400); }
.gg-card__meta-icon :deep(svg) { width: 14px; height: 14px; }
.gg-card__countdown { color: #e07800; font-weight: 500; }
.gg-card__location {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gg-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 10px;
  border-top: 0.5px solid var(--bg-200);
}
.gg-card__host {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.gg-card__avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
}
.gg-card__avatar--fallback {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--brand-500) 15%, transparent);
  color: var(--brand-500);
  font-size: 13px;
  font-weight: 600;
}
.gg-card__host-name {
  font-size: 13px;
  color: var(--text-600);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.gg-card__cat {
  flex-shrink: 0;
  padding: 2px 8px;
  background: var(--bg-100);
  border-radius: 10px;
  font-size: 11px;
  color: var(--text-500);
}
.gg-card__people {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.gg-card__people-bar {
  width: 56px;
  height: 5px;
  background: var(--bg-200);
  border-radius: 3px;
  overflow: hidden;
}
.gg-card__people-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--brand-500), #4d7cff);
  border-radius: 3px;
  transition: width 300ms ease;
}
.gg-card__people-num {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-600);
  white-space: nowrap;
}

/* ====== 空状态 ====== */
.gg-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 80px 24px;
  text-align: center;
}
.gg-empty__icon { font-size: 56px; line-height: 1; }
.gg-empty__text {
  font-size: 14px;
  color: #505464;
  margin: 0;
}
.gg-empty__btn {
  margin-top: 8px;
  padding: 10px 28px;
  background: var(--brand-500, #1942c2);
  color: #fff;
  border: none;
  border-radius: 20px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

/* ====== 加载更多 ====== */
.gg-load-more {
  padding: 16px 0 4px;
  text-align: center;
  font-size: 12px;
  color: var(--text-400);
}
.gg-load-more__end { color: #868a99; }

/* ====== 发布 FAB ====== */
.gg-fab {
  position: fixed;
  right: calc(16px + env(safe-area-inset-right));
  bottom: calc(84px + env(safe-area-inset-bottom));
  z-index: 60;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  width: 56px;
  height: 56px;
  background: var(--brand-500, #1942c2);
  color: #fff;
  border: none;
  border-radius: 50%;
  font-size: 10px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(25, 66, 194, 0.35);
}
.gg-fab :deep(svg) { width: 22px; height: 22px; }
</style>
