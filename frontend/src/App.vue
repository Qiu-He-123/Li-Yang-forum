<script setup lang="ts">
/**
 * 全局根组件。
 *
 * 「启动弹窗编排器」：
 *   公告 → 今日竞猜押注 → 新手教程
 * 规则：
 * - 只有「登录用户 + 未封禁」才会开启整套序列
 * - 每个阶段有"是否真的需要弹"的判定（没未读公告 / 今天已押过 / 已学完），
 *   不需要则直接 Done，不会真的打开空弹窗
 * - 所有启动条件就绪后（session 通过校验 / guess 首轮数据拉完 / announcement
 *   至少知道有没有未读），才把 uiStore.startupPopupsReady=true，
 *   然后依次串行推进每个弹窗
 *
 *   这样就修掉了"新手教程抢在公告/押注之前就先弹"的 Bug。
 */
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'

import BottomTabBar from './components/BottomTabBar.vue'
import FloatingPet from './components/FloatingPet.vue'
import AiAssistant from './components/AiAssistant.vue'
import FeedbackPrompt from './components/FeedbackPrompt.vue'
import { useSessionStore } from './stores/session'
import { useNotificationStore } from './stores/notification'
import { useUIStore } from './stores/ui'
import { useGuessStore } from './stores/guess'
import { useCoinStore } from './stores/coin'
import { connectWs, wsClient } from './utils/ws'
import { recordVisit } from './api/announcement'
import { useVersionCheck } from './utils/versionCheck'

// 弹窗类组件改为异步加载：避免 element-plus 被打入首屏主 chunk（EP ~400KB）
const AuthDialog = defineAsyncComponent(() => import('./components/auth/AuthDialog.vue'))
const InviteCodeDialog = defineAsyncComponent(() => import('./components/auth/InviteCodeDialog.vue'))
const AnnouncementPopup = defineAsyncComponent(() => import('./components/AnnouncementPopup.vue'))
const CaptchaGate = defineAsyncComponent(() => import('./components/CaptchaGate.vue'))
const OnboardingTour = defineAsyncComponent(() => import('./components/OnboardingTour.vue'))
const TodayGuessPopup = defineAsyncComponent(() => import('./components/home/TodayGuessPopup.vue'))

const route = useRoute()
const router = useRouter()
const uiStore = useUIStore()
const session = useSessionStore()
const notificationStore = useNotificationStore()
const guessStore = useGuessStore()
const coinStore = useCoinStore()
const {
  announcementPopupOpen,
  announcementPopupDone,
  guessPopupOpen,
  guessPopupDone,
  onboardingPopupOpen,
} = storeToRefs(uiStore)

// ============ 新人欢迎礼：首次进入赠送 500 积分 + 询问是否买宠物 ============
// 是否真正发放由后端一次性判定（幂等），这里只负责在其后弹"是否购买宠物"询问。
const welcomeBonusOpen = ref(false)
let welcomeBonusPending = false
// 等今日竞猜编排走完（guessPopupDone）再弹欢迎礼，避免两个全屏弹窗叠在一起。
watch(
  () => uiStore.guessPopupDone,
  (done) => {
    if (welcomeBonusPending && done && !uiStore.guessPopupOpen) {
      welcomeBonusPending = false
      welcomeBonusOpen.value = true
    }
  },
  { immediate: true },
)
function closeWelcomeBonus() {
  welcomeBonusOpen.value = false
}
function goBuyPet() {
  welcomeBonusOpen.value = false
  router.push('/pet-shop')
}

let wsNotificationUnsubscribe: (() => void) | null = null

/**
 * 手动打开竞猜押注弹窗：首页焦点区 TodayGuessHero 点击用。
 * 走 store 开关，与编排器状态兼容（已经 Done 过也没关系，再打开一轮就行）。
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
;(window as any).__TRY_OPEN_GUESS_POPUP__ = () => {
  if (!session.userId) {
    uiStore.openAuthDialog()
    return
  }
  void coinStore.loadBalance()
  uiStore.guessPopupDone = false
  uiStore.guessPopupOpen = true
}

/**
 * Keep-alive 缓存的视图组件名列表。
 * - HomeView（首页）
 * - SwipeFeedView
 * - CircleDiscoverView（圈子/广场）
 * - NotificationsView（消息）
 * - UserHomeView（我的）
 */
const cachedViewNames = ['HomeView', 'SwipeFeedView', 'CircleDiscoverView', 'NotificationsView', 'UserHomeView']

