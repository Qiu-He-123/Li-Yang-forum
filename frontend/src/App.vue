<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'

import BottomTabBar from './components/BottomTabBar.vue'
import { useSessionStore } from './stores/session'
import { useNotificationStore } from './stores/notification'
import { useUIStore } from './stores/ui'
import { connectWs, wsClient } from './utils/ws'
import { recordVisit } from './api/announcement'

// 弹窗类组件改为异步加载：避免 element-plus 被打入首屏主 chunk（EP ~400KB）
// 用户点击登录/收到邀请码提示/查看公告时才发起 chunk 下载，首屏只加载原生组件
const AuthDialog = defineAsyncComponent(() => import('./components/auth/AuthDialog.vue'))
const InviteCodeDialog = defineAsyncComponent(() => import('./components/auth/InviteCodeDialog.vue'))
const AnnouncementPopup = defineAsyncComponent(() => import('./components/AnnouncementPopup.vue'))

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

/**
 * Keep-alive 缓存的视图组件名列表。
 * 与各视图文件中的 defineOptions({ name }) 一致。
 * 仅缓存底部 5 个主 Tab 对应的视图，避免页面切换时重复加载：
 * - HomeView（首页）
 * - CircleDiscoverView（圈子）
 * - NotificationsView（消息）
 * - UserHomeView（我的）
 * 切换 Tab 时组件实例 + 滚动位置 + 已加载数据全部保留，
 * 配合各视图 onActivated 中的 SWR 静默刷新实现"即时展示 + 后台更新"。
 */
const cachedViewNames = ['HomeView', 'CircleDiscoverView', 'NotificationsView', 'UserHomeView']

/**
 * 移除 index.html 中的启动预加载遮罩（#app-preloader）。
 * 加 is-hidden 触发淡出动画，300ms 后彻底从 DOM 移除。
 * 若 Vue 挂载前用户已离开页面（preloader 不存在），静默忽略。
 */
function removeAppPreloader() {
  const preloader = document.getElementById('app-preloader')
  if (!preloader) return
  preloader.classList.add('is-hidden')
  // 淡出动画结束后移除节点（transition-duration: 0.3s）
  window.setTimeout(() => {
    const el = document.getElementById('app-preloader')
    if (el && el.parentNode) {
      el.parentNode.removeChild(el)
    }
  }, 400)
  // 兜底：5s 后强制移除，防止任何异常导致遮罩残留
  window.setTimeout(() => {
    const el = document.getElementById('app-preloader')
    if (el && el.parentNode) {
      el.parentNode.removeChild(el)
    }
  }, 5000)
}

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
  // 网站访问统计：每次打开站点上报一次（后台数据看板统计访问次数 / 独立 IP）
  recordVisit().catch(() => {})
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

  // Bug 修复：移除启动预加载遮罩。
  // 等 session 校验 + 通知初始化完成后再移除，确保用户看到的是已就绪的页面，
  // 避免路由组件 onMounted 异步加载期间闪现"帖子已删除"等错误状态。
  removeAppPreloader()
})
onUnmounted(() => {
  if (banCheckTimer) clearInterval(banCheckTimer)
  notificationStore.stopPolling()
  if (wsNotificationUnsubscribe) wsNotificationUnsubscribe()
  wsClient.disconnect()
})
</script>

<template>
  <RouterView v-slot="{ Component }">
    <KeepAlive :include="cachedViewNames">
      <component :is="Component" />
    </KeepAlive>
  </RouterView>
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
    <!-- skeleton 页面（首页/圈子/消息）不显示全屏遮罩，让组件内骨架屏可见 -->
    <div v-if="uiStore.globalLoadingVisible && route.meta.skeleton !== true" class="global-loading-overlay" aria-live="polite" aria-busy="true">
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
