import axios, { type AxiosError, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios'

import { toast } from '../components/native/Toast'
import { useUIStore } from '../stores/ui'
import type { ApiResponse } from '../types/api'

export interface LoadingAxiosRequestConfig extends AxiosRequestConfig {
  showGlobalLoading?: boolean
  showGlobalError?: boolean
  _globalLoading?: boolean
  _retried?: boolean
}

export const http = axios.create({
  baseURL: '/api',
  withCredentials: true,
  // 统一请求超时：避免上传/慢请求卡死，上传接口内部已单独处理
  timeout: 30_000,
})

// ============ T2-7 自动 refresh 队列 ============
// 当 access_token 过期（业务码 -101），自动调 /auth/refresh 续期；
// 续期期间其他并发请求挂起等待，避免同时触发多次 refresh。
let refreshing: Promise<void> | null = null
let authFailureHandled = false

// 后台轮询 / 静默请求的 URL 模式：这些请求不触发全屏遮罩，避免每次交互都"加载中"
const SILENT_URL_PATTERNS: string[] = [
  '/notifications/unread-count',
  '/notifications',          // 通知列表本身也常轮询
  '/auth/me',                // 会话校验（每 45s 一次）
  '/auth/refresh',           // token 续期
  '/images',                 // 图片上传（PostEditor 有局部进度条）
  '/posts/view',             // 浏览量上报（fire-and-forget）
  '/posts/related',          // 相关推荐（异步加载，不阻塞主帖）
  '/interactions/',          // 点赞 / 收藏（即时反馈，不应遮罩）
  '/follow/',                // 关注 / 取消关注
  '/comments/',              // 评论点赞等
  '/topics/search',          // 话题搜索浮层
  '/topics/hot',
  '/circles',                // 圈子列表加载（编辑器内异步）
  '/schools',                // 校区列表
  '/search/suggest',         // 搜索建议
  '/search/users',
  '/users/',                 // 用户主页相关
  '/polls/',                 // 投票详情
  '/match/',                 // 匹配相关
  '/bottle/',                // 漂流瓶
  '/dm/',                    // 私信
]

function shouldShowGlobalLoading(config: LoadingAxiosRequestConfig): boolean {
  if (config.showGlobalLoading === false) return false
  const url = String(config.url || '')
  // 显式 opt-in：调用方要求显示全屏加载（如首页帖子列表首次加载）
  if (config.showGlobalLoading === true) return true
  // 后台 / 交互类请求不显示全屏遮罩
  if (SILENT_URL_PATTERNS.some((p) => url.includes(p))) return false
  return true
}

function shouldShowGlobalError(config?: AxiosRequestConfig): boolean {
  const loadingConfig = config as LoadingAxiosRequestConfig | undefined
  if (loadingConfig?.showGlobalError === false) return false
  // Background polling and silent refreshes must never interrupt the user.
  if (loadingConfig?.showGlobalLoading === false) return false
  return true
}

function beginGlobalLoading(config: InternalAxiosRequestConfig) {
  const loadingConfig = config as LoadingAxiosRequestConfig
  if (!shouldShowGlobalLoading(loadingConfig)) return
  loadingConfig._globalLoading = true
  try {
    useUIStore().beginGlobalLoading()
  } catch {
    loadingConfig._globalLoading = false
  }
}

function endGlobalLoading(config?: AxiosRequestConfig) {
  const loadingConfig = config as LoadingAxiosRequestConfig | undefined
  if (!loadingConfig?._globalLoading) return
  loadingConfig._globalLoading = false
  try {
    useUIStore().endGlobalLoading()
  } catch {
    /* ignore */
  }
}

/** refresh 失败的类型区分：
 * - 'invalid'：refresh_token 无效/过期/被撤销 → 应清 session 让用户重新登录
 * - 'network'：网络错误/超时 → 不清 session，保留登录态，下次请求再试
 */
type RefreshFailReason = 'invalid' | 'network'
type RetriableRequestConfig = InternalAxiosRequestConfig & LoadingAxiosRequestConfig
type SilentNetworkError = Error & { isSilentNetworkError?: boolean }
type RequestErrorLike = Error & {
  isSilentNetworkError?: boolean
  isSessionInvalid?: boolean
  isAxiosError?: boolean
  response?: unknown
  config?: LoadingAxiosRequestConfig
}

export function isSilentRequestError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false
  const err = error as RequestErrorLike
  if (err.isSilentNetworkError || err.isSessionInvalid) return true
  if (!err.response && (err.config?.showGlobalError === false || err.config?.showGlobalLoading === false)) {
    return true
  }
  return false
}

