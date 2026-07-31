import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { listPosts, type PostView } from '../api/post'
import type { LoadingAxiosRequestConfig } from '../api/http'
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

  // ============ SWR（Stale-While-Revalidate）缓存 ============
  // 首页/圈子页共用 postStore，切换 Tab 时 view 会互相覆盖。
  // viewCache 按「view:category」缓存各视图的首页数据 + 时间戳，
  // 配合 keep-alive 的 onActivated 实现：
  // - 切回 Tab 时先从缓存恢复（即时展示，无骨架屏）
  // - 缓存超过 SWR_TTL 才后台静默刷新（用户无感知）
  const SWR_TTL = 30_000 // 30 秒内视为新鲜，不重复刷新
  interface CachedView {
    posts: Post[]
    total: number
    lastFetchAt: number
  }
  const viewCache = ref<Record<string, CachedView>>({})

  function cacheKey(): string {
    return `${activeView.value}:${activeCategory.value}`
  }

  /** 从缓存恢复当前视图的数据（用于 keep-alive 激活时即时展示） */
  function restoreFromCache(): boolean {
    const cached = viewCache.value[cacheKey()]
    if (!cached) return false
    posts.value = cached.posts
    total.value = cached.total
    page.value = 1
    return true
  }

  /**
   * SWR 核心方法：保持当前视图数据新鲜。
   * - 无缓存 → 正常 loadPosts（显示骨架屏）
   * - 缓存未过期 → 不做任何操作（避免无效请求）
   * - 缓存已过期 → silentRefresh（后台静默刷新，用户无感知）
   * 返回 true 表示数据有变化（调用方可据此触发渐变动画）
   */
  async function ensureFresh(): Promise<boolean> {
    const cached = viewCache.value[cacheKey()]
    if (!cached) { await loadPosts(); return false }
    if (Date.now() - cached.lastFetchAt < SWR_TTL) return false
    return silentRefresh()
  }

  // 是否存在 AI 审核中的帖子（用于驱动轮询刷新）
  const hasPendingAudit = computed(() => posts.value.some((p) => p.ai_status === 'pending'))

  /** 是否还有更多数据可加载（用于无限滚动判定） */
  const hasMore = computed(() => posts.value.length < total.value)

  async function loadPosts(config: LoadingAxiosRequestConfig = {}) {
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
      const { data } = await listPosts(params, config)
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
      // SWR：成功后写入缓存（存数组拷贝避免引用污染）
      viewCache.value[cacheKey()] = {
        posts: [...posts.value],
        total: total.value,
        lastFetchAt: Date.now(),
      }
      return true
    } catch (err) {
      error.value = (err as Error).message || '帖子加载失败'
      return false
    } finally {
      loading.value = false
    }
  }

  /**
   * 加载下一页（append 模式，用于无限滚动）。
   * - 递增 page，请求下一页数据
   * - append 到 posts 数组，不覆盖已有数据
   * - 静默请求（不触发 loading，避免骨架屏闪烁）
   * - 更新 total 和缓存
   */
  async function loadMore() {
    if (!hasMore.value || loading.value) return
    const nextPage = page.value + 1
    try {
      const params: Parameters<typeof listPosts>[0] = {
        view: activeView.value,
        page: nextPage,
        page_size: pageSize.value,
      }
      if (activeCategory.value) params.category = activeCategory.value
      const { data } = await listPosts(params, {
        showGlobalLoading: false,
        showGlobalError: false,
      })
      const payload = data.data as unknown as { items: Post[]; total: number; page: number; page_size: number } | Post[]
      if (Array.isArray(payload)) {
        posts.value = [...posts.value, ...payload]
        total.value = posts.value.length
      } else {
        // 去重：避免最后一页不足 page_size 时重复数据
        const existingIds = new Set(posts.value.map(p => p.id))
        const newItems = payload.items.filter(p => !existingIds.has(p.id))
        posts.value = [...posts.value, ...newItems]
        total.value = payload.total
        page.value = payload.page
        pageSize.value = payload.page_size
      }
      // 更新缓存
      const cached = viewCache.value[cacheKey()]
      if (cached) {
        cached.posts = [...posts.value]
        cached.total = total.value
      }
    } catch {
      // loadMore 失败由调用方的 useInfiniteScroll error 状态处理
      throw new Error('加载更多失败')
    }
  }

  // 静默刷新（不触发 loading），用于轮询 pending 帖子的 AI 审核状态 + SWR 后台刷新
  // 返回 true 表示数据有变化（调用方可据此触发渐变动画）
  async function silentRefresh(): Promise<boolean> {
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
      const newPosts = Array.isArray(payload) ? payload : payload.items
      // 对比新旧数据指纹：只有数据真的变了才更新 + 返回 true
      const oldFp = posts.value.map(p => `${p.id}:${p.like_count}:${p.comment_count}`).join('|')
      const newFp = newPosts.map(p => `${p.id}:${p.like_count}:${p.comment_count}`).join('|')
      const changed = oldFp !== newFp
      if (Array.isArray(payload)) {
        posts.value = payload
        total.value = payload.length
      } else {
        posts.value = payload.items
        total.value = payload.total
        page.value = payload.page
        pageSize.value = payload.page_size
      }
      // SWR：刷新成功后更新缓存时间戳
      const cached = viewCache.value[cacheKey()]
      if (cached) {
        cached.posts = [...posts.value]
        cached.total = total.value
        cached.lastFetchAt = Date.now()
      } else {
        viewCache.value[cacheKey()] = {
          posts: [...posts.value],
          total: total.value,
          lastFetchAt: Date.now(),
        }
      }
      return changed
    } catch {
      // 静默刷新失败不影响用户
      return false
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

  return { activeView, activeCategory, posts, total, page, pageSize, loading, error, hasPendingAudit, hasMore, loadPosts, loadMore, silentRefresh, ensureFresh, restoreFromCache, setView, setCategory, setPage }
})
