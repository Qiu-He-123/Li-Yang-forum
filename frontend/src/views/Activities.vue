<script setup lang="ts">
/**
 * 活动板块：校园活动列表
 * - 卡片展示封面/标题/时间/地点/报名人数
 * - 下拉加载更多
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import EmptyState from '../components/common/EmptyState.vue'
import InfiniteScrollFooter from '../components/common/InfiniteScrollFooter.vue'
import { Icon } from '../components/native'
import { listActivities, type Activity } from '../api/activity'
import { useInfiniteScroll } from '../composables/useInfiniteScroll'

const router = useRouter()

const items = ref<Activity[]>([])
const loading = ref(false)
const page = ref(1)
const total = ref(0)
const pageSize = 10
const hasMore = computed(() => items.value.length < total.value)

async function loadMore() {
  const nextPage = page.value + 1
  const { data } = await listActivities(nextPage, pageSize, {
    showGlobalLoading: false,
    showGlobalError: false,
  })
  const newItems = data.data.items || []
  const ids = new Set(items.value.map((i) => i.id))
  items.value = [...items.value, ...newItems.filter((i) => !ids.has(i.id))]
  total.value = data.data.total || 0
  page.value = nextPage
}

const { loading: loadingMore, error: scrollError, retry } = useInfiniteScroll({
  hasMore,
  onLoadMore: loadMore,
})

async function loadFirstPage() {
  loading.value = true
  try {
    const { data } = await listActivities(1, pageSize, {
      showGlobalLoading: false,
      showGlobalError: false,
    })
    items.value = data.data.items || []
    total.value = data.data.total || 0
    page.value = 1
  } finally {
    loading.value = false
  }
}

function goBack() {
  router.back()
}

function fmtTime(iso: string | null): string {
  if (!iso) return '待定'
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function isOngoing(a: Activity): boolean {
  if (!a.start_at) return true
  return new Date(a.start_at).getTime() <= Date.now() && (!a.end_at || new Date(a.end_at).getTime() > Date.now())
}

onMounted(loadFirstPage)
</script>

<template>
  <main class="page-activities">
    <div class="act-topbar">
      <button class="icon-btn" type="button" aria-label="返回" @click="goBack">
        <Icon name="arrow-left" :size="20" />
      </button>
      <span class="act-title">社区活动</span>
      <span class="icon-btn-placeholder" />
    </div>

    <div v-if="items.length" class="act-list">
      <button
        v-for="a in items"
        :key="a.id"
        class="act-card"
        type="button"
        @click="router.push(`/activities/${a.id}`)"
      >
        <div
          class="act-cover"
          :class="{ 'no-cover': !a.cover_url }"
          :style="a.cover_url ? { backgroundImage: `url(${a.cover_url})` } : undefined"
        >
          <span v-if="!a.cover_url" class="act-cover-icon">
            <Icon name="calendar" :size="26" color="#fff" />
          </span>
          <span class="act-status" :class="{ 'is-ended': !isOngoing(a) }">
            {{ isOngoing(a) ? '进行中' : '已结束' }}
          </span>
        </div>
        <div class="act-card-body">
          <h3 class="act-name">{{ a.title }}</h3>
          <p class="act-meta">
            <Icon name="clock" :size="12" />
            {{ fmtTime(a.start_at) }}
          </p>
          <p v-if="a.location" class="act-meta">
            <Icon name="map-pin" :size="12" />
            {{ a.location }}
          </p>
          <div class="act-card-foot">
            <span class="act-count">
              {{ a.participant_count }}{{ a.max_participants ? ` / ${a.max_participants}` : '' }} 人报名
            </span>
            <span class="act-join-state" :class="{ 'is-joined': a.joined }">
              {{ a.joined ? '已报名' : '去看看' }}
            </span>
          </div>
        </div>
      </button>
      <InfiniteScrollFooter
        :loading="loadingMore"
        :error="scrollError"
        :has-more="hasMore"
        :has-items="items.length > 0"
        @retry="retry"
      />
    </div>
    <div v-else-if="!loading" class="act-empty">
      <EmptyState icon="calendar" text="暂无活动，敬请期待" />
    </div>
  </main>
</template>

<style scoped>
.page-activities {
  min-height: 100vh;
  background: var(--bg-100, #f2f2f7);
  padding-bottom: 24px;
}

.act-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 48px;
  padding: 0 12px;
  background: var(--bg-50, #fff);
  border-bottom: 1px solid var(--bg-300, #e5e5ea);
  position: sticky;
  top: 0;
  z-index: 10;
}

.icon-btn {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: transparent;
  border: none;
  color: var(--text-900, #1c1c1e);
}

.icon-btn-placeholder {
  width: 36px;
}

.act-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-900, #1c1c1e);
}

.act-list {
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.act-card {
  display: flex;
  gap: 12px;
  padding: 0;
  border: none;
  background: var(--bg-50, #fff);
  border-radius: 14px;
  overflow: hidden;
  text-align: left;
  cursor: pointer;
  box-shadow: var(--shadow-sm, 0 1px 4px rgba(0, 0, 0, 0.08));
}

.act-card:active {
  transform: scale(0.99);
}

.act-cover {
  position: relative;
  flex: none;
  width: 104px;
  min-height: 104px;
  background-size: cover;
  background-position: center;
  display: grid;
  place-items: center;
}

.act-cover.no-cover {
  background: linear-gradient(135deg, #0a84ff, #5856d6);
}

.act-cover-icon {
  opacity: 0.9;
}

.act-status {
  position: absolute;
  left: 6px;
  bottom: 6px;
  font-size: 10px;
  color: #fff;
  background: rgba(52, 199, 89, 0.92);
  padding: 2px 7px;
  border-radius: 8px;
}

.act-status.is-ended {
  background: rgba(142, 142, 147, 0.9);
}

.act-card-body {
  flex: 1;
  min-width: 0;
  padding: 10px 12px 10px 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.act-name {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-900, #1c1c1e);
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.act-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 0;
  font-size: 12px;
  color: var(--text-500, #8e8e93);
}

.act-card-foot {
  margin-top: auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.act-count {
  font-size: 12px;
  color: var(--text-500, #8e8e93);
}

.act-join-state {
  font-size: 12px;
  font-weight: 600;
  color: #007aff;
}

.act-join-state.is-joined {
  color: #34c759;
}

.act-empty {
  padding-top: 80px;
}
</style>