class RefreshError extends Error {
  reason: RefreshFailReason
  constructor(reason: RefreshFailReason, msg: string) {
    super(msg)
    this.reason = reason
  }
}

async function refreshSession(): Promise<void> {
  // 用裸 axios 调 refresh，避免再走拦截器造成死循环
  try {
    const { data } = await axios.post('/api/auth/refresh', null, {
      withCredentials: true,
      timeout: 10_000, // refresh 请求较短超时，避免用户长时间等待
    })
    if (data.code !== 0) {
      // 仅 -100（未登录）和 -101（token 无效）才判定为 refresh_token 真正无效；
      // 其他非 0 错误码（如 -1 服务器内部错误）视为临时故障，不清 session，
      // 避免服务器偶发故障导致用户被强制登出（"每次重进页面都需要重新登录"的根因）。
      if (data.code === -100 || data.code === -101) {
        throw new RefreshError('invalid', data.msg || 'refresh failed')
      }
      throw new RefreshError('network', data.msg || '服务器临时故障')
    }
  } catch (err) {
    // 区分：AxiosError 无 response（网络错误） vs 有 response（业务错误）
    if (err instanceof RefreshError) throw err
    const axiosErr = err as AxiosError<ApiResponse<unknown>>
    if (axiosErr.response) {
      const bodyCode = axiosErr.response.data?.code
      if (bodyCode === -100 || bodyCode === -101) {
        throw new RefreshError('invalid', 'refresh token 无效')
      }
      // 其他业务码视为临时故障，不清 session
      throw new RefreshError('network', axiosErr.response.data?.msg || '服务器临时故障')
    }
    // 无 response：网络错误/超时，不清 session
    throw new RefreshError('network', '网络错误，请稍后重试')
  }
}

function clearSessionAndRedirect() {
  if (authFailureHandled) return
  authFailureHandled = true
  // Clear the persistent marker synchronously so concurrent views stop issuing
  // authenticated requests before the dynamic store import finishes.
  try {
    localStorage.removeItem('userId')
    localStorage.removeItem('nickname')
    localStorage.removeItem('verificationStatus')
    localStorage.removeItem('banned')
  } catch {
    /* ignore */
  }
  // Delay the import to avoid a circular dependency.
  void import('../stores/session').then(({ useSessionStore }) => {
    const session = useSessionStore()
    session.clearSession()
  })
  void import('../router').then(({ default: router }) => {
    const current = router.currentRoute.value
    // Bug 修复：仅在"需要登录"的页面才跳首页。
    // 公开页面（如 /post/:id、/circles、/circle/:slug、/announcements 等）
    // 游客本就可访问，不应因 session 失效被强制踢回首页 —— 否则
    // "分享帖子链接给朋友，朋友点进去回到首页"的 bug 就会出现。
    // 仅清 session 即可，当前页面会以游客身份继续渲染。
    if (current.meta.requiresAuth || current.meta.requiresAdmin) {
      if (current.name !== 'home') {
        router.replace({ name: 'home', query: { redirect: current.fullPath } })
      }
    }
  })
}

function sessionExpiredError(message = '登录已过期，请重新登录') {
  const error = new Error(message) as Error & { isSessionInvalid?: boolean }
  error.isSessionInvalid = true
  return error
}

async function retryAuthRequest(
  originalRequest: RetriableRequestConfig | undefined,
  code?: number,
) {
  if (originalRequest && !originalRequest._retried) {
    originalRequest._retried = true
    try {
      if (!refreshing) {
        refreshing = refreshSession().finally(() => {
          refreshing = null
        })
      }
      await refreshing
      return http(originalRequest as AxiosRequestConfig)
    } catch (err) {
      const reason = (err as RefreshError)?.reason
      if (reason !== 'network') {
        const shouldNotify = !authFailureHandled
        clearSessionAndRedirect()
        if (code === -101 && shouldNotify && shouldShowGlobalError(originalRequest)) {
          toast.error('登录已过期，请重新登录')
        }
        return Promise.reject(sessionExpiredError())
      }
      const networkErr = new Error('网络异常，登录状态暂未刷新') as SilentNetworkError
      networkErr.isSilentNetworkError = !shouldShowGlobalError(originalRequest)
      return Promise.reject(networkErr)
    }
  }

  clearSessionAndRedirect()
  return Promise.reject(sessionExpiredError())
}

