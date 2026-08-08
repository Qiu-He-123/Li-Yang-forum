<script setup lang="ts">
/**
 * AI 审核日志
 * - 列表展示每次 AI 审核的完整信息（目标、用户、AI 提供方、结果、原因、分类、严重程度）
 * - 筛选：目标类型（post/comment）、结果（approved/rejected/error）、用户 ID
 * - 支持查看内容快照
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  adminListAuditLogs,
  type AuditLog,
} from '../../api/admin'

const list = ref<AuditLog[]>([])
const loading = ref(false)
const total = ref(0)

const filter = reactive({
  target_type: '' as string,
  result: '' as string,
  user_id: undefined as number | undefined,
  page: 1,
  page_size: 20,
})

const targetTypeOptions = [
  { value: '', label: '全部类型' },
  { value: 'post', label: '帖子' },
  { value: 'comment', label: '评论' },
]

const resultOptions = [
  { value: '', label: '全部结果' },
  { value: 'approved', label: '通过' },
  { value: 'rejected', label: '违规' },
  { value: 'error', label: '异常' },
]

const resultMeta: Record<string, { type: 'success' | 'warning' | 'danger' | 'info'; text: string }> = {
  approved: { type: 'success', text: '通过' },
  rejected: { type: 'danger', text: '违规' },
  error: { type: 'warning', text: '异常' },
}

const providerMeta: Record<string, { type: 'success' | 'warning' | 'danger' | 'info'; text: string }> = {
  deepseek: { type: 'success', text: 'DeepSeek' },
  openai: { type: 'primary' as never, text: 'OpenAI' },
  none: { type: 'info', text: '无' },
}

const severityMeta: Record<string, string> = {
  high: '高危',
  medium: '中等',
  low: '轻微',
  none: '—',
}

const categoryMeta: Record<string, string> = {
  politics: '政治敏感',
  porn: '色情低俗',
  abuse: '辱骂攻击',
  ad: '广告引流',
  spam: '垃圾信息',
  none: '—',
}

// 内容快照弹窗
const snapshotVisible = ref(false)
const snapshotContent = ref('')

async function load() {
  loading.value = true
  try {
    const { data } = await adminListAuditLogs({
      page: filter.page,
      page_size: filter.page_size,
      target_type: filter.target_type || undefined,
      result: filter.result || undefined,
      user_id: filter.user_id || undefined,
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
  filter.target_type = ''
  filter.result = ''
  filter.user_id = undefined
  filter.page = 1
  load()
}

function onPageChange(p: number) {
  filter.page = p
  load()
}

function viewSnapshot(row: AuditLog) {
  snapshotContent.value = row.content_snapshot || '（无内容快照）'
  snapshotVisible.value = true
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
        <h2 class="page-title">AI 审核日志</h2>
        <p class="page-subtitle">共 {{ total }} 条审核记录 · 记录每次 AI 审核的完整信息</p>
      </div>
      <el-button :icon="'Refresh'" @click="load">刷新</el-button>
    </div>

    <div class="filter-card">
      <el-select
        v-model="filter.target_type"
        placeholder="目标类型"
        clearable
        style="width: 140px"
        @change="onSearch"
      >
        <el-option v-for="opt in targetTypeOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
      <el-select
        v-model="filter.result"
        placeholder="审核结果"
        clearable
        style="width: 140px"
        @change="onSearch"
      >
        <el-option v-for="opt in resultOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
      <el-input-number
        v-model="filter.user_id"
        :min="1"
        placeholder="用户 ID"
        controls-position="right"
        style="width: 140px"
      />
      <el-button type="primary" @click="onSearch">查询</el-button>
      <el-button @click="onReset">重置</el-button>
    </div>

    <div class="table-card">
      <el-table :data="list" border stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" fixed />
        <el-table-column label="目标" width="120">
          <template #default="{ row }">
            <div class="target-cell">
              <el-tag size="small" :type="row.target_type === 'post' ? 'primary' : 'success'">
                {{ row.target_type === 'post' ? '帖子' : '评论' }}
              </el-tag>
              <span class="target-id">#{{ row.target_id }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="用户" width="100">
          <template #default="{ row }">
            <span v-if="row.user_id">#{{ row.user_id }}</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="AI 提供方" width="110">
          <template #default="{ row }">
            <el-tag :type="providerMeta[row.ai_provider]?.type || 'info'" size="small">
              {{ providerMeta[row.ai_provider]?.text || row.ai_provider }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="结果" width="90">
          <template #default="{ row }">
            <el-tag :type="resultMeta[row.result]?.type || 'info'" size="small">
              {{ resultMeta[row.result]?.text || row.result }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="110">
          <template #default="{ row }">
            {{ categoryMeta[row.category] || row.category }}
          </template>
        </el-table-column>
        <el-table-column label="严重度" width="90">
          <template #default="{ row }">
            <span :class="'severity-' + row.severity">{{ severityMeta[row.severity] || row.severity }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原因" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.reason" class="reason-text">{{ row.reason }}</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="内容快照" width="100">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="viewSnapshot(row as AuditLog)">查看</el-button>
          </template>
        </el-table-column>
        <el-table-column label="审核时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
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

    <!-- 内容快照弹窗 -->
    <el-dialog v-model="snapshotVisible" title="审核内容快照" width="560px">
      <pre class="snapshot-content">{{ snapshotContent }}</pre>
      <template #footer>
        <el-button type="primary" @click="snapshotVisible = false">关闭</el-button>
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
.target-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}
.target-id {
  font-size: 12px;
  color: #8c8c8c;
  font-variant-numeric: tabular-nums;
}
.text-muted {
  color: #bfbfbf;
}
.reason-text {
  font-size: 13px;
  color: #595959;
  line-height: 1.5;
}
.severity-high {
  color: #ff3b30;
  font-weight: 600;
}
.severity-medium {
  color: #faad14;
  font-weight: 600;
}
.severity-low {
  color: #8c8c8c;
}
.severity-none {
  color: #bfbfbf;
}
.snapshot-content {
  margin: 0;
  padding: 12px 16px;
  background: #fafafa;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.6;
  color: #262626;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 400px;
  overflow-y: auto;
}
.pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 0 0;
}
</style>
