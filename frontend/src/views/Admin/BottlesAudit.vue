<script setup lang="ts">
/**
 * 漂流瓶审核
 * - 瓶子内容走 AI 审核；AI 不可用时转人工审核（不直接放行）
 * - 只有审核通过的瓶子才会进入拾取池
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  adminListBottles,
  adminReviewBottle,
  type AdminBottle,
} from '../../api/admin'

const list = ref<AdminBottle[]>([])
const loading = ref(false)
const total = ref(0)
const counts = ref({ pending: 0, approved: 0, rejected: 0, manual_review: 0 })

const filter = reactive({
  status: '' as '' | 'pending' | 'approved' | 'rejected' | 'manual_review',
  keyword: '',
  page: 1,
  page_size: 12,
})

const statusMeta: Record<string, { type: 'success' | 'warning' | 'danger' | 'info'; text: string }> = {
  pending: { type: 'warning', text: 'AI审核中' },
  approved: { type: 'success', text: '已通过' },
  rejected: { type: 'danger', text: '未通过' },
  manual_review: { type: 'info', text: '人工审核中' },
}

async function load() {
  loading.value = true
  try {
    const { data } = await adminListBottles({
      page: filter.page,
      page_size: filter.page_size,
      status: filter.status || undefined,
      keyword: filter.keyword || undefined,
    })
    list.value = data.data.items || []
    total.value = data.data.total || 0
    counts.value = data.data.counts || { pending: 0, approved: 0, rejected: 0, manual_review: 0 }
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

function onPageChange(p: number) {
  filter.page = p
  load()
}

async function review(row: AdminBottle, action: 'approve' | 'reject') {
  if (action === 'approve') {
    try {
      await ElMessageBox.confirm(
        `确认通过瓶子 #${row.id}？通过后将进入拾取池，等待其他用户拾取。`,
        '通过漂流瓶',
        { type: 'warning' },
      )
    } catch {
      return
    }
    try {
      await adminReviewBottle(row.id, { action: 'approve' })
      ElMessage.success('已通过')
      await load()
    } catch (error) {
      ElMessage.error((error as Error).message)
    }
    return
  }

  let reason = ''
  try {
    const { value } = await ElMessageBox.prompt(
      '请填写驳回原因（会通知作者）',
      '驳回漂流瓶',
      {
        confirmButtonText: '驳回',
        cancelButtonText: '取消',
        inputPlaceholder: '如：内容不适宜公开',
        inputValidator: (v: string) => (v && v.trim() ? true : '请填写驳回原因'),
      },
    )
    reason = value
  } catch {
    return
  }
  try {
    await adminReviewBottle(row.id, { action: 'reject', reject_reason: reason })
    ElMessage.success('已驳回并通知作者')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
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
        <h2 class="page-title">漂流瓶审核</h2>
        <p class="page-subtitle">
          瓶子内容走 AI 审核，AI 不可用时转人工审核；只有通过的瓶子进入拾取池
        </p>
      </div>
      <el-button :icon="'Refresh'" @click="load">刷新</el-button>
    </div>

    <!-- 状态统计 -->
    <div class="stat-cards">
      <div class="stat-card stat-card--pending">
        <span class="stat-num">{{ counts.pending }}</span>
        <span class="stat-label">AI审核中</span>
      </div>
      <div class="stat-card stat-card--manual">
        <span class="stat-num">{{ counts.manual_review }}</span>
        <span class="stat-label">人工审核中</span>
        <span class="stat-tip">AI 不可用时转入，需人工处理</span>
      </div>
      <div class="stat-card stat-card--approved">
        <span class="stat-num">{{ counts.approved }}</span>
        <span class="stat-label">已通过</span>
      </div>
      <div class="stat-card stat-card--rejected">
        <span class="stat-num">{{ counts.rejected }}</span>
        <span class="stat-label">未通过</span>
      </div>
    </div>

    <div class="filter-card">
      <el-select v-model="filter.status" placeholder="审核状态" clearable style="width: 160px" @change="onSearch">
        <el-option label="AI审核中" value="pending" />
        <el-option label="人工审核中" value="manual_review" />
        <el-option label="已通过" value="approved" />
        <el-option label="未通过" value="rejected" />
      </el-select>
      <el-input
        v-model="filter.keyword"
        placeholder="搜索瓶子内容"
        clearable
        style="width: 240px"
        @keyup.enter="onSearch"
      />
      <el-button type="primary" @click="onSearch">查询</el-button>
    </div>

    <div v-if="list.length" class="bottle-list">
      <div v-for="row in list" :key="row.id" class="bottle-card">
        <div class="bottle-head">
          <div class="bottle-author">
            <span class="bottle-id">#{{ row.id }}</span>
            <span>{{ row.author_nickname || '用户#' + row.author_id }}</span>
            <span>{{ row.school_name || '未知校区' }}</span>
            <span v-if="row.author_age != null">{{ row.author_age }} 岁</span>
          </div>
          <el-tag :type="statusMeta[row.audit_status]?.type || 'info'" size="small">
            {{ statusMeta[row.audit_status]?.text || row.audit_status }}
          </el-tag>
        </div>
        <p v-if="row.content" class="bottle-content">{{ row.content }}</p>
        <div v-if="row.image_urls?.length" class="bottle-images">
          <img
            v-for="(url, i) in row.image_urls"
            :key="i"
            :src="url"
            alt="瓶子图片"
            loading="lazy"
          />
        </div>
        <p v-if="row.reject_reason" class="bottle-reject">未通过原因：{{ row.reject_reason }}</p>
        <div class="bottle-foot">
          <span class="bottle-time">{{ fmtTime(row.created_at) }}</span>
          <div class="bottle-actions">
            <el-button
              v-if="row.audit_status !== 'approved'"
              size="small"
              type="success"
              @click="review(row, 'approve')"
            >通过</el-button>
            <el-button
              v-if="row.audit_status !== 'rejected'"
              size="small"
              type="danger"
              plain
              @click="review(row, 'reject')"
            >驳回</el-button>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="empty-tip">
      <p>暂无相关瓶子</p>
    </div>

    <div v-if="total > filter.page_size" class="pagination">
      <el-pagination
        v-model:current-page="filter.page"
        :page-size="filter.page_size"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="onPageChange"
      />
    </div>
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
  flex-wrap: wrap;
  gap: 12px;
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
.stat-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-bottom: 16px;
}
.stat-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 10px;
  padding: 14px 16px;
  border-left: 4px solid #d9d9d9;
}
.stat-card--pending {
  border-left-color: #f59e0b;
}
.stat-card--manual {
  border-left-color: #409eff;
}
.stat-card--approved {
  border-left-color: #67c23a;
}
.stat-card--rejected {
  border-left-color: #f56c6c;
}
.stat-num {
  font-size: 26px;
  font-weight: 800;
  color: #1f1f1f;
  line-height: 1.1;
}
.stat-label {
  font-size: 14px;
  font-weight: 600;
  color: #262626;
}
.stat-tip {
  font-size: 11px;
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
.bottle-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 14px;
}
.bottle-card {
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 10px;
  padding: 14px 16px;
  transition: box-shadow 0.15s;
}
.bottle-card:hover {
  box-shadow: 0 4px 16px rgba(0, 21, 41, 0.08);
}
.bottle-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.bottle-author {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
  color: #595959;
}
.bottle-id {
  font-weight: 700;
  color: #262626;
}
.bottle-content {
  margin: 0 0 8px;
  font-size: 13px;
  color: #262626;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.bottle-images {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.bottle-images img {
  width: 72px;
  height: 72px;
  border-radius: 8px;
  object-fit: cover;
}
.bottle-reject {
  margin: 0 0 8px;
  font-size: 12px;
  color: #dc2626;
  background: #fff5f4;
  border: 1px solid #ffd6d2;
  border-radius: 8px;
  padding: 6px 10px;
}
.bottle-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.bottle-time {
  font-size: 11px;
  color: #8c8c8c;
}
.bottle-actions {
  display: flex;
  gap: 6px;
}
.empty-tip {
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 10px;
  padding: 40px 0;
  text-align: center;
  color: #8c8c8c;
  font-size: 13px;
}
.empty-tip p {
  margin: 0;
}
.pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 0 0;
}

@media (max-width: 768px) {
  .stat-cards {
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .bottle-list {
    grid-template-columns: 1fr;
  }
}
</style>
