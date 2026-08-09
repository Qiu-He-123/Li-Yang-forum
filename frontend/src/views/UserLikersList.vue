<script setup lang="ts">
/**
 * 获赞列表页（点赞过该用户帖子的用户列表）
 *
 * 路由：/user/:id/likers
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import EmptyState from '../components/common/EmptyState.vue'
import BadgeIcon from '../components/common/BadgeIcon.vue'
import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import { fetchUser, fetchUserLikers } from '../api/user'
import { followUser, unfollowUser } from '../api/follow'
import { useSessionStore } from '../stores/session'
import type { Profile } from '../types/api'
import type { Badge } from '../types/api'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()

const userId = computed(() => Number(route.params.id))
const profile = ref<Profile | null>(null)

interface Liker {
  id: number
  nickname: string
  avatar_url: string | null
  badge?: Badge | null
  bio: string | null
  school: string | null
  /** @deprecated 已弃用，改用 age */
  grade: string | null
  age: number | null
  created_at: string | null
  post_id: number | null
  post_content: string | null
  is_following: boolean
  loading?: boolean
}

const likers = ref<Liker[]>([])
const loading = ref(false)

const displayName = computed(() => profile.value?.nickname || `用户 ${userId.value || ''}`.trim())
const pageTitle = computed(() => {
  return `${displayName.value}的获赞`
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

async function loadLikers() {
  if (!userId.value || isNaN(userId.value)) return
  loading.value = true
  try {
    const { data } = await fetchUserLikers(userId.value)
    likers.value = (data.data || []).map((u: Liker) => ({ ...u, loading: false }))
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

async function toggleFollow(liker: Liker) {
  if (!session.userId) {
    toast.info('请先登录')
    return
  }
  if (liker.id === session.userId) return
  liker.loading = true
  try {
    if (liker.is_following) {
      await unfollowUser(liker.id)
      liker.is_following = false
    } else {
      await followUser(liker.id)
      liker.is_following = true
    }
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    liker.loading = false
  }
}

function openUser(id: number) {
  router.push(`/user/${id}`)
}

function openPost(postId: number | null) {
  if (postId) router.push(`/post/${postId}`)
}

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push(`/user/${userId.value}`)
}

function timeAgo(dateStr?: string | null): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const now = new Date()
  const diff = (now.getTime() - d.getTime()) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  if (diff < 604800) return `${Math.floor(diff / 86400)}天前`
  return d.toLocaleDateString()
}

onMounted(async () => {
  // 性能优化：validateSession 与业务请求并行，不阻塞
  void session.validateSession()
  await Promise.all([loadProfile(), loadLikers()])
})

watch(userId, () => {
  if (!userId.value || isNaN(userId.value)) return
  loadProfile()
  loadLikers()
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
      <div v-if="loading && !likers.length" class="loading-tip">
        <Icon name="refresh" :size="20" />
        <span>加载中…</span>
      </div>

      <div v-else-if="likers.length" class="liker-list">
        <div v-for="liker in likers" :key="liker.id" class="liker-item">
          <div
            class="liker-avatar"
            :style="
              liker.avatar_url
                ? { backgroundImage: `url(${liker.avatar_url})` }
                : { background: avatarGradient(liker.id) }
            "
            @click="openUser(liker.id)"
          >
            <span v-if="!liker.avatar_url">{{ liker.nickname.charAt(0).toUpperCase() }}</span>
          </div>
          <div class="liker-info" @click="openUser(liker.id)">
            <span class="liker-name">
              <BadgeIcon :badge="liker.badge" :size="14" />
              {{ liker.nickname }}
            </span>
            <span v-if="liker.bio" class="liker-bio">{{ liker.bio }}</span>
            <span v-else-if="liker.school" class="liker-bio">{{ liker.school }}</span>
            <span v-if="liker.post_content" class="liker-source" @click.stop="openPost(liker.post_id)">
              <Icon name="heart" :size="10" />
              <span>点赞了 {{ liker.post_content }}</span>
            </span>
            <span class="liker-time">{{ timeAgo(liker.created_at) }}</span>
          </div>
          <button
            v-if="liker.id !== session.userId"
            class="follow-btn"
            :class="{ 'is-following': liker.is_following }"
            type="button"
            :disabled="liker.loading"
            @click="toggleFollow(liker)"
          >
            {{ liker.is_following ? '已关注' : '关注' }}
          </button>
        </div>
      </div>

      <EmptyState v-else icon="heart" text="还没有人点赞过" />
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
  padding: 8px 0 calc(80px + env(safe-area-inset-bottom));
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

.liker-list {
  background: var(--bg-50);
  margin: 8px 16px 0;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  overflow: hidden;
}
.liker-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 0.5px solid var(--bg-200);
}
.liker-item:last-child {
  border-bottom: none;
}
.liker-avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  color: #fff;
  display: grid;
  place-items: center;
  font-size: 17px;
  font-weight: 700;
  flex-shrink: 0;
  background-size: cover;
  background-position: center;
  text-transform: uppercase;
  cursor: pointer;
}
.liker-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
  cursor: pointer;
}
.liker-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-800);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.liker-bio {
  font-size: 12px;
  color: var(--text-400);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.liker-source {
  font-size: 11px;
  color: var(--text-500);
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 2px;
  color: #ff3b30;
  cursor: pointer;
}
.liker-source span {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
}
.liker-time {
  font-size: 10px;
  color: var(--text-300);
  margin-top: 2px;
}
.follow-btn {
  padding: 6px 14px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  background: var(--brand-500);
  color: white;
  flex-shrink: 0;
  transition: all 0.15s;
}
.follow-btn.is-following {
  background: var(--bg-200);
  color: var(--text-600);
}
.follow-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

@media (max-width: 768px) {
  .list-header {
    height: 48px;
    padding: 0 12px;
  }
  .liker-list {
    margin: 8px 12px 0;
  }
  .liker-item {
    padding: 12px 14px;
  }
}
</style>
