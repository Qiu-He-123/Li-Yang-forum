<script setup lang="ts">
/**
 * 通知列表页：按类型过滤展示通知
 *
 * 路由：/notifications/:type（type ∈ comment|like|follow|system|announcement|mention）
 * - 顶部标题随类型变化
 * - 列表项点击后标记已读，并跳转到对应帖子/用户
 * - 顶部「全部已读」按钮
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import EmptyState from '../components/common/EmptyState.vue'
import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import { listNotifications, markAllNotificationsRead, markNotificationRead } from '../api/notification'
import { useNotificationStore } from '../stores/notification'
import type { NotificationItem } from '../types/api'

const route = useRoute()
const router = useRouter()
const notificationStore = useNotificationStore()

type NotifType = 'comment' | 'like' | 'follow' | 'system' | 'announcement' | 'interaction' | 'mention'

const typeMeta: Record<NotifType, { title: string; icon: string; color: string }> = {
  comment: { title: '评论', icon: 'message-circle', color: '#007aff' },
  like: { title: '点赞', icon: 'heart', color: '#ff3b30' },
  follow: { title: '粉丝', icon: 'user-plus', color: '#34c759' },
  system: { title: '系统消息', icon: 'bell', color: '#5856d6' },
  announcement: { title: '公告', icon: 'megaphone', color: '#ff9500' },
  interaction: { title: '互动', icon: 'sparkles', color: '#00c7be' },
  mention: { title: '@我的', icon: 'at', color: '#ff9500' },
}

const currentType = computed<NotifType>(() => route.params.type as NotifType)
const meta = computed(() => typeMeta[currentType.value] || typeMeta.system)

const items = ref<NotificationItem[]>([])
const loading = ref(false)
const page = ref(1)
const total = ref(0)
const pageSize = 20

async function loadList() {
  loading.value = true
  try {
    const { data } = await listNotifications(currentType.value, page.value, pageSize)
    items.value = data.data.items || []
    total.value = data.data.total || 0
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

/** 进入列表页即清除该分类的未读红点：标记该类型全部已读并刷新 store。 */
async function clearUnreadDot() {
  try {
    await markAllNotificationsRead(currentType.value)
    notificationStore.refreshUnread()
  } catch {
    /* 静默失败，不影响列表展示 */
  }
}

async function onReadAll() {
  try {
    await markAllNotificationsRead(currentType.value)
    items.value = items.value.map((n) => ({ ...n, is_read: true }))
    notificationStore.refreshUnread()
    toast.success('已全部标记为已读')
  } catch (err) {
    toast.error((err as Error).message)
  }
}

async function onItemClick(item: NotificationItem) {
  // 标记已读
  if (!item.is_read) {
    try {
      await markNotificationRead(item.id)
      item.is_read = true
      notificationStore.refreshUnread()
    } catch {
      /* ignore */
    }
  }
  // 系统消息/公告 → 跳到通知详情页（展示原文 + 跳到原帖按钮）
  if (item.type === 'system' || item.type === 'announcement') {
    router.push(`/notification/${item.id}`)
    return
  }
  // 跳转到引用对象
  if (item.reference_type === 'post' && item.reference_id) {
    router.push(`/post/${item.reference_id}`)
  } else if (item.reference_type === 'user' && item.reference_id) {
    router.push(`/user/${item.reference_id}`)
  } else if (item.reference_type === 'comment' && item.reference_id) {
    // 评论引用的 reference_id 是 comment_id，需要后端补 post_id
    // 暂时跳到评论所在帖子（reference_id 作为 post_id 降级处理）
    router.push(`/post/${item.reference_id}`)
  } else if (item.sender_id && currentType.value === 'follow') {
    router.push(`/user/${item.sender_id}`)
  } else {
    // 兜底：跳到通知详情页
    router.push(`/notification/${item.id}`)
  }
}

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/notifications')
}

function timeAgo(dateStr?: string | null): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const now = new Date()
  const diff = (now.getTime() - d.getTime()) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  if (diff < 604800) return `${Math.floor(diff / 86400)}天前`
  return d.toLocaleDateString()
}

function avatarGradient(id: number | null | undefined): string {
  const idx = (id ?? 0) % 5
  const grads = [
    'linear-gradient(135deg, #66abff, #007aff)',
    'linear-gradient(135deg, #34c759, #2e8dff)',
    'linear-gradient(135deg, #ff9500, #007aff)',
    'linear-gradient(135deg, #5856d6, #0064d6)',
    'linear-gradient(135deg, #d1d1d6, #8e8e93)',
  ]
  return grads[idx]
}

