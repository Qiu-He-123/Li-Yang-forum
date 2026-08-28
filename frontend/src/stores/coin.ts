import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getCoinsMe, getWelcomeBonus } from '../api/coins'

export const useCoinStore = defineStore('coin', () => {
  const balance = ref(0)
  const onboardingDone = ref(false)
  const loaded = ref(false)

  async function loadBalance() {
    try {
      const r = await getCoinsMe()
      balance.value = r.data.data.coins
      onboardingDone.value = r.data.data.onboarding_done
      loaded.value = true
    } catch {
      loaded.value = true
    }
    return balance.value
  }

  /** 首次进入赠送 500 积分（一次性）。返回本次是否真正发放（granted）。 */
  async function claimWelcomeBonus() {
    try {
      const r = await getWelcomeBonus()
      balance.value = r.data.data.coins
      onboardingDone.value = r.data.data.onboarding_done
      loaded.value = true
      return r.data.data
    } catch {
      loaded.value = true
      return null
    }
  }

  function add(delta: number) {
    balance.value = Math.max(0, balance.value + delta)
  }

  return { balance, onboardingDone, loaded, loadBalance, claimWelcomeBonus, add }
})
