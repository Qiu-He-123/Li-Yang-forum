<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'

import AuthDialog from './components/auth/AuthDialog.vue'
import InviteCodeDialog from './components/auth/InviteCodeDialog.vue'
import BottomTabBar from './components/BottomTabBar.vue'
import AnnouncementPopup from './components/AnnouncementPopup.vue'
import { useSessionStore } from './stores/session'
import { useNotificationStore } from './stores/notification'
import { useUIStore } from './stores/ui'
import { connectWs, wsClient } from './utils/ws'

/**
 * 全局根组件（P1-10 改造后）。
 * - 全局挂载 AuthDialog，由 uiStore 控制显隐，任何位置都能触发登录弹窗
 * - 全局挂载 BottomTabBar，作为移动端主导航；管理端 /admin* 路由下隐藏
 * - 全局管理通知未读数轮询 + 封号实时检测（不依赖 AppHeader 是否挂载）
 * - 全局建立 WebSocket 连接（登录用户 + 游客），用于在线人数统计和实时消息
 */
const route = useRoute()
const uiStore = useUIStore()
const session = useSessionStore()
const notificationStore = useNotificationStore()
let wsNotificationUnsubscribe: (() => void) | null = null

// 管理端不显示底部 TabBar；聊天页全屏沉浸式，也不显示
const showTabBar = computed(() =>
  !route.path.startsWith('/admin') && !route.path.startsWith('/chat/'),
)

// 路由切换时关闭可能残留的登录/邀请码弹窗（避免停留在错误页面）；同时刷新通知未读数
// 封号用户不刷新未读数：/notifications/unread-count 虽已改为 allow_banned，
// 但封号页无需展示消息红点，避免无谓请求
watch(
  () => route.path,
  () => {
    if (uiStore.authDialogVisible) uiStore.closeAuthDialog()
    if (uiStore.inviteCodeDialogVisible) uiStore.closeInviteCodeDialog()
    if (session.userId && !session.isBanned) notificationStore.refreshUnread()
  },
)

// 登录态变化时启停通知轮询
watch(
  () => session.userId,
  (newId) => {
    if (newId && !session.isBanned) {
      notificationStore.refreshUnread()
      notificationStore.startPolling()
    } else {
      notificationStore.clear()
      notificationStore.stopPolling()
    }
    // 登录态变化时重连 WebSocket（切换游客/登录用户身份）
    wsClient.disconnect()
    connectWs()
  },
)

// 封号状态变化时启停通知轮询（响应式 isBanned）
watch(() => session.isBanned, (banned) => {
  if (banned) {
    notificationStore.stopPolling()
    notificationStore.clear()
  } else if (session.userId) {
    notificationStore.refreshUnread()
    notificationStore.startPolling()
  }
})

// 封号实时检测：登录态下每 45s 轮询一次会话校验，
// /auth/me 会返回 ban_info，validateSession 据此立即跳转封号提示页。
// 覆盖「被封后一直停留在当前页面不操作」的场景。
const BAN_CHECK_INTERVAL = 45_000
let banCheckTimer: ReturnType<typeof setInterval> | null = null
onMounted(async () => {
  // 通知未读数：登录态下立即拉取 + 启动轮询（全局，不依赖 AppHeader）
  // 封号用户跳过：避免在 /banned 页无意义轮询
  // 挂载时立即验证一次 session（封号/解封实时生效），避免等到 45s 后才触发
  if (session.userId) {
    await session.validateSession()
  }
  if (session.userId && !session.isBanned) {
    notificationStore.refreshUnread()
    notificationStore.startPolling()
  }
  banCheckTimer = setInterval(() => {
    if (session.userId && !session.isBanned) {
      session.validateSession()
    }
  }, BAN_CHECK_INTERVAL)
  // 全局建立 WebSocket 连接（登录用户和游客都连接，用于在线人数统计）
  connectWs()
  wsNotificationUnsubscribe = wsClient.on((message) => {
    if (message.type === 'dm_message' && session.userId && !session.isBanned) {
      notificationStore.refreshUnread()
    }
  })
})
onUnmounted(() => {
  if (banCheckTimer) clearInterval(banCheckTimer)
  notificationStore.stopPolling()
  if (wsNotificationUnsubscribe) wsNotificationUnsubscribe()
  wsClient.disconnect()
})
</script>

<template>
  <RouterView />
  <BottomTabBar v-if="showTabBar" />
  <AuthDialog
    :model-value="uiStore.authDialogVisible"
    @update:model-value="uiStore.authDialogVisible = $event"
  />
  <InviteCodeDialog
    :model-value="uiStore.inviteCodeDialogVisible"
    @update:model-value="uiStore.inviteCodeDialogVisible = $event"
  />
  <AnnouncementPopup />
  <Transition name="global-loading">
    <div v-if="uiStore.globalLoadingVisible" class="global-loading-overlay" aria-live="polite" aria-busy="true">
      <div class="global-loading-card">
        <span class="global-loading-spinner" aria-hidden="true"></span>
        <span class="global-loading-text">加载中…</span>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.global-loading-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(247, 247, 250, 0.72);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}
.global-loading-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  min-width: 132px;
  padding: 24px 28px;
  border: 1px solid rgba(229, 229, 234, 0.9);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: var(--shadow-xl);
}
.global-loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--bg-300);
  border-top-color: var(--brand-500);
  border-radius: 50%;
  animation: global-loading-spin 0.8s linear infinite;
}
.global-loading-text {
  color: var(--text-600);
  font-size: 14px;
  font-weight: 600;
}
.global-loading-enter-active,
.global-loading-leave-active {
  transition: opacity 0.16s var(--ease-apple);
}
.global-loading-enter-from,
.global-loading-leave-to {
  opacity: 0;
}
@keyframes global-loading-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
