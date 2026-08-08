<script setup lang="ts">
/**
 * 反馈管理（管理员）
 * - 列表展示所有用户反馈（ID、用户、分类、标题、状态、创建时间）
 * - 状态过滤：全部 / 待处理 / 已回复 / 已关闭
 * - 查看详情（含回复列表），管理员可输入回复并提交
 * - 关闭反馈
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  closeFeedback,
  listAllFeedbacks,
  replyFeedback,
  type Feedback,
} from '../../api/feedback'

const list = ref<Feedback[]>([])
const loading = ref(false)
const total = ref(0)

const filter = reactive({
  status: '' as string,
  page: 1,
  page_size: 20,
})

const tabs = [
  { value: '', label: '全部' },
  { value: 'pending', label: '待处理' },
  { value: 'replied', label: '已回复' },
  { value: 'closed', label: '已关闭' },
]

const statusMeta: Record<string, { type: 'success' | 'warning' | 'info'; text: string }> = {
  pending: { type: 'warning', text: '待处理' },
  replied: { type: 'success', text: '已回复' },
  closed: { type: 'info', text: '已关闭' },
}

// 详情对话框
const detailVisible = ref(false)
const detailLoading = ref(false)
const current = ref<Feedback | null>(null)
const replyContent = ref('')
const submitting = ref(false)

async function load() {
  loading.value = true
  try {
    const { data } = await listAllFeedbacks(filter.page, filter.page_size, filter.status || undefined)
    list.value = data.data.items || []
    total.value = data.data.total || 0
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

function onTabChange(v: string) {
  filter.status = v
  filter.page = 1
  load()
}

function onPageChange(p: number) {
  filter.page = p
  load()
}

async function openDetail(row: Feedback) {
  current.value = row
  replyContent.value = ''
  detailVisible.value = true
  // 列表行已含 replies，无需再请求详情接口
  detailLoading.value = false
}

async function submitReply() {
  if (!current.value) return
  if (!replyContent.value.trim()) {
    ElMessage.warning('请填写回复内容')
    return
  }
  if (submitting.value) return
  submitting.value = true
  try {
    const { data } = await replyFeedback(current.value.id, replyContent.value.trim())
    // 本地更新
    current.value.replies = [...(current.value.replies || []), data.data]
    current.value.status = 'replied'
    // 同步列表
    const target = list.value.find((f) => f.id === current.value!.id)
    if (target) {
      target.replies = current.value.replies
      target.status = 'replied'
    }
    ElMessage.success('已回复')
    replyContent.value = ''
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function onClose(row: Feedback) {
  try {
    await ElMessageBox.confirm(`确认关闭反馈 #${row.id}？关闭后将不再接受回复。`, '关闭反馈', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await closeFeedback(row.id)
    row.status = 'closed'
    if (current.value && current.value.id === row.id) {
      current.value.status = 'closed'
    }
    ElMessage.success('已关闭')
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function fmtTime(t: string | null | undefined): string {
  if (!t) return ''
  return t.replace('T', ' ').slice(0, 19)
}

onMounted(() => load())
</script>

<template>
  <div v-loading="loading" class="admin-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">反馈管理</h2>
        <p class="page-subtitle">共 {{ total }} 条用户反馈 · 处理用户意见与问题</p>
      </div>
      <el-button :icon="'Refresh'" @click="load">刷新</el-button>
    </div>

    <!-- 状态过滤 Tab -->
    <div class="filter-card">
      <div class="status-tabs">
        <button
          v-for="t in tabs"
          :key="t.value"
          type="button"
          class="status-tab"
          :class="{ active: filter.status === t.value }"
          @click="onTabChange(t.value)"
        >
          {{ t.label }}
        </button>
      </div>
    </div>

    <div class="table-card">
      <el-table :data="list" border stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" fixed />
        <el-table-column label="用户" min-width="140">
          <template #default="{ row }">
            <div class="user-cell">
              <div class="user-info">
                <div class="user-nickname">{{ row.user_name || '用户' + row.user_id }}</div>
                <div class="user-meta">#{{ row.user_id }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="90">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.category || '其他' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="标题" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="reason-text">{{ row.title }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusMeta[row.status]?.type || 'info'" size="small">
              {{ statusMeta[row.status]?.text || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="回复数" width="80" align="center">
          <template #default="{ row }">
            {{ row.replies?.length || 0 }}
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" plain @click="openDetail(row as Feedback)">查看 / 回复</el-button>
            <el-button
              v-if="row.status !== 'closed'"
              size="small"
              type="danger"
              plain
              @click="onClose(row as Feedback)"
            >
              关闭
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

    <!-- 详情对话框 -->
    <el-dialog v-model="detailVisible" title="反馈详情" width="600px" v-loading="detailLoading">
      <div v-if="current" class="detail-wrap">
        <div class="detail-head">
          <div class="detail-row">
            <span class="detail-label">用户：</span>
            <span>{{ current.user_name || '用户' + current.user_id }} (#{{ current.user_id }})</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">分类：</span>
            <span>{{ current.category || '其他' }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">状态：</span>
            <el-tag :type="statusMeta[current.status]?.type || 'info'" size="small">
              {{ statusMeta[current.status]?.text || current.status }}
            </el-tag>
          </div>
          <div class="detail-row">
            <span class="detail-label">提交时间：</span>
            <span>{{ fmtTime(current.created_at) }}</span>
          </div>
          <div v-if="current.contact" class="detail-row">
            <span class="detail-label">联系方式：</span>
            <span>{{ current.contact }}</span>
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-section-title">标题</div>
          <div class="detail-section-body">{{ current.title }}</div>
        </div>

        <div class="detail-section">
          <div class="detail-section-title">内容</div>
          <div class="detail-section-body content-text">{{ current.content }}</div>
        </div>

        <!-- 已有回复 -->
        <div v-if="current.replies?.length" class="detail-section">
          <div class="detail-section-title">回复记录（{{ current.replies.length }}）</div>
          <div class="reply-list">
            <div v-for="r in current.replies" :key="r.id" class="reply-item">
              <div class="reply-head">
                <span class="reply-name">{{ r.replier_name || '管理员' }}</span>
                <span class="reply-time">{{ fmtTime(r.created_at) }}</span>
              </div>
              <p class="reply-content">{{ r.content }}</p>
            </div>
          </div>
        </div>

        <!-- 回复输入 -->
        <div v-if="current.status !== 'closed'" class="detail-section">
          <div class="detail-section-title">新增回复</div>
          <el-input
            v-model="replyContent"
            type="textarea"
            :rows="4"
            maxlength="1000"
            show-word-limit
            placeholder="请输入回复内容，提交后将通知用户"
          />
          <div class="reply-actions">
            <el-button type="primary" :loading="submitting" @click="submitReply">提交回复</el-button>
            <el-button type="danger" plain @click="onClose(current)">关闭反馈</el-button>
          </div>
        </div>
        <div v-else class="closed-tip">该反馈已关闭，不再接受回复。</div>
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
  padding: 12px 16px;
  border-radius: 8px;
  border: 1px solid #f0f0f0;
  margin-bottom: 16px;
}
.status-tabs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.status-tab {
  padding: 6px 16px;
  border-radius: 999px;
  border: 1px solid #e5e5ea;
  background: #fff;
  color: #595959;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.status-tab:hover {
  border-color: #4096ff;
  color: #4096ff;
}
.status-tab.active {
  background: #4096ff;
  border-color: #4096ff;
  color: #fff;
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
.pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 0 0;
}

/* 详情对话框 */
.detail-wrap {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.detail-head {
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
  display: flex;
  align-items: center;
  gap: 4px;
}
.detail-label {
  color: #8c8c8c;
}
.detail-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.detail-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #595959;
}
.detail-section-body {
  font-size: 14px;
  color: #262626;
  line-height: 1.6;
  padding: 10px 12px;
  background: #fafafa;
  border-radius: 6px;
}
.content-text {
  white-space: pre-wrap;
  word-break: break-word;
}
.reply-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.reply-item {
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 10px 12px;
  background: #fff;
}
.reply-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}
.reply-name {
  font-size: 12px;
  font-weight: 600;
  color: #4096ff;
}
.reply-time {
  font-size: 11px;
  color: #bfbfbf;
}
.reply-content {
  margin: 0;
  font-size: 13px;
  color: #595959;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.reply-actions {
  margin-top: 8px;
  display: flex;
  gap: 8px;
}
.closed-tip {
  padding: 12px 16px;
  background: #fafafa;
  border-radius: 6px;
  font-size: 13px;
  color: #8c8c8c;
  text-align: center;
}
</style>
