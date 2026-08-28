<script setup lang="ts">
/**
 * 微信朋友圈管理（后台独立页）
 * - 社区微信号：用户绑定微信时需要添加的微信号（绑定引导页展示）
 * - 设备令牌：只读展示（由 start_server / init_wechat_sync 生成，与客户端 config.json 配套）
 * - 绑定管理：查看谁绑定了微信、同步开关、支持解绑
 * - 动态管理：查看客户端上报的朋友圈内容
 */
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  adminListSettings,
  adminUpdateSettings,
  adminWechatBindings,
  adminWechatMoments,
  adminWechatUnbind,
  type AdminWechatBinding,
  type AdminWechatMoment,
} from '../../api/admin'

const loading = ref(false)

// ============ 基础配置 ============
const bindAccount = ref('')
const deviceToken = ref('')
const savingConfig = ref(false)

// ============ 绑定列表 ============
const bindings = ref<AdminWechatBinding[]>([])
const bindingsTotal = ref(0)
const bindingsPage = ref(1)
const bindingsKeyword = ref('')
const bindingsLoading = ref(false)
const unbindingId = ref<number | null>(null)

// ============ 动态列表 ============
const moments = ref<AdminWechatMoment[]>([])
const momentsTotal = ref(0)
const momentsPage = ref(1)
const momentsKeyword = ref('')
const momentsLoading = ref(false)
const activeTab = ref('bindings')

const PAGE_SIZE = 20

function fmtTime(t: string | null | undefined): string {
  if (!t) return '—'
  return t.replace('T', ' ').slice(0, 19)
}

async function loadConfig() {
  const { data } = await adminListSettings()
  const list = data.data ?? []
  bindAccount.value = list.find((s) => s.key === 'wechat_bind_account')?.value ?? ''
  deviceToken.value = list.find((s) => s.key === 'wechat_device_token')?.value ?? ''
}

async function saveConfig() {
  savingConfig.value = true
  try {
    await adminUpdateSettings({
      wechat_bind_account: bindAccount.value.trim(),
    })
    ElMessage.success('微信同步配置已保存')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    savingConfig.value = false
  }
}

function copyBindAccount() {
  const text = bindAccount.value.trim()
  if (!text) {
    ElMessage.warning('请先填写社区微信号')
    return
  }
  navigator.clipboard.writeText(text).then(
    () => ElMessage.success('已复制'),
    () => ElMessage.error('复制失败，请手动复制'),
  )
}

function copyDeviceToken() {
  const text = deviceToken.value.trim()
  if (!text) {
    ElMessage.warning('暂无设备令牌，请先运行启动脚本生成')
    return
  }
  navigator.clipboard.writeText(text).then(
    () => ElMessage.success('已复制'),
    () => ElMessage.error('复制失败，请手动复制'),
  )
}

async function loadBindings() {
  bindingsLoading.value = true
  try {
    const { data } = await adminWechatBindings({
      page: bindingsPage.value,
      page_size: PAGE_SIZE,
      keyword: bindingsKeyword.value.trim() || undefined,
    })
    bindings.value = data.data.items
    bindingsTotal.value = data.data.total
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    bindingsLoading.value = false
  }
}

async function loadMoments() {
  momentsLoading.value = true
  try {
    const { data } = await adminWechatMoments({
      page: momentsPage.value,
      page_size: PAGE_SIZE,
      keyword: momentsKeyword.value.trim() || undefined,
    })
    moments.value = data.data.items
    momentsTotal.value = data.data.total
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    momentsLoading.value = false
  }
}

function onTabChange(name: string | number) {
  if (name === 'bindings' && !bindingsTotal.value) loadBindings()
  if (name === 'moments' && !momentsTotal.value) loadMoments()
}

