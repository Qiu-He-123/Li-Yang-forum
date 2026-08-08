<script setup lang="ts">
/**
 * 种子邀请码管理
 * - 列表展示所有种子邀请码（含批次号、状态、使用者信息）
 * - 批量生成邀请码（可指定数量、批次号、备注）
 * - 删除未使用的邀请码
 * - 筛选：状态（unused/used）、批次号
 * - 复制邀请码到剪贴板
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  adminDeleteSeedCode,
  adminGenerateSeedCodes,
  adminListSeedCodes,
  type SeedCode,
} from '../../api/verification'

const list = ref<SeedCode[]>([])
const loading = ref(false)
const total = ref(0)

const filter = reactive({
  status: '' as '' | 'unused' | 'used',
  batch_no: '',
  page: 1,
  page_size: 20,
})

const statusOptions = [
  { value: '', label: '全部状态' },
  { value: 'unused', label: '未使用' },
  { value: 'used', label: '已使用' },
]

const statusMeta: Record<string, { type: 'success' | 'warning' | 'info'; text: string }> = {
  unused: { type: 'warning', text: '未使用' },
  used: { type: 'success', text: '已使用' },
}

// 生成对话框
const generateDialogVisible = ref(false)
const generateForm = reactive({
  count: 10,
  batch_no: '',
  note: '',
})
const generating = ref(false)
const lastGenerated = ref<{ batch_no: string; codes: string[] } | null>(null)

async function load() {
  loading.value = true
  try {
    const { data } = await adminListSeedCodes({
      page: filter.page,
      page_size: filter.page_size,
      status: filter.status || undefined,
      batch_no: filter.batch_no || undefined,
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
  filter.status = ''
  filter.batch_no = ''
  filter.page = 1
  load()
}

function onPageChange(p: number) {
  filter.page = p
  load()
}

function openGenerate() {
  generateForm.count = 10
  generateForm.batch_no = ''
  generateForm.note = ''
  lastGenerated.value = null
  generateDialogVisible.value = true
}

async function submitGenerate() {
  // 防护：数量范围校验
  if (generateForm.count < 1 || generateForm.count > 500) {
    ElMessage.warning('生成数量必须在 1 ~ 500 之间')
    return
  }
  // 防护：备注长度
  if (generateForm.note.length > 200) {
    ElMessage.error('备注不能超过 200 字')
    return
  }
  generating.value = true
  try {
    const { data } = await adminGenerateSeedCodes({
      count: generateForm.count,
      batch_no: generateForm.batch_no.trim() || undefined,
      note: generateForm.note.trim() || undefined,
    })
    lastGenerated.value = {
      batch_no: data.data.batch_no,
      codes: data.data.codes,
    }
    ElMessage.success(`已成功生成 ${data.data.count} 个邀请码`)
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    generating.value = false
  }
}

async function deleteCode(row: SeedCode) {
  if (row.used_by) {
    ElMessage.warning('已使用的邀请码不能删除')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认删除邀请码「${row.code}」？删除后不可恢复。`,
      '删除邀请码',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await adminDeleteSeedCode(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

function copyCode(code: string) {
  navigator.clipboard.writeText(code).then(() => {
    ElMessage.success(`已复制：${code}`)
  }).catch(() => {
    ElMessage.info(`邀请码：${code}`)
  })
}

function copyAllCodes() {
  if (!lastGenerated.value || !lastGenerated.value.codes.length) return
  const text = lastGenerated.value.codes.join('\n')
  navigator.clipboard.writeText(text).then(() => {
    ElMessage.success(`已复制 ${lastGenerated.value!.codes.length} 个邀请码`)
  }).catch(() => {
    ElMessage.warning('复制失败，请手动选择')
  })
}

function exportCodes() {
  if (!lastGenerated.value || !lastGenerated.value.codes.length) return
  const codes = lastGenerated.value.codes
  const batchNo = lastGenerated.value.batch_no
  const content = `批次号：${batchNo}\n生成时间：${new Date().toLocaleString('zh-CN')}\n数量：${codes.length}\n\n${codes.join('\n')}`
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `seed_codes_${batchNo}.txt`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  ElMessage.success('已导出 txt 文件')
}

function fmtTime(t: string | null): string {
  if (!t) return ''
  return t.replace('T', ' ').slice(0, 19)
}

onMounted(() => load())
</script>

<template>
  <div v-loading="loading" class="admin-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">种子邀请码管理</h2>
        <p class="page-subtitle">共 {{ total }} 个邀请码 · 用于线下发放给可靠学生</p>
      </div>
      <div class="header-actions">
        <el-button :icon="'Refresh'" @click="load">刷新</el-button>
        <el-button type="primary" :icon="'Plus'" @click="openGenerate">批量生成</el-button>
      </div>
    </div>

    <div class="filter-card">
      <el-select
        v-model="filter.status"
        placeholder="使用状态"
        clearable
        style="width: 140px"
        @change="onSearch"
      >
        <el-option v-for="opt in statusOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
      <el-input
        v-model="filter.batch_no"
        placeholder="批次号筛选"
        clearable
        style="width: 200px"
        @keyup.enter="onSearch"
      />
      <el-button type="primary" @click="onSearch">查询</el-button>
      <el-button @click="onReset">重置</el-button>
    </div>

    <div class="table-card">
      <el-table :data="list" border stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" fixed />
        <el-table-column label="邀请码" min-width="160">
          <template #default="{ row }">
            <div class="code-cell">
              <span class="code-text">{{ row.code }}</span>
              <el-button size="small" text :icon="'CopyDocument'" @click="copyCode(row.code)" />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="批次号" width="160">
          <template #default="{ row }">
            <span v-if="row.batch_no" class="batch-text">{{ row.batch_no }}</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.note" class="reason-text">{{ row.note }}</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="(row.used_by ? statusMeta.used : statusMeta.unused).type" size="small">
              {{ (row.used_by ? statusMeta.used : statusMeta.unused).text }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="使用者" min-width="140">
          <template #default="{ row }">
            <div v-if="row.used_by" class="user-cell">
              <div class="user-info">
                <div class="user-nickname">{{ row.used_by_username || '用户' + row.used_by }}</div>
                <div class="user-meta">#{{ row.used_by }}</div>
              </div>
            </div>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="使用时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.used_at) }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="!row.used_by"
              size="small"
              type="danger"
              plain
              @click="deleteCode(row as SeedCode)"
            >
              删除
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

    <!-- 生成对话框 -->
    <el-dialog v-model="generateDialogVisible" title="批量生成种子邀请码" width="560px">
      <el-form :model="generateForm" label-width="90px">
        <el-form-item label="生成数量" required>
          <el-input-number
            v-model="generateForm.count"
            :min="1"
            :max="500"
            :step="1"
            style="width: 200px"
          />
          <span class="form-hint-inline">最多 500 个/批</span>
        </el-form-item>
        <el-form-item label="批次号">
          <el-input
            v-model="generateForm.batch_no"
            placeholder="选填，便于归类；留空则系统自动生成"
            maxlength="40"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input
            v-model="generateForm.note"
            type="textarea"
            :rows="2"
            placeholder="选填，如：发放给本部校区学生会"
            maxlength="200"
            show-word-limit
          />
        </el-form-item>
      </el-form>

      <!-- 防护提示 -->
      <el-alert type="warning" :closable="false" show-icon>
        <template #title>使用须知</template>
        <div class="text-xs mt-1">
          种子邀请码适用于线下发放给可靠的班长 / 学生会主席等，由他们再分享给同学。
          请妥善保管，避免被校外人员获取。
        </div>
      </el-alert>

      <!-- 生成结果 -->
      <div v-if="lastGenerated" class="generate-result">
        <div class="result-header">
          <div class="result-info">
            <span>批次号：<strong>{{ lastGenerated.batch_no }}</strong></span>
            <span>共 <strong>{{ lastGenerated.codes.length }}</strong> 个</span>
          </div>
          <div class="result-actions">
            <el-button size="small" type="primary" plain @click="copyAllCodes">复制全部</el-button>
            <el-button size="small" type="success" plain @click="exportCodes">导出 txt</el-button>
          </div>
        </div>
        <div class="codes-grid">
          <div
            v-for="code in lastGenerated.codes"
            :key="code"
            class="code-item"
            @click="copyCode(code)"
          >
            {{ code }}
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="generateDialogVisible = false">
          {{ lastGenerated ? '关闭' : '取消' }}
        </el-button>
        <el-button
          v-if="!lastGenerated"
          type="primary"
          :loading="generating"
          @click="submitGenerate"
        >
          生成邀请码
        </el-button>
        <el-button
          v-else
          type="primary"
          :loading="generating"
          @click="submitGenerate"
        >
          再生成一批
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
.header-actions {
  display: flex;
  gap: 8px;
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
.text-muted {
  color: #bfbfbf;
}
.form-hint-inline {
  font-size: 12px;
  color: #8c8c8c;
  margin-left: 8px;
}
.text-xs {
  font-size: 12px;
  color: #595959;
  line-height: 1.6;
}

/* 邀请码单元格 */
.code-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}
.code-text {
  font-family: 'Courier New', monospace;
  font-size: 13px;
  font-weight: 600;
  color: #262626;
  letter-spacing: 0.5px;
}
.batch-text {
  font-family: 'Courier New', monospace;
  font-size: 12px;
  color: #595959;
}

/* 生成结果 */
.generate-result {
  margin-top: 16px;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  overflow: hidden;
}
.result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: #fafafa;
  border-bottom: 1px solid #f0f0f0;
  flex-wrap: wrap;
  gap: 8px;
}
.result-info {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: #595959;
}
.result-info strong {
  color: #262626;
  font-family: 'Courier New', monospace;
}
.result-actions {
  display: flex;
  gap: 8px;
}
.codes-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 6px;
  padding: 12px;
  max-height: 280px;
  overflow-y: auto;
}
.code-item {
  font-family: 'Courier New', monospace;
  font-size: 13px;
  font-weight: 600;
  color: #262626;
  background: #f5f7fa;
  border: 1px solid #e8e8e8;
  border-radius: 4px;
  padding: 6px 10px;
  text-align: center;
  cursor: pointer;
  transition: all 0.15s;
  letter-spacing: 0.5px;
}
.code-item:hover {
  background: #409eff;
  color: #fff;
  border-color: #409eff;
}
.pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 0 0;
}
</style>
