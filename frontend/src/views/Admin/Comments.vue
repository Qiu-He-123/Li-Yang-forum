<script setup lang="ts">
/**
 * 评论管理（大厂风格）
 * - 搜索 + AI 状态过滤
 * - 分页列表
 * - 审核 + 删除
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { adminAuditComment, adminDeleteComment, adminListComments, type AdminComment } from '../../api/admin'

const list = ref<AdminComment[]>([])
const loading = ref(false)
const total = ref(0)

const filter = reactive({
  keyword: '',
  ai_status: '' as string,
  page: 1,
  page_size: 20,
})

const statusOptions = [
  { value: '', label: '全部状态' },
  { value: 'pending', label: '待审核' },
  { value: 'approved', label: '已通过' },
  { value: 'rejected', label: '已驳回' },
  { value: 'manual_review', label: '人工复审' },
]

const statusMeta: Record<string, { type: 'success' | 'warning' | 'danger' | 'info'; text: string }> = {
  pending: { type: 'warning', text: '待审核' },
  approved: { type: 'success', text: '已通过' },
  rejected: { type: 'danger', text: '已驳回' },
  manual_review: { type: 'info', text: '人工复审' },
}

async function load() {
  loading.value = true
  try {
    const { data } = await adminListComments({
      page: filter.page,
      page_size: filter.page_size,
      keyword: filter.keyword || undefined,
      ai_status: filter.ai_status || undefined,
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
  filter.keyword = ''
  filter.ai_status = ''
  filter.page = 1
  load()
}

function onPageChange(p: number) {
  filter.page = p
  load()
}

async function audit(row: AdminComment, status: string) {
  const label = statusMeta[status]?.text || status
  try {
    await ElMessageBox.confirm(`确认将评论 #${row.id} 审核状态改为「${label}」？`, '审核评论', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await adminAuditComment(row.id, status)
    ElMessage.success('已更新审核状态')
    row.ai_status = status
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function remove(row: AdminComment) {
  try {
    await ElMessageBox.confirm(`确认删除评论 #${row.id}？此操作不可恢复。`, '删除评论', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await adminDeleteComment(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function fmtTime(t: string | null): string {
  if (!t) return ''
  return t.replace('T', ' ').slice(0, 19)
}

function fmtContent(s: string): string {
  return s.length > 80 ? s.slice(0, 80) + '…' : s
}

onMounted(() => load())
</script>

<template>
  <div v-loading="loading" class="admin-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">评论管理</h2>
        <p class="page-subtitle">共 {{ total }} 条记录</p>
      </div>
      <el-button :icon="'Refresh'" @click="load">刷新</el-button>
    </div>

    <div class="filter-card">
      <el-input
        v-model="filter.keyword"
        placeholder="搜索评论内容"
        clearable
        style="width: 260px"
        @keyup.enter="onSearch"
      />
      <el-select v-model="filter.ai_status" placeholder="全部状态" style="width: 160px" @change="onSearch">
        <el-option v-for="opt in statusOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
      <el-button type="primary" @click="onSearch">查询</el-button>
      <el-button @click="onReset">重置</el-button>
    </div>

    <div class="table-card">
      <el-table :data="list" border stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" fixed />
        <el-table-column prop="post_id" label="帖子 ID" width="100" />
        <el-table-column label="评论内容" min-width="320">
          <template #default="{ row }">
            <div class="comment-cell">
              <div class="comment-text">{{ fmtContent(row.content) }}</div>
              <div class="comment-meta">
                <span>作者: {{ row.author || '#' + row.user_id }}</span>
                <span>👍 {{ row.like_count }}</span>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="审核状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusMeta[row.ai_status]?.type || 'info'" size="small">
              {{ statusMeta[row.ai_status]?.text || row.ai_status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="发布时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="success" @click="audit(row, 'approved')">通过</el-button>
            <el-button size="small" type="danger" @click="audit(row, 'rejected')">驳回</el-button>
            <el-button size="small" type="warning" @click="audit(row, 'manual_review')">复审</el-button>
            <el-button size="small" type="danger" plain @click="remove(row)">删除</el-button>
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
.comment-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.comment-text {
  font-size: 13px;
  color: #262626;
  line-height: 1.5;
}
.comment-meta {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: #8c8c8c;
}
.pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 0 0;
}
</style>
