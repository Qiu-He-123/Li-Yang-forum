<script setup lang="ts">
/**
 * 帖子审核管理（专门处理 AI 审核失败 / 待人工复审的帖子）
 *
 * 与「帖子管理」的区别：
 * - 默认只展示 ai_status=rejected 或 manual_review 的帖子
 * - 支持「重新 AI 审核」一键调用 DeepSeek 复审
 * - 支持查看帖子完整详情
 * - 顶部显示「自动删除天数」配置入口
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  adminAuditPost,
  adminDeletePost,
  adminDeepSeekAuditPost,
  adminListPosts,
  type AdminPost,
} from '../../api/admin'
import PostDetailDialog from '../../components/admin/PostDetailDialog.vue'

const list = ref<AdminPost[]>([])
const loading = ref(false)
const total = ref(0)

const filter = reactive({
  ai_status: 'audit_failed' as string, // 默认只看审核失败的
  keyword: '',
  page: 1,
  page_size: 20,
})

// 自动删除天数（来自后端配置，仅用于展示）
const autoDeleteDays = ref(0)

const statusOptions = [
  { value: 'audit_failed', label: '全部失败/复审' },
  { value: 'rejected', label: '已驳回' },
  { value: 'manual_review', label: '人工复审' },
]

const statusMeta: Record<string, { type: 'success' | 'warning' | 'danger' | 'info'; text: string }> = {
  pending: { type: 'warning', text: '待审核' },
  approved: { type: 'success', text: '已通过' },
  rejected: { type: 'danger', text: '已驳回' },
  manual_review: { type: 'info', text: '人工复审' },
}

// 帖子详情弹窗
const detailVisible = ref(false)
const detailPostId = ref<number | null>(null)

async function load() {
  loading.value = true
  try {
    const { data } = await adminListPosts({
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
  filter.ai_status = 'audit_failed'
  filter.page = 1
  load()
}

function onPageChange(p: number) {
  filter.page = p
  load()
}

function viewDetail(row: AdminPost) {
  detailPostId.value = row.id
  detailVisible.value = true
}

async function audit(row: AdminPost, status: string) {
  const label = statusMeta[status]?.text || status
  try {
    await ElMessageBox.confirm(`确认将帖子 #${row.id} 审核状态改为「${label}」？`, '审核帖子', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await adminAuditPost(row.id, status)
    ElMessage.success('已更新审核状态')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function reAuditByAI(row: AdminPost) {
  try {
    await ElMessageBox.confirm(
      `确认调用 DeepSeek 重新审核帖子 #${row.id}？将根据 AI 结果自动更新审核状态。`,
      'AI 重新审核',
      { type: 'info' },
    )
  } catch {
    return
  }
  try {
    const { data } = await adminDeepSeekAuditPost(row.id)
    const result = data.data
    if (result.audit_result?.skipped) {
      ElMessage.warning('DeepSeek 未启用或调用失败，已跳过')
    } else if (result.audit_result?.pass) {
      ElMessage.success(`AI 审核通过：${result.audit_result?.reason || '无'}`)
    } else {
      ElMessage.error(`AI 审核拦截：${result.audit_result?.reason || '违规'}`)
    }
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function remove(row: AdminPost) {
  try {
    await ElMessageBox.confirm(`确认删除帖子 #${row.id}？此操作不可恢复。`, '删除帖子', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await adminDeletePost(row.id)
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
    <!-- 页头 -->
    <div class="page-header">
      <div>
        <h2 class="page-title">帖子审核管理</h2>
        <p class="page-subtitle">
          专注处理 AI 审核失败 / 待人工复审的帖子
          <span v-if="autoDeleteDays > 0" class="auto-delete-tip">
            · 自动删除：超过 {{ autoDeleteDays }} 天的失败内容
          </span>
        </p>
      </div>
      <el-button :icon="'Refresh'" @click="load">刷新</el-button>
    </div>

    <!-- 筛选区 -->
    <div class="filter-card">
      <el-input
        v-model="filter.keyword"
        placeholder="搜索帖子内容"
        clearable
        style="width: 260px"
        @keyup.enter="onSearch"
      />
      <el-select v-model="filter.ai_status" placeholder="审核状态" style="width: 180px" @change="onSearch">
        <el-option v-for="opt in statusOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
      <el-button type="primary" @click="onSearch">查询</el-button>
      <el-button @click="onReset">重置</el-button>
    </div>

    <!-- 列表 -->
    <div class="table-card">
      <el-table :data="list" border stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" fixed />
        <el-table-column label="内容（点击查看详情）" min-width="320">
          <template #default="{ row }">
            <div class="post-content-cell clickable" @click="viewDetail(row)">
              <div class="post-content-text">{{ fmtContent(row.content) }}</div>
              <div class="post-content-meta">
                <span class="meta-item">分类: {{ row.category || '-' }}</span>
                <span class="meta-item">作者: {{ row.author || '#' + row.author_id }}</span>
                <span v-if="row.is_anonymous" class="meta-item anon">匿名</span>
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
        <el-table-column label="互动" width="180">
          <template #default="{ row }">
            <div class="stat-cell">
              <span>👍 {{ row.like_count }}</span>
              <span>💬 {{ row.comment_count }}</span>
              <span>👀 {{ row.view_count }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="发布时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="380" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewDetail(row)">查看详情</el-button>
            <el-button size="small" type="primary" plain @click="reAuditByAI(row)">AI 复审</el-button>
            <el-button size="small" type="success" @click="audit(row, 'approved')">通过</el-button>
            <el-button size="small" type="warning" @click="audit(row, 'manual_review')">复审</el-button>
            <el-button size="small" type="danger" plain @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
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

    <!-- 帖子详情弹窗 -->
    <PostDetailDialog v-model="detailVisible" :post-id="detailPostId" />
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
.auto-delete-tip {
  color: #faad14;
  margin-left: 4px;
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
.post-content-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.post-content-cell.clickable {
  cursor: pointer;
}
.post-content-cell.clickable:hover .post-content-text {
  color: #1890ff;
}
.post-content-text {
  font-size: 13px;
  color: #262626;
  line-height: 1.5;
  transition: color 0.15s;
}
.post-content-meta {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: #8c8c8c;
}
.meta-item {
  white-space: nowrap;
}
.meta-item.anon {
  color: #faad14;
}
.stat-cell {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: #595959;
}
.pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 0 0;
}
</style>
