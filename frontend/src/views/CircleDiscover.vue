<script setup lang="ts">
/**
 * 社交页（路由：/circles，底部 Tab「社交」）—— 与首页 UI 一致
 * - 顶部固定标题栏：标题「同伴圈·社交」居中 + 右侧搜索按钮（样式与首页一致）
 * - 一排圈子快捷入口（circleStore 驱动，渐变图标 + 名字 + 「全部圈子」末位卡片）
 * - 组局分类导航：全部 / 游戏组局 / 现实组局 / …（点击「现实组局」仅匹配 type=线下）
 * - 组局状态筛选：全部 / 招募中 / 已截至（已到截止时间的组局不再显示「招募中」）
 * - 下方：组局卡片列表，滚动到底自动加载
 * - 右下角蓝色拍摄按钮 → 发布游戏组局
 */
import { computed, onActivated, onMounted, ref } from 'vue'
import { useFadeUpdate } from '../composables/useFadeUpdate'
defineOptions({ name: 'CircleDiscoverView' })

const { fadeActive, triggerFade } = useFadeUpdate()
import { useRouter } from 'vue-router'
import { Icon } from '../components/native'
import InfiniteScrollFooter from '../components/common/InfiniteScrollFooter.vue'
import EmptyState from '../components/common/EmptyState.vue'
import PostListSkeleton from '../components/post/PostListSkeleton.vue'
import { useInfiniteScroll } from '../composables/useInfiniteScroll'
import { listGatherings, listGatheringCategories, type Gathering } from '../api/gathering'
import { useCircleStore } from '../stores/circle'

const router = useRouter()
const circleStore = useCircleStore()

// ====== 顶部通道导航：圈子 / 组局 ======
// 关注、推荐已移除（回到首页 Feed 用首页通道栏），此处仅保留站点内切换
const topNavTabs: { key: string; label: string }[] = [
  { key: 'circle', label: '圈子' },
  { key: 'gathering', label: '组局' },
]
const activeTopNav = ref<string>('gathering')

function onTopNav(key: string) {
  // 组局留在本页（下方组局列表）
  if (key === 'gathering') {
    activeTopNav.value = 'gathering'
    scrollShowcaseIntoView()
    return
  }
  // 圈子 → 圈子广场
  if (key === 'circle') {
    activeTopNav.value = 'circle'
    router.push('/circles/all')
  }
}
/** 组局：吸顶后回落到组局列表顶部，避免被导航遮挡 */
function scrollShowcaseIntoView() {
  requestAnimationFrame(() => {
    const show = document.querySelector<HTMLElement>('.page-discover .plaza-list')
    const header = document.querySelector<HTMLElement>('.page-discover .site-header')
    const quick = document.querySelector<HTMLElement>('.page-discover .plaza-quick')
    const overlay = (header ? header.clientHeight : 0) + (quick ? quick.clientHeight : 0)
    if (show) {
      const top = show.getBoundingClientRect().top + window.pageYOffset - overlay - 8
      window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' })
    }
  })
}

// ====== 圈子快捷入口（一排，circleStore 驱动）======
// 固定排序：按后端 sort_order 升序，保证「表白墙→求助区→游戏开黑」顺序永远不变
const sortedCircles = computed(() =>
  [...circleStore.circles].sort(
    (a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0),
  ),
)
const plazaCircles = computed(() => sortedCircles.value.slice(0, 6))
const totalCircleCount = computed(
  () => circleStore.circles.filter((c) => c.slug !== 'default').length,
)

