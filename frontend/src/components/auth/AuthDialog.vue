<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { useSessionStore } from '../../stores/session'
import { useSchoolStore } from '../../stores/school'
import { useUserStore } from '../../stores/user'
import { usePostStore } from '../../stores/post'

interface Props {
  modelValue: boolean
}
const props = defineProps<Props>()
const router = useRouter()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'authed'): void
}>()

const session = useSessionStore()
const schoolStore = useSchoolStore()
const userStore = useUserStore()
const postStore = usePostStore()

const authMode = ref<'login' | 'register'>('login')

const initialForm = {
  nickname: '',
  username: '',
  password: '',
  confirm_password: '',
  school_id: undefined as number | undefined,
  agreed: false,
  qq: '',
  invite_code: '',
}
const authForm = reactive({ ...initialForm })

const submitting = ref(false)

// 弹窗关闭时重置表单
watch(
  () => props.modelValue,
  (visible) => {
    if (visible) {
      schoolStore.loadSchools()
    } else {
      Object.assign(authForm, initialForm)
      authMode.value = 'login'
    }
  },
)

async function submit() {
  if (authMode.value === 'register') {
    if (!authForm.agreed) {
      ElMessage.error('请先同意社区协议')
      return
    }
    if (authForm.password !== authForm.confirm_password) {
      ElMessage.error('两次密码不一致')
      return
    }
    if (!authForm.school_id) {
      ElMessage.error('请选择校区')
      return
    }
    // 用户名格式校验
    if (!/^[A-Za-z0-9_]{3,32}$/.test(authForm.username)) {
      ElMessage.error('账号只能包含字母、数字和下划线，3-32 位')
      return
    }
  } else {
    if (!authForm.username || !authForm.password) {
      ElMessage.error('请输入账号和密码')
      return
    }
  }
  submitting.value = true
  try {
    if (authMode.value === 'register') {
      await session.register({
        nickname: authForm.nickname,
        username: authForm.username,
        password: authForm.password,
        confirm_password: authForm.confirm_password,
        school_id: authForm.school_id!,
        agreed: authForm.agreed,
        qq: authForm.qq || null,
        invite_code: authForm.invite_code || null,
      })
      // 根据认证状态给出不同提示
      if (session.verificationStatus === 'verified') {
        ElMessage.success('注册成功，已解锁全部功能')
      } else {
        ElMessage.success('注册成功，可浏览内容；发帖/评论需填写邀请码')
      }
    } else {
      await session.login({ username: authForm.username, password: authForm.password })
      ElMessage.success('已登录')
    }
    emit('update:modelValue', false)
    await userStore.loadProfile()
    await postStore.loadPosts()
    emit('authed')
  } catch (error) {
    // 封号用户：跳转到封号提示页
    if ((error as Error & { isBanned?: boolean }).isBanned) {
      emit('update:modelValue', false)
      router.push('/banned')
      return
    }
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="authMode === 'login' ? '登录' : '注册'"
    width="90%"
    style="max-width: 420px"
    :fullscreen="false"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-form label-position="top">
      <el-form-item v-if="authMode === 'register'" label="昵称">
        <el-input v-model="authForm.nickname" placeholder="展示给其他用户的名称" />
      </el-form-item>
      <el-form-item :label="authMode === 'login' ? '账号' : '账号（登录用的，不是昵称）'">
        <el-input
          v-model="authForm.username"
          :placeholder="authMode === 'login' ? '请输入注册时的账号（不是昵称）' : '设置登录账号，3-32 位字母/数字/下划线'"
        />
      </el-form-item>
      <p v-if="authMode === 'login'" class="m-0 -mt-1 mb-1 text-xs text-slate-400">
        登录用「账号」，不是昵称：账号是你注册时自己设置的登录名
      </p>
      <el-form-item label="密码">
        <el-input v-model="authForm.password" type="password" show-password placeholder="至少 8 位" />
      </el-form-item>
      <el-form-item v-if="authMode === 'register'" label="确认密码">
        <el-input v-model="authForm.confirm_password" type="password" show-password />
      </el-form-item>
      <el-form-item v-if="authMode === 'register'" label="校区">
        <el-select v-model="authForm.school_id" class="w-full" placeholder="请选择校区">
          <el-option v-for="school in schoolStore.schools" :key="school.id" :label="school.name" :value="school.id" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="authMode === 'register'" label="QQ 号（选填）">
        <el-input v-model="authForm.qq" placeholder="仅用于找回账号，可在设置中修改" />
        <div class="text-xs text-gray-400 mt-1">不填写账号丢失将无法找回</div>
      </el-form-item>
      <el-form-item v-if="authMode === 'register'" label="邀请码（选填）">
        <el-input v-model="authForm.invite_code" placeholder="有邀请码填写后直接解锁全部功能" />
        <div class="text-xs text-gray-400 mt-1">没有邀请码可先注册，后续在设置中补填</div>
      </el-form-item>
      <el-checkbox v-if="authMode === 'register'" v-model="authForm.agreed">
        阅读并同意
        <a href="/agreement" target="_blank" rel="noopener" class="text-ly-green" @click.stop>《社区协议》</a>
      </el-checkbox>
    </el-form>
    <template #footer>
      <el-button text @click="authMode = authMode === 'login' ? 'register' : 'login'">
        {{ authMode === 'login' ? '去注册' : '去登录' }}
      </el-button>
      <el-button type="primary" :loading="submitting" @click="submit">
        {{ authMode === 'login' ? '登录' : '注册' }}
      </el-button>
    </template>
  </el-dialog>
</template>
