<script setup lang="ts">
/**
 * 后台徽章管理
 * - 徽章列表：图标/名称/标识/描述/排序/状态/发放统计
 * - 创建/编辑徽章：支持上传图标图片（服务端自动极限压缩，徽章展示很小）
 * - 激活码管理：批量生成 / 列表 / 删除未使用激活码
 * - 直接发放：按用户 ID 发放徽章
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { http, type LoadingAxiosRequestConfig } from '../../api/http'
import {
  adminCreateBadge,
  adminDeleteBadge,
  adminDeleteBadgeCode,
  adminGenerateBadgeCodes,
  adminGrantBadge,
  adminListBadgeCodes,
  adminListBadges,
  adminUpdateBadge,
  type AdminBadge,
  type BadgeCodeItem,
} from '../../api/badge'

const list = ref<AdminBadge[]>([])
const loading = ref(false)
const keyword = ref('')

// 编辑弹窗
const editDialogVisible = ref(false)
const editing = ref<AdminBadge | null>(null)
const submitting = ref(false)
const editForm = reactive({
  name: '',
  code: '',
  icon: '🏅',
  description: '',
  sort_order: 0,
  is_active: true,
})
const iconUploading = ref(false)
const iconFileInput = ref<HTMLInputElement | null>(null)

// 生成激活码弹窗
const genDialogVisible = ref(false)
const genBadge = ref<AdminBadge | null>(null)
const genForm = reactive({ count: 5, note: '', batch_no: '' })
const generating = ref(false)
const generatedCodes = ref<string[]>([])

// 激活码列表弹窗
const codesDialogVisible = ref(false)
const codesBadge = ref<AdminBadge | null>(null)
const codes = ref<BadgeCodeItem[]>([])
const codesTotal = ref(0)
const codesLoading = ref(false)
const codesPage = ref(1)

// 发放徽章弹窗
const grantDialogVisible = ref(false)
const grantForm = reactive({ user_id: 0, badge_id: 0 })
const granting = ref(false)

async function load() {
  loading.value = true
  try {
    const { data } = await adminListBadges(keyword.value || undefined)
    list.value = data.data || []
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

function onSearch() {
  load()
}

function openCreate() {
  editing.value = null
  Object.assign(editForm, {
    name: '',
    code: '',
    icon: '🏅',
    description: '',
    sort_order: 0,
    is_active: true,
  })
  editDialogVisible.value = true
}

function openEdit(row: AdminBadge) {
  editing.value = row
  Object.assign(editForm, {
    name: row.name,
    code: row.code,
    icon: row.icon || '🏅',
    description: row.description || '',
    sort_order: row.sort_order || 0,
    is_active: row.is_active ?? true,
  })
  editDialogVisible.value = true
}

async function submitEdit() {
  if (!editForm.name.trim() || !editForm.code.trim()) {
    ElMessage.warning('请填写徽章名称和标识')
    return
  }
  submitting.value = true
  try {
    const payload = {
      name: editForm.name.trim(),
      icon: editForm.icon.trim() || '🏅',
      description: editForm.description.trim() || undefined,
      sort_order: Number(editForm.sort_order) || 0,
      is_active: editForm.is_active,
    }
    if (editing.value) {
      await adminUpdateBadge(editing.value.id, payload)
      ElMessage.success('徽章已更新')
    } else {
      await adminCreateBadge({ ...payload, code: editForm.code.trim().toLowerCase() })
      ElMessage.success('徽章已创建')
    }
    editDialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

async function onDelete(row: AdminBadge) {
  try {
    await ElMessageBox.confirm(
      `确认删除徽章「${row.name}」？已发放给用户的徽章将一并移除。`,
      '删除徽章',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await adminDeleteBadge(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

/** 上传徽章图标：后端自动极限压缩（徽章展示很小，压缩后不影响观感） */
async function onIconFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  iconUploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', file)
    const config: LoadingAxiosRequestConfig = {
      showGlobalLoading: false,
      showGlobalError: true,
      timeout: 120_000,
    }
    const { data } = await http.post('/admin/badges/icon', formData, config)
    editForm.icon = data.data.url
    ElMessage.success(`图标已上传并压缩（${data.data.size_text}）`)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    iconUploading.value = false
  }
}

/** 图标是否为图片地址（http(s) 或本站相对上传路径） */
function isImageUrl(url: string): boolean {
  return /^https?:\/\//i.test(url) || url.startsWith('/uploads/') || url.startsWith('/minio/')
}

