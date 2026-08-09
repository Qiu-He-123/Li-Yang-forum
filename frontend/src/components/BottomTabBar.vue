<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { Icon } from './native'
import { useSessionStore } from '../stores/session'
import { useNotificationStore } from '../stores/notification'
import { useUIStore } from '../stores/ui'

/**
 * 底部 TabBar（Apple HIG 风格改造）。
 * - 桌面端浮动药丸（max-width 460px，毛玻璃 + 26px 圆角）
 * - 移动端全宽贴底
 * - 5 个 Tab：首页 / 圈子 / 发布（凸起） / 消息 / 我的
 */
const router = useRouter()
const route = useRoute()
const session = useSessionStore()
const notificationStore = useNotificationStore()
const uiStore = useUIStore()

interface TabItem {
  key: string
  label: string
  icon: string
  to?: string
  requiresAuth?: boolean
  badge?: () => number
}

// tabs 必须是 computed：「我的」tab 的 to 依赖 session.userId，
// 若用静态数组，组件初始化时 userId 可能为 null（validateSession 未完成），
// 导致 to 永远是 '/'，点击「我的」跳到首页。
const tabs = computed<TabItem[]>(() => [
  { key: 'home', label: '首页', icon: 'home', to: '/' },
  { key: 'discover', label: '圈子', icon: 'map-pin', to: '/circles' },
  { key: 'create', label: '发布', icon: 'pen-line', to: '/post/create', requiresAuth: true },
  {
    key: 'notifications',
    label: '消息',
    icon: 'message-circle',
    to: '/notifications',
    requiresAuth: true,
    badge: () => notificationStore.unreadCount,
  },
  {
    key: 'me',
    label: session.userId ? '我的' : '登录',
    icon: session.userId ? 'user' : 'log-in',
    to: session.userId ? `/user/${session.userId}` : '/',
    requiresAuth: true,
  },
])

function activeKey(): string {
  const path = route.path
  if (path === '/') return 'home'
  if (path === '/circles') return 'discover'
  if (path === '/post/create') return 'create'
  if (path === '/notifications') return 'notifications'
  if (path.startsWith('/user/')) return 'me'
  if (path.startsWith('/circle/')) return 'discover'
  return ''
}

const activeTab = computed(() => activeKey())

function onClick(tab: TabItem) {
  if (tab.requiresAuth && !session.userId) {
    uiStore.openAuthDialog()
    return
  }
  if (tab.to) {
    // 在圈子详情页点击「发布」时，自动带上当前圈子 slug
    if (tab.key === 'create') {
      const circleMatch = route.path.match(/^\/circle\/([^/]+)/)
      if (circleMatch) {
        router.push({ path: tab.to, query: { circle: circleMatch[1] } })
        return
      }
    }
    router.push(tab.to)
  }
}
</script>

<template>
  <nav class="bottom-tabbar" aria-label="底部导航">
    <button
      v-for="tab in tabs"
      :key="tab.key"
      class="bottom-tab"
      :class="{
        'is-active': activeTab === tab.key,
        'bottom-tab--publish': tab.key === 'create',
      }"
      @click="onClick(tab)"
    >
      <template v-if="tab.key === 'create'">
        <span class="publish-btn">
          <Icon name="pen-line" :size="22" />
        </span>
      </template>
      <template v-else>
        <span class="tab-icon-wrap">
          <Icon :name="tab.icon" :size="22" />
          <span
            v-if="tab.badge && tab.badge() > 0"
            class="tab-badge"
          >{{ tab.badge() > 99 ? '99+' : tab.badge() }}</span>
        </span>
        <span class="bottom-tab-label">{{ tab.label }}</span>
      </template>
    </button>
  </nav>
</template>

<style scoped>
.bottom-tabbar {
  display: flex;
  position: fixed;
  bottom: 14px;
  left: 0;
  right: 0;
  z-index: 100;
  max-width: 460px;
  margin: 0 auto;
  height: 56px;
  padding: 0 10px;
  background: color-mix(in srgb, var(--bg-50) 88%, transparent);
  -webkit-backdrop-filter: blur(20px);
  backdrop-filter: blur(20px);
  border: 0.5px solid var(--bg-300);
  border-radius: 26px;
  box-shadow: var(--shadow-lg);
  align-items: stretch;
  justify-content: space-around;
}
.bottom-tab {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  flex: 1;
  color: var(--text-400);
  background: transparent;
  border: none;
  cursor: pointer;
  min-width: 0;
  transition: color 0.15s cubic-bezier(0.32, 0.72, 0, 1);
}
.bottom-tab.is-active {
  color: var(--brand-500);
}
.tab-icon-wrap {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.bottom-tab-label {
  font-size: 10px;
  line-height: 1;
  white-space: nowrap;
}
.tab-badge {
  position: absolute;
  top: -6px;
  right: -10px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  background: #ff3b30;
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  line-height: 16px;
  text-align: center;
  border-radius: 8px;
  border: 1.5px solid #fff;
  box-shadow: 0 1px 3px rgba(255, 59, 48, 0.4);
  white-space: nowrap;
}

/* 凸起发布按钮 */
.bottom-tab--publish {
  position: relative;
}
.publish-btn {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: var(--brand-500);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: -16px;
  box-shadow: var(--shadow-md);
  transition: transform 0.15s cubic-bezier(0.32, 0.72, 0, 1);
}
.bottom-tab--publish:active .publish-btn {
  transform: scale(0.94);
}

@media (max-width: 768px) {
  .bottom-tabbar {
    max-width: 100%;
    bottom: 0;
    border-radius: 0;
    border-left: none;
    border-right: none;
    border-bottom: none;
    height: calc(52px + env(safe-area-inset-bottom));
    padding-bottom: env(safe-area-inset-bottom);
  }
  .publish-btn {
    width: 42px;
    height: 42px;
    margin-top: -14px;
  }
}
</style>