/** 移除 index.html 启动预加载遮罩。 */
function removeAppPreloader() {
  const preloader = document.getElementById('app-preloader')
  if (!preloader) return
  preloader.classList.add('is-hidden')
  window.setTimeout(() => {
    const el = document.getElementById('app-preloader')
    if (el && el.parentNode) el.parentNode.removeChild(el)
  }, 400)
  window.setTimeout(() => {
    const el = document.getElementById('app-preloader')
    if (el && el.parentNode) el.parentNode.removeChild(el)
  }, 5000)
}

const showTabBar = computed(() => {
  const p = route.path
  if (p.startsWith('/admin') || p.startsWith('/chat/')) return false
  // 官网落地页：自带顶部导航，不显示底部 Tab
  if (p === '/xiguo') return false
  // 宠物聊天页：沉浸式聊天，隐藏底部导航避免遮挡输入框
  if (p.startsWith('/pet-chat/')) return false
  // Detail/publish pages have their own bottom bars - don't show tab bar
  if (p.startsWith('/gatherings/') && p !== '/gatherings') return false
  if (p.startsWith('/publish/')) return false
  if (p.startsWith('/pet-shop/') && p !== '/pet-shop') return false
  // 订单发布/钱包/明细等子页面自带底部操作栏，隐藏 Tab 避免遮挡；
  // 接单大厅 /orders 也隐藏，避免底部 Tab 盖住 AI 对话的输入框/发送按钮
  if (p === '/orders' || p.startsWith('/orders/')) return false
  // 陪我玩：沉浸式小游戏页，自带返回，不显示底部导航
  if (p === '/pet-play') return false
  return true
})

// 路由切换：关掉登录/邀请码弹窗，刷新未读数
watch(
  () => route.path,
  () => {
    if (uiStore.authDialogVisible) uiStore.closeAuthDialog()
    if (uiStore.inviteCodeDialogVisible) uiStore.closeInviteCodeDialog()
    if (session.userId && !session.isBanned) notificationStore.refreshUnread()
  },
)

// 登录态变化：启停通知轮询 + 断开并重连 WS（用新身份）
watch(
  () => session.userId,
  (newId) => {
    if (newId && !session.isBanned) {
      notificationStore.refreshUnread()
      notificationStore.startPolling()
    } else {
      notificationStore.clear()
      notificationStore.stopPolling()
    }
    wsClient.disconnect()
    connectWs()
  },
)

// 封号变化：启停通知轮询
watch(() => session.isBanned, (banned) => {
  if (banned) {
    notificationStore.stopPolling()
    notificationStore.clear()
  } else if (session.userId) {
    notificationStore.refreshUnread()
    notificationStore.startPolling()
  }
})

// ============================================================
// 启动弹窗编排器（announcement → guess → onboarding）
// /admin/* 后台页面不弹这些用户端弹窗：后台是管理功能，不需要押注/公告/新手教程。
// ============================================================
const BAN_CHECK_INTERVAL = 45_000
let banCheckTimer: ReturnType<typeof setInterval> | null = null

/** 当前路由是不是后台管理页（后台管理页一律跳过用户端启动编排弹窗） */
function isAdminRoute(): boolean {
  const p = route.path
  return p === '/admin' || p.startsWith('/admin/')
}

/** 官网落地页（/xiguo）：自带沉浸式氛围，不弹公告/押注/教程等任何启动弹窗 */
function isLandingRoute(): boolean {
  return route.path === '/xiguo'
}

/** 接单大厅（/orders）：不弹每日竞猜（今日投票）弹窗，避免与大厅打磨中提示冲突 */
function isOrderHallRoute(): boolean {
  return route.path === '/orders'
}

// 编排阶段：避免并发推进
let schedulingNow = false

/**
 * 判断今天是否真的需要弹押注弹窗：
 * - 有今日竞猜
 * - 还没押过 / 没跳过
 * - 还没截止/结算
 * - 用户未封禁（游客同样可弹，按钮文案为「登录即可参与」）
 * - 不是后台管理页
 */
function guessReallyNeedsPopup(): boolean {
  if (isAdminRoute() || isLandingRoute() || isOrderHallRoute()) return false
  if (session.isBanned) return false
  if (!guessStore.guess) return false
  if (guessStore.popupDismissedToday) return false
  if (guessStore.myBet && (guessStore.myBet.amount > 0 || guessStore.myBet.skipped)) return false
  if (guessStore.guess.settled_at) return false
  return true
}

