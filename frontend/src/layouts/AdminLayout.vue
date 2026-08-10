<script setup lang="ts">
/**
 * 管理后台布局（大厂风格）
 *
 * 设计参考：Ant Design Pro / 腾讯内部管理系统
 * - 深色侧边栏（#001529），白色内容区
 * - 顶部面包屑 + 用户信息
 * - 分组导航菜单（概览 / 内容管理 / 用户 / 安全 / 系统）
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { useAdminStore } from '../stores/admin'

const router = useRouter()
const route = useRoute()
const admin = useAdminStore()

interface MenuItem {
  index: string
  label: string
  icon: string
  badge?: number
}
interface MenuGroup {
  title: string
  items: MenuItem[]
}

const menuGroups = computed<MenuGroup[]>(() => [
  {
    title: '概览',
    items: [
      { index: '/admin/dashboard', label: '数据看板', icon: '📊' },
    ],
  },
  {
    title: '内容管理',
    items: [
      { index: '/admin/posts', label: '帖子管理', icon: '📝' },
      { index: '/admin/comments', label: '评论管理', icon: '💬' },
      { index: '/admin/posts-audit', label: '帖子审核', icon: '🔍' },
      { index: '/admin/comments-audit', label: '评论审核', icon: '🔎' },
      { index: '/admin/circles-audit', label: '吧审核', icon: '🏷️' },
      { index: '/admin/reports', label: '举报处理', icon: '🚩' },
      { index: '/admin/announcements', label: '公告管理', icon: '📢' },
      { index: '/admin/badges', label: '徽章管理', icon: '🏅' },
      { index: '/admin/badge-rules', label: '徽章自动发放', icon: '🤖' },
      { index: '/admin/images-audit', label: '图片审核', icon: '🖼️' },
      { index: '/admin/bottles-audit', label: '漂流瓶审核', icon: '🍾' },
    ],
  },
  {
    title: '用户与安全',
    items: [
      { index: '/admin/users', label: '用户管理', icon: '👤' },
      { index: '/admin/verifications-audit', label: '学生认证审核', icon: '🎓' },
      { index: '/admin/seed-codes', label: '种子邀请码', icon: '🎫' },
      { index: '/admin/ban-records', label: '封号管理', icon: '🔨' },
      { index: '/admin/appeals', label: '申诉管理', icon: '✊' },
      { index: '/admin/feedback', label: '反馈管理', icon: '📩' },
    ],
  },
  {
    title: '系统设置',
    items: [
      { index: '/admin/deepseek', label: 'AI 审核配置', icon: '🤖' },
      { index: '/admin/warning-config', label: '警告值配置', icon: '⚠️' },
      { index: '/admin/system-settings', label: '默认好友配置', icon: '👥' },
    ],
  },
  {
    title: '系统日志',
    items: [
      { index: '/admin/audit-logs', label: 'AI 审核日志', icon: '🗒️' },
      { index: '/admin/logs', label: '管理员操作日志', icon: '📋' },
      { index: '/admin/user-logs', label: '用户操作日志', icon: '📈' },
      { index: '/admin/login-logs', label: '登录日志', icon: '🔐' },
    ],
  },
])

const activeIndex = computed(() => route.path)

// 面包屑
const breadcrumb = computed(() => {
  const all = menuGroups.value.flatMap((g) => g.items)
  const found = all.find((m) => route.path.startsWith(m.index))
  return found ? found.label : '管理后台'
})

const collapsed = ref(false)
const mobileMenuOpen = ref(false)

function onSelect(index: string) {
  router.push(index)
  mobileMenuOpen.value = false
}

async function onLogout() {
  try {
    await ElMessageBox.confirm('确认退出管理员账号？', '退出登录', { type: 'warning' })
  } catch {
    return
  }
  await admin.logout()
  ElMessage.success('已退出')
  router.push('/admin/login')
}

onMounted(() => {
  // 路由守卫已校验 admin_token
  // 移动端切换路由时自动收起抽屉菜单
  router.afterEach(() => {
    mobileMenuOpen.value = false
  })
})
</script>

<template>
  <main class="admin-layout">
    <!-- 移动端抽屉遮罩 -->
    <div
      v-if="mobileMenuOpen"
      class="admin-mobile-mask"
      @click="mobileMenuOpen = false"
    />

    <!-- 侧边栏 -->
    <aside class="admin-sidebar" :class="{ collapsed, 'mobile-open': mobileMenuOpen }">
      <div class="sidebar-logo">
        <span class="logo-icon">🏛</span>
        <span v-if="!collapsed" class="logo-text">立洋管理后台</span>
      </div>
      <nav class="sidebar-menu">
        <div v-for="group in menuGroups" :key="group.title" class="menu-group">
          <div v-if="!collapsed" class="menu-group-title">{{ group.title }}</div>
          <button
            v-for="item in group.items"
            :key="item.index"
            class="menu-item"
            :class="{ active: activeIndex === item.index || (item.index !== '/admin/dashboard' && activeIndex.startsWith(item.index)) }"
            type="button"
            @click="onSelect(item.index)"
          >
            <span class="menu-icon">{{ item.icon }}</span>
            <span v-if="!collapsed" class="menu-label">{{ item.label }}</span>
          </button>
        </div>
      </nav>
      <div class="sidebar-footer">
        <div v-if="!collapsed && admin.adminInfo" class="admin-info">
          <div class="admin-avatar">{{ admin.adminInfo.username.charAt(0).toUpperCase() }}</div>
          <div class="admin-meta">
            <div class="admin-name">{{ admin.adminInfo.username }}</div>
            <div class="admin-role">{{ admin.adminInfo.role }}</div>
          </div>
        </div>
        <button class="logout-btn" type="button" @click="onLogout">
          <span>⏻</span>
          <span v-if="!collapsed">退出登录</span>
        </button>
      </div>
    </aside>

    <!-- 主内容区 -->
    <section class="admin-main">
      <header class="admin-header">
        <div class="header-left">
          <button class="collapse-btn" type="button" @click="collapsed = !collapsed">
            <span>{{ collapsed ? '☰' : '✕' }}</span>
          </button>
          <button class="mobile-menu-btn" type="button" @click="mobileMenuOpen = !mobileMenuOpen">
            <span>☰</span>
          </button>
          <span class="header-breadcrumb">{{ breadcrumb }}</span>
        </div>
        <div class="header-right">
          <span class="header-time">{{ new Date().toLocaleDateString('zh-CN') }}</span>
        </div>
      </header>
      <div class="admin-content">
        <RouterView />
      </div>
    </section>
  </main>
</template>

<style scoped>
.admin-layout {
  display: flex;
  min-height: 100vh;
  background: #f0f2f5;
}

/* 侧边栏 */
.admin-sidebar {
  width: 232px;
  flex-shrink: 0;
  background: #001529;
  color: rgba(255, 255, 255, 0.85);
  display: flex;
  flex-direction: column;
  transition: width 0.2s;
}
.admin-sidebar.collapsed {
  width: 64px;
}
.sidebar-logo {
  height: 60px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}
