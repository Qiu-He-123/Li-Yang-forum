<script setup lang="ts">
/**
 * 关注 / 粉丝列表页（同一组件，按路由名区分）
 *
 * 路由：
 * - /user/:id/followers  -> 粉丝列表
 * - /user/:id/following  -> 关注列表
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import EmptyState from '../components/common/EmptyState.vue'
import BadgeIcon from '../components/common/BadgeIcon.vue'
import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import { fetchUser } from '../api/user'
import { listFollowers, listFollowing, followUser, unfollowUser } from '../api/follow'
import { useSessionStore } from '../stores/session'
import type { FollowUser, Profile } from '../types/api'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()

const userId = computed(() => Number(route.params.id))
const isFollowers = computed(() => route.name === 'user-followers')

const profile = ref<Profile | null>(null)
const users = ref<(FollowUser & { loading?: boolean })[]>([])
const loading = ref(false)

const displayName = computed(() => profile.value?.nickname || `用户 ${userId.value || ''}`.trim())
const pageTitle = computed(() => {
  return `${displayName.value}的${isFollowers.value ? '粉丝' : '关注'}`
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

async function loadList() {
  if (!userId.value || isNaN(userId.value)) return
  loading.value = true
  try {
    const api = isFollowers.value ? listFollowers : listFollowing
    const { data } = await api(userId.value)
    users.value = (data.data || []).map((u) => ({ ...u, loading: false }))
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

async function toggleFollow(user: FollowUser & { loading?: boolean }) {
  if (!session.userId) {
    toast.info('请先登录')
    return
  }
  if (user.id === session.userId) return
  user.loading = true
  try {
    if (user.is_following) {
      await unfollowUser(user.id)
      user.is_following = false
    } else {
      await followUser(user.id)
      user.is_following = true
    }
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    user.loading = false
  }
}

function openUser(targetUserId: number) {
  router.push(`/user/${targetUserId}`)
}

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push(`/user/${userId.value}`)
}

onMounted(async () => {
  // 性能优化：validateSession 与业务请求并行，不阻塞
  void session.validateSession()
  await Promise.all([loadProfile(), loadList()])
})

watch([userId, isFollowers], () => {
  if (!userId.value || isNaN(userId.value)) return
  loadProfile()
  loadList()
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
      <div v-if="loading && !users.length" class="loading-tip">
        <Icon name="refresh" :size="20" />
        <span>加载中…</span>
      </div>

      <div v-else-if="users.length" class="user-list">
        <div v-for="user in users" :key="user.id" class="user-item" @click="openUser(user.id)">
          <div
            class="user-avatar"
            :style="
              user.avatar_url
                ? { backgroundImage: `url(${user.avatar_url})` }
                : { background: avatarGradient(user.id) }
            "
          >
            <span v-if="!user.avatar_url">{{ user.nickname.charAt(0).toUpperCase() }}</span>
          </div>
          <div class="user-info">
            <span class="user-name">
              <BadgeIcon :badge="user.badge" :size="14" />
              {{ user.nickname }}
            </span>
            <span v-if="user.bio" class="user-bio">{{ user.bio }}</span>
            <span v-else-if="user.school" class="user-bio">{{ user.school }}</span>
          </div>
          <button
            v-if="user.id !== session.userId"
            class="follow-btn"
            :class="{ 'is-following': user.is_following }"
            type="button"
            :disabled="user.loading"
            @click.stop="toggleFollow(user)"
          >
            {{ user.is_following ? '已关注' : '关注' }}
          </button>
        </div>
      </div>

      <EmptyState
        v-else
        :icon="isFollowers ? 'users' : 'user-check'"
        :text="isFollowers ? '还没有粉丝' : '还没有关注任何人'"
      />
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
  padding: 8px 0 0;
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

.user-list {
  background: var(--bg-50);
  margin: 8px 16px 0;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  overflow: hidden;
}
.user-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 0.5px solid var(--bg-200);
  cursor: pointer;
  transition: background 0.15s;
}
.user-item:last-child {
  border-bottom: none;
}
.user-item:hover {
  background: var(--bg-100);
}
.user-avatar {
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
}
.user-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.user-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-800);
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.user-bio {
  font-size: 12px;
  color: var(--text-400);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
  .user-list {
    margin: 8px 12px 0;
  }
  .user-item {
    padding: 12px 14px;
  }
}
</style>
