<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { getWechatStatus, refreshWechatMoments, setWechatSync, type WechatStatus } from '../api/wechat'
import { toast } from '../components/native/Toast'
import Switch from '../components/native/Switch.vue'

defineOptions({ name: 'SyncPublishView' })

const router = useRouter()
const status = ref<WechatStatus | null>(null)
const refreshing = ref(false)
const loading = ref(true)

async function loadStatus() {
  try {
    status.value = (await getWechatStatus()).data.data
  } finally {
    loading.value = false
  }
}

async function toggleSync(v: boolean) {
  if (!status.value?.bound) return
  try {
    status.value = (await setWechatSync(v)).data.data
    toast.success(v ? '已开启自动同步（只同步开启之后发布的朋友圈）' : '已关闭自动同步')
  } catch {
    toast.error('操作失败')
  }
}

async function refreshNow() {
  refreshing.value = true
  try {
    const res = (await refreshWechatMoments()) as { data?: { data?: { added?: number } } }
    const added = res?.data?.data?.added ?? 0
    toast.success(added ? `已刷新，新增 ${added} 条朋友圈` : '已刷新，暂无新动态')
  } catch {
    toast.error('刷新太频繁，请稍后再试')
  } finally {
    refreshing.value = false
  }
}

onMounted(loadStatus)
</script>

<template>
  <div class="page">
    <header class="page-header">
      <button type="button" class="back-btn" @click="router.back()">←</button>
      <h1>同步发布</h1>
    </header>

    <div v-if="loading" class="empty-tip">加载中…</div>
    <section v-else class="card">
      <div class="row">
        <span class="label">自动同步</span>
        <Switch :model-value="status?.sync_enabled ?? false" @update:model-value="toggleSync" />
      </div>
      <p class="tip">
        开启后，你之后发布的朋友圈会自动同步到社区（只同步开启之后的新动态，历史内容不同步）。
      </p>
      <p class="tip sync-notice">
        ⏱ 自动同步并非实时：朋友圈刷新后，社区约 1 分钟内自动同步发布。
      </p>
      <div class="row">
        <span class="label">已同步</span>
        <span class="value">{{ status?.synced_count ?? 0 }} 条</span>
      </div>
      <button type="button" class="btn-primary" :disabled="refreshing" @click="refreshNow">
        {{ refreshing ? '刷新中…' : '立即检查新动态' }}
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
.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px dashed #f0f0f0;
  font-size: 14px;
}
.row .label {
  color: var(--text-500, #777);
}
.tip {
  font-size: 12px;
  color: var(--text-400, #999);
  line-height: 1.7;
  margin: 12px 0;
}
.sync-notice {
  color: #b26a00;
  background: rgba(178, 106, 0, 0.08);
  border-radius: 8px;
  padding: 8px 10px;
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
.empty-tip {
  text-align: center;
  color: var(--text-400, #999);
  padding: 40px 0;
  font-size: 13px;
}
</style>
