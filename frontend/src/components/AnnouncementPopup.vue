<script setup lang="ts">
/**
 * 全局公告弹窗组件。
 *
 * 与启动弹窗编排（uiStore.announcementPopupOpen）协作：
 * - 编排器置 announcementPopupOpen=true → 开始拉取 & 展示未读公告
 * - 用户点「我知道了」或「稍后再说」→ 逐条处理
 * - 全部处理完（或根本没有未读）→ 把 announcementPopupOpen 改回 false 并
 *   置 announcementPopupDone=true（编排器据此推进到下一个弹窗）
 *
 * 60s 轮询仍然保留：页面停留期间后台新发的公告，会等下一个编排窗口
 * （或 announcementPopupDone=true 说明当前序列已走完，直接按新批次打开）。
 */
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { storeToRefs } from 'pinia'

import { listUnreadAnnouncements, markAnnouncementRead } from '../api/announcement'
import { useSessionStore } from '../stores/session'
import { useUIStore } from '../stores/ui'
import type { Announcement } from '../types/api'

const session = useSessionStore()
const uiStore = useUIStore()
const { announcementPopupOpen } = storeToRefs(uiStore)

const unreadList = ref<Announcement[]>([])
const currentIndex = ref(0)
const marking = ref(false)
// 「稍后再说」的公告：本次页面会话内不再打扰，刷新页面后仍会重新弹出
const dismissedIds = ref<Set<number>>(new Set())
const currentAnnouncement = ref<Announcement | null>(null)

let checkTimer: ReturnType<typeof setInterval> | null = null
// 加载中的竞态保护：防止连续两次 loadAndShow 并发把同一个公告加两遍
let loadingNow = false

async function loadAndShow() {
  if (loadingNow) return
  loadingNow = true
  try {
    // 没有登录态：直接结束这一轮
    if (!session.isLoggedIn()) {
      finishCurrentRound()
      return
    }
    const { data } = await listUnreadAnnouncements({
      showGlobalLoading: false,
      showGlobalError: false,
    })
    const list = (data.data || []).filter(
      (item: Announcement) => !dismissedIds.value.has(item.id),
    )
    unreadList.value = list
    if (list.length === 0) {
      finishCurrentRound()
      return
    }
    // 有未读 → 打开弹窗让用户点
    currentIndex.value = 0
    currentAnnouncement.value = list[0]
    uiStore.announcementPopupDone = false
    uiStore.announcementPopupOpen = true
  } catch (err) {
    console.warn('[AnnouncementPopup] load failed:', err)
    // 加载失败也别卡住后续的押注/新手教程
    finishCurrentRound()
  } finally {
    loadingNow = false
  }
}

/** 把当前轮次（一次 announcementPopupOpen=true 的展示过程）标记结束 */
function finishCurrentRound() {
  currentAnnouncement.value = null
  unreadList.value = []
  if (uiStore.announcementPopupOpen) uiStore.announcementPopupOpen = false
  uiStore.announcementPopupDone = true
}

onMounted(() => {
  // 启动时：如果编排器没立即打开，但登录用户已存在，也先把状态置为"无待处理"
  // 真正的打开时机由 App.vue 的编排器触发（startupPopupsReady 之后）
  if (session.isLoggedIn() && !uiStore.startupPopupsReady) {
    // 等待编排器开启即可
  }
  // 轮询兜底：页面停留期间发布的新公告，每隔 60s 检查
  checkTimer = setInterval(() => {
    if (!session.isLoggedIn()) return
    // 如果当前编排序列已经全部走完（announcementPopupDone=true），
    // 发现有新公告到来则作为"补充批次"重新打开一轮
    if (uiStore.announcementPopupDone && !uiStore.announcementPopupOpen) {
      void loadAndShow()
    }
  }, 60_000)
})

onUnmounted(() => {
  if (checkTimer) clearInterval(checkTimer)
  checkTimer = null
})

/** 稍后再说：不标记已读，本次会话不再弹，刷新后仍会弹出 */
function onDismiss() {
  if (!currentAnnouncement.value) {
    finishCurrentRound()
    return
  }
  dismissedIds.value.add(currentAnnouncement.value.id)
  next()
}

function next() {
  currentIndex.value += 1
  if (currentIndex.value < unreadList.value.length) {
    currentAnnouncement.value = unreadList.value[currentIndex.value]
  } else {
    finishCurrentRound()
  }
}

async function onConfirm() {
  if (!currentAnnouncement.value) {
    finishCurrentRound()
    return
  }
  marking.value = true
  try {
    await markAnnouncementRead(currentAnnouncement.value.id)
    next()
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    marking.value = false
  }
}

/**
 * 编排器入口：uiStore.announcementPopupOpen=true 时开始拉未读公告。
 * - 有未读 → 真的打开弹窗
 * - 没未读/加载失败/未登录 → loadAndShow 内部会把 announcementPopupDone 置 true，
 *   编排器据此继续推进到下一步（押注），不会打开空弹窗。
 */
watch(
  () => uiStore.announcementPopupOpen,
  (open) => {
    if (open) void loadAndShow()
  },
)

// 登录态变化：
// - 登录成功 → 由编排器统一触发；这里只处理登出时的清理
// - 注意：不再自己 setTimeout 500ms 就开，避免抢在公告/押注之前弹教程
watch(
  () => session.userId,
  (newId) => {
    if (!newId) {
      dismissedIds.value.clear()
      finishCurrentRound()
    }
  },
)
</script>

<template>
  <el-dialog
    v-if="currentAnnouncement"
    :model-value="true"
    :show-close="false"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    width="440px"
    class="announcement-popup"
    align-center
    :append-to-body="true"
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
      <el-button :disabled="marking" @click="onDismiss">稍后再说</el-button>
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
