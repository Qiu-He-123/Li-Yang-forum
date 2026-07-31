import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import router from './router'
import './style.css'
import { mountToast } from './components/native/Toast'
import { toast } from './components/native/Toast'

const app = createApp(App)

function isChunkLoadError(err: unknown): boolean {
  const message = String((err as { message?: unknown })?.message || err || '')
  return /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module/i.test(message)
}

function reloadOnceForChunkError(): boolean {
  const key = 'ly:chunk-reload-once'
  if (sessionStorage.getItem(key) === '1') return false
  sessionStorage.setItem(key, '1')
  window.location.reload()
  return true
}

function shouldSuppressUnhandledRejection(reason: unknown): boolean {
  if (!reason || typeof reason !== 'object') return false
  const err = reason as {
    isSilentNetworkError?: boolean
    isSessionInvalid?: boolean
    isAxiosError?: boolean
    response?: unknown
    config?: {
      showGlobalLoading?: boolean
      showGlobalError?: boolean
    }
  }
  if (err.isSilentNetworkError || err.isSessionInvalid) return true
  if (err.config?.showGlobalError === false || err.config?.showGlobalLoading === false) return true
  // Axios 网络错误如果没被上层 catch，HTTP 拦截器通常已处理过一次。
  if (err.isAxiosError && !err.response) return true
  return false
}

// ============ 全局错误处理 ============
// 1. Vue 组件渲染 / 事件处理器中未捕获异常
app.config.errorHandler = (err, _instance, info) => {
  console.error('[Vue errorHandler]', info, err)
  if (isChunkLoadError(err) && reloadOnceForChunkError()) return
  try {
    toast.error('页面异常，请稍后重试')
  } catch {
    /* toast 尚未就绪，忽略 */
  }
}

// 2. 未捕获的 Promise rejection
window.addEventListener('unhandledrejection', (event) => {
  console.error('[unhandledrejection]', event.reason)
  const reason = event.reason
  if (isChunkLoadError(reason) && reloadOnceForChunkError()) {
    event.preventDefault()
    return
  }
  if (shouldSuppressUnhandledRejection(reason)) {
    event.preventDefault()
    return
  }
  if (reason && typeof reason === 'object' && 'message' in reason) {
    try {
      toast.error((reason as Error).message || '请求失败，请稍后重试')
    } catch {
      /* ignore */
    }
  }
})

// 3. 同步未捕获异常
window.addEventListener('error', (event) => {
  console.error('[window error]', event.message, event.error)
})

// Element Plus 按需引入（通过 unplugin-vue-components + unplugin-auto-import）
// 用户端页面不加载 Element Plus，仅 /admin 后台页面按需加载
app.use(createPinia()).use(router).mount('#app')

// 挂载原生 Toast 容器
mountToast()
