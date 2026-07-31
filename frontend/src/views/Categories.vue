<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

import AppHeader from '../components/header/AppHeader.vue'
import { useSessionStore } from '../stores/session'

const router = useRouter()
const session = useSessionStore()

// 与 PostEditor 的 categories 保持一致
const categories = [
  { name: '普通', icon: '📝', desc: '日常动态' },
  { name: '表白', icon: '💌', desc: '心动告白' },
  { name: '树洞', icon: '🌳', desc: '匿名倾诉' },
  { name: '失物招领', icon: '🔍', desc: '丢失/拾到' },
  { name: '二手', icon: '📦', desc: '闲置交易' },
  { name: '学习', icon: '📚', desc: '课业交流' },
  { name: '活动', icon: '🎉', desc: '校园活动' },
  { name: '吐槽', icon: '💭', desc: '吐槽发泄' },
]

function enterCategory(name: string) {
  router.push({ path: '/', query: { category: name } })
}

onMounted(() => {
  if (!session.userId) {
    // 未登录也允许浏览分类入口，点击进入时再拦截
  }
})
</script>

<template>
  <main class="min-h-screen pb-16 lg:pb-0">
    <AppHeader />
    <div class="mx-auto max-w-3xl px-4 py-5">
      <h2 class="mb-4 text-lg font-black">选择版块</h2>
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <button
          v-for="cat in categories"
          :key="cat.name"
          class="focus-ring flex flex-col items-center gap-2 rounded border border-ly-line bg-white p-5 transition hover:border-ly-green hover:bg-ly-paper"
          @click="enterCategory(cat.name)"
        >
          <span class="text-3xl">{{ cat.icon }}</span>
          <span class="text-base font-bold">{{ cat.name }}</span>
          <span class="text-xs text-slate-500">{{ cat.desc }}</span>
        </button>
      </div>
    </div>
  </main>
</template>
