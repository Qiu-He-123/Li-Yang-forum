<script setup lang="ts">
/**
 * 登录日志（大厂风格）
 * - 用户 ID + 成功/失败过滤
 * - 分页列表
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { adminListLoginLogs, type AdminLoginLog } from '../../api/admin'

const list = ref<AdminLoginLog[]>([])
const loading = ref(false)
const total = ref(0)

const filter = reactive({
  user_id: undefined as number | undefined,
  success: '' as string,
  page: 1,
  page_size: 50,
})

const successOptions = [
  { value: '', label: '全部' },
  { value: 'true', label: '成功' },
  { value: 'false', label: '失败' },
]

async function load() {
  loading.value = true
  try {
    const { data } = await adminListLoginLogs({
      page: filter.page,
      page_size: filter.page_size,
      user_id: filter.user_id || undefined,
      success: filter.success === '' ? undefined : filter.success === 'true',
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
  filter.user_id = undefined
  filter.success = ''
  filter.page = 1
  load()
}

function onPageChange(p: number) {
  filter.page = p
  load()
}

function fmtTime(t: string | null): string {
  if (!t) return ''
  return t.replace('T', ' ').slice(0, 19)
}

function maskPhone(p: string | null): string {
  if (!p || p.length < 7) return p || '-'
  return p.slice(0, 3) + '****' + p.slice(-4)
}

onMounted(() => load())
</script>

<template>
  <div v-loading="loading" class="admin-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">登录日志</h2>
        <p class="page-subtitle">共 {{ total }} 条记录</p>
      </div>
      <el-button :icon="'Refresh'" @click="load">刷新</el-button>
    </div>

    <!-- 统计卡片 -->
    <div class="stat-cards">
      <div class="stat-card stat-card--success">
        <div class="stat-icon">✓</div>
        <div class="stat-body">
          <div class="stat-label">成功登录</div>
          <div class="stat-value">{{ list.filter((l) => l.success).length }}</div>
        </div>
      </div>
      <div class="stat-card stat-card--danger">
        <div class="stat-icon">✗</div>
        <div class="stat-body">
          <div class="stat-label">登录失败</div>
          <div class="stat-value">{{ list.filter((l) => !l.success).length }}</div>
        </div>
      </div>
      <div class="stat-card stat-card--info">
        <div class="stat-icon">📊</div>
        <div class="stat-body">
          <div class="stat-label">本页成功率</div>
          <div class="stat-value">
            {{ list.length ? Math.round((list.filter((l) => l.success).length / list.length) * 100) : 0 }}%
          </div>
        </div>
      </div>
    </div>

    <div class="filter-card">
      <div>
        <label class="filter-label">用户 ID</label>
        <el-input-number v-model="filter.user_id" :min="1" :controls="false" placeholder="留空查全部" />
      </div>
      <div>
        <label class="filter-label">登录状态</label>
        <el-select v-model="filter.success" placeholder="全部" style="width: 160px" @change="onSearch">
          <el-option v-for="opt in successOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
      </div>
      <div class="filter-actions">
        <el-button type="primary" @click="onSearch">查询</el-button>
        <el-button @click="onReset">重置</el-button>
      </div>
    </div>

    <div class="table-card">
      <el-table :data="list" border stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" fixed />
        <el-table-column prop="user_id" label="用户 ID" width="100">
          <template #default="{ row }">
            <span v-if="row.user_id" class="user-id">#{{ row.user_id }}</span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="手机号" width="160">
          <template #default="{ row }">{{ maskPhone(row.phone) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.success ? 'success' : 'danger'" size="small">
              {{ row.success ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="ip" label="IP 地址" width="160">
          <template #default="{ row }">{{ row.ip || '-' }}</template>
        </el-table-column>
        <el-table-column prop="device" label="设备" min-width="240">
          <template #default="{ row }">
            <span class="device-text">{{ row.device || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="180">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
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

/* 统计卡 */
.stat-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}
.stat-card {
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 16px 20px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.stat-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 18px;
  font-weight: 700;
  flex-shrink: 0;
}
.stat-card--success .stat-icon {
  background: #f6ffed;
  color: #52c41a;
}
.stat-card--danger .stat-icon {
  background: #fff2f0;
  color: #ff4d4f;
}
.stat-card--info .stat-icon {
  background: #e6f7ff;
  color: #1890ff;
}
.stat-body {
  flex: 1;
  min-width: 0;
}
.stat-label {
  font-size: 12px;
  color: #8c8c8c;
}
.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: #1f1f1f;
  line-height: 1.2;
}

/* 筛选 */
.filter-card {
  background: #fff;
  padding: 16px 20px;
  border-radius: 8px;
  border: 1px solid #f0f0f0;
  margin-bottom: 16px;
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  align-items: flex-end;
}
.filter-label {
  display: block;
  font-size: 12px;
  color: #8c8c8c;
  margin-bottom: 4px;
}
.filter-actions {
  display: flex;
  gap: 8px;
}
.table-card {
  background: #fff;
  padding: 16px;
  border-radius: 8px;
  border: 1px solid #f0f0f0;
}
.user-id {
  font-weight: 600;
  color: #1890ff;
}
.text-muted {
  color: #bfbfbf;
}
.device-text {
  font-size: 12px;
  color: #595959;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: inline-block;
  max-width: 100%;
}
.pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 0 0;
}

@media (max-width: 768px) {
  .stat-cards {
    grid-template-columns: 1fr;
  }
}
</style>
