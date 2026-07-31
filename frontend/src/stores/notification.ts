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

  function startPolling(intervalMs = 5_000) {
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
