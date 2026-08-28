<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <main class="grid min-h-screen place-items-center bg-ly-paper">
    <div class="text-center">
      <p class="text-9xl font-black text-ly-green">404</p>
      <p class="mt-2 text-base text-slate-600">页面走丢了</p>
      <el-button class="mt-6" type="primary" @click="router.push('/')">返回首页</el-button>
    </div>
  </main>
</template>
