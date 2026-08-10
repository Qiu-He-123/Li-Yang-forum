<script setup lang="ts">
/**
 * 好友/通讯录页面（Apple HIG 风格）
 * - 顶部固定栏：返回 + 标题「通讯录」+ 设置图标
 * - 搜索栏：常驻顶部，输入关键词搜索用户添加好友
 * - Tab 切换：好友 / 新的朋友（好友请求）
 * - 圆形渐变头像 + 卡片布局 + 带图标按钮
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import EmptyState from '../components/common/EmptyState.vue'
import BadgeIcon from '../components/common/BadgeIcon.vue'
import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import type { FriendItem, FriendRequestItem, SearchUserResult } from '../api/friend'
import {
  acceptFriendRequest,
  listFriendRequests,
  listFriends,
  rejectFriendRequest,
  searchUsers,
  sendFriendRequest,
} from '../api/friend'
import { useSessionStore } from '../stores/session'

const router = useRouter()
const session = useSessionStore()

const friends = ref<FriendItem[]>([])
const incomingRequests = ref<FriendRequestItem[]>([])
const activeTab = ref<'friends' | 'requests'>('friends')
const searchKeyword = ref('')
const searchResults = ref<SearchUserResult[]>([])
const searching = ref(false)
const hasSearched = ref(false)

let pollTimer: ReturnType<typeof setInterval> | null = null

// 头像渐变（与 UserHome.vue 保持一致）
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

async function loadFriends(showLoading = true) {
  if (!session.userId) return
  try {
    const { data } = await listFriends({
      showGlobalLoading: false,
      showGlobalError: false,
    })
    friends.value = data.data || []
  } catch {
    /* ignore */
  }
}

async function loadRequests(showLoading = true) {
  if (!session.userId) return
  try {
    const { data } = await listFriendRequests('incoming', {
      showGlobalLoading: false,
      showGlobalError: false,
    })
    incomingRequests.value = data.data || []
  } catch {
    /* ignore */
  }
}

async function onSearch() {
  const kw = searchKeyword.value.trim()
  if (!kw) {
    searchResults.value = []
    hasSearched.value = false
    return
  }
  searching.value = true
  hasSearched.value = true
  try {
    const { data } = await searchUsers(kw, {
      showGlobalLoading: false,
      showGlobalError: false,
    })
    searchResults.value = data.data || []
  } catch {
    /* ignore */
  } finally {
    searching.value = false
  }
}

function clearSearch() {
  searchKeyword.value = ''
  searchResults.value = []
  hasSearched.value = false
}

async function onAddFriend(userId: number) {
  try {
    await sendFriendRequest(userId, '你好，我想加你为好友')
    toast.success('好友请求已发送')
    await onSearch()
  } catch (err) {
    toast.error((err as Error).message)
  }
}

async function onAccept(requestId: number) {
  try {
    await acceptFriendRequest(requestId)
    toast.success('已添加好友')
    await loadRequests()
    await loadFriends()
  } catch (err) {
    toast.error((err as Error).message)
  }
}

async function onReject(requestId: number) {
  try {
    await rejectFriendRequest(requestId)
    toast.success('已拒绝')
    await loadRequests()
  } catch (err) {
    toast.error((err as Error).message)
  }
}

function openChat(friendId: number) {
  router.push(`/chat/${friendId}`)
}

function timeAgo(dateStr?: string | null): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const now = new Date()
  const diff = (now.getTime() - d.getTime()) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  return d.toLocaleDateString()
}

const requestCount = computed(() => incomingRequests.value.length)
const showSearchResults = computed(() => hasSearched.value && searchKeyword.value.trim().length > 0)

