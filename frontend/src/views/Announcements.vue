<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import AppHeader from '../components/header/AppHeader.vue'
import EmptyState from '../components/common/EmptyState.vue'
import type { Announcement } from '../types/api'

const router = useRouter()
const announcements = ref<Announcement[]>([])

onMounted(async () => {
  try {
    const { listAnnouncements } = await import('../api/announcement')
    const { data } = await listAnnouncements()
    announcements.value = data.data
  } catch {
    announcements.value = []
  }
})
</script>

<template>
  <main class="min-h-screen pb-16 lg:pb-0">
    <AppHeader />
    <div class="mx-auto max-w-3xl px-4 py-5">
      <h2 class="mb-3 text-lg font-black">公告</h2>
      <div v-if="announcements.length" class="space-y-3">
        <div
          v-for="item in announcements"
          :key="item.id"
          class="rounded border border-ly-line bg-white p-4"
        >
          <h3 class="m-0 text-base font-bold">{{ item.title }}</h3>
          <p v-if="item.created_at" class="m-0 mt-1 text-xs text-slate-400">{{ item.created_at }}</p>
          <p class="m-0 mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">{{ item.content }}</p>
        </div>
      </div>
      <EmptyState v-else text="暂无公告" />
    </div>
  </main>
</template>
