<script setup lang="ts">
/**
 * 吧审核管理（管理员后台）
 * 路由：/admin/circles-audit
 *
 * 功能：
 * - 表格展示待审核的吧申请列表
 * - 操作：通过 / 拒绝（拒绝时弹出输入原因的对话框）
 * - 操作完成后刷新列表
 * - 支持按状态过滤（待审核 / 已通过 / 已拒绝）
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { auditCircle, listPendingCircles } from '../../api/circleApply'
import type { CircleApply } from '../../types/api'

const list = ref<CircleApply[]>([])
const loading = ref(false)

// 状态过滤：默认 pending
const filterStatus = ref<'pending' | 'approved' | 'rejected'>('pending')

const statusOptions: { value: 'pending' | 'approved' | 'rejected'; label: string; type: 'warning' | 'success' | 'danger' }[] = [
  { value: 'pending', label: '待审核', type: 'warning' },
  { value: 'approved', label: '已通过', type: 'success' },
  { value: 'rejected', label: '已拒绝', type: 'danger' },
]

const statusMeta: Record<string, { type: 'warning' | 'success' | 'danger'; text: string }> = {
  pending: { type: 'warning', text: '待审核' },
  approved: { type: 'success', text: '已通过' },
  rejected: { type: 'danger', text: '已拒绝' },
}

// 拒绝原因对话框
const rejectDialogVisible = ref(false)
const rejectReason = ref('')
const rejectingItem = ref<CircleApply | null>(null)
const operating = ref(false)

// 统计
const stats = computed(() => ({
  pending: list.value.filter((a) => a.status === 'pending').length,
  total: list.value.length,
}))

function fmtTime(t: string | null): string {
  if (!t) return ''
  return t.replace('T', ' ').slice(0, 19)
}

function fmtDesc(s: string | null): string {
  if (!s) return '-'
  return s.length > 60 ? s.slice(0, 60) + '…' : s
}

async function load() {
  loading.value = true
  try {
    const { data } = await listPendingCircles(filterStatus.value)
    list.value = data.data || []
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

function onStatusChange() {
  load()
}

async function onApprove(row: CircleApply) {
  try {
    await ElMessageBox.confirm(
      `确认通过「${row.name}」的吧申请？通过后将自动创建该圈子。`,
      '审核通过',
      { type: 'success', confirmButtonText: '确认通过', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  operating.value = true
  try {
    await auditCircle(row.id, true)
    ElMessage.success('已通过审核')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    operating.value = false
  }
}

function openRejectDialog(row: CircleApply) {
  rejectingItem.value = row
  rejectReason.value = ''
  rejectDialogVisible.value = true
}

async function onConfirmReject() {
  if (!rejectingItem.value) return
  const reason = rejectReason.value.trim()
  if (!reason) {
    ElMessage.warning('请输入拒绝原因')
    return
  }
  operating.value = true
  try {
    await auditCircle(rejectingItem.value.id, false, reason)
    ElMessage.success('已拒绝申请')
    rejectDialogVisible.value = false
    rejectingItem.value = null
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    operating.value = false
  }
}

onMounted(() => load())
</script>

<template>
  <div v-loading="loading" class="admin-page">
    <!-- 页头 -->
    <div class="page-header">
      <div>
        <h2 class="page-title">吧审核管理</h2>
        <p class="page-subtitle">
          审核用户申请创建的圈子
          <span class="stat-tip">· 当前列表 {{ stats.total }} 条</span>
        </p>
      </div>
      <el-button :icon="'Refresh'" @click="load">刷新</el-button>
    </div>

    <!-- 状态筛选 -->
    <div class="filter-card">
      <span class="filter-label">状态：</span>
      <el-radio-group v-model="filterStatus" @change="onStatusChange">
        <el-radio-button
          v-for="opt in statusOptions"
          :key="opt.value"
          :value="opt.value"
          :label="opt.label"
        />
      </el-radio-group>
    </div>

    <!-- 列表 -->
    <div class="table-card">
      <el-table :data="list" border stripe style="width: 100%" empty-text="暂无待审核的吧申请">
        <el-table-column prop="id" label="ID" width="70" fixed />
        <el-table-column label="吧名称" min-width="160">
          <template #default="{ row }">
            <div class="name-cell">
              <span
                class="name-ic"
                :style="{ background: row.color || '#007aff' }"
                aria-hidden="true"
              >
                {{ (row.name || 'C').charAt(0) }}
              </span>
              <div class="name-body">
                <div class="name-text">{{ row.name }}</div>
                <div class="name-slug">/{{ row.slug }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="slug" label="标识" width="140" />
        <el-table-column label="简介" min-width="220">
          <template #default="{ row }">
            <span class="desc-text">{{ fmtDesc(row.description) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="申请人" width="130">
          <template #default="{ row }">
            <div class="creator-cell">
              <span v-if="row.creator_nickname" class="creator-name">{{ row.creator_nickname }}</span>
              <span v-else class="creator-id">#{{ row.creator_id ?? '-' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusMeta[row.status]?.type || 'info'" size="small">
              {{ statusMeta[row.status]?.text || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="申请时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column v-if="filterStatus === 'rejected'" label="拒绝原因" min-width="180">
          <template #default="{ row }">
            <span class="reject-reason-text">{{ row.reject_reason || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <template v-if="row.status === 'pending'">
              <el-button size="small" type="success" :disabled="operating" @click="onApprove(row)">
                通过
              </el-button>
              <el-button size="small" type="danger" plain :disabled="operating" @click="openRejectDialog(row)">
                拒绝
              </el-button>
            </template>
            <span v-else class="op-done">已处理</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 拒绝原因对话框 -->
    <el-dialog
      v-model="rejectDialogVisible"
      title="拒绝原因"
      width="460px"
      :close-on-click-modal="false"
    >
      <div class="reject-dialog-body">
        <p v-if="rejectingItem" class="reject-target">
          正在拒绝「<strong>{{ rejectingItem.name }}</strong>」(/{{ rejectingItem.slug }})
        </p>
        <el-input
          v-model="rejectReason"
          type="textarea"
          :rows="4"
          maxlength="200"
          show-word-limit
          placeholder="请输入拒绝原因（最多 200 字），将展示给申请人"
        />
      </div>
      <template #footer>
        <el-button @click="rejectDialogVisible = false">取消</el-button>
        <el-button type="danger" :loading="operating" @click="onConfirmReject">
          确认拒绝
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.admin-page {
  min-height: 100%;
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}
.page-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: #1f1f1f;
}
.page-subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: #8c8c8c;
}
.stat-tip {
  color: #1890ff;
  margin-left: 4px;
}
.filter-card {
  background: #fff;
  padding: 14px 20px;
  border-radius: 8px;
  border: 1px solid #f0f0f0;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.filter-label {
  font-size: 13px;
  color: #595959;
  font-weight: 500;
}
.table-card {
  background: #fff;
  padding: 16px;
  border-radius: 8px;
  border: 1px solid #f0f0f0;
}

/* 吧名称单元格 */
.name-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}
.name-ic {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  flex-shrink: 0;
}
.name-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.name-text {
  font-size: 13px;
  font-weight: 600;
  color: #262626;
  line-height: 1.2;
}
.name-slug {
  font-size: 11px;
  color: #8c8c8c;
}

.desc-text {
  font-size: 12px;
  color: #595959;
  line-height: 1.5;
}

.creator-cell {
  display: flex;
  align-items: center;
}
.creator-name {
  font-size: 13px;
  color: #262626;
  font-weight: 500;
}
.creator-id {
  font-size: 12px;
  color: #8c8c8c;
  font-family: monospace;
}

.reject-reason-text {
  font-size: 12px;
  color: #ff4d4f;
  line-height: 1.5;
}

.op-done {
  font-size: 12px;
  color: #8c8c8c;
}

/* 拒绝对话框 */
.reject-dialog-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.reject-target {
  margin: 0;
  padding: 10px 12px;
  background: #fff7f7;
  border-radius: 6px;
  font-size: 13px;
  color: #595959;
}
.reject-target strong {
  color: #262626;
}
</style>
