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

  function beginGlobalLoading() {
    globalLoadingCount.value += 1
    if (globalLoadingHideTimer) {
      clearTimeout(globalLoadingHideTimer)
      globalLoadingHideTimer = null
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
    if (globalLoadingVisible.value && !globalLoadingHideTimer) {
      globalLoadingHideTimer = setTimeout(() => {
        globalLoadingHideTimer = null
        if (globalLoadingCount.value === 0) {
          globalLoadingVisible.value = false
        }
      }, GLOBAL_LOADING_HIDE_DELAY)
    }
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
  }
})
