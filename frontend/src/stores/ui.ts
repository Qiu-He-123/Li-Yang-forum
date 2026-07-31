import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * 全局 UI 状态（P1-BottomTabBar）。
 * 把 AuthDialog / InviteCodeDialog 提升为全局组件，任何位置都能通过
 * openAuthDialog() / openInviteCodeDialog() 触发弹窗。
 */
export const useUIStore = defineStore('ui', () => {
  const authDialogVisible = ref(false)
  // 邀请码提示弹窗（已注册未填邀请码用户做发帖/评论/匹配/漂流瓶操作时触发）
  const inviteCodeDialogVisible = ref(false)
  const globalLoadingCount = ref(0)
  const globalLoadingVisible = ref(false)
  let globalLoadingShowTimer: ReturnType<typeof setTimeout> | null = null
  let globalLoadingHideTimer: ReturnType<typeof setTimeout> | null = null
  const GLOBAL_LOADING_DELAY = 120
  const GLOBAL_LOADING_HIDE_DELAY = 180
  // 路由 loading 结束后的宽限期：给组件 onMounted → HTTP 请求发起留足时间，
  // 避免"路由 loading 隐藏 → HTTP loading 又显示"的二次闪烁。
  // 500ms 足以覆盖异步 chunk 下载 + Vue 挂载 + onMounted + axios 拦截器触发。
  const ROUTE_LOADING_GRACE = 500

  // ============ 路由级 loading ============
  // 参考"心伴网页_新"的 safeNavigate 模式：点击导航瞬间立即显示全屏遮罩，
  // 而不是等组件 onMounted 发起 API 请求后才显示（HTTP loading 有 120ms 延迟 + 组件加载延迟）。
  // 路由 loading 立即显示，afterEach + nextTick 后结束，由 HTTP loading 无缝接管。
  const routeLoading = ref(false)

  function openAuthDialog() {
    authDialogVisible.value = true
  }

  function closeAuthDialog() {
    authDialogVisible.value = false
  }

  function openInviteCodeDialog() {
    inviteCodeDialogVisible.value = true
  }

  function closeInviteCodeDialog() {
    inviteCodeDialogVisible.value = false
  }

  /** 隐藏全屏 loading 的公共逻辑（考虑 HTTP loading 和路由 loading 双方） */
  function scheduleHide() {
    // 还有任意一方在进行，不隐藏
    if (globalLoadingCount.value > 0 || routeLoading.value) return
    if (!globalLoadingVisible.value) return
    if (globalLoadingHideTimer) return
    globalLoadingHideTimer = setTimeout(() => {
      globalLoadingHideTimer = null
      if (globalLoadingCount.value === 0 && !routeLoading.value) {
        globalLoadingVisible.value = false
      }
    }, GLOBAL_LOADING_HIDE_DELAY)
  }

  function beginGlobalLoading() {
    globalLoadingCount.value += 1
    if (globalLoadingHideTimer) {
      clearTimeout(globalLoadingHideTimer)
      globalLoadingHideTimer = null
    }
    // 路由 loading 已经在显示，无需 120ms 延迟，直接保持
    if (routeLoading.value) {
      if (globalLoadingShowTimer) {
        clearTimeout(globalLoadingShowTimer)
        globalLoadingShowTimer = null
      }
      return
    }
    if (
      globalLoadingCount.value === 1 &&
      !globalLoadingVisible.value &&
      !globalLoadingShowTimer
    ) {
      globalLoadingShowTimer = setTimeout(() => {
        globalLoadingShowTimer = null
        if (globalLoadingCount.value > 0) {
          globalLoadingVisible.value = true
        }
      }, GLOBAL_LOADING_DELAY)
    }
  }

  function endGlobalLoading() {
    globalLoadingCount.value = Math.max(0, globalLoadingCount.value - 1)
    if (globalLoadingCount.value > 0) return

    if (globalLoadingShowTimer) {
      clearTimeout(globalLoadingShowTimer)
      globalLoadingShowTimer = null
    }
    // 路由 loading 还在，不隐藏（等路由 afterEach 结束时统一处理）
    if (routeLoading.value) return
    scheduleHide()
  }

  /** 路由切换开始：立即显示全屏 loading（无延迟） */
  function beginRouteLoading() {
    if (globalLoadingShowTimer) {
      clearTimeout(globalLoadingShowTimer)
      globalLoadingShowTimer = null
    }
    if (globalLoadingHideTimer) {
      clearTimeout(globalLoadingHideTimer)
      globalLoadingHideTimer = null
    }
    routeLoading.value = true
    globalLoadingVisible.value = true
  }

  /** 路由切换结束：若 HTTP 请求仍在进行则交由 HTTP loading 接管，否则隐藏。
   *  关键：用 ROUTE_LOADING_GRACE 宽限期（而非 scheduleHide 的 180ms），
   *  因为 nextTick 时组件还没挂载，HTTP 请求还没发起，180ms 太短会导致
   *  loading 先隐藏再被 HTTP loading 重新触发 = 二次闪烁。
   */
  function endRouteLoading() {
    routeLoading.value = false
    if (globalLoadingCount.value > 0) return
    // HTTP loading 还没接管，用宽限期等待 onMounted 的 HTTP 请求发起
    if (globalLoadingHideTimer) clearTimeout(globalLoadingHideTimer)
    globalLoadingHideTimer = setTimeout(() => {
      globalLoadingHideTimer = null
      if (globalLoadingCount.value === 0 && !routeLoading.value) {
        globalLoadingVisible.value = false
      }
    }, ROUTE_LOADING_GRACE)
  }

  return {
    authDialogVisible,
    inviteCodeDialogVisible,
    globalLoadingCount,
    globalLoadingVisible,
    openAuthDialog,
    closeAuthDialog,
    openInviteCodeDialog,
    closeInviteCodeDialog,
    beginGlobalLoading,
    endGlobalLoading,
    beginRouteLoading,
    endRouteLoading,
  }
})
