<script setup lang="ts">
/**
 * 徽章中心（我的徽章）
 * - 顶部：当前佩戴徽章 + 领取激活码入口
 * - 我的徽章：选择佩戴哪一个（每人可拥有多个，佩戴一个展示在名字前）
 * - 全部徽章目录：未拥有的显示锁定状态
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import BadgeIcon from '../components/common/BadgeIcon.vue'
import { Dialog as NativeDialog, Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import {
  claimBadge,
  fetchMyBadges,
  unwearBadge,
  wearBadge,
  type MyBadgesData,
} from '../api/badge'
import { useSessionStore } from '../stores/session'
import { useUserStore } from '../stores/user'
import type { Badge } from '../types/api'

const router = useRouter()
const session = useSessionStore()
const userStore = useUserStore()

const data = ref<MyBadgesData | null>(null)
const loading = ref(false)
const wearingLoading = ref(false)

// 领取激活码
const claimDialogVisible = ref(false)
const claimCode = ref('')
const claiming = ref(false)

async function load() {
  if (!session.userId) {
    toast.info('请先登录')
    router.push('/')
    return
  }
  loading.value = true
  try {
    const { data: res } = await fetchMyBadges({
      showGlobalLoading: false,
      showGlobalError: false,
    })
    data.value = res.data
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

function openClaim() {
  claimCode.value = ''
  claimDialogVisible.value = true
}

async function submitClaim() {
  const code = claimCode.value.trim()
  if (!code) {
    toast.error('请输入激活码')
    return
  }
  claiming.value = true
  try {
    const { data: res } = await claimBadge(code)
    toast.success(`已获得「${res.data.icon} ${res.data.name}」徽章！`)
    claimDialogVisible.value = false
    await Promise.all([load(), userStore.loadProfile()])
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    claiming.value = false
  }
}

async function onWear(badge: Badge) {
  if (wearingLoading.value) return
  wearingLoading.value = true
  try {
    await wearBadge(badge.id)
    toast.success(`已佩戴「${badge.name}」，将展示在名字前`)
    await Promise.all([load(), userStore.loadProfile()])
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    wearingLoading.value = false
  }
}

async function onUnwear() {
  if (wearingLoading.value) return
  wearingLoading.value = true
  try {
    await unwearBadge()
    toast.success('已卸下徽章')
    await Promise.all([load(), userStore.loadProfile()])
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    wearingLoading.value = false
  }
}

const wearingBadge = computed(() => data.value?.wearing_badge || null)

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/')
}

onMounted(load)
</script>

<template>
  <main class="page-badges">
    <!-- 顶部栏 -->
    <header class="badges-header">
      <button class="icon-btn" type="button" aria-label="返回" @click="goBack">
        <Icon name="arrow-left" :size="20" />
      </button>
      <h1 class="badges-title">我的徽章</h1>
      <button class="icon-btn" type="button" aria-label="领取徽章" @click="openClaim">
        <Icon name="gift" :size="20" />
      </button>
    </header>

    <div class="badges-container">
      <!-- 佩戴展示区 -->
      <section class="wearing-card">
        <div class="wearing-icon">
          <BadgeIcon :badge="wearingBadge" :size="44" />
        </div>
        <div class="wearing-info">
          <p class="wearing-label">当前佩戴</p>
          <p v-if="wearingBadge" class="wearing-name">{{ wearingBadge.name }}</p>
          <p v-else class="wearing-name is-empty">未佩戴徽章</p>
          <p class="wearing-desc">
            佩戴后徽章会展示在你的名字前，如
            <span class="wearing-demo">
              <BadgeIcon v-if="wearingBadge" :badge="wearingBadge" :size="12" />
              {{ ' ' }}昵称
            </span>
          </p>
        </div>
        <button
          v-if="wearingBadge"
          class="wearing-action"
          type="button"
          :disabled="wearingLoading"
          @click="onUnwear"
        >卸下</button>
      </section>

      <!-- 领取激活码 -->
      <button class="claim-card" type="button" @click="openClaim">
        <span class="claim-icon"><Icon name="gift" :size="20" /></span>
        <span class="claim-body">
          <span class="claim-title">领取徽章</span>
          <span class="claim-desc">输入激活码领取专属徽章（激活码由管理员发放）</span>
        </span>
        <Icon name="chevron-right" :size="16" color="#c7c7cc" />
      </button>

      <!-- 我的徽章 -->
      <section class="badge-section">
        <div class="section-head">
          <h2 class="section-title">我的徽章（{{ data?.total || 0 }}）</h2>
        </div>
        <div v-if="loading && !data" class="loading-tip">加载中…</div>
        <div v-else-if="data?.owned.length" class="badge-grid">
          <button
            v-for="badge in data!.owned"
            :key="badge.id"
            class="badge-cell"
            :class="{ 'is-wearing': badge.is_wearing }"
            type="button"
            :disabled="wearingLoading"
            @click="badge.is_wearing ? onUnwear() : onWear(badge)"
          >
            <BadgeIcon :badge="badge" :size="34" />
            <span class="badge-name">{{ badge.name }}</span>
            <span class="badge-state">{{ badge.is_wearing ? '佩戴中' : '点击佩戴' }}</span>
          </button>
        </div>
        <div v-else class="badge-empty">
          <Icon name="medal" :size="28" color="#c7c7cc" />
          <p>还没有徽章，输入激活码领取第一个吧</p>
        </div>
      </section>

      <!-- 全部徽章目录 -->
      <section class="badge-section">
        <div class="section-head">
          <h2 class="section-title">全部徽章（{{ data?.all_badges.length || 0 }}）</h2>
          <span class="section-tip">未获得的徽章显示锁定</span>
        </div>
        <div class="badge-grid">
          <div
            v-for="badge in data?.all_badges"
            :key="badge.id"
            class="badge-cell"
            :class="{ 'is-owned': badge.is_owned }"
          >
            <div class="badge-icon-wrap" :class="{ locked: !badge.is_owned }">
              <BadgeIcon :badge="badge" :size="34" />
              <span v-if="!badge.is_owned" class="lock-overlay"><Icon name="lock" :size="14" /></span>
            </div>
            <span class="badge-name">{{ badge.name }}</span>
            <span class="badge-desc">{{ badge.description || '' }}</span>
          </div>
        </div>
      </section>
    </div>

    <!-- 领取徽章弹窗 -->
    <NativeDialog v-model="claimDialogVisible" title="领取徽章" width="420px">
      <p class="claim-tip">请输入管理员发放的激活码，领取成功后徽章将出现在「我的徽章」中。</p>
      <input
        v-model="claimCode"
        class="claim-input"
        type="text"
        maxlength="32"
        placeholder="请输入激活码（如 B1A2C3D4）"
        @keydown.enter="submitClaim"
      />
      <template #footer>
        <button class="btn btn-outline" type="button" @click="claimDialogVisible = false">取消</button>
        <button class="btn btn-primary" type="button" :disabled="claiming" @click="submitClaim">
          {{ claiming ? '领取中…' : '领取' }}
        </button>
      </template>
    </NativeDialog>
  </main>
</template>

<style scoped>
.page-badges {
  min-height: 100vh;
  background: var(--bg-100);
  padding-bottom: calc(80px + env(safe-area-inset-bottom));
}
.badges-header {
  position: sticky;
  top: 0;
  z-index: 50;
  background: rgba(255, 255, 255, 0.95);
  -webkit-backdrop-filter: blur(20px);
  backdrop-filter: blur(20px);
  border-bottom: 0.5px solid var(--bg-300);
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
}
.badges-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-800);
  margin: 0;
}
.icon-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: transparent;
  cursor: pointer;
  display: grid;
  place-items: center;
  color: var(--text-600);
  transition: background 0.15s;
}
.icon-btn:hover {
  background: var(--bg-100);
  color: var(--text-800);
}
.badges-container {
  max-width: 640px;
  margin: 0 auto;
  padding: 14px 16px 0;
}
.wearing-card {
  display: flex;
  align-items: center;
  gap: 14px;
  background: linear-gradient(135deg, #fff8e6, #fff);
  border: 1px solid #ffe1a6;
  border-radius: var(--radius-lg);
  padding: 16px;
  margin-bottom: 12px;
}
.wearing-icon {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: #fff;
  border: 1px dashed #f0c14b;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.wearing-info {
  flex: 1;
  min-width: 0;
}
.wearing-label {
  margin: 0 0 2px;
  font-size: 11px;
  color: var(--text-400);
}
.wearing-name {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-800);
}
.wearing-name.is-empty {
  color: var(--text-400);
}
.wearing-desc {
  margin: 4px 0 0;
  font-size: 11px;
  color: var(--text-500);
}
.wearing-demo {
  display: inline-flex;
  align-items: center;
  color: var(--brand-600);
  font-weight: 600;
}
.wearing-action {
  padding: 6px 14px;
  border-radius: 999px;
  border: 1px solid var(--bg-300);
  background: #fff;
  color: var(--text-600);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  flex-shrink: 0;
}
.claim-card {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  background: var(--bg-50);
  border: none;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  padding: 14px 16px;
  cursor: pointer;
  margin-bottom: 18px;
  text-align: left;
  transition: box-shadow 0.15s, transform 0.15s;
}
.claim-card:hover {
  box-shadow: var(--shadow-sm);
}
.claim-card:active {
  transform: scale(0.99);
}
.claim-icon {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: linear-gradient(135deg, #ffd60a, #f7b500);
  color: #fff;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.claim-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.claim-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-800);
}
.claim-desc {
  font-size: 12px;
  color: var(--text-500);
}
.badge-section {
  margin-bottom: 20px;
}
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 4px 10px;
}
.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-800);
}
.section-tip {
  font-size: 11px;
  color: var(--text-400);
}
.badge-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}
.badge-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 14px 8px;
  background: var(--bg-50);
  border-radius: var(--radius-lg);
  border: 1px solid transparent;
  box-shadow: var(--shadow-xs);
  cursor: pointer;
  transition: border-color 0.15s, transform 0.15s, opacity 0.15s;
}
.badge-cell:not(.is-owned):not(.is-wearing) {
  cursor: default;
}
.badge-cell.is-wearing {
  border-color: #f0c14b;
  background: #fffbea;
}
.badge-cell:hover {
  transform: translateY(-2px);
}
.badge-cell:disabled {
  opacity: 0.7;
}
.badge-cell.is-owned {
  opacity: 1;
}
.badge-icon-wrap {
  position: relative;
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
}
.badge-icon-wrap.locked {
  filter: grayscale(1);
  opacity: 0.55;
}
.lock-overlay {
  position: absolute;
  right: -4px;
  bottom: -4px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  display: grid;
  place-items: center;
}
.badge-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-800);
  text-align: center;
  line-height: 1.3;
}
.badge-desc {
  font-size: 10px;
  color: var(--text-400);
  text-align: center;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.badge-state {
  font-size: 10px;
  font-weight: 600;
  color: var(--brand-500);
}
.badge-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 28px 0;
  color: var(--text-400);
  font-size: 13px;
  background: var(--bg-50);
  border-radius: var(--radius-lg);
}
.loading-tip {
  text-align: center;
  padding: 30px 0;
  color: var(--text-400);
  font-size: 13px;
}
.claim-tip {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--text-500);
  line-height: 1.5;
}
.claim-input {
  width: 100%;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid var(--color-border, #e5e5ea);
  font-size: 15px;
  font-family: inherit;
  color: var(--text-800);
  outline: none;
  text-transform: uppercase;
  letter-spacing: 1px;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.claim-input:focus {
  border-color: var(--brand-500);
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.15);
}
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 8px 18px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  border: none;
  cursor: pointer;
  transition: transform 0.15s, opacity 0.15s;
}
.btn:active {
  transform: scale(0.98);
}
.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.btn-outline {
  background: transparent;
  color: var(--text-700);
  border: 1px solid var(--bg-300);
}
.btn-primary {
  background: var(--brand-500);
  color: #fff;
}

@media (max-width: 768px) {
  .badges-header {
    height: 48px;
    padding: 0 12px;
  }
  .badges-container {
    padding: 12px 12px 0;
  }
  .badge-grid {
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
  }
}
</style>
