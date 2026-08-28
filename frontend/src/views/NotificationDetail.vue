<script setup lang="ts">
/**
 * 通知详情页
 *
 * - 展示通知标题、内容原文、时间
 * - 下方提供「跳到原帖」按钮（若有 post_id）
 * - 进入页面自动标记已读
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import EmptyState from '../components/common/EmptyState.vue'
import { Dialog as NativeDialog, Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import {
  fetchNotificationDetail,
  markNotificationRead,
  type NotificationDetail,
} from '../api/notification'
import { claimBadge } from '../api/badge'
import { useNotificationStore } from '../stores/notification'

const route = useRoute()
const router = useRouter()
const notificationStore = useNotificationStore()

const detail = ref<NotificationDetail | null>(null)
const loading = ref(false)

// 徽章领取（系统消息详情内）
const claimDialogVisible = ref(false)
const claimCode = ref('')
const claiming = ref(false)

function openClaim() {
  claimCode.value = ''
  claimDialogVisible.value = true
}

async function submitClaim() {
  const code = claimCode.value.trim()
  if (!code) {
    toast.error('请输入激活码')
    return
  }
  claiming.value = true
  try {
    const { data } = await claimBadge(code)
    toast.success(`已获得「${data.data.icon} ${data.data.name}」徽章！`)
    claimDialogVisible.value = false
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    claiming.value = false
  }
}

const typeMeta: Record<string, { label: string; icon: string; color: string }> = {
  comment: { label: '评论', icon: 'message-circle', color: '#007aff' },
  like: { label: '点赞', icon: 'heart', color: '#ff3b30' },
  follow: { label: '关注', icon: 'user-plus', color: '#34c759' },
  system: { label: '系统消息', icon: 'bell', color: '#5856d6' },
  announcement: { label: '公告', icon: 'megaphone', color: '#ff9500' },
  interaction: { label: '互动', icon: 'sparkles', color: '#00c7be' },
  mention: { label: '@我', icon: 'at', color: '#ff9500' },
}

const meta = computed(() => (detail.value ? typeMeta[detail.value.type] || typeMeta.system : typeMeta.system))

async function load() {
  const id = Number(route.params.id)
  if (!id) {
    toast.error('通知 ID 无效')
    return
  }
  loading.value = true
  try {
    const { data } = await fetchNotificationDetail(id)
    detail.value = data.data
    // 自动标记已读
    if (!data.data.is_read) {
      try {
        await markNotificationRead(id)
        notificationStore.refreshUnread()
      } catch {
        /* ignore */
      }
    }
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

function goPost() {
  if (detail.value?.post_id) {
    router.push(`/post/${detail.value.post_id}`)
  }
}

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/notifications')
}

function fmtTime(t: string | null | undefined): string {
  if (!t) return ''
  return t.replace('T', ' ').slice(0, 19)
}

onMounted(load)
</script>

<template>
  <main class="page-notif-detail">
    <header class="detail-header">
      <button class="icon-btn" type="button" aria-label="返回" @click="goBack">
        <Icon name="arrow-left" :size="20" />
      </button>
      <h1 class="detail-title">消息详情</h1>
      <span class="icon-btn-placeholder" />
    </header>

    <div class="page-container">
      <div v-if="loading" class="loading-tip">
        <Icon name="refresh" :size="20" />
        <span>加载中…</span>
      </div>

      <article v-else-if="detail" class="notif-detail-card">
        <div class="detail-type-row">
          <span class="detail-type-badge" :style="{ background: meta.color }">
            <Icon :name="meta.icon" :size="14" />
            <span>{{ meta.label }}</span>
          </span>
          <span class="detail-time">{{ fmtTime(detail.created_at) }}</span>
        </div>

        <h2 class="detail-subject">{{ detail.title }}</h2>

        <div class="detail-content">
          {{ detail.content }}
        </div>

        <div v-if="detail.post_id" class="detail-action">
          <button class="btn btn-primary btn-pill" type="button" @click="goPost">
            <Icon name="external-link" :size="14" />
            跳到原帖
          </button>
        </div>
        <div v-if="detail.type === 'system'" class="detail-action">
          <button class="btn btn-primary btn-pill btn-gold" type="button" @click="openClaim">
            <Icon name="gift" :size="14" />
            领取徽章
          </button>
          <p class="claim-hint">输入管理员发放的激活码即可领取徽章</p>
        </div>
      </article>

      <EmptyState v-else icon="bell" text="通知不存在或已被删除" />
    </div>

    <!-- 领取徽章弹窗 -->
    <NativeDialog v-model="claimDialogVisible" title="领取徽章" width="420px">
      <p class="claim-tip">请输入管理员发放的激活码，领取后可前往「我的 → 我的徽章」选择佩戴。</p>
      <input
        v-model="claimCode"
        class="claim-input"
        type="text"
        maxlength="32"
        placeholder="请输入激活码"
        @keydown.enter="submitClaim"
      />
      <template #footer>
        <button class="btn btn-outline" type="button" @click="claimDialogVisible = false">取消</button>
        <button class="btn btn-primary" type="button" :disabled="claiming" @click="submitClaim">
          {{ claiming ? '领取中…' : '领取' }}
        </button>
      </template>
    </NativeDialog>
  </main>