// 轮询
onMounted(async () => {
  // 性能优化：validateSession 与业务请求并行；loadFriends/loadRequests 也并行
  void session.validateSession()
  await Promise.all([loadFriends(), loadRequests()])
  pollTimer = setInterval(() => {
    loadFriends(false)
    loadRequests(false)
  }, 10000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <main class="page-friends">
    <!-- ====== 顶部固定栏 ====== -->
    <header class="site-header" role="banner">
      <div class="header-inner">
        <div class="header-side header-side--left">
          <button class="icon-btn" type="button" aria-label="返回" @click="router.back()">
            <Icon name="arrow-left" :size="20" />
          </button>
        </div>
        <h1 class="header-title">通讯录</h1>
        <div class="header-side header-side--right">
          <button class="icon-btn" type="button" aria-label="设置" @click="router.push('/settings')">
            <Icon name="settings" :size="18" />
          </button>
        </div>
      </div>
    </header>

    <!-- ====== 主内容 ====== -->
    <div class="page-container">
      <!-- ====== 搜索栏（常驻）====== -->
      <div class="search-card">
        <div class="search-wrap">
          <Icon name="search" :size="16" color="var(--text-400)" />
          <input
            v-model="searchKeyword"
            class="search-input"
            type="text"
            placeholder="搜索用户昵称添加好友"
            @keydown.enter="onSearch"
          />
          <button
            v-if="searchKeyword"
            class="search-clear"
            type="button"
            aria-label="清空"
            @click="clearSearch"
          >
            <Icon name="x" :size="14" color="var(--text-400)" />
          </button>
        </div>
        <button
          v-if="searchKeyword"
          class="search-btn"
          type="button"
          :disabled="searching"
          @click="onSearch"
        >
          {{ searching ? '搜索中' : '搜索' }}
        </button>
      </div>

      <!-- ====== 搜索结果 ====== -->
      <section v-if="showSearchResults" class="result-section" aria-label="搜索结果">
        <div class="section-head">
          <h2 class="section-title">
            <span class="section-title-dot" aria-hidden="true"></span>
            搜索结果
          </h2>
          <button class="section-more" type="button" @click="clearSearch">
            关闭
            <Icon name="x" :size="13" />
          </button>
        </div>

        <div v-if="searching" class="loading-tip">
          <Icon name="refresh" :size="20" />
          <span>搜索中…</span>
        </div>

        <div v-else-if="searchResults.length" class="card-list">
          <div
            v-for="item in searchResults"
            :key="item.user.id"
            class="user-card"
          >
            <div
              class="user-avatar"
              :style="
                item.user.avatar_url
                  ? { backgroundImage: `url(${item.user.avatar_url})` }
                  : { background: avatarGradient(item.user.id) }
              "
            >
              <span v-if="!item.user.avatar_url">{{ item.user.nickname.charAt(0).toUpperCase() }}</span>
            </div>
            <div class="user-info">
              <span class="user-name">
                <BadgeIcon :badge="item.user.badge" :size="14" />
                {{ item.user.nickname }}
              </span>
              <span v-if="item.user.username" class="user-account">@{{ item.user.username }}</span>
              <span class="user-bio">
                <span v-if="item.user.school">{{ item.user.school }}</span>
                <span v-if="item.user.age !== null && item.user.age !== undefined && item.user.school"> · </span>
                <span v-if="item.user.age !== null && item.user.age !== undefined">{{ item.user.age }} 岁</span>
                <span v-if="!item.user.school && (item.user.age === null || item.user.age === undefined) && item.user.bio">{{ item.user.bio }}</span>
              </span>
            </div>
            <!-- 关系状态按钮 -->
            <button
              v-if="item.relation === 'none'"
              class="action-btn action-btn--primary"
              type="button"
              @click="onAddFriend(item.user.id)"
            >
              <Icon name="user-plus" :size="14" />
              <span>添加</span>
            </button>
            <button
              v-else-if="item.relation === 'pending_sent'"
              class="action-btn action-btn--disabled"
              type="button"
              disabled
            >
              <Icon name="clock" :size="14" />
              <span>已发送</span>
            </button>
            <button
              v-else-if="item.relation === 'pending_received'"
              class="action-btn action-btn--success"
              type="button"
              @click="onAccept(item.request_id!)"
            >
              <Icon name="check" :size="14" />
              <span>接受</span>
            </button>
            <button
              v-else-if="item.relation === 'friend'"
              class="action-btn action-btn--outline"
              type="button"
              @click="openChat(item.user.id)"
            >
              <Icon name="message-square" :size="14" />
              <span>发消息</span>
            </button>
          </div>
        </div>

        <EmptyState v-else icon="search" text="未找到相关用户，换个关键词试试" />
      </section>

      <!-- ====== 好友 / 请求 Tab ====== -->
      <template v-else>
        <div class="friends-tabs" role="tablist" aria-label="通讯录切换">
          <button
            class="friends-tab"
            :class="{ 'is-active': activeTab === 'friends' }"
            type="button"
            role="tab"
            :aria-selected="activeTab === 'friends'"
            @click="activeTab = 'friends'"
          >
            <Icon name="users" :size="15" />
            <span>好友</span>
            <span v-if="friends.length" class="tab-count">{{ friends.length }}</span>
          </button>
          <button
            class="friends-tab"
            :class="{ 'is-active': activeTab === 'requests' }"
            type="button"
            role="tab"
            :aria-selected="activeTab === 'requests'"
            @click="activeTab = 'requests'"
          >
            <Icon name="user-plus" :size="15" />
            <span>新的朋友</span>
            <span v-if="requestCount" class="tab-badge">{{ requestCount }}</span>
          </button>
        </div>

        <!-- ====== 好友请求列表 ====== -->
        <section v-if="activeTab === 'requests'" class="list-section" aria-label="好友请求">
          <div v-if="!incomingRequests.length" class="empty-wrap">
            <EmptyState icon="user-plus" text="暂无好友请求" />
          </div>
          <div v-else class="card-list">
            <div
              v-for="req in incomingRequests"
              :key="req.id"
              class="user-card user-card--request"
            >
              <div
                class="user-avatar"
                :style="
                  req.user.avatar_url
                    ? { backgroundImage: `url(${req.user.avatar_url})` }
                    : { background: avatarGradient(req.user.id) }
                "
              >
                <span v-if="!req.user.avatar_url">{{ req.user.nickname.charAt(0).toUpperCase() }}</span>
              </div>
              <div class="user-info">
                <span class="user-name">
                  <BadgeIcon :badge="req.user.badge" :size="14" />
                  {{ req.user.nickname }}
                </span>
                <span class="user-bio">{{ req.message || '请求加你为好友' }}</span>
              </div>
              <div class="request-actions">
                <button class="action-btn action-btn--success" type="button" @click="onAccept(req.id)">
                  <Icon name="check" :size="14" />
                  <span>接受</span>
                </button>
                <button class="action-btn action-btn--ghost" type="button" @click="onReject(req.id)">
                  <Icon name="x" :size="14" />
                  <span>拒绝</span>
                </button>
              </div>
            </div>
          </div>
        </section>

        <!-- ====== 好友列表 ====== -->
        <section v-if="activeTab === 'friends'" class="list-section" aria-label="好友列表">
          <div v-if="!friends.length" class="empty-wrap">
            <EmptyState icon="users" text="暂无好友，去搜索添加吧" />
          </div>
          <div v-else class="card-list">
            <div
              v-for="f in friends"
              :key="f.user.id"
              class="user-card"
              @click="openChat(f.user.id)"
            >
              <div
                class="user-avatar"
                :style="
                  f.user.avatar_url
                    ? { backgroundImage: `url(${f.user.avatar_url})` }
                    : { background: avatarGradient(f.user.id) }
                "
              >
                <span v-if="!f.user.avatar_url">{{ f.user.nickname.charAt(0).toUpperCase() }}</span>
              </div>
              <div class="user-info">
                <span class="user-name">
                  <BadgeIcon :badge="f.user.badge" :size="14" />
                  {{ f.user.nickname }}
                </span>
                <span class="user-bio">{{ f.last_message || f.user.bio || '点击开始聊天' }}</span>
              </div>
              <div class="friend-meta">
                <span v-if="f.last_time" class="friend-time">{{ timeAgo(f.last_time) }}</span>
                <span v-if="f.unread_count > 0" class="unread-badge">{{ f.unread_count }}</span>
              </div>
            </div>
          </div>
        </section>
      </template>
    </div>
  </main>
</template>

<style scoped>
*, *::before, *::after { box-sizing: border-box; }

.page-friends {
  min-height: 100vh;
  background: var(--bg-100);
  padding-top: 56px;
  padding-bottom: calc(56px + 28px + env(safe-area-inset-bottom));
  color: var(--text-800);
  font-family: var(--font-sans, inherit);
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* ====== SITE HEADER ====== */
.site-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  height: 56px;
  background: var(--bg-50);
  border-bottom: 0.5px solid var(--bg-300);
}
.header-inner {
  max-width: 640px;
  margin: 0 auto;
  height: 100%;
  padding: 0 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.header-side {
  display: flex;
  align-items: center;
  min-width: 36px;
}
.header-side--right { justify-content: flex-end; }
.header-title {
  flex: 1;
  text-align: center;
  font-size: 17px;
  font-weight: 700;
  color: var(--text-800);
  letter-spacing: -0.01em;
  margin: 0;
}
.icon-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: transparent;
  color: var(--text-700);
  display: grid;
  place-items: center;
  cursor: pointer;
  transition: background 0.15s;
}
.icon-btn:hover { background: var(--bg-100); }

/* ====== PAGE CONTAINER ====== */
.page-container {
  max-width: 640px;
  margin: 0 auto;
  padding: 12px 16px 0;
}

/* ====== SEARCH CARD ====== */
.search-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  margin-bottom: 14px;
}
.search-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--bg-100);
  border-radius: var(--radius-md);
  padding: 8px 12px;
  min-width: 0;
}
.search-input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-size: 15px;
  color: var(--text-800);
  font-family: inherit;
  min-width: 0;
}
.search-input::placeholder { color: var(--text-400); }
.search-clear {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: none;
  background: var(--bg-300);
  color: var(--text-400);
  display: grid;
  place-items: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s;
}
.search-clear:hover { background: var(--bg-400); }
.search-btn {
  padding: 8px 16px;
  border: none;
  border-radius: var(--radius-md);
  background: var(--brand-500);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  flex-shrink: 0;
  transition: background 0.15s;
}
.search-btn:hover { background: var(--brand-600); }
.search-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* ====== SECTION HEAD ====== */
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  padding: 0 4px;
}
.section-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-800);
  margin: 0;
}
.section-title-dot {
  width: 4px;
  height: 16px;
  border-radius: 2px;
  background: var(--brand-500);
}
.section-more {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 13px;
  color: var(--text-400);
  background: none;
  border: none;
  cursor: pointer;
  font-family: inherit;
  padding: 4px 6px;
  border-radius: var(--radius-sm);
  transition: color 0.15s, background 0.15s;
}
.section-more:hover { color: var(--brand-500); background: var(--brand-50); }