/**
 * 真正的串行推进器：
 *  Step 1) Announcement：若还没 done → 把 open 置 true 让 AnnouncementPopup 开始工作
 *          AnnouncementPopup 内部会自行"没未读就直接 announcementPopupDone=true"
 *          所以不会出现空弹窗。
 *  Step 2) 等 announcementPopupDone=true → 判断押注是否真的要弹，要弹则打开 guessPopupOpen
 *          不要弹则直接 guessPopupDone=true。
 *  Step 3) 新手教程：暂时取消（用户要求先不弹），直接结束。
 */
async function runStartupPopupQueue() {
  // 后台管理页：永远不弹启动编排。进来也直接走空分支，不打开任何一步的弹窗。
  if (isAdminRoute() || isLandingRoute()) return
  if (schedulingNow) return
  schedulingNow = true
  try {
    // --- Step 1: 公告 ---
    if (!announcementPopupDone.value) {
      if (!session.userId) {
        // 游客：没有"我"这个目标用户，公告直接跳过，不 Open（避免空弹窗），落到 Step 2
        uiStore.announcementPopupDone = true
      } else {
        uiStore.announcementPopupOpen = true
        return // 等用户点完后 watch(announcementPopupDone) 再推进
      }
    }
    // --- Step 2: 押注 ---
    if (!guessPopupDone.value) {
      if (guessReallyNeedsPopup()) {
        void coinStore.loadBalance()
        uiStore.guessPopupOpen = true
        return // 等关完后 watch(guessPopupDone) 再推进
      }
      // 今天不需要弹押注（已押/已跳/没竞猜），直接跳过
      uiStore.guessPopupDone = true
      return
    }
    // --- Step 3: 新手教程（暂时取消，不再弹）---
    // 未来恢复时，把下面这一行取消注释即可：
    // if (!onboardingPopupOpen.value) { uiStore.onboardingPopupOpen = true; return }
  } finally {
    schedulingNow = false
  }
}

// 三个 done 状态变化 → 推进下一步（未登录游客也会走完公告跳过 → 竞猜，故不再 gate on userId）
watch(
  [announcementPopupDone, guessPopupDone],
  () => {
    if (isAdminRoute()) return
    if (!uiStore.startupPopupsReady) return
    if (session.isBanned) return
    void runStartupPopupQueue()
  },
)

// 登录态变化 + 封禁变化 → 重置编排（登出就关；登录且 ready 就启动）
// 注意：游客（从没登录过）首次进入也能弹竞猜，不要被"登出重置"逻辑提前打断。
watch(
  () => [session.userId, session.isBanned, uiStore.startupPopupsReady] as const,
  ([uid, banned, ready]) => {
    if (isAdminRoute()) return
    if (!ready) return
    if (banned) {
      // 被封：全部关掉、状态重置
      uiStore.announcementPopupOpen = false
      uiStore.announcementPopupDone = false
      uiStore.guessPopupOpen = false
      uiStore.guessPopupDone = false
      uiStore.onboardingPopupOpen = false
      return
    }
    // 已登录或游客都推进启动编排（游客由 runStartupPopupQueue 内部跳过公告、再入竞猜）
    void runStartupPopupQueue()
  },
)

// 路由从用户端切到后台 / 或者反向切回来：
//  - 切去 /admin：立即关掉已弹出的编排弹窗，避免遮挡后台登录
//  - 切回用户端：若 startupPopupsReady 已过了 onMounted 的触发点，则重新推一次
watch(
  () => route.path,
  () => {
    if (isAdminRoute()) {
      uiStore.announcementPopupOpen = false
      uiStore.guessPopupOpen = false
      uiStore.onboardingPopupOpen = false
    } else if (isOrderHallRoute()) {
      // 接单大厅：不弹每日竞猜，关掉已弹出的押注弹窗（下一轮由 guessReallyNeedsPopup 拦截）
      uiStore.guessPopupOpen = false
      return
    } else if (uiStore.startupPopupsReady) {
      void runStartupPopupQueue()
    }
  },
)

// 竞猜第一轮加载结束（有或没有结果）后，编排器才能决定要不要弹
let guessFirstLoadTimer: ReturnType<typeof setTimeout> | null = null
function waitGuessFirstReady(timeoutMs = 5000): Promise<boolean> {
  return new Promise((resolve) => {
    if (guessStore.guess !== null || guessStore.error) {
      resolve(true)
      return
    }
    const start = Date.now()
    const tick = () => {
      if (guessStore.guess !== null || guessStore.error) {
        resolve(true); return
      }
      if (Date.now() - start > timeoutMs) {
        resolve(false); return
      }
      guessFirstLoadTimer = setTimeout(tick, 100)
    }
    guessFirstLoadTimer = setTimeout(tick, 100)
  })
}