onMounted(async () => {
  // 先加载列表展示，再后台清除该分类未读红点
  await loadList()
  clearUnreadDot()
})

// 切换分类时重新加载并清除该分类红点
watch(currentType, async () => {
  page.value = 1
  await loadList()
  clearUnreadDot()
})
</script>

<template>
  <main class="page-notif-list">
    <!-- 顶部栏 -->
    <header class="list-header">
      <button class="icon-btn" type="button" aria-label="返回" @click="goBack">
        <Icon name="arrow-left" :size="20" />
      </button>
      <h1 class="list-title">{{ meta.title }}</h1>
      <button v-if="items.length" class="read-all-btn" type="button" @click="onReadAll">
        全部已读
      </button>
      <span v-else class="icon-btn-placeholder" />
    </header>

    <div class="page-container">
      <div v-if="loading && !items.length" class="loading-tip">
        <Icon name="refresh" :size="20" />
        <span>加载中…</span>
      </div>

      <div v-else-if="items.length" class="notif-list">
        <div
          v-for="item in items"
          :key="item.id"
          class="notif-item"
          :class="{ 'is-unread': !item.is_read }"
          @click="onItemClick(item)"
        >
          <div
            class="notif-avatar"
            :style="
              item.sender_avatar_url
                ? { backgroundImage: `url(${item.sender_avatar_url})` }
                : { background: avatarGradient(item.sender_id) }
            "
          >
            <span v-if="!item.sender_avatar_url">
              {{ item.sender_nickname?.charAt(0).toUpperCase() || meta.icon === 'bell' ? '系' : 'U' }}
            </span>
          </div>
          <div class="notif-info">
            <div class="notif-row1">
              <span class="notif-name">{{ item.sender_nickname || meta.title }}</span>
              <span class="notif-time">{{ timeAgo(item.created_at) }}</span>
            </div>
            <p class="notif-content">{{ item.content }}</p>
          </div>
          <span v-if="!item.is_read" class="unread-dot" />
        </div>
      </div>

      <EmptyState v-else :icon="meta.icon" :text="`暂无${meta.title}消息`" />
    </div>
  </main>
</template>

<style scoped>
.page-notif-list {
  min-height: 100vh;
  background: var(--bg-100);
  padding-bottom: calc(80px + env(safe-area-inset-bottom));
}

.list-header {
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
.list-title {
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
.read-all-btn {
  font-size: 13px;
  color: var(--brand-500);
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 6px;
  font-weight: 500;
}
.read-all-btn:hover {
  background: var(--brand-50);
}

.page-container {
  max-width: 720px;
  margin: 0 auto;
  padding: 8px 0 0;
}

.loading-tip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 0;
  color: var(--text-500);
  font-size: 13px;
}

.notif-list {
  background: var(--bg-50);
  margin: 8px 16px 0;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  overflow: hidden;
}
.notif-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 0.5px solid var(--bg-200);
  cursor: pointer;
  transition: background 0.15s;
  position: relative;
}
.notif-item:last-child {
  border-bottom: none;
}
.notif-item:hover {
  background: var(--bg-100);
}
.notif-item.is-unread {
  background: rgba(0, 122, 255, 0.03);
}
.notif-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  color: #fff;
  display: grid;
  place-items: center;
  font-size: 15px;
  font-weight: 700;
  flex-shrink: 0;
  background-size: cover;
  background-position: center;
}
.notif-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.notif-row1 {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.notif-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-800);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.notif-time {
  font-size: 11px;
  color: var(--text-400);
  flex-shrink: 0;
}
.notif-content {
  font-size: 13px;
  color: var(--text-500);
  line-height: 1.5;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.unread-dot {
  position: absolute;
  top: 18px;
  right: 12px;
  width: 8px;
  height: 8px;
  background: #ff3b30;
  border-radius: 50%;
  flex-shrink: 0;
}

@media (max-width: 768px) {
  .list-header {
    height: 48px;
    padding: 0 12px;
    padding-top: env(safe-area-inset-top);
  }
  .notif-list {
    margin: 8px 12px 0;
  }
  .notif-item {
    padding: 12px 14px;
  }
}
</style>
