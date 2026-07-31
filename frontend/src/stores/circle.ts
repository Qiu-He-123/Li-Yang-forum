import { defineStore } from 'pinia'
import { ref } from 'vue'

import { fetchCircle, joinCircle, leaveCircle, listCircles } from '../api/circle'
import type { Circle } from '../types/api'

/**
 * 圈子 store
 * 管理圈子列表、加入/退出状态
 */
export const useCircleStore = defineStore('circle', () => {
  const circles = ref<Circle[]>([])
  const loaded = ref(false)

  async function loadCircles(force = false) {
    if (loaded.value && !force) return
    // 后端已支持匿名访问圈子列表（is_joined 始终为 false）
    try {
      const { data } = await listCircles({
        showGlobalLoading: false,
        showGlobalError: false,
      })
      circles.value = data.data
      loaded.value = true
    } catch {
      /* 静默失败 */
    }
  }

  async function loadCircle(slug: string) {
    const { data } = await fetchCircle(slug)
    return data.data
  }

  async function toggleJoin(circle: Circle) {
    const slug = circle.slug
    if (circle.is_joined) {
      const { data } = await leaveCircle(slug)
      circle.is_joined = false
      circle.member_count = data.data.member_count
    } else {
      const { data } = await joinCircle(slug)
      circle.is_joined = true
      circle.member_count = data.data.member_count
    }
    return circle.is_joined
  }

  function clear() {
    circles.value = []
    loaded.value = false
  }

  return { circles, loaded, loadCircles, loadCircle, toggleJoin, clear }
})
