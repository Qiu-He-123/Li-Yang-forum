<script setup lang="ts">
/**
 * 交易平台 · 任务管理（管理员）
 * 列表查看全部求助/接单任务，支持按状态过滤、下架。
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { adminListOrders, adminCancelOrder, type OrderTask } from '../../api/order'

const list = ref<OrderTask[]>([])
const loading = ref(false)
const total = ref(0)
const filter = reactive({ status: '', page: 1, page_size: 20 })

const tabs = [
  { value: '', label: '全部' },
  { value: 'open', label: '待接单' },
  { value: 'in_progress', label: '进行中' },
  { value: 'done', label: '已交付' },
  { value: 'completed', label: '已完成' },
  { value: 'cancelled', label: '已取消' },
]

const statusMap: Record<string, { type: 'primary' | 'warning' | 'success' | 'info' | 'danger'; text: string }> = {
  open: { type: 'primary', text: '待接单' },
  in_progress: { type: 'warning', text: '进行中' },
  done: { type: 'success', text: '已交付' },
  completed: { type: 'info', text: '已完成' },
  cancelled: { type: 'danger', text: '已取消' },
}

async function load() {
  loading.value = true
  try {
    const { data } = await adminListOrders({
      status: filter.status || undefined,
      page: filter.page,
      page_size: filter.page_size,
    })
    list.value = data.data.items || []
    total.value = data.data.total || 0
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

function onTab(v: string) { filter.status = v; filter.page = 1; load() }
function onPage(p: number) { filter.page = p; load() }

async function onCancel(row: OrderTask) {
  try {
    await ElMessageBox.confirm(`确认下架任务 #${row.id}「${row.title}」？托管悬赏将退回发布者。`, '下架任务', { type: 'warning' })
  } catch { return }
  try {
    await adminCancelOrder(row.id)
    ElMessage.success('已下架')
    load()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

function fmtTime(t?: string | null) { return t ? t.replace('T', ' ').slice(0, 19) : '' }

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="admin-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">交易平台 · 任务管理</h2>
        <p class="page-subtitle">共 {{ total }} 条求助任务 · 求助-接单-完单全流程</p>
      </div>
      <el-button :icon="'Refresh'" @click="load">刷新</el-button>
    </div>

    <div class="filter-card">
      <div class="status-tabs">
        <button v-for="t in tabs" :key="t.value" type="button" class="status-tab"
          :class="{ active: filter.status === t.value }" @click="onTab(t.value)">
          {{ t.label }}
        </button>
      </div>
    </div>

    <div class="table-card">
      <el-table :data="list" border stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" fixed />
        <el-table-column label="标题" min-width="200">
          <template #default="{ row }">
            <div class="cell-title">{{ row.title }}</div>
            <div class="cell-sub">{{ row.category }}</div>
          </template>
        </el-table-column>
        <el-table-column label="发布者" width="140">
          <template #default="{ row }">{{ row.poster_name || '用户' + row.user_id }}</template>
        </el-table-column>
        <el-table-column label="接单人" width="140">
          <template #default="{ row }">{{ row.assignee_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="悬赏" width="110">
          <template #default="{ row }"><b class="cell-coin">{{ row.reward }}</b> 交易币</template>
        </el-table-column>
        <el-table-column label="曝光" width="80">
          <template #default="{ row }">×{{ row.boost }}</template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="statusMap[row.status]?.type || 'info'">{{ statusMap[row.status]?.text || row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'open' || row.status === 'in_progress'" size="small" type="danger"
              plain @click="onCancel(row as OrderTask)">下架</el-button>
            <span v-else>—</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager-box">
        <el-pagination background layout="total, prev, pager, next" :total="total"
          :page-size="filter.page_size" :current-page="filter.page" @current-change="onPage" />
      </div>
    </div>
  </div>
</template>