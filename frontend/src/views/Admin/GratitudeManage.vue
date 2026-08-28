<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import type { UploadFile } from 'element-plus'
import {
  adminCreateGratitude,
  adminDeleteGratitude,
  adminFetchGratitudeList,
  adminUpdateGratitude,
  adminUploadGratitudeAvatar,
  type GratitudeItem,
} from '../../api/gratitude'

/**
 * 管理后台 - 感谢名单
 * - 列表展示（名字/头像/简介/排序/上架状态）
 * - 新增 / 编辑（头像、名字、简介、详细介绍、排序、上架）
 * - 删除
 */
const list = ref<GratitudeItem[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const dialogMode = ref<'create' | 'edit'>('create')
const submitting = ref(false)
const formRef = ref<FormInstance>()

const form = reactive<{ id: number; name: string; avatar_url: string; bio: string; detail: string; sort_order: number; is_active: boolean }>({
  id: 0,
  name: '',
  avatar_url: '',
  bio: '',
  detail: '',
  sort_order: 0,
  is_active: true,
})

const rules: FormRules = {
  name: [{ required: true, message: '请输入名字', trigger: 'blur' }],
}

async function load() {
  loading.value = true
  try {
    const { data: resp } = await adminFetchGratitudeList()
    list.value = resp.data ?? []
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

onMounted(load)

function openCreate() {
  dialogMode.value = 'create'
  Object.assign(form, { id: 0, name: '', avatar_url: '', bio: '', detail: '', sort_order: 0, is_active: true })
  dialogVisible.value = true
}

function openEdit(row: any) {
  dialogMode.value = 'edit'
  Object.assign(form, {
    id: row.id,
    name: row.name,
    avatar_url: row.avatar_url || '',
    bio: row.bio || '',
    detail: row.detail || '',
    sort_order: row.sort_order ?? 0,
    is_active: row.is_active,
  })
  dialogVisible.value = true
}

async function onSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    submitting.value = true
    try {
      const payload = {
        name: form.name.trim(),
        avatar_url: form.avatar_url.trim() || null,
        bio: form.bio.trim() || null,
        detail: form.detail,
        sort_order: form.sort_order || 0,
        is_active: form.is_active,
      }
      if (dialogMode.value === 'create') {
        await adminCreateGratitude(payload)
        ElMessage.success('新增成功')
      } else {
        await adminUpdateGratitude(form.id, payload)
        ElMessage.success('更新成功')
      }
      dialogVisible.value = false
      await load()
    } catch {
      // 拦截器已提示
    } finally {
      submitting.value = false
    }
  })
}

async function onDelete(row: any) {
  try {
    await ElMessageBox.confirm(`确认删除「${row.name}」？`, '删除提醒', { type: 'warning' })
  } catch {
    return
  }
  try {
    await adminDeleteGratitude(row.id)
    ElMessage.success('删除成功')
    await load()
  } catch {
    // 拦截器已提示
  }
}

// ====== 头像上传（jpg/png/webp/gif，≤5MB） ======
const avatarUploading = ref(false)

function isImageUrl(url: string | null | undefined): boolean {
  return !!url && (url.startsWith('/') || url.startsWith('http'))
}

async function onAvatarFileChange(file: UploadFile) {
  if (!file.raw) return
  if (file.raw.size > 5 * 1024 * 1024) {
    ElMessage.error('头像大小不能超过 5MB')
    return
  }
  avatarUploading.value = true
  try {
    const { data } = await adminUploadGratitudeAvatar(file.raw)
    form.avatar_url = (data as any).data.url
    ElMessage.success('头像上传成功')
  } catch {
    // 错误提示由 http 拦截器统一处理
  } finally {
    avatarUploading.value = false
  }
}
</script>

<template>
  <div class="grat-admin">
    <div class="grat-admin__head">
      <div>
        <h2>感谢名单</h2>
        <p class="muted">展示在「我的 → 感谢名单」页，支持头像、简介与详情页。</p>
      </div>
      <el-button type="primary" @click="openCreate">+ 新增</el-button>
    </div>

    <el-table v-loading="loading" :data="list" stripe style="width: 100%">
      <el-table-column prop="sort_order" label="排序" width="80" />
      <el-table-column label="头像" width="80">
        <template #default="{ row }">
          <el-avatar :size="38" :src="row.avatar_url || undefined">
            {{ (row.name || '?').charAt(0).toUpperCase() }}
          </el-avatar>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="名字" width="140" />
      <el-table-column prop="bio" label="简介" min-width="200" show-overflow-tooltip />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
            {{ row.is_active ? '上架' : '下架' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? '新增名单' : '编辑名单'"
      width="480px"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="88px">
        <el-form-item label="名字" prop="name">
          <el-input v-model="form.name" maxlength="50" placeholder="名字 / 昵称" />
        </el-form-item>
        <el-form-item label="头像">
          <div class="upload-row">
            <el-upload
              :auto-upload="false"
              :show-file-list="false"
              accept=".jpg,.jpeg,.png,.webp,.gif,image/png,image/jpeg,image/webp,image/gif"
              :on-change="onAvatarFileChange"
            >
              <div class="avatar-uploader">
                <img v-if="isImageUrl(form.avatar_url)" :src="form.avatar_url" class="avatar-uploader__img" alt="头像" />
                <div v-else class="avatar-uploader__placeholder">
                  <el-icon v-if="!avatarUploading"><Plus /></el-icon>
                  <span>{{ avatarUploading ? '上传中...' : '上传' }}</span>
                </div>
              </div>
            </el-upload>
            <div style="flex: 1">
              <el-input v-model="form.avatar_url" placeholder="图片 URL，留空用名字首字占位" />
              <div class="upload-tip">支持 JPG / PNG / WEBP / GIF，≤5MB。也可手动填写图片 URL。</div>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="form.bio" maxlength="200" show-word-limit placeholder="列表里的一句话简介" />
        </el-form-item>
        <el-form-item label="详细介绍">
          <el-input v-model="form.detail" type="textarea" :rows="5" placeholder="详情页内容，多行换行展示" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" :step="1" />
          <span class="tips">数字越小越靠前</span>
        </el-form-item>
        <el-form-item label="上架">
          <el-switch v-model="form.is_active" />
          <span class="tips">关闭后前端不再展示</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.grat-admin { padding: 0; }
.grat-admin__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 16px;
  gap: 16px;
}
.grat-admin__head h2 { margin: 0; font-size: 18px; }
.muted { margin: 4px 0 0; color: #909399; font-size: 13px; }
.tips { margin-left: 8px; color: #a0a4ad; font-size: 12px; }

.upload-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
}
.avatar-uploader {
  width: 64px;
  height: 64px;
  border: 1px dashed #d9d9d9;
  border-radius: 8px;
  cursor: pointer;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: #fafafa;
}
.avatar-uploader:hover { border-color: #409eff; }
.avatar-uploader__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.avatar-uploader__placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  font-size: 12px;
  color: #8c939d;
}
.upload-tip {
  width: 100%;
  font-size: 12px;
  color: #86868b;
  margin-top: 6px;
  line-height: 1.5;
}
</style>