onMounted(async () => {
  // 前端版本检测：发现线上有新版本时提示用户刷新，解决"发版后仍显示旧页面"。
  // 放最前面且独立于下方 return 分支，管理端/用户端都要监听。
  useVersionCheck()
  recordVisit().catch(() => {})
  // 启动时立即校验 session（封号/解封实时生效）
  if (session.userId) {
    await session.validateSession()
  }
  if (session.userId && !session.isBanned) {
    notificationStore.refreshUnread()
    notificationStore.startPolling()
    // 首次进入赠送 500 积分：真正发放后挂起"是否买宠物"询问，等竞猜编排走完再弹
    const welcome = await coinStore.claimWelcomeBonus()
    if (welcome?.granted) welcomeBonusPending = true
  }
  banCheckTimer = setInterval(() => {
    if (session.userId && !session.isBanned) session.validateSession()
  }, BAN_CHECK_INTERVAL)
  connectWs()
  wsNotificationUnsubscribe = wsClient.on((message) => {
    if (message.type === 'dm_message' && session.userId && !session.isBanned) {
      notificationStore.refreshUnread()
    } else if (message.type === 'pet_ai_proactive' && session.userId && !session.isBanned) {
      // 宠物 AI 主动/自动回复：刷新未读，让消息中心系统角标可见
      notificationStore.refreshUnread()
      // 转发给桌面漂浮宠物，让它开口说出这句话（App 是全局唯一的 WS 中枢）
      const said = (Array.isArray(message.messages) ? message.messages : []).find(
        (m: unknown) => {
          const r = m as { role?: string; content?: unknown }
          return r?.role === 'assistant' && r.content
        },
      )
      if (said && message.pet_id) {
        const content = (said as { content?: unknown })?.content
        window.dispatchEvent(
          new CustomEvent('pet-ai-say', {
            detail: { petId: Number(message.pet_id), text: String(content) },
          }),
        )
      }
    }
  })

  removeAppPreloader()

  // /admin/* 后台：不做启动编排（不弹公告/押注/新手教程），也不开启竞猜用户端轮询。
  if (isAdminRoute()) {
    uiStore.startupPopupsReady = true
    return
  }

  // 今日竞猜：立刻开始轮询（首页焦点区也要实时显示）
  guessStore.startPolling()
  // 等第一轮竞猜数据 / 公告检查实际触发都有了"初步结果"，再把编排器启动开关打开
  await waitGuessFirstReady()

  // 初始把"本阶段 done"都清为 false，避免之前的状态缓存造成推进被跳过
  uiStore.announcementPopupDone = false
  uiStore.guessPopupDone = false
  uiStore.startupPopupsReady = true
  // 立刻推第一步
  void runStartupPopupQueue()
})

onUnmounted(() => {
  if (banCheckTimer) clearInterval(banCheckTimer)
  if (guessFirstLoadTimer) clearTimeout(guessFirstLoadTimer)
  notificationStore.stopPolling()
  if (wsNotificationUnsubscribe) wsNotificationUnsubscribe()
  wsClient.disconnect()
})
</script>

