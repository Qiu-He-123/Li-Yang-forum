<script setup lang="ts">
/**
 * 用户操作日志（大厂风格）
 * - 用户 ID + 操作类型过滤
 * - 分页列表
 * - 详情查看
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { adminListUserLogs, type AdminLog } from '../../api/admin'

const list = ref<AdminLog[]>([])
const loading = ref(false)
const total = ref(0)

const filter = reactive({
  user_id: undefined as number | undefined,
  action: '' as string,
  page: 1,
  page_size: 50,
})

// 常见用户操作类型
const actionOptions = [
  { value: '', label: '全部操作' },
  { value: 'login', label: '登录' },
  { value: 'logout', label: '登出' },
  { value: 'post_create', label: '发帖' },
  { value: 'post_delete', label: '删帖' },
  { value: 'comment_create', label: '评论' },
  { value: 'like', label: '点赞' },
  { value: 'favorite', label: '收藏' },
  { value: 'follow', label: '关注' },
  { value: 'report', label: '举报' },
  { value: 'profile_update', label: '资料更新' },
]

const detailDialogVisible = ref(false)
const detailRow = ref<AdminLog | null>(null)

async function load() {
  loading.value = true
  try {
    const { data } = await adminListUserLogs({
      page: filter.page,
      page_size: filter.page_size,
      user_id: filter.user_id || undefined,
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
  filter.user_id = undefined
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
  login: '登录',
  logout: '登出',
  post_create: '发帖',
  post_delete: '删帖',
  comment_create: '评论',
  like: '点赞',
  favorite: '收藏',
  follow: '关注',
  report: '举报',
  profile_update: '资料更新',
}

onMounted(() => load())
</script>

<template>
  <div v-loading="loading" class="admin-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">用户操作日志</h2>
        <p class="page-subtitle">共 {{ total }} 条记录</p>
      </div>
      <el-button :icon="'Refresh'" @click="load">刷新</el-button>
    </div>

    <div class="filter-card">
      <div>
        <label class="filter-label">用户 ID</label>
        <el-input-number v-model="filter.user_id" :min="1" :controls="false" placeholder="留空查全部" />
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
        <el-table-column prop="user_id" label="用户" width="100">
          <template #default="{ row }">
            <span class="user-id">#{{ row.user_id }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <el-tag size="small" :type="row.action === 'login' ? 'success' : 'info'">
              {{ actionLabels[row.action] || row.action }}
            </el-tag>
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
          <span class="detail-key">用户 ID：</span>
          <span class="detail-val">{{ detailRow.user_id }}</span>
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
.user-id {
  font-weight: 600;
  color: #52c41a;
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
