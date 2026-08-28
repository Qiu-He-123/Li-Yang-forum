import { defineStore } from 'pinia'
import { computed, onUnmounted, ref, watch } from 'vue'
import {
  getTodayGuess,
  placeGuessBet,
  skipGuessBet,
  type GuessItem,
  type MyBet,
  type TodayGuessResp,
} from '../api/guess'
import { useSessionStore } from './session'

export const useGuessStore = defineStore('guess', () => {
  const loading = ref(false)
  const error = ref('')
  const guess = ref<GuessItem | null>(null)
  const myBet = ref<MyBet | null>(null)
  const now = ref<string>('')

  /** 竞猜弹窗是否已关闭（登录时只弹一次）：true = 今天已看过/处理过 */
  const popupDismissedToday = ref(false)

  let timer: number | null = null

  function _parseApi(resp: TodayGuessResp) {
    guess.value = resp.guess
    myBet.value = resp.my_bet
    now.value = resp.now
  }

  async function load() {
    try {
      loading.value = true
      error.value = ''
      const r = await getTodayGuess({ showGlobalLoading: false, showGlobalError: false })
      _parseApi(r.data.data)
    } catch (err) {
      error.value = (err as Error).message || '今日竞猜加载失败'
      guess.value = null
    } finally {
      loading.value = false
    }
  }

  async function bet(optionId: number, amount: number) {
    if (!guess.value) throw new Error('竞猜未加载')
    const r = await placeGuessBet(guess.value.id, optionId, amount)
    myBet.value = r.data.data.bet
    guess.value = r.data.data.guess
    return myBet.value
  }

  async function skip() {
    if (!guess.value) throw new Error('竞猜未加载')
    const r = await skipGuessBet(guess.value.id)
    myBet.value = r.data.data.bet
    popupDismissedToday.value = true
    return myBet.value
  }

  /** 登录用户才需要启动实时轮询；焦点区实时显示数据。 */
  function startPolling() {
    stopPolling()
    // 立即拉一次
    load()
    timer = window.setInterval(() => {
      void load()
    }, 8000)
  }

  function stopPolling() {
    if (timer != null) {
      window.clearInterval(timer)
      timer = null
    }
  }

  onUnmounted(() => stopPolling())

  // 登录状态变化：若已登录 + 今日有竞猜 + 未回应（没押也没跳）→ 把弹窗标记重置（交给组件自己弹一次就行）
  const session = useSessionStore()
  watch(
    () => [session.userId, guess.value?.id] as const,
    ([uid, gid], [prevUid, prevGid]) => {
      if (uid !== prevUid || gid !== prevGid) {
        popupDismissedToday.value = false
      }
    },
    { immediate: false },
  )

  const needShowPopup = computed(() => {
    if (!session.userId) return false
    if (!guess.value) return false
    if (popupDismissedToday.value) return false
    if (myBet.value && (myBet.value.amount > 0 || myBet.value.skipped)) return false
    // 已截止/已结算 → 不再弹
    if (guess.value.settled_at) return false
    return true
  })

  return {
    loading,
    error,
    guess,
    myBet,
    now,
    popupDismissedToday,
    needShowPopup,
    load,
    bet,
    skip,
    startPolling,
    stopPolling,
    dismissPopup() {
      popupDismissedToday.value = true
    },
  }
})