/* ====== LOADING ====== */
.loading-tip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 0;
  color: var(--text-400);
  font-size: 14px;
}

/* ====== TABS ====== */
.friends-tabs {
  display: flex;
  gap: 6px;
  padding: 4px;
  background: var(--bg-200);
  border-radius: var(--radius-md);
  margin-bottom: 14px;
}
.friends-tab {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 12px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-500);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  position: relative;
  transition: color 0.15s, background 0.15s;
}
.friends-tab.is-active {
  background: var(--bg-50);
  color: var(--brand-500);
  box-shadow: var(--shadow-xs);
}
.tab-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: var(--bg-300);
  color: var(--text-600);
  font-size: 11px;
  font-weight: 700;
}
.friends-tab.is-active .tab-count {
  background: var(--brand-50);
  color: var(--brand-600);
}
.tab-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: var(--error);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}

/* ====== CARD LIST ====== */
.card-list {
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  overflow: hidden;
}
.user-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 0.5px solid var(--bg-200);
  cursor: pointer;
  transition: background 0.15s;
}
.user-card:last-child { border-bottom: none; }
.user-card:hover { background: var(--bg-100); }
.user-card--request { cursor: default; }
.user-card--request:hover { background: var(--bg-50); }

/* ====== AVATAR ====== */
.user-avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background-size: cover;
  background-position: center;
  display: grid;
  place-items: center;
  color: #fff;
  font-size: 17px;
  font-weight: 700;
  flex-shrink: 0;
  text-transform: uppercase;
}

