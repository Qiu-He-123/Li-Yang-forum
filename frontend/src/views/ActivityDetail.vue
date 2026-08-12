<script setup lang="ts">
/**
 * 活动详情页：封面/信息/报名按钮
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { Icon } from '../components/native'
import { toast } from '../components/native/Toast'
import { fetchActivity, joinActivity, type Activity } from '../api/activity'
import { useSessionStore } from '../stores/session'
import { useUIStore } from '../stores/ui'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const uiStore = useUIStore()

const activity = ref<Activity | null>(null)
const loading = ref(false)
const submitting = ref(false)
const notFound = ref(false)

const activityId = computed(() => Number(route.params.id))

async function load() {
  loading.value = true
  notFound.value = false
  try {
    const { data } = await fetchActivity(activityId.value, {
      showGlobalLoading: false,
      showGlobalError: false,
    })
    activity.value = data.data
  } catch {
    notFound.value = true
  } finally {
    loading.value = false
  }
}

function fmtTime(iso: string | null): string {
  if (!iso) return '待定'
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const isFull = computed(() => {
  const a = activity.value
  return !!a && a.max_participants != null && a.participant_count >= a.max_participants
})

async function onToggleJoin() {
  if (!session.userId) {
    uiStore.authDialogVisible = true
    return
  }
  const a = activity.value
  if (!a || submitting.value) return
  submitting.value = true
  try {
    const { data } = await joinActivity(a.id, a.joined ? 'cancel' : 'join')
    activity.value = data.data
    toast.success(a.joined ? '已取消报名' : '报名成功')
  } catch (err) {
    toast.error((err as Error).message)
  } finally {
    submitting.value = false
  }
}

function goBack() {
  router.back()
}

onMounted(load)
</script>

<template>
  <main class="page-activity-detail">
    <div class="ad-topbar">
      <button class="icon-btn" type="button" aria-label="返回" @click="goBack">
        <Icon name="arrow-left" :size="20" />
      </button>
      <span class="ad-title">活动详情</span>
      <span class="icon-btn-placeholder" />
    </div>

    <div v-if="loading" class="ad-loading">加载中…</div>
    <div v-else-if="notFound || !activity" class="ad-loading">活动不存在或已下线</div>
    <template v-else>
      <div
        class="ad-cover"
        :class="{ 'no-cover': !activity.cover_url }"
        :style="activity.cover_url ? { backgroundImage: `url(${activity.cover_url})` } : undefined"
      >
        <Icon v-if="!activity.cover_url" name="calendar" :size="48" color="#fff" />
      </div>

      <div class="ad-body">
        <h1 class="ad-name">{{ activity.title }}</h1>
        <div class="ad-tags">
          <span class="ad-tag">{{ activity.joined ? '已报名' : '未报名' }}</span>
          <span v-if="isFull" class="ad-tag ad-tag--warn">名额已满</span>
        </div>

        <div class="ad-info-card">
          <div class="ad-info-row">
            <Icon name="clock" :size="16" color="#007aff" />
            <div>
              <span class="ad-info-label">活动时间</span>
              <span class="ad-info-value">{{ fmtTime(activity.start_at) }}{{ activity.end_at ? ` 至 ${fmtTime(activity.end_at)}` : '' }}</span>
            </div>
          </div>
          <div v-if="activity.location" class="ad-info-row">
            <Icon name="map-pin" :size="16" color="#ff3b30" />
            <div>
              <span class="ad-info-label">活动地点</span>
              <span class="ad-info-value">{{ activity.location }}</span>
            </div>
          </div>
          <div v-if="activity.organizer" class="ad-info-row">
            <Icon name="users" :size="16" color="#34c759" />
            <div>
              <span class="ad-info-label">主办方</span>
              <span class="ad-info-value">{{ activity.organizer }}</span>
            </div>
          </div>
          <div v-if="activity.contact" class="ad-info-row">
            <Icon name="phone" :size="16" color="#af52de" />
            <div>
              <span class="ad-info-label">联系方式</span>
              <span class="ad-info-value">{{ activity.contact }}</span>
            </div>
          </div>
          <div class="ad-info-row">
            <Icon name="users" :size="16" color="#ff9500" />
            <div>
              <span class="ad-info-label">报名人数</span>
              <span class="ad-info-value">
                {{ activity.participant_count }}{{ activity.max_participants ? ` / ${activity.max_participants}` : '' }} 人
              </span>
            </div>
          </div>
        </div>

        <div class="ad-desc-card">
          <h3 class="ad-desc-title">活动介绍</h3>
          <p class="ad-desc-text">{{ activity.description || '暂无介绍' }}</p>
        </div>

        <div class="ad-action-bar">
          <button
            class="ad-join-btn"
            :class="{ 'is-joined': activity.joined }"
            type="button"
            :disabled="submitting || (isFull && !activity.joined)"
            @click="onToggleJoin"
          >
            <Icon :name="activity.joined ? 'check' : 'user-plus'" :size="16" color="#fff" />
            {{ submitting ? '处理中…' : activity.joined ? '取消报名' : isFull ? '名额已满' : '立即报名' }}
          </button>
        </div>
      </div>
    </template>
  </main>
</template>

<style scoped>
.page-activity-detail {
  min-height: 100vh;
  background: var(--bg-100, #f2f2f7);
  padding-bottom: 90px;
}

.ad-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 48px;
  padding: 0 12px;
  background: var(--bg-50, #fff);
  border-bottom: 1px solid var(--bg-300, #e5e5ea);
  position: sticky;
  top: 0;
  z-index: 10;
}

.icon-btn {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: transparent;
  border: none;
  color: var(--text-900, #1c1c1e);
}

.icon-btn-placeholder {
  width: 36px;
}

.ad-title {
  font-size: 16px;
  font-weight: 600;
}

.ad-loading {
  padding: 80px 20px;
  text-align: center;
  color: var(--text-500, #8e8e93);
  font-size: 14px;
}

.ad-cover {
  width: 100%;
  height: 190px;
  background-size: cover;
  background-position: center;
  display: grid;
  place-items: center;
}

.ad-cover.no-cover {
  background: linear-gradient(135deg, #0a84ff, #5856d6);
}

.ad-body {
  padding: 16px 14px;
}

.ad-name {
  margin: 0 0 8px;
  font-size: 20px;
  font-weight: 700;
  color: var(--text-900, #1c1c1e);
}

.ad-tags {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.ad-tag {
  font-size: 11px;
  color: #34c759;
  background: #e8f9ee;
  padding: 3px 10px;
  border-radius: 10px;
}

.ad-tag--warn {
  color: #ff9500;
  background: #fff4e0;
}

.ad-info-card,
.ad-desc-card {
  background: var(--bg-50, #fff);
  border-radius: 14px;
  padding: 6px 14px;
  margin-bottom: 12px;
  box-shadow: var(--shadow-sm, 0 1px 4px rgba(0, 0, 0, 0.06));
}

.ad-info-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 0.5px solid var(--bg-300, #e5e5ea);
}

.ad-info-row:last-child {
  border-bottom: none;
}

.ad-info-label {
  display: block;
  font-size: 11px;
  color: var(--text-500, #8e8e93);
}

.ad-info-value {
  display: block;
  font-size: 14px;
  color: var(--text-900, #1c1c1e);
  margin-top: 1px;
}

.ad-desc-card {
  padding: 14px;
}

.ad-desc-title {
  margin: 0 0 8px;
  font-size: 15px;
  font-weight: 600;
}

.ad-desc-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-700, #3a3a3c);
  white-space: pre-wrap;
}

.ad-action-bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 58px;
  padding: 10px 16px calc(10px + env(safe-area-inset-bottom));
  background: var(--bg-50, #fff);
  border-top: 0.5px solid var(--bg-300, #e5e5ea);
}

.ad-join-btn {
  width: 100%;
  height: 44px;
  border: none;
  border-radius: 22px;
  background: #007aff;
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  cursor: pointer;
}

.ad-join-btn.is-joined {
  background: #8e8e93;
}

.ad-join-btn:disabled {
  opacity: 0.6;
}
</style>
