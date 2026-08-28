<script setup lang="ts">
/**
 * 活动管理（后台）
 * - 列表 + 分页 + 关键词搜索
 * - 新建 / 编辑 / 启用停用 / 删除
 * - 查看报名名单
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'

import {
  adminActivityParticipants,
  adminCreateActivity,
  adminDeleteActivity,
  adminListActivities,
  adminUpdateActivity,
  type AdminActivity,
  type AdminActivityParticipant,
} from '../../api/admin'

const list = ref<AdminActivity[]>([])
const loading = ref(false)
const total = ref(0)
const page = reactive({ page: 1, page_size: 20 })
const keyword = ref('')

const dialogVisible = ref(false)
const dialogMode = ref<'create' | 'edit'>('create')
const editing = ref<AdminActivity | null>(null)
const formRef = ref<FormInstance>()
const form = reactive({
  title: '',
  description: '',
  location: '',
  cover_url: '',
  start_at: '',
  end_at: '',
  organizer: '',
  contact: '',
  max_participants: undefined as number | undefined,
  is_active: true,
})
const rules: FormRules = {
  title: [{ required: true, message: '请输入活动标题', trigger: 'blur' }],
  description: [{ required: true, message: '请输入活动内容', trigger: 'blur' }],
}
const submitting = ref(false)

// 报名名单
const participantsVisible = ref(false)
const participants = ref<AdminActivityParticipant[]>([])
const participantsLoading = ref(false)
const participantsTotal = ref(0)
const participantsPage = ref(1)
const currentActivity = ref<AdminActivity | null>(null)

async function load() {
  loading.value = true
  try {
    const { data } = await adminListActivities({
      page: page.page,
      page_size: page.page_size,
      keyword: keyword.value || undefined,
    })
    list.value = data.data.items || []
    total.value = data.data.total || 0
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

function onPageChange(p: number) {
  page.page = p
  load()
}

function onSearch() {
  page.page = 1
  load()
}

function resetForm() {
  form.title = ''
  form.description = ''
  form.location = ''
  form.cover_url = ''
  form.start_at = ''
  form.end_at = ''
  form.organizer = ''
  form.contact = ''
  form.max_participants = undefined
  form.is_active = true
}

function openCreate() {
  dialogMode.value = 'create'
  editing.value = null
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: AdminActivity) {
  dialogMode.value = 'edit'
  editing.value = row
  form.title = row.title
  form.description = row.description
  form.location = row.location || ''
  form.cover_url = row.cover_url || ''
  form.start_at = row.start_at ? row.start_at.replace('T', ' ').slice(0, 16) : ''
  form.end_at = row.end_at ? row.end_at.replace('T', ' ').slice(0, 16) : ''
  form.organizer = row.organizer || ''
  form.contact = row.contact || ''
  form.max_participants = row.max_participants ?? undefined
  form.is_active = row.is_active
  dialogVisible.value = true
}

function toIso(v: string): string | null {
  if (!v) return null
  // "YYYY-MM-DD HH:mm" -> ISO（按本地时间）
  return new Date(v.replace(' ', 'T')).toISOString()
}

async function submit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  submitting.value = true
  const payload = {
    title: form.title,
    description: form.description,
    location: form.location || null,
    cover_url: form.cover_url || null,
    start_at: toIso(form.start_at),
    end_at: toIso(form.end_at),
    organizer: form.organizer || null,
    contact: form.contact || null,
    max_participants: form.max_participants ?? null,
    is_active: form.is_active,
  }
  try {
    if (dialogMode.value === 'create') {
      await adminCreateActivity(payload)
      ElMessage.success('活动已创建')
    } else if (editing.value) {
      await adminUpdateActivity(editing.value.id, payload)
      ElMessage.success('已保存')
    }
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function toggleActive(row: AdminActivity) {
  try {
    await adminUpdateActivity(row.id, { is_active: !row.is_active })
    ElMessage.success(!row.is_active ? '已启用' : '已停用')
    row.is_active = !row.is_active
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function remove(row: AdminActivity) {
  try {
    await ElMessageBox.confirm(`确认删除活动「${row.title}」？此操作不可恢复。`, '删除活动', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await adminDeleteActivity(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function openParticipants(row: AdminActivity) {
  currentActivity.value = row
  participantsVisible.value = true
  participantsPage.value = 1
  await loadParticipants()
}

async function loadParticipants() {
  if (!currentActivity.value) return
  participantsLoading.value = true
  try {
    const { data } = await adminActivityParticipants(currentActivity.value.id, {
      page: participantsPage.value,
      page_size: 20,
    })
    participants.value = data.data.items || []
    participantsTotal.value = data.data.total || 0
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    participantsLoading.value = false
  }
}

function onParticipantsPageChange(p: number) {
  participantsPage.value = p
  loadParticipants()
}

function fmtTime(t: string | null): string {
  if (!t) return '待定'
  return t.replace('T', ' ').slice(0, 19)
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="admin-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">活动管理</h2>
        <p class="page-subtitle">共 {{ total }} 个活动</p>
      </div>
      <div class="header-actions">
        <el-input
          v-model="keyword"
          placeholder="搜索活动标题"
          clearable
          style="width: 200px"
          @keyup.enter="onSearch"
          @clear="onSearch"
        />
        <el-button :icon="'Refresh'" @click="load">刷新</el-button>
        <el-button type="primary" @click="openCreate">+ 新建活动</el-button>
      </div>
    </div>

    <div class="table-card">
      <el-table :data="list" border stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" fixed />
        <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
        <el-table-column label="开始时间" width="150">
          <template #default="{ row }">{{ fmtTime(row.start_at) }}</template>
        </el-table-column>
        <el-table-column label="结束时间" width="150">
          <template #default="{ row }">{{ fmtTime(row.end_at) }}</template>
        </el-table-column>
        <el-table-column prop="location" label="地点" min-width="130" show-overflow-tooltip />
        <el-table-column label="报名" width="110">
          <template #default="{ row }">
            {{ row.participant_count }}{{ row.max_participants ? ` / ${row.max_participants}` : '' }} 人
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '上架' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" plain @click="openEdit(row as AdminActivity)">编辑</el-button>
            <el-button size="small" type="info" plain @click="openParticipants(row as AdminActivity)">报名名单</el-button>
            <el-button
              size="small"
              :type="row.is_active ? 'warning' : 'success'"
              @click="toggleActive(row as AdminActivity)"
            >
              {{ row.is_active ? '停用' : '启用' }}
            </el-button>
            <el-button size="small" type="danger" plain @click="remove(row as AdminActivity)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="page.page"
          :page-size="page.page_size"
          :total="total"
          layout="total, prev, pager, next, jumper"
          @current-change="onPageChange"
        />
      </div>
    </div>

    <!-- 新建/编辑活动 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? '新建活动' : '编辑活动'"
      width="640px"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="活动标题" prop="title">
          <el-input v-model="form.title" maxlength="100" show-word-limit />
        </el-form-item>
        <el-form-item label="活动内容" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="5" maxlength="5000" show-word-limit />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="开始时间">
              <el-input v-model="form.start_at" placeholder="2026-09-01 14:00" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="结束时间">
              <el-input v-model="form.end_at" placeholder="2026-09-01 17:00" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="活动地点">
          <el-input v-model="form.location" maxlength="200" />
        </el-form-item>
        <el-form-item label="封面图 URL（可选，使用图片上传接口获得）">
          <el-input v-model="form.cover_url" placeholder="/uploads/xxx.png" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="主办方">
              <el-input v-model="form.organizer" maxlength="100" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="联系方式">
              <el-input v-model="form.contact" maxlength="100" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="人数上限（留空不限制）">
              <el-input-number v-model="form.max_participants" :min="1" :controls="false" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="状态">
              <el-switch v-model="form.is_active" active-text="上架" inactive-text="停用" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">
          {{ dialogMode === 'create' ? '创建' : '保存' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 报名名单 -->
    <el-dialog
      v-model="participantsVisible"
      :title="`报名名单 - ${currentActivity?.title || ''}`"
      width="560px"
    >
      <div v-loading="participantsLoading">
        <el-table :data="participants" border stripe style="width: 100%">
          <el-table-column prop="user_id" label="用户ID" width="90" />
          <el-table-column label="昵称" min-width="160">
            <template #default="{ row }">
              <div class="participant-cell">
                <el-avatar :size="26" :src="row.avatar_url || undefined">
                  {{ (row.nickname || '?').charAt(0) }}
                </el-avatar>
                <span>{{ row.nickname }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="报名时间" width="170">
            <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
        <div v-if="!participants.length && !participantsLoading" class="empty-tip">暂无报名</div>
        <div class="pagination">
          <el-pagination
            v-model:current-page="participantsPage"
            :page-size="20"
            :total="participantsTotal"
            layout="total, prev, pager, next"
            @current-change="onParticipantsPageChange"
          />
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
.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
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
.table-card {
  background: #fff;
  padding: 16px;
  border-radius: 8px;
  border: 1px solid #f0f0f0;
}
.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
.participant-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}
.empty-tip {
  padding: 30px;
  text-align: center;
  color: #999;
  font-size: 13px;
}
</style>
