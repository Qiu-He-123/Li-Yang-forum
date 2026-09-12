<script setup lang="ts">
/**
 * AI 助手日志（后台）
 * 记录全局浮窗 AI 助手每次对话的埋点：统计（今日/总量/命中率/近7天）+ 明细列表。
 */
import { onMounted, reactive, ref } from 'vue'

import { adminAssistantLogs, adminAssistantStats, type AssistantLogRow, type AssistantStats } from '../../api/assistant'

const loading = ref(false)
const list = ref<AssistantLogRow[]>([])
const total = ref(0)
const page = reactive({ page: 1, page_size: 20 })
const keyword = ref('')
const hitFilter = ref<'' | 'true' | 'false'>('')

const stats = ref<AssistantStats | null>(null)

async function load() {
  loading.value = true
  try {
    const { data } = await adminAssistantLogs({
      page: page.page,
      page_size: page.page_size,
      keyword: keyword.value || undefined,
      hit: hitFilter.value === '' ? undefined : hitFilter.value === 'true',
    })
    list.value = data.data.items || []
    total.value = data.data.total || 0
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    const { data } = await adminAssistantStats()
    stats.value = data.data
  } catch { /* ignore */ }
}

function onPage(p: number) { page.page = p; load() }
function onSearch() { page.page = 1; load() }

function maxDayCount() {
  return Math.max(1, ...(stats.value?.per_day || []).map((d) => d.count))
}

onMounted(() => { void load(); void loadStats() })
</script>

<template>
  <div class="admin-page">
    <el-card shadow="never" class="toolbar">
      <div class="toolbar-left">
        <h2 class="page-title">AI 助手日志</h2>
        <p class="page-desc">同伴圈全局 AI 助手每次对话的埋点记录，用于查看用户在看什么、命中率与常见诉求。</p>
      </div>
      <div class="toolbar-right">
        <el-select v-model="hitFilter" style="width: 130px" @change="onSearch">
          <el-option label="全部" value="" />
          <el-option label="已命中" value="true" />
          <el-option label="未命中" value="false" />
        </el-select>
        <el-input v-model="keyword" placeholder="搜索原话/回复/用户" clearable style="width: 220px" @keyup.enter="onSearch" @clear="onSearch" />
        <el-button type="primary" icon="Search" @click="onSearch">搜索</el-button>
      </div>
    </el-card>

    <template v-if="stats">
      <el-card shadow="never" class="stats-grid">
        <div class="stat-cell">
          <div class="stat-num">{{ stats.total }}</div>
          <div class="stat-lab">累计对话</div>
        </div>
        <div class="stat-cell">
          <div class="stat-num">{{ stats.hits }}</div>
          <div class="stat-lab">已命中意图</div>
        </div>
        <div class="stat-cell">
          <div class="stat-num">{{ (stats.hit_rate * 100).toFixed(1) }}%</div>
          <div class="stat-lab">命中率</div>
        </div>
        <div class="stat-cell stat-bars">
          <div class="bar-row" v-for="d in stats.per_day.slice(-7)" :key="d.date">
            <span class="bar-lab">{{ d.date.slice(5) }}</span>
            <span class="bar-track"><span class="bar-fill" :style="{ width: (d.count / maxDayCount() * 100) + '%' }" /></span>
            <span class="bar-val">{{ d.count }}</span>
          </div>
        </div>
      </el-card>
    </template>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="list" style="width: 100%">
        <el-table-column label="时间" prop="created_at" width="170" show-overflow-tooltip />
        <el-table-column label="用户" min-width="130">
          <template #default="{ row }">
            <div>{{ row.user_name || ('用户 #' + row.user_id) }}</div>
            <div class="muted">UID {{ row.user_id }}</div>
          </template>
        </el-table-column>
        <el-table-column label="原话" prop="input" min-width="180" show-overflow-tooltip />
        <el-table-column label="命中意图" min-width="120">
          <template #default="{ row }">
            <el-tag v-if="row.hit" type="success" size="small">{{ row.intent || '—' }}</el-tag>
            <el-tag v-else type="info" size="small" effect="plain">未命中</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="回复" prop="reply" min-width="200" show-overflow-tooltip />
        <el-table-column label="动作" prop="action" min-width="160" show-overflow-tooltip />
      </el-table>

      <el-pagination
        style="margin-top: 16px; justify-content: flex-end"
        layout="prev, pager, next, total"
        :page-size="page.page_size"
        :total="total"
        :current-page="page.page"
        @current-change="onPage"
      />
    </el-card>
  </div>
</template>

<style scoped>
.admin-page { display: flex; flex-direction: column; gap: 14px; }
.toolbar { display: flex; flex-direction: row; align-items: center; justify-content: space-between; gap: 16px; }
.toolbar-left { flex: 1; min-width: 0; }
.page-title { margin: 0 0 4px; font-size: 18px; }
.page-desc { margin: 0; color: var(--el-text-color-secondary); font-size: 13px; line-height: 1.6; }
.toolbar-right { display: flex; gap: 10px; align-items: center; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
.stats-grid { display: grid; grid-template-columns: repeat(3, 1fr) 2fr; gap: 16px; }
.stat-cell { text-align: center; }
.stat-num { font-size: 26px; font-weight: 700; }
.stat-lab { color: var(--el-text-color-secondary); font-size: 12px; margin-top: 2px; }
.stat-bars { display: flex; flex-direction: column; gap: 4px; justify-content: center; }
.bar-row { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.bar-lab { width: 40px; color: var(--el-text-color-secondary); }
.bar-track { flex: 1; height: 10px; border-radius: 5px; background: var(--el-fill-color); overflow: hidden; }
.bar-fill { display: block; height: 100%; border-radius: 5px; background: linear-gradient(90deg, #409eff, #67c23a); }
.bar-val { width: 34px; text-align: right; }
@media (max-width: 768px) {
  .stats-grid { grid-template-columns: repeat(3, 1fr); }
  .stat-bars { grid-column: 1 / -1; }
}
</style>