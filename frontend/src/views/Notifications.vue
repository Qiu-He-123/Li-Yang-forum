<script setup lang="ts">
/**
 * 消息中心：
 * - 顶部通知分类入口（评论/点赞/粉丝/系统），有未读则显示红点
 * - 下方私信会话列表（抖音/快手风格）
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import EmptyState from '../components/common/EmptyState.vue'
import { Icon } from '../components/native'
import { listConversations } from '../api/friend'
import { useSessionStore } from '../stores/session'
import { useNotificationStore } from '../stores/notification'

const router = useRouter()
const session = useSessionStore()
const notificationStore = useNotificationStore()

interface Conversation {
  user: {
    id: number
    nickname: string
    avatar_url: string | null
    bio: string | null
    school: string | null
    /** @deprecated 已弃用，改用 age */
    grade: string | null
    age: number | null
  }
  last_message: string | null
  last_time: string | null
  unread_count: number
  is_mutual: boolean
}

const conversations = ref<Conversation[]>([])
const loading = ref(false)

let pollTimer: ReturnType<typeof setInterval> | null = null
// 上一次会话列表的指纹，用于避免无变化时的重渲染（防闪烁）
let lastFingerprint = ''

// 通知分类配置：type → 路由参数 + 图标 + 标签 + 颜色
const notifCategories = computed(() => [
  { type: 'like', icon: 'heart', color: '#ff3b30', label: '点赞', route: '/notifications/like' },
  { type: 'comment', icon: 'message-circle', color: '#007aff', label: '评论', route: '/notifications/comment' },
  { type: 'mention', icon: 'at', color: '#ff9500', label: '@我', route: '/notifications/mention' },
  { type: 'follow', icon: 'user-plus', color: '#34c759', label: '粉丝', route: '/notifications/follow' },
  { type: 'system', icon: 'bell', color: '#5856d6', label: '系统', route: '/notifications/system' },
])

// 某分类未读数：从 notificationStore.byType 读取
function unreadOfType(type: string): number {
  return notificationStore.byType[type] || 0
}

/** 生成会话列表的指纹：仅包含影响 UI 的关键字段 */
function buildFingerprint(list: Conversation[]): string {
  return list
    .map((c) => `${c.user.id}:${c.last_time || ''}:${c.unread_count}:${c.last_message || ''}`)
    .join('|')
}

