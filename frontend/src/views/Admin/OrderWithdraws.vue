<script setup lang="ts">
/** 交易平台 · 提现审核（管理员） */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { adminListWithdraws, adminApproveWithdraw, adminRejectWithdraw } from '../../api/order'

interface Row {
  id: number; user_name: string; amount_bin: number; amount_cents: number
  payee: string; status: string; reject_reason?: string | null; created_at: string
}
const list = ref<Row[]>([])
const loading = ref(false)
const total = ref(0)
const filter = reactive({ status: 'pending', page: 1, page_size: 20 })

const tabs = [
  { value: 'pending', label: '待审核' },
  { value: 'completed', label: '已打款' },
  { value: 'rejected', label: '已驳回' },
]
const statusMap: Record<string, { type: 'warning' | 'success' | 'danger'; text: string }> = {
  pending: { type: 'warning', text: '待审核' },
  completed: { type: 'success', text: '已打款' },
  rejected: { type: 'danger', text: '已驳回' },
}

async function load() {
  loading.value = true
  try {
    const { data } = await adminListWithdraws({
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
  try { await ElMessageBox.confirm(`确认打款 #${row.id}（${row.user_name}）¥${(row.amount_cents / 100).toFixed(2)}，收款 ${row.payee}？`, '提现打款', { type: 'warning' }) } catch { return }
  try { await adminApproveWithdraw(row.id); ElMessage.success('已打款'); load() } catch (e) { ElMessage.error((e as Error).message) }
}
async function reject(row: Row) {
  let reason = ''
  try { reason = (await ElMessageBox.prompt('请输入驳回原因', '驳回提现', { inputValue: '不符合提现条件' })).value.trim() || '' } catch { return }
  try { await adminRejectWithdraw(row.id, reason); ElMessage.success('已驳回，交易币已退回'); load() } catch (e) { ElMessage.error((e as Error).message) }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="admin-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">交易平台 · 提现审核</h2>
        <p class="page-subtitle">共 {{ total }} 条提现单 · 驳回自动退回交易币</p>
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
        <el-table-column label="用户" width="150">
          <template #default="{ row }">{{ row.user_name || '用户' }}</template>
        </el-table-column>
        <el-table-column label="交易币" width="110">
          <template #default="{ row }"><b class="cell-coin">{{ row.amount_bin }}</b></template>
        </el-table-column>
        <el-table-column label="金额(元)" width="110">
          <template #default="{ row }">¥{{ (row.amount_cents / 100).toFixed(2) }}</template>
        </el-table-column>
        <el-table-column label="收款账号" min-width="170">
          <template #default="{ row }">{{ row.payee }}</template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="statusMap[row.status]?.type || 'info'">{{ statusMap[row.status]?.text || row.status }}</el-tag>
            <div v-if="row.status === 'rejected' && row.reject_reason" class="cell-reason">{{ row.reject_reason }}</div>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ row.created_at }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <template v-if="row.status === 'pending'">
              <el-button size="small" type="success" @click="approve(row as Row)">打款</el-button>
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