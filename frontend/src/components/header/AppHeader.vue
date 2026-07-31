<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { Icon } from '../native'
import { toast } from '../native/Toast'
import { useSessionStore } from '../../stores/session'
import { useUserStore } from '../../stores/user'
import { useNotificationStore } from '../../stores/notification'
import { useUIStore } from '../../stores/ui'

/**
 * 顶部导航栏（Apple HIG 风格改造）。
 * - 居中标题 / 右侧搜索 + 头像
 * - 桌面端顶部主导航；移动端导航交给 BottomTabBar
 */
const session = useSessionStore()
const userStore = useUserStore()
const notificationStore = useNotificationStore()
const uiStore = useUIStore()
const router = useRouter()
const route = useRoute()

const keyword = ref('')
const menuOpen = ref(false)

const navItems = computed(() => [
  { key: 'home', label: '立洋社区·首页', to: '/', icon: 'home' },
  { key: 'discover', label: '立洋社区·圈子', to: '/circles', icon: 'map-pin' },
  { key: 'create', label: '发布', to: '/post/create', icon: 'pen-line', requiresAuth: true },
  {
    key: 'notifications',
    label: '立洋社区·消息',
    to: '/notifications',
    icon: 'bell',
    requiresAuth: true,
    badge: notificationStore.unreadCount,
  },
  {
    key: 'me',
    label: '立洋社区·我的',
    to: session.userId ? `/user/${session.userId}` : '/',
    icon: 'user',
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
const pageTitle = computed(() => {
  const path = route.path
  if (path === '/') return '立洋社区·首页'
  if (path === '/post/create') return '发帖'
  if (path === '/notifications') return '立洋社区·消息'
  if (path.startsWith('/user/')) return '立洋社区·我的'
  if (path.startsWith('/circle/')) return '立洋社区·圈子'
  if (path === '/search') return '搜索'
  if (path === '/settings') return '设置'
  return '立洋社区'
})

// 通知未读数轮询已提升到 App.vue 全局管理，此处仅读取 store 用于展示。
// 路由切换时收起菜单
watch(
  () => route.path,
  () => {
    menuOpen.value = false
  },
)

function onSearch() {
  const q = keyword.value.trim()
  if (!q) return
  router.push({ path: '/search', query: { q } })
}

function onNavClick(item: typeof navItems.value[number]) {
  if (item.requiresAuth && !session.userId) {
    uiStore.openAuthDialog()
    return
  }
  router.push(item.to)
}

function onUserCommand(command: string) {
  menuOpen.value = false
  if (!session.userId && command !== 'login') {
    uiStore.openAuthDialog()
    return
  }
  if (command === 'profile') router.push(`/user/${session.userId}`)
  else if (command === 'drafts') router.push('/my/drafts')
  else if (command === 'favorites') router.push('/my/favorites')
  else if (command === 'notifications') router.push('/notifications')
  else if (command === 'settings') router.push('/settings')
  else if (command === 'logout') {
    session.logout().then(() => {
      userStore.clearProfile()
      notificationStore.clear()
      toast.success('已登出')
      router.push('/')
    })
  } else if (command === 'login') {
    uiStore.openAuthDialog()
  }
}
</script>

<template>
  <header class="site-header">
    <div class="header-inner">
      <!-- 左：品牌 / 移动端返回 -->
      <div class="header-side header-side--left" @click="router.push('/')">
        <div class="brand-mark">LY</div>
        <span class="brand-text hidden sm:inline">立洋社区</span>
      </div>

      <!-- 中：标题 -->
      <h1 class="header-title">{{ pageTitle }}</h1>

      <!-- 右：搜索 + 头像 -->
      <div class="header-side header-side--right">
        <button class="icon-btn" type="button" aria-label="搜索" @click="router.push('/search')">
          <Icon name="search" :size="20" />
        </button>
        <div v-if="session.userId" class="user-menu-wrap">
          <button
            class="avatar-btn"
            :style="userStore.profile?.avatar_url ? `background-image:url(${userStore.profile.avatar_url})` : ''"
            aria-label="个人头像"
            @click="menuOpen = !menuOpen"
          >
            <span v-if="!userStore.profile?.avatar_url">{{ (session.nickname || 'U').charAt(0).toUpperCase() }}</span>
          </button>
          <div v-if="menuOpen" class="dropdown-mask" @click="menuOpen = false" />
          <transition name="dropdown">
            <div v-if="menuOpen" class="user-dropdown" role="menu">
              <button class="dropdown-item" @click="onUserCommand('profile')">
                <Icon name="user" :size="16" /> 个人中心
              </button>
              <button class="dropdown-item" @click="onUserCommand('notifications')">
                <Icon name="bell" :size="16" />
                <span>通知中心</span>
                <span v-if="notificationStore.hasUnread" class="badge-dot"></span>
              </button>
              <button class="dropdown-item" @click="onUserCommand('drafts')">
                <Icon name="edit" :size="16" /> 我的草稿
              </button>
              <button class="dropdown-item" @click="onUserCommand('favorites')">
                <Icon name="bookmark" :size="16" /> 我的收藏
              </button>
              <div class="dropdown-divider" />
              <button class="dropdown-item" @click="onUserCommand('settings')">
                <Icon name="settings" :size="16" /> 设置
              </button>
              <button class="dropdown-item text-error" @click="onUserCommand('logout')">
                <Icon name="logout" :size="16" /> 登出
              </button>
            </div>
          </transition>
        </div>
        <button v-else class="icon-btn" aria-label="登录" @click="uiStore.openAuthDialog()">
          <Icon name="log-in" :size="20" />
        </button>
      </div>
    </div>

    <!-- 桌面端顶部主导航 -->
    <nav class="topnav-desktop">
      <div class="mx-auto flex max-w-[1200px] items-center gap-1 px-5">
        <button
          v-for="item in navItems"
          :key="item.key"
          class="topnav-item"
          :class="{ 'is-active': activeTab === item.key }"
          @click="onNavClick(item)"
        >
          <span class="topnav-icon-wrap">
            <Icon :name="item.icon" :size="16" />
            <span
              v-if="item.badge && item.badge > 0"
              class="topnav-badge"
            >{{ item.badge > 99 ? '99+' : item.badge }}</span>
          </span>
          <span>{{ item.label }}</span>
        </button>
      </div>
    </nav>
  </header>
</template>

<style scoped>
.site-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(255, 255, 255, 0.88);
  -webkit-backdrop-filter: blur(20px);
  backdrop-filter: blur(20px);
  border-bottom: 0.5px solid var(--bg-300);
}
.header-inner {
  max-width: 1200px;
  margin: 0 auto;
  height: 56px;
  padding: 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.header-side {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
}
.header-side--left {
  cursor: pointer;
}
.header-side--right {
  justify-content: flex-end;
  gap: 4px;
}
.brand-mark {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, #007aff, #0064d6);
  color: white;
  display: grid;
  place-items: center;
  font-size: 13px;
  font-weight: 800;
  letter-spacing: -0.02em;
  box-shadow: 0 2px 4px -1px rgba(0, 122, 255, 0.3);
}
.brand-text {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-800);
  letter-spacing: -0.01em;
}
.header-title {
  flex: 0 0 auto;
  font-size: 17px;
  font-weight: 700;
  color: var(--text-800);
  letter-spacing: -0.01em;
  text-align: center;
  white-space: nowrap;
  margin: 0;
}
.icon-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--text-600);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: all 0.15s cubic-bezier(0.32, 0.72, 0, 1);
}
.icon-btn:hover {
  background: var(--bg-100);
  color: var(--text-800);
}
.avatar-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: linear-gradient(135deg, #66abff, #007aff);
  color: white;
  border: none;
  cursor: pointer;
  display: grid;
  place-items: center;
  font-size: 13px;
  font-weight: 700;
  background-size: cover;
  background-position: center;
}
.user-menu-wrap {
  position: relative;
}
.dropdown-mask {
  position: fixed;
  inset: 0;
  z-index: 10;
}
.user-dropdown {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 200px;
  background: rgba(255, 255, 255, 0.96);
  -webkit-backdrop-filter: blur(20px);
  backdrop-filter: blur(20px);
  border: 0.5px solid var(--bg-300);
  border-radius: 14px;
  box-shadow: 0 16px 40px -10px rgba(0, 0, 0, 0.1), 0 8px 16px -8px rgba(0, 0, 0, 0.06);
  padding: 6px;
  z-index: 11;
}
.dropdown-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  width: 100%;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-800);
  background: transparent;
  border: none;
  cursor: pointer;
  text-align: left;
  transition: background 0.15s;
}
.dropdown-item:hover {
  background: var(--bg-100);
}
.dropdown-item.text-error {
  color: var(--error);
}
.dropdown-divider {
  height: 1px;
  background: var(--bg-200);
  margin: 4px 8px;
}
.badge-dot {
  margin-left: auto;
  width: 8px;
  height: 8px;
  background: var(--error);
  border-radius: 50%;
}

