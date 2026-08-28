import { defineStore } from 'pinia'
import { ref } from 'vue'

import { fetchMyLikes, fetchMyFavorites } from '../api/user'

/**
 * 维护当前用户的点赞 / 收藏 ID 集合。
 * 用于 PostCard / CommentItem 的 active 态回填，避免刷新后丢失。
 */
export const useInteractionStore = defineStore('interaction', () => {
  const likedPostIds = ref<Set<number>>(new Set())
  const favoritedPostIds = ref<Set<number>>(new Set())
  const likedCommentIds = ref<Set<number>>(new Set())
  const loaded = ref(false)

  async function loadAll() {
    if (loaded.value) return
    try {
      const [{ data: likes }, { data: favs }] = await Promise.all([
        fetchMyLikes({
          showGlobalLoading: false,
          showGlobalError: false,
        }),
        fetchMyFavorites({
          showGlobalLoading: false,
          showGlobalError: false,
        }),
      ])
      likedPostIds.value = new Set(likes.data.post_ids)
      likedCommentIds.value = new Set(likes.data.comment_ids)
      favoritedPostIds.value = new Set(favs.data.post_ids)
      loaded.value = true
    } catch {
      // 未登录或加载失败：保持空集合
    }
  }

  function clear() {
    likedPostIds.value = new Set()
    favoritedPostIds.value = new Set()
    likedCommentIds.value = new Set()
    loaded.value = false
  }

  function toggleLikedPost(id: number, liked: boolean) {
    if (liked) likedPostIds.value.add(id)
    else likedPostIds.value.delete(id)
  }

  function toggleFavoritedPost(id: number, favorited: boolean) {
    if (favorited) favoritedPostIds.value.add(id)
    else favoritedPostIds.value.delete(id)
  }

  function toggleLikedComment(id: number, liked: boolean) {
    if (liked) likedCommentIds.value.add(id)
    else likedCommentIds.value.delete(id)
  }

  return {
    likedPostIds,
    favoritedPostIds,
    likedCommentIds,
    loaded,
    loadAll,
    clear,
    toggleLikedPost,
    toggleFavoritedPost,
    toggleLikedComment,
  }
})
