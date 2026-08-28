<script setup lang="ts">
import { computed } from 'vue'

import { usePostStore } from '../../stores/post'
import { useSchoolStore } from '../../stores/school'

const postStore = usePostStore()
const schoolStore = useSchoolStore()

const schoolCount = computed(() => schoolStore.schools.length)
const postCount = computed(() => postStore.posts.length)
</script>

<template>
  <div class="overflow-hidden rounded-lg border border-tie-line bg-white">
    <div class="border-b border-tie-line px-3 py-2.5">
      <h2 class="tie-module-title m-0 text-sm font-bold text-tie-ink">今日数据</h2>
    </div>
    <div class="grid grid-cols-2 divide-x divide-tie-line">
      <div class="py-3 text-center">
        <b class="block text-xl text-tie-blue">{{ postCount }}</b>
        <span class="text-[11px] text-tie-sub">本页帖子</span>
      </div>
      <div class="py-3 text-center">
        <b class="block text-xl text-tie-blue">{{ schoolCount }}</b>
        <span class="text-[11px] text-tie-sub">校区</span>
      </div>
    </div>
  </div>
</template>
