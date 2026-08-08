<script setup lang="ts">
/**
 * 封号管理
 * - 列表展示封号记录（用户、原因、时长、状态）
 * - 支持手动封号（输入原因、选择时长、是否可申诉）
 * - 支持手动解封
 * - 筛选：状态（active/expired/revoked）、用户
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  adminListBanRecords,
  adminBanUser,
  adminUnbanUser,
  adminListUsers,
  type BanRecord,
  type AdminUser,
} from '../../api/admin'

const list = ref<BanRecord[]>([])
const loading = ref(false)
const total = ref(0)

const filter = reactive({
  status: '' as string,
  user_id: undefined as number | undefined,
  page: 1,
  page_size: 20,
})

const statusOptions = [
  { value: '', label: '全部状态' },
  { value: 'active', label: '封禁中' },
  { value: 'expired', label: '已到期' },
  { value: 'revoked', label: '已解封' },
]

const statusMeta: Record<string, { type: 'success' | 'warning' | 'danger' | 'info'; text: string }> = {
  active: { type: 'danger', text: '封禁中' },
  expired: { type: 'info', text: '已到期' },
  revoked: { type: 'success', text: '已解封' },
}

// ============ 手动封号对话框 ============
const banDialogVisible = ref(false)
const banForm = reactive({
  user_id: undefined as number | undefined,
  reason: '',
  duration_hours: 24,
  appealable: true,
})
const userOptions = ref<AdminUser[]>([])
const userSearchLoading = ref(false)
const submitting = ref(false)

const durationOptions = [
  { value: 1, label: '警告（不封号）' },
  { value: 24, label: '1 天' },
  { value: 168, label: '7 天' },
  { value: 720, label: '30 天' },
  { value: -1, label: '永久封禁' },
]

async function load() {
  loading.value = true
  try {
    const { data } = await adminListBanRecords({
      page: filter.page,
      page_size: filter.page_size,
      status: filter.status || undefined,
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

async function searchUsers(keyword: string) {
  if (!keyword.trim()) {
    userOptions.value = []
    return
  }
  userSearchLoading.value = true
  try {
    const { data } = await adminListUsers({ keyword, page: 1, page_size: 20 })
    userOptions.value = data.data.items || []
  } catch {
    userOptions.value = []
  } finally {
    userSearchLoading.value = false
  }
}

function onSearch() {
  filter.page = 1
  load()
}

function onReset() {
  filter.status = ''
  filter.user_id = undefined
  filter.page = 1
  load()
}

function onPageChange(p: number) {
  filter.page = p
  load()
}

function openBanDialog() {
  banForm.user_id = undefined
  banForm.reason = ''
  banForm.duration_hours = 24
  banForm.appealable = true
  userOptions.value = []
  banDialogVisible.value = true
}

async function submitBan() {
  if (!banForm.user_id) {
    ElMessage.warning('请选择要封号的用户')
    return
  }
  if (!banForm.reason.trim()) {
    ElMessage.warning('请填写封号原因')
    return
  }
  submitting.value = true
  try {
    await adminBanUser(banForm.user_id, {
      reason: banForm.reason.trim(),
      duration_hours: banForm.duration_hours,
      appealable: banForm.appealable,
    })
    ElMessage.success('已封号')
    banDialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function unban(row: BanRecord) {
  try {
    await ElMessageBox.confirm(
      `确认解封用户「${row.user_nickname || '#' + row.user_id}」？`,
      '解封用户',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await adminUnbanUser(row.user_id)
    ElMessage.success('已解封')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function fmtTime(t: string | null): string {
  if (!t) return ''
  return t.replace('T', ' ').slice(0, 19)
}

function fmtDuration(hours: number): string {
  if (hours === 0) return '警告'
  if (hours === -1 || hours === 0 && false) return '永久'
  if (hours < 24) return `${hours} 小时`
  return `${hours / 24} 天`
}

onMounted(() => load())
</script>

<template>
  <div v-loading="loading" class="admin-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">封号管理</h2>
        <p class="page-subtitle">共 {{ total }} 条封号记录 · 分级封号机制：1 次警告 → 2 次 24h → 3 次 7 天 → 4 次 30 天 → 5 次永久</p>
      </div>
      <div>
        <el-button type="primary" @click="openBanDialog">手动封号</el-button>
        <el-button :icon="'Refresh'" @click="load">刷新</el-button>
      </div>
    </div>

    <div class="filter-card">
      <el-select
        v-model="filter.status"
        placeholder="封号状态"
        clearable
        style="width: 160px"
        @change="onSearch"
      >
        <el-option v-for="opt in statusOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
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
        <el-table-column label="用户" min-width="160">
          <template #default="{ row }">
            <div class="user-cell">
              <div class="user-info">
                <div class="user-nickname">{{ row.user_nickname || '用户' + row.user_id }}</div>
                <div class="user-meta">#{{ row.user_id }} · {{ row.user_phone || '无手机号' }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="封号原因" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="reason-text">{{ row.reason }}</span>
          </template>
        </el-table-column>
        <el-table-column label="时长" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.duration_hours === -1 || row.duration_hours === 0 ? 'danger' : 'warning'">
              {{ fmtDuration(row.duration_hours) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusMeta[row.status]?.type || 'info'" size="small">
              {{ statusMeta[row.status]?.text || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="可申诉" width="80">
          <template #default="{ row }">
            <el-tag :type="row.appealable ? 'success' : 'info'" size="small">
              {{ row.appealable ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="封禁时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.banned_at) }}</template>
        </el-table-column>
        <el-table-column label="到期时间" width="160">
          <template #default="{ row }">
            <span v-if="row.duration_hours === -1" class="permanent">永久</span>
            <span v-else>{{ fmtTime(row.ban_until) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作人" width="120">
          <template #default="{ row }">
            {{ row.admin_name || '系统自动' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'active'"
              size="small"
              type="success"
              plain
              @click="unban(row as BanRecord)"
            >
              解封
            </el-button>
            <span v-else class="text-muted">—</span>
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

    <!-- 手动封号对话框 -->
    <el-dialog v-model="banDialogVisible" title="手动封号" width="480px">
      <el-form :model="banForm" label-width="90px">
        <el-form-item label="选择用户" required>
          <el-select
            v-model="banForm.user_id"
            filterable
            remote
            reserve-keyword
            placeholder="输入昵称/手机号搜索"
            :remote-method="searchUsers"
            :loading="userSearchLoading"
            style="width: 100%"
          >
            <el-option
              v-for="u in userOptions"
              :key="u.id"
              :label="`${u.nickname} (#${u.id})`"
              :value="u.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="封号原因" required>
          <el-input
            v-model="banForm.reason"
            type="textarea"
            :rows="3"
            maxlength="200"
            show-word-limit
            placeholder="请填写封号原因，将通知用户"
          />
        </el-form-item>
        <el-form-item label="封号时长">
          <el-select v-model="banForm.duration_hours" style="width: 100%">
            <el-option
              v-for="opt in durationOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="允许申诉">
          <el-switch v-model="banForm.appealable" />
          <span class="form-tip">关闭后用户将无法对该封号记录发起申诉</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="banDialogVisible = false">取消</el-button>
        <el-button type="danger" :loading="submitting" @click="submitBan">确认封号</el-button>
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
.permanent {
  color: #ff3b30;
  font-weight: 600;
}
.text-muted {
  color: #bfbfbf;
}
.form-tip {
  margin-left: 8px;
  font-size: 12px;
  color: #8c8c8c;
}
.pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 0 0;
}
</style>
