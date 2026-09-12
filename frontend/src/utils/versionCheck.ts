import { ref, onMounted, onUnmounted } from 'vue'

/**
 * 前端版本自动检测：
 * 发版后浏览器/nginx 允许 HTML no-cache，但正在使用的 SPA 页面不会自己触发重载，
 * 导致用户一直看到旧页面。这里定期请求一个不缓存、随每次构建更新的版本文件，
 * 与本地首次记录比对；一旦发现线上版本更新，提示用户刷新加载新版本。
 *
 * 用法：在 App.vue 根组件调用 useVersionCheck() 即可。
 *
 * 注意：严禁在此顶层 import element-plus，否则会把 EP 拉进用户端首屏主 chunk
 * （该项目刻意保持"用户端 0 KB EP"）。确认弹窗用动态 import 按需加载。
 */
const VERSION_FILE = '/build_version.json'
const STORAGE_KEY = 'ly_web_build_ver'
const CHECK_INTERVAL = 5 * 60 * 1000 // 每 5 分钟检查一次
const CHECK_INTERVAL_ACTIVE = 30 * 1000 // 页面重新可见时，30s 内立即再查一次

// 模块级单例：避免重复初始化（App 只应存在一个根实例，但防御性去重）
let registered = false
let currentVersion: string | null = null

export function useVersionCheck() {
  const checking = ref(false)

  async function fetchVersion(): Promise<string | null> {
    try {
      // 每次都带时间戳，绕过 nginx/browser 对 build_version.json 可能的内存缓存
      const res = await fetch(`${VERSION_FILE}?t=${Date.now()}`, {
        cache: 'no-store',
      })
      if (!res.ok) return null
      const data = await res.json()
      return data?.version || null
    } catch {
      return null
    }
  }

  async function check() {
    if (checking.value) return
    checking.value = true
    try {
      const remote = await fetchVersion()
      if (!remote) return // 拉不到版本（未部署完/网络差）就跳过本轮

      // 本地已记录的版本（用于检测"这次会话是否发生过升级提示"）
      let local: string | null = localStorage.getItem(STORAGE_KEY)
      if (!local) {
        // 首次：以当前线上版本作为基准，防止刚发完版误弹一波
        localStorage.setItem(STORAGE_KEY, remote)
        currentVersion = remote
        return
      }
      currentVersion = local

      if (remote !== local) {
        // 升级提示（全局一次）：用户点刷新后，升级前再写入新版本基准
        // 动态加载 ElMessageBox，避免把 element-plus 打进用户端首屏主 chunk
        try {
          const { ElMessageBox } = await import('element-plus')
          await ElMessageBox.confirm(
            '页面有新版本，点击刷新即可加载最新功能与修复。',
            '发现新版本',
            {
              confirmButtonText: '立即刷新',
              cancelButtonText: '稍后',
              closeOnClickModal: false,
              distinguishCancelAndClose: false,
            },
          )
          localStorage.setItem(STORAGE_KEY, remote)
          window.location.reload()
        } catch {
          // 用户点了"稍后"，不刷新，下次轮询会再提示
        }
      }
    } finally {
      checking.value = false
    }
  }

  onMounted(() => {
    if (registered) return
    registered = true
    // 启动延迟检查一次（避开首屏渲染，给用户先看到界面）
    setTimeout(check, 3000)
    timer = window.setInterval(check, CHECK_INTERVAL)
    // 页面重新可见时，比后台轮询更快提醒一次（用户切回来时通常马上会被用到）
    document.addEventListener('visibilitychange', onVisibility)
  })

  onUnmounted(() => {
    if (timer) clearInterval(timer)
    document.removeEventListener('visibilitychange', onVisibility)
  })

  let timer: number | undefined

  function onVisibility() {
    if (document.visibilityState === 'visible') {
      if (timer) clearInterval(timer)
      timer = window.setInterval(check, CHECK_INTERVAL)
      setTimeout(check, CHECK_INTERVAL_ACTIVE)
    }
  }

  return { checking }
}