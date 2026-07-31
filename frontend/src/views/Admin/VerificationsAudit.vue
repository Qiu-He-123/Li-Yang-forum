<script setup lang="ts">
/**
 * 学生认证审核
 * - 列表展示用户提交的学生证 / 校园卡照片审核申请
 * - 支持审核：通过（自动发放邀请码）/ 驳回（填写驳回原因）
 * - 筛选：状态（pending/approved/rejected）
 * - 防护：通过后系统自动发放邀请码并标记用户为已认证
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  adminListVerifications,
  adminReviewVerification,
  type VerificationApplication,
} from '../../api/verification'

const list = ref<VerificationApplication[]>([])
const loading = ref(false)
const total = ref(0)

const filter = reactive({
  status: '' as '' | 'pending' | 'approved' | 'rejected',
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
const reviewing = ref<VerificationApplication | null>(null)
const reviewForm = reactive({
  action: 'approve' as 'approve' | 'reject',
  reject_reason: '',
})
const submitting = ref(false)

async function load() {
  loading.value = true
  try {
    const { data } = await adminListVerifications({
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

function openReview(row: VerificationApplication) {
  reviewing.value = row
  reviewForm.action = 'approve'
  reviewForm.reject_reason = ''
  reviewDialogVisible.value = true
}

async function submitReview() {
  if (!reviewing.value) return
  if (reviewForm.action === 'reject' && !reviewForm.reject_reason.trim()) {
    ElMessage.warning('驳回时必须填写原因')
    return
  }
  const label = reviewForm.action === 'approve' ? '通过（自动发放邀请码）' : '驳回'
  try {
    await ElMessageBox.confirm(
      `确认将申请 #${reviewing.value.id}（用户 ${reviewing.value.user_nickname || reviewing.value.user_id}）标记为「${label}」？`,
      '审核学生认证',
      { type: 'warning' },
    )
  } catch {
    return
  }
  submitting.value = true
  try {
    const { data } = await adminReviewVerification(reviewing.value.id, {
      action: reviewForm.action,
      reject_reason: reviewForm.action === 'reject' ? reviewForm.reject_reason.trim() : undefined,
    })
    const granted = data.data.granted_invite_code
    if (reviewForm.action === 'approve' && granted) {
      ElMessage.success(`已通过审核，系统已自动发放邀请码：${granted}`)
    } else if (reviewForm.action === 'approve') {
      ElMessage.success('已通过审核')
    } else {
      ElMessage.success('已驳回申请')
    }
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
        <h2 class="page-title">学生认证审核</h2>
        <p class="page-subtitle">共 {{ total }} 条申请 · 通过后自动发放邀请码</p>
      </div>
      <el-button :icon="'Refresh'" @click="load">刷新</el-button>
    </div>

    <div class="filter-card">
      <el-select
        v-model="filter.status"
        placeholder="审核状态"
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
        <el-table-column label="证件照片" width="120">
          <template #default="{ row }">
            <el-image
              v-if="row.image_url"
              :src="row.image_url"
              :preview-src-list="[row.image_url]"
              fit="cover"
              class="verify-thumb"
              :preview-teleported="true"
            />
            <span v-else class="text-muted">无</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.note" class="reason-text">{{ row.note }}</span>
            <span v-else class="text-muted">—</span>
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
            {{ row.reviewer_username || '—' }}
          </template>
        </el-table-column>
        <el-table-column label="驳回原因" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.reject_reason" class="reject-reason">{{ row.reject_reason }}</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="发放邀请码" width="140">
          <template #default="{ row }">
            <el-tag v-if="row.granted_invite_code" type="success" size="small" class="code-tag">
              {{ row.granted_invite_code }}
            </el-tag>
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
              @click="openReview(row)"
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
    <el-dialog v-model="reviewDialogVisible" title="审核学生认证" width="560px">
      <div v-if="reviewing" class="review-detail">
        <div class="detail-row">
          <span class="detail-label">用户：</span>
          <span>{{ reviewing.user_nickname }} (#{{ reviewing.user_id }})</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">提交时间：</span>
          <span>{{ fmtTime(reviewing.created_at) }}</span>
        </div>
        <div v-if="reviewing.note" class="detail-row">
          <span class="detail-label">用户备注：</span>
          <span>{{ reviewing.note }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">证件照片：</span>
        </div>
        <div class="image-preview-wrap">
          <el-image
            :src="reviewing.image_url"
            :preview-src-list="[reviewing.image_url]"
            fit="contain"
            class="verify-image"
            :preview-teleported="true"
          />
        </div>
      </div>
      <el-form :model="reviewForm" label-width="90px" style="margin-top: 16px">
        <el-form-item label="审核结果">
          <el-radio-group v-model="reviewForm.action">
            <el-radio value="approve">通过（自动发放邀请码并解锁）</el-radio>
            <el-radio value="reject">驳回</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="reviewForm.action === 'reject'" label="驳回原因" required>
          <el-input
            v-model="reviewForm.reject_reason"
            type="textarea"
            :rows="3"
            maxlength="300"
            show-word-limit
            placeholder="请填写驳回原因，将通知用户"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reviewDialogVisible = false">取消</el-button>
        <el-button
          :type="reviewForm.action === 'approve' ? 'success' : 'danger'"
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
.reject-reason {
  font-size: 13px;
  color: #ff4d4f;
  line-height: 1.5;
}
.text-muted {
  color: #bfbfbf;
}
.code-tag {
  font-family: 'Courier New', monospace;
  font-weight: 600;
  letter-spacing: 0.5px;
}
.verify-thumb {
  width: 60px;
  height: 60px;
  border-radius: 4px;
  cursor: pointer;
  border: 1px solid #f0f0f0;
}
.pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 0 0;
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
.image-preview-wrap {
  display: flex;
  justify-content: center;
  padding: 8px;
  background: #fff;
  border-radius: 6px;
  border: 1px solid #f0f0f0;
}
.verify-image {
  max-width: 100%;
  max-height: 320px;
  border-radius: 4px;
}
</style>