/* ====== USER INFO ====== */
.user-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
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
.user-account {
  font-size: 12px;
  color: var(--text-500);
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

/* ====== FRIEND META ====== */
.friend-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  flex-shrink: 0;
}
.friend-time {
  font-size: 11px;
  color: var(--text-300);
}
.unread-badge {
  background: var(--error);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 999px;
  min-width: 18px;
  text-align: center;
  line-height: 1.4;
}

/* ====== ACTION BUTTONS ====== */
.action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 7px 14px;
  border: none;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  flex-shrink: 0;
  font-family: inherit;
  transition: background 0.15s, transform 0.15s;
}
.action-btn:active { transform: scale(0.96); }
.action-btn--primary {
  background: var(--brand-500);
  color: #fff;
}
.action-btn--primary:hover { background: var(--brand-600); }
.action-btn--success {
  background: #34c759;
  color: #fff;
}
.action-btn--success:hover { background: #2bb24c; }
.action-btn--outline {
  background: var(--bg-100);
  color: var(--text-700);
}
.action-btn--outline:hover { background: var(--bg-200); }
.action-btn--ghost {
  background: transparent;
  color: var(--text-500);
  border: 1px solid var(--bg-300);
}
.action-btn--ghost:hover { background: var(--bg-100); }
.action-btn--disabled {
  background: var(--bg-100);
  color: var(--text-400);
  cursor: not-allowed;
}
.action-btn--disabled:active { transform: none; }

/* ====== REQUEST ACTIONS ====== */
.request-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.request-actions .action-btn {
  padding: 7px 12px;
  font-size: 12px;
}

/* ====== EMPTY ====== */
.empty-wrap {
  padding: 20px 0;
}
.list-section {
  min-height: 200px;
}

/* ====== RESULT SECTION ====== */
.result-section {
  margin-top: 0;
}

/* ====== RESPONSIVE ====== */
@media (max-width: 768px) {
  .page-container { padding: 10px 12px 0; }
  .user-card { padding: 12px 14px; }
  .user-avatar { width: 40px; height: 40px; font-size: 15px; }
  .user-name { font-size: 14px; }
  .user-bio { font-size: 11px; }
  .action-btn { padding: 6px 12px; font-size: 12px; }
}
</style>
