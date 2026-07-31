import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { listPosts, type PostView } from '../api/post'
import type { Post } from '../types/api'

export const usePostStore = defineStore('post', () => {
  const activeView = ref<PostView>('all')
  const activeCategory = ref<string>('')
  const posts = ref<Post[]>([])
  const total = ref(0)
  const page = ref(1)
  // 卡片高度增大后一屏自然约 5 个，但保持 20 条总数支持滚动加载更多
  const pageSize = ref(20)
  const loading = ref(false)
  const error = ref('')

  // 是否存在 AI 审核中的帖子（用于驱动轮询刷新）
  const hasPendingAudit = computed(() => posts.value.some((p) => p.ai_status === 'pending'))

  async function loadPosts() {
    loading.value = true
    error.value = ''
    try {
      const params: Parameters<typeof listPosts>[0] = {
        view: activeView.value,
        page: page.value,
        page_size: pageSize.value,
      }
      // P0-Bug#1：分类筛选 previously 被忽略，导致 SideMenu 的 /?category=树洞 无效果
      if (activeCategory.value) params.category = activeCategory.value
      const { data } = await listPosts(params)
      // 后端 T4-11 起返回 { items, total, page, page_size }
      const payload = data.data as unknown as { items: Post[]; total: number; page: number; page_size: number } | Post[]
      if (Array.isArray(payload)) {
        // 兼容旧版（无分页）返回
        posts.value = payload
        total.value = payload.length
      } else {
        posts.value = payload.items
        total.value = payload.total
        page.value = payload.page
        pageSize.value = payload.page_size
      }
      return true
    } catch (err) {
      error.value = (err as Error).message || '帖子加载失败'
      return false
    } finally {
      loading.value = false
    }
  }

  // 静默刷新（不触发 loading），用于轮询 pending 帖子的 AI 审核状态
  async function silentRefresh() {
    try {
      const params: Parameters<typeof listPosts>[0] = {
        view: activeView.value,
        page: page.value,
        page_size: pageSize.value,
      }
      if (activeCategory.value) params.category = activeCategory.value
      const { data } = await listPosts(params, {
        showGlobalLoading: false,
        showGlobalError: false,
      })
      const payload = data.data as unknown as { items: Post[]; total: number; page: number; page_size: number } | Post[]
      if (Array.isArray(payload)) {
        posts.value = payload
        total.value = payload.length
      } else {
        posts.value = payload.items
        total.value = payload.total
        page.value = payload.page
        pageSize.value = payload.page_size
      }
    } catch {
      // 静默刷新失败不影响用户
    }
  }

  function setView(view: PostView) {
    activeView.value = view
    page.value = 1
  }

  function setCategory(category: string) {
    activeCategory.value = category
    page.value = 1
  }

  function setPage(p: number) {
    page.value = p
  }

  return { activeView, activeCategory, posts, total, page, pageSize, loading, error, hasPendingAudit, loadPosts, silentRefresh, setView, setCategory, setPage }
})
