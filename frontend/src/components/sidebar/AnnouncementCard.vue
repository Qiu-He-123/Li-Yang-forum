<script setup lang="ts">
import { useAnnouncementStore } from '../../stores/announcement'

const announcementStore = useAnnouncementStore()
</script>

<template>
  <div class="overflow-hidden rounded-lg border border-tie-line bg-white">
    <div class="border-b border-tie-line px-3 py-2.5">
      <h2 class="tie-module-title m-0 text-sm font-bold text-tie-ink">公告</h2>
    </div>
    <div class="p-2.5">
      <div v-if="announcementStore.announcements.length" class="space-y-1.5">
        <div
          v-for="item in announcementStore.announcements.slice(0, 5)"
          :key="item.id"
          class="rounded-md bg-tie-fill px-2.5 py-2"
        >
          <p class="m-0 text-[13px] font-semibold text-tie-text">{{ item.title }}</p>
          <p class="m-0 mt-1 line-clamp-2 text-xs leading-5 text-tie-sub">{{ item.content }}</p>
        </div>
      </div>
      <p v-else-if="announcementStore.loaded" class="px-1 py-2 text-center text-xs text-tie-sub">暂无公告</p>
      <p v-else class="px-1 py-2 text-center text-xs text-tie-sub">加载中...</p>
    </div>
  </div>
</template>