/** 封号用户自动跳转封号提示页（立即封号后实时生效，无需用户重新登录） */
function handleBannedRedirect() {
  // 同步响应式 isBanned 状态（供 App.vue 启停通知轮询），并写 localStorage 供路由守卫读取
  try {
    // 动态导入避免循环依赖：http.ts 被 stores 引用，stores 又被 http.ts 引用
    void import('../stores/session').then(({ useSessionStore }) => {
      try {
        useSessionStore().setBanned(true)
      } catch {
        // pinia 尚未初始化（应用启动早期），降级写 localStorage
        localStorage.setItem('banned', '1')
      }
    })
  } catch {
    localStorage.setItem('banned', '1')
  }
  void import('../router').then(({ default: router }) => {
    if (router.currentRoute.value.name !== 'banned') {
      router.replace({ name: 'banned' })
    }
  })
}

/** 邀请码系统：已注册但未填邀请码（-302），弹邀请码提示窗 */
function handleInviteCodeRequired() {
  void import('../stores/ui').then(({ useUIStore }) => {
    try {
      useUIStore().openInviteCodeDialog()
    } catch {
      // pinia 尚未初始化，忽略
    }
  })
}

http.interceptors.request.use((config) => {
  beginGlobalLoading(config)
  return config
})

http.interceptors.response.use(
  (response) => {
    endGlobalLoading(response.config)
    const responseUrl = String(response.config.url || '')
    if (responseUrl.includes('/auth/login') || responseUrl.includes('/auth/register')) {
      authFailureHandled = false
    }
    const body = response.data as ApiResponse<unknown>
    if (body.code !== 0) {
      if (body.code === -101 || body.code === -100) {
        return retryAuthRequest(response.config as RetriableRequestConfig, body.code)
      }
      // 封号用户：立即跳转封号提示页（覆盖所有写操作接口）
      if (body.code === -301) {
        handleBannedRedirect()
      }
      // 邀请码系统：已注册但未填邀请码（-302），弹邀请码提示窗
      if (body.code === -302) {
        handleInviteCodeRequired()
      }
      // 后端已统一返回具体错误码 + 中文消息，直接抛错让 ElMessage 展示
      // 挂载 code 到 Error 对象，供调用方区分错误类型（如帖子私密 vs 已删除）
      const e = new Error(body.msg || '请求失败') as Error & { code?: number }
      e.code = body.code
      return Promise.reject(e)
    }
    return response
  },
  async (error: AxiosError<ApiResponse<unknown>>) => {
    endGlobalLoading(error.config)
    const response = error.response
    const body = response?.data
    const code = body?.code

    // 封号用户：立即跳转封号提示页（HTTP 403 + code -301）
    if (code === -301) {
      handleBannedRedirect()
      return Promise.reject(new Error(body?.msg || '账号已被封禁'))
    }

    // 邀请码系统：已注册但未填邀请码（-302），弹邀请码提示窗
    if (code === -302) {
      handleInviteCodeRequired()
      return Promise.reject(new Error(body?.msg || '需要邀请码'))
    }

    // ============ T7-5 401 / Token 过期统一处理 ============
    // code === -100 NOT_LOGGED_IN：未登录（refresh_token 也无效），清 session 跳首页
    // code === -101 TOKEN_INVALID：access_token 过期/缺失，尝试自动 refresh
    //
    // 修复自动登录问题：
    // 后端 current_user 在 access_token 缺失但 refresh_token 仍在时返回 -101，
    // 这里 -100 和 -101 都先尝试 refresh，refresh 失败才真正清 session。
    // 这样用户 30 分钟 access_token 过期后不会被动登出。
    if (code === -101 || code === -100) {
      return retryAuthRequest(error.config as RetriableRequestConfig | undefined, code)
    }

    // ============ 网络错误统一提示 ============
    if (!response) {
      const msg = error?.message || '网络错误'
      // Network failures from background polling are expected and must stay silent.
      if (shouldShowGlobalError(error.config)) {
        const isTimeout = error.code === 'ECONNABORTED'
          || error.code === 'ETIMEDOUT'
          || /timeout/i.test(msg)
        toast.error(isTimeout ? '请求超时' : '网络错误，请稍后重试')
      } else {
        const silentError = error as SilentNetworkError
        silentError.isSilentNetworkError = true
      }
      return Promise.reject(error)
    }

    // 业务错误（已有 msg），交给调用方 ElMessage 处理
    // 挂载 code 到 Error 对象，供调用方区分错误类型（如帖子私密 vs 已删除）
    const bizErr = new Error(body?.msg || '请求失败') as Error & { code?: number }
    bizErr.code = code
    return Promise.reject(bizErr)
  },
)
