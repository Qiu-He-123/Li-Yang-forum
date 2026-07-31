import { defineStore } from 'pinia'
import { ref } from 'vue'

import { fetchCircle, joinCircle, leaveCircle, listCircles } from '../api/circle'
import type { Circle } from '../types/api'

/**
 * 圈子 store
 * 管理圈子列表、加入/退出状态、我的足迹
 */
export const useCircleStore = defineStore('circle', () => {
  const circles = ref<Circle[]>([])
  const loaded = ref(false)
  // 我的足迹：登录用户浏览过的圈子列表（按最近浏览排序）
  // 提升到 store 层，CircleDetail 进入时即可即时更新，避免返回后才刷新的"延迟一步"问题
  const viewedCircles = ref<Circle[]>([])

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

  /**
   * 即时记录圈子浏览（前端乐观更新）。
   * CircleDetail onMounted loadCircle 成功后调用，把圈子移到足迹列表最前面（去重）。
   * 这样返回 CircleDiscover 时足迹已更新，无需等待 onActivated 的后台刷新。
   */
  function recordView(circle: Circle) {
    if (!circle?.id) return
    const idx = viewedCircles.value.findIndex((c) => c.id === circle.id)
    if (idx >= 0) {
      // 已存在：移到最前
      const [existing] = viewedCircles.value.splice(idx, 1)
      // 保留 viewed_at 等后端字段，用最新圈子信息覆盖
      viewedCircles.value.unshift({ ...existing, ...circle })
    } else {
      // 新圈子：加到最前
      viewedCircles.value.unshift(circle)
    }
  }

  /** 设置足迹列表（后端数据回填） */
  function setViewedCircles(list: Circle[]) {
    viewedCircles.value = list || []
  }

  function clear() {
    circles.value = []
    loaded.value = false
    viewedCircles.value = []
  }

  return { circles, loaded, viewedCircles, loadCircles, loadCircle, toggleJoin, recordView, setViewedCircles, clear }
})
