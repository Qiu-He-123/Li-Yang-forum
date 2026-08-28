<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '../components/native'
import { fetchGratitudeDetail, type GratitudeItem } from '../api/gratitude'

/**
 * 感谢名单 - 详情页
 * - 个人名片式头部（头像/名字/一句话简介）
 * - 详细介绍正文（支持段落换行展示）
 */
const route = useRoute()
const router = useRouter()
const item = ref<GratitudeItem | null>(null)
const loading = ref(true)
const loadError = ref(false)

async function load() {
  loading.value = true
  loadError.value = false
  try {
    const { data: resp } = await fetchGratitudeDetail(Number(route.params.id))
    item.value = resp.data
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

onMounted(load)

const detailLines = computed<string[]>(() => {
  return (item.value?.detail || '').split('\n').map((l) => l.trim()).filter((l) => !!l)
})

function avatarUrl(it: GratitudeItem | null): string {
  return it?.avatar_url && it.avatar_url.trim() ? it.avatar_url : ''
}
function initial(name: string): string {
  return (name || '?').trim().charAt(0).toUpperCase()
}
function avatarHue(name: string): number {
  let h = 0
  for (const ch of (name || '')) h = (h * 31 + ch.charCodeAt(0)) % 360
  return h
}
</script>

<template>
  <div class="gd-page">
    <button class="gd-back" type="button" aria-label="返回" @click="router.back()">
      <Icon name="chevron-left" :size="22" color="#1a1a2e" />
    </button>

    <div v-if="loading" class="gd-empty">加载中…</div>
    <div v-else-if="loadError || !item" class="gd-empty">
      <p>名单不存在或已下架</p>
      <button class="gd-retry" type="button" @click="router.replace('/gratitude')">返回名单</button>
    </div>
    <div v-else class="gd-wrap">
      <!-- 名片头部 -->
      <div class="gd-card gd-card--meta">
        <span
          v-if="avatarUrl(item)"
          class="gd-avatar"
          :style="{ backgroundImage: `url(${avatarUrl(item)})` }"
        ></span>
        <span
          v-else
          class="gd-avatar gd-avatar--char"
          :style="{ background: `linear-gradient(135deg, hsl(${avatarHue(item.name)},70%,58%), hsl(${(avatarHue(item.name) + 50) % 360},70%,46%))` }"
        >{{ initial(item.name) }}</span>
        <h1 class="gd-name">{{ item.name }}</h1>
        <p class="gd-bio">{{ item.bio || '感谢一路支持 ♥' }}</p>
      </div>

      <!-- 详细介绍 -->
      <div v-if="detailLines.length" class="gd-card gd-card--detail">
        <h2 class="gd-sec">致谢</h2>
        <div class="gd-text">
          <p v-for="(line, i) in detailLines" :key="i">{{ line }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.gd-page {
  min-height: 100vh;
  padding: 64px 16px 40px;
  background: #f2f3f7;
}
.gd-back {
  position: fixed;
  top: 14px;
  left: 14px;
  z-index: 5;
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border: none;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 2px 10px rgba(23, 32, 64, 0.14);
  cursor: pointer;
}
.gd-empty { padding: 120px 0; text-align: center; color: #999; }
.gd-retry { margin-top: 14px; padding: 8px 22px; border: none; border-radius: 999px; background: #3550ff; color: #fff; cursor: pointer; }
.gd-wrap { max-width: 460px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px; }
.gd-card {
  padding: 20px;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 3px 16px rgba(23, 32, 64, 0.1);
}
.gd-card--meta { text-align: center; padding-bottom: 26px; }
.gd-avatar {
  width: 88px;
  height: 88px;
  border-radius: 50%;
  display: inline-block;
  background-size: cover;
  background-position: center;
  background-color: #eef0f6;
  box-shadow: 0 6px 18px rgba(23, 32, 64, 0.2);
}
.gd-avatar--char { display: grid; place-items: center; color: #fff; font-size: 34px; font-weight: 800; }
.gd-name { margin: 14px 0 4px; font-size: 22px; font-weight: 800; color: #1a1a2e; }
.gd-bio { margin: 0; font-size: 14px; color: #888; }
.gd-sec { margin: 0 0 12px; font-size: 14px; font-weight: 700; color: #3550ff; }
.gd-text p { margin: 0 0 8px; font-size: 14px; line-height: 1.8; color: #3a3a4a; }
</style>