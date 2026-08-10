<script setup lang="ts">
/**
 * 全局公告弹窗组件。
 * - 监听 session.userId 变化：用户登录后自动拉取未读公告
 * - 依次展示未读公告，用户点击"我知道了"标记已读并展示下一条
 * - 已读公告下次登录不再弹窗
 * - 在 sessionStorage 中标记本次会话已检查，避免重复弹窗
 */
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { listUnreadAnnouncements, markAnnouncementRead } from '../api/announcement'
import { useSessionStore } from '../stores/session'
import type { Announcement } from '../types/api'

const session = useSessionStore()

const visible = ref(false)
const unreadList = ref<Announcement[]>([])
const currentIndex = ref(0)
const marking = ref(false)

const currentAnnouncement = ref<Announcement | null>(null)

let checkTimer: ReturnType<typeof setInterval> | null = null

async function loadAndShow() {
  // 弹窗已在展示中则跳过，避免重复拉取打断用户
  if (visible.value) return
  try {
    const { data } = await listUnreadAnnouncements({
      showGlobalLoading: false,
      showGlobalError: false,
    })
    unreadList.value = data.data || []
    if (unreadList.value.length > 0) {
      currentIndex.value = 0
      currentAnnouncement.value = unreadList.value[0]
      visible.value = true
    }
  } catch (err) {
    console.warn('[AnnouncementPopup] load failed:', err)
  }
}

onMounted(() => {
  // 已登录用户每次进入页面都检查一次，新公告也会弹
  if (session.isLoggedIn()) loadAndShow()
  // 轮询兜底：页面停留期间发布的新公告，60 秒内弹出
  checkTimer = setInterval(() => {
    if (session.isLoggedIn()) loadAndShow()
  }, 60_000)
})

onUnmounted(() => {
  if (checkTimer) clearInterval(checkTimer)
  checkTimer = null
})

async function onConfirm() {
  if (!currentAnnouncement.value) {
    visible.value = false
    return
  }
  marking.value = true
  try {
    await markAnnouncementRead(currentAnnouncement.value.id)
    // 下一条
    currentIndex.value += 1
    if (currentIndex.value < unreadList.value.length) {
      currentAnnouncement.value = unreadList.value[currentIndex.value]
    } else {
      visible.value = false
      currentAnnouncement.value = null
    }
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    marking.value = false
  }
}

// 监听登录态变化：登录成功后立即检查未读公告
watch(
  () => session.userId,
  (newId) => {
    if (newId) {
      // 延迟 500ms 等其他初始化完成后再弹窗，避免与登录欢迎提示冲突
      setTimeout(() => {
        loadAndShow()
      }, 500)
    } else {
      // 登出时清理
      visible.value = false
      unreadList.value = []
      currentAnnouncement.value = null
    }
  },
)
</script>

<template>
  <el-dialog
    v-model="visible"
    :show-close="false"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    width="440px"
    class="announcement-popup"
    align-center
  >
    <template #header>
      <div class="popup-header">
        <span class="popup-badge" aria-hidden="true">公告</span>
        <span class="popup-title">{{ currentAnnouncement?.title }}</span>
      </div>
    </template>
    <div v-if="currentAnnouncement" class="popup-content">
      <p class="popup-text">{{ currentAnnouncement.content }}</p>
      <p v-if="unreadList.length > 1" class="popup-count">
        第 {{ currentIndex + 1 }} / {{ unreadList.length }} 条
      </p>
    </div>
    <template #footer>
      <el-button type="primary" :loading="marking" @click="onConfirm">我知道了</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.popup-header {
  display: flex;
  align-items: center;
  gap: 10px;
}
.popup-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  background: #f59e0b;
}
.popup-title {
  font-size: 16px;
  font-weight: 700;
  color: #1f2937;
  flex: 1;
  min-width: 0;
  word-break: break-all;
}
.popup-content {
  padding: 4px 0;
}
.popup-text {
  font-size: 14px;
  color: #374151;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0 0 8px;
}
.popup-count {
  font-size: 12px;
  color: #9ca3af;
  margin: 0;
}
</style>