<template>
  <RouterView v-slot="{ Component }">
    <KeepAlive :include="cachedViewNames">
      <component :is="Component" />
    </KeepAlive>
  </RouterView>
  <BottomTabBar v-if="showTabBar" />
  <AuthDialog
    :model-value="uiStore.authDialogVisible"
    @update:model-value="uiStore.authDialogVisible = $event"
  />
  <InviteCodeDialog
    :model-value="uiStore.inviteCodeDialogVisible"
    @update:model-value="uiStore.inviteCodeDialogVisible = $event"
  />
  <!-- 公告/押注/新手教程都是用户端的启动编排弹窗，后台管理页 /admin* 不挂载，避免遮挡后台登录界面 -->
  <template v-if="!isAdminRoute()">
    <AnnouncementPopup />
    <CaptchaGate />
    <OnboardingTour />
    <TodayGuessPopup />
    <!-- 主界面漂浮宠物（已领养像素宠物，桌面宠玩法） -->
    <FloatingPet />

    <!-- 全局 AI 助手：告诉 AI 想做什么，帮你跳转到对应功能（官网 /xiguo、接单大厅 /orders 隐藏，各自带专属 AI） -->
    <AiAssistant v-if="!isLandingRoute() && !route.path.startsWith('/orders')" />

    <!-- 意见反馈：使用过一段后轻提示「给点意见吧」，被采纳可加金币 -->
    <FeedbackPrompt />

    <!-- 新人欢迎礼：首次进入赠送500积分并询问是否购买宠物 -->
    <Teleport to="body">
      <div v-if="welcomeBonusOpen" class="welcome-mask" @click.self="closeWelcomeBonus">
        <div class="welcome-modal" role="dialog" aria-modal="true">
          <div class="welcome-emoji" aria-hidden="true">🎁</div>
          <h2 class="welcome-title">新人欢迎礼</h2>
          <p class="welcome-desc">恭喜你！已为你送上 <b>500 积分</b> 作为见面礼，快去挑选一只心仪的宠物作伴吧～</p>
          <div class="welcome-actions">
            <button class="welcome-btn welcome-btn--ghost" type="button" @click="closeWelcomeBonus">稍后再说</button>
            <button class="welcome-btn welcome-btn--primary" type="button" @click="goBuyPet">去逛逛宠物商城</button>
          </div>
        </div>
      </div>
    </Teleport>
  </template>
  <Transition name="global-loading">
    <!-- skeleton 页面（首页/圈子/消息）不显示全屏遮罩，让组件内骨架屏可见 -->
    <div v-if="uiStore.globalLoadingVisible && route.meta.skeleton !== true" class="global-loading-overlay" aria-live="polite" aria-busy="true">
      <div class="global-loading-card">
        <span class="global-loading-spinner" aria-hidden="true"></span>
        <span class="global-loading-text">加载中…</span>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.global-loading-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(247, 247, 250, 0.72);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}
.global-loading-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  min-width: 132px;
  padding: 24px 28px;
  border: 1px solid rgba(229, 229, 234, 0.9);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: var(--shadow-xl);
}
.global-loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--bg-300);
  border-top-color: var(--brand-500);
  border-radius: 50%;
  animation: global-loading-spin 0.8s linear infinite;
}
.global-loading-text {
  color: var(--text-600);
  font-size: 14px;
  font-weight: 600;
}
.global-loading-enter-active,
.global-loading-leave-active {
  transition: opacity 0.16s var(--ease-apple);
}
.global-loading-enter-from,
.global-loading-leave-to {
  opacity: 0;
}
@keyframes global-loading-spin {
  to {
    transform: rotate(360deg);
  }
}

/* ============================================================
   新人欢迎礼弹窗
   ============================================================ */
.welcome-mask {
  position: fixed;
  inset: 0;
  z-index: 10010;               /* 高于今日竞猜弹窗(9999) */
  background: rgba(8, 8, 14, 0.5);
  -webkit-backdrop-filter: blur(4px);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  animation: welcome-fade 0.2s ease;
}
@keyframes welcome-fade {
  from { opacity: 0; }
  to { opacity: 1; }
}
.welcome-modal {
  width: 100%;
  max-width: 360px;
  border-radius: 22px;
  background: #fff;
  padding: 26px 22px 22px;
  text-align: center;
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.25);
  animation: welcome-pop 0.24s cubic-bezier(0.2, 1.2, 0.3, 1);
}
@keyframes welcome-pop {
  from { transform: scale(0.92); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}
.welcome-emoji {
  font-size: 48px;
  line-height: 1;
  margin-bottom: 10px;
}
.welcome-title {
  margin: 0 0 6px;
  font-size: 20px;
  font-weight: 700;
  color: #111;
}
.welcome-desc {
  margin: 0 0 20px;
  font-size: 14px;
  line-height: 1.7;
  color: #676767;
}
.welcome-desc b {
  color: #ff9500;
  font-weight: 700;
}
.welcome-actions {
  display: flex;
  gap: 10px;
}
.welcome-btn {
  flex: 1;
  padding: 12px 14px;
  border-radius: 14px;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  border: 1px solid transparent;
  transition: transform 0.12s ease, opacity 0.15s ease;
}
.welcome-btn:active {
  transform: translateY(1px);
}
.welcome-btn--ghost {
  background: transparent;
  color: #8a8a8e;
  border-color: #e5e5ea;
}
.welcome-btn--primary {
  background: linear-gradient(135deg, #ff9f0a, #ff7a00);
  color: #fff;
  box-shadow: 0 8px 20px rgba(255, 138, 0, 0.28);
}

/* ============================================================
   全局 AI 助手 / 反馈提示 样式由各自组件内部负责
   ============================================================ */
</style>
