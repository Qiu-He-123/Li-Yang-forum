import { createRouter, createWebHistory } from 'vue-router'
import { nextTick } from 'vue'

import { useSessionStore } from '../stores/session'
import { useUIStore } from '../stores/ui'

// 首页直接同步加载，避免首屏闪烁
import HomeView from '../views/HomeView.vue'

const routes = [
  {
    path: '/',
    name: 'home',
    component: HomeView,
    // keep-alive + skeleton：底部主 Tab，缓存组件实例；首次加载用骨架屏替代全屏遮罩
    meta: { keepAlive: true, skeleton: true },
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
    meta: { keepAlive: true, skeleton: true },
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
    // 帖子详情：骨架屏替代全屏遮罩
    meta: { skeleton: true },
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
    // 「我的」Tab：keep-alive + skeleton，频繁切换时保留资料 + 已加载列表
    meta: { requiresAuth: true, keepAlive: true, skeleton: true },
  },
  {
    path: '/user/:id/posts',
    name: 'user-posts',
    component: () => import('../views/UserPostsList.vue'),
    meta: { requiresAuth: true, skeleton: true },
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
    component: () => import('../views/Settings.vue'),
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
    path: '/my/badges',
    name: 'my-badges',
    component: () => import('../views/MyBadges.vue'),
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
    // 「消息」Tab：keep-alive + skeleton，避免每次切换都重新拉取会话列表
    meta: { requiresAuth: true, keepAlive: true, skeleton: true },
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
    meta: { requiresAuth: true, skeleton: true },
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
        path: 'images-audit',
        name: 'admin-images-audit',
        component: () => import('../views/Admin/ImagesAudit.vue'),
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
        path: 'badges',
        name: 'admin-badges',
        component: () => import('../views/Admin/Badges.vue'),
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
  scrollBehavior(to, from, savedPosition) {
    // 返回/前进（浏览器 back/forward）：恢复上次的滚动位置
    // 这样从帖子详情返回个人主页时，能回到之前浏览的位置（不回顶部）
    if (savedPosition) return savedPosition
    // 导航到新页面时回到顶部
    // 修复：从"我的-作品"（已滚动到下方）点击帖子进入详情，
    // 浏览器默认保持滚动位置导致直接显示在页面底部
    return { top: 0 }
  },
})

router.onError((error) => {
  // 路由出错也要结束 loading，避免遮罩残留
  try {
    useUIStore().endRouteLoading()
  } catch {
    /* pinia 未就绪 */
  }
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
  // 等组件挂载 + onMounted 发起 API 请求后再结束路由 loading，
  // 让 HTTP loading 无缝接管，避免 loading 闪烁消失再出现。
  // 参考"心伴网页_新"双 requestAnimationFrame 确保绘制后再跳转的思路。
  nextTick(() => {
    try {
      useUIStore().endRouteLoading()
    } catch {
      /* pinia 未就绪 */
    }
  })
})

// 全局守卫：
// - requiresAuth：未登录跳首页
// - requiresAdmin：未登录管理员跳 /admin/login
router.beforeEach(async (to) => {
  // 有骨架屏的页面（首页/圈子/消息）不显示全屏遮罩，让组件内骨架屏可见。
  // 非骨架屏页面（详情页/设置页等）仍用全屏遮罩 + routeLoading 即时显示。
  if (to.meta.skeleton !== true) {
    try {
      useUIStore().beginRouteLoading()
    } catch {
      /* pinia 未就绪（应用启动极早期） */
    }
  }
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
