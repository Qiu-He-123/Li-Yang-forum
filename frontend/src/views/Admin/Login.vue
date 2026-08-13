<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'

import { useAdminStore } from '../../stores/admin'
import { fetchCaptcha } from '../../api/auth'

const router = useRouter()
const route = useRoute()
const admin = useAdminStore()

const formRef = ref<FormInstance>()
const form = reactive({
  username: '',
  password: '',
})
const captchaImg = ref('')
const captchaId = ref('')
const captchaText = ref('')
const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}
const loading = ref(false)

async function loadCaptcha() {
  captchaText.value = ''
  try {
    const { data } = await fetchCaptcha()
    captchaId.value = data.data.captcha_id
    captchaImg.value = data.data.image
  } catch {
    captchaId.value = ''
    captchaImg.value = ''
  }
}

onMounted(loadCaptcha)

async function submit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  if (!captchaId.value || !captchaText.value.trim()) {
    ElMessage.error('请输入图形验证码')
    return
  }
  loading.value = true
  try {
    await admin.login({
      ...form,
      captcha_id: captchaId.value,
      captcha_text: captchaText.value.trim(),
    })
    ElMessage.success('登录成功')
    const redirect = (route.query.redirect as string) || '/admin/posts'
    router.push(redirect)
  } catch (error) {
    ElMessage.error((error as Error).message)
    void loadCaptcha()
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
        <el-form-item label="图形验证码">
          <div class="flex w-full items-center gap-2">
            <el-input
              v-model="captchaText"
              placeholder="输入图中字符"
              maxlength="8"
              @keyup.enter="submit"
            />
            <img
              v-if="captchaImg"
              :src="captchaImg"
              alt="验证码"
              class="h-12 w-[160px] shrink-0 cursor-pointer rounded border border-slate-200 object-cover"
              title="看不清？点击刷新"
              @click="loadCaptcha"
            />
          </div>
        </el-form-item>
        <el-button class="w-full" type="primary" :loading="loading" @click="submit">登录</el-button>
      </el-form>
    </div>
  </main>
</template>
