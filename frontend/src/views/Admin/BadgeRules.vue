<script setup lang="ts">
/**
 * 徽章自动发放规则
 * - 将「行为动作 + 阈值」绑定到徽章：用户达成后系统自动发放
 * - 动作类型集中在 BADGE_ACTIONS，新增动作只需在后端注册，扩展性高
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  adminCreateBadgeRule,
  adminDeleteBadgeRule,
  adminListBadgeRules,
  adminListBadges,
  adminUpdateBadgeRule,
  BADGE_ACTIONS,
  type AdminBadge,
  type BadgeRule,
} from '../../api/badge'

const rules = ref<BadgeRule[]>([])
const badges = ref<AdminBadge[]>([])
const loading = ref(false)

const editDialogVisible = ref(false)
const editing = ref<BadgeRule | null>(null)
const submitting = ref(false)
const editForm = reactive({
  action: '',
  badge_id: 0,
  threshold: 1,
  description: '',
  is_enabled: true,
})

async function load() {
  loading.value = true
  try {
    const [ruleRes, badgeRes] = await Promise.all([
      adminListBadgeRules(),
      adminListBadges(),
    ])
    rules.value = ruleRes.data.data || []
    badges.value = badgeRes.data.data || []
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  Object.assign(editForm, {
    action: BADGE_ACTIONS[0]?.value || '',
    badge_id: badges.value[0]?.id || 0,
    threshold: 1,
    description: '',
    is_enabled: true,
  })
  editDialogVisible.value = true
}

function openEdit(row: BadgeRule) {
  editing.value = row
  Object.assign(editForm, {
    action: row.action,
    badge_id: row.badge_id,
    threshold: row.threshold,
    description: row.description || '',
    is_enabled: row.is_enabled,
  })
  editDialogVisible.value = true
}

async function submitEdit() {
  if (!editForm.action || !editForm.badge_id || editForm.threshold < 1) {
    ElMessage.warning('请选择动作、徽章并填写有效阈值')
    return
  }
  submitting.value = true
  try {
    if (editing.value) {
      await adminUpdateBadgeRule(editing.value.id, {
        badge_id: editForm.badge_id,
        threshold: editForm.threshold,
        description: editForm.description.trim() || undefined,
        is_enabled: editForm.is_enabled,
      })
      ElMessage.success('规则已更新')
    } else {
      await adminCreateBadgeRule({
        action: editForm.action,
        badge_id: editForm.badge_id,
        threshold: editForm.threshold,
        description: editForm.description.trim() || undefined,
        is_enabled: editForm.is_enabled,
      })
      ElMessage.success('规则已创建')
    }
    editDialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function onToggle(row: BadgeRule) {
  try {
    await adminUpdateBadgeRule(row.id, { is_enabled: !row.is_enabled })
    row.is_enabled = !row.is_enabled
    ElMessage.success(row.is_enabled ? '已启用' : '已停用')
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function onDelete(row: BadgeRule) {
  try {
    await ElMessageBox.confirm(
      `确认删除规则「${row.action_label} ≥ ${row.threshold}」？删除后不再自动发放。`,
      '删除规则',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await adminDeleteBadgeRule(row.id)
    ElMessage.success('已删除')
    await load()
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
        <h2 class="page-title">徽章自动发放</h2>
        <p class="page-subtitle">
          用户达到指定行为阈值时系统自动发放徽章并通知；新增动作只需在后端注册，规则可随意扩展
        </p>
      </div>
      <div class="header-actions">
        <el-button :icon="'Refresh'" @click="load">刷新</el-button>
        <el-button type="primary" :icon="'Plus'" @click="openCreate">新建规则</el-button>
      </div>
    </div>

    <div v-if="rules.length" class="rule-list">
      <div v-for="row in rules" :key="row.id" class="rule-card" :class="{ 'is-disabled': !row.is_enabled }">
        <div class="rule-main">
          <div class="rule-badge">
            <span class="rule-badge-icon">{{ row.badge_icon || '🏅' }}</span>
          </div>
          <div class="rule-info">
            <div class="rule-title-row">
              <span class="rule-title">{{ row.action_label }} ≥ {{ row.threshold }}</span>
              <el-tag :type="row.is_enabled ? 'success' : 'info'" size="small">
                {{ row.is_enabled ? '启用中' : '已停用' }}
              </el-tag>
            </div>
            <span class="rule-badge-name">发放徽章：{{ row.badge_name || '#' + row.badge_id }}</span>
            <span v-if="row.description" class="rule-desc">{{ row.description }}</span>
            <span class="rule-time">创建于 {{ fmtTime(row.created_at) }}</span>
          </div>
        </div>
        <div class="rule-actions">
          <el-switch :model-value="row.is_enabled" @change="onToggle(row)" />
          <el-button size="small" type="primary" plain @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" plain @click="onDelete(row)">删除</el-button>
        </div>
      </div>
    </div>

    <div v-else class="empty-tip">
      <p>还没有自动发放规则，点击右上角「新建规则」配置一个吧</p>
    </div>

    <!-- 新建/编辑规则 -->
    <el-dialog
      v-model="editDialogVisible"
      :title="editing ? '编辑自动发放规则' : '新建自动发放规则'"
      width="520px"
    >
      <el-form :model="editForm" label-width="110px">
        <el-form-item label="触发动作" required>
          <el-select
            v-model="editForm.action"
            :disabled="!!editing"
            style="width: 100%"
            placeholder="选择用户行为"
          >
            <el-option
              v-for="opt in BADGE_ACTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <div class="form-hint">用户在该行为上达到阈值后自动发放</div>
        </el-form-item>
        <el-form-item label="发放徽章" required>
          <el-select v-model="editForm.badge_id" style="width: 100%" placeholder="选择要发放的徽章">
            <el-option
              v-for="b in badges"
              :key="b.id"
              :value="b.id"
              :label="`${b.icon} ${b.name}`"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="发放阈值" required>
          <el-input-number v-model="editForm.threshold" :min="1" :max="99999" style="width: 100%" />
          <div class="form-hint">达到该数值（含）即自动发放</div>
        </el-form-item>
        <el-form-item label="规则说明">
          <el-input v-model="editForm.description" type="textarea" :rows="2" maxlength="200" placeholder="选填，给其他管理员看的说明" />
        </el-form-item>
        <el-form-item label="启用状态">
          <el-switch v-model="editForm.is_enabled" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitEdit">保存</el-button>
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
.header-actions {
  display: flex;
  gap: 8px;
}
.rule-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.rule-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 10px;
  padding: 14px 16px;
  flex-wrap: wrap;
}
.rule-card.is-disabled {
  opacity: 0.6;
}
.rule-main {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  flex: 1;
}
.rule-badge {
  width: 46px;
  height: 46px;
  border-radius: 50%;
  background: #f6f7f9;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.rule-badge-icon {
  font-size: 24px;
}
.rule-info {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.rule-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.rule-title {
  font-size: 15px;
  font-weight: 700;
  color: #262626;
}
.rule-badge-name {
  font-size: 12px;
  color: #595959;
}
.rule-desc {
  font-size: 12px;
  color: #8c8c8c;
}
.rule-time {
  font-size: 11px;
  color: #bfbfbf;
}
.rule-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.form-hint {
  font-size: 11px;
  color: #8c8c8c;
  margin-top: 4px;
  line-height: 1.5;
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
</style>
