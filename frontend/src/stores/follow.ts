import { defineStore } from 'pinia'
import { ref } from 'vue'

import { checkFollowing, followUser, unfollowUser } from '../api/follow'

/**
 * 关注关系 store
 * 管理当前用户对其他用户的关注状态（按需缓存）
 */
export const useFollowStore = defineStore('follow', () => {
  /** key: followee_id, value: 是否已关注 */
  const followingMap = ref<Record<number, boolean>>({})

  async function loadFollowing(userId: number) {
    if (followingMap.value[userId] !== undefined) return followingMap.value[userId]
    try {
      const { data } = await checkFollowing(userId, {
        showGlobalLoading: false,
        showGlobalError: false,
      })
      followingMap.value[userId] = data.data.following
      return data.data.following
    } catch {
      return false
    }
  }

  async function toggleFollow(userId: number) {
    const current = followingMap.value[userId] ?? false
    if (current) {
      const { data } = await unfollowUser(userId)
      followingMap.value[userId] = false
      return false
    } else {
      const { data } = await followUser(userId)
      followingMap.value[userId] = true
      return true
    }
  }

  function setFollowing(userId: number, following: boolean) {
    followingMap.value[userId] = following
  }

  function isFollowing(userId: number): boolean {
    return followingMap.value[userId] ?? false
  }

  function clear() {
    followingMap.value = {}
  }

  return { followingMap, loadFollowing, toggleFollow, setFollowing, isFollowing, clear }
})
