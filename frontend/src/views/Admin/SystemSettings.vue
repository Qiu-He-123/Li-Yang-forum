<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { adminListSettings, adminUpdateSettings } from '../../api/admin'

const friendUserId = ref('')
const loading = ref(false)
const saving = ref(false)

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
    </div>
  </div>
</template>
