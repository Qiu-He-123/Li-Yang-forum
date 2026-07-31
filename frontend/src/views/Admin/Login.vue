<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'

import { useAdminStore } from '../../stores/admin'

const router = useRouter()
const route = useRoute()
const admin = useAdminStore()

const formRef = ref<FormInstance>()
const form = reactive({
  username: '',
  password: '',
})
const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}
const loading = ref(false)

async function submit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    await admin.login({ ...form })
    ElMessage.success('登录成功')
    const redirect = (route.query.redirect as string) || '/admin/posts'
    router.push(redirect)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="grid min-h-screen place-items-center bg-ly-paper">
    <div class="w-full max-w-sm rounded border border-ly-line bg-white p-6">
      <h1 class="m-0 mb-1 text-center text-xl font-black text-ly-green">LY 管理后台</h1>
      <p class="m-0 mb-6 text-center text-xs text-slate-500">仅授权管理员可登录</p>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent>
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="管理员用户名" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password placeholder="管理员密码" @keyup.enter="submit" />
        </el-form-item>
        <el-button class="w-full" type="primary" :loading="loading" @click="submit">登录</el-button>
      </el-form>
    </div>
  </main>
</template>
