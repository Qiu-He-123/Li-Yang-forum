<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { bindWechat, getBindGuide, verifyBindCode, type BindResult } from '../api/wechat'
import { toast } from '../components/native/Toast'

defineOptions({ name: 'BindWechatView' })

const router = useRouter()
const step = ref(1)
const guideId = ref('')
const query = ref('')
const submitting = ref(false)
const bindResult = ref<BindResult | null>(null)
const error = ref('')
const verifying = ref(false)
const verifyMsg = ref('')
const coinReward = ref<number | null>(null)
const verifyHint = ref('')

onMounted(async () => {
  try {
    guideId.value = (await getBindGuide()).data.data.wechat_id || ''
  } catch {
    /* 忽略，进入流程时后端会再次返回 */
  }
})

async function step1Submit() {
  if (!query.value.trim()) {
    toast.info('请输入你的微信号')
    return
  }
  submitting.value = true
  error.value = ''
  try {
    const data = (await bindWechat(query.value.trim())).data.data
    bindResult.value = data
    if (!guideId.value) guideId.value = data.wechat_id
    step.value = 2
  } catch (e: unknown) {
    const err = e as { response?: { data?: { msg?: string } } }
    error.value = err.response?.data?.msg || '绑定失败，请重试'
  } finally {
    submitting.value = false
  }
}

function startVerify() {
  verifying.value = true
  verifyMsg.value = ''
  verifyHint.value = '正在检测验证码消息，请确认已在微信里发送…'
  pollVerify(0)
}

async function pollVerify(tryCount: number) {
  if (tryCount >= 12) {
    verifying.value = false
    verifyHint.value = ''
    verifyMsg.value = '仍未检测到验证码消息，请确认已把验证码发给社区微信号，然后重新验证'
    return
  }
  try {
    const data = (await verifyBindCode(bindResult.value!.verify_code)).data.data
    if (data.matched) {
      verifying.value = false
      verifyHint.value = ''
      coinReward.value = data.coins ?? null
      step.value = 3
      return
    }
    // 收到了消息但验证码发错了：停止轮询，直接提示，不用继续傻等
    if (data.wrong_code) {
      verifying.value = false
      verifyHint.value = ''
      verifyMsg.value = data.reason || '验证码发错了，请核对后重新发送'
      return
    }
    // 检测中不展示红字，只用灰色提示；每 0.8 秒查一次，约 10 秒内完成
    verifyHint.value = `正在检测验证码消息（${tryCount + 1}/12），请确认已在微信里发送…`
    setTimeout(() => pollVerify(tryCount + 1), 800)
  } catch (e: unknown) {
    const err = e as { response?: { data?: { msg?: string } } }
    verifyHint.value = ''
    verifyMsg.value = err.response?.data?.msg || '校验失败，请重试'
    verifying.value = false
  }
}
</script>

<template>
  <div class="page">
    <header class="page-header">
      <button type="button" class="back-btn" @click="router.back()">←</button>
      <h1>绑定微信</h1>
    </header>

    <!-- 第 1 步：加好友 + 输入微信号 -->
    <section v-if="step === 1" class="card">
      <h2>第 1 步 · 添加社区微信</h2>
      <p class="tip">请先在微信中搜索并添加社区微信号为好友：</p>
      <p class="guide-id">{{ guideId || '（后台未配置社区微信号）' }}</p>
      <p class="tip">添加成功后，在下方输入你自己的微信号：</p>
      <input v-model="query" type="text" class="input" placeholder="输入你的微信号" maxlength="64" />
      <p v-if="error" class="error">{{ error }}</p>
      <button type="button" class="btn-primary wechat-bind-next" :disabled="submitting" @click="step1Submit">
        {{ submitting ? '确认中…' : '下一步' }}
      </button>
      <p class="mini">需先填写邀请码（已认证）才能绑定微信</p>
    </section>

    <!-- 第 2 步：发送验证码 -->
    <section v-else-if="step === 2" class="card">
      <h2>第 2 步 · 发送验证码</h2>
      <p class="tip">请在微信里，把下面的验证码发给社区微信号 <b>{{ guideId }}</b>：</p>
      <p class="code">{{ bindResult?.verify_code }}</p>
      <p class="mini">发完消息后点下方按钮，系统会自动检测是否收到</p>
      <button type="button" class="btn-primary" :disabled="verifying" @click="startVerify">
        {{ verifying ? '检测中…' : '我已发送，验证' }}
      </button>
      <p v-if="verifyHint" class="hint">{{ verifyHint }}</p>
      <p v-if="verifyMsg" class="error">{{ verifyMsg }}</p>
    </section>

    <!-- 第 3 步：绑定成功 -->
    <section v-else class="card">
      <h2>绑定成功</h2>
      <p class="ok">✓ 已绑定 {{ bindResult?.nickname }}（{{ bindResult?.wxid }}）</p>
      <p v-if="coinReward !== null" class="ok">获得 {{ coinReward }} 金币奖励</p>
      <div class="btn-row">
        <button type="button" class="btn-ghost" @click="router.back()">退出</button>
        <button type="button" class="btn-primary" @click="router.push('/wechat/publish')">选择朋友圈发布</button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.page {
  max-width: 720px;
  margin: 0 auto;
  padding: 0 14px 60px;
  min-height: 100vh;
}
.page-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 0;
}
.page-header h1 {
  font-size: 17px;
  margin: 0;
}
.back-btn {
  border: none;
  background: transparent;
  font-size: 20px;
  cursor: pointer;
  padding: 0 4px;
}
.card {
  background: #fff;
  border-radius: 12px;
  padding: 18px;
  margin-top: 10px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
}
.card h2 {
  font-size: 16px;
  margin: 0 0 12px;
}
.tip {
  font-size: 13px;
  color: var(--text-600, #555);
  margin: 8px 0;
  line-height: 1.7;
}
.guide-id {
  font-size: 16px;
  font-weight: 700;
  color: #1a3d7c;
  background: var(--bg-app, #f6f7f9);
  border-radius: 8px;
  padding: 10px;
  text-align: center;
}
.code {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: 3px;
  text-align: center;
  color: #1a3d7c;
  background: var(--bg-app, #f6f7f9);
  border-radius: 8px;
  padding: 14px;
  margin: 12px 0;
}
.input {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 14px;
  margin: 4px 0 10px;
}
.btn-primary {
  width: 100%;
  border: none;
  background: #4f9cff;
  color: #fff;
  border-radius: 8px;
  padding: 10px;
  font-size: 14px;
  cursor: pointer;
  margin-top: 8px;
}
.btn-primary:disabled {
  opacity: 0.6;
}
.btn-ghost {
  border: 1px solid #ddd;
  background: #fff;
  color: var(--text-600, #555);
  border-radius: 8px;
  padding: 10px 16px;
  font-size: 14px;
  cursor: pointer;
}
.btn-row {
  display: flex;
  gap: 10px;
  margin-top: 14px;
}
.btn-row .btn-primary {
  flex: 1;
  margin-top: 0;
}
.error {
  color: #c62828;
  font-size: 12px;
  margin: 8px 0 0;
}
.hint {
  color: var(--text-400, #999);
  font-size: 12px;
  margin: 8px 0 0;
  line-height: 1.6;
}
.ok {
  color: #2e7d32;
  font-size: 14px;
  margin: 8px 0;
}
.mini {
  font-size: 11px;
  color: var(--text-400, #999);
  margin: 10px 0 0;
}
</style>
