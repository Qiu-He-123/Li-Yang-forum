<script setup lang="ts">
/**
 * 图片人工审核（图片不走 AI 审核）
 * - 上传的图片默认进入待审核队列
 * - 通过：相关因「图片需人工审核」挂起的帖子自动放行
 * - 驳回：相关帖子标记未通过并通知作者
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  adminListImages,
  adminReviewImage,
  type AdminImage,
} from '../../api/admin'

const list = ref<AdminImage[]>([])
const loading = ref(false)
const total = ref(0)
const counts = ref({ pending: 0, approved: 0, rejected: 0 })

const filter = reactive({
  status: 'pending' as '' | 'pending' | 'approved' | 'rejected',
  keyword: '',
  page: 1,
  page_size: 12,
})

const statusMeta: Record<string, { type: 'success' | 'warning' | 'danger' | 'info'; text: string }> = {
  pending: { type: 'warning', text: '待审核' },
  approved: { type: 'success', text: '已通过' },
  rejected: { type: 'danger', text: '已驳回' },
}

async function load() {
  loading.value = true
  try {
    const { data } = await adminListImages({
      page: filter.page,
      page_size: filter.page_size,
      status: filter.status || undefined,
      keyword: filter.keyword || undefined,
    })
    list.value = data.data.items || []
    total.value = data.data.total || 0
    counts.value = data.data.counts || { pending: 0, approved: 0, rejected: 0 }
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

async function review(row: AdminImage, action: 'approve' | 'reject') {
  if (action === 'approve') {
    try {
      await ElMessageBox.confirm(
        `确认通过图片 #${row.id}？关联的 ${row.used_in_posts} 个帖子（挂起中）将自动放行。`,
        '通过图片审核',
        { type: 'warning' },
      )
    } catch {
      return
    }
    try {
      const { data } = await adminReviewImage(row.id, { action: 'approve' })
      ElMessage.success(`已通过，放行 ${data.data.related_posts.length} 个帖子`)
      await load()
    } catch (error) {
      ElMessage.error((error as Error).message)
    }
    return
  }

  let reason = ''
  try {
    const { value } = await ElMessageBox.prompt(
      '请填写驳回原因（会通知作者并展示在帖子上）',
      '驳回图片',
      {
        confirmButtonText: '驳回',
        cancelButtonText: '取消',
        inputPlaceholder: '如：图片包含不适宜内容',
        inputValidator: (v: string) => (v && v.trim() ? true : '请填写驳回原因'),
      },
    )
    reason = value
  } catch {
    return
  }
  try {
    await adminReviewImage(row.id, { action: 'reject', reject_reason: reason })
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

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

onMounted(() => load())
</script>

<template>
  <div v-loading="loading" class="admin-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">图片审核</h2>
        <p class="page-subtitle">
          图片不走 AI 审核，上传后默认进入人工审核队列；通过后关联帖子自动放行
        </p>
      </div>
      <el-button :icon="'Refresh'" @click="load">刷新</el-button>
    </div>

    <!-- 状态统计 -->
    <div class="stat-cards">
      <div class="stat-card stat-card--pending">
        <span class="stat-num">{{ counts.pending }}</span>
        <span class="stat-label">待审核</span>
        <span class="stat-tip">等待人工处理</span>
      </div>
      <div class="stat-card stat-card--approved">
        <span class="stat-num">{{ counts.approved }}</span>
        <span class="stat-label">已通过</span>
        <span class="stat-tip">可正常展示</span>
      </div>
      <div class="stat-card stat-card--rejected">
        <span class="stat-num">{{ counts.rejected }}</span>
        <span class="stat-label">已驳回</span>
        <span class="stat-tip">作者需更换图片</span>
      </div>
    </div>

    <div class="filter-card">
      <el-select v-model="filter.status" placeholder="审核状态" clearable style="width: 150px" @change="onSearch">
        <el-option label="待审核" value="pending" />
        <el-option label="已通过" value="approved" />
        <el-option label="已驳回" value="rejected" />
      </el-select>
      <el-input
        v-model="filter.keyword"
        placeholder="搜索图片 URL"
        clearable
        style="width: 240px"
        @keyup.enter="onSearch"
      />
      <el-button type="primary" @click="onSearch">查询</el-button>
    </div>

    <!-- 图片网格 -->
    <div v-if="list.length" class="image-grid">
      <div v-for="row in list" :key="row.id" class="image-card">
        <div class="image-preview">
          <img :src="row.url" :alt="`图片 #${row.id}`" loading="lazy" />
          <el-tag :type="statusMeta[row.audit_status]?.type || 'info'" size="small" class="image-status">
            {{ statusMeta[row.audit_status]?.text || row.audit_status }}
          </el-tag>
        </div>
        <div class="image-info">
          <div class="image-meta">
            <span>#{{ row.id }}</span>
            <span>{{ row.user_nickname || '用户#' + row.user_id }}</span>
            <span>{{ fmtSize(row.size_bytes) }}</span>
          </div>
          <div class="image-meta">
            <span>关联帖子 {{ row.used_in_posts }}</span>
            <span>{{ fmtTime(row.created_at) }}</span>
          </div>
          <div class="image-url" :title="row.url">{{ row.url }}</div>
        </div>
        <div class="image-actions">
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

    <div v-else class="empty-tip">
      <p>暂无{{ filter.status === 'approved' ? '已通过' : filter.status === 'rejected' ? '已驳回' : '待审核' }}图片</p>
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
  grid-template-columns: repeat(3, 1fr);
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
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 14px;
}
.image-card {
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 10px;
  overflow: hidden;
  transition: box-shadow 0.15s;
}
.image-card:hover {
  box-shadow: 0 4px 16px rgba(0, 21, 41, 0.08);
}
.image-preview {
  position: relative;
  aspect-ratio: 16 / 10;
  background: #fafafa;
}
.image-preview img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}
.image-status {
  position: absolute;
  top: 8px;
  left: 8px;
}
.image-info {
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.image-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #595959;
}
.image-url {
  font-size: 11px;
  color: #8c8c8c;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: 'Courier New', monospace;
}
.image-actions {
  display: flex;
  gap: 8px;
  padding: 0 12px 12px;
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
    grid-template-columns: 1fr;
    gap: 8px;
  }
  .stat-card {
    flex-direction: row;
    align-items: baseline;
    gap: 10px;
  }
  .stat-tip {
    margin-left: auto;
  }
  .image-grid {
    grid-template-columns: 1fr;
  }
}
</style>
