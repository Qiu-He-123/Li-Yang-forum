<script setup lang="ts">
/**
 * 举报处理（大厂风格）
 * - 状态过滤（待处理/已处理/已驳回）
 * - 分页列表
 * - 处理举报（已处理/驳回/重置）
 * - 查看帖子详情（点击「查看详情」按钮）
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { adminHandleReport, adminListReports, type AdminReport } from '../../api/admin'
import PostDetailDialog from '../../components/admin/PostDetailDialog.vue'

const list = ref<AdminReport[]>([])
const loading = ref(false)
const total = ref(0)

const filter = reactive({
  status: '' as string,
  page: 1,
  page_size: 20,
})

const statusOptions = [
  { value: '', label: '全部状态' },
  { value: 'pending', label: '待处理' },
  { value: 'resolved', label: '已处理' },
  { value: 'dismissed', label: '已驳回' },
]

const statusMeta: Record<string, { type: 'success' | 'warning' | 'info'; text: string }> = {
  pending: { type: 'warning', text: '待处理' },
  resolved: { type: 'success', text: '已处理' },
  dismissed: { type: 'info', text: '已驳回' },
  rejected: { type: 'info', text: '已驳回' },
}

const targetTypeMap: Record<string, string> = {
  post: '帖子',
  comment: '评论',
  user: '用户',
}

// 帖子详情弹窗
const detailVisible = ref(false)
const detailPostId = ref<number | null>(null)

async function load() {
  loading.value = true
  try {
    const { data } = await adminListReports({
      status: filter.status || undefined,
      page: filter.page,
      page_size: filter.page_size,
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

async function handle(row: AdminReport, status: string) {
  const label = statusMeta[status]?.text || status
  try {
    await ElMessageBox.confirm(`确认将举报 #${row.id} 标记为「${label}」？`, '处理举报', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await adminHandleReport(row.id, status)
    ElMessage.success('已处理')
    row.status = status
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function viewPostDetail(row: AdminReport) {
  if (row.target_type === 'post') {
    detailPostId.value = row.target_id
    detailVisible.value = true
  } else if (row.target_type === 'comment') {
    // 评论举报：跳转到该评论所属帖子的详情
    const comment = row.target as { post_id?: number } | null
    if (comment?.post_id) {
      detailPostId.value = comment.post_id
      detailVisible.value = true
    }
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
        <h2 class="page-title">举报处理</h2>
        <p class="page-subtitle">共 {{ total }} 条记录</p>
      </div>
      <el-button :icon="'Refresh'" @click="load">刷新</el-button>
    </div>

    <div class="filter-card">
      <el-select v-model="filter.status" placeholder="全部状态" style="width: 160px" @change="onSearch">
        <el-option v-for="opt in statusOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
      <el-button type="primary" @click="onSearch">查询</el-button>
      <el-button @click="onReset">重置</el-button>
    </div>

    <div class="table-card">
      <el-table :data="list" border stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" fixed />
        <el-table-column label="举报对象" width="160">
          <template #default="{ row }">
            <div class="target-cell">
              <span class="target-type">{{ targetTypeMap[row.target_type] || row.target_type }}</span>
              <span class="target-id">#{{ row.target_id }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="reporter_id" label="举报人" width="120">
          <template #default="{ row }">
            <span>{{ row.reporter_nickname || '#' + row.reporter_id }}</span>
          </template>
        </el-table-column>
        <el-table-column label="举报理由" min-width="240">
          <template #default="{ row }">
            <div class="reason-cell">{{ row.reason }}</div>
          </template>
        </el-table-column>
        <el-table-column label="内容预览" min-width="240">
          <template #default="{ row }">
            <div v-if="row.target" class="preview-cell">
              <div v-if="row.target_type === 'post'" class="preview-text">
                {{ row.target.content?.slice(0, 80) || '-' }}{{ (row.target.content?.length || 0) > 80 ? '…' : '' }}
              </div>
              <div v-else-if="row.target_type === 'comment'" class="preview-text">
                {{ row.target.content?.slice(0, 80) || '-' }}{{ (row.target.content?.length || 0) > 80 ? '…' : '' }}
              </div>
              <div v-else-if="row.target_type === 'user'" class="preview-text">
                {{ row.target.nickname || '#' + row.target_id }}
              </div>
            </div>
            <div v-else class="preview-text empty">内容已删除</div>
          </template>
        </el-table-column>
        <el-table-column label="AI 摘要" min-width="180">
          <template #default="{ row }">
            <div class="ai-cell">{{ row.ai_summary || '-' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusMeta[row.status]?.type || 'info'" size="small">
              {{ statusMeta[row.status]?.text || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="举报时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.target_type === 'post' || row.target_type === 'comment'"
              size="small"
              type="primary"
              plain
              @click="viewPostDetail(row)"
            >
              查看详情
            </el-button>
            <el-button
              v-if="row.status !== 'resolved'"
              size="small"
              type="success"
              @click="handle(row, 'resolved')"
            >
              标记已处理
            </el-button>
            <el-button
              v-if="row.status !== 'dismissed'"
              size="small"
              type="info"
              @click="handle(row, 'dismissed')"
            >
              驳回
            </el-button>
            <el-button
              v-if="row.status !== 'pending'"
              size="small"
              type="warning"
              plain
              @click="handle(row, 'pending')"
            >
              重置
            </el-button>
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
.target-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}
.target-type {
  font-size: 12px;
  color: #1890ff;
  font-weight: 600;
}
.target-id {
  font-size: 12px;
  color: #8c8c8c;
}
.reason-cell,
.ai-cell {
  font-size: 13px;
  color: #262626;
  line-height: 1.5;
  white-space: normal;
  word-break: break-all;
}
.ai-cell {
  color: #8c8c8c;
}
.preview-cell {
  font-size: 13px;
  color: #262626;
  line-height: 1.5;
}
.preview-text {
  white-space: normal;
  word-break: break-all;
}
.preview-text.empty {
  color: #bfbfbf;
  font-style: italic;
}
.pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 0 0;
}
</style>