// 圈子图标与色调映射（对齐 AllCircles/discover 设计稿）
const circleMeta: Record<string, { icon: string; gradient: string }> = {
  confess: { icon: 'heart', gradient: 'linear-gradient(135deg, #ff6b9d, #af52de)' },
  help: { icon: 'circle-question', gradient: 'linear-gradient(135deg, #66abff, #0064d6)' },
  qa: { icon: 'circle-question', gradient: 'linear-gradient(135deg, #66abff, #0064d6)' },
  lost: { icon: 'circle-question', gradient: 'linear-gradient(135deg, #66abff, #0064d6)' },
  market: { icon: 'tag', gradient: 'linear-gradient(135deg, #ff9500, #ff6b35)' },
  study: { icon: 'file', gradient: 'linear-gradient(135deg, #34c759, #007aff)' },
  food: { icon: 'map-pin', gradient: 'linear-gradient(135deg, #ffb347, #ff9500)' },
  game: { icon: 'star', gradient: 'linear-gradient(135deg, #5856d6, #af52de)' },
  club: { icon: 'star', gradient: 'linear-gradient(135deg, #af52de, #ff6b9d)' },
  sport: { icon: 'flame', gradient: 'linear-gradient(135deg, #007aff, #34c759)' },
  treehole: { icon: 'lock', gradient: 'linear-gradient(135deg, #8e8e93, #48484a)' },
  flea: { icon: 'tag', gradient: 'linear-gradient(135deg, #34c759, #00c7be)' },
}
function getCircleMeta(slug: string) {
  return (
    circleMeta[slug] || {
      icon: 'sparkles',
      gradient: 'linear-gradient(135deg, #66abff, #007aff)',
    }
  )
}
function openCircle(slug: string) {
  if (!slug) return
  router.push(`/circle/${slug}`)
}

// ====== 组局分类导航：全部 + 各组局分类 ======
const categoryTabs = ref<string[]>(['全部'])
const activeCategory = ref('全部')

// ====== 组局状态筛选：全部 / 招募中 / 已截至 ======
type StatusMode = 'all' | 'recruiting' | 'ended'
const activeStatus = ref<StatusMode>('recruiting')
const statusTabs: { key: StatusMode; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'recruiting', label: '招募中' },
  { key: 'ended', label: '已截至' },
]
/** 组局是否已截止（含已取消/已结束/已过截止时间） */
function isGatheringEnded(g: Gathering): boolean {
  if (g.status === 'cancelled' || g.status === 'ended') return true
  if (g.end_time && new Date(g.end_time).getTime() <= Date.now()) return true
  return false
}

async function loadCategories() {
  try {
    const { data: resp } = await listGatheringCategories()
    const cats = resp.data || []
    categoryTabs.value = ['全部', ...cats.filter((c: string) => c && c !== '全部')]
  } catch {
    categoryTabs.value = ['全部']
  }
}

// ====== 组局列表（真实后端，滚动分页）======
const gatherings = ref<Gathering[]>([])
const total = ref(0)
const page = ref(1)
const PAGE_SIZE = 20
const loading = ref(false)
const loadingMore = ref(false)
const error = ref('')
const hasMore = computed(() => {
  // 「已截至 / 全部」一次性拉取（page_size 放大），不做滚动分页
  if (activeStatus.value !== 'recruiting') return false
  return gatherings.value.length < total.value
})

const { error: scrollError, retry: retryScroll } = useInfiniteScroll({
  hasMore,
  onLoadMore: () => loadGatherings(false),
  containerSelector: '.page-discover',
})

