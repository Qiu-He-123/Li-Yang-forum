<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { adminGetUser, adminListSettings, adminUpdateSettings, type AdminUserBrief } from '../../api/admin'

const friendUserIds = ref('')
const loading = ref(false)
const saving = ref(false)
const userInfos = ref<AdminUserBrief[]>([])
const userError = ref('')
let queryTimer: ReturnType<typeof setTimeout> | null = null

function parseIds(raw: string): number[] {
  const ids: number[] = []
  for (const part of raw.split(/[,，\n\r\s]+/)) {
    const id = Number(part.trim())
    if (Number.isInteger(id) && id > 0 && !ids.includes(id)) ids.push(id)
  }
  return ids
}

onMounted(async () => {
  loading.value = true
  try {
    const { data } = await adminListSettings()
    const list = data.data ?? []
    friendUserIds.value = list.find((s) => s.key === 'default_friend_user_ids')?.value ?? ''
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
})

// 输入用户 ID 后自动查询并展示用户名（防抖 300ms）
watch(friendUserIds, () => {
  if (queryTimer) clearTimeout(queryTimer)
  userInfos.value = []
  userError.value = ''
  const ids = parseIds(friendUserIds.value)
  if (!ids.length) return
  queryTimer = setTimeout(async () => {
    const infos: AdminUserBrief[] = []
    for (const id of ids) {
      try {
        const { data } = await adminGetUser(id)
        infos.push(data.data)
      } catch (error) {
        userError.value = `用户 #${id}：${(error as Error).message}`
        break
      }
    }
    userInfos.value = infos
  }, 300)
})

async function save() {
  const ids = parseIds(friendUserIds.value)
  saving.value = true
  try {
    await adminUpdateSettings({ default_friend_user_ids: ids.join(',') })
    friendUserIds.value = ids.join(',')
    ElMessage.success('已保存')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="p-4">
    <div v-loading="loading" class="rounded border border-ly-line bg-white p-4">
      <h3 class="m-0 mb-1 text-base font-bold">默认好友</h3>
      <p class="mt-1 mb-3 text-sm text-slate-500">
        配置后，所有用户默认与这些用户互相关注，且无法取消关注；默认好友会置顶显示在消息-好友/会话列表（留空表示关闭）。
      </p>
      <div class="flex max-w-md items-start gap-2">
        <el-input
          v-model="friendUserIds"
          type="textarea"
          :rows="3"
          placeholder="输入用户 ID，多个用逗号或换行分隔，例如：1,2,3"
        />
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </div>
      <div v-if="userInfos.length" class="mt-3 space-y-1">
        <div
          v-for="info in userInfos"
          :key="info.id"
          class="rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700"
        >
          用户 #{{ info.id }}：{{ info.nickname }}（账号：{{ info.username }}）{{ info.school ? ' · ' + info.school : '' }}
        </div>
      </div>
      <div v-else-if="userError" class="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
        {{ userError }}
      </div>
    </div>
  </div>
</template>
