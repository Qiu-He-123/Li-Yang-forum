<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { applyInviteCode } from '../../api/auth'
import { useSessionStore } from '../../stores/session'

interface Props {
  modelValue: boolean
}
const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'verified'): void
}>()

const session = useSessionStore()

// ============ 邀请码模式 ============
const inviteCode = ref('')
const submitting = ref(false)

// 弹窗打开时重置
watch(
  () => props.modelValue,
  (visible) => {
    if (visible) {
      inviteCode.value = ''
    }
  },
)

async function submit() {
  if (!inviteCode.value.trim()) {
    ElMessage.error('请输入邀请码')
    return
  }
  submitting.value = true
  try {
    const { data } = await applyInviteCode({ code: inviteCode.value.trim() })
    if (data.data.verification_status === 'verified') {
      session.setVerificationStatus('verified')
      ElMessage.success('邀请码验证成功，已解锁全部功能')
      emit('update:modelValue', false)
      emit('verified')
    }
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    submitting.value = false
  }
}

function copyWechat() {
  navigator.clipboard.writeText('qhsqq2623655749').then(() => {
    ElMessage.success('管理员微信号已复制')
  }).catch(() => {
    ElMessage.info('管理员微信号：qhsqq2623655749')
  })
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="需要邀请码才能使用此功能"
    width="90%"
    style="max-width: 500px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="space-y-4">
      <!-- 提示信息 -->
      <el-alert type="info" :closable="false" show-icon>
        <template #title>
          发帖 / 评论 / 随机匹配 / 漂流瓶 需要邀请码解锁
        </template>
        <div class="text-sm mt-1">
          你已注册成功，可以正常浏览帖子内容。如需发布内容或参与互动，请通过下方方式获取邀请码。
        </div>
      </el-alert>

      <!-- 邀请码输入 -->
      <el-form label-position="top">
        <el-form-item label="邀请码">
          <el-input
            v-model="inviteCode"
            placeholder="请输入邀请码"
            maxlength="16"
            class="uppercase"
            @keyup.enter="submit"
          />
        </el-form-item>
      </el-form>

      <el-divider content-position="left">如何获取邀请码</el-divider>

      <div class="space-y-3 text-sm">
        <!-- 方式 1：找已认证的同学 -->
        <div class="p-3 bg-gray-50 rounded">
          <div class="font-medium text-gray-700 mb-1">方式一：找已认证的同学</div>
          <div class="text-gray-500">
            请身边已认证的同学在他的「设置 → 我的邀请码」中查看邀请码并分享给你。
            每位同学 3 天只能分享 1 次，请珍惜使用。
          </div>
        </div>

        <!-- 方式 2：联系管理员 -->
        <div class="p-3 bg-gray-50 rounded">
          <div class="font-medium text-gray-700 mb-1">方式二：添加管理员微信获取邀请码</div>
          <div class="text-gray-500 mb-2">
            添加管理员微信，说明身份后获取专属邀请码：
          </div>
          <div class="flex items-center gap-2">
            <el-tag type="success" size="large">微信号：qhsqq2623655749</el-tag>
            <el-button size="small" @click="copyWechat">复制</el-button>
          </div>
        </div>
      </div>

      <!-- 连坐提示 -->
      <el-alert type="warning" :closable="false" show-icon>
        <template #title>邀请码连坐机制</template>
        <div class="text-xs mt-1">
          邀请人需对被邀请人身份负责。若被邀请人被核实非本校学生，邀请人将
          被冻结 30 天分享资格。请勿将邀请码出售或分享给校外人员。
        </div>
      </el-alert>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">稍后再说</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        @click="submit"
      >
        解锁功能
      </el-button>
    </template>
  </el-dialog>
</template>