async function loadConversations(force = false) {
  if (!session.userId) return
  // 首次加载或强制刷新时显示 loading
  if (conversations.value.length === 0) loading.value = true
  try {
    const { data } = await listConversations({
      showGlobalLoading: false,
      showGlobalError: false,
    })
    const next = data.data || []
    const fp = buildFingerprint(next)
    // 仅在指纹变化时更新，避免无变化重渲染导致的闪烁
    if (force || fp !== lastFingerprint) {
      conversations.value = next
      lastFingerprint = fp
    }
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

function openChat(userId: number) {
  router.push(`/chat/${userId}`)
}

function goBack() {
  // 修复：使用 router.back()，如果没有历史则回首页
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/')
  }
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

function startPolling() {
  if (pollTimer) return
  // 15 秒轮询；只在指纹变化时才更新 UI，无变化时不触发重渲染（防闪烁）
  pollTimer = setInterval(() => loadConversations(false), 15000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function onVisibilityChange() {
  // 页面隐藏时暂停轮询，可见时立即刷新并恢复轮询（节流）
  if (document.hidden) {
    stopPolling()
  } else {
    loadConversations(false)
    startPolling()
  }
}

onMounted(async () => {
  const valid = await session.validateSession()
  if (!valid) return
  await loadConversations(true)
  startPolling()
  // 加载通知未读数（按类型分组，用于分类入口红点）
  notificationStore.refreshUnread()
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onUnmounted(() => {
  stopPolling()
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<template>
  <main class="page-msg">
    <!-- 顶部栏 -->
    <header class="msg-header">
      <button class="icon-btn" type="button" aria-label="返回" @click="goBack">
        <Icon name="arrow-left" :size="20" />
      </button>
      <h1 class="msg-title">立洋社区·消息</h1>
      <span class="icon-btn-placeholder" />
    </header>

    <!-- 会话列表 -->
    <div class="page-container">
      <!-- 通知分类入口 -->
      <div class="notif-cats">
        <button
          v-for="cat in notifCategories"
          :key="cat.type"
          class="notif-cat-item"
          type="button"
          @click="router.push(cat.route)"
        >
          <div class="notif-cat-icon" :style="{ background: cat.color }">
            <Icon :name="cat.icon" :size="22" />
            <span v-if="unreadOfType(cat.type) > 0" class="notif-cat-dot" />
          </div>
          <span class="notif-cat-label">{{ cat.label }}</span>
        </button>
      </div>

      <!-- 私信标题 -->
      <div class="section-title">
        <span>私信</span>
      </div>

      <div v-if="loading && !conversations.length" class="loading-tip">
        <Icon name="refresh" :size="20" />
        <span>加载中…</span>
      </div>

      <div v-else-if="conversations.length" class="chat-list">
        <div
          v-for="conv in conversations"
          :key="conv.user.id"
          class="chat-item"
          @click="openChat(conv.user.id)"
        >
          <div
            class="chat-item-avatar"
            :style="
              conv.user.avatar_url
                ? { backgroundImage: `url(${conv.user.avatar_url})` }
                : { background: avatarGradient(conv.user.id) }
            "
          >
            <span v-if="!conv.user.avatar_url">{{ conv.user.nickname.charAt(0).toUpperCase() }}</span>
          </div>
          <div class="chat-item-info">
            <div class="chat-item-row">
              <span class="chat-item-name">
                {{ conv.user.nickname }}
                <span v-if="conv.is_mutual" class="mutual-tag">互关</span>
              </span>
              <span class="chat-item-time">{{ timeAgo(conv.last_time) }}</span>
            </div>
            <div class="chat-item-row2">
              <span class="chat-item-preview">{{ conv.last_message || '开始聊天吧' }}</span>
              <span v-if="conv.unread_count > 0" class="chat-item-badge">{{ conv.unread_count }}</span>
            </div>
          </div>
        </div>
      </div>

      <EmptyState v-else icon="message-circle" text="还没有消息，去认识新朋友吧" />
    </div>
  </main>
</template>

<style scoped>
.page-msg {
  min-height: 100vh;
  background: var(--bg-100);
  padding-bottom: calc(80px + env(safe-area-inset-bottom));
}

/* 顶部 */
.msg-header {
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
}
.msg-title {
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
  color: var(--text-800);
}
.icon-btn-placeholder {
  width: 36px;
  height: 36px;
  display: inline-block;
}

/* 内容区 */
.page-container {
  max-width: 720px;
  margin: 0 auto;
  padding: 8px 0 0;
}

/* 通知分类入口 */
.notif-cats {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;
  padding: 12px 16px;
  background: var(--bg-50);
  margin: 8px 16px 0;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
}
.notif-cat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 8px 4px;
  background: transparent;
  border: none;
  cursor: pointer;
  transition: opacity 0.15s;
}
.notif-cat-item:hover {
  opacity: 0.8;
}
.notif-cat-icon {
  position: relative;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  color: #fff;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.notif-cat-label {
  font-size: 12px;
  color: var(--text-600);
  font-weight: 500;
}
.notif-cat-dot {
  position: absolute;
  top: 0;
  right: 0;
  width: 10px;
  height: 10px;
  background: #ff3b30;
  border-radius: 50%;
  border: 2px solid var(--bg-50);
}

/* 私信分区标题 */
.section-title {
  display: flex;
  align-items: center;
  padding: 16px 20px 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-500);
  letter-spacing: 0.5px;
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

/* 会话列表 */
.chat-list {
  background: var(--bg-50);
  margin: 8px 16px 0;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  overflow: hidden;
}
.chat-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 0.5px solid var(--bg-200);
  cursor: pointer;
  transition: background 0.15s;
}
.chat-item:last-child {
  border-bottom: none;
}
.chat-item:hover {
  background: var(--bg-100);
}
.chat-item-avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  color: #fff;
  display: grid;
  place-items: center;
  font-size: 18px;
  font-weight: 700;
  flex-shrink: 0;
  background-size: cover;
  background-position: center;
  text-transform: uppercase;
}
.chat-item-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.chat-item-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.chat-item-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-800);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.mutual-tag {
  font-size: 10px;
  font-weight: 600;
  color: var(--brand-600);
  background: var(--brand-50);
  padding: 1px 6px;
  border-radius: 999px;
  flex-shrink: 0;
}
.chat-item-time {
  font-size: 11px;
  color: var(--text-400);
  flex-shrink: 0;
}
.chat-item-row2 {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.chat-item-preview {
  font-size: 13px;
  color: var(--text-400);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}
.chat-item-badge {
  background: #ff3b30;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 999px;
  min-width: 18px;
  text-align: center;
  flex-shrink: 0;
}

@media (max-width: 768px) {
  .msg-header {
    height: 48px;
    padding: 0 12px;
  }
  .chat-list {
    margin: 8px 12px 0;
  }
  .chat-item {
    padding: 12px 14px;
  }
  .notif-cats {
    margin: 8px 12px 0;
    padding: 10px 8px;
    gap: 4px;
  }
  .notif-cat-icon {
    width: 44px;
    height: 44px;
  }
  .notif-cat-label {
    font-size: 11px;
  }
}
</style>
