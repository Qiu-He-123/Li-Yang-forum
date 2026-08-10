<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'

import { usePostStore } from '../../stores/post'
import MarkdownText from '../common/MarkdownText.vue'

const postStore = usePostStore()
const router = useRouter()

// 取当前列表中热度（赞 + 评论）最高的 8 条作为热帖榜
const hotPosts = computed(() =>
  [...postStore.posts]
    .sort((a, b) => b.like_count + b.comment_count - (a.like_count + a.comment_count))
    .slice(0, 8),
)

function goDetail(id: number) {
  router.push(`/post/${id}`)
}
</script>

<template>
  <div class="rounded-lg border border-tie-line bg-white">
    <div class="border-b border-tie-line px-3 py-2.5">
      <h2 class="tie-module-title m-0 text-sm font-bold text-tie-ink">热帖榜</h2>
    </div>
    <div v-if="hotPosts.length" class="p-2">
      <button
        v-for="(post, i) in hotPosts"
        :key="post.id"
        class="group focus-ring flex w-full items-start gap-2.5 rounded-md px-2 py-2 text-left transition hover:bg-tie-50"
        @click="goDetail(post.id)"
      >
        <span
          class="mt-0.5 grid h-4 w-4 flex-none place-items-center rounded text-[11px] font-bold"
          :class="i < 3 ? 'bg-tie-orange text-white' : 'bg-tie-fill text-tie-sub'"
        >
          {{ i + 1 }}
        </span>
        <span class="min-w-0 flex-1">
          <MarkdownText :content="post.content" class="line-clamp-1 text-[13px] leading-5 text-tie-text transition group-hover:text-tie-blue" :clamp="1" />
          <span class="mt-0.5 flex items-center gap-1 text-[11px] text-tie-sub">
            <span v-if="post.is_public === false" class="rounded-full bg-amber-100 px-1.5 py-0.5 font-semibold text-amber-700">已私密</span>
            <span>赞 {{ post.like_count }} · 回复 {{ post.comment_count }}</span>
          </span>
        </span>
      </button>
    </div>
    <p v-else class="px-3 py-4 text-center text-xs text-tie-sub">暂无热帖</p>
  </div>
</template>
