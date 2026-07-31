<script setup lang="ts">
/**
 * 警告值系统配置
 *
 * 功能：
 * - 配置警告值阈值（警告 / 临时封号 / 永久封号）
 * - 配置每次违规警告值增加值
 * - 配置积极行为减少值（签到 / 发帖 / 评论）
 * - 手动调整指定用户的警告值（增/减）
 * - 查看指定用户的警告值变动记录
 *
 * 警告值机制：
 * - warning_score < warn_threshold: 正常
 * - warning_score >= warn_threshold: 发警告通知
 * - warning_score >= temp_ban_threshold: 封号 temp_ban_hours 小时
 * - warning_score >= perm_ban_threshold: 永久封号
 * - 签到 / 发帖审核通过 / 评论审核通过 可减少警告值
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  adminAdjustUserWarning,
  adminGetWarningConfig,
  adminListUserWarningLogs,
  adminListUsers,
  adminUpdateWarningConfig,
  type AdminUser,
  type WarningConfig as WarningConfigType,
  type WarningLog,
} from '../../api/admin'

// ============ 配置 ============
const loading = ref(false)
const saving = ref(false)
const config = reactive<WarningConfigType>({
  warn_threshold: 30,
  temp_ban_threshold: 60,
  temp_ban_hours: 24,
  perm_ban_threshold: 100,
  violation_base_score: 20,
  checkin_reduce: 2,
  post_reduce: 1,
  comment_reduce: 1,
  updated_at: null,
})

const lastUpdatedAt = computed(() => {
  if (!config.updated_at) return ''
  return config.updated_at.replace('T', ' ').slice(0, 19)
})

async function loadConfig() {
  loading.value = true
  try {
    const { data } = await adminGetWarningConfig()
    Object.assign(config, data.data)
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

async function saveConfig() {
  // 校验阈值合理性
  if (
    !(
      0 <= config.warn_threshold &&
      config.warn_threshold <= config.temp_ban_threshold &&
      config.temp_ban_threshold <= config.perm_ban_threshold
    )
  ) {
    ElMessage.warning('阈值关系不合法，需满足 0 ≤ 警告阈值 ≤ 临时封号阈值 ≤ 永久封号阈值')
    return
  }
  if (config.temp_ban_hours <= 0) {
    ElMessage.warning('临时封号时长必须大于 0 小时')
    return
  }
  saving.value = true
  try {
    const { data } = await adminUpdateWarningConfig({
      warn_threshold: config.warn_threshold,
      temp_ban_threshold: config.temp_ban_threshold,
      temp_ban_hours: config.temp_ban_hours,
      perm_ban_threshold: config.perm_ban_threshold,
      violation_base_score: config.violation_base_score,
      checkin_reduce: config.checkin_reduce,
      post_reduce: config.post_reduce,
      comment_reduce: config.comment_reduce,
    })
    Object.assign(config, data.data)
    ElMessage.success('配置已保存')
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    saving.value = false
  }
}

function resetConfig() {
  loadConfig()
}

// ============ 手动调整用户警告值 ============
const adjustDialogVisible = ref(false)
const adjustForm = reactive({
  user_id: undefined as number | undefined,
  delta: 0,
  reason: '',
})
const userOptions = ref<AdminUser[]>([])
const userSearchLoading = ref(false)
const submitting = ref(false)
const adjustResult = ref<{ triggered_ban: boolean; new_score: number } | null>(null)

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

function openAdjustDialog() {
  adjustForm.user_id = undefined
  adjustForm.delta = 0
  adjustForm.reason = ''
  adjustResult.value = null
  userOptions.value = []
  adjustDialogVisible.value = true
}

async function submitAdjust() {
  if (!adjustForm.user_id) {
    ElMessage.warning('请选择要调整的用户')
    return
  }
  if (adjustForm.delta === 0) {
    ElMessage.warning('调整值不能为 0')
    return
  }
  if (!adjustForm.reason.trim()) {
    ElMessage.warning('请填写调整原因')
    return
  }
  submitting.value = true
  try {
    const { data } = await adminAdjustUserWarning(
      adjustForm.user_id,
      adjustForm.delta,
      adjustForm.reason.trim(),
    )
    adjustResult.value = data.data
    if (data.data.triggered_ban) {
      ElMessage.warning(`已触发封号机制，当前警告值 ${data.data.new_score}`)
    } else {
      ElMessage.success(`调整成功，当前警告值 ${data.data.new_score}`)
    }
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    submitting.value = false
  }
}

// ============ 用户警告值记录查看 ============
const logsDialogVisible = ref(false)
const logsForm = reactive({
  user_id: undefined as number | undefined,
})
const logsData = ref<WarningLog[]>([])
const logsTotal = ref(0)
const logsPage = ref(1)
const logsPageSize = ref(20)
const logsLoading = ref(false)

function openLogsDialog(row?: AdminUser) {
  logsForm.user_id = row?.id
  logsPage.value = 1
  logsData.value = []
  logsTotal.value = 0
  logsDialogVisible.value = true
  if (logsForm.user_id) {
    loadLogs()
  }
}

async function loadLogs() {
  if (!logsForm.user_id) {
    ElMessage.warning('请选择用户')
    return
  }
  logsLoading.value = true
  try {
    const { data } = await adminListUserWarningLogs(logsForm.user_id, {
      page: logsPage.value,
      page_size: logsPageSize.value,
    })
    logsData.value = data.data.items || []
    logsTotal.value = data.data.total || 0
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    logsLoading.value = false
  }
}

function onLogsPageChange(p: number) {
  logsPage.value = p
  loadLogs()
}

// ============ 工具方法 ============
const sourceMap: Record<string, { text: string; type: 'success' | 'warning' | 'danger' | 'info' | 'primary' }> = {
  violation: { text: '违规', type: 'danger' },
  checkin: { text: '签到', type: 'success' },
  post: { text: '发帖', type: 'success' },
  comment: { text: '评论', type: 'success' },
  admin_adjust: { text: '管理员调整', type: 'warning' },
  system: { text: '系统', type: 'info' },
}

function fmtTime(t: string | null): string {
  if (!t) return ''
  return t.replace('T', ' ').slice(0, 19)
}

function fmtDelta(delta: number): string {
  if (delta > 0) return `+${delta}`
  return `${delta}`
}

onMounted(() => loadConfig())
</script>

<template>
  <div v-loading="loading" class="admin-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">警告值系统配置</h2>
        <p class="page-subtitle">
          警告值机制：违规累加，签到/发帖/评论减少 · 达到阈值自动警告/封号
          <span v-if="lastUpdatedAt" class="updated-at">最近更新：{{ lastUpdatedAt }}</span>
        </p>
      </div>
      <div>
        <el-button type="primary" @click="openAdjustDialog">手动调整用户警告值</el-button>
        <el-button :icon="'Refresh'" @click="loadConfig">刷新</el-button>
      </div>
    </div>

    <!-- 配置说明卡片 -->
    <div class="info-card">
      <div class="info-card-title">
        <span class="info-ic">ⓘ</span>
        警告值机制说明
      </div>
      <ul class="info-list">
        <li>每次违规：警告值 += 违规增加值（根据 AI 判定 severity 在基础值上 ×0.5/1.0/1.5）</li>
        <li>达到 <b>警告阈值</b>：仅发警告通知，不封号</li>
        <li>达到 <b>临时封号阈值</b>：账号封禁 N 小时</li>
        <li>达到 <b>永久封号阈值</b>：账号永久封禁</li>
        <li>积极行为可减少警告值：每日签到、帖子审核通过、评论审核通过</li>
        <li>警告值下限为 0（不会变成负数）</li>
      </ul>
    </div>

    <!-- 阈值配置 -->
    <div class="config-card">
      <div class="card-title">阈值配置</div>
      <div class="config-grid">
        <div class="config-item">
          <div class="config-label">
            警告阈值
            <span class="config-hint">达到此值发送警告通知</span>
          </div>
          <el-input-number v-model="config.warn_threshold" :min="0" :max="500" />
        </div>
        <div class="config-item">
          <div class="config-label">
            临时封号阈值
            <span class="config-hint">达到此值封禁账号</span>
          </div>
          <el-input-number v-model="config.temp_ban_threshold" :min="1" :max="500" />
        </div>
        <div class="config-item">
          <div class="config-label">
            临时封号时长（小时）
            <span class="config-hint">临时封号持续时长</span>
          </div>
          <el-input-number v-model="config.temp_ban_hours" :min="1" :max="720" />
        </div>
        <div class="config-item">
          <div class="config-label">
            永久封号阈值
            <span class="config-hint">达到此值永久封禁</span>
          </div>
          <el-input-number v-model="config.perm_ban_threshold" :min="1" :max="1000" />
        </div>
      </div>
    </div>

    <!-- 违规增加值配置 -->
    <div class="config-card">
      <div class="card-title">违规增加值</div>
      <div class="config-grid">
        <div class="config-item">
          <div class="config-label">
            每次违规基础增加值
            <span class="config-hint">severity=medium 时的基础值</span>
          </div>
          <el-input-number v-model="config.violation_base_score" :min="1" :max="100" />
        </div>
      </div>
    </div>

    <!-- 积极行为减少值配置 -->
    <div class="config-card">
      <div class="card-title">积极行为减少值</div>
      <div class="config-grid">
        <div class="config-item">
          <div class="config-label">
            签到减少
            <span class="config-hint">每日签到成功时减少</span>
          </div>
          <el-input-number v-model="config.checkin_reduce" :min="0" :max="50" />
        </div>
        <div class="config-item">
          <div class="config-label">
            发帖审核通过减少
            <span class="config-hint">帖子通过 AI 审核时减少</span>
          </div>
          <el-input-number v-model="config.post_reduce" :min="0" :max="50" />
        </div>
        <div class="config-item">
          <div class="config-label">
            评论审核通过减少
            <span class="config-hint">评论通过 AI 审核时减少</span>
          </div>
          <el-input-number v-model="config.comment_reduce" :min="0" :max="50" />
        </div>
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="action-bar">
      <el-button type="primary" :loading="saving" @click="saveConfig">保存配置</el-button>
      <el-button @click="resetConfig">重置</el-button>
    </div>

    <!-- 手动调整对话框 -->
    <el-dialog v-model="adjustDialogVisible" title="手动调整用户警告值" width="520px">
      <el-form :model="adjustForm" label-width="100px">
        <el-form-item label="选择用户" required>
          <el-select
            v-model="adjustForm.user_id"
            filterable
            remote
            reserve-keyword
            placeholder="输入昵称/手机号搜索用户"
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
        <el-form-item label="调整值" required>
          <el-input-number v-model="adjustForm.delta" :min="-100" :max="100" />
          <div class="form-tip">
            正数增加（违规），负数减少（奖励/纠正）。例如 +20 表示增加 20 点警告值，-10 表示减少 10 点。
          </div>
        </el-form-item>
        <el-form-item label="调整原因" required>
          <el-input
            v-model="adjustForm.reason"
            type="textarea"
            :rows="3"
            maxlength="200"
            show-word-limit
            placeholder="请填写调整原因，将记录到用户的警告值变动记录中"
          />
        </el-form-item>
        <el-form-item v-if="adjustResult" label="调整结果">
          <el-alert
            :title="`调整成功：当前警告值 ${adjustResult.new_score}${adjustResult.triggered_ban ? '（已触发封号机制）' : ''}`"
            :type="adjustResult.triggered_ban ? 'warning' : 'success'"
            :closable="false"
            show-icon
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="adjustDialogVisible = false">关闭</el-button>
        <el-button type="primary" :loading="submitting" @click="submitAdjust">确认调整</el-button>
      </template>
    </el-dialog>

    <!-- 警告值记录对话框 -->
    <el-dialog v-model="logsDialogVisible" title="用户警告值变动记录" width="780px">
      <div class="logs-toolbar">
        <el-input-number
          v-model="logsForm.user_id"
          :min="1"
          placeholder="用户 ID"
          controls-position="right"
          style="width: 160px"
        />
        <el-button type="primary" @click="logsPage = 1; loadLogs()">查询</el-button>
      </div>
      <el-table v-loading="logsLoading" :data="logsData" border stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="变化" width="90">
          <template #default="{ row }">
            <el-tag :type="row.delta > 0 ? 'danger' : 'success'" size="small">
              {{ fmtDelta(row.delta) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="score_after" label="变动后" width="90" />
        <el-table-column label="来源" width="120">
          <template #default="{ row }">
            <el-tag :type="sourceMap[row.source]?.type || 'info'" size="small">
              {{ sourceMap[row.source]?.text || row.source }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="原因" min-width="200" show-overflow-tooltip />
        <el-table-column label="时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>
      <div class="pagination">
        <el-pagination
          v-model:current-page="logsPage"
          :page-size="logsPageSize"
          :total="logsTotal"
          layout="total, prev, pager, next"
          @current-change="onLogsPageChange"
        />
      </div>
      <template #footer>
        <el-button @click="logsDialogVisible = false">关闭</el-button>
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
.updated-at {
  margin-left: 12px;
  color: #bfbfbf;
}

/* 信息卡片 */
.info-card {
  background: #e6f4ff;
  border: 1px solid #bae0ff;
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 16px;
}
.info-card-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: #0958d9;
  margin-bottom: 8px;
}
.info-ic {
  font-size: 14px;
}
.info-list {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  color: #595959;
  line-height: 1.8;
}
.info-list b {
  color: #1f1f1f;
}

/* 配置卡片 */
.config-card {
  background: #fff;
  padding: 20px 24px;
  border-radius: 8px;
  border: 1px solid #f0f0f0;
  margin-bottom: 16px;
}
.card-title {
  font-size: 15px;
  font-weight: 600;
  color: #262626;
  margin-bottom: 16px;
  padding-bottom: 10px;
  border-bottom: 1px solid #f0f0f0;
}
.config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 18px 24px;
}
.config-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.config-label {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
  font-weight: 500;
  color: #262626;
}
.config-hint {
  font-size: 11px;
  font-weight: 400;
  color: #8c8c8c;
}

/* 操作栏 */
.action-bar {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  padding: 16px 0;
}

/* 表单提示 */
.form-tip {
  font-size: 12px;
  color: #8c8c8c;
  margin-top: 4px;
  line-height: 1.5;
}

/* 日志工具栏 */
.logs-toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
  align-items: center;
}
.pagination {
  display: flex;
  justify-content: flex-end;
  padding: 12px 0 0;
}
</style>
