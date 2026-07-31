<script setup lang="ts">
import { useUserStore } from '../../stores/user'
import { useSessionStore } from '../../stores/session'
import { useUIStore } from '../../stores/ui'

const userStore = useUserStore()
const session = useSessionStore()
const uiStore = useUIStore()
</script>

<template>
  <div class="overflow-hidden rounded-lg border border-tie-line bg-white">
    <div class="border-b border-tie-line px-3 py-2.5">
      <h2 class="tie-module-title m-0 text-sm font-bold text-tie-ink">个人主页</h2>
    </div>
    <div class="p-3">
      <template v-if="userStore.profile">
        <div class="flex items-center gap-3">
          <el-avatar :size="44" :src="userStore.profile.avatar_url || undefined">
            {{ userStore.profile.nickname?.[0] || '?' }}
          </el-avatar>
          <div class="min-w-0">
            <p class="m-0 truncate text-[15px] font-bold text-tie-ink">{{ userStore.profile.nickname }}</p>
            <p class="m-0 truncate text-xs text-tie-sub">
              {{ userStore.profile.uid }} · {{ userStore.profile.school }}
            </p>
          </div>
        </div>
        <div class="mt-3 grid grid-cols-2 gap-2">
          <div class="rounded-md bg-tie-fill py-2 text-center">
            <b class="block text-lg text-tie-blue">{{ userStore.profile.post_count }}</b>
            <span class="text-[11px] text-tie-sub">发帖</span>
          </div>
          <div class="rounded-md bg-tie-fill py-2 text-center">
            <b class="block text-lg text-tie-blue">{{ userStore.profile.like_count }}</b>
            <span class="text-[11px] text-tie-sub">获赞</span>
          </div>
        </div>
        <router-link
          v-if="session.userId"
          :to="`/user/${session.userId}`"
          class="mt-3 block rounded-md border border-tie-line py-2 text-center text-xs font-semibold text-tie-blue transition hover:bg-tie-50"
        >
          查看个人主页
        </router-link>
      </template>
      <el-button v-else class="w-full" type="primary" @click="uiStore.openAuthDialog()">登录查看</el-button>
    </div>
  </div>
</template>