const isImageIcon = computed(() => isImageUrl(editForm.icon))

function openGen(row: AdminBadge) {
  genBadge.value = row
  Object.assign(genForm, { count: 5, note: '', batch_no: '' })
  generatedCodes.value = []
  genDialogVisible.value = true
}

async function submitGen() {
  if (!genBadge.value) return
  generating.value = true
  try {
    const { data } = await adminGenerateBadgeCodes(genBadge.value.id, {
      count: Number(genForm.count) || 1,
      note: genForm.note || undefined,
      batch_no: genForm.batch_no || undefined,
    })
    generatedCodes.value = data.data.codes
    ElMessage.success(`已生成 ${data.data.codes.length} 个激活码`)
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    generating.value = false
  }
}

function copyCodes() {
  if (!generatedCodes.value.length) return
  navigator.clipboard.writeText(generatedCodes.value.join('\n')).then(() => {
    ElMessage.success('激活码已复制')
  }).catch(() => {
    ElMessage.info(generatedCodes.value.join('，'))
  })
}

async function openCodes(row: AdminBadge) {
  codesBadge.value = row
  codes.value = []
  codesTotal.value = 0
  codesPage.value = 1
  codesDialogVisible.value = true
  await loadCodes()
}

async function loadCodes() {
  if (!codesBadge.value) return
  codesLoading.value = true
  try {
    const { data } = await adminListBadgeCodes({
      badge_id: codesBadge.value.id,
      page: codesPage.value,
      page_size: 10,
    })
    codes.value = data.data.items || []
    codesTotal.value = data.data.total || 0
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    codesLoading.value = false
  }
}

function onCodesPageChange(p: number) {
  codesPage.value = p
  loadCodes()
}