async function unbind(row: AdminWechatBinding) {
  try {
    await ElMessageBox.confirm(
      `确认解绑 ${row.nickname || row.username || `用户 #${row.user_id}`} 的微信（${row.wechat_id || row.wxid}）？\n解绑后对方需重新走绑定流程，自动同步将关闭。`,
      '解绑微信',
      { type: 'warning', confirmButtonText: '确认解绑', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  unbindingId.value = row.id
  try {
    await adminWechatUnbind(row.id)
    ElMessage.success('已解绑')
    await loadBindings()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    unbindingId.value = null
  }
}

onMounted(async () => {
  loading.value = true
  try {
    await loadConfig()
    await loadBindings()
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div v-loading="loading" class="p-4">
    <!-- ====== 基础配置 ====== -->
    <div class="mb-4 rounded border border-ly-line bg-white p-4">
      <h3 class="m-0 mb-1 text-base font-bold">社区微信号</h3>
      <p class="mt-1 mb-3 text-sm text-slate-500">
        用户绑定微信时的第一步是添加这个微信号为好友，并在此展示；后台修改后前端绑定页立即生效。
      </p>
      <div class="flex items-center gap-2" style="max-width: 480px">
        <el-input v-model="bindAccount" placeholder="例如：ly_shequ（微信号或 wxid）" />
        <el-button @click="copyBindAccount">复制</el-button>
      </div>
      <h3 class="m-0 mb-1 mt-5 text-base font-bold">同步设备令牌（只读）</h3>
      <p class="mt-1 mb-3 text-sm text-slate-500">
        同步客户端连接后端时使用的令牌，由「重启服务器」流程自动生成并写入客户端
        config.json，这里仅作查看，请勿手动修改——改了一边另一边就会对不上。
      </p>
      <div class="flex items-center gap-2" style="max-width: 480px">
        <el-input :model-value="deviceToken" readonly placeholder="暂无令牌，请先运行启动脚本" />
        <el-button @click="copyDeviceToken">复制</el-button>
      </div>
      <div class="mt-3">
        <el-button type="primary" :loading="savingConfig" @click="saveConfig">保存配置</el-button>
      </div>
    </div>

    <!-- ====== 绑定 / 动态 ====== -->
    <div class="rounded border border-ly-line bg-white p-4">
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <el-tab-pane label="微信绑定" name="bindings">
          <div class="mb-3 flex items-center gap-2">
            <el-input
              v-model="bindingsKeyword"
              placeholder="搜索用户昵称 / 账号 / 微信号"
              clearable
              style="max-width: 320px"
              @keyup.enter="loadBindings"
              @clear="loadBindings"
            />
            <el-button type="primary" @click="loadBindings">搜索</el-button>
          </div>
          <el-table v-loading="bindingsLoading" :data="bindings" stripe>
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column label="用户" min-width="140">
              <template #default="{ row }">
                <span class="font-medium">{{ row.nickname || '—' }}</span>
                <span class="ml-1 text-slate-400">@{{ row.username }}</span>
              </template>
            </el-table-column>
            <el-table-column label="微信号" min-width="140">
              <template #default="{ row }">
                <div>{{ row.wechat_id || '—' }}</div>
                <div class="text-xs text-slate-400">{{ row.wechat_nickname }} · {{ row.wxid }}</div>
              </template>
            </el-table-column>
            <el-table-column label="自动同步" width="100">
              <template #default="{ row }">
                <el-tag :type="row.sync_enabled ? 'success' : 'info'" size="small">
                  {{ row.sync_enabled ? '开启' : '关闭' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row.status === 'verified' ? 'success' : 'warning'" size="small">
                  {{ row.status === 'verified' ? '已绑定' : '待验证' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="绑定时间" width="160">
              <template #default="{ row }">{{ fmtTime(row.bound_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ row }">
                <el-button
                  type="danger"
                  link
                  :loading="unbindingId === row.id"
                  @click="unbind(row as AdminWechatBinding)"
                >解绑</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="mt-3 flex justify-end">
            <el-pagination
              v-model:current-page="bindingsPage"
              :total="bindingsTotal"
              :page-size="PAGE_SIZE"
              layout="prev, pager, next, total"
              @current-change="loadBindings"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane label="朋友圈动态" name="moments">
          <div class="mb-3 flex items-center gap-2">
            <el-input
              v-model="momentsKeyword"
              placeholder="搜索作者 / 内容"
              clearable
              style="max-width: 320px"
              @keyup.enter="loadMoments"
              @clear="loadMoments"
            />
            <el-button type="primary" @click="loadMoments">搜索</el-button>
          </div>
          <el-table v-loading="momentsLoading" :data="moments" stripe>
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column label="作者" min-width="120">
              <template #default="{ row }">
                <div>{{ row.author_name || '—' }}</div>
                <div class="text-xs text-slate-400">{{ row.wxid }}</div>
              </template>
            </el-table-column>
            <el-table-column label="内容" min-width="260" show-overflow-tooltip>
              <template #default="{ row }">
                <span>{{ row.content || '（仅图片/视频）' }}</span>
                <el-tag v-if="row.media_count > 0" type="primary" size="small" class="ml-2">
                  {{ row.media_count }} 张媒体
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="发布时间" width="160">
              <template #default="{ row }">{{ fmtTime(row.create_time) }}</template>
            </el-table-column>
            <el-table-column label="同步时间" width="160">
              <template #default="{ row }">{{ fmtTime(row.fetched_at) }}</template>
            </el-table-column>
          </el-table>
          <div class="mt-3 flex justify-end">
            <el-pagination
              v-model:current-page="momentsPage"
              :total="momentsTotal"
              :page-size="PAGE_SIZE"
              layout="prev, pager, next, total"
              @current-change="loadMoments"
            />
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>
