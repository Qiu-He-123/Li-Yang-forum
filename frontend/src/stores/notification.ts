import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { fetchUnreadCount } from '../api/notification'
import { useSessionStore } from './session'

export const useNotificationStore = defineStore('notification', () => {
  const notifUnread = ref(0)
  const dmUnread = ref(0)
  const byType = ref<Record<string, number>>({})
  const unreadCount = computed(() => notifUnread.value + dmUnread.value)
  const hasUnread = computed(() => unreadCount.value > 0)

  let timer: ReturnType<typeof setInterval> | null = null
  let refreshPromise: Promise<void> | null = null

  async function refreshUnread() {
    if (refreshPromise) return refreshPromise

    const session = useSessionStore()
    if (!session.userId) {
      notifUnread.value = 0
      dmUnread.value = 0
      byType.value = {}
      return
    }

    refreshPromise = (async () => {
      try {
        const { data } = await fetchUnreadCount()
        const result = data.data || { unread: 0, dm_unread: 0, by_type: {} }
        notifUnread.value = Number(result.unread) || 0
        dmUnread.value = Number(result.dm_unread) || 0
        byType.value = Object.fromEntries(
          Object.entries(result.by_type || {}).map(([type, count]) => [type, Number(count) || 0]),
        )
      } catch {
        // Badge refresh is best-effort.
      } finally {
        refreshPromise = null
      }
    })()

    return refreshPromise
  }

  // 轮询间隔：30s。
  // 已有 WebSocket 兜底：收到 dm_message 时 App.vue 立即调用 refreshUnread()，
  // 因此轮询只需保证"长时间无 WS 事件时也能拿到点赞/关注等非 DM 类通知的未读数"。
  function startPolling(intervalMs = 60_000) {
    stopPolling()
    timer = setInterval(refreshUnread, intervalMs)
  }

  function stopPolling() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  function clear() {
    notifUnread.value = 0
    dmUnread.value = 0
    byType.value = {}
    stopPolling()
  }

  return {
    unreadCount,
    notifUnread,
    dmUnread,
    byType,
    hasUnread,
    refreshUnread,
    startPolling,
    stopPolling,
    clear,
  }
})
