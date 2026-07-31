import { defineStore } from 'pinia'
import { ref } from 'vue'

import { clearSearchHistory, deleteSearchHistory, listHotSearch, listSearchHistory } from '../api/search'
import type { HotSearch, SearchHistory } from '../types/api'
import { useSessionStore } from './session'

/**
 * 搜索 store
 * 管理搜索历史 + 热搜榜
 */
export const useSearchStore = defineStore('search', () => {
  const history = ref<SearchHistory[]>([])
  const hotList = ref<HotSearch[]>([])
  const loaded = ref(false)

  async function loadHistory() {
    const session = useSessionStore()
    if (!session.userId) return
    try {
      const { data } = await listSearchHistory({
        showGlobalLoading: false,
        showGlobalError: false,
      })
      history.value = data.data
    } catch {
      /* 静默失败 */
    }
  }

  async function loadHot() {
    if (loaded.value) return
    try {
      const { data } = await listHotSearch({
        showGlobalLoading: false,
        showGlobalError: false,
      })
      hotList.value = data.data
      loaded.value = true
    } catch {
      /* 静默失败 */
    }
  }

  async function removeHistory(keyword: string) {
    try {
      await deleteSearchHistory(keyword)
      history.value = history.value.filter((h) => h.keyword !== keyword)
    } catch {
      /* 静默失败 */
    }
  }

  async function clearHistory() {
    try {
      await clearSearchHistory()
      history.value = []
    } catch {
      /* 静默失败 */
    }
  }

  /** 搜索成功后调用，前端先乐观追加，后端在 /posts?q= 时也会写入 */
  function appendHistoryLocal(keyword: string) {
    const existed = history.value.findIndex((h) => h.keyword === keyword)
    if (existed >= 0) history.value.splice(existed, 1)
    history.value.unshift({
      id: Date.now(),
      keyword,
      created_at: new Date().toISOString(),
    })
    if (history.value.length > 20) history.value = history.value.slice(0, 20)
  }

  function clear() {
    history.value = []
    hotList.value = []
    loaded.value = false
  }

  return { history, hotList, loaded, loadHistory, loadHot, removeHistory, clearHistory, appendHistoryLocal, clear }
})
