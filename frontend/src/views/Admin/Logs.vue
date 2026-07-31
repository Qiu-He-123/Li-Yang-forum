<script setup lang="ts">
/**
 * 管理员操作日志（大厂风格）
 * - 管理员 ID + 操作类型过滤
 * - 分页列表
 * - 详情查看
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { adminListLogs, type AdminLog } from '../../api/admin'

const list = ref<AdminLog[]>([])
const loading = ref(false)
const total = ref(0)

const filter = reactive({
  admin_id: undefined as number | undefined,
  action: '' as string,
  page: 1,
  page_size: 50,
})

// 常见操作类型
const actionOptions = [
  { value: '', label: '全部操作' },
  { value: 'admin_login', label: '管理员登录' },
  { value: 'delete_post', label: '删除帖子' },
  { value: 'audit_post', label: '审核帖子' },
  { value: 'delete_comment', label: '删除评论' },
  { value: 'audit_comment', label: '审核评论' },
  { value: 'update_user', label: '更新用户' },
  { value: 'handle_report', label: '处理举报' },
  { value: 'create_announcement', label: '创建公告' },
  { value: 'update_announcement', label: '更新公告' },
  { value: 'delete_announcement', label: '删除公告' },
]

const detailDialogVisible = ref(false)
const detailRow = ref<AdminLog | null>(null)

async function load() {
  loading.value = true
  try {
    const { data } = await adminListLogs({
      page: filter.page,
      page_size: filter.page_size,
      admin_id: filter.admin_id || undefined,
      action: filter.action || undefined,
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
  filter.admin_id = undefined
  filter.action = ''
  filter.page = 1
  load()
}

function onPageChange(p: number) {
  filter.page = p
  load()
}

function showDetail(row: AdminLog) {
  detailRow.value = row
  detailDialogVisible.value = true
}

function fmtTime(t: string | null): string {
  if (!t) return ''
  return t.replace('T', ' ').slice(0, 19)
}

function fmtDetail(s: string | null | undefined): string {
  if (!s) return '-'
  try {
    return JSON.stringify(JSON.parse(s), null, 2)
  } catch {
    return s
  }
}

const actionLabels: Record<string, string> = {
  admin_login: '管理员登录',
  delete_post: '删除帖子',
  audit_post: '审核帖子',
  delete_comment: '删除评论',
  audit_comment: '审核评论',
  update_user: '更新用户',
  handle_report: '处理举报',
  create_announcement: '创建公告',
  update_announcement: '更新公告',
  delete_announcement: '删除公告',
}

onMounted(() => load())
</script>

<template>
  <div v-loading="loading" class="admin-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">管理员操作日志</h2>
        <p class="page-subtitle">共 {{ total }} 条记录</p>
      </div>
      <el-button :icon="'Refresh'" @click="load">刷新</el-button>
    </div>

    <div class="filter-card">
      <div>
        <label class="filter-label">管理员 ID</label>
        <el-input-number v-model="filter.admin_id" :min="1" :controls="false" placeholder="留空查全部" />
      </div>
      <div>
        <label class="filter-label">操作类型</label>
        <el-select v-model="filter.action" placeholder="全部操作" style="width: 200px" @change="onSearch">
          <el-option v-for="opt in actionOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
      </div>
      <div class="filter-actions">
        <el-button type="primary" @click="onSearch">查询</el-button>
        <el-button @click="onReset">重置</el-button>
      </div>
    </div>

    <div class="table-card">
      <el-table :data="list" border stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" fixed />
        <el-table-column prop="admin_id" label="管理员" width="100">
          <template #default="{ row }">
            <span class="admin-id">#{{ row.admin_id }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-tag size="small" type="warning">{{ actionLabels[row.action] || row.action }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="详情" min-width="280">
          <template #default="{ row }">
            <div class="detail-cell" @click="showDetail(row)">
              <span class="detail-text">{{ row.detail || '-' }}</span>
              <span v-if="row.detail" class="detail-link">查看</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="ip" label="IP" width="140" />
        <el-table-column label="时间" width="180">
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

    <!-- 详情对话框 -->
    <el-dialog v-model="detailDialogVisible" title="日志详情" width="600px">
      <div v-if="detailRow" class="detail-view">
        <div class="detail-row">
          <span class="detail-key">日志 ID：</span>
          <span class="detail-val">{{ detailRow.id }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-key">管理员 ID：</span>
          <span class="detail-val">{{ detailRow.admin_id }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-key">操作类型：</span>
          <span class="detail-val">{{ actionLabels[detailRow.action] || detailRow.action }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-key">IP 地址：</span>
          <span class="detail-val">{{ detailRow.ip || '-' }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-key">操作时间：</span>
          <span class="detail-val">{{ fmtTime(detailRow.created_at) }}</span>
        </div>
        <div class="detail-row detail-row--block">
          <span class="detail-key">操作详情：</span>
          <pre class="detail-pre">{{ fmtDetail(detailRow.detail) }}</pre>
        </div>
      </div>
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
  gap: 16px;
  flex-wrap: wrap;
  align-items: flex-end;
}
.filter-label {
  display: block;
  font-size: 12px;
  color: #8c8c8c;
  margin-bottom: 4px;
}
.filter-actions {
  display: flex;
  gap: 8px;
}
.table-card {
  background: #fff;
  padding: 16px;
  border-radius: 8px;
  border: 1px solid #f0f0f0;
}
.admin-id {
  font-weight: 600;
  color: #1890ff;
}
.detail-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}
.detail-text {
  flex: 1;
  font-size: 12px;
  color: #595959;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.detail-link {
  font-size: 12px;
  color: #1890ff;
  flex-shrink: 0;
}
.detail-link:hover {
  text-decoration: underline;
}
.pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 0 0;
}

/* 详情对话框 */
.detail-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.detail-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.detail-row--block {
  flex-direction: column;
  align-items: flex-start;
}
.detail-key {
  font-size: 13px;
  color: #8c8c8c;
  min-width: 80px;
}
.detail-val {
  font-size: 13px;
  color: #262626;
  font-weight: 500;
}
.detail-pre {
  background: #f5f5f5;
  padding: 12px;
  border-radius: 4px;
  font-size: 12px;
  color: #595959;
  margin: 4px 0 0;
  width: 100%;
  max-height: 240px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
