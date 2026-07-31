import { defineStore } from 'pinia'
import { ref } from 'vue'

import { listAnnouncements } from '../api/announcement'
import type { Announcement } from '../types/api'

export const useAnnouncementStore = defineStore('announcement', () => {
  const announcements = ref<Announcement[]>([])
  const loaded = ref(false)
  const error = ref('')

  async function loadAnnouncements() {
    error.value = ''
    try {
      const { data } = await listAnnouncements({
        showGlobalLoading: false,
        showGlobalError: false,
      })
      announcements.value = data.data
    } catch (err) {
      announcements.value = []
      error.value = (err as Error).message || '公告加载失败'
    } finally {
      loaded.value = true
    }
  }

  return { announcements, loaded, error, loadAnnouncements }
})
