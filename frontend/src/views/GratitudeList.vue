<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Icon } from '../components/native'
import { fetchGratitudeList, type GratitudeItem } from '../api/gratitude'

/**
 * 感谢名单 - 列表页
 * - 大厂风卡片：头部渐变横幅 + 名单卡片（头像/名字/简介）
 * - 点击卡片进入详情页查看详细介绍
 */
const router = useRouter()
const list = ref<GratitudeItem[]>([])
const loading = ref(true)
const loadError = ref(false)

async function load() {
  loading.value = true
  loadError.value = false
  try {
    const { data: resp } = await fetchGratitudeList()
    list.value = resp.data ?? []
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

onMounted(load)

function avatarUrl(item: GratitudeItem): string {
  return item.avatar_url && item.avatar_url.trim() ? item.avatar_url : ''
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
  <div class="grat-page">
    <!-- 顶部渐变大图 -->
    <div class="grat-hero">
      <button class="grat-hero__back" type="button" aria-label="返回" @click="router.back()">
        <Icon name="chevron-left" :size="22" color="#fff" />
      </button>
      <span class="grat-hero__badge">🎁</span>
      <h1 class="grat-hero__title">感谢名单</h1>
      <p class="grat-hero__sub">感谢每一位种下星光的人，让这个小社区一点点长大</p>
    </div>

    <div class="grat-body">
      <div v-if="loading" class="grat-empty">正在翻阅星光…</div>
      <div v-else-if="loadError" class="grat-empty">
        <p>加载失败</p>
        <button class="grat-empty__btn" type="button" @click="load">重试</button>
      </div>
      <div v-else-if="list.length === 0" class="grat-empty">
        <p>名单正在筹备中，敬请期待 ✨</p>
      </div>
      <div v-else class="grat-list">
        <button
          v-for="(item, idx) in list"
          :key="item.id"
          class="grat-item"
          type="button"
          @click="router.push(`/gratitude/${item.id}`)"
        >
          <span class="grat-item__rank">{{ idx + 1 }}</span>
          <span
            v-if="avatarUrl(item)"
            class="grat-item__avatar"
            :style="{ backgroundImage: `url(${avatarUrl(item)})` }"
          ></span>
          <span
            v-else
            class="grat-item__avatar grat-item__avatar--char"
            :style="{ background: `linear-gradient(135deg, hsl(${avatarHue(item.name)},70%,58%), hsl(${(avatarHue(item.name) + 50) % 360},70%,46%))` }"
          >{{ initial(item.name) }}</span>
          <span class="grat-item__body">
            <span class="grat-item__name">{{ item.name }}</span>
            <span class="grat-item__bio">{{ item.bio || '感谢支持 ♥' }}</span>
          </span>
          <Icon name="chevron-right" :size="17" color="#c7c7cc" />
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.grat-page {
  min-height: 100vh;
  background: #f2f3f7;
}
.grat-hero {
  position: relative;
  padding: 40px 20px 46px;
  text-align: center;
  overflow: hidden;
  background: linear-gradient(135deg, #3550ff, #8a5cff 55%, #ff5f9e);
  color: #fff;
}
.grat-hero::after {
  content: '';
  position: absolute;
  right: -50px;
  top: -40px;
  width: 180px;
  height: 180px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.12);
}
.grat-hero__back {
  position: absolute;
  left: 12px;
  top: 12px;
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.18);
  color: #fff;
  cursor: pointer;
}
.grat-hero__badge { display: block; font-size: 44px; margin-bottom: 8px; }
.grat-hero__title { margin: 0; font-size: 26px; font-weight: 800; letter-spacing: 2px; }
.grat-hero__sub { margin: 10px 0 0; font-size: 13px; opacity: 0.9; }
.grat-body { padding: 18px 14px 40px; }
.grat-list { display: flex; flex-direction: column; gap: 12px; }
.grat-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid rgba(23, 32, 64, 0.08);
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 3px 14px rgba(23, 32, 64, 0.1);
  cursor: pointer;
}
.grat-item__rank {
  width: 22px;
  font-size: 14px;
  font-weight: 800;
  color: #ff9a56;
  text-align: center;
}
.grat-item__avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  flex: none;
  background-size: cover;
  background-position: center;
  background-color: #eef0f6;
}
.grat-item__avatar--char {
  display: grid;
  place-items: center;
  color: #fff;
  font-size: 20px;
  font-weight: 800;
}
.grat-item__body { flex: 1; min-width: 0; text-align: left; }
.grat-item__name { display: block; font-size: 16px; font-weight: 700; color: #1a1a2e; }
.grat-item__bio {
  display: block;
  margin-top: 3px;
  font-size: 12px;
  color: #888;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.grat-empty {
  padding: 80px 0;
  text-align: center;
  color: #999;
  font-size: 14px;
}
.grat-empty__btn {
  margin-top: 14px;
  padding: 8px 22px;
  border: none;
  border-radius: 999px;
  background: #3550ff;
  color: #fff;
  font-size: 14px;
  cursor: pointer;
}
</style>