</template>

<style scoped>
.page-notif-detail {
  min-height: 100vh;
  background: var(--bg-100);
  padding-bottom: calc(80px + env(safe-area-inset-bottom));
}

.detail-header {
  position: sticky;
  top: 0;
  z-index: 50;
  background: rgba(255, 255, 255, 0.95);
  -webkit-backdrop-filter: blur(20px);
  backdrop-filter: blur(20px);
  border-bottom: 0.5px solid var(--bg-300);
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  padding-top: env(safe-area-inset-top);
}
.detail-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-800);
  margin: 0;
  flex: 1;
  text-align: center;
}
.icon-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: transparent;
  cursor: pointer;
  display: grid;
  place-items: center;
  color: var(--text-600);
  transition: background 0.15s;
}
.icon-btn:hover {
  background: var(--bg-100);
}
.icon-btn-placeholder {
  width: 36px;
  height: 36px;
  display: inline-block;
}

.page-container {
  max-width: 720px;
  margin: 0 auto;
  padding: 16px;
}

.loading-tip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 48px 0;
  color: var(--text-500);
  font-size: 13px;
}

.notif-detail-card {
  background: #fff;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  padding: 20px;
}

.detail-type-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.detail-type-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 999px;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}
.detail-time {
  font-size: 12px;
  color: var(--text-400);
}

.detail-subject {
  margin: 0 0 12px;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-900);
  line-height: 1.4;
}

.detail-content {
  font-size: 15px;
  line-height: 1.7;
  color: var(--text-700);
  white-space: pre-wrap;
  word-break: break-word;
}

.detail-action {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 0.5px solid var(--bg-200);
  display: flex;
  justify-content: flex-end;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  padding: 8px 16px;
  border-radius: 999px;
  border: none;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.15s;
}
.btn:hover {
  opacity: 0.9;
}
.btn:active {
  transform: scale(0.97);
}
.btn-primary {
  background: var(--brand-500, #007aff);
  color: #fff;
}
.btn-gold {
  background: linear-gradient(135deg, #ffd60a, #f7b500);
  color: #fff;
}
.btn-outline {
  background: transparent;
  border: 1px solid var(--bg-300);
  color: var(--text-700);
}
.claim-hint {
  margin: 0;
  width: 100%;
  text-align: right;
  font-size: 12px;
  color: var(--text-400);
}
.claim-tip {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--text-500);
  line-height: 1.6;
}
.claim-input {
  width: 100%;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid var(--color-border, #e5e5ea);
  font-size: 15px;
  font-family: inherit;
  color: var(--text-800);
  outline: none;
  text-transform: uppercase;
  letter-spacing: 1px;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.claim-input:focus {
  border-color: var(--brand-500);
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.15);
}

@media (max-width: 768px) {
  .detail-header {
    height: 48px;
    padding: 0 12px;
    padding-top: env(safe-area-inset-top);
  }
  .page-container {
    padding: 12px;
  }
  .notif-detail-card {
    padding: 16px;
  }
  .detail-subject {
    font-size: 17px;
  }
  .detail-content {
    font-size: 14px;
  }
}
</style>
