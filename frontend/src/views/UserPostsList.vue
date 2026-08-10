<script setup lang="ts">
/**
 * 用户作品列表页（瀑布流展示）
 *
 * 路由：/user/:id/posts
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import EmptyState from '../components/common/EmptyState.vue'
import PostListSkeleton from '../components/post/PostListSkeleton.vue'
import MarkdownText from '../components/common/MarkdownText.vue'
import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import { fetchUser, fetchUserPosts } from '../api/user'
import type { Post, Profile } from '../types/api'

const route = useRoute()
const router = useRouter()

const userId = computed(() => Number(route.params.id))
const profile = ref<Profile | null>(null)
const posts = ref<Post[]>([])
const loading = ref(false)

const displayName = computed(() => profile.value?.nickname || `用户 ${userId.value || ''}`.trim())
const pageTitle = computed(() => {
  return `${displayName.value}的作品`
})

function avatarGradient(id: number | undefined): string {
  const idx = (id || 0) % 5
  const grads = [
    'linear-gradient(135deg, #66abff, #007aff)',
    'linear-gradient(135deg, #34c759, #2e8dff)',
    'linear-gradient(135deg, #ff9500, #007aff)',
    'linear-gradient(135deg, #5856d6, #0064d6)',
    'linear-gradient(135deg, #d1d1d6, #8e8e93)',
  ]
  return grads[idx]
}

async function loadProfile() {
  // keep-alive 守卫：route.params.id 变 undefined 时 Number(undefined)=NaN，必须跳过
  if (!userId.value || isNaN(userId.value)) return
  try {
    const { data } = await fetchUser(userId.value)
    profile.value = data.data
  } catch (err) {
    toast.error((err as Error).message)
  }
}

async function loadPosts() {
  if (!userId.value || isNaN(userId.value)) return
  loading.value = true
  try {
    const { data } = await fetchUserPosts(userId.value)
    // 兼容分页结构 {items, total} 和旧版数组结构
    const payload = data.data as any
    posts.value = Array.isArray(payload) ? payload : (payload.items || [])
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

function openPost(post: Post) {
  if (post.is_viewable === false) {
    toast.info(post.content || '审核中，暂无法查看原文')
    return
  }
  router.push(`/post/${post.id}`)
}

/** 推导缩略图 URL（与 PostImages.vue 一致的规则） */
function thumbUrl(url: string): string {
  if (/\.gif$/i.test(url)) return url
  return url.replace(/\.(jpe?g|png|webp)$/i, '_thumb.jpg')
}

/** 缩略图加载失败 → 回退原图 */
function onImgError(e: Event, originalUrl: string) {
  const img = e.target as HTMLImageElement
  if (img.src !== originalUrl) img.src = originalUrl
}

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push(`/user/${userId.value}`)
}

onMounted(async () => {
  await Promise.all([loadProfile(), loadPosts()])
})

watch(userId, () => {
  if (!userId.value || isNaN(userId.value)) return
  loadProfile()
  loadPosts()
})
</script>

<template>
  <main class="page-list">
    <!-- 顶部栏 -->
    <header class="list-header">
      <button class="icon-btn" type="button" aria-label="返回" @click="goBack">
        <Icon name="arrow-left" :size="20" />
      </button>
      <h1 class="list-title">{{ pageTitle }}</h1>
      <span class="icon-btn-placeholder" />
    </header>

    <!-- 列表 -->
    <div class="page-container">
      <!-- 骨架屏替代"加载中..."文字 -->
      <PostListSkeleton v-if="loading && !posts.length" :count="4" />

      <div v-else-if="posts.length" class="posts-waterfall">
        <article
          v-for="post in posts"
          :key="post.id"
          class="post-card"
          @click="openPost(post)"
        >
          <img
            v-if="post.image_urls?.length"
            class="post-img"
            :src="thumbUrl(post.image_urls[0])"
            :alt="post.title || ''"
            loading="lazy"
            decoding="async"
            @error="onImgError($event, post.image_urls[0])"
          />
          <div v-else class="post-img-placeholder">
            <Icon name="image" :size="24" />
          </div>
          <div class="post-body">
            <p v-if="post.title" class="post-content">{{ post.title }}</p>
            <MarkdownText v-else :content="post.content" class="post-content" :clamp="4" />
            <div class="post-meta">
              <span class="post-cat">#{{ post.category || '校园' }}</span>
              <span v-if="post.is_public === false" class="private-badge">
                <Icon name="lock" :size="11" />
                已私密
              </span>
              <span class="post-stats">
                <Icon name="heart" :size="11" />
                {{ post.like_count }}
                <Icon name="message-square" :size="11" />
                {{ post.comment_count }}
              </span>
            </div>
          </div>
        </article>
      </div>

      <EmptyState v-else icon="file-text" text="还没有发布过作品" />
    </div>
  </main>
</template>

<style scoped>
.page-list {
  min-height: 100vh;
  background: var(--bg-100);
}

.list-header {
  position: sticky;
  top: 0;
  z-index: 50;
  background: rgba(255, 255, 255, 0.95);
  -webkit-backdrop-filter: blur(20px);
  backdrop-filter: blur(20px);
  border-bottom: 0.5px solid var(--bg-300);
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  padding-top: env(safe-area-inset-top);
}
.list-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-800);
  margin: 0;
  flex: 1;
  text-align: center;
}
.icon-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: transparent;
  cursor: pointer;
  display: grid;
  place-items: center;
  color: var(--text-600);
  transition: background 0.15s;
}
.icon-btn:hover {
  background: var(--bg-100);
  color: var(--text-800);
}
.icon-btn-placeholder {
  width: 36px;
  height: 36px;
  display: inline-block;
}

.page-container {
  max-width: 720px;
  margin: 0 auto;
  padding: 8px 12px calc(80px + env(safe-area-inset-bottom));
}

.loading-tip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 0;
  color: var(--text-500);
  font-size: 13px;
}

.posts-waterfall {
  column-count: 2;
  column-gap: 10px;
}
.post-card {
  break-inside: avoid;
  margin-bottom: 10px;
  background: var(--bg-50);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-xs);
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
}
.post-card:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}
.post-img {
  width: 100%;
  display: block;
  background: var(--bg-200);
}
.post-img-placeholder {
  width: 100%;
  aspect-ratio: 1;
  display: grid;
  place-items: center;
  background: var(--bg-200);
  color: var(--text-300);
}
.post-body {
  padding: 8px 10px 10px;
}
.post-content {
  margin: 0 0 6px;
  font-size: 13px;
  line-height: 1.4;
  color: var(--text-800);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.private-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 6px;
  border-radius: 999px;
  background: rgba(245, 158, 11, 0.12);
  color: #b45309;
  font-size: 11px;
  font-weight: 600;
}
.post-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  font-size: 10px;
  color: var(--text-400);
}
.post-cat {
  color: var(--brand-500);
}
.post-stats {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

@media (max-width: 480px) {
  .list-header {
    height: 48px;
    padding: 0 12px;
  }
}
</style>