async function onDeleteCode(row: BadgeCodeItem) {
  if (row.used_by != null) {
    ElMessage.warning('已使用的激活码不可删除')
    return
  }
  try {
    await ElMessageBox.confirm(`确认删除激活码 ${row.code}？`, '删除激活码', { type: 'warning' })
  } catch {
    return
  }
  try {
    await adminDeleteBadgeCode(row.id)
    ElMessage.success('已删除')
    await loadCodes()
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function openGrant() {
  grantForm.user_id = 0
  grantForm.badge_id = list.value[0]?.id || 0
  grantDialogVisible.value = true
}

async function submitGrant() {
  if (!grantForm.user_id || !grantForm.badge_id) {
    ElMessage.warning('请填写用户 ID 并选择徽章')
    return
  }
  granting.value = true
  try {
    await adminGrantBadge(grantForm.user_id, grantForm.badge_id)
    ElMessage.success('徽章已发放')
    grantDialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    granting.value = false
  }
}

function fmtTime(t: string | null | undefined): string {
  if (!t) return ''
  return t.replace('T', ' ').slice(0, 19)
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="admin-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">徽章管理</h2>
        <p class="page-subtitle">
          共 {{ list.length }} 个徽章 · 徽章以图标展示在用户名字前（如 [🏅] 昵称）
        </p>
      </div>
      <div class="header-actions">
        <el-button :icon="'Refresh'" @click="load">刷新</el-button>
        <el-button type="primary" @click="openCreate">新建徽章</el-button>
        <el-button type="warning" plain @click="openGrant">直接发放</el-button>
      </div>
    </div>

    <div class="filter-card">
      <el-input
        v-model="keyword"
        placeholder="搜索徽章名称 / 标识"
        clearable
        style="width: 260px"
        @keyup.enter="onSearch"
      />
      <el-button type="primary" @click="onSearch">查询</el-button>
      <el-button @click="keyword = ''; load()">重置</el-button>
    </div>

    <!-- 徽章卡片列表（桌面网格 + 移动单列） -->
    <div class="badge-list">
      <div v-for="b in list" :key="b.id" class="badge-card" :class="{ 'is-disabled': !b.is_active }">
        <div class="badge-card-head">
          <div class="badge-icon" :class="{ 'is-image': isImageUrl(b.icon) }">
            <img v-if="isImageUrl(b.icon)" :src="b.icon" :alt="b.name" />
            <span v-else>{{ b.icon || '🏅' }}</span>
          </div>
          <div class="badge-title-wrap">
            <div class="badge-title-row">
              <span class="badge-name">{{ b.name }}</span>
              <el-tag v-if="b.is_system" type="warning" size="small">系统</el-tag>
              <el-tag v-if="!b.is_active" type="info" size="small">已停用</el-tag>
            </div>
            <span class="badge-code">{{ b.code }}</span>
          </div>
          <div class="badge-stats">
            <span>拥有 {{ b.owner_count }}</span>
            <span>激活码 {{ b.used_code_count }}/{{ b.code_count }}</span>
          </div>
        </div>
        <p class="badge-desc">{{ b.description || '暂无描述' }}</p>
        <div class="badge-actions">
          <el-button size="small" type="primary" plain @click="openEdit(b)">编辑</el-button>
          <el-button size="small" type="success" plain @click="openGen(b)">生成激活码</el-button>
          <el-button size="small" @click="openCodes(b)">激活码({{ b.code_count }})</el-button>
          <el-button
            v-if="!b.is_system"
            size="small"
            type="danger"
            plain
            @click="onDelete(b)"
          >删除</el-button>
        </div>
      </div>
    </div>

    <!-- 创建/编辑徽章 -->
    <el-dialog
      v-model="editDialogVisible"
      :title="editing ? `编辑徽章「${editing.name}」` : '新建徽章'"
      width="520px"
    >
      <el-form :model="editForm" label-width="90px">
        <el-form-item label="徽章名称">
          <el-input v-model="editForm.name" maxlength="32" placeholder="如：管理员" />
        </el-form-item>
        <el-form-item label="徽章标识">
          <el-input
            v-model="editForm.code"
            maxlength="32"
            :disabled="!!editing"
            placeholder="唯一标识，如 admin（创建后不可改）"
          />
        </el-form-item>
        <el-form-item label="图标">
          <div class="icon-editor">
            <div class="icon-preview">
              <img v-if="isImageIcon" :src="editForm.icon" alt="图标预览" />
              <span v-else>{{ editForm.icon || '🏅' }}</span>
            </div>
            <div class="icon-inputs">
              <el-input v-model="editForm.icon" maxlength="500" placeholder="Emoji（如 🏅）或图片 URL" />
              <el-button :loading="iconUploading" @click="iconFileInput?.click()">
                上传图标（自动压缩）
              </el-button>
              <input
                ref="iconFileInput"
                class="hidden-file-input"
                type="file"
                accept="image/*"
                @change="onIconFileChange"
              />
            </div>
          </div>
          <div class="form-hint">徽章展示很小（约 16-32px），上传后服务端自动压缩到 96px 内，不影响观感。</div>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" type="textarea" :rows="2" maxlength="200" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="editForm.sort_order" :min="0" :max="9999" />
          <div class="form-hint">数字越小越靠前</div>
        </el-form-item>
        <el-form-item label="启用状态">
          <el-switch v-model="editForm.is_active" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 生成激活码 -->
    <el-dialog v-model="genDialogVisible" title="生成激活码" width="520px">
      <template v-if="genBadge">
        <p class="dialog-tip">
          为徽章「{{ genBadge.icon }} {{ genBadge.name }}」批量生成激活码，用户可在
          「消息 → 系统 → 领取徽章」中输入激活码领取。
        </p>
        <el-form :model="genForm" label-width="90px">
          <el-form-item label="数量">
            <el-input-number v-model="genForm.count" :min="1" :max="100" />
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="genForm.note" maxlength="100" placeholder="如：发给班长张三" />
          </el-form-item>
          <el-form-item label="批次号">
            <el-input v-model="genForm.batch_no" maxlength="32" placeholder="不填自动生成" />
          </el-form-item>
        </el-form>
        <div v-if="generatedCodes.length" class="gen-result">
          <div class="gen-result-head">
            <span class="gen-result-title">已生成 {{ generatedCodes.length }} 个激活码</span>
            <el-button size="small" @click="copyCodes">复制全部</el-button>
          </div>
          <div class="gen-codes">
            <span v-for="c in generatedCodes" :key="c" class="gen-code">{{ c }}</span>
          </div>
        </div>
      </template>
      <template #footer>
        <el-button @click="genDialogVisible = false">关闭</el-button>
        <el-button type="primary" :loading="generating" @click="submitGen">生成</el-button>
      </template>
    </el-dialog>

    <!-- 激活码列表 -->
    <el-dialog v-model="codesDialogVisible" :title="`激活码列表（${codesBadge?.name || ''}）`" width="640px">
      <div v-loading="codesLoading" class="codes-table-wrap">
        <el-table :data="codes" border stripe size="small">
          <el-table-column prop="code" label="激活码" width="130" />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.used_by != null ? 'info' : 'success'" size="small">
                {{ row.used_by != null ? '已使用' : '未使用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="used_nickname" label="使用者" width="100">
            <template #default="{ row }">{{ row.used_nickname || '—' }}</template>
          </el-table-column>
          <el-table-column label="使用时间" width="150">
            <template #default="{ row }">{{ fmtTime(row.used_at) || '—' }}</template>
          </el-table-column>
          <el-table-column prop="note" label="备注" min-width="120" show-overflow-tooltip />
          <el-table-column label="操作" width="90" fixed="right">
            <template #default="{ row }">
              <el-button
                size="small"
                type="danger"
                plain
                :disabled="row.used_by != null"
                @click="onDeleteCode(row as BadgeCodeItem)"
              >删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="pagination">
          <el-pagination
            v-model:current-page="codesPage"
            :page-size="10"
            :total="codesTotal"
            layout="total, prev, pager, next"
            @current-change="onCodesPageChange"
          />
        </div>
      </div>
      <template #footer>
        <el-button @click="codesDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 直接发放徽章 -->
    <el-dialog v-model="grantDialogVisible" title="直接发放徽章" width="460px">
      <el-form label-width="90px">
        <el-form-item label="用户 ID">
          <el-input-number v-model="grantForm.user_id" :min="1" style="width: 100%" />
          <div class="form-hint">在「用户管理」中查看用户 ID</div>
        </el-form-item>
        <el-form-item label="徽章">
          <el-select v-model="grantForm.badge_id" style="width: 100%">
            <el-option
              v-for="b in list"
              :key="b.id"
              :value="b.id"
              :label="`${b.icon} ${b.name}`"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="grantDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="granting" @click="submitGrant">发放</el-button>
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
  flex-wrap: wrap;
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
.badge-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 14px;
}
.badge-card {
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 10px;
  padding: 16px;
  transition: box-shadow 0.15s;
}
.badge-card:hover {
  box-shadow: 0 4px 16px rgba(0, 21, 41, 0.08);
}
.badge-card.is-disabled {
  opacity: 0.65;
}
.badge-card-head {
  display: flex;
  align-items: center;
  gap: 12px;
}
.badge-icon {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: #f6f7f9;
  display: grid;
  place-items: center;
  font-size: 28px;
  flex-shrink: 0;
  overflow: hidden;
}
.badge-icon.is-image img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.badge-title-wrap {
  flex: 1;
  min-width: 0;
}
.badge-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.badge-name {
  font-size: 15px;
  font-weight: 700;
  color: #262626;
}
.badge-code {
  font-size: 12px;
  color: #8c8c8c;
  font-family: monospace;
}
.badge-stats {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  font-size: 11px;
  color: #8c8c8c;
  white-space: nowrap;
}
.badge-desc {
  margin: 10px 0;
  font-size: 12px;
  color: #595959;
  line-height: 1.5;
  min-height: 18px;
}
.badge-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.icon-editor {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
}
.icon-preview {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: #f6f7f9;
  border: 1px dashed #d9d9d9;
  display: grid;
  place-items: center;
  font-size: 34px;
  flex-shrink: 0;
  overflow: hidden;
}
.icon-preview img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.icon-inputs {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}
.hidden-file-input {
  display: none;
}
.form-hint {
  font-size: 11px;
  color: #8c8c8c;
  margin-top: 4px;
  line-height: 1.5;
}
.dialog-tip {
  margin: 0 0 14px;
  font-size: 13px;
  color: #595959;
  line-height: 1.6;
}
.gen-result {
  margin-top: 12px;
  padding: 12px;
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  border-radius: 8px;
}
.gen-result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.gen-result-title {
  font-size: 13px;
  font-weight: 600;
  color: #389e0d;
}
.gen-codes {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.gen-code {
  padding: 4px 10px;
  background: #fff;
  border: 1px solid #b7eb8f;
  border-radius: 6px;
  font-family: monospace;
  font-size: 12px;
  color: #262626;
}
.codes-table-wrap {
  width: 100%;
}
.pagination {
  display: flex;
  justify-content: flex-end;
  padding: 12px 0 0;
}

@media (max-width: 768px) {
  .badge-list {
    grid-template-columns: 1fr;
  }
  .badge-card-head {
    flex-wrap: wrap;
  }
  .badge-stats {
    align-items: flex-start;
    width: 100%;
  }
  .icon-editor {
    flex-direction: column;
  }
}
</style>
