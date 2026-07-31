<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import AppHeader from '../components/header/AppHeader.vue'
import PostCard from '../components/post/PostCard.vue'
import EmptyState from '../components/common/EmptyState.vue'
import { fetchMyFavoritePosts } from '../api/user'
import { unfavoritePost } from '../api/interaction'
import { useSessionStore } from '../stores/session'
import type { Post } from '../types/api'

const router = useRouter()
const session = useSessionStore()

const posts = ref<Post[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const { data } = await fetchMyFavoritePosts()
    posts.value = data.data
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    loading.value = false
  }
}

async function removeFavorite(post: Post) {
  try {
    await ElMessageBox.confirm('确认取消收藏该帖子？', '取消收藏', { type: 'warning' })
  } catch {
    return
  }
  try {
    await unfavoritePost(post.id)
    ElMessage.success('已取消收藏')
    posts.value = posts.value.filter((p) => p.id !== post.id)
  } catch (error) {
    ElMessage.error((error as Error).message)
  }
}

// Bug 修复：PostCard 删除帖子后通知父组件，从本地列表移除
function onPostDeleted(postId: number) {
  posts.value = posts.value.filter((p) => p.id !== postId)
}

onMounted(() => {
  if (!session.userId) {
    ElMessage.info('请先登录')
    router.push('/')
  } else {
    load()
  }
})
</script>

<template>
  <main class="min-h-screen pb-16 lg:pb-0">
    <AppHeader />
    <div class="mx-auto max-w-3xl px-4 py-5" v-loading="loading">
      <div class="mb-4 flex items-center justify-between">
        <h2 class="m-0 text-lg font-black">我的收藏</h2>
        <span class="text-xs text-slate-500">{{ posts.length }} 条收藏</span>
      </div>

      <div v-if="posts.length" class="space-y-3">
        <div
          v-for="post in posts"
          :key="post.id"
          class="rounded border border-ly-line bg-white p-4"
        >
          <PostCard :post="post" @deleted="onPostDeleted" />
          <div class="mt-2 flex justify-end">
            <el-button size="small" type="danger" plain @click="removeFavorite(post)">取消收藏</el-button>
          </div>
        </div>
      </div>

      <EmptyState v-else text="暂无收藏，在帖子卡片点击收藏按钮即可加入" />
    </div>
  </main>
</template>