async function loadGatherings(resetPage = true) {
  if (!resetPage && (loadingMore.value || !hasMore.value)) return
  resetPage ? (loading.value = true) : (loadingMore.value = true)
  if (resetPage) error.value = ''
  try {
    const p = resetPage ? 1 : page.value + 1
    // 「现实组局」分类固定匹配线下（type=offline）
    const isShiXian = activeCategory.value === '现实组局'
    const loadAll = activeStatus.value !== 'recruiting'
    const { data } = await listGatherings(
      {
        category: activeCategory.value === '全部' ? undefined : activeCategory.value,
        type: isShiXian ? 'offline' : undefined,
        all_status: loadAll,
        page: p,
        page_size: loadAll ? 100 : PAGE_SIZE,
      },
      resetPage ? {} : { showGlobalLoading: false, showGlobalError: false },
    )
    const payload = data.data
    let items: Gathering[] = payload.items || []
    // 「已截至」模式：仅保留已截止（含过期）的组局
    if (activeStatus.value === 'ended') {
      items = items.filter(isGatheringEnded)
    }
    if (resetPage) {
      gatherings.value = items
    } else {
      const existIds = new Set(gatherings.value.map((g) => g.id))
      gatherings.value = [...gatherings.value, ...items.filter((g) => !existIds.has(g.id))]
    }
    total.value = payload.total || 0
    page.value = payload.page || p
  } catch (err) {
    if (resetPage) error.value = (err as Error).message || '加载失败'
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

function selectCategory(cat: string) {
  if (activeCategory.value === cat) return
  activeCategory.value = cat
  triggerFade()
  loadGatherings(true)
}

function selectStatus(key: StatusMode) {
  if (activeStatus.value === key) return
  activeStatus.value = key
  triggerFade()
  loadGatherings(true)
}

function openGathering(g: Gathering) {
  router.push(`/gatherings/${g.id}`)
}

function onSearch() {
  router.push('/search')
}

// ====== 展示辅助 ======
function isImageUrl(url: string | null | undefined): boolean {
  return !!url && (url.startsWith('/') || url.startsWith('http'))
}
function footerStatusText(g: Gathering): string {
  if (g.status === 'cancelled') return '已取消'
  if (g.status === 'ended') return '已结束'
  if (g.end_time && new Date(g.end_time).getTime() <= Date.now()) return '已结束'
  if (g.joined_people >= g.max_people) return '已满员'
  return '招募中'
}
function categoryEmoji(cat: string | null): string {
  if (!cat) return '🎪'
  if (cat.includes('游戏')) return '🎮'
  if (cat.includes('现实') || cat.includes('线下')) return '📍'
  if (cat.includes('运动') || cat.includes('健身')) return '⚽'
  if (cat.includes('吃饭') || cat.includes('拼单') || cat.includes('美食')) return '🍜'
  if (cat.includes('学习') || cat.includes('自习')) return '📚'
  if (cat.includes('音乐')) return '🎵'
  if (cat.includes('电影')) return '🎬'
  if (cat.includes('聊天') || cat.includes('扩列')) return '💬'
  return '🎪'
}
function timeText(iso: string | null): string {
  if (!iso) return '时间待定'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '时间待定'
  const now = new Date()
  const md = `${d.getMonth() + 1}月${d.getDate()}日`
  const hm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  return d.getFullYear() === now.getFullYear() ? `${md} ${hm}` : `${d.getFullYear()}年${md} ${hm}`
}

onMounted(async () => {
  circleStore.loadCircles()
  await loadCategories()
  await loadGatherings(true)
})
// 从后台返回时刷新数据，保证人数进度/状态最新
onActivated(() => {
  loadGatherings(true)
})
</script>

<template>
  <div class="page-discover" :class="{ 'swr-updated': fadeActive }">
    <!-- ====== 顶部固定栏：与首页 site-header 完全一致（白底 / 标题居中 / 右侧搜索）===== -->
    <header class="site-header" role="banner">
      <div class="header-inner">
        <div class="header-side header-side--left" aria-hidden="true"></div>
        <h1 class="header-title">同伴圈·社交</h1>
        <div class="header-side header-side--right">
          <button class="icon-btn" type="button" aria-label="搜索" @click="onSearch">
            <Icon name="search" :size="20" />
          </button>
        </div>
      </div>
    </header>

    <div class="social-container">
    <!-- ====== 通道 Tab：关注 / 推荐 / 圈子 / 组局（feed-tabs 风格，动态加粗+蓝色下划线）===== -->
    <nav class="feed-tabs" role="tablist" aria-label="社交通道">
      <button
        v-for="t in topNavTabs"
        :key="t.key"
        type="button"
        class="feed-tab"
        :class="{ 'is-active': activeTopNav === t.key }"
        role="tab"
        :aria-selected="activeTopNav === t.key"
        @click="onTopNav(t.key)"
      >{{ t.label }}</button>
    </nav>

    <!-- 一排圈子快捷入口 -->
    <section class="plaza-quick" aria-label="圈子入口">
      <div class="plaza-quick__scroll">
        <a
          v-for="circle in plazaCircles"
          :key="'qc-' + circle.id"
          class="plaza-quick__item"
          @click="openCircle(circle.slug)"
        >
          <span
            class="plaza-quick__ic"
            :style="{
              background: getCircleMeta(circle.slug).gradient,
              '--ring': getCircleMeta(circle.slug).gradient,
            }"
            aria-hidden="true"
          >
            <Icon :name="getCircleMeta(circle.slug).icon" :size="24" color="#fff" :stroke-width="1.5" />
          </span>
          <span class="plaza-quick__name">{{ circle.name }}</span>
        </a>
        <!-- 末位：查看全部 -->
        <a
          v-if="totalCircleCount > 6"
          class="plaza-quick__item"
          @click="router.push('/circles/all')"
        >
          <span class="plaza-quick__ic plaza-quick__ic--all" aria-hidden="true">
            <Icon name="grid" :size="24" color="#fff" :stroke-width="1.5" />
          </span>
          <span class="plaza-quick__name">全部圈子</span>
        </a>
      </div>
    </section>

    <!-- 组局状态筛选 -->
    <nav class="plaza-status" aria-label="组局状态筛选">
      <button
        v-for="s in statusTabs"
        :key="s.key"
        type="button"
        class="plaza-status__tab"
        :class="{ 'is-active': activeStatus === s.key }"
        @click="selectStatus(s.key)"
      >
        {{ s.label }}
      </button>
    </nav>

    <!-- 组局分类导航 -->
    <nav class="plaza-cats" aria-label="组局分类">
      <div class="plaza-cats__scroll">
        <button
          v-for="cat in categoryTabs"
          :key="cat"
          type="button"
          class="plaza-cat"
          :class="{ 'is-active': activeCategory === cat }"
          @click="selectCategory(cat)"
        >
          {{ cat }}
        </button>
      </div>
    </nav>

    <!-- 组局列表 -->
    <main class="plaza-list">
      <PostListSkeleton v-if="loading" :count="4" />

      <template v-else>
        <div v-if="error" class="plaza-error">
          <p class="plaza-error__text">加载失败，请检查网络后重试</p>
          <button class="plaza-error__btn" type="button" @click="loadGatherings(true)">重新加载</button>
        </div>

        <EmptyState
          v-else-if="!gatherings.length"
          icon="calendar"
          :text="activeStatus === 'ended' ? '暂无已截至的组局' : '还没有招募中的组局，去发起一个吧～'"
        />

        <div v-else class="plaza-list__inner">
          <article
            v-for="g in gatherings"
            :key="g.id"
            class="room-card"
            @click="openGathering(g)"
          >
            <!-- 封面图 -->
            <div v-if="g.images.length && isImageUrl(g.images[0])" class="room-card__cover">
              <img :src="g.images[0]" :alt="g.title" loading="lazy" />
              <span class="room-card__cover-mask"></span>
              <div class="room-card__cover-info">
                <span class="room-card__type" :class="g.type === 'online' ? 'is-online' : 'is-offline'">
                  {{ g.type === 'online' ? '🎮 线上' : '📍 线下' }}
                </span>
                <span class="room-card__status" :class="g.status">{{ footerStatusText(g) }}</span>
              </div>
            </div>

            <div class="room-card__body">
              <div v-if="!(g.images.length && isImageUrl(g.images[0]))" class="room-card__tags">
                <span class="room-card__type" :class="g.type === 'online' ? 'is-online' : 'is-offline'">
                  {{ g.type === 'online' ? '🎮 线上' : '📍 线下' }}
                </span>
                <span class="room-card__status" :class="g.status">{{ footerStatusText(g) }}</span>
              </div>

              <h3 class="room-card__title">
                <span class="room-card__emoji">{{ categoryEmoji(g.category) }}</span>
                {{ g.title }}
              </h3>

              <div class="room-card__meta">
                <div class="room-card__meta-row">
                  <Icon name="clock" :size="14" class="room-card__icon" />
                  <span>{{ timeText(g.start_time) }}</span>
                </div>
                <div v-if="g.location" class="room-card__meta-row">
                  <Icon name="map-pin" :size="14" class="room-card__icon" />
                  <span class="room-card__location">{{ g.location }}</span>
                </div>
              </div>

              <div class="room-card__footer">
                <div class="room-card__host">
                  <img v-if="g.host.avatar" class="room-card__avatar" :src="g.host.avatar" alt="" />
                  <span v-else class="room-card__avatar room-card__avatar--fallback">
                    {{ g.host.nickname.slice(0, 1) }}
                  </span>
                  <span class="room-card__host-name">{{ g.host.nickname }}</span>
                  <span class="room-card__cat">{{ g.category }}</span>
                </div>
                <div class="room-card__people">
                  <div class="room-card__people-bar">
                    <div
                      class="room-card__people-fill"
                      :style="{ width: Math.min(100, (g.joined_people / g.max_people) * 100) + '%' }"
                    ></div>
                  </div>
                  <span class="room-card__people-num">{{ g.joined_people }}/{{ g.max_people }}人</span>
                </div>
              </div>
            </div>
          </article>

          <div class="plaza-list__foot">
            <InfiniteScrollFooter
              :loading="loadingMore"
              :error="scrollError"
              :has-more="hasMore"
              :has-items="gatherings.length > 0"
              @retry="retryScroll"
            />
          </div>
        </div>
      </template>
    </main>

    </div><!-- /social-container -->

    <!-- 右下角发布按钮 → 发布游戏组局 -->
    <button class="plaza-fab" type="button" aria-label="发布游戏组局" @click="router.push('/publish/gathering')">
      <Icon name="camera" :size="24" color="#fff" />
    </button>
  </div>
</template>

<style scoped>
.page-discover {
  --dd-bg: #f2f3f7;
  --brand-600: #1942c2;
  --home-tab-unselected: #606474;
  --home-icon-deep: #222222;
  min-height: 100vh;
  background: var(--dd-bg);
  padding-top: 56px;
  padding-bottom: calc(96px + env(safe-area-inset-bottom));
  max-width: 720px;
  margin: 0 auto;
}
.swr-updated { animation: dd-fade 0.4s ease; }
@keyframes dd-fade { from { opacity: 0.4; } to { opacity: 1; } }

/* 内容容器：把 Tab / 圈子 / 筛选 / 列表包在内，控制内边距 */
.social-container {
  max-width: 100%;
}

/* ====== 顶部固定栏：与首页 site-header 完全一致（白底 / 标题居中 / 右侧搜索）====== */
.site-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  height: 56px;
  background: #ffffff;
  border-bottom: 0.5px solid #e9e7ef;
  max-width: 720px;
  margin: 0 auto;
}
.header-inner {
  height: 100%;
  padding: 0 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.header-side {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
}
.header-side--left { justify-content: flex-start; }
.header-side--right { justify-content: flex-end; gap: 6px; }
.header-title {
  flex: 0 0 auto;
  font-size: 18px;
  font-weight: 700;
  color: #1d1d1f;
  letter-spacing: -0.01em;
  text-align: center;
  white-space: nowrap;
  margin: 0;
}
.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  color: var(--home-icon-deep);
  background: transparent;
  border: none;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 150ms cubic-bezier(0.32, 0.72, 0, 1), color 150ms ease;
}
.icon-btn:hover { background: rgba(0, 0, 0, 0.05); color: #000; }
.icon-btn :deep(svg) { width: 20px; height: 20px; }

/* ====== 通道 Tab：与首页 feed-tabs 一致（动态加粗 + 2px 蓝色下划线）====== */
.feed-tabs {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 12px 16px 0;
  border-bottom: none;
  overflow-x: auto;
  white-space: nowrap;
  scrollbar-width: none;
  /* 固定在顶部标题栏下方：滚动组局列表时通道栏依然可见可切换 */
  position: sticky;
  top: 56px;
  z-index: 90;
  background: var(--dd-bg);
}
.feed-tabs::-webkit-scrollbar { display: none; }
.feed-tab {
  position: relative;
  padding: 8px 2px 10px;
  font-size: 16px;
  font-weight: 400;
  color: var(--home-tab-unselected);
  background: transparent;
  flex: 0 0 auto;
  border: none;
  cursor: pointer;
  transition: color 150ms cubic-bezier(0.32, 0.72, 0, 1), font-weight 150ms cubic-bezier(0.32, 0.72, 0, 1);
}
.feed-tab::after {
  content: '';
  position: absolute;
  left: 50%;
  bottom: 2px;
  width: 60%;
  height: 2px;
  border-radius: 2px;
  background: transparent;
  transform: translateX(-50%) scaleX(0);
  transform-origin: center;
  transition: background 150ms ease, transform 180ms cubic-bezier(0.32, 0.72, 0, 1);
}
.feed-tab:hover { color: var(--brand-600); }
.feed-tab.is-active {
  color: var(--brand-600);
  font-weight: 700;
}
.feed-tab.is-active::after {
  background: var(--brand-600);
  transform: translateX(-50%) scaleX(1);
}

/* ====== 一排圈子快捷入口 ====== */
.plaza-quick { padding: 12px 0 4px; }
.plaza-quick__scroll {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 0 16px;
  overflow-x: auto;
  scrollbar-width: none;
}
.plaza-quick__scroll::-webkit-scrollbar { display: none; }
.plaza-quick__item {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  width: 58px;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}
.plaza-quick__ic {
  position: relative;
  width: 50px;
  height: 50px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 6px 14px rgba(0, 0, 0, 0.12), inset 0 0 0 1px rgba(255, 255, 255, 0.25);
  transition: transform 150ms cubic-bezier(0.32, 0.72, 0, 1), box-shadow 150ms ease;
}
.plaza-quick__ic::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: var(--ring, linear-gradient(135deg, #66abff, #007aff));
  filter: blur(8px);
  opacity: 0.35;
  z-index: -1;
}
.plaza-quick__item:active .plaza-quick__ic { transform: scale(0.92); }
.plaza-quick__ic--all { background: linear-gradient(135deg, #1c1c1e, #3a3a3c); }
.plaza-quick__name {
  font-size: 12px;
  color: #3c3c43;
  max-width: 62px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ====== 组局状态筛选 ====== */
.plaza-status {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px 4px;
}
.plaza-status__tab {
  flex-shrink: 0;
  padding: 6px 15px;
  background: transparent;
  border: none;
  border-radius: 16px;
  font-size: 14px;
  font-weight: 500;
  color: #60647a;
  cursor: pointer;
  transition: all 0.18s ease;
}
.plaza-status__tab.is-active {
  background: color-mix(in srgb, #1942c2 12%, transparent);
  color: #1942c2;
  font-weight: 700;
}

/* ====== 分类导航 ====== */
.plaza-cats {
  position: sticky;
  top: 56px; /* 固定白色标题栏高度 */
  z-index: 45;
  background: color-mix(in srgb, var(--dd-bg, #f2f3f7) 95%, transparent);
  -webkit-backdrop-filter: blur(14px);
  backdrop-filter: blur(14px);
  border-bottom: 0.5px solid rgba(0, 0, 0, 0.06);
}
.plaza-cats__scroll {
  display: flex;
  gap: 6px;
  padding: 10px 14px;
  overflow-x: auto;
  scrollbar-width: none;
}
.plaza-cats__scroll::-webkit-scrollbar { display: none; }
.plaza-cat {
  flex-shrink: 0;
  padding: 6px 15px;
  background: transparent;
  border: none;
  border-radius: 16px;
  font-size: 14px;
  font-weight: 500;
  color: #60647a;
  cursor: pointer;
  transition: all 0.18s ease;
}
.plaza-cat.is-active {
  background: color-mix(in srgb, #1942c2 12%, transparent);
  color: #1942c2;
  font-weight: 700;
}

/* ====== 列表 ====== */
.plaza-list {
  padding: 12px 12px 0;
}
.plaza-list__inner {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.plaza-list__foot { padding-top: 4px; }

/* ====== 组局卡片 ====== */
.room-card {
  background: #fff;
  border-radius: 16px;
  border: 0.5px solid rgba(0, 0, 0, 0.06);
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.room-card:active { transform: scale(0.985); }
.room-card__cover { position: relative; aspect-ratio: 16 / 8; overflow: hidden; }
.room-card__cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.room-card__cover-mask {
  position: absolute;
  inset: 0;
  background: linear-gradient(to top, rgba(0, 0, 0, 0.4), transparent 55%);
}
.room-card__cover-info {
  position: absolute;
  top: 10px;
  left: 10px;
  right: 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.room-card__tags {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.room-card__type {
  padding: 3px 10px;
  border-radius: 7px;
  font-size: 11px;
  font-weight: 600;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.08);
}
.room-card__type.is-online { color: #1942c2; }
.room-card__type.is-offline { color: #e07800; }
.room-card__status {
  padding: 3px 10px;
  border-radius: 7px;
  font-size: 11px;
  font-weight: 600;
  background: rgba(52, 199, 89, 0.14);
  color: #1f9d52;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.04);
}
.room-card__status.cancelled,
.room-card__status.ended { background: rgba(142, 142, 147, 0.16); color: #6d6d73; }

.room-card__body { padding: 14px; }
.room-card__title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 16px;
  font-weight: 600;
  color: #111;
  line-height: 1.4;
  margin: 0 0 10px;
  overflow-wrap: anywhere;
}
.room-card__emoji { flex-shrink: 0; }
.room-card__meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}
.room-card__meta-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #50546a;
}
.room-card__icon { flex-shrink: 0; color: #a0a4b3; }
.room-card__icon :deep(svg) { width: 14px; height: 14px; }
.room-card__location {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.room-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 10px;
  border-top: 0.5px solid rgba(0, 0, 0, 0.06);
}
.room-card__host {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.room-card__avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
}
.room-card__avatar--fallback {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, #1942c2 15%, transparent);
  color: #1942c2;
  font-size: 13px;
  font-weight: 700;
}
.room-card__host-name {
  font-size: 13px;
  color: #5a5e70;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.room-card__cat {
  flex-shrink: 0;
  padding: 2px 8px;
  background: #f0f1f5;
  border-radius: 10px;
  font-size: 11px;
  color: #5a5e70;
}
.room-card__people {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.room-card__people-bar {
  width: 56px;
  height: 5px;
  background: #ececf1;
  border-radius: 3px;
  overflow: hidden;
}
.room-card__people-fill {
  height: 100%;
  background: linear-gradient(90deg, #1942c2, #4d7cff);
  border-radius: 3px;
}
.room-card__people-num {
  font-size: 12px;
  font-weight: 600;
  color: #5a5e70;
  white-space: nowrap;
}

/* ====== 错误态 ====== */
.plaza-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 70px 24px;
  text-align: center;
}
.plaza-error__text { font-size: 14px; color: #60647a; margin: 0; }
.plaza-error__btn {
  padding: 9px 26px;
  background: #1942c2;
  color: #fff;
  border: none;
  border-radius: 20px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

/* ====== 右下角拍摄按钮 ====== */
.plaza-fab {
  position: fixed;
  right: calc(16px + env(safe-area-inset-right));
  bottom: calc(86px + env(safe-area-inset-bottom));
  z-index: 60;
  width: 58px;
  height: 58px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
  background: linear-gradient(135deg, #1942c2, #2f6bff);
  color: #fff;
  border: none;
  border-radius: 50%;
  font-size: 10px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 6px 18px rgba(25, 66, 194, 0.35);
  transition: transform 0.15s ease;
}
.plaza-fab:active { transform: scale(0.94); }
.plaza-fab :deep(svg) { width: 22px; height: 22px; }
</style>