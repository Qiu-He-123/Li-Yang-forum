import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import router from './router'
import './style.css'
// ElMessage / ElMessageBox 是命令式 API（代码里显式 import { ElMessage } from 'element-plus'），
// unplugin 按需解析器只处理模板组件，不会自动带上这两个服务组件的样式。
// 不引入样式时 .el-message 会以无样式普通文本渲染在页面底部（屏幕外），用户看不到任何提示。
// 这里统一在入口引入，用户端与后台所有 ElMessage 提示都能正常显示。
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
// Element Plus 暗色模式变量（html.dark 时生效，覆盖后台/表单/弹窗）
import 'element-plus/theme-chalk/dark/css-vars.css'
import { mountToast } from './components/native/Toast'
import { toast } from './components/native/Toast'
import { ensureDeepEntryBackTarget } from './utils/backNav'

// 手机 App（套壳 WebView）UA 标记：隐藏仅网页版才需要展示的入口
if (typeof navigator !== 'undefined' && navigator.userAgent.includes('LYCommunityApp')) {
  document.documentElement.classList.add('ly-app')
}

// 主题初始化：白天/暗色（localStorage 持久化，设置页可切换）
const savedTheme = localStorage.getItem('ly:theme')
const isDark = savedTheme === 'dark'
document.documentElement.dataset.theme = isDark ? 'dark' : 'light'
if (isDark) document.documentElement.classList.add('dark')

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
app.use(createPinia())
app.use(router)

// 深链接/扫码直接打开详情页时，先补一条「返回目标」历史，
// 这样按返回（App 返回键 / 浏览器返回）会直接回首页或会话列表
router.isReady().then(async () => {
  await ensureDeepEntryBackTarget(router.currentRoute.value.fullPath)
  app.mount('#app')
})

// 挂载 Toast 容器
mountToast()

// ============ 启动预加载遮罩兜底移除 ============
// App.vue onMounted 正常情况下会移除 #app-preloader，
// 但如果 Vue 挂载失败 / onMounted 抛异常，遮罩会永久残留导致白屏。
// 这里设一个 8s 兜底定时器，确保任何情况下遮罩最终都会被移除。
function forceRemovePreloader() {
  const el = document.getElementById('app-preloader')
  if (el && el.parentNode) {
    el.parentNode.removeChild(el)
  }
}
window.setTimeout(forceRemovePreloader, 8000)
// 如果页面发生致命错误，立即移除遮罩让用户看到错误
window.addEventListener('error', () => {
  // 延迟一点移除，给 errorHandler 处理时间
  window.setTimeout(forceRemovePreloader, 1000)
}, { once: true })
