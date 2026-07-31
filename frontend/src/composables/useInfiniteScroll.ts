import { onMounted, onUnmounted, ref, type Ref } from 'vue'

interface UseInfiniteScrollOptions {
  /** 是否还有更多数据可加载 */
  hasMore: Ref<boolean>
  /** 加载下一页的函数（由调用方负责递增 page 和 append 数据） */
  onLoadMore: () => Promise<void>
  /** 距底部多少像素时触发预加载（默认 250） */
  threshold?: number
  /** 滚动容器选择器（默认 window 整页滚动） */
  containerSelector?: string
}

/**
 * 通用无限滚动 composable
 *
 * 特性：
 * - 距底部 threshold px 时自动触发预加载（默认 250px）
 * - 请求锁：loading 期间不重复触发
 * - 节流：100ms 内只检查一次滚动位置，防止疯狂滚动
 * - 错误重试：接口报错后显示「加载失败，点击重试」，保留已加载数据
 * - 自动生命周期管理：onMounted 注册，onUnmounted 清理
 */
export function useInfiniteScroll(opts: UseInfiniteScrollOptions) {
  const loading = ref(false)
  const error = ref(false)
  let scrollTimer: ReturnType<typeof setTimeout> | null = null

  function getScrollInfo() {
    if (opts.containerSelector) {
      const el = document.querySelector(opts.containerSelector)
      if (el) {
        return {
          scrollTop: el.scrollTop,
          scrollHeight: el.scrollHeight,
          clientHeight: el.clientHeight,
        }
      }
    }
    return {
      scrollTop: window.scrollY,
      scrollHeight: document.documentElement.scrollHeight,
      clientHeight: window.innerHeight,
    }
  }

  async function checkAndLoad() {
    // 请求锁：loading 中 / 无更多 / 已出错 → 跳过
    if (loading.value || !opts.hasMore.value || error.value) return
    const { scrollTop, scrollHeight, clientHeight } = getScrollInfo()
    const distanceToBottom = scrollHeight - scrollTop - clientHeight
    if (distanceToBottom <= (opts.threshold ?? 250)) {
      loading.value = true
      error.value = false
      try {
        await opts.onLoadMore()
      } catch {
        error.value = true
      } finally {
        loading.value = false
      }
    }
  }

  function onScroll() {
    // 节流：100ms 内只检查一次
    if (scrollTimer) return
    scrollTimer = setTimeout(() => {
      scrollTimer = null
      void checkAndLoad()
    }, 100)
  }

  /** 手动重试（用户点击「加载失败，点击重试」时调用） */
  function retry() {
    error.value = false
    void checkAndLoad()
  }

  onMounted(() => {
    window.addEventListener('scroll', onScroll, { passive: true })
  })

  onUnmounted(() => {
    window.removeEventListener('scroll', onScroll)
    if (scrollTimer) clearTimeout(scrollTimer)
  })

  return { loading, error, retry }
}
