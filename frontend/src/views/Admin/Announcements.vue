<script setup lang="ts">
/**
 * 公告管理（大厂风格）
 * - 列表 + 分页
 * - 新建 / 编辑 / 删除 / 启停
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'

import {
  adminCreateAnnouncement,
  adminDeleteAnnouncement,
  adminListAnnouncements,
  adminUpdateAnnouncement,
  type AdminAnnouncement,
} from '../../api/admin'

const list = ref<AdminAnnouncement[]>([])
const loading = ref(false)
const total = ref(0)
const page = reactive({ page: 1, page_size: 20 })

const dialogVisible = ref(false)
const dialogMode = ref<'create' | 'edit'>('create')
const editing = ref<AdminAnnouncement | null>(null)
const formRef = ref<FormInstance>()
const form = reactive({
  title: '',
  content: '',
  school_id: undefined as number | undefined,
  is_active: true,
  scope: 'all' as 'all' | 'guest' | 'user',
})

const scopeOptions: { value: 'all' | 'guest' | 'user'; label: string; tip: string }[] = [
  { value: 'all', label: '所有人', tip: '游客和登录用户都能看到' },
  { value: 'guest', label: '仅游客', tip: '未登录访客可见；同一 IP 只投递一次，发过就不再发' },
  { value: 'user', label: '仅登录用户', tip: '只有登录用户能看到（弹窗/我的公告）' },
]
const rules: FormRules = {
  title: [{ required: true, message: '请输入标题', trigger: 'blur' }],
  content: [{ required: true, message: '请输入内容', trigger: 'blur' }],
}
const submitting = ref(false)

async function load() {
  loading.value = true
  try {
    const { data } = await adminListAnnouncements({ page: page.page, page_size: page.page_size })
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

function openCreate() {
  dialogMode.value = 'create'
  editing.value = null
  form.title = ''
  form.content = ''
  form.school_id = undefined
  form.is_active = true
  form.scope = 'all'
  dialogVisible.value = true
}

function openEdit(row: AdminAnnouncement) {
  dialogMode.value = 'edit'
  editing.value = row
  form.title = row.title
  form.content = row.content
  form.school_id = row.school_id || undefined
  form.is_active = row.is_active
  form.scope = (row.scope as 'all' | 'guest' | 'user') || 'all'
  dialogVisible.value = true
}

async function submit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  submitting.value = true
  try {
    if (dialogMode.value === 'create') {
      await adminCreateAnnouncement({
        title: form.title,
        content: form.content,
        school_id: form.school_id || null,
        scope: form.scope,
      })
      ElMessage.success('公告已发布')
    } else if (editing.value) {
      await adminUpdateAnnouncement(editing.value.id, {
        title: form.title,
        content: form.content,
        school_id: form.school_id || null,
        is_active: form.is_active,
        scope: form.scope,
      })
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

async function toggleActive(row: AdminAnnouncement) {
  try {
    await adminUpdateAnnouncement(row.id, { is_active: !row.is_active })
    ElMessage.success(!row.is_active ? '已启用' : '已停用')
    row.is_active = !row.is_active
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

async function remove(row: AdminAnnouncement) {
  try {
    await ElMessageBox.confirm(`确认删除公告「${row.title}」？此操作不可恢复。`, '删除公告', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await adminDeleteAnnouncement(row.id)
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

function scopeLabel(scope?: string): string {
  return scope === 'guest' ? '仅游客' : scope === 'user' ? '仅登录用户' : '所有人'
}

function scopeTagType(scope?: string): 'warning' | 'primary' | 'info' {
  return scope === 'guest' ? 'warning' : scope === 'user' ? 'primary' : 'info'
}

onMounted(() => load())
</script>

<template>
  <div v-loading="loading" class="admin-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">公告管理</h2>
        <p class="page-subtitle">共 {{ total }} 条公告</p>
      </div>
      <div>
        <el-button :icon="'Refresh'" @click="load">刷新</el-button>
        <el-button type="primary" @click="openCreate">+ 新建公告</el-button>
      </div>
    </div>

    <div class="table-card">
      <el-table :data="list" border stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" fixed />
        <el-table-column label="标题" min-width="200">
          <template #default="{ row }">
            <div class="ann-title-cell">
              <span class="ann-title">{{ row.title }}</span>
              <span v-if="row.school_id" class="ann-school">校区 #{{ row.school_id }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="内容" min-width="280">
          <template #default="{ row }">
            <div class="ann-content">{{ fmtContent(row.content) }}</div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="可见范围" width="110">
          <template #default="{ row }">
            <el-tag :type="scopeTagType(row.scope)" size="small">
              {{ scopeLabel(row.scope) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" plain @click="openEdit(row as AdminAnnouncement)">编辑</el-button>
            <el-button
              size="small"
              :type="row.is_active ? 'warning' : 'success'"
              @click="toggleActive(row as AdminAnnouncement)"
            >
              {{ row.is_active ? '停用' : '启用' }}
            </el-button>
            <el-button size="small" type="danger" plain @click="remove(row as AdminAnnouncement)">删除</el-button>
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

    <!-- 新建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? '发布新公告' : '编辑公告'"
      width="600px"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" maxlength="100" show-word-limit />
        </el-form-item>
        <el-form-item label="内容" prop="content">
          <el-input v-model="form.content" type="textarea" :rows="6" maxlength="5000" show-word-limit />
        </el-form-item>
        <el-form-item label="指定校区（可选，留空表示全校）">
          <el-input-number v-model="form.school_id" :min="1" :controls="false" placeholder="留空表示全校" />
        </el-form-item>
        <el-form-item label="可见范围">
          <el-radio-group v-model="form.scope">
            <el-radio v-for="opt in scopeOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </el-radio>
          </el-radio-group>
          <div class="scope-tip">
            {{ scopeOptions.find((o) => o.value === form.scope)?.tip }}
          </div>
        </el-form-item>
        <el-form-item v-if="dialogMode === 'edit'" label="状态">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">
          {{ dialogMode === 'create' ? '发布' : '保存' }}
        </el-button>
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
.table-card {
  background: #fff;
  padding: 16px;
  border-radius: 8px;
  border: 1px solid #f0f0f0;
}
.ann-title-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ann-title {
  font-size: 14px;
  font-weight: 600;
  color: #262626;
}
.ann-school {
  font-size: 11px;
  color: #8c8c8c;
}
.ann-content {
  font-size: 13px;
  color: #595959;
  line-height: 1.5;
}
.pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 0 0;
}
.scope-tip {
  margin-top: 4px;
  font-size: 12px;
  color: #8c8c8c;
  line-height: 1.5;
}
</style>
