<script setup lang="ts">
/**
 * 用户管理（大厂风格）
 * - 搜索（昵称/手机号）
 * - 分页列表
 * - 封禁/解封 + 编辑（昵称/简介）
 * - 年龄由用户生日自动计算，管理员不可直接修改
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { adminListUsers, adminUpdateUser, type AdminUser } from '../../api/admin'

const list = ref<AdminUser[]>([])
const loading = ref(false)
const total = ref(0)

const filter = reactive({
  keyword: '',
  page: 1,
  page_size: 20,
})

const editDialogVisible = ref(false)
const editing = ref<AdminUser | null>(null)
const editForm = reactive({
  nickname: '',
  bio: '',
  is_active: true,
})
const submitting = ref(false)

async function load() {
  loading.value = true
  try {
    const { data } = await adminListUsers({
      page: filter.page,
      page_size: filter.page_size,
      keyword: filter.keyword || undefined,
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
  filter.keyword = ''
  filter.page = 1
  load()
}

function onPageChange(p: number) {
  filter.page = p
  load()
}

async function toggleActive(row: AdminUser) {
  const next = !row.is_active
  const action = next ? '解封' : '封禁'
  try {
    await ElMessageBox.confirm(
      `确认${action}用户「${row.nickname}」(#${row.id})？`,
      `${action}用户`,
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await adminUpdateUser(row.id, { is_active: next })
    ElMessage.success(`已${action}`)
    row.is_active = next
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function openEdit(row: AdminUser) {
  editing.value = row
  editForm.nickname = row.nickname
  editForm.bio = row.bio || ''
  editForm.is_active = row.is_active
  editDialogVisible.value = true
}

async function submitEdit() {
  if (!editing.value) return
  submitting.value = true
  try {
    await adminUpdateUser(editing.value.id, {
      nickname: editForm.nickname,
      bio: editForm.bio,
      is_active: editForm.is_active,
    })
    ElMessage.success('已保存')
    editDialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

function fmtTime(t: string | null): string {
  if (!t) return ''
  return t.replace('T', ' ').slice(0, 19)
}

function maskPhone(p: string): string {
  if (!p || p.length < 7) return p
  return p.slice(0, 3) + '****' + p.slice(-4)
}

function ageText(age: number | null | undefined): string {
  if (age === null || age === undefined) return '—'
  return `${age} 岁`
}

onMounted(() => load())
</script>

<template>
  <div v-loading="loading" class="admin-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">用户管理</h2>
        <p class="page-subtitle">共 {{ total }} 个用户</p>
      </div>
      <el-button :icon="'Refresh'" @click="load">刷新</el-button>
    </div>

    <div class="filter-card">
      <el-input
        v-model="filter.keyword"
        placeholder="搜索昵称 / 手机号"
        clearable
        style="width: 260px"
        @keyup.enter="onSearch"
      />
      <el-button type="primary" @click="onSearch">查询</el-button>
      <el-button @click="onReset">重置</el-button>
    </div>

    <div class="table-card">
      <el-table :data="list" border stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" fixed />
        <el-table-column label="用户" min-width="200">
          <template #default="{ row }">
            <div class="user-cell">
              <div
                class="user-avatar"
                :style="row.avatar_url ? { backgroundImage: `url(${row.avatar_url})` } : { background: 'linear-gradient(135deg, #66abff, #007aff)' }"
              >
                <span v-if="!row.avatar_url">{{ (row.nickname || 'U').charAt(0).toUpperCase() }}</span>
              </div>
              <div class="user-info">
                <div class="user-nickname">{{ row.nickname }}</div>
                <div class="user-meta">{{ maskPhone(row.phone) }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="school" label="校区" width="140" />
        <el-table-column label="年龄" width="100">
          <template #default="{ row }">{{ ageText(row.age) }}</template>
        </el-table-column>
        <el-table-column label="粉丝/关注" width="120">
          <template #default="{ row }">
            <span>{{ row.followers_count }} / {{ row.following_count }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
              {{ row.is_active ? '正常' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="注册时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" plain @click="openEdit(row)">编辑</el-button>
            <el-button
              size="small"
              :type="row.is_active ? 'danger' : 'success'"
              @click="toggleActive(row)"
            >
              {{ row.is_active ? '封禁' : '解封' }}
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

    <!-- 编辑对话框 -->
    <el-dialog v-model="editDialogVisible" title="编辑用户" width="480px">
      <el-form :model="editForm" label-width="80px">
        <el-form-item label="昵称">
          <el-input v-model="editForm.nickname" maxlength="30" />
        </el-form-item>
        <el-form-item label="年龄">
          <el-input :value="ageText(editing?.age)" disabled />
          <div class="form-hint">年龄由用户设置的生日自动计算，管理员不可直接修改</div>
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="editForm.bio" type="textarea" :rows="3" maxlength="200" />
        </el-form-item>
        <el-form-item label="账号状态">
          <el-switch
            v-model="editForm.is_active"
            active-text="正常"
            inactive-text="禁用"
          />
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
.user-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background-size: cover;
  background-position: center;
  color: #fff;
  display: grid;
  place-items: center;
  font-size: 14px;
  font-weight: 700;
  flex-shrink: 0;
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
.pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 0 0;
}
.form-hint {
  font-size: 11px;
  color: #8c8c8c;
  margin-top: 4px;
  line-height: 1.5;
}
</style>