.logo-icon {
  font-size: 24px;
  flex-shrink: 0;
}
.logo-text {
  font-size: 16px;
  font-weight: 700;
  color: #fff;
  white-space: nowrap;
}

.sidebar-menu {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}
.menu-group {
  margin-bottom: 4px;
}
.menu-group-title {
  padding: 8px 24px 4px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.35);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 24px;
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.65);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
  text-align: left;
}
.menu-item:hover {
  background: rgba(255, 255, 255, 0.06);
  color: #fff;
}
.menu-item.active {
  background: #1890ff;
  color: #fff;
}
.menu-icon {
  font-size: 16px;
  flex-shrink: 0;
  width: 20px;
  text-align: center;
}
.menu-label {
  white-space: nowrap;
}

.sidebar-footer {
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  padding: 12px;
  flex-shrink: 0;
}
.admin-info {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 4px;
  margin-bottom: 8px;
}
.admin-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #1890ff;
  color: #fff;
  display: grid;
  place-items: center;
  font-size: 14px;
  font-weight: 700;
  flex-shrink: 0;
}
.admin-meta {
  min-width: 0;
}
.admin-name {
  font-size: 13px;
  color: #fff;
  font-weight: 500;
}
.admin-role {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.45);
}
.logout-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding: 8px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 6px;
  background: transparent;
  color: rgba(255, 255, 255, 0.65);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.logout-btn:hover {
  background: rgba(255, 59, 48, 0.15);
  border-color: #ff3b30;
  color: #ff3b30;
}

/* 主内容区 */
.admin-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.admin-header {
  height: 60px;
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  flex-shrink: 0;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
}
.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}
.collapse-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 18px;
  color: #595959;
  border-radius: 4px;
  transition: background 0.15s;
}
.mobile-menu-btn {
  display: none;
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 18px;
  color: #595959;
  border-radius: 4px;
}
.mobile-menu-btn:hover {
  background: #f0f0f0;
}
.collapse-btn:hover {
  background: #f0f0f0;
}
.header-breadcrumb {
  font-size: 16px;
  font-weight: 600;
  color: #262626;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.header-time {
  font-size: 13px;
  color: #8c8c8c;
}
.admin-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

/* ============ 移动端适配（手机也能顺畅操作后台） ============ */
.admin-mobile-mask {
  display: none;
}
@media (max-width: 768px) {
  .mobile-menu-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  .collapse-btn {
    display: none;
  }
  .admin-sidebar {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    z-index: 1200;
    transform: translateX(-100%);
    transition: transform 0.25s cubic-bezier(0.32, 0.72, 0, 1);
    box-shadow: 0 0 24px rgba(0, 0, 0, 0.2);
  }
  .admin-sidebar.mobile-open {
    transform: translateX(0);
  }
  .admin-sidebar.collapsed {
    width: 232px;
  }
  .admin-mobile-mask {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.45);
    z-index: 1100;
  }
  .admin-header {
    height: 52px;
    padding: 0 12px;
  }
  .header-breadcrumb {
    font-size: 14px;
  }
  .header-time {
    display: none;
  }
  .admin-content {
    padding: 12px;
  }
}
</style>

<style>
/* ============ 后台页面通用移动端适配（作用于所有 Admin 子页面） ============ */
@media (max-width: 768px) {
  .admin-page .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
  .admin-page .page-title {
    font-size: 18px;
  }
  .admin-page .filter-card {
    flex-direction: column;
    align-items: stretch;
    padding: 12px;
  }
  .admin-page .filter-card .el-input,
  .admin-page .filter-card .el-select,
  .admin-page .filter-card .el-date-editor,
  .admin-page .filter-card input {
    width: 100% !important;
    max-width: none !important;
  }
  .admin-page .table-card {
    padding: 8px;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  .admin-page .el-table {
    min-width: 720px;
  }
  .admin-page .el-dialog {
    width: calc(100vw - 24px) !important;
    max-width: calc(100vw - 24px) !important;
    margin-top: 5vh !important;
  }
  .admin-page .el-pagination {
    justify-content: center;
    flex-wrap: wrap;
    gap: 4px;
  }
  .admin-page .el-pagination .el-pagination__jump {
    display: none;
  }
  .admin-page .el-pagination .el-pagination__sizes {
    display: none;
  }
}
</style>
