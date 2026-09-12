<script setup lang="ts">
/**
 * 我的订单（项目 2）
 * 全部 / 我发布的 / 我接的，分页加载。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import EmptyState from '../../components/common/EmptyState.vue'
import InfiniteScrollFooter from '../../components/common/InfiniteScrollFooter.vue'
import { Icon } from '../../components/native'
import { toast } from '../../components/native/Toast'
import { myOrders, ORDER_STATUS_META, type OrderTask } from '../../api/order'
import { useInfiniteScroll } from '../../composables/useInfiniteScroll'

const router = useRouter()
const items = ref<OrderTask[]>([])
const role = ref<'all' | 'posted' | 'taken'>('all')
const total = ref(0)
const page = ref(1)
const pageSize = 12
const loading = ref(false)
const hasMore = computed(() => items.value.length < total.value)

async function fetchPage(p: number) {
  const { data } = await myOrders({ role: role.value, page: p, page_size: pageSize })
  return { rows: data.data.items || [], total: data.data.total }
}

async function loadMore() {
  const next = page.value + 1
  const { rows, total: t } = await fetchPage(next)
  const ids = new Set(items.value.map((i) => i.id))
  items.value = [...items.value, ...rows.filter((i) => !ids.has(i.id))]
  total.value = t
  page.value = next
}
const { loading: loadingMore, error: scrollError, retry } = useInfiniteScroll({ hasMore, onLoadMore: loadMore })

async function loadFirst() {
  loading.value = true
  try {
    const { rows, total: t } = await fetchPage(1)
    items.value = rows
    total.value = t
    page.value = 1
  } catch (e) {
    toast.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

function onRole(v: 'all' | 'posted' | 'taken') {
  role.value = v
  loadFirst()
}
function goDetail(t: OrderTask) { router.push(`/orders/${t.id}`) }
function goBack() { router.push('/orders') }

onMounted(loadFirst)
</script>

<template>
  <div class="mo-page">
    <header class="mo-header">
      <button class="mo-back" type="button" aria-label="返回" @click="goBack">
        <Icon name="chevron-left" :size="22" />
      </button>
      <h1>我的订单</h1>
      <div class="mo-spacer" />
    </header>

    <nav class="mo-tabs">
      <button type="button" :class="{ active: role === 'all' }" @click="onRole('all')">全部</button>
      <button type="button" :class="{ active: role === 'posted' }" @click="onRole('posted')">我发布的</button>
      <button type="button" :class="{ active: role === 'taken' }" @click="onRole('taken')">我接的</button>
    </nav>

    <main class="mo-list">
      <EmptyState v-if="!loading && items.length === 0" text="暂无订单" />
      <article v-for="t in items" :key="t.id" class="mo-card" @click="goDetail(t)">
        <div class="mo-top">
          <span class="mo-cat">{{ t.category }}</span>
          <span class="mo-status" :class="ORDER_STATUS_META[t.status]?.cls || ''">
            {{ ORDER_STATUS_META[t.status]?.text || t.status }}
          </span>
        </div>
        <h2 class="mo-title">{{ t.title }}</h2>
        <div class="mo-bottom">
          <span class="mo-reward">{{ t.reward }} 交易币</span>
          <span v-if="t.is_mine" class="mo-tag mine">我发布的</span>
          <span v-else-if="t.is_assigned_to_me" class="mo-tag taken">我接的</span>
        </div>
      </article>
      <InfiniteScrollFooter :loading="loadingMore" :error="scrollError" :has-more="hasMore" :has-items="items.length > 0" @retry="retry" />
    </main>
  </div>
</template>

<style scoped>
.mo-page { min-height: 100vh; background: #f7f8fb; color: #1d1d1f; padding-bottom: 40px; }
.mo-header { position: sticky; top: 0; z-index: 10; display: flex; align-items: center; gap: 8px; padding: calc(10px + env(safe-area-inset-top,0px)) 14px 10px; background: rgba(255,255,255,0.86); -webkit-backdrop-filter: saturate(1.8) blur(16px); backdrop-filter: saturate(1.8) blur(16px); border-bottom: 1px solid rgba(0,0,0,0.05); }
.mo-header h1 { margin: 0; font-size: 18px; font-weight: 800; flex: 1; text-align: center; }
.mo-back { width: 34px; height: 34px; border: none; background: transparent; cursor: pointer; display: grid; place-items: center; }
.mo-spacer { width: 34px; }
.mo-tabs { display: flex; gap: 8px; padding: 12px 14px; position: sticky; top: 52px; z-index: 9; background: rgba(247,248,251,0.9); -webkit-backdrop-filter: blur(12px); backdrop-filter: blur(12px); }
.mo-tabs button { flex: 1; height: 34px; border: none; border-radius: 17px; background: #fff; color: #6e6e73; font-size: 14px; font-weight: 600; cursor: pointer; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.mo-tabs button.active { background: #0071e3; color: #fff; box-shadow: 0 4px 12px rgba(0,113,227,0.3); }
.mo-list { padding: 4px 14px; max-width: 720px; margin: 0 auto; }
.mo-card { margin-bottom: 12px; padding: 14px; border-radius: 16px; background: #fff; box-shadow: 0 2px 8px rgba(0,0,0,0.05); cursor: pointer; }
.mo-top { display: flex; align-items: center; justify-content: space-between; }
.mo-cat { font-size: 12px; color: #0071e3; background: rgba(0,113,227,0.08); padding: 2px 9px; border-radius: 8px; font-weight: 700; }
.mo-status { font-size: 12px; font-weight: 800; }
.st-open { color: #0071e3; } .st-going { color: #ff9500; } .st-done { color: #34c759; } .st-completed { color: #6e6e73; } .st-cancel { color: #ff3b30; }
.mo-title { font-size: 16px; font-weight: 800; margin: 10px 0 8px; }
.mo-bottom { display: flex; align-items: center; justify-content: space-between; }
.mo-reward { font-size: 18px; font-weight: 800; color: #0071e3; }
.mo-tag { font-size: 11px; padding: 2px 8px; border-radius: 8px; font-weight: 600; }
.mo-tag.mine { background: rgba(0,113,227,0.1); color: #0071e3; }
.mo-tag.taken { background: rgba(88,86,214,0.1); color: #5856d6; }
@media (min-width: 720px) { .mo-list { padding-top: 8px; gap: 12px; } }
</style>