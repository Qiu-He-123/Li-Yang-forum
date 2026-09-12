<script setup lang="ts">
/**
 * 订单 AI 管理（后台）
 * - 会话列表：每用户一行，显示额度用量 / 消息数
 * - 查看某用户对话消息详情
 * - 开关 AI、设置每日 token 上限与上下文条数（即时生效）
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  adminOrderAiMessages,
  adminOrderAiSessions,
  adminOrderAiSettings,
  adminUpdateOrderAiSettings,
  type AiChatMsg,
  type OrderAiSessionRow,
  type OrderAiSettings,
} from '../../api/order'

const loading = ref(false)
const list = ref<OrderAiSessionRow[]>([])
const total = ref(0)
const page = reactive({ page: 1, page_size: 20 })
const keyword = ref('')

// 设置
const settings = ref<OrderAiSettings>({ enabled: false, daily_token_limit: 200000, context_messages: 12 })
const saving = ref(false)

// 对话详情
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<{ role: string; messages: AiChatMsg[] } | null>(null)

async function load() {
  loading.value = true
  try {
    const { data } = await adminOrderAiSessions({ page: page.page, page_size: page.page_size, keyword: keyword.value || undefined })
    list.value = data.data.items || []
    total.value = data.data.total || 0
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

async function loadSettings() {
  try {
    const { data } = await adminOrderAiSettings()
    settings.value = { ...data.data }
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

async function saveSettings() {
  saving.value = true
  try {
    const { data } = await adminUpdateOrderAiSettings({ ...settings.value })
    settings.value = { ...data.data }
    ElMessage.success('设置已保存（即时生效）')
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    saving.value = false
  }
}

async function openDetail(row: OrderAiSessionRow) {
  detailLoading.value = true
  detailVisible.value = true
  try {
    const { data } = await adminOrderAiMessages(row.user_id)
    detail.value = data.data
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    detailLoading.value = false
  }
}

function onPage(p: number) { page.page = p; load() }
function onSearch() { page.page = 1; load() }

const ROLE_TEXT: Record<string, string> = { user: '用户', assistant: 'AI', tool: '工具' }

onMounted(() => { void load(); void loadSettings() })
</script>

<template>
  <div class="admin-page">
    <el-card shadow="never" class="toolbar">
      <div class="toolbar-left">
        <h2 class="page-title">订单 AI 管理</h2>
        <p class="page-desc">接单大厅的对话助手。可查看各用户会话与消息、开关服务、调整每日 token 上限（保存后即时生效）。</p>
      </div>
      <div class="toolbar-right">
        <el-input
          v-model="keyword"
          placeholder="按昵称/账号搜索用户"
          clearable
          style="width: 220px"
          @keyup.enter="onSearch"
          @clear="onSearch"
        />
        <el-button type="primary" icon="Search" @click="onSearch">搜索</el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="list" style="width: 100%">
        <el-table-column label="用户" min-width="160">
          <template #default="{ row }">
            <div><b>{{ row.user_name || ('用户 #' + row.user_id) }}</b></div>
            <div class="muted">UID: {{ row.user_id }}</div>
          </template>
        </el-table-column>
        <el-table-column label="消息数" prop="message_count" width="90" />
        <el-table-column label="今日 Token" width="150">
          <template #default="{ row }">
            <el-tag type="warning">{{ row.daily_token }} / {{ row.daily_token_limit }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="额度日期" prop="daily_date" width="120" />
        <el-table-column label="最近活跃" prop="updated_at" min-width="170" show-overflow-tooltip />
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row as OrderAiSessionRow)">查看对话</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        style="margin-top: 16px; justify-content: flex-end"
        layout="prev, pager, next, total"
        :page-size="page.page_size"
        :total="total"
        :current-page="page.page"
        @current-change="onPage"
      />
    </el-card>

    <!-- 额度设置 -->
    <el-card shadow="never">
      <template #header>服务与额度设置</template>
      <el-form label-width="180px" style="max-width: 640px">
        <el-form-item label="启用订单 AI">
          <el-switch v-model="settings.enabled" />
          <span class="muted" style="margin-left: 8px">关闭后接单大厅 AI 助手无法对话</span>
        </el-form-item>
        <el-form-item label="每日 Token 上限">
          <el-input-number v-model="settings.daily_token_limit" :min="0" :step="10000" style="width: 220px" />
        </el-form-item>
        <el-form-item label="上下文消息条数">
          <el-input-number v-model="settings.context_messages" :min="1" :max="200" style="width: 220px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="saveSettings">保存设置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 对话详情 -->
    <el-dialog v-model="detailVisible" title="对话详情" width="640px" top="6vh">
      <div v-if="detailLoading">加载中...</div>
      <div v-else-if="!detail">无数据</div>
      <div v-else>
        <div style="margin-bottom: 10px"><el-tag type="info">用户：{{ detail.role }}</el-tag>（共 {{ detail.messages.length }} 条）</div>
        <el-scrollbar max-height="60vh">
          <div
            v-for="m in detail.messages"
            :key="m.id || m.created_at"
            :class="['msg-line', m.role === 'user' ? 'msg-user' : m.role === 'tool' ? 'msg-tool' : 'msg-ai']"
          >
            <div class="msg-head">
              <el-tag size="small" :type="m.role === 'user' ? 'primary' : m.role === 'tool' ? 'warning' : 'success'">
                {{ ROLE_TEXT[m.role] || m.role }}
              </el-tag>
              <span class="muted" style="margin-left: 8px">{{ m.created_at }}</span>
            </div>
            <pre v-if="m.content" class="msg-content">{{ m.content }}</pre>
            <pre v-else-if="m.meta" class="msg-content msg-json">{{ JSON.stringify(m.meta, null, 2) }}</pre>
            <div v-else class="muted msg-content">（无内容）</div>
          </div>
        </el-scrollbar>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.admin-page { display: flex; flex-direction: column; gap: 14px; }
.toolbar { display: flex; flex-direction: row; align-items: center; justify-content: space-between; gap: 16px; }
.toolbar-left { flex: 1; min-width: 0; }
.page-title { margin: 0 0 4px; font-size: 18px; }
.page-desc { margin: 0; color: var(--el-text-color-secondary); font-size: 13px; line-height: 1.6; }
.toolbar-right { display: flex; gap: 10px; align-items: center; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
.msg-line { margin-bottom: 10px; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--el-border-color-lighter); }
.msg-user { background: #ecf5ff; }
.msg-ai { background: #f0f9eb; }
.msg-tool { background: #fdf6ec; }
.msg-head { display: flex; align-items: center; margin-bottom: 4px; }
.msg-content { margin: 0; white-space: pre-wrap; word-break: break-word; font-family: inherit; font-size: 13px; line-height: 1.6; }
.msg-json { font-family: var(--el-font-family-mono, monospace); }
</style>