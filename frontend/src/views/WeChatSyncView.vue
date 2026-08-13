<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { getBindGuide, getWechatStatus, unbindWechat, type WechatStatus } from '../api/wechat'
import { useSessionStore } from '../stores/session'
import { toast } from '../components/native/Toast'

defineOptions({ name: 'WeChatSyncView' })

const router = useRouter()
const session = useSessionStore()
const status = ref<WechatStatus | null>(null)
const guideId = ref('')
const loading = ref(true)
const unbinding = ref(false)

onMounted(async () => {
  try {
    status.value = (await getWechatStatus()).data.data
  } catch {
    status.value = null
  } finally {
    loading.value = false
  }
  try {
    guideId.value = (await getBindGuide()).data.data.wechat_id || ''
  } catch {
    /* 忽略 */
  }
})

async function onUnbind() {
  if (!window.confirm('解绑后将关闭自动同步，需要重新绑定微信才能继续同步朋友圈，确定解绑吗？')) return
  unbinding.value = true
  try {
    await unbindWechat()
    toast.success('已解绑，可重新绑定其他微信')
    router.push('/wechat/bind')
  } catch (e: unknown) {
    const err = e as { response?: { data?: { msg?: string } } }
    toast.error(err.response?.data?.msg || '解绑失败，请重试')
  } finally {
    unbinding.value = false
  }
}
</script>

<template>
  <div class="page">
    <header class="page-header">
      <button type="button" class="back-btn" @click="router.back()">←</button>
      <h1>微信朋友圈同步</h1>
    </header>

    <div v-if="loading" class="empty-tip">加载中…</div>

    <!-- 未认证：需先填邀请码 -->
    <section v-else-if="!session.isVerified()" class="card">
      <h2>需要先填写邀请码</h2>
      <p class="tip">绑定微信前需要先填写邀请码完成认证，请在「我的」页填写邀请码后再来。</p>
      <button type="button" class="btn-primary" @click="router.push(`/user/${session.userId}`)">去填写邀请码</button>
    </section>

    <!-- 未绑定：引导 -->
    <section v-else-if="!status?.bound" class="card">
      <h2>绑定微信</h2>
      <p class="tip">
        添加社区微信号 <b>{{ guideId || '（后台未配置）' }}</b> 为好友，
        绑定后可以自动/手动同步微信朋友圈。
      </p>
      <button type="button" class="btn-primary wechat-start-btn" @click="router.push('/wechat/bind')">
        开始绑定
      </button>
    </section>

    <!-- 已绑定：状态 + 发布设置入口 -->
    <section v-else class="card">
      <h2>已绑定</h2>
      <div class="row">
        <span class="label">微信昵称</span>
        <span class="value">{{ status.nickname || '—' }}</span>
      </div>
      <div class="row">
        <span class="label">已同步</span>
        <span class="value">{{ status.synced_count }} 条</span>
      </div>
      <div class="row">
        <span class="label">自动同步</span>
        <span class="value">{{ status.sync_enabled ? '已开启' : '未开启' }}</span>
      </div>
      <button type="button" class="btn-primary" @click="router.push('/wechat/publish')">
        选择朋友圈发布
      </button>
      <button type="button" class="unbind-btn" :disabled="unbinding" @click="onUnbind">
        {{ unbinding ? '解绑中…' : '解绑并重新绑定' }}
      </button>
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
  margin: 0 0 10px;
}
.tip {
  font-size: 13px;
  color: var(--text-600, #555);
  line-height: 1.7;
  margin: 8px 0 12px;
}
.row {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px dashed #f0f0f0;
  font-size: 14px;
}
.row .label {
  color: var(--text-500, #777);
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
  margin-top: 10px;
}
.unbind-btn {
  width: 100%;
  border: 1px solid #ff8a80;
  background: #fff;
  color: #e5484d;
  border-radius: 8px;
  padding: 10px;
  font-size: 14px;
  cursor: pointer;
  margin-top: 8px;
}
.unbind-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.empty-tip {
  text-align: center;
  color: var(--text-400, #999);
  padding: 40px 0;
  font-size: 13px;
}
</style>
