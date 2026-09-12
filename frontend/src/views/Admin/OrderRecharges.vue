<script setup lang="ts">
/** 交易平台 · 充值审核（管理员） */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { adminListRecharges, adminApproveRecharge, adminRejectRecharge } from '../../api/order'

interface Row { id: number; user_name: string; amount: number; status: string; description?: string | null; created_at: string }
const list = ref<Row[]>([])
const loading = ref(false)
const total = ref(0)
const filter = reactive({ status: 'pending', page: 1, page_size: 20 })

const tabs = [
  { value: 'pending', label: '待审核' },
  { value: 'completed', label: '已到账' },
  { value: 'rejected', label: '已驳回' },
]
const statusMap: Record<string, { type: 'warning' | 'success' | 'danger'; text: string }> = {
  pending: { type: 'warning', text: '待审核' },
  completed: { type: 'success', text: '已到账' },
  rejected: { type: 'danger', text: '已驳回' },
}

async function load() {
  loading.value = true
  try {
    const { data } = await adminListRecharges({
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

async function approve(row: Row) {
  try { await ElMessageBox.confirm(`确认到账 #${row.id}（${row.user_name}）充值 ${row.amount} 交易币？`, '充值到账', { type: 'warning' }) } catch { return }
  try { await adminApproveRecharge(row.id); ElMessage.success('已到账'); load() } catch (e) { ElMessage.error((e as Error).message) }
}
async function reject(row: Row) {
  try { await ElMessageBox.confirm(`确认驳回充值 #${row.id}？`, '驳回充值', { type: 'warning' }) } catch { return }
  try { await adminRejectRecharge(row.id); ElMessage.success('已驳回'); load() } catch (e) { ElMessage.error((e as Error).message) }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="admin-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">交易平台 · 充值审核</h2>
        <p class="page-subtitle">共 {{ total }} 条充值单 · 人工审核到账（生产接入支付后自动）</p>
      </div>
      <el-button :icon="'Refresh'" @click="load">刷新</el-button>
    </div>

    <div class="filter-card">
      <div class="status-tabs">
        <button v-for="t in tabs" :key="t.value" type="button" class="status-tab"
          :class="{ active: filter.status === t.value }" @click="onTab(t.value)">{{ t.label }}</button>
      </div>
    </div>

    <div class="table-card">
      <el-table :data="list" border stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" fixed />
        <el-table-column label="用户" width="160">
          <template #default="{ row }">{{ row.user_name || '用户' }}</template>
        </el-table-column>
        <el-table-column label="到账交易币" width="140">
          <template #default="{ row }"><b class="cell-coin">{{ row.amount }}</b></template>
        </el-table-column>
        <el-table-column label="说明" min-width="200">
          <template #default="{ row }">{{ row.description }}</template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="statusMap[row.status]?.type || 'info'">{{ statusMap[row.status]?.text || row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ row.created_at }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <template v-if="row.status === 'pending'">
              <el-button size="small" type="success" @click="approve(row as Row)">到账</el-button>
              <el-button size="small" type="danger" plain @click="reject(row as Row)">驳回</el-button>
            </template>
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