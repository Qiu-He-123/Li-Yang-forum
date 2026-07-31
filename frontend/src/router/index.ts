import { createRouter, createWebHistory } from 'vue-router'

import { useSessionStore } from '../stores/session'

// 首页直接同步加载，避免首屏闪烁
import HomeView from '../views/HomeView.vue'
// 设置页入口高频且历史上出现过 chunk 缓存失配，直接同步加载避免点击时动态导入失败
import SettingsView from '../views/Settings.vue'

const routes = [
  {
    path: '/',
    name: 'home',
    component: HomeView,
  },
  {
    path: '/banned',
    name: 'banned',
    component: () => import('../views/Banned.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/circles',
    name: 'circles',
    component: () => import('../views/CircleDiscover.vue'),
  },
  {
    path: '/circles/all',
    name: 'all-circles',
    component: () => import('../views/AllCircles.vue'),
  },
  {
    path: '/categories',
    name: 'categories',
    component: () => import('../views/Categories.vue'),
  },
  {
    path: '/circle/:slug',
    name: 'circle-detail',
    component: () => import('../views/CircleDetail.vue'),
  },
  {
    path: '/topic/:id',
    name: 'topic-detail',
    component: () => import('../views/TopicDetail.vue'),
  },
  {
    path: '/post/create',
    name: 'post-create',
    component: () => import('../views/PostCreate.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/post/:id',
    name: 'post-detail',
    component: () => import('../views/PostDetail.vue'),
  },
  {
    path: '/search',
    name: 'search',
    component: () => import('../views/Search.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/user/:id',
    name: 'user-home',
    component: () => import('../views/UserHome.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/user/:id/posts',
    name: 'user-posts',
    component: () => import('../views/UserPostsList.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/user/:id/followers',
    name: 'user-followers',
    component: () => import('../views/FollowList.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/user/:id/following',
    name: 'user-following',
    component: () => import('../views/FollowList.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/user/:id/likers',
    name: 'user-likers',
    component: () => import('../views/UserLikersList.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/settings',
    name: 'settings',
    component: SettingsView,
    meta: { requiresAuth: true },
  },
  {
    path: '/my/drafts',
    name: 'my-drafts',
    component: () => import('../views/MyDrafts.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/my/favorites',
    name: 'my-favorites',
    component: () => import('../views/MyFavorites.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/my/checkin',
    name: 'my-checkin',
    component: () => import('../views/CheckIn.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/my/history',
    name: 'my-history',
    component: () => import('../views/BrowseHistory.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/feedback',
    name: 'feedback',
    component: () => import('../views/Feedback.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/my/circles-applied',
    name: 'my-circles-applied',
    component: () => import('../views/MyCircleApplies.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/my/warning-logs',
    name: 'my-warning-logs',
    component: () => import('../views/MyWarningLogs.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/notifications',
    name: 'notifications',
    component: () => import('../views/Notifications.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/notifications/:type',
    name: 'notification-list',
    component: () => import('../views/NotificationList.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/notification/:id',
    name: 'notification-detail',
    component: () => import('../views/NotificationDetail.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/friends',
    name: 'friends',
    component: () => import('../views/FriendsView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/chat/:id',
    name: 'chat',
    component: () => import('../views/ChatView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/announcements',
    name: 'announcements',
    component: () => import('../views/Announcements.vue'),
  },
  {
    path: '/bottle',
    name: 'bottle',
    component: () => import('../views/BottleView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/match',
    name: 'match',
    component: () => import('../views/MatchView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/agreement',
    name: 'agreement',
    component: () => import('../views/Agreement.vue'),
  },
  // ============ T5-6 管理员后台 ============
  {
    path: '/admin/login',
    name: 'admin-login',
    component: () => import('../views/Admin/Login.vue'),
  },
  {
    path: '/admin',
    component: () => import('../layouts/AdminLayout.vue'),
    meta: { requiresAdmin: true },
    children: [
      { path: '', redirect: '/admin/dashboard' },
      {
        path: 'dashboard',
        name: 'admin-dashboard',
        component: () => import('../views/Admin/Dashboard.vue'),
      },
      {
        path: 'posts',
        name: 'admin-posts',
        component: () => import('../views/Admin/Posts.vue'),
      },
      {
        path: 'comments',
        name: 'admin-comments',
        component: () => import('../views/Admin/Comments.vue'),
      },
      {
        path: 'posts-audit',
        name: 'admin-posts-audit',
        component: () => import('../views/Admin/PostsAudit.vue'),
      },
      {
        path: 'comments-audit',
        name: 'admin-comments-audit',
        component: () => import('../views/Admin/CommentsAudit.vue'),
      },
      {
        path: 'users',
        name: 'admin-users',
        component: () => import('../views/Admin/Users.vue'),
      },
      {
        path: 'verifications-audit',
        name: 'admin-verifications-audit',
        component: () => import('../views/Admin/VerificationsAudit.vue'),
      },
      {
        path: 'seed-codes',
        name: 'admin-seed-codes',
        component: () => import('../views/Admin/SeedCodesManage.vue'),
      },
      {
        path: 'ban-records',
        name: 'admin-ban-records',
        component: () => import('../views/Admin/BanRecords.vue'),
      },
      {
        path: 'appeals',
        name: 'admin-appeals',
        component: () => import('../views/Admin/Appeals.vue'),
      },
      {
        path: 'audit-logs',
        name: 'admin-audit-logs',
        component: () => import('../views/Admin/AuditLogs.vue'),
      },
      {
        path: 'reports',
        name: 'admin-reports',
        component: () => import('../views/Admin/Reports.vue'),
      },
      {
        path: 'announcements',
        name: 'admin-announcements',
        component: () => import('../views/Admin/Announcements.vue'),
      },
      {
        path: 'circles-audit',
        name: 'admin-circles-audit',
        component: () => import('../views/Admin/CircleAudit.vue'),
      },
      {
        path: 'feedback',
        name: 'admin-feedback',
        component: () => import('../views/Admin/FeedbackManage.vue'),
      },
      {
        path: 'deepseek',
        name: 'admin-deepseek',
        component: () => import('../views/Admin/DeepSeek.vue'),
      },
      {
        path: 'warning-config',
        name: 'admin-warning-config',
        component: () => import('../views/Admin/WarningConfig.vue'),
      },
      {
        path: 'logs',
        name: 'admin-logs',
        component: () => import('../views/Admin/Logs.vue'),
      },
      {
        path: 'user-logs',
        name: 'admin-user-logs',
        component: () => import('../views/Admin/UserLogs.vue'),
      },
      {
        path: 'login-logs',
        name: 'admin-login-logs',
        component: () => import('../views/Admin/LoginLogs.vue'),
      },
    ],
  },
  // 404 兜底
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('../views/Error/NotFound.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.onError((error) => {
  const message = String(error?.message || error)
  if (!/Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module/i.test(message)) {
    return
  }
  const key = 'ly:chunk-reload-once'
  if (sessionStorage.getItem(key) === '1') return
  sessionStorage.setItem(key, '1')
  window.location.reload()
})

router.afterEach(() => {
  sessionStorage.removeItem('ly:chunk-reload-once')
})

// 全局守卫：
// - requiresAuth：未登录跳首页
// - requiresAdmin：未登录管理员跳 /admin/login
router.beforeEach(async (to) => {
  // 封号用户强制跳转到封号提示页（除非已在封号页/退出登录流程）
  if (to.name !== 'banned' && localStorage.getItem('banned') === '1') {
    const session = useSessionStore()
    if (session.userId) {
      return { name: 'banned' }
    }
  }
  if (to.meta.requiresAuth) {
    const session = useSessionStore()
    if (!session.userId) {
      return { name: 'home', query: { redirect: to.fullPath } }
    }
  }
  if (to.meta.requiresAdmin) {
    // 延迟导入避免循环依赖
    const { useAdminStore } = await import('../stores/admin')
    const admin = useAdminStore()
    // 已有本地态：跳过 ping，避免每次切换菜单都打一次接口
    if (!admin.isLogged()) {
      return { name: 'admin-login', query: { redirect: to.fullPath } }
    }
  }
  return true
})

export default router
