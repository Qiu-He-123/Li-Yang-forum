<script setup lang="ts">
/**
 * 申诉管理
 * - 列表展示用户申诉（用户、原因、关联封号记录、状态）
 * - 支持审核：通过（解封）/ 驳回（维持封号），需填写审核意见
 * - 筛选：状态（pending/approved/rejected）
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  adminListAppeals,
  adminReviewAppeal,
  type AdminAppeal,
} from '../../api/admin'

const list = ref<AdminAppeal[]>([])
const loading = ref(false)
const total = ref(0)

const filter = reactive({
  status: '' as string,
  page: 1,
  page_size: 20,
})

const statusOptions = [
  { value: '', label: '全部状态' },
  { value: 'pending', label: '待审核' },
  { value: 'approved', label: '已通过' },
  { value: 'rejected', label: '已驳回' },
]

const statusMeta: Record<string, { type: 'success' | 'warning' | 'danger' | 'info'; text: string }> = {
  pending: { type: 'warning', text: '待审核' },
  approved: { type: 'success', text: '已通过' },
  rejected: { type: 'danger', text: '已驳回' },
}

// 审核对话框
const reviewDialogVisible = ref(false)
const reviewing = ref<AdminAppeal | null>(null)
const reviewForm = reactive({
  status: 'approved' as 'approved' | 'rejected',
  review_comment: '',
})
const submitting = ref(false)

async function load() {
  loading.value = true
  try {
    const { data } = await adminListAppeals({
      page: filter.page,
      page_size: filter.page_size,
      status: filter.status || undefined,
    })
    list.value = data.data.items || []
    total.value = data.data.total || 0
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

function onSearch() {
  filter.page = 1
  load()
}

function onReset() {
  filter.status = ''
  filter.page = 1
  load()
}

function onPageChange(p: number) {
  filter.page = p
  load()
}

function openReview(row: AdminAppeal) {
  reviewing.value = row
  reviewForm.status = 'approved'
  reviewForm.review_comment = ''
  reviewDialogVisible.value = true
}

async function submitReview() {
  if (!reviewing.value) return
  if (!reviewForm.review_comment.trim()) {
    ElMessage.warning('请填写审核意见')
    return
  }
  const label = reviewForm.status === 'approved' ? '通过（解封用户）' : '驳回（维持封号）'
  try {
    await ElMessageBox.confirm(
      `确认将申诉 #${reviewing.value.id} 标记为「${label}」？`,
      '审核申诉',
      { type: 'warning' },
    )
  } catch {
    return
  }
  submitting.value = true
  try {
    await adminReviewAppeal(reviewing.value.id, {
      status: reviewForm.status,
      review_comment: reviewForm.review_comment.trim(),
    })
    ElMessage.success('已审核')
    reviewDialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

function fmtTime(t: string | null): string {
  if (!t) return ''
  return t.replace('T', ' ').slice(0, 19)
}

onMounted(() => load())
</script>

<template>
  <div v-loading="loading" class="admin-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">申诉管理</h2>
        <p class="page-subtitle">共 {{ total }} 条申诉 · 人工客服复查流程</p>
      </div>
      <el-button :icon="'Refresh'" @click="load">刷新</el-button>
    </div>

    <div class="filter-card">
      <el-select
        v-model="filter.status"
        placeholder="申诉状态"
        clearable
        style="width: 160px"
        @change="onSearch"
      >
        <el-option v-for="opt in statusOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
      <el-button type="primary" @click="onSearch">查询</el-button>
      <el-button @click="onReset">重置</el-button>
    </div>

    <div class="table-card">
      <el-table :data="list" border stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" fixed />
        <el-table-column label="用户" min-width="140">
          <template #default="{ row }">
            <div class="user-cell">
              <div class="user-info">
                <div class="user-nickname">{{ row.user_nickname || '用户' + row.user_id }}</div>
                <div class="user-meta">#{{ row.user_id }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="申诉原因" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="reason-text">{{ row.reason }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关联封号" width="110">
          <template #default="{ row }">
            <span v-if="row.ban_record_id">#{{ row.ban_record_id }}</span>
            <span v-else class="text-muted">无</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusMeta[row.status]?.type || 'info'" size="small">
              {{ statusMeta[row.status]?.text || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="审核人" width="120">
          <template #default="{ row }">
            {{ row.reviewer_name || '—' }}
          </template>
        </el-table-column>
        <el-table-column label="审核意见" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.review_comment" class="reason-text">{{ row.review_comment }}</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="提交时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="审核时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.reviewed_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'pending'"
              size="small"
              type="primary"
              @click="openReview(row as AdminAppeal)"
            >
              审核
            </el-button>
            <span v-else class="text-muted">已处理</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="filter.page"
          :page-size="filter.page_size"
          :total="total"
          layout="total, prev, pager, next, jumper"
          @current-change="onPageChange"
        />
      </div>
    </div>

    <!-- 审核对话框 -->
    <el-dialog v-model="reviewDialogVisible" title="审核申诉" width="480px">
      <div v-if="reviewing" class="review-detail">
        <div class="detail-row">
          <span class="detail-label">用户：</span>
          <span>{{ reviewing.user_nickname }} (#{{ reviewing.user_id }})</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">申诉原因：</span>
          <span>{{ reviewing.reason }}</span>
        </div>
        <div v-if="reviewing.ban_record_id" class="detail-row">
          <span class="detail-label">关联封号记录：</span>
          <span>#{{ reviewing.ban_record_id }}</span>
        </div>
      </div>
      <el-form :model="reviewForm" label-width="90px" style="margin-top: 16px">
        <el-form-item label="审核结果">
          <el-radio-group v-model="reviewForm.status">
            <el-radio value="approved">通过（解封用户）</el-radio>
            <el-radio value="rejected">驳回（维持封号）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="审核意见" required>
          <el-input
            v-model="reviewForm.review_comment"
            type="textarea"
            :rows="4"
            maxlength="500"
            show-word-limit
            placeholder="请填写审核意见，将通知用户"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reviewDialogVisible = false">取消</el-button>
        <el-button
          :type="reviewForm.status === 'approved' ? 'success' : 'danger'"
          :loading="submitting"
          @click="submitReview"
        >
          确认审核
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
.filter-card {
  background: #fff;
  padding: 16px 20px;
  border-radius: 8px;
  border: 1px solid #f0f0f0;
  margin-bottom: 16px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
}
.table-card {
  background: #fff;
  padding: 16px;
  border-radius: 8px;
  border: 1px solid #f0f0f0;
}
.user-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}
.user-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.user-nickname {
  font-size: 13px;
  font-weight: 600;
  color: #262626;
}
.user-meta {
  font-size: 11px;
  color: #8c8c8c;
}
.reason-text {
  font-size: 13px;
  color: #595959;
  line-height: 1.5;
}
.text-muted {
  color: #bfbfbf;
}
.review-detail {
  background: #fafafa;
  border-radius: 6px;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.detail-row {
  font-size: 13px;
  color: #262626;
  line-height: 1.6;
}
.detail-label {
  color: #8c8c8c;
  margin-right: 4px;
}
.pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 0 0;
}
</style>
