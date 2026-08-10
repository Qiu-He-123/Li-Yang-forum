<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { adminGetUser, adminListSettings, adminUpdateSettings, type AdminUserBrief } from '../../api/admin'

const friendUserId = ref('')
const loading = ref(false)
const saving = ref(false)
const userInfo = ref<AdminUserBrief | null>(null)
const userError = ref('')
let queryTimer: ReturnType<typeof setTimeout> | null = null

onMounted(async () => {
  loading.value = true
  try {
    const { data } = await adminListSettings()
    const list = data.data ?? []
    friendUserId.value = list.find((s) => s.key === 'default_friend_user_id')?.value ?? ''
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
})

// 输入用户 ID 后自动查询并展示用户名（防抖 300ms）
watch(friendUserId, () => {
  if (queryTimer) clearTimeout(queryTimer)
  userInfo.value = null
  userError.value = ''
  const raw = friendUserId.value.trim()
  if (!raw) return
  const id = Number(raw)
  if (!Number.isInteger(id) || id <= 0) {
    userError.value = '请输入有效的用户 ID'
    return
  }
  queryTimer = setTimeout(async () => {
    try {
      const { data } = await adminGetUser(id)
      userInfo.value = data.data
    } catch (error) {
      userError.value = (error as Error).message
    }
  }, 300)
})

async function save() {
  saving.value = true
  try {
    await adminUpdateSettings({ default_friend_user_id: friendUserId.value.trim() })
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
        配置后，所有用户默认与该用户互相关注，且无法取消关注（留空表示关闭）。
      </p>
      <div class="flex max-w-md items-center gap-2">
        <el-input v-model="friendUserId" type="number" placeholder="输入用户 ID，例如 1" />
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </div>
      <div v-if="userInfo" class="mt-3 rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
        用户 #{{ userInfo.id }}：{{ userInfo.nickname }}（账号：{{ userInfo.username }}）{{ userInfo.school ? ' · ' + userInfo.school : '' }}
      </div>
      <div v-else-if="userError" class="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
        {{ userError }}
      </div>
    </div>
  </div>
</template>