/* 桌面端导航 */
.topnav-desktop {
  border-top: 0.5px solid var(--bg-200);
  background: rgba(255, 255, 255, 0.6);
  display: block;
}
.topnav-item {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 14px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-500);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: color 0.15s;
}
.topnav-item:hover {
  color: var(--text-800);
}
.topnav-item.is-active {
  color: var(--brand-500);
  font-weight: 600;
}
.topnav-item.is-active::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 14px;
  right: 14px;
  height: 2px;
  background: var(--brand-500);
  border-radius: 1px;
}
/* 图标容器：用于锚定红点 */
.topnav-icon-wrap {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
/* 红点 / 数字徽标：锚定在图标右上角，与微信/抖音一致 */
.topnav-badge {
  position: absolute;
  top: -5px;
  right: -8px;
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

@media (max-width: 768px) {
  .header-inner {
    height: 48px;
    padding: 0 12px;
  }
  .topnav-desktop {
    display: none;
  }
  .header-title {
    font-size: 16px;
  }
  .icon-btn {
    width: 34px;
    height: 34px;
  }
  .brand-text {
    display: none;
  }
}

/* 下拉动画 */
.dropdown-enter-active,
.dropdown-leave-active {
  transition: all 0.2s cubic-bezier(0.32, 0.72, 0, 1);
}
.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-6px) scale(0.96);
}
</style>
