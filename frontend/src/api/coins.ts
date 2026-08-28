import { http } from './http'

export interface CoinTransactionItem {
  id: number
  amount: number
  balance_after: number
  type: string
  ref_id: string | null
  description: string | null
  created_at: string
}

export interface BadgeShopItem {
  id: number
  name: string
  code: string
  icon: string
  description: string | null
  price: number
  owned: boolean
}

export function getCoinsMe() {
  return http.get<unknown, { data: { code: number; msg: string; data: { coins: number; onboarding_done: boolean } } }>(
    '/coins/me',
  )
}

/** 首次进入赠送 500 积分（一次性，幂等；granted=true 表示本次真正发放了新人礼） */
export function getWelcomeBonus() {
  return http.get<unknown, { data: { code: number; msg: string; data: { granted: boolean; coins: number; onboarding_done: boolean } } }>(
    '/coins/welcome-bonus',
  )
}

export function getCoinTransactions(page = 1, pageSize = 50) {
  return http.get<unknown, { data: { code: number; msg: string; data: { items: CoinTransactionItem[]; total: number } } }>(
    '/coins/transactions',
    { params: { page, page_size: pageSize } },
  )
}

export function getBadgeShop() {
  return http.get<unknown, { data: { code: number; msg: string; data: { items: BadgeShopItem[]; coins: number } } }>(
    '/coins/badges',
  )
}

export function purchaseBadge(badgeId: number) {
  return http.post<unknown, { data: { code: number; msg: string; data: { badge: BadgeShopItem; coins: number } } }>(
    `/coins/badges/${badgeId}/purchase`,
  )
}

export interface DailyMissionItem {
  key: string
  name: string
  icon: string
  desc: string
  reward: number
  target: number
  progress: number
  done: boolean
  claimed: boolean
}

export function getDailyMissions() {
  return http.get<unknown, { data: { code: number; msg: string; data: { coins: number; items: DailyMissionItem[] } } }>(
    '/coins/missions',
  )
}

export function claimDailyMission(key: string) {
  return http.post<unknown, { data: { code: number; msg: string; data: { awarded: number; message: string; coins: number; progress: number; target: number } } }>(
    `/coins/missions/${key}/claim`,
  )
}
