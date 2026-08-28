<script setup lang="ts">
import { Flag, HomeFilled, MessageBox, Star, User } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { computed } from 'vue'

import { useSessionStore } from '../../stores/session'
import { usePostStore } from '../../stores/post'

const router = useRouter()
const session = useSessionStore()
const postStore = usePostStore()

interface MenuItem {
  label: string
  icon: typeof HomeFilled
  action: () => void
  active?: () => boolean
}

const items = computed<MenuItem[]>(() => [
  {
    label: '首页',
    icon: HomeFilled,
    action: () => router.push('/'),
    active: () => router.currentRoute.value.path === '/' && postStore.activeView === 'all' && !postStore.activeCategory,
  },
  {
    label: '我的校区',
    icon: HomeFilled,
    action: () => {
      if (!session.userId) return
      // P0-Bug#1：setView 后必须显式 loadPosts，否则列表不刷新
      postStore.setView('school')
      router.push('/').then(() => postStore.loadPosts())
    },
    active: () => router.currentRoute.value.path === '/' && postStore.activeView === 'school' && !postStore.activeCategory,
  },
  {
    label: '热门',
    icon: Star,
    action: () => {
      // P0-Bug#1：setView 后必须显式 loadPosts
      postStore.setView('hot')
      router.push('/').then(() => postStore.loadPosts())
    },
    active: () => router.currentRoute.value.path === '/' && postStore.activeView === 'hot' && !postStore.activeCategory,
  },
  {
    label: '树洞',
    icon: MessageBox,
    action: () => router.push({ path: '/', query: { category: '树洞' } }),
    active: () => router.currentRoute.value.path === '/' && postStore.activeCategory === '树洞',
  },
  {
    label: '表白',
    icon: Flag,
    action: () => router.push({ path: '/', query: { category: '表白' } }),
    active: () => router.currentRoute.value.path === '/' && postStore.activeCategory === '表白',
  },
  {
    label: '二手',
    icon: MessageBox,
    action: () => router.push({ path: '/', query: { category: '二手' } }),
    active: () => router.currentRoute.value.path === '/' && postStore.activeCategory === '二手',
  },
  {
    label: '失物招领',
    icon: Flag,
    action: () => router.push({ path: '/', query: { category: '失物招领' } }),
    active: () => router.currentRoute.value.path === '/' && postStore.activeCategory === '失物招领',
  },
  {
    label: '公告',
    icon: HomeFilled,
    action: () => router.push('/announcements'),
  },
  {
    label: '个人中心',
    icon: User,
    action: () => {
      if (session.userId) {
        router.push(`/user/${session.userId}`)
      } else {
        router.push('/')
      }
    },
  },
])

function onMenuClick(item: MenuItem) {
  item.action()
}

function isActive(item: MenuItem): boolean {
  return item.active ? item.active() : false
}
</script>

<template>
  <aside class="space-y-2">
    <button
      v-for="item in items"
      :key="item.label"
      class="focus-ring flex h-10 w-full items-center gap-2 rounded border px-3 text-left text-sm font-semibold"
      :class="isActive(item) ? 'border-ly-green bg-ly-paper text-ly-green' : 'border-transparent hover:border-ly-line hover:bg-white'"
      @click="onMenuClick(item)"
    >
      <el-icon><component :is="item.icon" /></el-icon>
      {{ item.label }}
    </button>
  </aside>
</template>
